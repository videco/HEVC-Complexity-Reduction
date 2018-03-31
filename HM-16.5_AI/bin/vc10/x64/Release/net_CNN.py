#coding=utf-8

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
import tensorflow as tf

IMAGE_SIZE = 64

NUM_CHANNELS = 1 

NUM_EXT_FEATURES = 1 
NUM_LABEL_BYTES = 16

NUM_CONVLAYER1_FILTERS = 16
NUM_CONVLAYER2_FILTERS = 24
NUM_CONVLAYER3_FILTERS = 32

NUM_CONV2_FLAT_S_FILTERS = 8 * 8 * NUM_CONVLAYER2_FILTERS
NUM_CONV2_FLAT_M_FILTERS = 4 * 4 * NUM_CONVLAYER2_FILTERS
NUM_CONV2_FLAT_L_FILTERS = 2 * 2 * NUM_CONVLAYER2_FILTERS

NUM_CONV3_FLAT_S_FILTERS = 4 * 4 * NUM_CONVLAYER3_FILTERS 
NUM_CONV3_FLAT_M_FILTERS = 2 * 2 * NUM_CONVLAYER3_FILTERS 
NUM_CONV3_FLAT_L_FILTERS = 1 * 1 * NUM_CONVLAYER3_FILTERS 

NUM_CONVLAYER_FLAT_FILTERS = NUM_CONV2_FLAT_S_FILTERS + NUM_CONV2_FLAT_M_FILTERS + NUM_CONV2_FLAT_L_FILTERS + NUM_CONV3_FLAT_S_FILTERS + NUM_CONV3_FLAT_M_FILTERS + NUM_CONV3_FLAT_L_FILTERS

NUM_DENLAYER1_FEATURES_64 = 64        
NUM_DENLAYER2_FEATURES_64 = 48

NUM_DENLAYER1_FEATURES_32 = 128       
NUM_DENLAYER2_FEATURES_32 = 96 

NUM_DENLAYER1_FEATURES_16 = 256       
NUM_DENLAYER2_FEATURES_16 = 192    

def get_thresholds(thr_file):
    f = open(thr_file,'r+')
    line=f.readline()
    str_arr=line.split(' ')
    thr_l1_lower = float(str_arr[1])  
    thr_l2_lower = float(str_arr[3])
    f.close()
    return thr_l1_lower, thr_l2_lower  

THR_L1_LOWER, THR_L2_LOWER = get_thresholds('Thr_info.txt')

# weight initialization
def weight_variable(shape, name=None):
    initial = tf.truncated_normal(shape, stddev=0.1)
    return tf.Variable(initial, name=name)

def bias_variable(shape, name=None):
    initial = tf.truncated_normal(shape, stddev=0.1)
    return tf.Variable(initial, name=name)
 	
# convolution
def conv2d(x, W):
    return tf.nn.conv2d(x, W, strides=[1, 1, 1, 1], padding='VALID')

def aver_pool(x, k_width):
    return tf.nn.avg_pool(x, ksize=[1, k_width, k_width, 1], strides=[1, k_width, k_width, 1], padding='SAME')

def activate(x, acti_mode):
    if acti_mode==0:
        return x
    elif acti_mode==1:
        return tf.nn.leaky_relu(x)
    elif acti_mode==2:
        return tf.nn.sigmoid(x)
    
def zero_mean_norm_global(x, reduce_axis=[1,2,3], tile_multiples=[1,64,64,1]):
    x_mean_reduced=tf.reduce_mean(x,axis=reduce_axis,keep_dims=True)
    x_mean_tiled=tf.tile(x_mean_reduced,tile_multiples)
    return x-x_mean_tiled

def zero_mean_norm_local(x, x_width, kernel_width):
    w_norm = tf.constant(1.0/(kernel_width*kernel_width), tf.float32, shape=[kernel_width, kernel_width,1,1])
    x_mean_reduced = tf.nn.conv2d(x, w_norm, [1, kernel_width, kernel_width, 1],'VALID')
    x_mean_expanded = tf.image.resize_nearest_neighbor(x_mean_reduced, [x_width, x_width])
    print(x_mean_reduced)
    print(x_mean_expanded)
    return x-x_mean_expanded

def non_overlap_conv(x, k_width, num_filters_in, num_filters_out, acti_mode):
    w_conv = weight_variable([k_width, k_width, num_filters_in, num_filters_out])
    b_conv = bias_variable([num_filters_out])
    h_conv = tf.nn.conv2d(x, w_conv, strides=[1, k_width, k_width, 1], padding='VALID') + b_conv
    h_conv = activate(h_conv, acti_mode)
    print(h_conv)
    return(h_conv)    

def full_connect(x, num_filters_in, num_filters_out, acti_mode, keep_prob=1, name_w=None, name_b=None): 
    w_fc = weight_variable([num_filters_in, num_filters_out], name_w)
    b_fc = bias_variable([num_filters_out], name_b)
    h_fc = tf.matmul(x, w_fc) + b_fc
    h_fc = activate(h_fc, acti_mode)
    h_fc = tf.cond(keep_prob < tf.constant(1.0), lambda: tf.nn.dropout(h_fc, keep_prob), lambda: h_fc)
    print(h_fc) 
    return h_fc

def net(x,y_,qp,isdrop):
    
    x = tf.scalar_mul(1.0 / 255.0, x)
    qp = tf.scalar_mul(1 / 51.0, qp)
    x_image = tf.reshape(x, [-1, IMAGE_SIZE, IMAGE_SIZE, NUM_CHANNELS])
    y_image = tf.reshape(y_, [-1, 4, 4, 1])
    
    y_image_16 = tf.nn.relu(y_image-2)
    y_image_32 = tf.nn.relu(aver_pool(y_image, 2)-1)-tf.nn.relu(aver_pool(y_image, 2)-2)
    y_image_64 = tf.nn.relu(aver_pool(y_image, 4)-0)-tf.nn.relu(aver_pool(y_image, 4)-1)
    y_image_valid_32 = tf.nn.relu(aver_pool(y_image, 2)-0)-tf.nn.relu(aver_pool(y_image, 2)-1)
    y_image_valid_16 = tf.nn.relu(y_image-1)-tf.nn.relu(y_image-2)
    
    y_flat_16 = tf.reshape(y_image_16, [-1, 16])
    y_flat_32 = tf.reshape(y_image_32, [-1, 4])
    y_flat_64 = tf.reshape(y_image_64, [-1, 1])
    
    y_flat_valid_32 = tf.reshape(y_image_valid_32, [-1, 4])
    y_flat_valid_16 = tf.reshape(y_image_valid_16, [-1, 16])

    #----------------------------------------------------------------------------------------------------------------------------------------------------------
    acti_mode_conv = 1
    # for extracting textures of 64*64 CTUs
    h_image_L = zero_mean_norm_local(aver_pool(x_image, 4), 16, 16)
    h_conv1_L = non_overlap_conv(h_image_L, 4, NUM_CHANNELS, NUM_CONVLAYER1_FILTERS, acti_mode = acti_mode_conv)
    h_conv2_L = non_overlap_conv(h_conv1_L, 2, NUM_CONVLAYER1_FILTERS, NUM_CONVLAYER2_FILTERS, acti_mode = acti_mode_conv)
    h_conv3_L = non_overlap_conv(h_conv2_L, 2, NUM_CONVLAYER2_FILTERS, NUM_CONVLAYER3_FILTERS, acti_mode = acti_mode_conv)
    
    # for extracting textures of 32*32 CTUs
    h_image_M = zero_mean_norm_local(aver_pool(x_image, 2), 32, 16)
    h_conv1_M = non_overlap_conv(h_image_M, 4, NUM_CHANNELS, NUM_CONVLAYER1_FILTERS, acti_mode = acti_mode_conv)
    h_conv2_M = non_overlap_conv(h_conv1_M, 2, NUM_CONVLAYER1_FILTERS, NUM_CONVLAYER2_FILTERS, acti_mode = acti_mode_conv)
    h_conv3_M = non_overlap_conv(h_conv2_M, 2, NUM_CONVLAYER2_FILTERS, NUM_CONVLAYER3_FILTERS, acti_mode = acti_mode_conv)
    
    # for extracting textures of 16*16 CTUs
    h_image_S = zero_mean_norm_local(x_image, 64, 16)
    h_conv1_S = non_overlap_conv(h_image_S, 4, NUM_CHANNELS, NUM_CONVLAYER1_FILTERS, acti_mode = acti_mode_conv)
    h_conv2_S = non_overlap_conv(h_conv1_S, 2, NUM_CONVLAYER1_FILTERS, NUM_CONVLAYER2_FILTERS, acti_mode = acti_mode_conv)
    h_conv3_S = non_overlap_conv(h_conv2_S, 2, NUM_CONVLAYER2_FILTERS, NUM_CONVLAYER3_FILTERS, acti_mode = acti_mode_conv)
    
    h_conv3_S_flat = tf.reshape(h_conv3_S, [-1, NUM_CONV3_FLAT_S_FILTERS])
    h_conv3_M_flat = tf.reshape(h_conv3_M, [-1, NUM_CONV3_FLAT_M_FILTERS])
    h_conv3_L_flat = tf.reshape(h_conv3_L, [-1, NUM_CONV3_FLAT_L_FILTERS])    
    h_conv2_S_flat = tf.reshape(h_conv2_S, [-1, NUM_CONV2_FLAT_S_FILTERS])
    h_conv2_M_flat = tf.reshape(h_conv2_M, [-1, NUM_CONV2_FLAT_M_FILTERS])
    h_conv2_L_flat = tf.reshape(h_conv2_L, [-1, NUM_CONV2_FLAT_L_FILTERS])

    h_conv_flat = tf.concat( values=[h_conv3_S_flat, h_conv3_M_flat, h_conv3_L_flat, h_conv2_S_flat, h_conv2_M_flat, h_conv2_L_flat], axis=1)
    print(h_conv_flat)

    acti_mode_fc = 1
    #-------------------------------------------------------------------------------------------------------------------------------------------------------------

    h_fc1_64 = full_connect(h_conv_flat, NUM_CONVLAYER_FLAT_FILTERS, NUM_DENLAYER1_FEATURES_64, 
                            acti_mode=acti_mode_fc, keep_prob=1-isdrop*0.5, name_w='h_fc1__64__w', name_b='h_fc1__64__b')
    h_fc1_64 = tf.concat([h_fc1_64, qp], axis=1)
    h_fc2_64 = full_connect(h_fc1_64, NUM_DENLAYER1_FEATURES_64 + NUM_EXT_FEATURES, NUM_DENLAYER2_FEATURES_64, 
                            acti_mode=acti_mode_fc, keep_prob=1-isdrop*0.2, name_w='h_fc2__64__w', name_b='h_fc2__64__b')    
    h_fc2_64 = tf.concat([h_fc2_64, qp], axis=1)
    y_conv_flat_64 = full_connect(h_fc2_64, NUM_DENLAYER2_FEATURES_64 + NUM_EXT_FEATURES, 1, 
                            acti_mode = 2 , name_w='y_conv_flat__64__w', name_b='y_conv_flat__64__b')


    h_fc1_32 = full_connect(h_conv_flat, NUM_CONVLAYER_FLAT_FILTERS, NUM_DENLAYER1_FEATURES_32, 
                            acti_mode=acti_mode_fc, keep_prob=1-isdrop*0.5, name_w='h_fc1__32__w', name_b='h_fc1__32__b')
    h_fc1_32 = tf.concat([h_fc1_32, qp], axis=1)
    h_fc2_32 = full_connect(h_fc1_32, NUM_DENLAYER1_FEATURES_32 + NUM_EXT_FEATURES, NUM_DENLAYER2_FEATURES_32, 
                            acti_mode=acti_mode_fc, keep_prob=1-isdrop*0.2, name_w='h_fc2__32__w', name_b='h_fc2__32__b')
    h_fc2_32 = tf.concat([h_fc2_32, qp], axis=1)
    y_conv_flat_32_temp = full_connect(h_fc2_32, NUM_DENLAYER2_FEATURES_32 + NUM_EXT_FEATURES, 4, 
                            acti_mode = 2, name_w='y_conv_flat__32__w', name_b='y_conv_flat__32__b')

    y_conv_flat_32 = tf.cond(tf.count_nonzero(y_conv_flat_64 > THR_L1_LOWER) > 0, lambda: y_conv_flat_32_temp, lambda: tf.zeros([tf.shape(y_conv_flat_64)[0], 4], tf.float32))


    h_fc1_16 = full_connect(h_conv_flat, NUM_CONVLAYER_FLAT_FILTERS, NUM_DENLAYER1_FEATURES_16, 
                            acti_mode=acti_mode_fc, keep_prob=1-isdrop*0.5, name_w='h_fc1__16__w', name_b='h_fc1__16__b')
    h_fc1_16 = tf.concat([h_fc1_16, qp], axis=1)
    h_fc2_16 = full_connect(h_fc1_16, NUM_DENLAYER1_FEATURES_16 + NUM_EXT_FEATURES, NUM_DENLAYER2_FEATURES_16, 
                            acti_mode=acti_mode_fc, keep_prob=1-isdrop*0.2, name_w='h_fc2__16__w', name_b='h_fc2__16__b')
    h_fc2_16 = tf.concat([h_fc2_16, qp], axis=1)
    y_conv_flat_16_temp = full_connect(h_fc2_16, NUM_DENLAYER2_FEATURES_16 + NUM_EXT_FEATURES, 16, 
                            acti_mode = 2, name_w='y_conv_flat__16__w', name_b='y_conv_flat__16__b')

    y_conv_flat_16 = tf.cond(tf.count_nonzero(y_conv_flat_32 > THR_L2_LOWER) > 0, lambda: y_conv_flat_16_temp, lambda: tf.zeros([tf.shape(y_conv_flat_64)[0], 16], tf.float32))



    
    
    opt_vars_all = [v for v in tf.trainable_variables()]
    
    return y_flat_64, y_flat_32, y_flat_16, y_conv_flat_64, y_conv_flat_32, y_conv_flat_16, opt_vars_all
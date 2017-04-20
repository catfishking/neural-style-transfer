# Copyright 2016 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

'''ResNet model.
    Related papers:
    https://arxiv.org/pdf/1603.05027v2.pdf
    https://arxiv.org/pdf/1512.03385v1.pdf
    https://arxiv.org/pdf/1605.07146v1.pdf
    Reference:
    https://github.com/tensorflow/models/blob/master/resnet/resnet_model.py
'''
import time
import numpy as np
import tensorflow as tf
import vgg_19
import utils
from tensorflow.python.client import timeline


#config = tf.ConfigProto(allow_soft_placement=True)
#config = tf.ConfigProto()
#config.gpu_options.allow_growth=True

class StyleGenerator():
    def __init__(self,input_size, mode='train'):
        '''
            input_size: height or weight
            mode: 'train' or 'test'
        '''
        self.input_size = input_size
        self.mode = mode
        self.alpha = 1.
        self.beta = 1.


    def build_graph(self):
        self._build_model()
        #XXX
        #if self.mode == 'train':
        #    self._build_train_op()
        #self.summaries = tf.summary.merge_all()


    def _stride_arr(self,stride):
        '''Map a stride scalar to the stride array for tf.nn.conv2d.'''
        return [1, stride, stride, 1]

    def _out_shape(self, x, shape, out_dim):
        ''' Build out_shape array for tf.nn.conv2d_transpose '''
        # use tf.shape(x)[0] to obtain batch size
        return [ tf.shape(x)[0],shape,shape,out_dim]

    # TODO: use args to pass arch opts
    def _build_model(self):
        with tf.variable_scope('init'):
            self.x_input = tf.placeholder(tf.float32,[None, self.input_size, self.input_size, 3])
            x = self._conv('init_conv', self.x_input, 9, 3, 32,self._stride_arr(1))
            x = self._batch_norm('bn',x)
        #activate_before_residual = [True, False, False]
        filters = [32, 64, 128,64,32,3]
        
        with tf.variable_scope('dsample_1'):
            x = self._conv('ds64', x, 3,filters[0],filters[1],self._stride_arr(2) )
            x = self._relu(x)
            x = self._batch_norm('bn',x)
        with tf.variable_scope('dsample_2'):
            x = self._conv('ds128', x, 3,filters[1],filters[2], self._stride_arr(2))
            x = self._relu(x)
            x = self._batch_norm('bn',x)
        
        for i in range(5): # five residual blocks
            with tf.variable_scope('res_block_{}'.format(i)):
                x = self._residual(x,filters[2],filters[2], self._stride_arr(1))
        
        # NOTE google brain use nearest neighbors + cnn
        with tf.variable_scope('usample_1'):
            x = self._conv_trans('us64', x, 3, filters[2], filters[3], self._stride_arr(2),\
                    self._out_shape(x, 128, filters[3]))
            x = self._relu(x)
            x = self._batch_norm('bn',x)
        with tf.variable_scope('usample_2'):
            x = self._conv_trans('us32', x, 3, filters[3], filters[4], self._stride_arr(2),\
                    self._out_shape(x, 256, filters[4]))
            x = self._relu(x)
            x = self._batch_norm('bn',x)
        
        with tf.variable_scope('last'):
            x = self._conv('last_conv', x, 9, filters[4], filters[5],self._stride_arr(1))
            x = self._batch_norm('bn',x)
            self.out = tf.nn.tanh(x) * 150 + 255./2
        
        return self.out

        # XXX
        '''
        with tf.variable_scope('vgg'):
            self.vgg = vgg_19.VGG19('./model/vgg19.npy', x=x, HEIGHT=256, WIDTH=256)
        with tf.variable_scope('cost'):
            content_loss = self.vgg.set_content_loss()
            style_loss = self.vgg.set_style_loss()
            self.cost = self.alpha*content_loss + self.beta*style_loss
            # TODO: add L2 norm
            tf.summary.scalar('cost',self.cost)
        '''

    # NOTE: use argv to pass some options
    '''
    def _build_train_op(self):
        """Build training specific ops for the graph."""

        optimizer = tf.train.AdamOptimizer()
        self.train_step = optimizer.minimize(self.cost)
    '''
    # NOTE: use batch_norm in tf layers
    def _batch_norm(self,name,x):
        if self.mode == 'train':
            BN = tf.contrib.layers.batch_norm(x,center=True,scale=True,\
                epsilon=1e-5,is_training=True,scope=name)
        else:
            BN = tf.contrib.layers.batch_norm(x,center=True,scale=True,\
                    epsilon=1e-5,is_training=False,scope=name)
        return BN


    def _conv(self,name,x,filter_size,in_filters,out_filters,stride):
        ''' Convolution '''
        with tf.variable_scope(name):
            n = filter_size * filter_size * out_filters
            # NOTE not use shared variable
            #kernel = tf.get_variable('W',[filter_size,filter_size,in_filters,out_filters],\
            #        tf.float32,initializer=tf.random_normal_initializer(stddev=np.sqrt(2.0/n)))
            kernel = tf.Variable(tf.random_normal([filter_size,filter_size,in_filters,out_filters]),\
                    name = 'W')
            return tf.nn.conv2d(x,kernel,stride,padding='SAME')

    def _conv_trans(self, name, x, filter_size, in_filters, out_filters, stride, out_shape):
        ''' transpose convolution '''
        with tf.variable_scope(name):
            kernel = tf.Variable(tf.random_normal([filter_size,filter_size, out_filters, in_filters]),\
                    name = 'W')
            x = tf.nn.conv2d_transpose(x, kernel, out_shape, stride, padding='SAME')

            # NOTE after conv2d_transpose, dim info loss... use this hack keep static dim info
            x = tf.reshape(x,out_shape)
            return x

    def _residual(self,x,in_filter,out_filter,stride):
        orig_x = x
        with tf.variable_scope('sub1'):
            x = self._conv('conv1', x, 3, in_filter, out_filter, stride)
            x = self._batch_norm('bn1',x)
            x = self._relu(x)

        with tf.variable_scope('sub2'):
            x = self._conv('conv2', x, 3, in_filter, out_filter, stride)
            x = self._batch_norm('bn2',x)

        with tf.variable_scope('sub_add'):
            if in_filter != out_filter:
                orig_x = tf.nn.avg_pool(orig_x, stride, stride, 'VALID')
                orig_x = tf.pad(orig_x, [[0, 0], [0, 0], [0, 0],\
                                [(out_filter-in_filter)//2, (out_filter-in_filter)//2]])
            x += orig_x
        return x

    # TODO pass relu leakiness argvs
    def _relu(self,x,leakiness=0.0):
        return tf.where(tf.less(x, 0.0), leakiness * x, x, name='leaky_relu' )
 

def set_loss(style_img):

    style_loss = 0.
    content_loss = 0.
    with tf.Graph().as_default(), tf.Session() as sess:
        style_image = tf.placeholder(tf.float32, shape=[1,256,256,3], name='style_image')
        style_net = vgg_19.VGG19('./model/vgg19.npy',x=style_image,HEIGHT=256,WIDTH=256)
        style_layers = ['conv1_1', 'conv2_1', 'conv3_1', 'conv4_1', 'conv5_1']

        def gram_matrix(conv,N,M):
            matrix = tf.reshape(conv,(M,N))
            return tf.matmul(tf.transpose(matrix), matrix)

        style_mat = {}

        for l in style_layers:
            style_layer = sess.run([style_net.model[l]],feed_dict={style_image:style_img})
            style_layer = style_layer[0]
            N = style_layer.shape[3]
            M = style_layer.shape[1]*style_layer.shape[2]

            matrix = np.reshape(style_layer,(M,N))
            G = np.dot(matrix.T, matrix)

            style_mat[l] = G
                
    with tf.Graph().as_default(), tf.Session() as sess:
        content_image = tf.placeholder(tf.float32, shape=[None, 256, 256, 3], name='content_image')
        content_net = vgg_19.VGG19('./model/vgg19.npy', x=content_image, HEIGHT=256,WIDTH=256)

        model = StyleGenerator(256)
        model.build_graph()
        net = vgg_19.VGG19('./model/vgg19.npy', x=model.out, HEIGHT=256, WIDTH=256)

        content_layers = ['conv4_2']
        #content_layers = ['input']
        content_layer = content_net.model[content_layers[0]]
        N = content_layer.get_shape().as_list()[3]
        M = content_layer.get_shape().as_list()[1]*content_layer.get_shape().as_list()[2]

        content_loss = 1./(2. * M * N) * tf.reduce_sum(tf.pow((content_net.model[content_layers[0]] -\
                                                net.model[content_layers[0]]),2))


        for l in style_layers:
            style_layer = net.model[l]
            N = style_layer.get_shape().as_list()[3]
            M = style_layer.get_shape().as_list()[1]*style_layer.get_shape().as_list()[2]
            B = tf.shape(style_layer)[0]

            matrix = tf.reshape(style_layer,(B,M,N))
            A = tf.matmul(tf.transpose(matrix,perm=[0, 2, 1]), matrix)

            style_loss += 1./(4.* M**2 * N**2)* tf.reduce_sum(tf.pow(style_mat[l]-A,2)) * 1./5.

        Loss =  model.alpha * content_loss + model.beta * style_loss*0.
        optimizer = tf.train.AdamOptimizer(learning_rate=1).minimize(Loss)
        
        in_image_bufffer = tf.summary.image('input_image',model.x_input, max_outputs=2)
        out_image_buffer = tf.summary.image('output_image',model.out, max_outputs=2)
        tf.summary.scalar("loss", Loss)
        summary_op = tf.summary.merge_all()
        
        batch_size = 20
        data_batch = utils.coco_input('/tmp3/troutman/COCO/train2014_256', batch_size)
        #data_batch = utils.coco_input('/tmp3/troutman/COCO/debug', batch_size)
        nb_batch = 82784/batch_size

        init = tf.global_variables_initializer()

        writer = tf.summary.FileWriter('./log', graph=tf.get_default_graph())
        print('start training')
        sess.run(init)
        coord = tf.train.Coordinator()
        threads = tf.train.start_queue_runners(coord = coord)
        for ep in xrange(200):
            ep_time = time.time()
            ep_loss = 0.
            for bs in xrange(nb_batch):
                image = sess.run(data_batch)
                print image.shape
                _, loss,out,summary = sess.run([optimizer, Loss, model.out,summary_op],\
                        feed_dict={model.x_input:image,content_image:image})
                print bs,loss
                writer.add_summary(summary, ep * nb_batch + bs)

                if bs % 10 == 9:
                    print 'save'
                    utils.save_rgb('haha.jpg'.format(ep,bs),out[0][np.newaxis,:])
            print('Epoch:{:4} Loss:{:f} Time:{:f}seconds'.format(ep,ep_loss/nb_batch,time.time()-ep_time))

        coord.request_stop()
        coord.join(threads)


if __name__ == '__main__':
    
    style_img = utils.load_rgb('./image/StarryNight_256.jpg')
    set_loss(style_img)
       

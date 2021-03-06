from os import listdir
from os.path import isfile, isdir, join, splitext, basename, dirname
import sys
import argparse
import numpy as np
import cv2
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
from _init_paths import *
from util import *
from signdet import *
from speeddet import *
from objdet import *
from lightdet import *
import pickle
import time
import logging
import shutil

logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)
fullname = {
    'vf':'Forward Velocity',
    'wu':'Upward angular velocity',
    'af':'Forward Acceleration'
}
unit = {
    'vf':'m/s',
    'wu':'deg/sec',
    'af':'m/s^2'
}

def roadSignMatching(frame, org, sn):
    sign = cv2.imread(signs[sn])
    sign = cv2.GaussianBlur(sign,(5,5),0)
    img = match(sign, frame, org, draw=True, drawKeyPoint=False, ratioTestPct=0.7, minMatchCnt=5)
    return img

def setInputShape(im, **options):
    H,W,_ = im.shape
    speedmode = options['speedmode']
    if speedmode==0:
        C = 2 # flow
    elif speedmode==1:
        C = 3 # flow + objmask
    elif speedmode==2:
        C = 5 # flow + rgb
    elif speedmode==3:
        C = 6 # flow + objmask + rgb
    elif speedmode==4:
        C = 3 # rgb
    options['inputshape'] = (H,W,C)
    return options

def restoreModel(**options):
    modelname = options['model']
    speedmode = options['speedmode']
    mode = options['mode']
    path = options['path']
    options['path'] = '/home/ubuntu/project/cs231n/kitti/2011_09_26_drive_0117_sync/data'
    if options['testpath'] == '':
        options['testpath'] = '/home/ubuntu/project/cs231n/kitti/2011_09_26_drive_0117_sync/data'
    if mode in ['testspeed', 'all']:
        path = options['testpath']
        options['path'] = path
    fn = '0000000001.png'
    im = cv2.imread(join(path, fn), cv2.IMREAD_COLOR)
    options = setInputShape(im, **options)
    if mode in ['all', 'testspeed']:
        if modelname=='conv':
            from convmodel import ConvModel, get_model_path
            model_path = get_model_path(**options)
            if isfile(model_path + "model.conf"):
                restored_options = pickle.load(open(model_path + "model.conf", "rb" ))
                restored_options['mode'] = options['mode']
                restored_options['numframe'] = options['numframe']
                restored_options['testpath'] = options['testpath']
                restored_options['path'] = options['path']
                options = restored_options
            else:
                print("No stored configuration available! use current configuration!")
            model = ConvModel(options)
            model.restore()
        elif modelname=='linear':
            pass #TODO
    return model, options

def play(framePaths, **options):
    model = options['model']
    mode = options['mode']
    speedmode = options['speedmode']
    sample_every = options['sample_every']
    includeflow, includeobj, includeimg = lookup(speedmode)

    #options['path']='/home/ubuntu/project/cs231n/kitti/2011_09_26_drive_0117_sync/data/'
    
    path = options['path']
    if mode in ['testspeed', 'all']:
        path = options['testpath']
        options['path'] = options['testpath']
        if options['if_kitti']==1:
            if options['if_af']==1:
                out = './' + 'kitti_af_1/' + path.split('/')[-2]
            elif options['if_af']==0:
                out = './' + 'kitti_af_0/' + path.split('/')[-2]
            elif options['if_af']==2:
                out = './' + 'kitti_af_2/' + path.split('/')[-2]
            elif options['if_af']==3:
                out = './' + 'kitti_af_3/' + path.split('/')[-2]
        else:
            if options['if_af']==1:
                out = './' + 'own_af_1/' + path.split('/')[-2]
            elif options['if_af']==0:
                out = './' + 'own_af_0/' + path.split('/')[-2]
            elif options['if_af']==2:
                out = './' + 'own_af_2/' + path.split('/')[-2]
            elif options['if_af']==3:
                out = './' + 'own_af_3/' + path.split('/')[-2]

        if os.path.isdir(out):
            shutil.rmtree(out)
        os.mkdir(out)
        os.mkdir(join(out,"output"))
        if options['if_af']==1 or options['if_af']==0:
            file_out = open(join(join(out,"output"),"motion.txt") , 'w')
        elif options['if_af']==2:
            file_out = open(join(join(out,"output"),"motion_vf.txt") , 'w')
        elif options['if_af']==3:
            file_out = open(join(join(out,"output"),"motion_wu.txt") , 'w')
        test_mses = {}

    print('Playing video {}'.format(path))
    files = [f for f in listdir(path) if isfile(join(path, f)) and f.endswith('.png')]
    files = sorted(files)

    #if mode in ['loadmatch', 'all']:
       #matches = mcread(path)
    if mode in ['trainspeed', 'all', 'testspeed']:
        headers = loadHeader('{0}/../oxts'.format(path))
        im = cv2.imread(join(path, files[0]), cv2.IMREAD_COLOR)
        options = setInputShape(im, **options)
    if options['if_af']==1:
        labels = dict(vf=[], wu=[], af=[])
    elif options['if_af']==0:
        labels = dict(vf=[], wu=[])
    elif options['if_af']==2:
        labels = dict(vf=[])
    elif options['if_af']==3:
        labels = dict(wu=[])
    img = None
    icmp = None
    porg = None
    if (mode not in ['trainspeed', 'testspeed']):
      plt.figure(dpi=140)
    for i, impath in enumerate(files):
        if mode in ['trainspeed', 'testspeed', 'all']:
            if (i % sample_every) != 0:
                continue
        fn, ext = splitext(impath)
        if i<options['startframe']:
            continue
        if options['endframe']>0 and i>options['endframe']:
            break
        if options['numframe']>0 and i>(options['startframe'] + options['numframe']):
            break

        root, ext = splitext(impath)
        im = cv2.imread(join(path, impath), cv2.IMREAD_COLOR)
        org = im.copy()

        options['fn'] = fn
        if mode == 'roadsign':
            im = roadSignMatching(im, org, options['sign'])
        elif mode == 'loadmatch':
            im,_ = loadMatch(im, org, icmp, fn, matches)
        elif mode == 'detlight':
            im,icmp = detlight(im, org, mode='compare')
        elif mode == 'flow':
            if porg is not None:
                options['flowmode'] = 'avgflow'
                im = detflow(im, porg, org, **options)
        elif mode == 'objdet':
            scores, boxes = getObj(im, checkcache=False, **options)
            icmp = getObjChannel(im, checkcache=False, **options)
            icmp = icmp[:,:,0].squeeze() # plot 1 interested channel
        elif mode == 'trainspeed':
            if porg is not None:
                H,W,_ = im.shape
                # speedX = np.zeros((H,W,0))
                if includeflow:
                    if model=='linear':
                        polarflow(porg, org, checkcache=True, **options)
                    elif model=='conv':
                        getflow(porg, org, checkcache=True, **options)
                    # speedX = np.concatenate((speedX,flow), axis=-1)
                if includeobj:
                    getObjChannel(im, checkcache=True, **options)
                    # speedX = np.concatenate((speedX,objchannel), axis=-1)
                # if includeimg:
                    # speedX = np.concatenate((speedX,im), axis=-1)
                framePath = join(path, impath)
                framePaths.append(framePath)
                # print('speedmode={} speedX.shape={}'.format(speedmode, np.array(speedX).shape))
                # loadLabels(fn, headers, labels, '{0}/../oxts'.format(path))
        elif mode == 'test':
            sp = 30
            sr = 30
            im = cv2.pyrMeanShiftFiltering(im, sp, sr, maxLevel=1)
        elif mode == 'all':
            h,w,_ = im.shape
            h = 200
            icmp = np.ones((h,w,3), np.uint8) * 255
            im, ans = predSpeed(im, porg, org, labels, restored_model, '{0}/../oxts'.format(path), **options)
            # im, lights = detlight(im, org, mode='label')
            # if options['detsign']:
                # im, signs = loadMatch(im, org, fn, matches)
            scores, boxes = getObj(im, checkcache=False, **options)

            info = []
            info.append('Frame: {0}'.format(fn))
            for k in ans:
                if k not in test_mses:
                    test_mses[k] = []
                pred, gt = ans[k]
                mse = (pred - gt) ** 2
                test_mses[k].append(mse)
                if k=='wu':
                    pred = np.rad2deg(pred)
                    gt = np.rad2deg(gt)
                info.append('Predicted {}: {} {}. Ground Truth: {} {}'.format(fullname[k], pred,
                    unit[k], gt, unit[k]))
            if 'vf' in ans and 'wu' in ans:
                speed,_ = ans['vf']
                angle,_ = np.rad2deg(ans['wu'])
                if (speed > 2):
                    if abs(angle)<2:
                        state = 'Forward'
                    elif angle < 0:
                        state = 'Turning Right'
                    else:
                        state = 'Turning Left'
                else:
                    state = 'Still'
                info.append('Current state: {0}'.format(state))
                file_out.write(str(speed) + " " + str(ans['wu']) + "\n")
            elif 'vf' in ans:
                speed,_ = ans['vf']
                file_out.write(str(speed) + "\n")
            elif 'wu' in ans:
                angle,_ = np.rad2deg(ans['wu'])
                if abs(angle)<2:
                    state = 'Forward'
                elif angle < 0:
                    state = 'Turning Right'
                else:
                    state = 'Turning Left'
                info.append('Current state: {0}'.format(state))
                file_out.write(str(ans['wu']) + "\n")
            # info.append('Current lights: [{0}]'.format(','.join(lights)))
            # if options['detsign']:
                # info.append('Current signs: [{0}]'.format(','.join(signs)))

            h = icmp.shape[0]
            for i, text in enumerate(info):
                coord = (20, h * (i+1)/(len(info)+1))
                fontface = cv2.FONT_HERSHEY_SIMPLEX;
                if iscv2():
                    cv2.putText(img=icmp, text=text, org=coord, fontFace=fontface, fontScale=0.6,
                        color=bgr('k'), thickness=2, lineType=8);
                elif iscv3():
                    icmp = cv2.putText(img=icmp, text=text, org=coord, fontFace=fontface, fontScale=0.6,
                        color=bgr('k'), thickness=2, lineType=8);
            loadLabels(fn, headers, labels, '{0}/../oxts'.format(path))
        if mode in ['testspeed']:
            im, ans = predSpeed(im, porg, org, labels, restored_model, '{0}/../oxts'.format(path), **options)
            for k in ans:
                if k not in test_mses:
                    test_mses[k] = []
                pred, gtruth = ans[k]
                mse = (pred - gtruth) ** 2
                test_mses[k].append(mse)
            loadLabels(fn, headers, labels, '{0}/../oxts'.format(path))
        porg = org.copy()

        if mode in ['trainspeed', 'testspeed']:
            continue

        im = cv2.cvtColor(im, cv2.COLOR_BGR2RGB)
        if icmp is not None:
            if mode not in ['objdet']:
                icmp = cv2.cvtColor(icmp, cv2.COLOR_BGR2RGB)

        if img is None:
            if icmp is not None:
                imgax = plt.subplot(2,1,1)
                imgoax = plt.subplot(2,1,2)
            else:
                imgax = plt.subplot()

        if icmp is not None:
            if mode in ['objdet']:
                imgo = plt.imshow(icmp, cmap='Greys', interpolation='nearest')
            else:
                imgo = plt.imshow(icmp)
            img = imgax.imshow(im)
        else:
            img = imgax.imshow(im)

        if mode in ['objdet', 'all'] and imgax is not None:
            drawObj(imgax, scores, boxes, **options)

        plt.savefig(join(out, impath))
        #plt.pause(options['delay'])
        if imgax is not None:
            imgax.clear()

    if mode in ['testspeed', 'all']:
        file_out.close()
        for k in test_mses:
            print('Overall averaged test mse {}: {}'.format(k, np.sum(test_mses[k])/len(test_mses[k])))
    return options

def demo(**options):
    options['path'] = '/home/ubuntu/project/cs231n/kitti/2011_09_26-3/data'
    options['startframe'] = 100
    options['endframe'] = 125
    play([], **options)
    options['path'] = '/home/ubuntu/project/cs231n/kitti/2011_09_26-1/data'
    options['startframe'] = 0
    options['endframe'] = 30
    play([], **options)

def trainModel(**options):
    print('Configuration: pid={}'.format(os.getpid()))
    sys.stdout.flush()
    framePaths = []

    if options['if_kitti']==1:
        dirs = [join(KITTI_PATH, d) for d in listdir(KITTI_PATH) if isdir(join(KITTI_PATH, d))]
    else:
        dirs = [join(OWN_PATH, d) for d in listdir(OWN_PATH) if isdir(join(OWN_PATH, d))]
    for vdir in dirs:
        options['path'] = '{0}/data/'.format(vdir)
        if options['path']==options['testpath']+'/':
            continue
        options = play(framePaths, **options)
        sys.stdout.flush()
    print('Configuration: num_frames={}'.format(len(framePaths)))
    return trainSpeed(framePaths, **options)

def main():
    usage = "Usage: play [options --path]"
    parser = argparse.ArgumentParser(description='Visualize a sequence of images as video')
    parser.add_argument('--demo', dest='demo', action='store_true',default=False,
        help='Demo mode')
    parser.add_argument('--testpath', dest='testpath', action='store', default='',
            help='Specify path for testing of speed detection')
    parser.add_argument('--path', dest='path', action='store', default='',
            help='Specify path for the image files')
    parser.add_argument('--delay', dest='delay', nargs='?', default=0.01, type=float,
            help='Amount of delay between images')
    parser.add_argument('--start-frame', dest='startframe', nargs='?', default=0, type=int,
            help='Starting frame to play')
    parser.add_argument('--end-frame', dest='endframe', nargs='?', default=-1, type=int,
            help='Ending frame to play, -1 for last frame')
    parser.add_argument('--num-frame', dest='numframe', nargs='?', default=-1, type=int,
            help='Number of frame to play, -1 for all frames')
    parser.add_argument('--mode', dest='mode', action='store', default='roadsign',
            help='Supporting mode: all, loadmatch, roadsign, detlight, flow, test, trainspeed, objdet')
    parser.add_argument('--rseg', dest='rseg', nargs='?', default=100, type=int,
            help='Number of vertical segmentation in computing averaged flow')
    parser.add_argument('--cseg', dest='cseg', nargs='?', default=300, type=int,
            help='Number of horizontal segmentation in computing averaged flow')
    parser.add_argument('--no-sign', dest='detsign', action='store_false',default=True,
        help='Disable sign detection')
    parser.add_argument('--sign', dest='sign', action='store', default='pedestrian_crossing_left')
    parser.add_argument('--model', dest='model', action='store', default='linear',
            help='Specify model for speed detection')
    parser.add_argument('--plot-losses', dest='plot_losses', action='store_true',default=False,
        help='Enable visualization of loss')
    parser.add_argument('--net', dest='net', help='Network to use [vgg16]',
        default='VGGnet_test')
    parser.add_argument('--modelpath', dest='modelpath', help='Model path',
        default='{}model/VGGnet_fast_rcnn_iter_70000.ckpt'.format(Faster_RCNN_PATH))
    parser.add_argument('--sample-every', dest='sample_every', nargs='?', default=3, type=int,
            help='Sample every <#> of frames')
    parser.add_argument('--convmode', dest='convmode', nargs='?', default=0, type=int,
            help='cnn network. 0 - baseline, 1 - resnet, 2 - alexnet, 4 - alexnet-pretrained')
    parser.add_argument('--speedmode', dest='speedmode', nargs='?', default=0, type=int,
            help='input mode for speed detection: 0 - flow only, 1 - flow + objmask, 2 - flow + \
            img, 3 - flow + objmask + img, 4 - img only')
    parser.add_argument('--flowmode', dest='flowmode', nargs='?', default=0, type=int,
            help='flow mode for speed detection: 0 - original flow, 1 - polarflow, 2 - avgflow, \
                    3 - polar avgflow ')
    parser.add_argument('--cpu', dest='cpu', action='store_true',default=False,
        help='use 1 cpu to trainspeed')
    parser.add_argument('--pcttrain', dest='pcttrain', nargs='?', default=0.7, type=float,
            help='Percentage of frames for training')
    parser.add_argument('--valmode', dest='valmode', nargs='?', default=0, type=int,
            help='valmode')
    parser.add_argument('--learning_rate', dest='learning_rate', nargs='?', default=0.001, type=float,
            help='Learning rate')
    parser.add_argument('--dropout', dest='dropout', nargs='?', default=0.5, type=float,
            help='Dropout rate')
    parser.add_argument('--epochs', dest='epochs', nargs='?', default=15, type=int,
            help='Number of epochs to train')
    parser.add_argument('--batch_size', dest='batch_size', nargs='?', default=16, type=int,
            help='Batch size to use during training. ')
    parser.add_argument('--decay_step', dest='decay_step', nargs='?', default=100, type=int,
            help='Number of steps between decays.')
    parser.add_argument('--decay_rate', dest='decay_rate', nargs='?', default=0.95, type=float,
            help='Decay rate.')
    parser.add_argument('--print_every', dest='print_every', nargs='?', default=100, type=int,
            help='How many iterations to do per print')
    parser.add_argument('--weight_init', dest='weight_init', default="xavier",
            help='tf method for weight initialization')
    parser.add_argument('--step_optimize', dest='step_optimize', default=False, nargs='?',
            type=float, help='tf method for weight initialization')
    parser.add_argument('--if_kitti', dest='if_kitti', default=0, nargs='?', type=int,
            help='use 1 for using kitti dataset, 0 otherwise')
    parser.add_argument('--if_af', dest='if_af', default=0, nargs='?', type=int,
            help='use 1 for (af,vf,wu), 0 for (vf,wu), 2 for (vf), 3 for (wu)')
    (options, args) = parser.parse_known_args()

    if (options.path==''):
        options.path = '{0}2011_09_26{1}/data'.format(KITTI_PATH, '_drive_0117_sync')
    if (options.testpath==''):
        options.testpath = '{0}2011_09_26{1}/data'.format(KITTI_PATH, '_drive_0117_sync')

    options = vars(options)
    if (options['demo']):
        options['mode'] = 'all'
    if options['mode'] in ['all', 'testspeed']:
        global restored_model
        restored_model,options = restoreModel(**options)
    if (options['demo']):
        while True:
            demo(**options)
        return

    for k in options:
        print('Configuration: {}={}'.format(k,options[k]))
    if (options['mode'] in ['trainspeed', 'testspeed']):
        trainModel(**options)
    else:
        play([], **options)

if __name__ == "__main__":
    main()

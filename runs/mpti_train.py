""" Attetion-aware Multi-Prototype Transductive Inference for Few-shot 3D Point Cloud Semantic Segmentation [Our method]

Author: Zhao Na, 2020
"""
import os
import torch
from torch.utils.data import DataLoader
from torch.utils.tensorboard import SummaryWriter

from runs.eval import test_few_shot
from dataloaders.loader import MyDataset, MyTestDataset, batch_test_task_collate
from models.mpti_learner import MPTILearner
from utils.cuda_util import cast_cuda
from utils.logger import init_logger


def train(args):
    logger = init_logger(args.log_dir, args)

    # yang
    log_model_path = os.path.join(args.log_dir, 'models')
    if not os.path.exists(log_model_path):
        os.makedirs(log_model_path)
    os.system('cp models/mpti_learner.py %s' % (log_model_path))
    os.system('cp models/mpti.py %s' % (log_model_path))
    os.system('cp models/dgcnn.py %s' % (log_model_path))
    os.system('cp runs/mpti_train.py %s' % (log_model_path))

    # init model and optimizer
    MPTI = MPTILearner(args)

    #Init datasets, dataloaders, and writer
    PC_AUGMENT_CONFIG = {'scale': args.pc_augm_scale,
                         'rot': args.pc_augm_rot,
                         'mirror_prob': args.pc_augm_mirror_prob,
                         'jitter': args.pc_augm_jitter
                         }

    TRAIN_DATASET = MyDataset(args.data_path, args.dataset, cvfold=args.cvfold, num_episode=args.n_iters,
                              n_way=args.n_way, k_shot=args.k_shot, n_queries=args.n_queries,
                              phase=args.phase, mode='train',
                              num_point=args.pc_npts, pc_attribs=args.pc_attribs,
                              pc_augm=args.pc_augm, pc_augm_config=PC_AUGMENT_CONFIG)

    VALID_DATASET = MyTestDataset(args.data_path, args.dataset, cvfold=args.cvfold,
                                  num_episode_per_comb=args.n_episode_test,
                                  n_way=args.n_way, k_shot=args.k_shot, n_queries=args.n_queries,
                                  num_point=args.pc_npts, pc_attribs=args.pc_attribs)
    VALID_CLASSES = list(VALID_DATASET.classes)

    TRAIN_LOADER = DataLoader(TRAIN_DATASET, batch_size=1, collate_fn=batch_test_task_collate)
    VALID_LOADER = DataLoader(VALID_DATASET, batch_size=1, collate_fn=batch_test_task_collate)

    WRITER = SummaryWriter(log_dir=args.log_dir)

    # train
    best_iou = 0
    for batch_idx, (data, sampled_classes) in enumerate(TRAIN_LOADER):

        if torch.cuda.is_available():
            data = cast_cuda(data)

        loss, accuracy = MPTI.train(data)

        logger.cprint('==[Train] Iter: %d | Loss: %.4f |  Accuracy: %f  ==' % (batch_idx, loss, accuracy))
        WRITER.add_scalar('Train/loss', loss, batch_idx)
        WRITER.add_scalar('Train/accuracy', accuracy, batch_idx)

        if (batch_idx+1) % args.eval_interval == 0:
            valid_loss, mean_IoU = test_few_shot(VALID_LOADER, MPTI, logger, VALID_CLASSES)
            logger.cprint('\n=====[VALID] Loss: %.4f | Mean IoU: %f  =====\n' % (valid_loss, mean_IoU))
            WRITER.add_scalar('Valid/loss', valid_loss, batch_idx)
            WRITER.add_scalar('Valid/meanIoU', mean_IoU, batch_idx)
            if mean_IoU > best_iou:
                best_iou = mean_IoU
                logger.cprint('*******************Model Saved*******************')
                save_dict = {'iteration': batch_idx + 1,
                             'model_state_dict': MPTI.model.state_dict(),
                             'optimizer_state_dict': MPTI.optimizer.state_dict(),
                             'loss': valid_loss,
                             'IoU': best_iou
                             }
                torch.save(save_dict, os.path.join(args.log_dir, 'checkpoint.tar'))
        
        if (batch_idx+1) % 2000 == 0:
        # if batch_idx % 1 == 0:
            path = os.path.join(args.log_dir, 'checkpoint_' + str(batch_idx) + '.pth')
            save_dict = {'iteration': batch_idx + 1,
                             'model_state_dict': MPTI.model.state_dict(),
                             'optimizer_state_dict': MPTI.optimizer.state_dict(),
                             'loss': loss
                             }
            torch.save(save_dict, path)
            print('Checkpoint saved to %s' % path)

    WRITER.close()

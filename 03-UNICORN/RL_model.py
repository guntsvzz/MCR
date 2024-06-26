
import math
import random
import numpy as np
import os
import sys
from tqdm.auto import tqdm
# sys.path.append('..')
# from Graph_generate.knowledge_graph import KnowledgeGraph
from Graph_generate.amazon_graph import AmazonGraph
from Graph_generate.amazon_data_process import AmazonDataset
from collections import namedtuple
import argparse
from itertools import count, chain
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
from utils import *
from sum_tree import SumTree
from memory import ReplayMemory, ReplayMemoryPER
from agent import Agent

#TODO select env
from RL.env_binary_question import BinaryRecommendEnv
from RL.env_enumerated_question import EnumeratedRecommendEnv
# from RL.env_binary_question_pgpr import BinaryRecommendEnvPGPR
from RL.env_binary_question_pgpr_feature import BinaryRecommendEnvPGPR
from RL.RL_evaluate import dqn_evaluate
from gcn import GraphEncoder
import time
import warnings

warnings.filterwarnings("ignore")
EnvDict = {
    LAST_FM: BinaryRecommendEnv,
    LAST_FM_STAR: BinaryRecommendEnv,
    YELP: EnumeratedRecommendEnv,
    YELP_STAR: BinaryRecommendEnv,
    AMAZON: BinaryRecommendEnv,
    AMAZON_STAR: BinaryRecommendEnv,
    BEAUTY : BinaryRecommendEnvPGPR,
    CELLPHONES : BinaryRecommendEnvPGPR, 
    CLOTH : BinaryRecommendEnvPGPR, 
    CDS : BinaryRecommendEnvPGPR
    }

FeatureDict = {
    LAST_FM: 'feature',
    LAST_FM_STAR: 'feature',
    YELP: 'large_feature',
    YELP_STAR: 'feature',
    AMAZON: 'feature',
    AMAZON_STAR: 'feature',
    BEAUTY : 'feature',
    CELLPHONES : 'feature',
    CLOTH : 'feature',
    CDS : 'feature'
}

Transition = namedtuple(
    'Transition',
    ('state', 'action', 'next_state', 'reward', 'next_cand'))

def train(args, kg, dataset, filename):
    env = EnvDict[args.data_name](
        kg, 
        dataset, 
        args.data_name, 
        args.embed, 
        seed=args.seed, 
        max_turn=args.max_turn, 
        cand_num=args.cand_num, 
        cand_item_num=args.cand_item_num,
        attr_num=args.attr_num, 
        mode='train', 
        ask_num=args.ask_num,
        entropy_way=args.entropy_method, 
        fm_epoch=args.fm_epoch,
        domain = args.domain
    )
        
    set_random_seed(args.seed)
    memory = ReplayMemoryPER(args.memory_size) #50000
    embed = torch.FloatTensor(
        np.concatenate((env.ui_embeds, env.feature_emb, np.zeros((1,env.ui_embeds.shape[1]))), axis=0))
    gcn_net = GraphEncoder(
        device=args.device, 
        entity=embed.size(0), 
        emb_size=embed.size(1), 
        kg=kg, 
        embeddings=embed, 
        fix_emb=args.fix_emb, 
        seq=args.seq, 
        gcn=args.gcn, 
        hidden_size=args.hidden
    ).to(args.device)
    agent = Agent(
        device=args.device, 
        memory=memory, 
        state_size=args.hidden, 
        action_size=embed.size(1), 
        hidden_size=args.hidden, 
        gcn_net=gcn_net, 
        learning_rate=args.learning_rate, 
        l2_norm=args.l2_norm, 
        PADDING_ID=embed.size(0)-1
       )
    # self.reward_dict = {
    #     'ask_suc': 0.01,
    #     'ask_fail': -0.1,
    #     'rec_suc': 1,
    #     'rec_fail': -0.1,
    #     'until_T': -0.3,  # until MAX_Turn
    # }
    #ealuation metric  ST@T
    #agent load policy parameters
    if args.load_rl_epoch != 0 :
        print('Staring loading rl model in epoch {}'.format(args.load_rl_epoch))
        agent.load_model(data_name=args.data_name, filename=filename, epoch_user=args.load_rl_epoch)

    test_performance = []
    if args.eval_num == 1:
        SR15_mean = dqn_evaluate(args, kg, dataset, agent, filename, 0)
        test_performance.append(SR15_mean)
    for train_step in tqdm(range(1, args.max_steps+1)):
        SR5, SR10, SR15, AvgT, Rank, total_reward = 0., 0., 0., 0., 0., 0.
        loss = torch.tensor(0, dtype=torch.float, device=args.device)
        for i_episode in tqdm(range(args.sample_times),desc='sampling'):
            #blockPrint()
            print('\n================new tuple:{}===================='.format(i_episode))
            success = False
            while not success:
                try:
                    if not args.fix_emb:
                        state, cand, action_space = env.reset(agent.gcn_net.embedding.weight.data.cpu().detach().numpy())  # Reset environment and record the starting state
                        success = True  # If reset succeeds, mark success as True to exit the loop
                    else:
                        state, cand, action_space = env.reset() 
                        success = True  # If reset succeeds, mark success as True to exit the loop
                except Exception as e:
                    print(f"Error occurred during reset: {e}")
                    print("Retrying...")
                    time.sleep(0.5)  # Wait for 1 second before retrying (adjust as needed)
                    # You can add more sophisticated retry logic here if needed
            #state = torch.unsqueeze(torch.FloatTensor(state), 0).to(args.device)
            epi_reward = 0
            is_last_turn = False
            for t in count():   # user  dialog
                if t == 14:
                    is_last_turn = True
                action, sorted_actions = agent.select_action(state, cand, action_space, is_last_turn=is_last_turn) 
                if not args.fix_emb:
                    next_state, next_cand, action_space, reward, done = env.step(action.item(), sorted_actions, agent.gcn_net.embedding.weight.data.cpu().detach().numpy())
                else:
                    next_state, next_cand, action_space, reward, done = env.step(action.item(), sorted_actions)
                
                print(f"Step {t}, Action: {action}, Reward: {reward}, Done: {done}")
                if math.isnan(reward):
                    raise ValueError("Reward is NaN")
                epi_reward += reward
                reward = torch.tensor([reward], device=args.device, dtype=torch.float)
                if done:
                    next_state = None

                agent.memory.push(state, action, next_state, reward, next_cand)
                state = next_state
                cand = next_cand

                newloss = agent.optimize_model(args.batch_size, args.gamma)
                if newloss is not None:
                    loss += newloss

                if done:
                    # every episode update the target model to be same with model
                    if reward.item() == 1:  # recommend successfully
                        if t < 5:
                            SR5 += 1
                            SR10 += 1
                            SR15 += 1
                        elif t < 10:
                            SR10 += 1
                            SR15 += 1
                        else:
                            SR15 += 1
                        Rank += (1/math.log(t+3,2) + (1/math.log(t+2,2)-1/math.log(t+3,2))/math.log(done+1,2))
                    else:
                        Rank += 0
                    AvgT += t+1
                    total_reward += epi_reward
                    
                    break
                
            # user's profile
            user_acc_feature = env.user_acc_feature 
            user_rej_feature = env.user_rej_feature 
            cand_items = env.cand_items 
            print("user's profile")
            print('user_acc_feature', user_acc_feature)
            print('user_rej_feature', user_rej_feature)
            print('Number of cand_items', len(cand_items))
            
        enablePrint() # Enable print function
        print('loss : {} in epoch_uesr {}'.format(loss.item()/args.sample_times, args.sample_times))
        print('SR5:{}, SR10:{}, SR15:{}, AvgT:{}, Rank:{}, rewards:{} '
                  'Total epoch_uesr:{}'.format(SR5 / args.sample_times, SR10 / args.sample_times, SR15 / args.sample_times,
                                                AvgT / args.sample_times, Rank / args.sample_times, total_reward / args.sample_times, args.sample_times))

        if train_step % args.eval_num == 0:
            SR15_mean = dqn_evaluate(args, kg, dataset, agent, filename, train_step)
            test_performance.append(SR15_mean)
        if train_step % args.save_num == 0:
            agent.save_model(data_name=args.data_name, filename=filename, epoch_user=train_step)
    print(test_performance)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', '-seed', type=int, default=1, help='random seed.')
    parser.add_argument('--gpu', type=str, default='1', help='gpu device.')
    parser.add_argument('--epochs', '-me', type=int, default=50000, help='the number of RL train epoch') #fix here 50000
    parser.add_argument('--fm_epoch', type=int, default=0, help='the epoch of FM embedding')
    parser.add_argument('--batch_size', type=int, default=128, help='batch size.')
    parser.add_argument('--gamma', type=float, default=0.999, help='reward discount factor.')
    parser.add_argument('--learning_rate', type=float, default=1e-4, help='learning rate.')
    parser.add_argument('--l2_norm', type=float, default=1e-6, help='l2 regularization.')
    parser.add_argument('--hidden', type=int, default=100, help='number of samples')
    parser.add_argument('--memory_size', type=int, default=50000, help='size of memory ')

    parser.add_argument('--data_name', type=str, default=AMAZON, choices=[BEAUTY, CELLPHONES, CLOTH, CDS, AMAZON, AMAZON_STAR, LAST_FM, LAST_FM_STAR, YELP, YELP_STAR],
                        help='One of {BEAUTY, CELLPHONES, CLOTH, CDS, AMAZON, AMAZON_STAR, LAST_FM, LAST_FM_STAR, YELP, YELP_STAR}.')
    parser.add_argument('--domain', type=str, default='Beauty', choices=['Beauty','Cellphones', 'Cloth', 'CDs'],
                        help='One of {CDs, Beauty, Cloth, Cell, Appliances, Office_Products, Electronics, Sports_and_Outdoors, Clothing_Shoes_and_Jewelry}.')
    parser.add_argument('--entropy_method', type=str, default='weight_entropy', help='entropy_method is one of {entropy, weight entropy}')
    # Although the performance of 'weighted entropy' is better, 'entropy' is an alternative method considering the time cost.
    parser.add_argument('--max_turn', type=int, default=15, help='max conversation turn')
    parser.add_argument('--attr_num', type=int, help='the number of attributes')
    parser.add_argument('--mode', type=str, default='train', help='the mode in [train, test]')
    parser.add_argument('--ask_num', type=int, default=1, help='the number of features asked in a turn')
    parser.add_argument('--load_rl_epoch', type=int, default=0, help='the epoch of loading RL model')

    parser.add_argument('--sample_times', type=int, default=100, help='the epoch of sampling') #fix here espisode 100
    parser.add_argument('--max_steps', type=int, default=100, help='max training steps')
    parser.add_argument('--eval_num', type=int, default=10, help='the number of steps to evaluate RL model and metric')
    parser.add_argument('--save_num', type=int, default=10, help='the number of steps to save RL model and metric')
    parser.add_argument('--observe_num', type=int, default=10, help='the number of steps to print metric')
    parser.add_argument('--cand_num', type=int, default=10, help='candidate sampling number')
    parser.add_argument('--cand_item_num', type=int, default=10, help='candidate item sampling number')
    parser.add_argument('--fix_emb', action='store_false', help='fix embedding or not')
    parser.add_argument('--embed', type=str, default=None, help='pretrained embeddings', choices=['transe', None])
    parser.add_argument('--seq', type=str, default='transformer', choices=['rnn', 'transformer', 'mean'], help='sequential learning method')
    parser.add_argument('--gcn', action='store_false', help='use GCN or not')

    args = parser.parse_args()
    os.environ['CUDA_VISIBLE_DEVICES'] = args.gpu
    args.device = torch.device('cuda') if torch.cuda.is_available() else 'cpu'
    print(args.device)
    print('data_set:{}'.format(args.data_name))
    
    if args.data_name == AMAZON:
        kg = AmazonGraph(args.domain) #dont use   
    else:
        kg = load_kg(args.data_name, mode='train')
        print(kg.G.keys())
        print('Number of User',len(kg.G['user']))
        print('Number of Item',len(kg.G['item']))
        print('Number of Category',len(kg.G['category']))
        print('Number of Feature',len(kg.G['feature']))
        
    #reset attr_num
    feature_name = FeatureDict[args.data_name]
    # feature_name = "category" #brand, word fix later
    feature_length = len(kg.G[feature_name].keys())
    print('dataset:{}, feature_length:{}'.format(args.data_name, feature_length))
    args.attr_num = feature_length  # set attr_num  = feature_length
    print('args.attr_num:', args.attr_num)
    print('args.entropy_method:', args.entropy_method)

    if args.data_name == AMAZON:
        dataset = AmazonDataset(args.domain) #dont use  
    else:
        dataset = load_dataset(args.data_name, mode='train')
        print('Number of user',     getattr(dataset, 'user').vocab_size)
        print('Number of item',     getattr(dataset, 'item').vocab_size)
        print('Number of category', getattr(dataset, 'category').vocab_size)
        
    filename = 'train-data-{}-RL-cand_num-{}-cand_item_num-{}-embed-{}-seq-{}-gcn-{}'.format(
        args.data_name, args.cand_num, args.cand_item_num, args.embed, args.seq, args.gcn)
    train(args, kg, dataset, filename)

if __name__ == '__main__':
    main()
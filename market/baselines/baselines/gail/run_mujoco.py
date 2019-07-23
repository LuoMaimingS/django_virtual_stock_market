'''
Disclaimer: this code is highly based on trpo_mpi at @openai/baselines and @openai/imitation
'''

import argparse
import os.path as osp
import logging
from mpi4py import MPI
from tqdm import tqdm

import numpy as np
import os
import datetime as dt
from decimal import Decimal

from market.baselines.baselines.gail import mlp_policy
from market.baselines.baselines.common import set_global_seeds, tf_util as U
from market.baselines.baselines.common.misc_util import boolean_flag
from market.baselines.baselines import bench
from market.baselines.baselines import logger
from market.baselines.baselines.gail.dataset.mujoco_dset import Mujoco_Dset
from market.baselines.baselines.gail.adversary import TransitionClassifier

from market.models import sim_market, sim_stocks, sim_trades
from market.models.clients import BaseClient
from market import simulator_main


class GailArgs:
    def __init__(self):
        self.seed = 0
        self.task = 'train'
        self.algo = 'trpo'
        self.g_step = 0
        self.d_step = 0
        self.policy_entcoeff = 0
        self.adversary_entcoeff = 1e-3
        self.num_timesteps = 5e6
        self.save_per_iter = 100
        self.checkpoint_dir = 'checkpoint'
        self.log_dir = 'log'
        self.pretrained = False
        self.BC_max_iter = 1e4

        self.expert_path = 'data/000009.XSHE_traj_length2.npz'
        self.traj_limitation = -1
        self.adversary_hidden_size = 64
        self.policy_hidden_size = 64

    def set_args(self, seed, task, algo, g_step, d_step):
        self.seed = seed
        self.task = task
        self.algo = algo
        self.g_step = g_step
        self.d_step = d_step

    def get_task_name(self):
        task_name = self.algo + "_gail."
        if self.pretrained:
            task_name += "with_pretrained."
        if self.traj_limitation != np.inf:
            task_name += "transition_limitation_%d." % self.traj_limitation
        task_name = task_name + ".g_step_" + str(self.g_step) + ".d_step_" + str(self.d_step)
                    # + ".policy_entcoeff_" + str(self.policy_entcoeff) + ".adversary_entcoeff_" + str(self.adversary_entcoeff)
        task_name += ".seed_" + str(self.seed)
        return task_name


class Enviroment:
    def __init__(self):
        self.env_id = 'Market-v0'
        self.manager = 'Amadeus'
        self.observation_space = np.zeros((25, ))
        self.action_space = np.zeros((3, ))
        self.horizon = 1024

    def seed(self, seed):
        pass

    def step(self, action, next_datetime):
        """
        目前默认标的股票是000009.XSHE
        """
        try:
            super_client = BaseClient.objects.get(name=self.manager)
            assert super_client.driver is not None
        except:
            logger.error('Environment Reset Error.')
            return False
        action = self.revert_action(action)
        simulator_main.act_according_to_calculated_actions(super_client, [action])
        market = sim_market.SimMarket.objects.get(id=1)
        market.datetime = next_datetime
        market.tick += 1
        market.save()
        ob = self.get_ob()
        true_rew = 1.0
        new = False
        logger.debug(ob)
        return ob, true_rew, new, None

    def reset(self, stock, datetime):
        try:
            super_client = BaseClient.objects.get(name=self.manager)
            assert super_client.driver is not None
        except:
            logger.error('Environment Reset Error.')
            return False
        simulator_main.simulator_resetter(super_client)
        simulator_main.anchor_one_stock(stock, datetime, super_client)
        market = sim_market.SimMarket.objects.get(id=1)
        market.datetime = datetime
        market.tick = 0
        market.save()
        ob = self.get_ob()
        return ob

    def close(self):
        pass

    def set_manager(self, manager):
        self.manager = manager

    def set_space(self, ob_shape, ac_shape, horizon):
        self.observation_space = np.zeros((ob_shape, ))
        self.action_space = np.zeros((ac_shape, ))
        self.horizon = horizon

    def action_space_sample(self):
        if self.action_space.shape == (3, ):
            import random
            return random.randint(0, 2), random.random(), random.random()
        else:
            logger.debug(self.action_space.shape)
            raise NotImplementedError

    @staticmethod
    def revert_action(action):
        policy_action = action.copy()
        stock = sim_stocks.SimStock.objects.get(symbol='000009.XSHE')
        direction = np.clip(round(action[0]), 0, 2)
        if direction == 0:
            direction = 'a'
        elif direction == 1:
            direction = 'b'
        else:
            direction = 'c'
        price = np.clip(action[1], 0, 1)
        volume = np.clip(action[2], 0, 1)

        level5_data = stock.get_order_book_data(level=5, to_list=True)
        total_volume = 0
        for i in range(len(level5_data)):
            if i % 2 == 0:
                continue
            total_volume += level5_data[i]
        a5 = level5_data[0]
        b5 = level5_data[18]
        if a5 != 0 and b5 != 0:
            assert a5 > b5
        price = b5 + Decimal(price * float(a5 - b5))
        price = Decimal(round(float(price), 2)).quantize(Decimal('0.00'))
        vol = int(total_volume / 10 * volume)
        logger.debug('Market revert action. From {} to {}'.format(policy_action, (direction, price, vol)))
        return direction, price, vol

    @staticmethod
    def get_ob():
        stock = sim_stocks.SimStock.objects.get(symbol='000009.XSHE')
        ob = stock.get_order_book_data(level=5, to_list=True)
        ob.append(stock.last_price)
        ob.append(stock.high)
        ob.append(stock.low)
        ob.append(stock.volume)
        ob.append(stock.amount)
        return np.array(ob)


def main(args):
    U.make_session(num_cpu=1).__enter__()
    set_global_seeds(args.seed)
    env = Enviroment()

    def policy_fn(name, ob_space, ac_space, reuse=False):
        return mlp_policy.MlpPolicy(name=name, ob_space=ob_space, ac_space=ac_space,
                                    reuse=reuse, hid_size=args.policy_hidden_size, num_hid_layers=2)
    task_name = args.get_task_name()
    args.checkpoint_dir = osp.join(os.path.split(os.path.abspath(os.curdir))[0], 'gail',
                                   args.checkpoint_dir, task_name)
    args.checkpoint_dir = None
    args.log_dir = osp.join(os.path.split(os.path.abspath(os.curdir))[0],
                            'VirtualStockMarket', 'market', 'baselines', 'baselines', 'gail',
                            args.log_dir, task_name)
    args.expert_path = osp.join(os.path.split(os.path.abspath(os.curdir))[0],
                                'VirtualStockMarket', 'market', 'baselines', 'baselines', 'gail',
                                args.expert_path)

    logger.set_level(10)
    logger.info('Begin to {}'.format(args.task))
    logger.info('task name: {}'.format(task_name))
    logger.info('check_point_dir: {}'.format(args.checkpoint_dir))
    logger.info('log_dir: {}'.format(args.log_dir))
    logger.info('expert_path: {}'.format(args.expert_path))

    if args.task == 'train':
        dataset = Mujoco_Dset(expert_path=args.expert_path, traj_limitation=args.traj_limitation)
        env.set_space(dataset.obs.shape[1], dataset.acs.shape[1], dataset.traj_length)
        logger.debug('Environment Set: {} Manager: {} \nob shape: {}, ac shape: {}, horizon: {}'.
                     format(env.env_id, env.manager, env.observation_space.shape, env.action_space.shape, env.horizon))
        reward_giver = TransitionClassifier(env, args.adversary_hidden_size, entcoeff=args.adversary_entcoeff)
        train(env,
              args.seed,
              policy_fn,
              reward_giver,
              dataset,
              args.algo,
              args.g_step,
              args.d_step,
              args.policy_entcoeff,
              args.num_timesteps,
              args.save_per_iter,
              args.checkpoint_dir,
              args.log_dir,
              args.pretrained,
              args.BC_max_iter,
              task_name
              )
    elif args.task == 'evaluate':
        runner(env,
               policy_fn,
               args.load_model_path,
               timesteps_per_batch=1024,
               number_trajs=10,
               stochastic_policy=args.stochastic_policy,
               save=args.save_sample
               )
    else:
        raise NotImplementedError
    env.close()


def train(env, seed, policy_fn, reward_giver, dataset, algo,
          g_step, d_step, policy_entcoeff, num_timesteps, save_per_iter,
          checkpoint_dir, log_dir, pretrained, BC_max_iter, task_name=None):

    pretrained_weight = None
    if pretrained and (BC_max_iter > 0):
        # Pretrain with behavior cloning
        from market.baselines.baselines.gail import behavior_clone
        pretrained_weight = behavior_clone.learn(env, policy_fn, dataset,
                                                 max_iters=BC_max_iter)

    if algo == 'trpo':
        from market.baselines.baselines.gail import trpo_mpi
        # Set up for MPI seed
        rank = MPI.COMM_WORLD.Get_rank()
        if rank != 0:
            logger.set_level(logger.DISABLED)
        workerseed = seed + 10000 * MPI.COMM_WORLD.Get_rank()
        set_global_seeds(workerseed)
        env.seed(workerseed)
        trpo_mpi.learn(env, policy_fn, reward_giver, dataset, rank,
                       pretrained=pretrained, pretrained_weight=pretrained_weight,
                       g_step=g_step, d_step=d_step,
                       entcoeff=policy_entcoeff,
                       max_timesteps=num_timesteps,
                       ckpt_dir=checkpoint_dir, log_dir=log_dir,
                       save_per_iter=save_per_iter,
                       timesteps_per_batch=env.horizon,
                       max_kl=0.01, cg_iters=10, cg_damping=0.1,
                       gamma=0.995, lam=0.97,
                       vf_iters=5, vf_stepsize=1e-3,
                       task_name=task_name)
    else:
        raise NotImplementedError


def runner(env, policy_func, load_model_path, timesteps_per_batch, number_trajs,
           stochastic_policy, save=False, reuse=False):

    # Setup network
    # ----------------------------------------
    ob_space = env.observation_space
    ac_space = env.action_space
    pi = policy_func("pi", ob_space, ac_space, reuse=reuse)
    U.initialize()
    # Prepare for rollouts
    # ----------------------------------------
    U.load_state(load_model_path)

    obs_list = []
    acs_list = []
    len_list = []
    ret_list = []
    for _ in tqdm(range(number_trajs)):
        traj = traj_1_generator(pi, env, timesteps_per_batch, stochastic=stochastic_policy)
        obs, acs, ep_len, ep_ret = traj['ob'], traj['ac'], traj['ep_len'], traj['ep_ret']
        obs_list.append(obs)
        acs_list.append(acs)
        len_list.append(ep_len)
        ret_list.append(ep_ret)
    if stochastic_policy:
        print('stochastic policy:')
    else:
        print('deterministic policy:')
    if save:
        filename = load_model_path.split('/')[-1] + '.' + env.spec.id
        np.savez(filename, obs=np.array(obs_list), acs=np.array(acs_list),
                 lens=np.array(len_list), rets=np.array(ret_list))
    avg_len = sum(len_list)/len(len_list)
    avg_ret = sum(ret_list)/len(ret_list)
    print("Average length:", avg_len)
    print("Average return:", avg_ret)
    return avg_len, avg_ret


# Sample one trajectory (until trajectory end)
def traj_1_generator(pi, env, horizon, stochastic):

    t = 0
    ac = env.action_space.sample()  # not used, just so we have the datatype
    new = True  # marks if we're on first timestep of an episode

    ob = env.reset()
    cur_ep_ret = 0  # return in current episode
    cur_ep_len = 0  # len of current episode

    # Initialize history arrays
    obs = []
    rews = []
    news = []
    acs = []

    while True:
        ac, vpred = pi.act(stochastic, ob)
        obs.append(ob)
        news.append(new)
        acs.append(ac)

        ob, rew, new, _ = env.step(ac)
        rews.append(rew)

        cur_ep_ret += rew
        cur_ep_len += 1
        if new or t >= horizon:
            break
        t += 1

    obs = np.array(obs)
    rews = np.array(rews)
    news = np.array(news)
    acs = np.array(acs)
    traj = {"ob": obs, "rew": rews, "new": news, "ac": acs,
            "ep_ret": cur_ep_ret, "ep_len": cur_ep_len}
    return traj

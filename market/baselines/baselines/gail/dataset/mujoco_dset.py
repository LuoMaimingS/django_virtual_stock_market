'''
Data structure of the input .npz:
the data is save in python dictionary format with keys: 'acs', 'ep_rets', 'rews', 'obs'
the values of each item is a list storing the expert trajectory sequentially
a transition can be: (data['obs'][t], data['acs'][t], data['obs'][t+1]) and get reward data['rews'][t]
'''

from market.baselines.baselines import logger
import numpy as np


class Dset(object):
    def __init__(self, inputs, labels, datemtimes, randomize):
        self.inputs = inputs
        self.labels = labels
        self.dts = datemtimes
        assert len(self.inputs) == len(self.labels)
        assert len(self.inputs) == len(self.dts)
        self.randomize = randomize
        self.num_pairs = len(inputs)
        self.init_pointer()

    def init_pointer(self):
        self.pointer = 0
        if self.randomize:
            idx = np.arange(self.num_pairs)
            np.random.shuffle(idx)
            self.inputs = self.inputs[idx, :]
            self.labels = self.labels[idx, :]
            self.dts = self.dts[idx, :]

    def get_next_batch(self, batch_size):
        # if batch_size is negative -> return all
        if batch_size < 0:
            return self.inputs, self.labels, self.dts
        if self.pointer + batch_size >= self.num_pairs:
            self.init_pointer()
        end = self.pointer + batch_size
        inputs = self.inputs[self.pointer:end, :]
        labels = self.labels[self.pointer:end, :]
        dts = self.dts[self.pointer:end, :]
        self.pointer = end
        return inputs, labels, dts


class Mujoco_Dset(object):
    def __init__(self, expert_path, train_fraction=0.7, traj_limitation=-1, randomize=False):
        traj_data = np.load(expert_path)
        if traj_limitation < 0:
            traj_limitation = len(traj_data['obs'])
        obs = traj_data['obs'][:traj_limitation]
        acs = traj_data['acs'][:traj_limitation]
        trks = traj_data['trk'][:traj_limitation]
        dts = traj_data['dts'][:traj_limitation]

        logger.info('Expert Data Loaded. Observation shape: {}  Action shape: {}, Track shape: {}' 
                    'Datetime shape: {}'.format(obs.shape, acs.shape, trks.shape, dts.shape))

        # obs, acs: shape (N, L, ) + S where N = # episodes, L = episode length
        # and S is the environment observation/action space.
        # Flatten to (N * L, prod(S))
        self.obs = np.reshape(obs, [-1, np.prod(obs.shape[2:])])
        self.acs = np.reshape(acs, [-1, np.prod(acs.shape[2:])])
        self.trks = np.reshape(trks, [-1, np.prod(trks.shape[2:])])
        self.dts = np.reshape(dts, [-1, int(np.prod(dts.shape[2:]))])

        self.rets = traj_data['ep_rets'][:traj_limitation]
        self.avg_ret = sum(self.rets)/len(self.rets)
        self.std_ret = np.std(np.array(self.rets))
        if len(self.acs) > 2:
            self.acs = np.squeeze(self.acs)
        assert len(self.obs) == len(self.acs)
        self.num_traj = min(traj_limitation, len(traj_data['obs']))
        self.num_transition = len(self.obs)
        self.traj_length = int(self.num_transition / self.num_traj)
        self.randomize = randomize
        self.dset = Dset(self.obs, self.acs, self.dts, self.randomize)
        # for behavior cloning
        self.train_set = Dset(self.obs[:int(self.num_transition*train_fraction), :],
                              self.acs[:int(self.num_transition*train_fraction), :],
                              self.dts[:int(self.num_transition * train_fraction), :],
                              self.randomize)
        self.val_set = Dset(self.obs[int(self.num_transition*train_fraction):, :],
                            self.acs[int(self.num_transition*train_fraction):, :],
                            self.dts[int(self.num_transition * train_fraction):, :],
                            self.randomize)
        self.log_info()

    def log_info(self):
        logger.log("Total trajectories: %d" % self.num_traj)
        logger.log("Total transitions: %d" % self.num_transition)
        logger.log("Average returns: %f" % self.avg_ret)
        logger.log("Std for returns: %f" % self.std_ret)

    def get_next_batch(self, batch_size, split=None):
        if split is None:
            return self.dset.get_next_batch(batch_size)
        elif split == 'train':
            return self.train_set.get_next_batch(batch_size)
        elif split == 'val':
            return self.val_set.get_next_batch(batch_size)
        else:
            raise NotImplementedError

    def plot(self):
        import matplotlib.pyplot as plt
        plt.hist(self.rets)
        plt.savefig("histogram_rets.png")
        plt.close()


def tes(expert_path, traj_limitation, plot):
    dset = Mujoco_Dset(expert_path, traj_limitation=traj_limitation)
    logger.log(dset.dts)
    if plot:
        dset.plot()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--expert_path", type=str, default="D:/VirtualStockMarket/market/baselines/baselines/gail/data/000009.XSHE_traj_length64.npz")
    parser.add_argument("--traj_limitation", type=int, default=-1)
    parser.add_argument("--plot", type=bool, default=False)
    args = parser.parse_args()
    tes(args.expert_path, args.traj_limitation, args.plot)

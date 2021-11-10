# TODO: implement RL algorithms

def coma(args):
    import os
    import gym
    from copy import deepcopy
    from pathlib import Path
    from easydict import EasyDict
    from rl2.agents.utils import LinearDecay
    from rlena.algos.agents.coma import COMAPGModel, COMAgent
    from rlena.algos.workers import ComaWorker
    from rlena.algos.utils import Logger
    args = EasyDict(args.__dict__)

    if args.env == 'pommerman':
        import pommerman
        from rlena.envs.customPomme import TwoVsTwoPomme

        env = TwoVsTwoPomme(ramdom_num_wall=args.random_num_wall,
                            max_rigid=args.max_rigid,
                            max_wood=args.max_wood,
                            max_steps=args.max_steps,
                            remove_stop=args.remove_stop,
                            onehot=args.onehot)
        env.seed(args.seed)
        _ = env.reset()

        # Setup shapes
        g_obs_shape = env.get_global_obs_shape()
        observation_shape = env.observation_shape
        ac_shape = (env.action_space.n - int(args.remove_stop),)
        # -1 in action_space.n to remove stop action

        config = args
        if config.mode == 'train':
            training = True
            max_episode = 20000
            render_mode = 'rgb_array'
            render_interval = 10
            save_gif = False
        else:
            training = False
            config.explore = False
            max_episode = 10
            render_mode = 'human'
            render_interval = 1
            save_gif = True

        # Epsilon decay
        eps = LinearDecay(start=args.eps_start,
                          end=args.eps_end,
                          decay_step=args.decay_step)

        logger = Logger(name=args.algo, args=config)

        config.log_dir = logger.log_dir
        config.ckpt_dir = os.path.join(logger.log_dir, 'ckpt')
        Path(config.ckpt_dir).mkdir(parents=True, exist_ok=True)

        team1 = COMAPGModel(observation_shape, g_obs_shape,
                            ac_shape, n_agents=2, **config)
        team2 = COMAPGModel(observation_shape, g_obs_shape,
                            ac_shape, n_agents=2, **config)

        magent = COMAgent([team1, team2], eps=eps, **config)

        worker = ComaWorker(
            env,
            n_env=args.n_env,
            agent=magent,
            n_agents=4,
            max_episodes=max_episode,
            training=training,
            logger=logger,
            log_interval=config.log_interval,
            render=True,
            render_mode=render_mode,
            render_interval=render_interval,
            save_gif=save_gif,
            is_save=True,
        )

    if args.env == 'snake':
        raise NotImplementedError

    worker.run()


def sacd(args):  # args: argparse.ArgumentParser
    from easydict import EasyDict
    import numpy as np
    import os
    import gym
    from pathlib import Path
    import json
    from rlena.algos.agents.sac_discrete import SACAgentDISC, SACModelDISC
    from rlena.algos.workers import SACDworker
    from rlena.algos.utils import Logger
    # TODO: Intergrate with my config easydict in sacd
    args = EasyDict(args.__dict__)

    if args.env == 'pommerman':
        import pommerman
        from rlena.envs.customPomme import ConservativeEnvWrapper
        from pommerman.configs import one_vs_one_env
        import pommerman.envs as envs
        from pommerman.agents import SimpleAgent
        from pommerman.characters import Bomber

        config = EasyDict({
            'gamma': 0.99,
            'n_agents': 2,
            'n_env': 1,
            'train_interval': args.train_interval,
            'train_after': args.rand_until,
            'update_interval': args.update_interval,
            'update_after': args.rand_until,
            'rand_until': args.rand_until,
            'save_interval': 1000,
            'batch_size': 32,
            'max_step': args.max_steps,
            'device': args.device,
            'render': True,
            'render_interval': 10,
            'log_interval': 10, 
            'eps': args.eps,  # for decaying epsilon greedy
            'log_dir': args.log_dir,
            'save_dir': args.ckpt_dir,
            'lr_ac': 1e-4,
            'lr_cr': 1e-4,
        })

        env_config = one_vs_one_env()
        if args.empty_map:
            # TODO: use eunki's argparser options instead
            env_config['env_kwargs']['num_rigid'] = 0
            env_config['env_kwargs']['num_wood'] = 0
            env_config['env_kwargs']['num_items'] = 0

        env_config['env_kwargs']['agent_view_size'] = 4
        env_config['env_kwargs']['max_step'] = args.max_steps
        env = ConservativeEnvWrapper(env_config)
        action_shape = env.action_space.n if hasattr(env.action_space,
                                                     'n') else env.action_space.shape
        observation_shape, additional_shape = env.observation_shape

        def obs_handler(obs, keys=['locational', 'additional']):
            if isinstance(obs, dict):
                loc, add = [obs[key] for key in keys]
            else:
                loc = []
                add = []
                for o in obs:
                    loc.append(o[0]['locational'])
                    add.append(o[0]['additional'])
                loc = np.stack(loc, axis=0)
                add = np.stack(add, axis=0)
            return loc, add

        model = SACModelDISC(observation_shape,
                             (action_shape,),
                             discrete=True,
                             injection_shape=additional_shape,
                             preprocessor=obs_handler,
                             lr_ac=config.lr_ac,
                             lr_cr=config.lr_cr)
        # observation: tuple, action_shape: int
        trainee_agent = SACAgentDISC(model,
                                     batch_size=config.batch_size,
                                     train_interval=config.train_interval,
                                     train_after=config.train_after,
                                     update_interval=config.update_interval,
                                     update_after=config.update_after,
                                     render_interval=config.render_interval,
                                     save_interval=config.save_interval,
                                     buffer_cls=ReplayBuffer,
                                     buffer_kwargs=buffer_kwargs,
                                     save_dir=config.save_dir,
                                     eps = config.eps,
                                     rand_until=config.rand_until,
                                     # log_dir='sac_discrete/train/log',
                                     character=Bomber(0, env_config["game_type"]))

        agents = {
            0: trainee_agent,
            1: SimpleAgent(env_config['agent'](1, env_config["game_type"]))
        }

        env.set_agents(list(agents.values))
        env.set_training_agents(0)
        env.seed(args.seed)

        worker = SACDworker(env,
                            agents=[trainee_agent],
                            n_agents=args.n_agents,
                            n_env=config.n_env,
                            max_episodes=3e4,
                            training=True,
                            logger=logger, 
                            log_interval=config.log_interval,
                            render=config.render,
                            render_interval=config.render_interval,
                            is_save= True,
                            random_until=config.rand_until)

        worker.run()

    if args.env == 'snake':
        raise NotImplementedError

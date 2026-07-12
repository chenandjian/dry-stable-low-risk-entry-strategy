# 策略6双路径历史回测与参数调优报告

## 可信度

- 运行ID：`s6bt-aa448a5523c49c7223ac`
- 可信度：`RESEARCH_ONLY_CURRENT_UNIVERSE`
- OOS状态：`OOS_LOCKED`
- OOS起始：`2026-01-01`
- 幸存者偏差：存在
- 历史ST、退市和停牌状态不完整，结果仅用于研究，不构成生产参数升级依据。

## 汇总指标

| 指标 | 数值 |
| --- | ---: |
| avg_loss_r | 1.0261854068965517 |
| avg_net_return | -0.02498339010869565 |
| avg_win_r | 2.518105076923077 |
| equal_weight_portfolio | {'trades': 95, 'wins': 18, 'losses': 77, 'win_rate': 0.18947368421052632, 'avg_win_r': 2.1882923333333335, 'avg_loss_r': 1.0140905714285715, 'expectancy_r': -0.4073232842105263, 'profit_factor': 0.4926527089523539, 'avg_net_return': -0.030925262631578947, 'median_net_return': -0.06704872, 'net_profit': -459701.143044, 'initial_equity': 1000000.0, 'final_equity': 540298.8569559999, 'net_return': -0.4597011430440001, 'max_drawdown': 0.5054959345633627} |
| expectancy_r | -0.27494992391304346 |
| fixed_risk_portfolio | {'trades': 113, 'wins': 27, 'losses': 86, 'win_rate': 0.23893805309734514, 'avg_win_r': 2.4138301481481483, 'avg_loss_r': 1.0066673139534883, 'expectancy_r': -0.18938030973451328, 'profit_factor': 0.6103609250364849, 'avg_net_return': -0.017749504955752213, 'median_net_return': -0.0662007, 'net_profit': -300175.337196, 'initial_equity': 1000000.0, 'final_equity': 699824.6628040004, 'net_return': -0.30017533719599954, 'max_drawdown': 0.32491914543121625} |
| losses | 145 |
| median_net_return | -0.06336705 |
| net_profit | -21743.035469 |
| profit_factor | 0.5366129385310102 |
| trades | 184 |
| unfilled_rate | 0.7401129943502824 |
| win_rate | 0.21195652173913043 |
| wins | 39 |

## 实验对比

| 实验 | 结果 |
| --- | --- |
| E0_ORIGINAL_BASELINE | `{"avg_loss_r": 1.0204185833333332, "avg_net_return": -0.014103189032258063, "avg_win_r": 3.0212957142857144, "equal_weight_portfolio": {"avg_loss_r": 1.020201652173913, "avg_net_return": -0.012865892333333332, "avg_win_r": 3.0212957142857144, "expectancy_r": -0.0771856, "final_equity": 906105.1486070002, "initial_equity": 1000000.0, "losses": 23, "max_drawdown": 0.15998601836816498, "median_net_return": -0.06933868, "net_profit": -93894.851393, "net_return": -0.0938948513929998, "profit_factor": 0.739144492600384, "trades": 30, "win_rate": 0.23333333333333334, "wins": 7}, "expectancy_r": -0.10777341935483871, "fixed_risk_portfolio": {"avg_loss_r": 1.020201652173913, "avg_net_return": -0.012865892333333332, "avg_win_r": 3.0212957142857144, "expectancy_r": -0.0771856, "final_equity": 941756.1387729998, "initial_equity": 1000000.0, "losses": 23, "max_drawdown": 0.11693200035614411, "median_net_return": -0.06933868, "net_profit": -58243.861227, "net_return": -0.058243861227000204, "profit_factor": 0.7709076031011031, "trades": 30, "win_rate": 0.23333333333333334, "wins": 7}, "losses": 24, "median_net_return": -0.06828661, "net_profit": -1150.7663679999998, "profit_factor": 0.8343166095597508, "trades": 31, "unfilled_rate": 0.8402061855670103, "win_rate": 0.22580645161290322, "wins": 7}` |
| E1_DUAL_DEFAULT | `{"avg_loss_r": 1.0261854068965517, "avg_net_return": -0.02498339010869565, "avg_win_r": 2.518105076923077, "expectancy_r": -0.27494992391304346, "losses": 145, "median_net_return": -0.06336705, "net_profit": -21743.035469, "profit_factor": 0.5366129385310102, "trades": 184, "win_rate": 0.21195652173913043, "wins": 39}` |
| E2_BOX_ONLY_INCREMENT | `{"avg_loss_r": 1.0285186776859505, "avg_net_return": -0.027561079934640523, "avg_win_r": 2.408032125, "expectancy_r": -0.30976295424836603, "losses": 121, "median_net_return": -0.06330153, "net_profit": -20787.7754, "profit_factor": 0.48252951155296026, "trades": 153, "win_rate": 0.20915032679738563, "wins": 32}` |
| E3_BOTH_ONLY | `{"avg_loss_r": 1.0118333, "avg_net_return": 0.0013324333333333339, "avg_win_r": 3.0212957142857144, "expectancy_r": 0.033792740740740734, "losses": 20, "median_net_return": -0.05691296, "net_profit": 187.67575800000017, "profit_factor": 1.033470897091732, "trades": 27, "win_rate": 0.25925925925925924, "wins": 7}` |
| E4_BOX_COMPACT_READY | `{"avg_loss_r": 1.0182537435897436, "avg_net_return": -0.005378437407407407, "avg_win_r": 2.9393344666666668, "expectancy_r": 0.08107631481481481, "losses": 39, "median_net_return": -0.055615725000000005, "net_profit": -3452.799835, "profit_factor": 0.786667929727522, "trades": 54, "win_rate": 0.2777777777777778, "wins": 15}` |
| E5_BOX_BREAKOUT_READY | `{"avg_loss_r": 1.0162619047619048, "avg_net_return": -0.021549887037037037, "avg_win_r": 2.5158981666666667, "expectancy_r": -0.23133744444444446, "losses": 21, "median_net_return": -0.05651691, "net_profit": -5117.403116, "profit_factor": 0.43920346266978716, "trades": 27, "win_rate": 0.2222222222222222, "wins": 6}` |
| E5_BOX_STABLE | `{"avg_loss_r": 1.0908791612903226, "avg_net_return": -0.02493578794871795, "avg_win_r": 2.93617475, "expectancy_r": -0.2648168205128205, "losses": 31, "median_net_return": -0.06263697, "net_profit": -153.4695649999997, "profit_factor": 0.986122065902695, "trades": 39, "win_rate": 0.20512820512820512, "wins": 8}` |
| E5_BOX_SUPPORT_READY | `{"avg_loss_r": 1.0059401348314607, "avg_net_return": -0.023039709210526317, "avg_win_r": 2.38485244, "expectancy_r": -0.26234527192982454, "losses": 89, "median_net_return": -0.06660358, "net_profit": -15329.226961, "profit_factor": 0.40109133278115344, "trades": 114, "win_rate": 0.21929824561403508, "wins": 25}` |

## 明细文件

- 每日候选：`s6bt-aa448a5523c49c7223ac-daily-candidates.csv`
- 订单：`s6bt-aa448a5523c49c7223ac-orders.csv`
- 交易：`s6bt-aa448a5523c49c7223ac-trades.csv`
- 参数试验：`s6bt-aa448a5523c49c7223ac-parameter-trials.csv`

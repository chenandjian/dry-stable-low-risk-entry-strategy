# 策略6历史回测与参数调优报告

## 可信度

- 运行ID：`s6bt-a2bfa470fa23daf14703`
- 可信度：`RESEARCH_ONLY_CURRENT_UNIVERSE`
- OOS状态：`OOS_LOCKED`
- OOS起始：`2026-01-01`
- 幸存者偏差：存在
- 历史ST、退市和停牌状态不完整，结果仅用于研究，不构成生产参数升级依据。

## 汇总指标

| 指标 | 数值 |
| --- | ---: |
| avg_loss_r | 1.0310127 |
| avg_net_return | -0.04981189 |
| avg_win_r | 3.357892 |
| equal_weight_portfolio | {'trades': 12, 'wins': 2, 'losses': 10, 'win_rate': 0.16666666666666666, 'avg_win_r': 3.357892, 'avg_loss_r': 1.0310127, 'expectancy_r': -0.2995285833333333, 'profit_factor': 0.36736489204768386, 'avg_net_return': -0.04981189, 'median_net_return': -0.08783665, 'net_profit': -113200.570907, 'initial_equity': 1000000.0, 'final_equity': 886799.429093, 'net_return': -0.11320057090699998, 'max_drawdown': 0.11320057090699999} |
| expectancy_r | -0.2995285833333333 |
| fixed_risk_portfolio | {'trades': 12, 'wins': 2, 'losses': 10, 'win_rate': 0.16666666666666666, 'avg_win_r': 3.357892, 'avg_loss_r': 1.0310127, 'expectancy_r': -0.2995285833333333, 'profit_factor': 0.5813916034319343, 'avg_net_return': -0.04981189, 'median_net_return': -0.08783665, 'net_profit': -45099.910928000005, 'initial_equity': 1000000.0, 'final_equity': 954900.089072, 'net_return': -0.04509991092800003, 'max_drawdown': 0.053708089338761957} |
| losses | 10 |
| median_net_return | -0.08783665 |
| net_profit | -1560.181972 |
| profit_factor | 0.18478867053207682 |
| trades | 12 |
| unfilled_rate | 0.6923076923076923 |
| win_rate | 0.16666666666666666 |
| wins | 2 |

## 旧双路径归因

| 实验 | 结果 |
| --- | --- |
| BOTH | `{"avg_loss_r": 1.013474, "avg_net_return": -0.07582322, "avg_win_r": 0.0, "expectancy_r": -1.013474, "losses": 1, "median_net_return": -0.07582322, "net_profit": -142.538403, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}` |
| BOX | `{"avg_loss_r": 1.03597275, "avg_net_return": -0.041409808, "avg_win_r": 3.357892, "expectancy_r": -0.15719979999999995, "losses": 8, "median_net_return": -0.08783665, "net_profit": -1208.0450600000001, "profit_factor": 0.22645537309791208, "trades": 10, "win_rate": 0.2, "wins": 2}` |
| ORIGINAL | `{"avg_loss_r": 1.008871, "avg_net_return": -0.10782138, "avg_win_r": 0.0, "expectancy_r": -1.008871, "losses": 1, "median_net_return": -0.10782138, "net_profit": -209.598509, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}` |

## 权威三路径归因

| 实验 | 结果 |
| --- | --- |
| BOX | `{"avg_loss_r": 1.0334728888888889, "avg_net_return": -0.0445383, "avg_win_r": 3.357892, "expectancy_r": -0.23504290909090905, "losses": 9, "median_net_return": -0.0871403, "net_profit": -1350.583463, "profit_factor": 0.2075151960748443, "trades": 11, "win_rate": 0.18181818181818182, "wins": 2}` |
| BROOKS | `{"avg_loss_r": 0.0, "avg_net_return": 0.07037548, "avg_win_r": 1.277843, "expectancy_r": 1.277843, "losses": 0, "median_net_return": 0.07037548, "net_profit": 92.530631, "profit_factor": Infinity, "trades": 1, "win_rate": 1.0, "wins": 1}` |
| ORIGINAL | `{"avg_loss_r": 1.0111725, "avg_net_return": -0.0918223, "avg_win_r": 0.0, "expectancy_r": -1.0111725, "losses": 2, "median_net_return": -0.0918223, "net_profit": -352.136912, "profit_factor": 0.0, "trades": 2, "win_rate": 0.0, "wins": 0}` |

## 权威主路径与汇总

| 实验 | 结果 |
| --- | --- |
| primary | `{"BOX": {"avg_loss_r": 1.03597275, "avg_net_return": -0.053830395555555556, "avg_win_r": 5.437941, "expectancy_r": -0.31664899999999996, "losses": 8, "median_net_return": -0.088533, "net_profit": -1300.575691, "profit_factor": 0.16720545370011264, "trades": 9, "win_rate": 0.1111111111111111, "wins": 1}, "BROOKS": {"avg_loss_r": 0.0, "avg_net_return": 0.07037548, "avg_win_r": 1.277843, "expectancy_r": 1.277843, "losses": 0, "median_net_return": 0.07037548, "net_profit": 92.530631, "profit_factor": Infinity, "trades": 1, "win_rate": 1.0, "wins": 1}, "ORIGINAL": {"avg_loss_r": 1.0111725, "avg_net_return": -0.0918223, "avg_win_r": 0.0, "expectancy_r": -1.0111725, "losses": 2, "median_net_return": -0.0918223, "net_profit": -352.136912, "profit_factor": 0.0, "trades": 2, "win_rate": 0.0, "wins": 0}}` |
| summary | `{"BOX": {"avg_loss_r": 1.03597275, "avg_net_return": -0.053830395555555556, "avg_win_r": 5.437941, "expectancy_r": -0.31664899999999996, "losses": 8, "median_net_return": -0.088533, "net_profit": -1300.575691, "profit_factor": 0.16720545370011264, "trades": 9, "win_rate": 0.1111111111111111, "wins": 1}, "MULTI": {"avg_loss_r": 1.013474, "avg_net_return": -0.0027238699999999963, "avg_win_r": 1.277843, "expectancy_r": 0.13218450000000004, "losses": 1, "median_net_return": -0.0027238699999999963, "net_profit": -50.00777199999999, "profit_factor": 0.6491628154413938, "trades": 2, "win_rate": 0.5, "wins": 1}, "ORIGINAL": {"avg_loss_r": 1.008871, "avg_net_return": -0.10782138, "avg_win_r": 0.0, "expectancy_r": -1.008871, "losses": 1, "median_net_return": -0.10782138, "net_profit": -209.598509, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}}` |

## Brooks状态与结构

| 实验 | 结果 |
| --- | --- |
| status | `{"BROOKS_CONTEXT_REJECT": {"avg_loss_r": 1.0458586666666667, "avg_net_return": -0.08011005833333333, "avg_win_r": 0.0, "expectancy_r": -1.0458586666666667, "losses": 6, "median_net_return": -0.08148176, "net_profit": -1229.031495, "profit_factor": 0.0, "trades": 6, "win_rate": 0.0, "wins": 0}, "BROOKS_FAILED": {"avg_loss_r": 1.00874375, "avg_net_return": -0.1136157275, "avg_win_r": 0.0, "expectancy_r": -1.00874375, "losses": 4, "median_net_return": -0.112842635, "net_profit": -684.805955, "profit_factor": 0.0, "trades": 4, "win_rate": 0.0, "wins": 0}, "BROOKS_FAILED_BREAKOUT_READY": {"avg_loss_r": 0.0, "avg_net_return": 0.07037548, "avg_win_r": 1.277843, "expectancy_r": 1.277843, "losses": 0, "median_net_return": 0.07037548, "net_profit": 92.530631, "profit_factor": Infinity, "trades": 1, "win_rate": 1.0, "wins": 1}, "COMPACT_BEARISH_REJECT": {"avg_loss_r": 0.0, "avg_net_return": 0.2670051, "avg_win_r": 5.437941, "expectancy_r": 5.437941, "losses": 0, "median_net_return": 0.2670051, "net_profit": 261.124847, "profit_factor": Infinity, "trades": 1, "win_rate": 1.0, "wins": 1}}` |
| structure | `{"BEAR_FOLLOW_THROUGH_FAILED": {"avg_loss_r": 1.0128515, "avg_net_return": -0.08280735, "avg_win_r": 0.0, "expectancy_r": -1.0128515, "losses": 4, "median_net_return": -0.08217811, "net_profit": -586.818543, "profit_factor": 0.0, "trades": 4, "win_rate": 0.0, "wins": 0}, "FAILED_BEAR_BREAKOUT": {"avg_loss_r": 1.112522, "avg_net_return": -0.021050396666666665, "avg_win_r": 1.277843, "expectancy_r": -0.31573366666666663, "losses": 2, "median_net_return": -0.05770345, "net_profit": -603.359622, "profit_factor": 0.13296727551664672, "trades": 3, "win_rate": 0.3333333333333333, "wins": 1}, "MICRO_DOUBLE_BOTTOM": {"avg_loss_r": 1.112522, "avg_net_return": -0.06676333500000001, "avg_win_r": 0.0, "expectancy_r": -1.112522, "losses": 2, "median_net_return": -0.06676333500000001, "net_profit": -695.890253, "profit_factor": 0.0, "trades": 2, "win_rate": 0.0, "wins": 0}}` |

## 实验对比

无实验结果。

## 训练与验证

无实验结果。

## 压力测试

无实验结果。

## 滚动验证

`{}`

## 参数优化与建议

- 优化结论：`INSUFFICIENT_DATA`
- 最终决策：`INSUFFICIENT_DATA`
- 生产配置已修改：`False`

## 明细文件

- 每日候选：`s6bt-a2bfa470fa23daf14703-daily-candidates.csv`
- 订单：`s6bt-a2bfa470fa23daf14703-orders.csv`
- 交易：`s6bt-a2bfa470fa23daf14703-trades.csv`
- 参数试验：`s6bt-a2bfa470fa23daf14703-parameter-trials.csv`

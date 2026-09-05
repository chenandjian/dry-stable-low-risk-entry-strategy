# 策略6历史回测与参数调优报告

## 可信度

- 运行ID：`s6bt-0f1deb0a2fd3df6d15e7`
- 可信度：`RESEARCH_ONLY_CURRENT_UNIVERSE`
- OOS状态：`OOS_LOCKED`
- OOS起始：`2026-01-01`
- 幸存者偏差：存在
- 历史ST、退市和停牌状态不完整，结果仅用于研究，不构成生产参数升级依据。

## 汇总指标

| 指标 | 数值 |
| --- | ---: |
| avg_loss_r | 1.0472006086956522 |
| avg_net_return | -0.0461072948 |
| avg_win_r | 5.484767 |
| equal_weight_portfolio | {'trades': 20, 'wins': 2, 'losses': 18, 'win_rate': 0.1, 'avg_win_r': 5.484767, 'avg_loss_r': 1.028060611111111, 'expectancy_r': -0.37677785, 'profit_factor': 0.34778767242896536, 'avg_net_return': -0.039837878, 'median_net_return': -0.06607828, 'net_profit': -152432.912834, 'initial_equity': 1000000.0, 'final_equity': 847567.0871659998, 'net_return': -0.15243291283400018, 'max_drawdown': 0.19444334592131698} |
| expectancy_r | -0.5246432000000001 |
| fixed_risk_portfolio | {'trades': 22, 'wins': 2, 'losses': 20, 'win_rate': 0.09090909090909091, 'avg_win_r': 5.484767, 'avg_loss_r': 1.02714265, 'expectancy_r': -0.4351508636363637, 'profit_factor': 0.38384429693854055, 'avg_net_return': -0.04145100318181818, 'median_net_return': -0.06607828, 'net_profit': -130478.60647299999, 'initial_equity': 1000000.0, 'final_equity': 869521.3935269999, 'net_return': -0.13047860647300014, 'max_drawdown': 0.17893300712950305} |
| losses | 23 |
| median_net_return | -0.0663677 |
| net_profit | -3857.363235 |
| profit_factor | 0.16269707843940642 |
| trades | 25 |
| unfilled_rate | 0.24242424242424243 |
| win_rate | 0.08 |
| wins | 2 |

## 旧双路径归因

| 实验 | 结果 |
| --- | --- |
| ORIGINAL | `{"avg_loss_r": 1.0472006086956522, "avg_net_return": -0.0461072948, "avg_win_r": 5.484767, "expectancy_r": -0.5246432000000001, "losses": 23, "median_net_return": -0.0663677, "net_profit": -3857.363235, "profit_factor": 0.16269707843940642, "trades": 25, "win_rate": 0.08, "wins": 2}` |

## 权威三路径归因

| 实验 | 结果 |
| --- | --- |
| ORIGINAL | `{"avg_loss_r": 1.0472006086956522, "avg_net_return": -0.0461072948, "avg_win_r": 5.484767, "expectancy_r": -0.5246432000000001, "losses": 23, "median_net_return": -0.0663677, "net_profit": -3857.363235, "profit_factor": 0.16269707843940642, "trades": 25, "win_rate": 0.08, "wins": 2}` |

## 权威主路径与汇总

| 实验 | 结果 |
| --- | --- |
| primary | `{"ORIGINAL": {"avg_loss_r": 1.0472006086956522, "avg_net_return": -0.0461072948, "avg_win_r": 5.484767, "expectancy_r": -0.5246432000000001, "losses": 23, "median_net_return": -0.0663677, "net_profit": -3857.363235, "profit_factor": 0.16269707843940642, "trades": 25, "win_rate": 0.08, "wins": 2}}` |
| summary | `{"ORIGINAL": {"avg_loss_r": 1.0472006086956522, "avg_net_return": -0.0461072948, "avg_win_r": 5.484767, "expectancy_r": -0.5246432000000001, "losses": 23, "median_net_return": -0.0663677, "net_profit": -3857.363235, "profit_factor": 0.16269707843940642, "trades": 25, "win_rate": 0.08, "wins": 2}}` |

## Brooks状态与结构

| 实验 | 结果 |
| --- | --- |
| status | `{"BROOKS_DISABLED": {"avg_loss_r": 1.0472006086956522, "avg_net_return": -0.0461072948, "avg_win_r": 5.484767, "expectancy_r": -0.5246432000000001, "losses": 23, "median_net_return": -0.0663677, "net_profit": -3857.363235, "profit_factor": 0.16269707843940642, "trades": 25, "win_rate": 0.08, "wins": 2}}` |
| structure | `{}` |

## 入场类型与质量归因

| 实验 | 结果 |
| --- | --- |
| entry_archetype | `{"SUPPORT_PULLBACK": {"avg_loss_r": 1.0472006086956522, "avg_net_return": -0.0461072948, "avg_win_r": 5.484767, "expectancy_r": -0.5246432000000001, "losses": 23, "median_net_return": -0.0663677, "net_profit": -3857.363235, "profit_factor": 0.16269707843940642, "trades": 25, "win_rate": 0.08, "wins": 2}}` |
| path_evidence | `{"15-19": {"avg_loss_r": 1.015941, "avg_net_return": 0.060791994999999995, "avg_win_r": 6.23199, "expectancy_r": 2.6080245, "losses": 1, "median_net_return": 0.060791994999999995, "net_profit": 63.19159300000001, "profit_factor": 1.3434484924763088, "trades": 2, "win_rate": 0.5, "wins": 1}, "20-24": {"avg_loss_r": 1.0486215, "avg_net_return": -0.055402885217391305, "avg_win_r": 4.737544, "expectancy_r": -0.7970490869565218, "losses": 22, "median_net_return": -0.06860136, "net_profit": -3920.554828, "profit_factor": 0.11357812596535939, "trades": 23, "win_rate": 0.043478260869565216, "wins": 1}}` |
| setup_quality | `{"05-09": {"avg_loss_r": 1.020436, "avg_net_return": -0.05340668, "avg_win_r": 0.0, "expectancy_r": -1.020436, "losses": 1, "median_net_return": -0.05340668, "net_profit": -100.611883, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}, "10-14": {"avg_loss_r": 1.096699375, "avg_net_return": -0.021583997, "avg_win_r": 5.484767, "expectancy_r": 0.21959389999999993, "losses": 8, "median_net_return": -0.07479488000000001, "net_profit": -1529.079658, "profit_factor": 0.3289411376704181, "trades": 10, "win_rate": 0.2, "wins": 2}, "15-19": {"avg_loss_r": 1.0208273571428572, "avg_net_return": -0.06310255142857144, "avg_win_r": 0.0, "expectancy_r": -1.0208273571428572, "losses": 14, "median_net_return": -0.06486098000000001, "net_profit": -2227.671694, "profit_factor": 0.0, "trades": 14, "win_rate": 0.0, "wins": 0}}` |
| start_quality | `{"00-04": {"avg_loss_r": 1.023578, "avg_net_return": -0.04405728, "avg_win_r": 0.0, "expectancy_r": -1.023578, "losses": 1, "median_net_return": -0.04405728, "net_profit": -230.318053, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}, "05-09": {"avg_loss_r": 1.011229, "avg_net_return": 0.0457925, "avg_win_r": 6.23199, "expectancy_r": 2.6103804999999998, "losses": 1, "median_net_return": 0.0457925, "net_profit": 159.923674, "profit_factor": 2.8327388700830807, "trades": 2, "win_rate": 0.5, "wins": 1}, "15-19": {"avg_loss_r": 1.0627737692307693, "avg_net_return": -0.04917221857142857, "avg_win_r": 4.737544, "expectancy_r": -0.6484653571428571, "losses": 13, "median_net_return": -0.07038371, "net_profit": -2919.743752, "profit_factor": 0.1467947567773866, "trades": 14, "win_rate": 0.07142857142857142, "wins": 1}, "20-24": {"avg_loss_r": 1.0293435, "avg_net_return": -0.06397487875, "avg_win_r": 0.0, "expectancy_r": -1.0293435, "losses": 8, "median_net_return": -0.06607828, "net_profit": -867.225104, "profit_factor": 0.0, "trades": 8, "win_rate": 0.0, "wins": 0}}` |
| support_reaction | `{"05-09": {"avg_loss_r": 1.0344728571428572, "avg_net_return": -0.034614503125, "avg_win_r": 5.484767, "expectancy_r": -0.21956787500000005, "losses": 14, "median_net_return": -0.06748453, "net_profit": -2136.936061, "profit_factor": 0.2596698792569214, "trades": 16, "win_rate": 0.125, "wins": 2}, "10-14": {"avg_loss_r": 1.0669993333333334, "avg_net_return": -0.06653892444444444, "avg_win_r": 0.0, "expectancy_r": -1.0669993333333334, "losses": 9, "median_net_return": -0.0639331, "net_profit": -1720.427174, "profit_factor": 0.0, "trades": 9, "win_rate": 0.0, "wins": 0}}` |

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

- 每日候选：`s6bt-0f1deb0a2fd3df6d15e7-daily-candidates.csv`
- 订单：`s6bt-0f1deb0a2fd3df6d15e7-orders.csv`
- 交易：`s6bt-0f1deb0a2fd3df6d15e7-trades.csv`
- 参数试验：`s6bt-0f1deb0a2fd3df6d15e7-parameter-trials.csv`

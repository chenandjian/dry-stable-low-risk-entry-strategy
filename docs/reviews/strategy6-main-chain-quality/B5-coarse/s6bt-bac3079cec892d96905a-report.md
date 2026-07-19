# 策略6历史回测与参数调优报告

## 可信度

- 运行ID：`s6bt-bac3079cec892d96905a`
- 可信度：`RESEARCH_ONLY_CURRENT_UNIVERSE`
- OOS状态：`OOS_LOCKED`
- OOS起始：`2026-01-01`
- 幸存者偏差：存在
- 历史ST、退市和停牌状态不完整，结果仅用于研究，不构成生产参数升级依据。

## 汇总指标

| 指标 | 数值 |
| --- | ---: |
| avg_loss_r | 1.0389918333333332 |
| avg_net_return | -0.07745006166666667 |
| avg_win_r | 0.0 |
| equal_weight_portfolio | {'trades': 6, 'wins': 0, 'losses': 6, 'win_rate': 0.0, 'avg_win_r': 0.0, 'avg_loss_r': 1.0389918333333332, 'expectancy_r': -1.0389918333333332, 'profit_factor': 0.0, 'avg_net_return': -0.07745006166666667, 'median_net_return': -0.068977345, 'net_profit': -88761.731413, 'initial_equity': 1000000.0, 'final_equity': 911238.268587, 'net_return': -0.08876173141300003, 'max_drawdown': 0.08876173141300003} |
| expectancy_r | -1.0389918333333332 |
| fixed_risk_portfolio | {'trades': 6, 'wins': 0, 'losses': 6, 'win_rate': 0.0, 'avg_win_r': 0.0, 'avg_loss_r': 1.0389918333333332, 'expectancy_r': -1.0389918333333332, 'profit_factor': 0.0, 'avg_net_return': -0.07745006166666667, 'median_net_return': -0.068977345, 'net_profit': -59457.368013, 'initial_equity': 1000000.0, 'final_equity': 940542.631987, 'net_return': -0.059457368012999945, 'max_drawdown': 0.059457368013} |
| losses | 6 |
| median_net_return | -0.068977345 |
| net_profit | -1317.372913 |
| profit_factor | 0.0 |
| trades | 6 |
| unfilled_rate | 0.25 |
| win_rate | 0.0 |
| wins | 0 |

## 旧双路径归因

| 实验 | 结果 |
| --- | --- |
| BOTH | `{"avg_loss_r": 1.0530035, "avg_net_return": -0.065289335, "avg_win_r": 0.0, "expectancy_r": -1.0530035, "losses": 4, "median_net_return": -0.058235355, "net_profit": -1038.159524, "profit_factor": 0.0, "trades": 4, "win_rate": 0.0, "wins": 0}` |
| BOX | `{"avg_loss_r": 1.007125, "avg_net_return": -0.13373116, "avg_win_r": 0.0, "expectancy_r": -1.007125, "losses": 1, "median_net_return": -0.13373116, "net_profit": -143.503163, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}` |
| ORIGINAL | `{"avg_loss_r": 1.014812, "avg_net_return": -0.06981187, "avg_win_r": 0.0, "expectancy_r": -1.014812, "losses": 1, "median_net_return": -0.06981187, "net_profit": -135.710226, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}` |

## 权威三路径归因

| 实验 | 结果 |
| --- | --- |
| BOX | `{"avg_loss_r": 1.0438278, "avg_net_return": -0.0789777, "avg_win_r": 0.0, "expectancy_r": -1.0438278, "losses": 5, "median_net_return": -0.06814282, "net_profit": -1181.662687, "profit_factor": 0.0, "trades": 5, "win_rate": 0.0, "wins": 0}` |
| BROOKS | `{"avg_loss_r": 1.022211, "avg_net_return": -0.04832789, "avg_win_r": 0.0, "expectancy_r": -1.022211, "losses": 1, "median_net_return": -0.04832789, "net_profit": -127.471334, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}` |
| ORIGINAL | `{"avg_loss_r": 1.0453652, "avg_net_return": -0.066193842, "avg_win_r": 0.0, "expectancy_r": -1.0453652, "losses": 5, "median_net_return": -0.06814282, "net_profit": -1173.86975, "profit_factor": 0.0, "trades": 5, "win_rate": 0.0, "wins": 0}` |

## 权威主路径与汇总

| 实验 | 结果 |
| --- | --- |
| primary | `{"BOX": {"avg_loss_r": 1.007125, "avg_net_return": -0.13373116, "avg_win_r": 0.0, "expectancy_r": -1.007125, "losses": 1, "median_net_return": -0.13373116, "net_profit": -143.503163, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}, "ORIGINAL": {"avg_loss_r": 1.0453652, "avg_net_return": -0.066193842, "avg_win_r": 0.0, "expectancy_r": -1.0453652, "losses": 5, "median_net_return": -0.06814282, "net_profit": -1173.86975, "profit_factor": 0.0, "trades": 5, "win_rate": 0.0, "wins": 0}}` |
| summary | `{"BOX": {"avg_loss_r": 1.007125, "avg_net_return": -0.13373116, "avg_win_r": 0.0, "expectancy_r": -1.007125, "losses": 1, "median_net_return": -0.13373116, "net_profit": -143.503163, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}, "MULTI": {"avg_loss_r": 1.0530035, "avg_net_return": -0.065289335, "avg_win_r": 0.0, "expectancy_r": -1.0530035, "losses": 4, "median_net_return": -0.058235355, "net_profit": -1038.159524, "profit_factor": 0.0, "trades": 4, "win_rate": 0.0, "wins": 0}, "ORIGINAL": {"avg_loss_r": 1.014812, "avg_net_return": -0.06981187, "avg_win_r": 0.0, "expectancy_r": -1.014812, "losses": 1, "median_net_return": -0.06981187, "net_profit": -135.710226, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}}` |

## Brooks状态与结构

| 实验 | 结果 |
| --- | --- |
| status | `{"BROOKS_CONTEXT_REJECT": {"avg_loss_r": 1.032671, "avg_net_return": -0.0348538, "avg_win_r": 0.0, "expectancy_r": -1.032671, "losses": 1, "median_net_return": -0.0348538, "net_profit": -94.722695, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}, "BROOKS_FAILED": {"avg_loss_r": 1.078149, "avg_net_return": -0.08982235, "avg_win_r": 0.0, "expectancy_r": -1.078149, "losses": 2, "median_net_return": -0.08982235, "net_profit": -849.018222, "profit_factor": 0.0, "trades": 2, "win_rate": 0.0, "wins": 0}, "FAILED_BEAR_BREAKOUT": {"avg_loss_r": 1.0189285, "avg_net_return": -0.058235355, "avg_win_r": 0.0, "expectancy_r": -1.0189285, "losses": 2, "median_net_return": -0.058235355, "net_profit": -230.128833, "profit_factor": 0.0, "trades": 2, "win_rate": 0.0, "wins": 0}, "MICRO_DOUBLE_BOTTOM": {"avg_loss_r": 1.007125, "avg_net_return": -0.13373116, "avg_win_r": 0.0, "expectancy_r": -1.007125, "losses": 1, "median_net_return": -0.13373116, "net_profit": -143.503163, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}}` |
| structure | `{"BEAR_FOLLOW_THROUGH_FAILED": {"avg_loss_r": 1.0743055, "avg_net_return": -0.121781995, "avg_win_r": 0.0, "expectancy_r": -1.0743055, "losses": 2, "median_net_return": -0.121781995, "net_profit": -856.811159, "profit_factor": 0.0, "trades": 2, "win_rate": 0.0, "wins": 0}, "FAILED_BEAR_BREAKOUT": {"avg_loss_r": 1.0235093333333334, "avg_net_return": -0.05044150333333333, "avg_win_r": 0.0, "expectancy_r": -1.0235093333333334, "losses": 3, "median_net_return": -0.04832789, "net_profit": -324.85152800000003, "profit_factor": 0.0, "trades": 3, "win_rate": 0.0, "wins": 0}, "MICRO_DOUBLE_BOTTOM": {"avg_loss_r": 1.0184806666666666, "avg_net_return": -0.07890926, "avg_win_r": 0.0, "expectancy_r": -1.0184806666666666, "losses": 3, "median_net_return": -0.06814282, "net_profit": -340.883357, "profit_factor": 0.0, "trades": 3, "win_rate": 0.0, "wins": 0}, "SECOND_ENTRY_LONG_READY": {"avg_loss_r": 1.032671, "avg_net_return": -0.0348538, "avg_win_r": 0.0, "expectancy_r": -1.032671, "losses": 1, "median_net_return": -0.0348538, "net_profit": -94.722695, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}}` |

## 入场类型与质量归因

| 实验 | 结果 |
| --- | --- |
| entry_archetype | `{"SUPPORT_PULLBACK": {"avg_loss_r": 1.0389918333333332, "avg_net_return": -0.07745006166666667, "avg_win_r": 0.0, "expectancy_r": -1.0389918333333332, "losses": 6, "median_net_return": -0.068977345, "net_profit": -1317.372913, "profit_factor": 0.0, "trades": 6, "win_rate": 0.0, "wins": 0}}` |
| path_evidence | `{"00-04": {"avg_loss_r": 1.007125, "avg_net_return": -0.13373116, "avg_win_r": 0.0, "expectancy_r": -1.007125, "losses": 1, "median_net_return": -0.13373116, "net_profit": -143.503163, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}, "10-14": {"avg_loss_r": 1.014812, "avg_net_return": -0.06981187, "avg_win_r": 0.0, "expectancy_r": -1.014812, "losses": 1, "median_net_return": -0.06981187, "net_profit": -135.710226, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}, "15-19": {"avg_loss_r": 1.0530035, "avg_net_return": -0.065289335, "avg_win_r": 0.0, "expectancy_r": -1.0530035, "losses": 4, "median_net_return": -0.058235355, "net_profit": -1038.159524, "profit_factor": 0.0, "trades": 4, "win_rate": 0.0, "wins": 0}}` |
| setup_quality | `{"15-19": {"avg_loss_r": 1.0389918333333332, "avg_net_return": -0.07745006166666667, "avg_win_r": 0.0, "expectancy_r": -1.0389918333333332, "losses": 6, "median_net_return": -0.068977345, "net_profit": -1317.372913, "profit_factor": 0.0, "trades": 6, "win_rate": 0.0, "wins": 0}}` |
| start_quality | `{"15-19": {"avg_loss_r": 1.014668, "avg_net_return": -0.091029525, "avg_win_r": 0.0, "expectancy_r": -1.014668, "losses": 2, "median_net_return": -0.091029525, "net_profit": -270.974497, "profit_factor": 0.0, "trades": 2, "win_rate": 0.0, "wins": 0}, "20-24": {"avg_loss_r": 1.05115375, "avg_net_return": -0.07066033000000001, "avg_win_r": 0.0, "expectancy_r": -1.05115375, "losses": 4, "median_net_return": -0.068977345, "net_profit": -1046.398416, "profit_factor": 0.0, "trades": 4, "win_rate": 0.0, "wins": 0}}` |
| support_reaction | `{"05-09": {"avg_loss_r": 1.014668, "avg_net_return": -0.091029525, "avg_win_r": 0.0, "expectancy_r": -1.014668, "losses": 2, "median_net_return": -0.091029525, "net_profit": -270.974497, "profit_factor": 0.0, "trades": 2, "win_rate": 0.0, "wins": 0}, "10-14": {"avg_loss_r": 1.05115375, "avg_net_return": -0.07066033000000001, "avg_win_r": 0.0, "expectancy_r": -1.05115375, "losses": 4, "median_net_return": -0.068977345, "net_profit": -1046.398416, "profit_factor": 0.0, "trades": 4, "win_rate": 0.0, "wins": 0}}` |

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

- 每日候选：`s6bt-bac3079cec892d96905a-daily-candidates.csv`
- 订单：`s6bt-bac3079cec892d96905a-orders.csv`
- 交易：`s6bt-bac3079cec892d96905a-trades.csv`
- 参数试验：`s6bt-bac3079cec892d96905a-parameter-trials.csv`

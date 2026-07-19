# 策略6历史回测与参数调优报告

## 可信度

- 运行ID：`s6bt-913e70dc048b07da25e1`
- 可信度：`RESEARCH_ONLY_CURRENT_UNIVERSE`
- OOS状态：`OOS_LOCKED`
- OOS起始：`2026-01-01`
- 幸存者偏差：存在
- 历史ST、退市和停牌状态不完整，结果仅用于研究，不构成生产参数升级依据。

## 汇总指标

| 指标 | 数值 |
| --- | ---: |
| avg_loss_r | 1.0111725 |
| avg_net_return | -0.0918223 |
| avg_win_r | 0.0 |
| equal_weight_portfolio | {'trades': 2, 'wins': 0, 'losses': 2, 'win_rate': 0.0, 'avg_win_r': 0.0, 'avg_loss_r': 1.0111725, 'expectancy_r': -1.0111725, 'profit_factor': 0.0, 'avg_net_return': -0.0918223, 'median_net_return': -0.0918223, 'net_profit': -36203.04183, 'initial_equity': 1000000.0, 'final_equity': 963796.95817, 'net_return': -0.036203041830000005, 'max_drawdown': 0.036203041830000005} |
| expectancy_r | -1.0111725 |
| fixed_risk_portfolio | {'trades': 2, 'wins': 0, 'losses': 2, 'win_rate': 0.0, 'avg_win_r': 0.0, 'avg_loss_r': 1.0111725, 'expectancy_r': -1.0111725, 'profit_factor': 0.0, 'avg_net_return': -0.0918223, 'median_net_return': -0.0918223, 'net_profit': -21312.844078000002, 'initial_equity': 1000000.0, 'final_equity': 978687.1559220001, 'net_return': -0.021312844077999937, 'max_drawdown': 0.021312844077999937} |
| losses | 2 |
| median_net_return | -0.0918223 |
| net_profit | -352.136912 |
| profit_factor | 0.0 |
| trades | 2 |
| unfilled_rate | 0.8 |
| win_rate | 0.0 |
| wins | 0 |

## 旧双路径归因

| 实验 | 结果 |
| --- | --- |
| BOTH | `{"avg_loss_r": 1.013474, "avg_net_return": -0.07582322, "avg_win_r": 0.0, "expectancy_r": -1.013474, "losses": 1, "median_net_return": -0.07582322, "net_profit": -142.538403, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}` |
| ORIGINAL | `{"avg_loss_r": 1.008871, "avg_net_return": -0.10782138, "avg_win_r": 0.0, "expectancy_r": -1.008871, "losses": 1, "median_net_return": -0.10782138, "net_profit": -209.598509, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}` |

## 权威三路径归因

| 实验 | 结果 |
| --- | --- |
| BOX | `{"avg_loss_r": 1.013474, "avg_net_return": -0.07582322, "avg_win_r": 0.0, "expectancy_r": -1.013474, "losses": 1, "median_net_return": -0.07582322, "net_profit": -142.538403, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}` |
| BROOKS | `{"avg_loss_r": 1.013474, "avg_net_return": -0.07582322, "avg_win_r": 0.0, "expectancy_r": -1.013474, "losses": 1, "median_net_return": -0.07582322, "net_profit": -142.538403, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}` |
| ORIGINAL | `{"avg_loss_r": 1.0111725, "avg_net_return": -0.0918223, "avg_win_r": 0.0, "expectancy_r": -1.0111725, "losses": 2, "median_net_return": -0.0918223, "net_profit": -352.136912, "profit_factor": 0.0, "trades": 2, "win_rate": 0.0, "wins": 0}` |

## 权威主路径与汇总

| 实验 | 结果 |
| --- | --- |
| primary | `{"ORIGINAL": {"avg_loss_r": 1.0111725, "avg_net_return": -0.0918223, "avg_win_r": 0.0, "expectancy_r": -1.0111725, "losses": 2, "median_net_return": -0.0918223, "net_profit": -352.136912, "profit_factor": 0.0, "trades": 2, "win_rate": 0.0, "wins": 0}}` |
| summary | `{"MULTI": {"avg_loss_r": 1.013474, "avg_net_return": -0.07582322, "avg_win_r": 0.0, "expectancy_r": -1.013474, "losses": 1, "median_net_return": -0.07582322, "net_profit": -142.538403, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}, "ORIGINAL": {"avg_loss_r": 1.008871, "avg_net_return": -0.10782138, "avg_win_r": 0.0, "expectancy_r": -1.008871, "losses": 1, "median_net_return": -0.10782138, "net_profit": -209.598509, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}}` |

## Brooks状态与结构

| 实验 | 结果 |
| --- | --- |
| status | `{"BROOKS_FAILED": {"avg_loss_r": 1.008871, "avg_net_return": -0.10782138, "avg_win_r": 0.0, "expectancy_r": -1.008871, "losses": 1, "median_net_return": -0.10782138, "net_profit": -209.598509, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}, "BROOKS_FAILED_BREAKOUT_READY": {"avg_loss_r": 1.013474, "avg_net_return": -0.07582322, "avg_win_r": 0.0, "expectancy_r": -1.013474, "losses": 1, "median_net_return": -0.07582322, "net_profit": -142.538403, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}}` |
| structure | `{"BEAR_FOLLOW_THROUGH_FAILED": {"avg_loss_r": 1.013474, "avg_net_return": -0.07582322, "avg_win_r": 0.0, "expectancy_r": -1.013474, "losses": 1, "median_net_return": -0.07582322, "net_profit": -142.538403, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}, "FAILED_BEAR_BREAKOUT": {"avg_loss_r": 1.013474, "avg_net_return": -0.07582322, "avg_win_r": 0.0, "expectancy_r": -1.013474, "losses": 1, "median_net_return": -0.07582322, "net_profit": -142.538403, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}, "MICRO_DOUBLE_BOTTOM": {"avg_loss_r": 1.013474, "avg_net_return": -0.07582322, "avg_win_r": 0.0, "expectancy_r": -1.013474, "losses": 1, "median_net_return": -0.07582322, "net_profit": -142.538403, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}, "ORDERLY_COMPRESSION_AT_SUPPORT": {"avg_loss_r": 1.013474, "avg_net_return": -0.07582322, "avg_win_r": 0.0, "expectancy_r": -1.013474, "losses": 1, "median_net_return": -0.07582322, "net_profit": -142.538403, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}}` |

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

- 每日候选：`s6bt-913e70dc048b07da25e1-daily-candidates.csv`
- 订单：`s6bt-913e70dc048b07da25e1-orders.csv`
- 交易：`s6bt-913e70dc048b07da25e1-trades.csv`
- 参数试验：`s6bt-913e70dc048b07da25e1-parameter-trials.csv`

# 策略6历史回测与参数调优报告

## 可信度

- 运行ID：`s6bt-46913bb97feee28bc538`
- 可信度：`RESEARCH_ONLY_CURRENT_UNIVERSE`
- OOS状态：`OOS_LOCKED`
- OOS起始：`2026-01-01`
- 幸存者偏差：存在
- 历史ST、退市和停牌状态不完整，结果仅用于研究，不构成生产参数升级依据。

## 汇总指标

| 指标 | 数值 |
| --- | ---: |
| avg_loss_r | 1.0890584545454545 |
| avg_net_return | -0.052891871666666666 |
| avg_win_r | 4.456959 |
| equal_weight_portfolio | {'trades': 11, 'wins': 1, 'losses': 10, 'win_rate': 0.09090909090909091, 'avg_win_r': 4.456959, 'avg_loss_r': 1.0966013000000001, 'expectancy_r': -0.5917321818181818, 'profit_factor': 0.32880638228340114, 'avg_net_return': -0.05110021636363637, 'median_net_return': -0.08533561, 'net_profit': -105007.90743400001, 'initial_equity': 1000000.0, 'final_equity': 894992.0925660001, 'net_return': -0.1050079074339999, 'max_drawdown': 0.11635393170700001} |
| expectancy_r | -0.6268903333333333 |
| fixed_risk_portfolio | {'trades': 12, 'wins': 1, 'losses': 11, 'win_rate': 0.08333333333333333, 'avg_win_r': 4.456959, 'avg_loss_r': 1.0890584545454545, 'expectancy_r': -0.6268903333333333, 'profit_factor': 0.35263068802022907, 'avg_net_return': -0.052891871666666666, 'median_net_return': -0.080579415, 'net_profit': -76700.851417, 'initial_equity': 1000000.0, 'final_equity': 923299.148583, 'net_return': -0.076700851417, 'max_drawdown': 0.08673978173399996} |
| losses | 11 |
| median_net_return | -0.080579415 |
| net_profit | -2040.874432 |
| profit_factor | 0.11343393952470476 |
| trades | 12 |
| unfilled_rate | 0.6666666666666666 |
| win_rate | 0.08333333333333333 |
| wins | 1 |

## 旧双路径归因

| 实验 | 结果 |
| --- | --- |
| BOTH | `{"avg_loss_r": 1.013474, "avg_net_return": -0.07582322, "avg_win_r": 0.0, "expectancy_r": -1.013474, "losses": 1, "median_net_return": -0.07582322, "net_profit": -142.538403, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}` |
| BOX | `{"avg_loss_r": 1.1063664444444445, "avg_net_return": -0.045105786, "avg_win_r": 4.456959, "expectancy_r": -0.5500339, "losses": 9, "median_net_return": -0.07896784500000001, "net_profit": -1688.7375200000001, "profit_factor": 0.13391963013356625, "trades": 10, "win_rate": 0.1, "wins": 1}` |
| ORIGINAL | `{"avg_loss_r": 1.008871, "avg_net_return": -0.10782138, "avg_win_r": 0.0, "expectancy_r": -1.008871, "losses": 1, "median_net_return": -0.10782138, "net_profit": -209.598509, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}` |

## 权威三路径归因

| 实验 | 结果 |
| --- | --- |
| BOX | `{"avg_loss_r": 1.0970772, "avg_net_return": -0.04789828, "avg_win_r": 4.456959, "expectancy_r": -0.5921648181818182, "losses": 10, "median_net_return": -0.07582322, "net_profit": -1831.275923, "profit_factor": 0.12479676491420903, "trades": 11, "win_rate": 0.09090909090909091, "wins": 1}` |
| BROOKS | `{"avg_loss_r": 1.013474, "avg_net_return": -0.07582322, "avg_win_r": 0.0, "expectancy_r": -1.013474, "losses": 1, "median_net_return": -0.07582322, "net_profit": -142.538403, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}` |
| ORIGINAL | `{"avg_loss_r": 1.0111725, "avg_net_return": -0.0918223, "avg_win_r": 0.0, "expectancy_r": -1.0111725, "losses": 2, "median_net_return": -0.0918223, "net_profit": -352.136912, "profit_factor": 0.0, "trades": 2, "win_rate": 0.0, "wins": 0}` |

## 权威主路径与汇总

| 实验 | 结果 |
| --- | --- |
| primary | `{"BOX": {"avg_loss_r": 1.1063664444444445, "avg_net_return": -0.045105786, "avg_win_r": 4.456959, "expectancy_r": -0.5500339, "losses": 9, "median_net_return": -0.07896784500000001, "net_profit": -1688.7375200000001, "profit_factor": 0.13391963013356625, "trades": 10, "win_rate": 0.1, "wins": 1}, "ORIGINAL": {"avg_loss_r": 1.0111725, "avg_net_return": -0.0918223, "avg_win_r": 0.0, "expectancy_r": -1.0111725, "losses": 2, "median_net_return": -0.0918223, "net_profit": -352.136912, "profit_factor": 0.0, "trades": 2, "win_rate": 0.0, "wins": 0}}` |
| summary | `{"BOX": {"avg_loss_r": 1.1063664444444445, "avg_net_return": -0.045105786, "avg_win_r": 4.456959, "expectancy_r": -0.5500339, "losses": 9, "median_net_return": -0.07896784500000001, "net_profit": -1688.7375200000001, "profit_factor": 0.13391963013356625, "trades": 10, "win_rate": 0.1, "wins": 1}, "MULTI": {"avg_loss_r": 1.013474, "avg_net_return": -0.07582322, "avg_win_r": 0.0, "expectancy_r": -1.013474, "losses": 1, "median_net_return": -0.07582322, "net_profit": -142.538403, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}, "ORIGINAL": {"avg_loss_r": 1.008871, "avg_net_return": -0.10782138, "avg_win_r": 0.0, "expectancy_r": -1.008871, "losses": 1, "median_net_return": -0.10782138, "net_profit": -209.598509, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}}` |

## Brooks状态与结构

| 实验 | 结果 |
| --- | --- |
| status | `{"BROOKS_CONTEXT_REJECT": {"avg_loss_r": 1.1679916000000001, "avg_net_return": -0.072311142, "avg_win_r": 0.0, "expectancy_r": -1.1679916000000001, "losses": 5, "median_net_return": -0.07260008, "net_profit": -1362.2952520000001, "profit_factor": 0.0, "trades": 5, "win_rate": 0.0, "wins": 0}, "BROOKS_FAILED": {"avg_loss_r": 1.0252422, "avg_net_return": -0.092865726, "avg_win_r": 0.0, "expectancy_r": -1.0252422, "losses": 5, "median_net_return": -0.10664587, "net_profit": -797.165624, "profit_factor": 0.0, "trades": 5, "win_rate": 0.0, "wins": 0}, "BROOKS_FAILED_BREAKOUT_READY": {"avg_loss_r": 1.013474, "avg_net_return": -0.07582322, "avg_win_r": 0.0, "expectancy_r": -1.013474, "losses": 1, "median_net_return": -0.07582322, "net_profit": -142.538403, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}, "COMPACT_BEARISH_REJECT": {"avg_loss_r": 0.0, "avg_net_return": 0.2670051, "avg_win_r": 4.456959, "expectancy_r": 4.456959, "losses": 0, "median_net_return": 0.2670051, "net_profit": 261.124847, "profit_factor": Infinity, "trades": 1, "win_rate": 1.0, "wins": 1}}` |
| structure | `{"BEAR_FOLLOW_THROUGH_FAILED": {"avg_loss_r": 1.01298, "avg_net_return": -0.08244459, "avg_win_r": 0.0, "expectancy_r": -1.01298, "losses": 4, "median_net_return": -0.08217811, "net_profit": -583.823071, "profit_factor": 0.0, "trades": 4, "win_rate": 0.0, "wins": 0}, "FAILED_BEAR_BREAKOUT": {"avg_loss_r": 1.112522, "avg_net_return": -0.06676333500000001, "avg_win_r": 0.0, "expectancy_r": -1.112522, "losses": 2, "median_net_return": -0.06676333500000001, "net_profit": -695.890253, "profit_factor": 0.0, "trades": 2, "win_rate": 0.0, "wins": 0}, "MICRO_DOUBLE_BOTTOM": {"avg_loss_r": 1.112522, "avg_net_return": -0.06676333500000001, "avg_win_r": 0.0, "expectancy_r": -1.112522, "losses": 2, "median_net_return": -0.06676333500000001, "net_profit": -695.890253, "profit_factor": 0.0, "trades": 2, "win_rate": 0.0, "wins": 0}, "ORDERLY_COMPRESSION_AT_SUPPORT": {"avg_loss_r": 1.013474, "avg_net_return": -0.07582322, "avg_win_r": 0.0, "expectancy_r": -1.013474, "losses": 1, "median_net_return": -0.07582322, "net_profit": -142.538403, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}}` |

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

- 每日候选：`s6bt-46913bb97feee28bc538-daily-candidates.csv`
- 订单：`s6bt-46913bb97feee28bc538-orders.csv`
- 交易：`s6bt-46913bb97feee28bc538-trades.csv`
- 参数试验：`s6bt-46913bb97feee28bc538-parameter-trials.csv`

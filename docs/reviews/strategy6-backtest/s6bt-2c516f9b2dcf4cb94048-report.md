# 策略6双路径历史回测与参数调优报告

## 可信度

- 运行ID：`s6bt-2c516f9b2dcf4cb94048`
- 可信度：`RESEARCH_ONLY_CURRENT_UNIVERSE`
- OOS状态：`OOS_LOCKED`
- OOS起始：`2026-01-01`
- 幸存者偏差：存在
- 历史ST、退市和停牌状态不完整，结果仅用于研究，不构成生产参数升级依据。

## 汇总指标

| 指标 | 数值 |
| --- | ---: |
| avg_loss_r | 0.9648135833333333 |
| avg_net_return | -0.004772506875 |
| avg_win_r | 3.0160236666666664 |
| equal_weight_portfolio | {'trades': 41, 'wins': 12, 'losses': 29, 'win_rate': 0.2926829268292683, 'avg_win_r': 3.0160236666666664, 'avg_loss_r': 0.9461356896551724, 'expectancy_r': 0.21352070731707315, 'profit_factor': 1.0248086700678738, 'avg_net_return': 0.005359092926829269, 'median_net_return': -0.05585576, 'net_profit': 11322.396108, 'initial_equity': 1000000.0, 'final_equity': 1011322.3961079998, 'net_return': 0.011322396107999788, 'max_drawdown': 0.16637014556649837} |
| expectancy_r | 0.03039572916666666 |
| fixed_risk_portfolio | {'trades': 44, 'wins': 12, 'losses': 32, 'win_rate': 0.2727272727272727, 'avg_win_r': 3.0160236666666664, 'avg_loss_r': 0.9563228125, 'expectancy_r': 0.12704440909090908, 'profit_factor': 0.9382464567396961, 'avg_net_return': 0.00014491386363636426, 'median_net_return': -0.056384359999999994, 'net_profit': -21306.414575000003, 'initial_equity': 1000000.0, 'final_equity': 978693.585425, 'net_return': -0.021306414574999932, 'max_drawdown': 0.13948608896300818} |
| losses | 36 |
| median_net_return | -0.056384359999999994 |
| net_profit | -971.2231739999997 |
| profit_factor | 0.8915407854449473 |
| trades | 48 |
| unfilled_rate | 0.8321678321678322 |
| win_rate | 0.25 |
| wins | 12 |

## 实验对比

无实验结果。

## 明细文件

- 每日候选：`s6bt-2c516f9b2dcf4cb94048-daily-candidates.csv`
- 订单：`s6bt-2c516f9b2dcf4cb94048-orders.csv`
- 交易：`s6bt-2c516f9b2dcf4cb94048-trades.csv`
- 参数试验：`s6bt-2c516f9b2dcf4cb94048-parameter-trials.csv`

# 策略6历史回测与参数调优报告

## 可信度

- 运行ID：`s6bt-772c046cb6c982f61fc5`
- 可信度：`RESEARCH_ONLY_CURRENT_UNIVERSE`
- OOS状态：`OOS_LOCKED`
- OOS起始：`2026-01-01`
- 幸存者偏差：存在
- 历史ST、退市和停牌状态不完整，结果仅用于研究，不构成生产参数升级依据。

## 汇总指标

| 指标 | 数值 |
| --- | ---: |
| avg_loss_r | 1.0315334338624338 |
| avg_net_return | -0.022296216307053942 |
| avg_win_r | 2.710470346153846 |
| equal_weight_portfolio | {'trades': 100, 'wins': 28, 'losses': 72, 'win_rate': 0.28, 'avg_win_r': 2.796269142857143, 'avg_loss_r': 1.0350282361111112, 'expectancy_r': 0.03773503000000002, 'profit_factor': 0.8815048355933105, 'avg_net_return': -0.0039737088, 'median_net_return': -0.065157315, 'net_profit': -129593.63767800003, 'initial_equity': 1000000.0, 'final_equity': 870406.3623220002, 'net_return': -0.1295936376779998, 'max_drawdown': 0.28830183975055407} |
| expectancy_r | -0.2241301286307054 |
| fixed_risk_portfolio | {'trades': 124, 'wins': 28, 'losses': 96, 'win_rate': 0.22580645161290322, 'avg_win_r': 2.9815855714285715, 'avg_loss_r': 1.0254567083333332, 'expectancy_r': -0.12064070967741936, 'profit_factor': 0.6986466967181965, 'avg_net_return': -0.0126858175, 'median_net_return': -0.06742522000000001, 'net_profit': -280446.192659, 'initial_equity': 1000000.0, 'final_equity': 719553.8073410003, 'net_return': -0.2804461926589997, 'max_drawdown': 0.3032060233578811} |
| losses | 189 |
| median_net_return | -0.064767 |
| net_profit | -23653.908517 |
| profit_factor | 0.5767032948505815 |
| trades | 241 |
| unfilled_rate | 0.7231638418079096 |
| win_rate | 0.2157676348547718 |
| wins | 52 |

## 旧双路径归因

| 实验 | 结果 |
| --- | --- |
| BOTH | `{"avg_loss_r": 1.015867, "avg_net_return": -0.011065820731707319, "avg_win_r": 3.4231365, "expectancy_r": -0.14971997560975608, "losses": 33, "median_net_return": -0.06050471, "net_profit": 156.80766400000016, "profit_factor": 1.0226005595794259, "trades": 41, "win_rate": 0.1951219512195122, "wins": 8}` |
| BOX | `{"avg_loss_r": 1.0339585, "avg_net_return": -0.02152838860962567, "avg_win_r": 2.58879311627907, "expectancy_r": -0.20091935828877006, "losses": 144, "median_net_return": -0.064767, "net_profit": -19979.353422, "profit_factor": 0.5549310880259428, "trades": 187, "win_rate": 0.22994652406417113, "wins": 43}` |
| NONE | `{"avg_loss_r": 1.0142315, "avg_net_return": -0.023548656666666667, "avg_win_r": 2.241262, "expectancy_r": 0.07093299999999998, "losses": 2, "median_net_return": -0.06797336, "net_profit": -1203.7746439999999, "profit_factor": 0.15461054448836786, "trades": 3, "win_rate": 0.3333333333333333, "wins": 1}` |
| ORIGINAL | `{"avg_loss_r": 1.0517721, "avg_net_return": -0.082323484, "avg_win_r": 0.0, "expectancy_r": -1.0517721, "losses": 10, "median_net_return": -0.082152995, "net_profit": -2627.588115, "profit_factor": 0.0, "trades": 10, "win_rate": 0.0, "wins": 0}` |

## 权威三路径归因

| 实验 | 结果 |
| --- | --- |
| BOX | `{"avg_loss_r": 1.0305855084745763, "avg_net_return": -0.019646961929824562, "avg_win_r": 2.7196705098039216, "expectancy_r": -0.19171245175438595, "losses": 177, "median_net_return": -0.06376031, "net_profit": -19822.545758, "profit_factor": 0.6175372187535323, "trades": 228, "win_rate": 0.2236842105263158, "wins": 51}` |
| BROOKS | `{"avg_loss_r": 1.069201925925926, "avg_net_return": -0.003243258536585366, "avg_win_r": 2.7313365714285713, "expectancy_r": 0.2285429268292683, "losses": 27, "median_net_return": -0.05858246, "net_profit": -6824.91181, "profit_factor": 0.4619673953510557, "trades": 41, "win_rate": 0.34146341463414637, "wins": 14}` |
| ORIGINAL | `{"avg_loss_r": 1.0242170232558139, "avg_net_return": -0.02503791156862745, "avg_win_r": 3.4231365, "expectancy_r": -0.3265929411764706, "losses": 43, "median_net_return": -0.06355762, "net_profit": -2470.7804509999996, "profit_factor": 0.7417070975546441, "trades": 51, "win_rate": 0.1568627450980392, "wins": 8}` |

## 权威主路径与汇总

| 实验 | 结果 |
| --- | --- |
| primary | `{"BOX": {"avg_loss_r": 1.0307908604651164, "avg_net_return": -0.024988199444444446, "avg_win_r": 2.597272424242424, "expectancy_r": -0.29174093209876545, "losses": 129, "median_net_return": -0.065523955, "net_profit": -14474.714173, "profit_factor": 0.6030652689207183, "trades": 162, "win_rate": 0.2037037037037037, "wins": 33}, "BROOKS": {"avg_loss_r": 1.0556744705882353, "avg_net_return": -0.00172736892857143, "avg_win_r": 2.5317614545454545, "expectancy_r": 0.35367535714285714, "losses": 17, "median_net_return": -0.059038900000000005, "net_profit": -6708.413893, "profit_factor": 0.3188160861421144, "trades": 28, "win_rate": 0.39285714285714285, "wins": 11}, "ORIGINAL": {"avg_loss_r": 1.0242170232558139, "avg_net_return": -0.02503791156862745, "avg_win_r": 3.4231365, "expectancy_r": -0.3265929411764706, "losses": 43, "median_net_return": -0.06355762, "net_profit": -2470.7804509999996, "profit_factor": 0.7417070975546441, "trades": 51, "win_rate": 0.1568627450980392, "wins": 8}}` |
| summary | `{"BOX": {"avg_loss_r": 1.0307908604651164, "avg_net_return": -0.024988199444444446, "avg_win_r": 2.597272424242424, "expectancy_r": -0.29174093209876545, "losses": 129, "median_net_return": -0.065523955, "net_profit": -14474.714173, "profit_factor": 0.6030652689207183, "trades": 162, "win_rate": 0.2037037037037037, "wins": 33}, "BROOKS": {"avg_loss_r": 1.0142315, "avg_net_return": -0.023548656666666667, "avg_win_r": 2.241262, "expectancy_r": 0.07093299999999998, "losses": 2, "median_net_return": -0.06797336, "net_profit": -1203.7746439999999, "profit_factor": 0.15461054448836786, "trades": 3, "win_rate": 0.3333333333333333, "wins": 1}, "MULTI": {"avg_loss_r": 1.0321492244897958, "avg_net_return": -0.007337378507462688, "avg_win_r": 2.944067, "expectancy_r": 0.036087970149253745, "losses": 49, "median_net_return": -0.05915639, "net_profit": -6120.4384039999995, "profit_factor": 0.6206747341991439, "trades": 67, "win_rate": 0.26865671641791045, "wins": 18}, "ORIGINAL": {"avg_loss_r": 1.0426692222222222, "avg_net_return": -0.08478327666666666, "avg_win_r": 0.0, "expectancy_r": -1.0426692222222222, "losses": 9, "median_net_return": -0.08942529, "net_profit": -1854.981296, "profit_factor": 0.0, "trades": 9, "win_rate": 0.0, "wins": 0}}` |

## Brooks状态与结构

| 实验 | 结果 |
| --- | --- |
| status | `{"BARB_WIRE_WAIT": {"avg_loss_r": 1.069369, "avg_net_return": -0.05858246, "avg_win_r": 0.0, "expectancy_r": -1.069369, "losses": 1, "median_net_return": -0.05858246, "net_profit": -677.128117, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}, "BROOKS_CONTEXT_REJECT": {"avg_loss_r": 1.037101275, "avg_net_return": -0.018806580792079208, "avg_win_r": 2.8559776666666665, "expectancy_r": -0.22764921782178216, "losses": 80, "median_net_return": -0.06604643, "net_profit": -7672.419363999999, "profit_factor": 0.6405007048638653, "trades": 101, "win_rate": 0.2079207920792079, "wins": 21}, "BROOKS_FAILED": {"avg_loss_r": 0.9935981777777778, "avg_net_return": -0.036092629811320755, "avg_win_r": 2.19542025, "expectancy_r": -0.5122369056603774, "losses": 45, "median_net_return": -0.06363227, "net_profit": -817.0415169999995, "profit_factor": 0.9222369197096176, "trades": 53, "win_rate": 0.1509433962264151, "wins": 8}, "BROOKS_FAILED_BREAKOUT_READY": {"avg_loss_r": 1.0814986666666666, "avg_net_return": 0.006229947, "avg_win_r": 2.414045, "expectancy_r": 0.31671879999999997, "losses": 12, "median_net_return": -0.053188635, "net_profit": -197.37801499999986, "profit_factor": 0.9511720882081569, "trades": 20, "win_rate": 0.4, "wins": 8}, "BROOKS_SUPPORT_READY": {"avg_loss_r": 1.0185686, "avg_net_return": -0.077753762, "avg_win_r": 0.0, "expectancy_r": -1.0185686, "losses": 5, "median_net_return": -0.07622901, "net_profit": -1867.235902, "profit_factor": 0.0, "trades": 5, "win_rate": 0.0, "wins": 0}, "COMPACT_BEARISH_REJECT": {"avg_loss_r": 1.0159548333333333, "avg_net_return": 0.0022878670000000016, "avg_win_r": 2.35266925, "expectancy_r": 0.33149480000000003, "losses": 6, "median_net_return": -0.056155815, "net_profit": -945.561466, "profit_factor": 0.34664005616272153, "trades": 10, "win_rate": 0.4, "wins": 4}, "FAILED_BEAR_BREAKOUT": {"avg_loss_r": 1.0548829166666667, "avg_net_return": -0.033491064318181815, "avg_win_r": 3.1501782499999997, "expectancy_r": -0.29032634090909093, "losses": 36, "median_net_return": -0.06906915, "net_profit": -11500.758595000001, "profit_factor": 0.2538706246216579, "trades": 44, "win_rate": 0.18181818181818182, "wins": 8}, "ORDERLY_COMPRESSION_AT_SUPPORT": {"avg_loss_r": 1.018373, "avg_net_return": 0.08771888, "avg_win_r": 4.043981, "expectancy_r": 1.5128039999999998, "losses": 1, "median_net_return": 0.08771888, "net_profit": 183.47748199999995, "profit_factor": 3.257392070067025, "trades": 2, "win_rate": 0.5, "wins": 1}, "SECOND_ENTRY_LONG_READY": {"avg_loss_r": 1.016572, "avg_net_return": 0.007405728000000002, "avg_win_r": 2.7185605, "expectancy_r": 0.4774810000000001, "losses": 3, "median_net_return": -0.04236232, "net_profit": -159.863023, "profit_factor": 0.6817764541092882, "trades": 5, "win_rate": 0.4, "wins": 2}}` |
| structure | `{"BEAR_FOLLOW_THROUGH_FAILED": {"avg_loss_r": 1.0046968378378378, "avg_net_return": -0.038673128095238096, "avg_win_r": 2.8302009999999997, "expectancy_r": -0.548161380952381, "losses": 37, "median_net_return": -0.07767619, "net_profit": 1115.7345450000005, "profit_factor": 1.132905189426849, "trades": 42, "win_rate": 0.11904761904761904, "wins": 5}, "FAILED_BEAR_BREAKOUT": {"avg_loss_r": 1.0476445670103092, "avg_net_return": -0.021636854516129032, "avg_win_r": 2.9075515185185186, "expectancy_r": -0.18643251612903225, "losses": 97, "median_net_return": -0.06695441499999999, "net_profit": -21556.741429, "profit_factor": 0.3846478328121717, "trades": 124, "win_rate": 0.21774193548387097, "wins": 27}, "MICRO_DOUBLE_BOTTOM": {"avg_loss_r": 1.0373046379310344, "avg_net_return": -0.020189713066666667, "avg_win_r": 2.9996006470588235, "expectancy_r": -0.12227277333333333, "losses": 58, "median_net_return": -0.06881444, "net_profit": -9454.308001, "profit_factor": 0.491783813811888, "trades": 75, "win_rate": 0.22666666666666666, "wins": 17}, "ORDERLY_COMPRESSION_AT_SUPPORT": {"avg_loss_r": 1.0379729473684212, "avg_net_return": 0.014278418387096774, "avg_win_r": 2.933467, "expectancy_r": 0.4993586451612903, "losses": 19, "median_net_return": -0.05267241, "net_profit": -482.8776880000001, "profit_factor": 0.9218171319785938, "trades": 31, "win_rate": 0.3870967741935484, "wins": 12}, "SECOND_ENTRY_LONG_READY": {"avg_loss_r": 0.9688641428571428, "avg_net_return": -0.028307061666666668, "avg_win_r": 2.42984825, "expectancy_r": -0.2135947222222222, "losses": 14, "median_net_return": -0.05669822, "net_profit": -3720.976225, "profit_factor": 0.2625126680808039, "trades": 18, "win_rate": 0.2222222222222222, "wins": 4}}` |

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

- 每日候选：`s6bt-772c046cb6c982f61fc5-daily-candidates.csv`
- 订单：`s6bt-772c046cb6c982f61fc5-orders.csv`
- 交易：`s6bt-772c046cb6c982f61fc5-trades.csv`
- 参数试验：`s6bt-772c046cb6c982f61fc5-parameter-trials.csv`

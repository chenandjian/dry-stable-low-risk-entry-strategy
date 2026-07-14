# 策略6历史回测与参数调优报告

## 可信度

- 运行ID：`s6bt-90385365c8ffef4d972c`
- 可信度：`RESEARCH_ONLY_CURRENT_UNIVERSE`
- OOS状态：`OOS_LOCKED`
- OOS起始：`2026-01-01`
- 幸存者偏差：存在
- 历史ST、退市和停牌状态不完整，结果仅用于研究，不构成生产参数升级依据。

## 汇总指标

| 指标 | 数值 |
| --- | ---: |
| avg_loss_r | 1.0638654069767441 |
| avg_net_return | -0.01858141119266055 |
| avg_win_r | 3.7814420869565217 |
| equal_weight_portfolio | {'trades': 73, 'wins': 16, 'losses': 57, 'win_rate': 0.2191780821917808, 'avg_win_r': 3.682287125, 'avg_loss_r': 1.0460796842105262, 'expectancy_r': -0.009725315068493157, 'profit_factor': 0.6678707319825823, 'avg_net_return': -0.015578456438356165, 'median_net_return': -0.05502714, 'net_profit': -221907.892196, 'initial_equity': 1000000.0, 'final_equity': 778092.107804, 'net_return': -0.22190789219599993, 'max_drawdown': 0.24004342489200003} |
| expectancy_r | -0.041461073394495424 |
| fixed_risk_portfolio | {'trades': 79, 'wins': 17, 'losses': 62, 'win_rate': 0.21518987341772153, 'avg_win_r': 3.6918711176470587, 'avg_loss_r': 1.0439816774193549, 'expectancy_r': -0.02487411392405064, 'profit_factor': 0.7277808256930242, 'avg_net_return': -0.01589400835443038, 'median_net_return': -0.05800059, 'net_profit': -160353.204571, 'initial_equity': 1000000.0, 'final_equity': 839646.795429, 'net_return': -0.160353204571, 'max_drawdown': 0.21012355898399976} |
| losses | 86 |
| median_net_return | -0.05858246 |
| net_profit | -8455.639172 |
| profit_factor | 0.6836032761571399 |
| trades | 109 |
| unfilled_rate | 0.3888888888888889 |
| win_rate | 0.21100917431192662 |
| wins | 23 |

## 旧双路径归因

| 实验 | 结果 |
| --- | --- |
| BOTH | `{"avg_loss_r": 1.062634984375, "avg_net_return": -0.006453122, "avg_win_r": 4.014750285714285, "expectancy_r": 0.19177784705882353, "losses": 64, "median_net_return": -0.05378331, "net_profit": -2645.747847, "profit_factor": 0.8721561832240975, "trades": 85, "win_rate": 0.24705882352941178, "wins": 21}` |
| BOX | `{"avg_loss_r": 1.0553107142857143, "avg_net_return": -0.08377607857142857, "avg_win_r": 0.0, "expectancy_r": -1.0553107142857143, "losses": 7, "median_net_return": -0.08949402, "net_profit": -2161.949961, "profit_factor": 0.0, "trades": 7, "win_rate": 0.0, "wins": 0}` |
| ORIGINAL | `{"avg_loss_r": 1.0731074, "avg_net_return": -0.052377994117647056, "avg_win_r": 1.331706, "expectancy_r": -0.7901881764705883, "losses": 15, "median_net_return": -0.06981187, "net_profit": -3647.941364, "profit_factor": 0.056817277370787414, "trades": 17, "win_rate": 0.11764705882352941, "wins": 2}` |

## 权威三路径归因

| 实验 | 结果 |
| --- | --- |
| BOX | `{"avg_loss_r": 1.0619128732394367, "avg_net_return": -0.012336390434782608, "avg_win_r": 4.014750285714285, "expectancy_r": 0.09689067391304347, "losses": 71, "median_net_return": -0.057584300000000005, "net_profit": -4807.697808, "profit_factor": 0.7896628896637479, "trades": 92, "win_rate": 0.22826086956521738, "wins": 21}` |
| BROOKS | `{"avg_loss_r": 1.0224743043478262, "avg_net_return": -0.018335567, "avg_win_r": 4.500406571428572, "expectancy_r": 0.26619790000000004, "losses": 23, "median_net_return": -0.054967485, "net_profit": -4582.16467, "profit_factor": 0.3689169770037435, "trades": 30, "win_rate": 0.23333333333333334, "wins": 7}` |
| ORIGINAL | `{"avg_loss_r": 1.064623417721519, "avg_net_return": -0.014107267352941176, "avg_win_r": 3.7814420869565217, "expectancy_r": 0.028116843137254894, "losses": 79, "median_net_return": -0.057584300000000005, "net_profit": -6293.689211, "profit_factor": 0.7437720298895966, "trades": 102, "win_rate": 0.22549019607843138, "wins": 23}` |

## 权威主路径与汇总

| 实验 | 结果 |
| --- | --- |
| primary | `{"BOX": {"avg_loss_r": 1.0553107142857143, "avg_net_return": -0.08377607857142857, "avg_win_r": 0.0, "expectancy_r": -1.0553107142857143, "losses": 7, "median_net_return": -0.08949402, "net_profit": -2161.949961, "profit_factor": 0.0, "trades": 7, "win_rate": 0.0, "wins": 0}, "BROOKS": {"avg_loss_r": 2.118414, "avg_net_return": -0.10897518, "avg_win_r": 0.0, "expectancy_r": -2.118414, "losses": 1, "median_net_return": -0.10897518, "net_profit": -1952.606378, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}, "ORIGINAL": {"avg_loss_r": 1.051113282051282, "avg_net_return": -0.013167981089108912, "avg_win_r": 3.7814420869565217, "expectancy_r": 0.049369623762376226, "losses": 78, "median_net_return": -0.05747764, "net_profit": -4341.082833, "profit_factor": 0.8080037130932856, "trades": 101, "win_rate": 0.22772277227722773, "wins": 23}}` |
| summary | `{"BOX": {"avg_loss_r": 1.0553107142857143, "avg_net_return": -0.08377607857142857, "avg_win_r": 0.0, "expectancy_r": -1.0553107142857143, "losses": 7, "median_net_return": -0.08949402, "net_profit": -2161.949961, "profit_factor": 0.0, "trades": 7, "win_rate": 0.0, "wins": 0}, "MULTI": {"avg_loss_r": 1.0618662615384615, "avg_net_return": -0.007403213139534884, "avg_win_r": 4.014750285714285, "expectancy_r": 0.17777266279069767, "losses": 65, "median_net_return": -0.054405225, "net_profit": -2710.619776, "profit_factor": 0.8694308279532384, "trades": 86, "win_rate": 0.2441860465116279, "wins": 21}, "ORIGINAL": {"avg_loss_r": 1.0774245, "avg_net_return": -0.050141558749999995, "avg_win_r": 1.331706, "expectancy_r": -0.7762831875, "losses": 14, "median_net_return": -0.06614903, "net_profit": -3583.069435, "profit_factor": 0.05778651735359119, "trades": 16, "win_rate": 0.125, "wins": 2}}` |

## Brooks状态与结构

| 实验 | 结果 |
| --- | --- |
| status | `{"BARB_WIRE_WAIT": {"avg_loss_r": 1.069369, "avg_net_return": -0.05858246, "avg_win_r": 0.0, "expectancy_r": -1.069369, "losses": 1, "median_net_return": -0.05858246, "net_profit": -677.128117, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}, "BROOKS_CONTEXT_REJECT": {"avg_loss_r": 1.0039904, "avg_net_return": 0.0077639226923076924, "avg_win_r": 4.097943166666666, "expectancy_r": 0.1733788846153846, "losses": 20, "median_net_return": -0.05435613, "net_profit": -1029.3479660000003, "profit_factor": 0.8220778979593801, "trades": 26, "win_rate": 0.23076923076923078, "wins": 6}, "BROOKS_FAILED": {"avg_loss_r": 1.0498284210526316, "avg_net_return": -0.023251528333333334, "avg_win_r": 3.5105396, "expectancy_r": -0.09975175, "losses": 19, "median_net_return": -0.06978922, "net_profit": -1739.807421, "profit_factor": 0.6602015366245568, "trades": 24, "win_rate": 0.20833333333333334, "wins": 5}, "BROOKS_FAILED_BREAKOUT_READY": {"avg_loss_r": 1.0561106, "avg_net_return": 0.015719595714285717, "avg_win_r": 6.121786, "expectancy_r": 0.9947170000000001, "losses": 5, "median_net_return": -0.03804944, "net_profit": -311.81766400000004, "profit_factor": 0.8375060428642114, "trades": 7, "win_rate": 0.2857142857142857, "wins": 2}, "BROOKS_SUPPORT_READY": {"avg_loss_r": 1.1557125, "avg_net_return": -0.054603288, "avg_win_r": 1.515196, "expectancy_r": -0.6215308, "losses": 4, "median_net_return": -0.07411043, "net_profit": -2222.55241, "profit_factor": 0.06247418332025056, "trades": 5, "win_rate": 0.2, "wins": 1}, "COMPACT_BEARISH_REJECT": {"avg_loss_r": 1.025505, "avg_net_return": -0.042501, "avg_win_r": 0.0, "expectancy_r": -1.025505, "losses": 1, "median_net_return": -0.042501, "net_profit": -128.43883, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}, "FAILED_BEAR_BREAKOUT": {"avg_loss_r": 1.1040446060606062, "avg_net_return": -0.039157938461538463, "avg_win_r": 3.346401666666667, "expectancy_r": -0.4193605641025641, "losses": 33, "median_net_return": -0.05769096, "net_profit": -2356.103874, "profit_factor": 0.7638107478170034, "trades": 39, "win_rate": 0.15384615384615385, "wins": 6}, "MICRO_DOUBLE_BOTTOM": {"avg_loss_r": 1.0098965, "avg_net_return": -0.11094605999999999, "avg_win_r": 0.0, "expectancy_r": -1.0098965, "losses": 2, "median_net_return": -0.11094605999999999, "net_profit": -208.375092, "profit_factor": 0.0, "trades": 2, "win_rate": 0.0, "wins": 0}, "SECOND_ENTRY_LONG_READY": {"avg_loss_r": 1.014335, "avg_net_return": 0.08597883, "avg_win_r": 3.665211, "expectancy_r": 2.4953245, "losses": 1, "median_net_return": 0.10973907, "net_profit": 217.93220200000005, "profit_factor": 1.4033849006040997, "trades": 4, "win_rate": 0.75, "wins": 3}}` |
| structure | `{"BEAR_FOLLOW_THROUGH_FAILED": {"avg_loss_r": 1.0020337391304348, "avg_net_return": -0.031086486296296297, "avg_win_r": 3.365394, "expectancy_r": -0.35500740740740744, "losses": 23, "median_net_return": -0.06579904, "net_profit": -289.9779929999999, "profit_factor": 0.9598084274158739, "trades": 27, "win_rate": 0.14814814814814814, "wins": 4}, "FAILED_BEAR_BREAKOUT": {"avg_loss_r": 1.0731803275862069, "avg_net_return": -0.011610228666666667, "avg_win_r": 3.781222294117647, "expectancy_r": 0.027150933333333318, "losses": 58, "median_net_return": -0.05266383, "net_profit": -4139.712671, "profit_factor": 0.7802964534357273, "trades": 75, "win_rate": 0.22666666666666666, "wins": 17}, "MICRO_DOUBLE_BOTTOM": {"avg_loss_r": 1.06293325, "avg_net_return": -0.013472795714285715, "avg_win_r": 3.9022415, "expectancy_r": 0.1192512142857143, "losses": 32, "median_net_return": -0.058787175, "net_profit": -1445.9644099999998, "profit_factor": 0.8497605347734117, "trades": 42, "win_rate": 0.23809523809523808, "wins": 10}, "ORDERLY_COMPRESSION_AT_SUPPORT": {"avg_loss_r": 0.9073868571428572, "avg_net_return": -0.033856163333333335, "avg_win_r": 5.1170275, "expectancy_r": 0.4313718888888889, "losses": 7, "median_net_return": -0.07477612, "net_profit": 332.29567, "profit_factor": 1.526202265754185, "trades": 9, "win_rate": 0.2222222222222222, "wins": 2}, "SECOND_ENTRY_LONG_READY": {"avg_loss_r": 1.0710878181818182, "avg_net_return": -0.005339484375, "avg_win_r": 3.530104, "expectancy_r": 0.366784625, "losses": 11, "median_net_return": -0.042092649999999995, "net_profit": -3253.348842, "profit_factor": 0.25140570020448594, "trades": 16, "win_rate": 0.3125, "wins": 5}}` |

## 入场类型与质量归因

| 实验 | 结果 |
| --- | --- |
| entry_archetype | `{"FAILED_BREAKOUT_RECLAIM": {"avg_loss_r": 1.0561106, "avg_net_return": 0.015719595714285717, "avg_win_r": 6.121786, "expectancy_r": 0.9947170000000001, "losses": 5, "median_net_return": -0.03804944, "net_profit": -311.81766400000004, "profit_factor": 0.8375060428642114, "trades": 7, "win_rate": 0.2857142857142857, "wins": 2}, "SUPPORT_PULLBACK": {"avg_loss_r": 1.064344098765432, "avg_net_return": -0.020935401862745097, "avg_win_r": 3.5585521904761905, "expectancy_r": -0.11257133333333334, "losses": 81, "median_net_return": -0.05918292, "net_profit": -8143.821508, "profit_factor": 0.6716975524455919, "trades": 102, "win_rate": 0.20588235294117646, "wins": 21}}` |
| path_evidence | `{"00-04": {"avg_loss_r": 1.0553107142857143, "avg_net_return": -0.08377607857142857, "avg_win_r": 0.0, "expectancy_r": -1.0553107142857143, "losses": 7, "median_net_return": -0.08949402, "net_profit": -2161.949961, "profit_factor": 0.0, "trades": 7, "win_rate": 0.0, "wins": 0}, "10-14": {"avg_loss_r": 1.0731074, "avg_net_return": -0.052377994117647056, "avg_win_r": 1.331706, "expectancy_r": -0.7901881764705883, "losses": 15, "median_net_return": -0.06981187, "net_profit": -3647.941364, "profit_factor": 0.056817277370787414, "trades": 17, "win_rate": 0.11764705882352941, "wins": 2}, "15-19": {"avg_loss_r": 1.062634984375, "avg_net_return": -0.006453122, "avg_win_r": 4.014750285714285, "expectancy_r": 0.19177784705882353, "losses": 64, "median_net_return": -0.05378331, "net_profit": -2645.747847, "profit_factor": 0.8721561832240975, "trades": 85, "win_rate": 0.24705882352941178, "wins": 21}}` |
| setup_quality | `{"05-09": {"avg_loss_r": 1.020503, "avg_net_return": -0.05324495, "avg_win_r": 0.0, "expectancy_r": -1.020503, "losses": 1, "median_net_return": -0.05324495, "net_profit": -100.626992, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}, "10-14": {"avg_loss_r": 1.07178965, "avg_net_return": -0.014620550576923078, "avg_win_r": 4.12129775, "expectancy_r": 0.12661513461538462, "losses": 40, "median_net_return": -0.05322357, "net_profit": -2307.466717, "profit_factor": 0.831660752725, "trades": 52, "win_rate": 0.23076923076923078, "wins": 12}, "15-19": {"avg_loss_r": 1.0577852444444444, "avg_net_return": -0.02164036142857143, "avg_win_r": 3.4106904545454544, "expectancy_r": -0.18004894642857144, "losses": 45, "median_net_return": -0.061501235, "net_profit": -6047.5454629999995, "profit_factor": 0.5318125321563164, "trades": 56, "win_rate": 0.19642857142857142, "wins": 11}}` |
| start_quality | `{"00-04": {"avg_loss_r": 1.0372873333333335, "avg_net_return": 0.0070515675, "avg_win_r": 3.936857, "expectancy_r": 0.20624874999999993, "losses": 3, "median_net_return": -0.047915349999999995, "net_profit": -1391.230656, "profit_factor": 0.291365218895891, "trades": 4, "win_rate": 0.25, "wins": 1}, "05-09": {"avg_loss_r": 1.011389, "avg_net_return": -0.08942529, "avg_win_r": 0.0, "expectancy_r": -1.011389, "losses": 1, "median_net_return": -0.08942529, "net_profit": -122.277101, "profit_factor": 0.0, "trades": 1, "win_rate": 0.0, "wins": 0}, "10-14": {"avg_loss_r": 1.063467, "avg_net_return": -0.0584072675, "avg_win_r": 0.0, "expectancy_r": -1.063467, "losses": 4, "median_net_return": -0.051580724999999994, "net_profit": -1621.4606840000001, "profit_factor": 0.0, "trades": 4, "win_rate": 0.0, "wins": 0}, "15-19": {"avg_loss_r": 1.0280407, "avg_net_return": -0.02782080244897959, "avg_win_r": 3.163832, "expectancy_r": -0.2581048979591837, "losses": 40, "median_net_return": -0.06051628, "net_profit": -3653.537109, "profit_factor": 0.6984839207033962, "trades": 49, "win_rate": 0.1836734693877551, "wins": 9}, "20-24": {"avg_loss_r": 1.1050967894736843, "avg_net_return": -0.007202086470588236, "avg_win_r": 4.197063307692307, "expectancy_r": 0.2464342156862745, "losses": 38, "median_net_return": -0.05899189, "net_profit": -1667.133622, "profit_factor": 0.8470601826975789, "trades": 51, "win_rate": 0.2549019607843137, "wins": 13}}` |
| support_reaction | `{"05-09": {"avg_loss_r": 1.0587965128205128, "avg_net_return": -0.019766091020408164, "avg_win_r": 4.0068759, "expectancy_r": -0.024985816326530626, "losses": 39, "median_net_return": -0.05324495, "net_profit": -2212.89052, "profit_factor": 0.7604458170486305, "trades": 49, "win_rate": 0.20408163265306123, "wins": 10}, "10-14": {"avg_loss_r": 1.0680715106382979, "avg_net_return": -0.017613922666666667, "avg_win_r": 3.6080314615384617, "expectancy_r": -0.054915866666666674, "losses": 47, "median_net_return": -0.060106145, "net_profit": -6242.748652, "profit_factor": 0.6430116889768547, "trades": 60, "win_rate": 0.21666666666666667, "wins": 13}}` |

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

- 每日候选：`s6bt-90385365c8ffef4d972c-daily-candidates.csv`
- 订单：`s6bt-90385365c8ffef4d972c-orders.csv`
- 交易：`s6bt-90385365c8ffef4d972c-trades.csv`
- 参数试验：`s6bt-90385365c8ffef4d972c-parameter-trials.csv`

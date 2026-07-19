# 策略6 V4 真实数据验证报告

## 验证范围

- 数据库：`data/cuphandle.db`
- 个股日线：3,895,072 根，5,016 只股票，日期覆盖 2023-01-03 至 2026-07-09
- 满足至少500根日线的股票：4,843 只
- 价格口径：前复权
- 验证方式：只读本地数据库，逐股调用 `StrongVcpTailEngine.evaluate_at()`；分别验证默认市场过滤和关闭市场过滤的纯个股结构口径
- 未执行：回测、参数寻优、未复权成交模拟

## 全量结果

| 项目 | 数量 |
| --- | ---: |
| READY_CANDIDATE | 0 |
| KEY_CANDIDATE | 0 |
| WATCH_CANDIDATE | 61 |
| REJECTED | 4,782 |

61 个观察项全部处于 `START_TOO_RECENT / START_CONFIRMED`，属于刚启动的生命周期跟踪项，不是成熟交易计划；其形态、支撑和客观盈亏比尚未形成。

## 阶段与形态漏斗

| 阶段 | 数量 |
| --- | ---: |
| START_TOO_RECENT | 2,329 |
| PHASE_VALID | 1,584 |
| CONSOLIDATION_TOO_SHORT | 546 |
| CONSOLIDATION_TOO_LONG | 384 |

| 形态 | 数量 |
| --- | ---: |
| VCP | 177 |
| CUP_HANDLE | 22 |
| PLATFORM | 29 |
| UNKNOWN | 4,615 |

真实数据中共识别出228个明确形态。VCP 按尾段之前的整理主体识别连续局部峰谷，要求至少两轮振幅和成交量递减，不允许跳过中间失败收缩，并要求信号价不明显低于最后收缩上沿。相较审查前偏宽的808个 VCP，严格规则收敛为177个；这只影响形态标签和形态分，未绕过趋势、流动性、阶段、支撑、尾段和客观盈亏比硬条件。明确形态最终没有进入成熟候选。

## 主要首个淘汰原因

| 原因 | 数量 |
| --- | ---: |
| CLOSE_LE_MA250 | 2,945 |
| CONSOLIDATION_TOO_SHORT | 546 |
| CONSOLIDATION_TOO_LONG | 384 |
| AVG60D_LT_MIN | 245 |
| AVG30D_LT_MIN | 110 |
| AVG10D_LT_AVG30D_RATIO | 95 |
| NO_NEW_HIGH_CONFIRMATION | 85 |
| MA120_LE_MA250 | 56 |
| NO_STRONG_START | 51 |
| CLOSE_LT_KEY_SUPPORT_0_96 | 47 |
| CONSOLIDATION_RANGE_5_GT_A_LIMIT | 43 |
| TAIL_NEW_LOW | 36 |
| BREAKOUT_EXTENDED | 13 |

## 生命周期观察

| 状态 | 数量 |
| --- | ---: |
| START_CONFIRMED | 2,329 |
| FAILED | 2,114 |
| EXTENDED | 361 |
| SETUP_FORMING | 29 |
| BUY_ZONE | 7 |
| BREAKOUT_CONFIRMED | 2 |
| READY | 1 |

生命周期状态用于解释股票当前所处位置，不等同于最终候选。`BUY_ZONE`、`READY` 或 `BREAKOUT_CONFIRMED` 仍可能因长期趋势、流动性、结构失败或客观盈亏比不合格而被硬性排除。

## 市场数据边界

本地 `market_index_ohlc` 最新日期为 2026-07-02，早于个股最新日期 2026-07-09，因此本报告没有用该缓存冒充同步市场环境。默认市场过滤与关闭市场过滤两种口径均为 61 个 WATCH、0 个 KEY/READY；这 61 个入选项全部属于 `START_TOO_RECENT / START_CONFIRMED`，形态尚未进入正式识别阶段，成熟候选本身为 0。正式扫描仍会在线拉取上证、深证、创业板和沪深300；至少两个宽基指数必须覆盖股票评估日才形成市场状态，RS20只接受同日沪深300，不再回退上证指数。沪深300缺失时，即使其他宽基完整也只允许 WATCH。任务结果页展示 `新鲜/过期/缺失`、指数日期、来源和抓取时间供核验。

## 结论

V4 在 4,843 只合格股票上完成全量执行，零评估异常，阶段、形态和淘汰漏斗均可解释。当前参数下没有成熟 KEY/READY，不应在本开发任务中为了数量临时放宽阈值；形态识别准确率和参数效果仍需在独立回测、人工抽样及样本外验证任务中评估。

最终自动门禁：后端常规回归 946 项通过，前端 73 项通过，Python 编译和前端生产构建通过。真实外部行情网络测试、回测、参数寻优和未复权成交模拟不属于本次范围。

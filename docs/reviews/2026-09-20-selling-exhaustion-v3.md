# 卖压衰竭 V3：重新观察与近期承接改善验收

## 范围与边界
仅修改批量评分独立 sellingExhaustion 诊断；不修改策略6正式资格、总分、排序、候选或生命周期，不修改策略1-5、生产配置和行情数据。本次没有收益调优或交易回测，以下是按历史日期截断的信号重放。

## 规则
1. 保留原回调背景、四因子评分和原有“新回调 / 两个收跌日回踩”恢复路径。
2. 增加重新观察路径：反弹退出后至少经过两个交易数据日，最近两根收盘位置均达到普通阈值，当前全部原始确认条件通过；且距离原底部不超过1 ATR、三日和单日净上涨均不超过0.5 ATR。不是隔两天自动恢复，也不免除最近5日至少2个收跌样本。
3. 恢复时补记反弹期间真实最低价及发生日，再次检查离底距离，禁止遗漏低价导致支撑抬高。例600673的9月11日低价30.03必须保留，不能误记成9月14日30.47。
4. 五日平均收盘位置仍为首选。若不足，允许近期持续改善获得普通确认：近3日平均位置至少0.55且不低于普通阈值；比紧邻前2日平均提高至少0.10；最近两天各自均不低于普通阈值0.45。只补普通确认，不提高原始分、不直接授予强/极致确认。
5. 量比、跌幅比、低点变化、当前3日破位保护和反弹阈值不放宽。单根漂亮K线、最新弱收盘不能走改善路径。新配置 close_recent_mean_min=0.55、close_improvement_min=0.10 位于模块DEFAULTS，可在原诊断配置节覆盖；不新增复杂前端筛选项。
6. 详情新增承接路径、近3日/前2日收盘位置和改善幅度，旧字段全部保留，模型版本V3。

## 真实数据与复现
- 基线：a2da9fb 中的V2原文件，运行时 git show 读取冻结实现。
- 数据库：worktree/data/cuphandle.db，只读SQLite；个股前复权日线，不联网，不生成假数据。
- 区间：2026-08-24 至 2026-09-18，仅有真实当日K线才评估。
- 当前库股票数 5024；代码排序后等距抽样200只。**不是全市场统计，也不是200只全部都有完整日期**。
- 对比 3989 个股票日期。额外检查600673、000811等指定股票；未在抽样中的股票不混入200只样本统计。
- 输入OHLCV指纹（含额外指定股）：1b586996653595e8412f7c6658b0b81a304c1171fbf8085817472b667c3fe437
- 复现：`python scripts/compare_selling_exhaustion_v3.py`，输出JSON含样本名单、统计、全部命中/移除和指定股明细。本机耗时 56.83 秒；数据库更新后结果及指纹可能变化。

## 对比结论
| 指标 | 结果 |
|---|---:|
| V2确认股票日期 | 99 |
| V3确认股票日期 | 104 |
| 保留 | 97 |
| 新增 | 7 |
| 移除 | 2 |
| 近期承接改善补入 | 2 |
| 原始评分改变 | 0 |
| 确认结果违反离底/涨幅/破位保护 | 0 |

这是重复的股票日期记录，不是104笔独立交易。不能根据数量变化推断胜率或收益改善。新增规则是结构假设，尚未做独立样本的收益验证。

## 全部变更记录（抽样200只）
| 股票 | 日期 | V2状态 | V3状态 | 原始分 | 当日涨跌 | 离底ATR | 承接路径 |
|---|---|---|---|---|---|---|---|
| 000001 | 2026-09-15 | REBOUNDED | NORMAL | 74 | -0.253% | 0.924 | FIVE_DAY_MEAN |
| 000593 | 2026-09-10 | NOT_CONFIRMED | NORMAL | 73 | -0.869% | 0.518 | RECENT_IMPROVEMENT |
| 000862 | 2026-08-24 | NOT_CONFIRMED | NORMAL | 68 | 0.000% | 0.428 | RECENT_IMPROVEMENT |
| 002132 | 2026-09-14 | REBOUNDED | STRONG | 87 | 0.472% | 0.570 | FIVE_DAY_MEAN |
| 300812 | 2026-08-28 | NORMAL | REBOUNDED | 74 | -0.983% | 0.877 | FIVE_DAY_MEAN |
| 300812 | 2026-09-03 | NORMAL | REBOUNDED | 82 | 0.208% | 1.056 | FIVE_DAY_MEAN |
| 603187 | 2026-08-28 | REBOUNDED | ULTRA | 98 | 0.359% | 0.970 | FIVE_DAY_MEAN |
| 603187 | 2026-08-31 | REBOUNDED | ULTRA | 98 | -0.715% | 0.732 | FIVE_DAY_MEAN |
| 603187 | 2026-09-01 | REBOUNDED | ULTRA | 98 | 0.090% | 0.780 | FIVE_DAY_MEAN |

300812的移除与恢复期间真实低价补记后阶段判断变化有关；9月3日离底1.056 ATR明确超过上限，8月28日处于此前退出后尚未满足重新观察条件的阶段。未为保留旧命中放宽规则。

## 600673专项
8月28日收在当日最低点，仍不确认。9月11日新增普通确认80分，9月14日78分、9月15日76分保留。9月18日仍已反弹，不因90分而放行。
| 股票 | 日期 | V2状态 | V3状态 | 原始分 | 当日涨跌 | 离底ATR | 承接路径 |
|---|---|---|---|---|---|---|---|
| 600673 | 2026-08-24 | NOT_CONFIRMED | NOT_CONFIRMED | 13 | -3.468% | 0.229 | NONE |
| 600673 | 2026-08-25 | NOT_CONFIRMED | NOT_CONFIRMED | 15 | -1.535% | 0.341 | NONE |
| 600673 | 2026-08-26 | NOT_CONFIRMED | NOT_CONFIRMED | 47 | -1.933% | 0.049 | NONE |
| 600673 | 2026-08-27 | NOT_CONFIRMED | NOT_CONFIRMED | 52 | 3.116% | 0.547 | FIVE_DAY_MEAN |
| 600673 | 2026-08-28 | NOT_CONFIRMED | NOT_CONFIRMED | 69 | -1.696% | 0.274 | NONE |
| 600673 | 2026-08-31 | REBOUNDED | REBOUNDED | 72 | 3.952% | 1.092 | FIVE_DAY_MEAN |
| 600673 | 2026-09-01 | REBOUNDED | REBOUNDED | 45 | -4.768% | 0.241 | NONE |
| 600673 | 2026-09-02 | NOT_CONFIRMED | NOT_CONFIRMED | 41 | -1.521% | 0.135 | NONE |
| 600673 | 2026-09-03 | REBOUNDED | REBOUNDED | 50 | 3.378% | 0.733 | NONE |
| 600673 | 2026-09-04 | REBOUNDED | REBOUNDED | 25 | -4.980% | -0.172 | FIVE_DAY_MEAN |
| 600673 | 2026-09-07 | REBOUNDED | REBOUNDED | 21 | 3.701% | 0.466 | NONE |
| 600673 | 2026-09-08 | NOT_CONFIRMED | NOT_CONFIRMED | 47 | -1.516% | 0.503 | FIVE_DAY_MEAN |
| 600673 | 2026-09-09 | REBOUNDED | REBOUNDED | 55 | 1.347% | 0.770 | FIVE_DAY_MEAN |
| 600673 | 2026-09-10 | REBOUNDED | REBOUNDED | 57 | 0.095% | 0.820 | FIVE_DAY_MEAN |
| 600673 | 2026-09-11 | REBOUNDED | NORMAL | 80 | -1.201% | 0.777 | FIVE_DAY_MEAN |
| 600673 | 2026-09-14 | NORMAL | NORMAL | 78 | -0.608% | 0.655 | FIVE_DAY_MEAN |
| 600673 | 2026-09-15 | NORMAL | NORMAL | 76 | 0.386% | 0.752 | FIVE_DAY_MEAN |
| 600673 | 2026-09-16 | NOT_CONFIRMED | REBOUNDED | 80 | 1.572% | 1.124 | FIVE_DAY_MEAN |
| 600673 | 2026-09-17 | NOT_CONFIRMED | REBOUNDED | 78 | 0.221% | 1.201 | FIVE_DAY_MEAN |
| 600673 | 2026-09-18 | REBOUNDED | REBOUNDED | 90 | 1.197% | 1.495 | FIVE_DAY_MEAN |

## 抽样200只股票全部104条V3历史匹配
FIVE_DAY_MEAN=5日均值达标；RECENT_IMPROVEMENT=近期持续改善。NORMAL/STRONG/ULTRA分别为普通/强/极致确认；评分等级与确认强度不是同一维度。
| 股票 | 日期 | V2状态 | V3状态 | 原始分 | 当日涨跌 | 离底ATR | 承接路径 |
|---|---|---|---|---|---|---|---|
| 000001 | 2026-09-15 | REBOUNDED | NORMAL | 74 | -0.253% | 0.924 | FIVE_DAY_MEAN |
| 000039 | 2026-09-11 | STRONG | STRONG | 87 | -3.474% | 0.192 | FIVE_DAY_MEAN |
| 000039 | 2026-09-14 | STRONG | STRONG | 87 | 0.545% | 0.438 | FIVE_DAY_MEAN |
| 000422 | 2026-08-26 | NORMAL | NORMAL | 78 | 0.893% | 0.746 | FIVE_DAY_MEAN |
| 000593 | 2026-09-10 | NOT_CONFIRMED | NORMAL | 73 | -0.869% | 0.518 | RECENT_IMPROVEMENT |
| 000725 | 2026-09-02 | NORMAL | NORMAL | 83 | -2.030% | 0.897 | FIVE_DAY_MEAN |
| 000811 | 2026-09-11 | STRONG | STRONG | 80 | -1.854% | 0.542 | FIVE_DAY_MEAN |
| 000811 | 2026-09-14 | STRONG | STRONG | 80 | -1.727% | 0.338 | FIVE_DAY_MEAN |
| 000811 | 2026-09-15 | STRONG | STRONG | 81 | -0.220% | 0.323 | FIVE_DAY_MEAN |
| 000811 | 2026-09-16 | ULTRA | ULTRA | 90 | 3.523% | 0.793 | FIVE_DAY_MEAN |
| 000862 | 2026-08-24 | NOT_CONFIRMED | NORMAL | 68 | 0.000% | 0.428 | RECENT_IMPROVEMENT |
| 000977 | 2026-08-26 | NORMAL | NORMAL | 68 | -0.432% | 0.490 | FIVE_DAY_MEAN |
| 001337 | 2026-09-07 | NORMAL | NORMAL | 82 | -3.703% | 0.108 | FIVE_DAY_MEAN |
| 002019 | 2026-09-17 | NORMAL | NORMAL | 69 | 0.651% | 0.599 | FIVE_DAY_MEAN |
| 002073 | 2026-09-10 | NORMAL | NORMAL | 68 | -0.685% | 0.296 | FIVE_DAY_MEAN |
| 002132 | 2026-09-14 | REBOUNDED | STRONG | 87 | 0.472% | 0.570 | FIVE_DAY_MEAN |
| 002132 | 2026-09-15 | STRONG | STRONG | 91 | -1.643% | 0.244 | FIVE_DAY_MEAN |
| 002271 | 2026-09-09 | NORMAL | NORMAL | 86 | -0.820% | 0.893 | FIVE_DAY_MEAN |
| 002298 | 2026-08-28 | ULTRA | ULTRA | 100 | -0.617% | 0.946 | FIVE_DAY_MEAN |
| 002531 | 2026-09-02 | NORMAL | NORMAL | 82 | -1.908% | 0.908 | FIVE_DAY_MEAN |
| 002559 | 2026-08-28 | NORMAL | NORMAL | 86 | -0.978% | 0.658 | FIVE_DAY_MEAN |
| 002559 | 2026-09-02 | NORMAL | NORMAL | 86 | -0.986% | 0.548 | FIVE_DAY_MEAN |
| 002559 | 2026-09-03 | NORMAL | NORMAL | 82 | 0.000% | 0.568 | FIVE_DAY_MEAN |
| 002647 | 2026-09-16 | NORMAL | NORMAL | 78 | 0.091% | 0.857 | FIVE_DAY_MEAN |
| 002675 | 2026-08-31 | STRONG | STRONG | 88 | -0.310% | 0.653 | FIVE_DAY_MEAN |
| 002675 | 2026-09-03 | NORMAL | NORMAL | 81 | -0.541% | 0.709 | FIVE_DAY_MEAN |
| 002739 | 2026-08-27 | STRONG | STRONG | 90 | -0.357% | 0.486 | FIVE_DAY_MEAN |
| 002739 | 2026-08-28 | ULTRA | ULTRA | 96 | 0.000% | 0.514 | FIVE_DAY_MEAN |
| 002919 | 2026-09-02 | NORMAL | NORMAL | 74 | 0.230% | 0.879 | FIVE_DAY_MEAN |
| 300045 | 2026-09-03 | NORMAL | NORMAL | 86 | -1.459% | 0.680 | FIVE_DAY_MEAN |
| 300045 | 2026-09-04 | NORMAL | NORMAL | 86 | -0.493% | 0.593 | FIVE_DAY_MEAN |
| 300074 | 2026-09-10 | NORMAL | NORMAL | 81 | -0.261% | 0.477 | FIVE_DAY_MEAN |
| 300137 | 2026-09-03 | NORMAL | NORMAL | 89 | -1.121% | 0.917 | FIVE_DAY_MEAN |
| 300194 | 2026-09-10 | NORMAL | NORMAL | 73 | -1.772% | 0.088 | FIVE_DAY_MEAN |
| 300345 | 2026-09-16 | NORMAL | NORMAL | 82 | 2.125% | 0.744 | FIVE_DAY_MEAN |
| 300515 | 2026-09-04 | STRONG | STRONG | 83 | -1.309% | 0.804 | FIVE_DAY_MEAN |
| 300812 | 2026-08-26 | NORMAL | NORMAL | 68 | -1.560% | 0.654 | FIVE_DAY_MEAN |
| 300812 | 2026-09-02 | NORMAL | NORMAL | 84 | -1.133% | 0.977 | FIVE_DAY_MEAN |
| 300863 | 2026-08-27 | NORMAL | NORMAL | 80 | 2.261% | 0.882 | FIVE_DAY_MEAN |
| 300863 | 2026-08-28 | NORMAL | NORMAL | 87 | -2.234% | 0.570 | FIVE_DAY_MEAN |
| 300863 | 2026-09-03 | NORMAL | NORMAL | 80 | -0.837% | 0.574 | FIVE_DAY_MEAN |
| 300996 | 2026-08-27 | STRONG | STRONG | 88 | 1.738% | 0.285 | FIVE_DAY_MEAN |
| 300996 | 2026-08-28 | NORMAL | NORMAL | 84 | -1.210% | 0.154 | FIVE_DAY_MEAN |
| 300996 | 2026-09-04 | NORMAL | NORMAL | 84 | 2.261% | 0.791 | FIVE_DAY_MEAN |
| 301133 | 2026-09-16 | NORMAL | NORMAL | 74 | 0.113% | 0.585 | FIVE_DAY_MEAN |
| 301262 | 2026-08-28 | NORMAL | NORMAL | 94 | 0.269% | 0.966 | FIVE_DAY_MEAN |
| 301262 | 2026-09-16 | NORMAL | NORMAL | 68 | 0.663% | 0.466 | FIVE_DAY_MEAN |
| 301291 | 2026-09-10 | NORMAL | NORMAL | 86 | -2.352% | 0.438 | FIVE_DAY_MEAN |
| 600118 | 2026-09-14 | NORMAL | NORMAL | 77 | -1.122% | 0.257 | FIVE_DAY_MEAN |
| 600118 | 2026-09-15 | NORMAL | NORMAL | 79 | 0.175% | 0.310 | FIVE_DAY_MEAN |
| 600118 | 2026-09-16 | NORMAL | NORMAL | 81 | 1.481% | 0.693 | FIVE_DAY_MEAN |
| 600301 | 2026-09-01 | NORMAL | NORMAL | 83 | -1.715% | 0.843 | FIVE_DAY_MEAN |
| 600335 | 2026-09-11 | NORMAL | NORMAL | 65 | -2.286% | 0.154 | FIVE_DAY_MEAN |
| 600458 | 2026-09-02 | NORMAL | NORMAL | 74 | -2.462% | 0.998 | FIVE_DAY_MEAN |
| 600785 | 2026-09-18 | NORMAL | NORMAL | 76 | 3.097% | 0.777 | FIVE_DAY_MEAN |
| 600851 | 2026-09-04 | NORMAL | NORMAL | 81 | -1.506% | 0.679 | FIVE_DAY_MEAN |
| 600851 | 2026-09-16 | NORMAL | NORMAL | 84 | 0.726% | 0.638 | FIVE_DAY_MEAN |
| 600851 | 2026-09-17 | NORMAL | NORMAL | 87 | -0.720% | 0.457 | FIVE_DAY_MEAN |
| 601001 | 2026-09-17 | NORMAL | NORMAL | 86 | -0.177% | 0.523 | FIVE_DAY_MEAN |
| 601001 | 2026-09-18 | STRONG | STRONG | 85 | -0.415% | 0.445 | FIVE_DAY_MEAN |
| 601127 | 2026-08-27 | NORMAL | NORMAL | 84 | -0.178% | 0.685 | FIVE_DAY_MEAN |
| 601127 | 2026-08-28 | STRONG | STRONG | 93 | 0.139% | 0.760 | FIVE_DAY_MEAN |
| 601127 | 2026-08-31 | STRONG | STRONG | 85 | -1.957% | 0.245 | FIVE_DAY_MEAN |
| 601216 | 2026-09-18 | NORMAL | NORMAL | 72 | -0.216% | 0.358 | FIVE_DAY_MEAN |
| 601698 | 2026-09-14 | NORMAL | NORMAL | 81 | -1.531% | 0.798 | FIVE_DAY_MEAN |
| 601858 | 2026-09-17 | NORMAL | NORMAL | 80 | -0.398% | 0.563 | FIVE_DAY_MEAN |
| 603091 | 2026-08-27 | NORMAL | NORMAL | 80 | 0.766% | 0.914 | FIVE_DAY_MEAN |
| 603119 | 2026-08-26 | NORMAL | NORMAL | 80 | -0.962% | 0.475 | FIVE_DAY_MEAN |
| 603119 | 2026-09-02 | NORMAL | NORMAL | 72 | -0.714% | 0.756 | FIVE_DAY_MEAN |
| 603187 | 2026-08-28 | REBOUNDED | ULTRA | 98 | 0.359% | 0.970 | FIVE_DAY_MEAN |
| 603187 | 2026-08-31 | REBOUNDED | ULTRA | 98 | -0.715% | 0.732 | FIVE_DAY_MEAN |
| 603187 | 2026-09-01 | REBOUNDED | ULTRA | 98 | 0.090% | 0.780 | FIVE_DAY_MEAN |
| 603187 | 2026-09-02 | NORMAL | NORMAL | 88 | -1.619% | 0.178 | FIVE_DAY_MEAN |
| 603317 | 2026-08-28 | NORMAL | NORMAL | 72 | 1.343% | 0.937 | FIVE_DAY_MEAN |
| 603317 | 2026-08-31 | NORMAL | NORMAL | 80 | -0.957% | 0.727 | FIVE_DAY_MEAN |
| 603317 | 2026-09-01 | NORMAL | NORMAL | 80 | -1.264% | 0.430 | FIVE_DAY_MEAN |
| 603317 | 2026-09-02 | NORMAL | NORMAL | 72 | -0.678% | 0.440 | FIVE_DAY_MEAN |
| 603317 | 2026-09-03 | NORMAL | NORMAL | 74 | -0.379% | 0.350 | FIVE_DAY_MEAN |
| 603317 | 2026-09-18 | STRONG | STRONG | 86 | 1.106% | 0.742 | FIVE_DAY_MEAN |
| 603636 | 2026-08-27 | NORMAL | NORMAL | 86 | -0.288% | 0.697 | FIVE_DAY_MEAN |
| 603636 | 2026-08-28 | NORMAL | NORMAL | 92 | 0.578% | 0.847 | FIVE_DAY_MEAN |
| 605033 | 2026-09-18 | NORMAL | NORMAL | 84 | -0.162% | 0.531 | FIVE_DAY_MEAN |
| 605128 | 2026-08-26 | NORMAL | NORMAL | 83 | -0.474% | 0.433 | FIVE_DAY_MEAN |
| 605128 | 2026-08-27 | ULTRA | ULTRA | 93 | 1.600% | 0.770 | FIVE_DAY_MEAN |
| 688004 | 2026-09-03 | NORMAL | NORMAL | 84 | -0.897% | 0.128 | FIVE_DAY_MEAN |
| 688032 | 2026-09-16 | NORMAL | NORMAL | 69 | 1.060% | 0.807 | FIVE_DAY_MEAN |
| 688032 | 2026-09-17 | NORMAL | NORMAL | 72 | -1.224% | 0.399 | FIVE_DAY_MEAN |
| 688096 | 2026-09-02 | NORMAL | NORMAL | 84 | -1.808% | 0.948 | FIVE_DAY_MEAN |
| 688096 | 2026-09-10 | NORMAL | NORMAL | 81 | -1.238% | 0.199 | FIVE_DAY_MEAN |
| 688213 | 2026-09-11 | NORMAL | NORMAL | 72 | 1.236% | 0.907 | FIVE_DAY_MEAN |
| 688213 | 2026-09-14 | NORMAL | NORMAL | 76 | 0.184% | 0.956 | FIVE_DAY_MEAN |
| 688213 | 2026-09-15 | NORMAL | NORMAL | 82 | -0.388% | 0.862 | FIVE_DAY_MEAN |
| 688213 | 2026-09-16 | STRONG | STRONG | 88 | 0.000% | 0.895 | FIVE_DAY_MEAN |
| 688277 | 2026-08-31 | NORMAL | NORMAL | 87 | 0.583% | 0.656 | FIVE_DAY_MEAN |
| 688306 | 2026-09-04 | NORMAL | NORMAL | 69 | -0.581% | 0.515 | FIVE_DAY_MEAN |
| 688363 | 2026-08-31 | NORMAL | NORMAL | 78 | -1.604% | 0.308 | FIVE_DAY_MEAN |
| 688363 | 2026-09-08 | NORMAL | NORMAL | 78 | 0.426% | 0.564 | FIVE_DAY_MEAN |
| 688363 | 2026-09-17 | NORMAL | NORMAL | 67 | -0.059% | 0.719 | FIVE_DAY_MEAN |
| 688568 | 2026-09-03 | NORMAL | NORMAL | 86 | -1.858% | 0.925 | FIVE_DAY_MEAN |
| 688597 | 2026-08-27 | NORMAL | NORMAL | 68 | -1.198% | 0.211 | FIVE_DAY_MEAN |
| 688626 | 2026-09-01 | STRONG | STRONG | 85 | -1.440% | 0.521 | FIVE_DAY_MEAN |
| 688796 | 2026-09-07 | NORMAL | NORMAL | 82 | -0.492% | 0.559 | FIVE_DAY_MEAN |
| 688796 | 2026-09-10 | NORMAL | NORMAL | 72 | -2.785% | 0.859 | FIVE_DAY_MEAN |
| 688796 | 2026-09-11 | NORMAL | NORMAL | 80 | -1.714% | 0.666 | FIVE_DAY_MEAN |

## 验证与风险
- `SELLING_EXHAUSTION_REAL_DB=data/cuphandle.db` 下执行 `python -m pytest tests/test_selling_exhaustion.py tests/test_selling_exhaustion_local.py tests/test_strategy6_batch_evaluation.py tests/test_ema_compression.py -q`：50通过。
- `python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py`：1769通过、9跳过（需显式本地DB的测试，已在上述专项启用验证），259.72秒。
- `npm --prefix web test -- --run`：168通过；`npm --prefix web run build`：成功。保留已有Vite CJS弃用及大包体积警告；未做真实浏览器人工验收。
- `python -m compileall scanner strategy6 server.py scripts/compare_selling_exhaustion_v3.py -q`、`git diff --check`：通过。
- 开发后审核未发现未处理的中高等级问题；真实低点漏记已修复并用600673的30.03价格/日期断言覆盖。
- 无未来数据：阶段、ATR及承接窗口均只读取评估日及之前；保留逐日prefix一致性测试。
- 000811的9月14/15日强确认保持；002774、688112、000811、001339、688052的9月18日仍为REBOUNDED。
- 边界测试覆盖一根好K线不足、最新弱收盘、配置无效、单日反弹、新低保护、恢复原底部、原始评分独立、前端字段与筛选。
- 只验证代理指标，不等于真实主动卖单耗尽；停牌、流动性、真实跌停仍不在本诊断范围内。
- 当前股票池有幸存者偏差，样本与案例已被查看，不能当作未见数据或独立OOS验证。
- 未修改正在运行服务；需后端加载新代码后重新点击批量评分，旧页面已返回的数据不会自动重算。

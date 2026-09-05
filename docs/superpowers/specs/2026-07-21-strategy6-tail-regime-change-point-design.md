# 策略6尾部收缩变点识别设计

## 1. 目标

在不修改策略6正式5日尾段、正式评分、硬过滤、候选分层和旧扫描入口的前提下，新增一个基于历史可见数据的尾部收缩变点识别器。尾段长度由数据中的波动和成交量状态变化推导，不再预设为4、5、6或7日。

首期只作为影子研究能力：输出变点、实际尾段长度和证据，不参与正式候选资格。完成历史As-Of对比并通过预注册门禁后，才允许另行申请正式升级。

## 2. 不变边界

- `StrongVcpTailEngine.evaluate_at()` 仍是策略6唯一入口。
- 默认 `decision_profile=formal_original` 不变。
- `evaluate_dry_tail()` 的固定5日业务逻辑、阈值和输出不变。
- BOX、Brooks、动态尾段和质量V2继续只属于研究画像。
- 变点结果不得改变 `dry_tail_pass`、`tail_score`、`reject_reasons`、`candidate_type`、生命周期和交易计划。
- 不修改策略1至策略5。
- 只使用评估日及以前的K线；回测必须逐日As-Of重建。
- 不读取2026年起OOS收益，不自动修改生产配置。

## 3. 核心定义

### 3.1 识别区间

仅在策略6阶段划分已经找到有效启动和整理区后运行。

- 搜索终点：当前评估日。
- 搜索起点：整理阶段起点之后。
- 每个候选变点之前至少有5根整理K线作为基准。
- 变点之后至少有3根K线才计算当前证据。
- 基准最多取变点前20根整理K线，使用中位数和MAD，禁止包含变点后的缩量K线。
- 不枚举固定尾段天数；候选变点遍历整理阶段内所有满足样本要求的位置。

最少样本只用于统计可识别性，不代表3日即可成为正式候选。首期没有任何变点结果进入正式决策。

### 3.2 每日特征

对每根K线计算四个无量纲特征：

1. `log_volume`：`log1p(volume)`。
2. `true_range_pct`：真实波幅除以前收盘。
3. `body_pct`：实体绝对值除以前收盘。
4. `abs_return`：收盘收益率绝对值。

价格结构另行计算：

- 尾段收盘离散度：`MAD(close) / median(close)`。
- 尾段低点斜率：以ATR归一化的稳健线性斜率。
- 是否存在放量大跌、连续低点恶化或关键支撑破位。

### 3.3 鲁棒变点代价

对每个候选变点，分别计算“不分段”和“基准/尾段两段”的鲁棒BIC：

```text
feature_cost(segment) = sum(abs(x - median(segment))) / max(global_MAD, epsilon)
BIC = n * log(max(total_cost / n, epsilon)) + parameter_count * log(n)
delta_bic = BIC_single - BIC_split
```

单段模型每个特征使用1个位置参数，分段模型每个特征使用2个位置参数；四个特征的BIC分别计算后求和。`delta_bic` 越大，表示两段状态比单一状态更可信。V1固定使用 `delta_bic >= 6` 作为中等证据标准，不在首轮实验中搜索该阈值。

### 3.4 收缩方向约束

统计分段成立还必须满足方向正确：

- 尾段/基准成交量中位数比 `<= 0.80`，这是必选条件。
- `true_range`、实体、绝对收益三个比值中至少两个 `<= 0.85`。
- 尾段最高/最低收盘区间不超过现有正式尾段8%的结构上限；MAD比例只作为连续诊断字段输出，不替代该硬口径。
- 尾段低点的Theil-Sen斜率除以尾段ATR中位数后必须 `>= -0.10 ATR/交易日`。
- 放量大跌复用现有 `big_down_return` 和 `big_down_volume_ratio`；连续低点恶化复用“后半最低价不得低于前半最低价99%”；有效支撑破位复用当前策略6关键支撑和连续两日收盘破位口径。任一触发时状态为 `BROKEN`，不得确认为收缩尾段。

这些是预注册V1常量，不增加到普通前端可调参数，避免扩大生产参数空间。

### 3.5 变点选择

1. 找出所有同时满足BIC和收缩方向的候选变点。
2. 取 `delta_bic` 最大值作为最佳证据。
3. 与最佳值相差不超过2的候选视为统计不可区分，选择其中最早的变点，优先保留更完整的稳定阶段。
4. 不按总分挑选最好看的窗口，不允许同一股票事后选择最有利阈值。

### 3.6 连续确认

为避免单日重新分段造成抖动，评估日T还要按As-Of方式对T-1重新运行识别：

- T检测成立、T-1不成立：`FORMING`。
- T和T-1均成立，且两个起点相同或相差不超过1个交易日：`CONFIRMED`。
- T结构风险触发：`BROKEN`。
- 无显著变点：`NO_REGIME_CHANGE`。
- 数据不足：`INSUFFICIENT_BASELINE`。

`CONFIRMED`只是研究标签，不具有买入或正式候选语义。

## 4. 输出结构

新增 `Strategy6TailRegime`，并保留所有旧字段：

| 字段 | 含义 |
| --- | --- |
| `tail_regime_enabled` | 影子识别是否启用 |
| `tail_regime_status` | FORMING / CONFIRMED / BROKEN / NO_REGIME_CHANGE / INSUFFICIENT_BASELINE |
| `tail_regime_start_date` | 推导出的收缩起点 |
| `tail_regime_days` | 评估日到变点的实际交易日数 |
| `tail_regime_delta_bic` | 分段相对不分段的证据强度 |
| `tail_regime_volume_ratio` | 尾段/基准成交量中位数比 |
| `tail_regime_range_ratio` | true range中位数比 |
| `tail_regime_body_ratio` | 实体中位数比 |
| `tail_regime_abs_return_ratio` | 绝对收益中位数比 |
| `tail_regime_close_dispersion` | 尾段收盘MAD比例 |
| `tail_regime_low_slope_atr` | ATR归一化低点斜率 |
| `tail_regime_model_version` | 固定为 `TAIL_REGIME_CP_V1` |
| `tail_regime_reasons` | 成立证据 |
| `tail_regime_risks` | 结构风险或数据问题 |

SQLite使用兼容加列；旧任务字段为空。Excel/CSV和候选详情可展示这些字段，但候选列表不得按该字段过滤。

## 5. 代码结构

- 新增 `strategy6/tail_regime.py`：无数据库依赖，实现特征、鲁棒BIC、候选选择和T/T-1确认；当前评估日的支撑价和风险上下文由引擎显式传入，内部不得读取全局状态。
- 修改 `strategy6/models.py`：新增数据模型和候选兼容输出。
- 修改 `strategy6/engine.py`：在阶段划分后调用影子识别器，但不把结果传入评分和过滤。
- 修改 `strategy6/validation.py`：仅增加 `tail_regime_shadow_enabled`，默认开启；V1统计常量不暴露为普通配置。
- 修改 `scanner/db.py`、`strategy6/report.py`：兼容持久化和导出。
- 修改 `web/src/pages/Strategy6Results.vue`：详情增加“尾部变点观察”，明确标记“不参与正式选股”。
- 新增 `strategy6/backtest/tail_regime_research.py`：使用冻结引擎逐日As-Of生成固定5日与变点标签对照，不复制正式候选逻辑。

## 6. 历史研究设计

### 6.1 对照组

按评估日记录四组：

- `BOTH`：固定5日通过且变点确认。
- `FIXED_ONLY`：固定5日通过但变点未确认。
- `REGIME_ONLY`：固定5日失败但变点确认。
- `NEITHER`：两者都未通过。

研究报告必须说明每组股票、日期、固定尾段拒绝原因、变点起点、实际天数和证据指标。

`REGIME_ONLY`的假设交易只能替换“ORIGINAL固定尾部是否通过”这一项证据：流动性、趋势、启动、阶段、形态、支撑、市场、RR和其它正式硬过滤必须全部通过。研究适配器仍调用冻结引擎获得这些结论，禁止复制一套候选规则。入场、T+1、NEXT_OPEN、涨跌停、停牌、费用、滑点、止损优先和退出规则全部复用现有回测执行引擎。

### 6.2 时间边界

- 2023-2024：训练研究，只用于判断变点标签是否有增量价值。
- 2025：确认期，只验证预注册V1，不根据结果反向修改算法。
- 2026起：继续锁定，不读取收益。

### 6.3 首轮验收门禁

影子能力不以候选数量增加作为成功标准。申请正式实验至少满足：

1. `REGIME_ONLY`有足够闭合样本；少于30笔只能继续观察。
2. 训练期和2025确认期的期望R均为正。
3. PF均不低于1.20。
4. 平均盈利R/平均亏损R不低于2.5。
5. 参数上下扰动测试不适用于V1固定常量；只能整体比较V1是否稳定，禁止根据2025结果调阈值。
6. 高成本、70%成交率和延迟一天压力测试不能全面失效。

首轮不通过时保留影子字段，不进入正式评分和过滤。

## 7. 测试计划

### 7.1 单元测试

- 明显量缩、ATR收缩和实体收缩能够定位已知变点。
- 只有成交量收缩、价格仍剧烈波动时不得确认。
- 平稳但没有显著前后状态变化时返回 `NO_REGIME_CHANGE`。
- 候选变点并列时选择统计不可区分范围内的最早起点。
- 放量下跌、低点恶化和支撑破位返回 `BROKEN`。
- T成立但T-1不成立为 `FORMING`；起点稳定后为 `CONFIRMED`。
- 增加评估日之后的未来K线不改变历史日结果。
- 缺量、零价格、样本不足不会抛异常。

### 7.2 集成测试

- 正式画像开启/关闭影子识别时，旧 `dry_tail_pass`、总分、拒绝原因和候选类型完全一致。
- 研究画像的BOX/Brooks/动态尾段行为不变。
- SQLite旧库自动加列，旧任务仍可读取。
- 前端详情显示起点、天数、状态和“不参与正式选股”。
- 策略1至策略5测试不受影响。

### 7.3 验证命令

```powershell
python -m pytest tests/test_strategy6_tail_regime.py tests/test_strategy6_core_rules.py tests/test_strategy6_db_api.py -q
python -m pytest tests -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py --ignore=tests/test_yfinance_hist.py
python -m compileall scanner strategy2 strategy3 strategy4 strategy5 strategy6 server.py -q
npm.cmd --prefix web test -- --run Strategy6Results
npm.cmd --prefix web test -- --run
npm.cmd --prefix web run build
```

## 8. 风险与控制

- **伪科学置信度：** 不输出概率，只输出可复核的 `delta_bic`、比值和状态。
- **短窗口过拟合：** BIC复杂度惩罚、最少样本和T/T-1连续确认共同约束。
- **参数再次膨胀：** V1阈值固定在版本代码中，普通配置只提供影子启停。
- **未来数据泄漏：** 所有计算都从As-Of切片执行；T-1确认必须重新截断，不能从T结果倒推。
- **正式结果漂移：** 影子结果不进入任何正式决策函数，并用开关前后完全一致测试锁定。
- **历史验证污染：** 2025只确认，2026继续锁定；验证失败不得调阈值后重跑宣称通过。

## 9. 最终交付

- 尾部变点影子识别代码、模型、SQLite字段、导出和前端详情。
- 单元、集成和全量回归结果。
- 2023-2025真实本地数据研究报告及每日股票明细。
- 固定5日与变点识别四组差异统计。
- 明确结论：继续影子观察、申请下一阶段正式实验，或否定该能力。

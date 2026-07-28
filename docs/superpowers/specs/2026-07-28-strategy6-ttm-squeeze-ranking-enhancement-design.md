# 策略6 TTM Squeeze 质量排序增强设计

## 1. 目标

在策略6现有“强势启动后整理、量干价稳、支撑和客观盈亏比”主链上增加 TTM Squeeze 波动压缩与动量诊断，用来识别：

- 波动率正在压缩且多头动量改善的蓄力结构；
- 挤压刚解除、波动开始扩张且多头动量确认的释放结构；
- 挤压向弱势方向释放的风险结构。

TTM Squeeze 只增加独立质量分和排序能力，不作为硬过滤，不改变策略6原有 `total_score`、候选门槛、候选类型、生命周期和交易计划。策略1至策略5不受影响。

参考口径：[StockCharts ChartSchool TTM Squeeze](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/ttm-squeeze) 与 [SharpCharts 参数参考](https://help.stockcharts.com/charts-and-tools/sharpcharts/sharpcharts-workbench/editing-sharpcharts/sharpcharts-parameter-reference)。默认参数为布林带 `20, 2.0`、Keltner Channel `20, 1.5, 20`、动量周期 `20`。

## 2. 不变边界

1. `StrongVcpTailEngine.evaluate_at()` 继续作为策略6扫描和回测的唯一入口。
2. `score.total_score` 继续使用现有正式画像或研究画像模型，不加入 TTM 分。
3. `classify_candidate()`、`hard_filter_reasons()` 不读取 TTM 结果。
4. 原 `evaluate_dry_tail()`、稳定箱体、Brooks、VCP轮次、支撑、盈亏比和市场过滤逻辑不修改。
5. 不删除或改名任何旧输出字段、数据库字段和 API 字段。
6. TTM 只读取评估日及以前的日线；历史回测必须随 `evaluation_date` 截断，禁止未来数据泄漏。
7. 当前全部价格为前复权口径。TTM 内部只使用同一套前复权 OHLC，不混入未复权价格。

## 3. 指标计算

新增策略6专用模块 `strategy6/ttm_squeeze.py`，不得放入策略1至策略5共享指标模块。

### 3.1 数据要求

- 输入为策略6已标准化、按日期升序的 OHLC 行。
- 计算当前与前一交易日完整状态至少需要 40 根日线。
- 数据不足、OHLC 非法或中间值不可计算时返回 `INSUFFICIENT_DATA`，TTM 分为0，不阻断原策略。

### 3.2 布林带

默认周期 `20`：

```text
BB Middle = SMA20(Close)
BB Upper  = BB Middle + 2.0 * PopulationStdDev20(Close)
BB Lower  = BB Middle - 2.0 * PopulationStdDev20(Close)
```

标准差固定使用总体标准差，避免不同运行环境的样本标准差差异。

### 3.3 Keltner Channel

采用 StockCharts 参数参考中可复现的 EMA + ATR 口径：

```text
KC Middle = EMA20(Close)
KC Upper  = KC Middle + 1.5 * WilderATR20
KC Lower  = KC Middle - 1.5 * WilderATR20
```

True Range：

```text
TR = max(High-Low, abs(High-PreviousClose), abs(Low-PreviousClose))
```

首个 ATR 为前20个 TR的简单平均，后续按 Wilder 公式平滑。EMA 以首个20日 SMA作为种子，后续使用 `2/(20+1)` 平滑。

### 3.4 挤压状态

当前交易日同时满足下列条件时 `squeeze_on=true`：

```text
BB Upper < KC Upper
BB Lower > KC Lower
```

连续挤压天数从当前交易日向前统计连续 `squeeze_on` 的交易日数量。

若当前交易日 `squeeze_on=false` 且前一交易日 `squeeze_on=true`，则 `fired=true`，表示挤压刚解除。

### 3.5 动量柱

每个可计算交易日先计算：

```text
Donchian Midline = (HighestHigh20 + LowestLow20) / 2
Delta = Close - ((Donchian Midline + SMA20(Close)) / 2)
```

对最近20个 `Delta` 使用普通最小二乘线性回归，横坐标固定为 `0..19`。当前动量柱取回归直线在最后一个横坐标 `19` 的拟合值：

```text
slope = sum((x-xMean)*(y-yMean)) / sum((x-xMean)^2)
intercept = yMean - slope*xMean
momentum = intercept + slope*19
```

同时计算前一交易日动量。方向定义：

- `RISING`：当前动量大于前一动量；
- `FALLING`：当前动量小于前一动量；
- `FLAT`：二者差值绝对值不超过 `max(abs(previous), close*0.0001, 1e-9) * 0.001`。

## 4. 状态与质量分

新增 `Strategy6TtmSqueeze` 数据结构，独立于原六维评分。

| 状态 | 条件 | 分数 | 说明 |
|---|---|---:|---|
| `FIRED_BULLISH` | 当日解除挤压，动量>0且上升 | 4 | 多头挤压释放，优先级最高 |
| `SQUEEZE_BULLISH` | 当前挤压连续至少3日，动量>0且上升 | 3 | 蓄力增强 |
| `SQUEEZE_NEUTRAL` | 当前挤压，且动量不是“≤0并下降” | 2 | 波动压缩成立，多头方向未完全确认 |
| `SQUEEZE_BEARISH` | 当前挤压，动量≤0且下降 | 0 | 弱势压缩，仅风险提示 |
| `FIRED_WEAK` | 当日解除挤压，但动量≤0或未上升 | 0 | 释放方向不利，仅风险提示 |
| `OFF` | 未挤压且当日没有解除挤压 | 0 | 无TTM加分 |
| `INSUFFICIENT_DATA` | 数据不足或不可计算 | 0 | 不阻断旧逻辑 |
| `DISABLED` | 配置关闭 | 0 | 不计算 |

触发原因使用稳定代码，例如：

- `TTM_SQUEEZE_ON`
- `TTM_SQUEEZE_3D_PLUS`
- `TTM_FIRED`
- `TTM_MOMENTUM_POSITIVE`
- `TTM_MOMENTUM_RISING`

风险提示使用稳定代码：

- `TTM_SQUEEZE_BEARISH_MOMENTUM`
- `TTM_FIRED_WITHOUT_BULLISH_MOMENTUM`
- `TTM_DATA_INSUFFICIENT`

这些风险提示只写入 TTM 自身的 `risk_tags`，不写入策略6硬过滤原因。

## 5. 排序规则

新增：

```text
ttm_squeeze_score = 0..4
ranking_score = total_score + ttm_squeeze_score
```

约束：

1. `ranking_score` 只用于同一候选类型内部排序和前端展示。
2. `READY_CANDIDATE`、`KEY_CANDIDATE`、`WATCH_CANDIDATE` 的类型优先级保持不变，不能让观察候选因 TTM 分排到重点候选之前。
3. 候选资格、评分门槛、生命周期状态和回测信号生成仍只使用原 `total_score` 与原规则。
4. 排序顺序为：候选类型优先级、`ranking_score DESC`、`total_score DESC`、股票代码升序。
5. 旧任务缺失 `ranking_score` 时按 `total_score` 回退，不能显示0或改变旧任务顺序。

## 6. 配置

在 `strategy6.ttm_squeeze` 增加显式配置：

```yaml
strategy6:
  ttm_squeeze:
    enabled: true
    bb_period: 20
    bb_stddev: 2.0
    kc_ema_period: 20
    kc_atr_period: 20
    kc_atr_multiplier: 1.5
    momentum_period: 20
    bullish_squeeze_min_days: 3
    max_ranking_bonus: 4
```

参数校验：

- 周期必须为整数，范围 `5..120`；
- 倍数必须为正数，范围 `(0, 10]`；
- `bullish_squeeze_min_days` 范围 `1..20`；
- `max_ranking_bonus` 本版本固定为4，拒绝其他值，避免前端配置无效。

前端策略配置页提供启停开关和上述参数。默认启用，但关闭后必须完全退化为旧排序。

## 7. 输出和兼容

新增字段：

- `ttm_squeeze_status`
- `ttm_squeeze_on`
- `ttm_squeeze_days`
- `ttm_fired`
- `ttm_momentum`
- `ttm_previous_momentum`
- `ttm_momentum_direction`
- `ttm_bb_upper` / `ttm_bb_lower`
- `ttm_kc_upper` / `ttm_kc_lower`
- `ttm_squeeze_score`
- `ranking_score`
- `ttm_reasons`
- `ttm_risk_tags`
- `ttm_model_version`，固定为 `S6_TTM_SQUEEZE_V1`

字段写入策略6候选数据库、API、CSV/XLSX报告和回测信号快照。数据库使用兼容迁移，不执行破坏性变更。

前端：

- 重点候选、观察候选和 VCP确认候选表增加简洁的“TTM状态”列；
- 显示中文状态、`TTM +N` 和连续挤压天数；
- 详情区展示布林带、Keltner、动量方向、原因和风险提示；
- 旧任务字段缺失时显示“未计算”，不得伪造成 `OFF`。

## 8. 数据流

```text
标准化日线
  -> calculate_ttm_squeeze(rows, config)
  -> Strategy6TtmSqueeze
  -> StrongVcpTailEngine.evaluate_at()
  -> Strategy6Evaluation
  -> to_candidate_dict()
  -> SQLite / API / 报告 / 回测快照
  -> 前端展示和候选类型内排序
```

TTM 计算放在指标标准化之后、最终评分之前。评分函数不读取 TTM；引擎在原 `score_strategy6()` 完成后计算 `ranking_score`，从结构上保证原100分和分类行为不变。

## 9. 测试

### 9.1 单元测试

1. 布林带、EMA、Wilder ATR、Keltner和线性回归使用可手算序列验证。
2. 挤压边界：上下轨严格位于通道内才成立，等于边界不成立。
3. 连续挤压天数统计正确。
4. 覆盖全部8种状态和 `0/2/3/4` 分值。
5. 数据不足、非法 OHLC 不抛出未处理异常。
6. 改变评估日之后的数据不影响历史评估结果。

### 9.2 引擎与兼容测试

1. 开启与关闭 TTM 时，原 `total_score`、候选类型、拒绝原因、生命周期和交易计划完全一致。
2. TTM 只改变 `ranking_score` 和同类候选顺序。
3. 正式画像与研究画像都输出 TTM，但不改变各自评分模型版本。
4. 策略1至策略5测试不受影响。

### 9.3 存储、API和前端测试

1. 新字段可写入、读取、导出并兼容旧数据库。
2. 旧任务 `ranking_score` 回退到 `total_score`。
3. 前端中文状态、详情和配置参数可加载、保存。
4. CSV/XLSX包含全部审计字段。

### 9.4 真实数据验证

使用本地 `data/cuphandle.db`：

1. 对最近一个完整交易日重跑策略6；
2. 输出各TTM状态数量、候选类型分布和前20名排序变化；
3. 列出因TTM上升和未变化的代表股票；
4. 不因本轮验证自动调整正式参数；
5. 后续只有历史回测显示候选质量有稳定提升，才讨论将TTM升级为候选门槛。

## 10. 风险控制

1. TTM 衡量波动压缩与方向，不等于突破一定成功，必须继续依赖策略6强势启动、支撑和盈亏比。
2. TTM与尾部价稳、箱体紧密K线存在相关性，因此不并入原尾部分，避免重复计分。
3. 单日挤压可能是噪声，只有连续至少3日且多头动量改善才获得3分；但挤压刚释放遵循指标原始语义，可获得4分。
4. 前复权历史在除权点可能改变历史波动结构；扫描和回测必须使用同一数据快照口径。
5. 本版本只做日线，不引入小时线或多周期确认。

## 11. 验收标准

1. 原策略6候选资格与 `total_score` 在相同数据和配置下零变化。
2. TTM计算、状态、分值和排序可由输出字段完整审计。
3. 历史回测不存在未来数据泄漏。
4. 旧任务、旧数据库和旧 API 调用方兼容。
5. 策略1至策略5无回归。
6. 后端专项与完整测试、前端测试和构建全部通过。

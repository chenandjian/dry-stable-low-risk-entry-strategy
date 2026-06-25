# 开发方案文档：策略3「强势回踩二次启动」

## 1. 需求背景

### 1.1 当前问题

项目当前已有两条正式策略链路：

- 策略1：杯柄/VCP 结构扫描，核心入口为 `scanner/strategy_engine.py::CupHandleStrategyEngine.evaluate_at()`。
- 策略2：极致量干价稳扫描，核心入口为 `strategy2/engine.py::ExtremeDryStableStrategyEngine.evaluate_at()`。

策略1质量要求高，但强依赖杯柄/VCP结构，市场缺少标准形态时容易长期无候选。策略2不依赖杯柄/VCP，但强调极致缩量、价格稳定、趋势过滤、一票否决和低风险比，在波动稍大的强势行情中也容易无候选。

因此需要新增策略3，覆盖一种策略1和策略2都不擅长的机会：

> 已经被市场证明过强的股票，经过健康回踩后，缩量企稳并出现二次转强迹象。

策略3不是策略1/2的放宽版，也不是为了强行增加候选数量。它应当识别独立机会类型：强趋势中的低风险回踩再启动。

### 1.2 用户痛点

- 策略1/2都可能在真实行情中出现 0 候选，用户无法判断是否错过非标准但高质量的强势股回踩机会。
- 标准杯柄/VCP以外的趋势延续机会缺少统一识别和解释。
- 策略2的极致量干价稳适合非常安静的结构，但部分强势股回踩企稳后并不会满足极致缩量。
- 用户需要高质量候选，可以接受候选变少，但不希望因为规则形态过窄而长期没有可观察股票。

### 1.3 业务目标

新增策略3「强势回踩二次启动」，目标是：

1. 找强势趋势中回踩后的二次启动机会。
2. 不追高，不抄弱势深跌，不依赖完整杯柄/VCP。
3. 保持风险位置清晰，当前价到止损距离可控。
4. 每个候选都能解释：为什么强、为什么回踩健康、为什么正在二次转强、风险在哪里。
5. 与策略1/2配置、候选、API、前端页面和回测结果隔离。

### 1.4 预期效果

用户可以独立启动策略3扫描。系统对全市场股票执行流动性过滤、趋势强度判断、健康回踩判断、缩量企稳判断、二次转强判断和风险收益判断。通过正式阈值的股票写入策略3独立候选表，并在策略3结果页按核心候选、观察候选分层展示。低优先级观察仅写入逐股审计或回测诊断，不进入首期正式候选列表。

---

## 2. 策略定位

### 2.1 策略名称

策略3：强势回踩二次启动

英文内部命名：

```text
STRATEGY_3_STRONG_PULLBACK_SECOND_BREAKOUT
```

目录：

```text
strategy3/
```

### 2.2 策略一句话定义

先证明它强，再等待它回踩，最后只在缩量企稳后重新转强时入选。

### 2.3 与策略1的区别

策略1以杯柄/VCP形态为核心。策略3不检测杯柄，不要求杯柄、柄部、杯口、VCP收缩次数，不使用策略1的 `CupHandleStrategyEngine`、`pattern_detector`、`analyzer.*` 或候选决策模块。

### 2.4 与策略2的区别

策略2以极致量干价稳为核心，先排除下降趋势，再要求低波动、低风险和高量干价稳评分。策略3允许强势股回踩后存在适度波动，但要求趋势仍强、回踩健康、支撑未破、二次转强明确。

### 2.5 策略3适合的行情

- 结构性行情。
- 指数震荡但局部强势股活跃。
- 强势板块回踩后重新启动。
- 标准杯柄/VCP较少，但趋势延续机会较多。

### 2.6 策略3不适合的行情

- 单边普跌行情。
- 普遍放量下跌行情。
- 高位情绪末端加速行情。
- 弱势股深跌反抽行情。

---

## 3. 需求目标

### 3.1 必须实现

- 新增策略3独立配置段 `strategy3`。
- 新增策略3独立核心模型、指标、评分、否决、风险、引擎和扫描编排。
- 策略3扫描不调用策略1/策略2判断入口。
- 允许复用股票池、日线数据、数据库基础能力、数据新鲜度判断、流动性过滤和全局扫描互斥能力。
- 新增 `scan_tasks.strategy_type` 取值 `STRATEGY_3_STRONG_PULLBACK_SECOND_BREAKOUT`。
- 新增策略3独立候选表，不写入策略1 `candidates`，不写入策略2 `strategy2_candidates`。
- 新增策略3扫描启动、状态、候选列表、候选详情、历史任务列表 API。
- 前端扫描控制台新增策略3启动入口。
- 前端新增策略3结果页。
- 前端策略配置页新增策略3配置分区。
- 策略3回测必须只读本地 `stock_pool` / `daily_ohlc`。
- 回测结果必须能追溯原始信号、机会、入场、止损、目标和失败原因。
- 补充核心算法、扫描隔离、API、前端和回测测试。

### 3.2 可选增强

- 策略3与策略1/2候选横向对比页面。
- 策略3候选加入板块/行业统计。
- 支持策略3参数实验，不直接影响正式扫描参数。
- 支持导出 CSV。

可选增强不作为首期验收阻塞项。

### 3.3 不做范围

- 不修改策略1评分、形态、决策、候选规则。
- 不修改策略2评分、趋势、否决、风险规则。
- 不引入新的外部行情源。
- 不做行业轮动模型。
- 不做机器学习模型。
- 不做自动买卖建议。
- 不把策略3结果混入策略1/策略2结果页。
- 不为了增加候选数而取消风险过滤。

---

## 4. 策略3核心规则

### 4.1 数据窗口

默认配置：

```yaml
strategy3:
  enabled: true
  strategy_window_days: 250
  minimum_required_days: 180
  pullback_lookback_days: 60
  support_lookback_days: 20
  candidate_min_score: 75
  core_min_score: 85
  max_risk_ratio: 0.08
  max_pullback_from_high: 0.30
  min_pullback_from_high: 0.08
  max_recent_range_5: 0.12
  max_recent_surge_3: 0.10
  min_relative_strength_60: 0.05
  volume_shrink_ratio: 0.85
```

约束：

- `minimum_required_days >= 120`。
- `strategy_window_days >= minimum_required_days`。
- `strategy_window_days <= liquidity.min_listing_days`。
- `pullback_lookback_days` 范围 40 至 120。
- `support_lookback_days` 范围 10 至 40。
- 所有计算只使用评估日及之前数据。

### 4.2 全局前置过滤

股票必须先通过：

- 股票池过滤。
- ST/北交所等全局过滤。
- 上市天数检查。
- 全局流动性过滤。
- 日线数据新鲜度检查。

若全局数据源全部失败，不允许用旧缓存产出新候选，股票进入失败列表。

### 4.3 强势趋势过滤

目的：只找已被市场证明过强的股票。

计算项：

- `ma20`、`ma60`、`ma120`。
- `return_20`、`return_60`、`return_120`。
- `high_120`、`drawdown_from_high_120`。
- `relative_strength_60 = stock_return_60 - index_return_60`。
- `ma60_slope_20 = ma60_now / ma60_20_days_ago - 1`。

硬过滤：

- `close < ma60` 且 `ma20 < ma60`：排除。
- `drawdown_from_high_120 > 35%`：排除。
- `relative_strength_60 < min_relative_strength_60`：排除，默认阈值为 5%。
- `ma60_slope_20 < -3%`：排除。

加分：

- `close >= ma20 >= ma60`。
- `ma60_slope_20 > 0`。
- `relative_strength_60 >= min_relative_strength_60`。
- `return_60 >= 10%`。
- `drawdown_from_high_120 <= 20%`。

### 4.4 健康回踩过滤

目的：避免追高，也避免深跌弱反抽。

定义：

- `recent_high = 最近 pullback_lookback_days 的最高价`，固定使用日线 `high` 字段，避免不同实现用收盘价和最高价产生不一致结果。
- `pullback_pct = (recent_high - close) / recent_high`。

硬过滤：

- `pullback_pct < 8%`：排除为“回踩不足，偏追高风险”。
- `pullback_pct > 30%`：排除为“回撤过深，趋势损坏风险”。
- 最近 5 日最大振幅 `range_5 > 12%`：排除。
- 最近 5 日任一单日跌幅 <= -5% 且成交量 > V20：排除。
- 当前收盘价连续两日低于 `ma60`：排除。

加分：

- `pullback_pct` 位于 10% 至 22%。
- 当前价高于 `ma60`。
- 当前价在 `ma20` 附近或刚收复 `ma20`。
- 最近 10 日没有放量长阴。

### 4.5 缩量企稳

目的：确认回踩过程中抛压减弱。

计算项：

- `v5`、`v10`、`v20`。
- `volume_ratio_5_20 = v5 / v20`。
- `down_day_volume_ratio = 最近下跌日平均量 / v20`。
- `close_range_5`。
- `low_stability_5 = 最近5日最低价波动区间`。

硬过滤：

- `volume_ratio_5_20 > 1.20` 且最近 5 日涨幅不明显：排除为“缩量不足或放量滞涨”。
- `close_range_5 > 8%`：排除。
- 最近 3 日连续收阴且总跌幅超过 6%：排除。

加分：

- `volume_ratio_5_20 <= 0.85`。
- `volume_ratio_5_20 <= 0.70`。
- `close_range_5 <= 5%`。
- 最近 5 日低点没有持续下移。
- 下跌日成交量低于 V20。

### 4.6 二次转强

目的：避免只买“还在下跌的安静股票”，要求出现再启动迹象。

硬过滤：

- 当前收盘仍低于 `ma5` 且 `ma5` 下行：排除。
- 最近 3 日涨幅 `return_3 >= 10%`：排除为“短线已过热”。
- 当前价距离最近 20 日高点不到 1%，且最近 3 日涨幅超过 7%：排除为“临近追高”。

加分：

- 当前收盘重新站上 `ma5`。
- 当前收盘重新站上 `ma10`。
- 最近 3 日至少 2 日收阳。
- 当前收盘位于最近 5 日收盘区间上半区。
- 当日成交量高于 V5 但不超过 V20 的 1.8 倍。

### 4.7 风险收益

支撑位取三者中的最低值，作为风险计算的保守支撑：

- 最近 `support_lookback_days` 最低价。
- `ma20`。
- 最近回踩低点。

止损：

```text
support_price = min(pullback_low, ma20, support_low)
stop_loss = support_price * 0.98
```

风险比：

```text
risk_ratio = (close - stop_loss) / close
```

第一目标：

- 最近 `pullback_lookback_days` 高点。
- 若已非常接近前高，则目标取前高上方 3%。

硬过滤：

- `risk_ratio > max_risk_ratio`：排除。
- `target_1 <= close`：排除。
- `rr1 < 1.5`：排除。

加分：

- `risk_ratio <= 5%`。
- `rr1 >= 2`。
- 当前价距离支撑不远，但没有跌破支撑。

---

## 5. 评分体系

满分 100：

| 模块 | 分值 | 说明 |
|---|---:|---|
| 趋势强度 | 25 | 是否是强势趋势，而非弱势反抽 |
| 回踩质量 | 25 | 回踩深度是否合理，结构是否未损坏 |
| 缩量企稳 | 20 | 抛压是否减弱，价格是否收窄 |
| 二次转强 | 15 | 是否出现重新转强迹象 |
| 风险收益 | 15 | 止损是否明确，风险是否可控 |

### 5.1 趋势强度 25 分

- `close >= ma20 >= ma60`：5 分。
- `close >= ma60`：5 分。
- `ma60_slope_20 > 0`：5 分。
- `relative_strength_60 >= min_relative_strength_60`：5 分。
- `return_60 >= 10%` 且 `drawdown_from_high_120 <= 25%`：5 分。

模块得分必须封顶 25 分。

### 5.2 回踩质量 25 分

- `pullback_pct` 在 10% 至 22%：8 分。
- `pullback_pct` 在 8% 至 30%：4 分。
- 当前价高于 `ma60`：5 分。
- 当前价在 `ma20` 上下 5% 内：4 分。
- 最近 10 日没有放量长阴：4 分。
- 低点没有连续破位：4 分。

同一子项不得重复得分；若命中 10% 至 22%，不再叠加 8% 至 30% 的 4 分。
模块得分必须封顶 25 分。

### 5.3 缩量企稳 20 分

- `volume_ratio_5_20 <= 0.85`：5 分。
- `volume_ratio_5_20 <= 0.70`：额外 5 分。
- `close_range_5 <= 5%`：4 分。
- 最近 5 日低点没有持续下移：3 分。
- 下跌日平均量低于 V20：3 分。

模块得分必须封顶 20 分。

### 5.4 二次转强 15 分

- 收盘站上 `ma5`：3 分。
- 收盘站上 `ma10`：3 分。
- 最近 3 日至少 2 日收阳：3 分。
- 收盘位于最近 5 日收盘区间上半区：3 分。
- 当日温和放量，`v_today > v5` 且 `v_today <= 1.8 * v20`：3 分。

模块得分必须封顶 15 分。

### 5.5 风险收益 15 分

- `risk_ratio <= 8%`：4 分。
- `risk_ratio <= 5%`：额外 3 分。
- `rr1 >= 1.5`：4 分。
- `rr1 >= 2`：额外 2 分。
- 当前价未跌破关键支撑：2 分。

模块得分必须封顶 15 分。

---

## 6. 入选分层

### 6.1 核心候选

条件：

- 总分 `>= core_min_score`，默认 85。
- 无硬过滤。
- `risk_ratio <= max_risk_ratio`。
- `rr1 >= 1.5`。

展示标签：

```text
核心候选
```

### 6.2 观察候选

条件：

- 总分 `>= candidate_min_score`，默认 75。
- 无硬过滤。
- `risk_ratio <= max_risk_ratio`。
- `rr1 >= 1.5`。

展示标签：

```text
观察候选
```

### 6.3 低优先级观察

条件：

- 总分 65 至 74。
- 无硬过滤。

默认不进入正式候选表；可在回测或诊断页展示。

首期正式扫描只保存核心候选和观察候选，低优先级观察写入逐股状态或审计明细，不展示在正式候选列表。

---

## 7. 一票否决规则

策略3任何一票否决触发即不入正式候选：

| 错误码 | 规则 |
|---|---|
| `BELOW_MA60_AND_WEAK_TREND` | 收盘低于 MA60 且 MA20 低于 MA60 |
| `DEEP_DRAWDOWN_FROM_HIGH` | 120 日高点回撤超过 35% |
| `RELATIVE_STRENGTH_WEAK` | 60 日相对强度小于 0 |
| `PULLBACK_TOO_SHALLOW` | 回踩小于 8% |
| `PULLBACK_TOO_DEEP` | 回踩超过 30% |
| `RECENT_RANGE_TOO_WIDE` | 最近 5 日振幅超过 12% |
| `HEAVY_VOLUME_DROP` | 最近 5 日存在放量大跌 |
| `MA60_BREAKDOWN` | 连续两日收盘低于 MA60 |
| `VOLUME_NOT_STABLE` | 缩量不足且放量滞涨 |
| `RECENT_OVERHEATED` | 最近 3 日涨幅超过 10% |
| `CHASE_NEAR_HIGH` | 临近前高且短线涨幅过快 |
| `RISK_RATIO_TOO_HIGH` | 当前价到止损超过配置上限 |
| `RR_TOO_LOW` | 第一目标盈亏比低于 1.5 |

---

## 8. 数据模型

### 8.1 策略3候选表

新增表：

```text
strategy3_candidates
```

首期字段：

- `id`
- `task_id`
- `code`
- `name`
- `evaluation_date`
- `total_score`
- `level`
- `trend_score`
- `pullback_score`
- `volume_stability_score`
- `second_breakout_score`
- `risk_reward_score`
- `current_close`
- `ma5`
- `ma10`
- `ma20`
- `ma60`
- `ma120`
- `recent_high`
- `pullback_pct`
- `relative_strength_60`
- `volume_ratio_5_20`
- `range_5`
- `close_range_5`
- `support_price`
- `stop_loss`
- `target_1`
- `risk_ratio`
- `rr1`
- `score_reasons`
- `reject_reasons`
- `created_at`

唯一约束：

```text
(task_id, code)
```

### 8.2 逐股状态

继续复用 `task_stocks`，但 `strategy_type` 为策略3时：

- `status='candidate'` 表示策略3正式候选。
- `status='scanned'` 表示已评估但未入选。
- `status_reason` 写入稳定错误码或 `SCORE_BELOW_THRESHOLD`。
- `error_detail` 可写入关键指标 JSON，便于调试和前端诊断。

---

## 9. 后端模块设计

新增模块：

```text
strategy3/
  __init__.py
  models.py
  validation.py
  indicators.py
  trend.py
  pullback.py
  volume_stability.py
  second_breakout.py
  risk.py
  scorer.py
  rejection.py
  engine.py
  scanner.py
  backtester.py
  backtest_models.py
```

### 9.1 唯一策略入口

```python
StrongPullbackSecondBreakoutEngine.evaluate_at(data, code="", name="", market_data=None)
```

返回：

```python
Strategy3Evaluation
```

必须包含：

- `passed`
- `status_reason`
- `evaluation_date`
- `total_score`
- 五个子评分
- 关键指标
- 风险信息
- `score_reasons`
- `reject_reasons`

### 9.2 独立性要求

`strategy3/` 不得导入：

- `scanner.pattern_detector`
- `scanner.strategy_engine`
- `analyzer.*`
- `strategy2.engine`
- `strategy2.scorer`
- `strategy2.rejection`
- `strategy2.trend`

允许导入：

- `scanner.db`
- `scanner.daily_data_service`
- `scanner.data_source`
- `scanner.liquidity_filter`
- 通用标准库

如需与策略2共享数学 helper，应先提取到中立共享模块，例如 `scanner/market_math.py`，不得从 `strategy2/` 反向 import。首期优先在 `strategy3/` 内实现策略3所需的纯函数，只有出现明确重复且不改变策略语义时才提取共享模块。

---

## 10. API 设计

新增接口：

```text
POST /api/strategy3/scans
GET  /api/strategy3/scans/status
GET  /api/strategy3/tasks
GET  /api/strategy3/candidates?task_id=
GET  /api/strategy3/candidates/{code}?task_id=
POST /api/strategy3/tasks/{task_id}/retry-failed
POST /api/strategy3/tasks/{task_id}/re-evaluate
```

策略隔离：

- 策略1 task_id 调策略3接口返回 `TASK_STRATEGY_MISMATCH`。
- 策略2 task_id 调策略3接口返回 `TASK_STRATEGY_MISMATCH`。
- 策略3 task_id 调策略1/2接口返回 `TASK_STRATEGY_MISMATCH`。

全局互斥：

- 任一策略全市场扫描运行时，不允许启动策略3。
- 策略3运行时，不允许启动策略1/2。

---

## 11. 前端设计

### 11.1 扫描控制台

新增策略3启动按钮：

```text
启动策略3：强势回踩
```

任一策略运行时，三个启动按钮全部禁用。

扫描进度展示：

- 当前策略名称。
- task_id。
- 总数、已处理、跳过、失败、候选。
- 最新交易日。
- 当前股票。
- 实时发现。

策略3实时发现字段：

- 代码/名称。
- 总分。
- 等级。
- 回踩幅度。
- 风险比。
- RR1。

### 11.2 策略3结果页

新增页面：

```text
/strategy3/results
```

表格字段：

- 代码
- 名称
- 总分
- 等级
- 趋势分
- 回踩分
- 缩量企稳分
- 二次转强分
- 风险收益分
- 回踩幅度
- 风险比
- RR1
- 支撑位
- 止损
- 第一目标
- 评估日期

支持排序：

- 总分。
- 风险比。
- RR1。
- 回踩幅度。
- 趋势分。

### 11.3 策略配置页

新增策略3配置分区：

- 是否启用。
- 策略窗口天数。
- 最低有效数据天数。
- 候选最低分。
- 核心候选最低分。
- 最大风险比。
- 最小回踩幅度。
- 最大回踩幅度。
- 最大最近5日振幅。
- 最大最近3日涨幅。
- 最低60日相对强度。
- 缩量比例。

文案必须说明：

- 策略3不是杯柄/VCP策略。
- 策略3不是极致量干价稳策略。
- 策略3重点寻找强势股健康回踩后的二次启动。

---

## 12. 回测设计

### 12.1 回测原则

- 只读本地 `stock_pool` 和 `daily_ohlc`。
- 禁止拉取外部行情。
- 每个评估日只使用当日及之前数据。
- 信号、机会、入场、止损和目标必须可追溯。

### 12.2 执行模型

默认执行模型：

```text
NEXT_OPEN
```

入场：

- 信号日次日开盘价。
- 若次日开盘低于止损，则标记 `NO_ENTRY_GAP_BELOW_STOP`。
- 若次日开盘高于第一目标附近，标记 `NO_ENTRY_GAP_TOO_HIGH`。

退出：

- 首先观察止损。
- 再观察第一目标。
- 持有期默认 10 个交易日和 20 个交易日两组统计。
- 同日同时触发止损和目标时，按止损优先。

### 12.3 机会合并

同一股票连续多个策略3信号应合并为一次机会。

拆分新机会条件：

- 两次命中之间累计 10 个有效未命中交易日。
- 或前一机会已触发止损/目标/时间退出。

### 12.4 回测统计

必须统计：

- 信号数。
- 机会数。
- 入场数。
- 未入场数。
- 止损率。
- 目标达成率。
- 10 日收益均值/中位数。
- 20 日收益均值/中位数。
- 按等级分组。
- 按回踩幅度分组。
- 按风险比分组。
- 按月份分组。

---

## 13. 测试要求

### 13.1 单元测试

- 配置校验。
- 指标计算。
- 强势趋势过滤。
- 健康回踩过滤。
- 缩量企稳评分。
- 二次转强评分。
- 风险收益计算。
- 一票否决稳定错误码。
- 策略3引擎 `evaluate_at()`。

### 13.2 隔离测试

- `strategy3/` 不导入策略1判断模块。
- `strategy3/` 不导入策略2判断模块。
- 策略3候选不写入 `candidates`。
- 策略3候选不写入 `strategy2_candidates`。
- 跨策略 task_id 返回 `TASK_STRATEGY_MISMATCH`。

### 13.3 扫描测试

- 正常全市场扫描。
- 无候选扫描。
- 有候选扫描。
- 流动性过滤。
- 数据不足。
- 数据源全部失败。
- 运行中互斥。
- 失败股票重试。

### 13.4 回测测试

- 本地 DB 只读数据。
- 不访问外部源。
- 信号不读取未来数据。
- NEXT_OPEN 入场。
- 止损优先。
- 机会合并和拆分。
- 零机会合法完成。
- 任务恢复和幂等重跑。

### 13.5 前端测试

- 策略3配置页校验。
- 扫描控制台三个策略互斥按钮。
- 策略3结果页候选展示。
- 策略3空结果展示。
- 历史任务切换防 stale response。

---

## 14. 验收标准

### 14.1 功能验收

- 能独立启动策略3扫描。
- 策略3任务写入 `scan_tasks.strategy_type`。
- 策略3候选写入独立表。
- 策略3结果页可查看历史任务和候选。
- 策略1/2功能不回归。

### 14.2 数据验收

- 所有策略3候选均能解释入选原因。
- 未入选股票有稳定 `status_reason`。
- 扫描完成后 `processed = scanned + skipped + failed + candidate`。
- 任务候选数与候选表数量一致。

### 14.3 策略验收

- 策略3不得长期只靠低分放水产出候选。
- 策略3候选必须有明确止损和 RR1。
- 深跌弱反抽不得入选。
- 已大幅追高不得入选。
- 当前价跌破核心支撑不得入选。

### 14.4 回测验收

- 回测任务可完成并生成汇总。
- 每个机会可追溯到原始信号。
- 回测不请求外部数据源。
- 回测结果区分零机会、失败、中断和完成。

---

## 15. 建议实施顺序

1. 新增策略3核心模型和配置校验。
2. 实现指标、过滤、评分、风险模块。
3. 实现 `StrongPullbackSecondBreakoutEngine.evaluate_at()`。
4. 增加数据库表和任务类型。
5. 增加扫描编排和 API。
6. 增加前端配置、启动入口和结果页。
7. 增加本地 DB 回测。
8. 跑一轮策略3回测和扫描，生成审核文档。
9. 根据回测结果只调整解释性展示和默认参数，不直接追求候选数量。

---

## 16. 给开发 AI 的执行要求

请按以下要求实现：

1. 不要修改策略1和策略2核心规则。
2. 策略3必须独立目录、独立引擎、独立候选表。
3. 策略3不得导入策略1/策略2判断模块。
4. 优先实现可测试的纯函数，再接扫描和 API。
5. 每个硬过滤必须有稳定错误码。
6. 每个候选必须保存评分原因和风险字段。
7. 不要引入机器学习、行业模型或新外部数据源。
8. 回测只读本地数据库。
9. 修复或开发时遵守 TDD，先写失败测试再实现。
10. 完成后必须跑后端测试、前端测试和构建。

---

## 17. 不建议修改的内容

- 不要修改策略1杯柄/VCP判断。
- 不要修改策略1干稳决策。
- 不要修改策略2趋势过滤、评分、否决和风险规则。
- 不要改动共享日线数据源语义。
- 不要降低全局流动性过滤来制造候选。
- 不要把策略3候选混入策略1/2页面。
- 不要改动历史任务的策略类型语义。

---

## 18. 最终交付标准

策略3开发完成后应满足：

1. 策略3可以独立扫描、独立展示、独立回测。
2. 策略3候选解释清晰，包括趋势、回踩、缩量、转强和风险。
3. 策略3不破坏策略1/2。
4. 扫描结果和数据库状态一致。
5. 回测可信、可追溯、可重复。
6. 前端能清晰区分三套策略。
7. 有完整测试和验证结果。

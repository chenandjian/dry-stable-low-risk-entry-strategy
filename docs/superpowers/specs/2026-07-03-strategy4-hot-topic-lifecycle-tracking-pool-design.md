# 策略4热点生命周期跟踪池设计

## 1. 背景

策略4当前定位是「热点龙头二波」：先识别热门行业/题材，再识别题材内龙头，最后判断龙头是否出现第一波上涨后的健康回踩和二次启动。

当前实现已经具备两类热点/龙头来源：

- `live_external`：实时 AkShare / 同花顺行业、概念摘要和成分股来源。
- `historical_kline_derived`：基于真实行业/题材指数 K 线和成分股 K 线，在 `evaluation_date` 当日及之前反推热点和龙头。

现有问题不再是“没有行业 K 线”或“不能反推历史热点”，而是策略4仍然偏向「单次扫描即时判断」：

```text
当前扫描日热门行业
  -> 当前扫描日龙头
  -> 当前扫描日是否回踩/二波
  -> 当前扫描日候选
```

这会漏掉一种很常见的二波机会：某个行业在 1 号成为热点，龙头第一波上涨后，随后 20-60 天进入回踩、缩量、修复、二次启动。到二次启动当天，该行业可能已经不是当天榜单最热的行业，但它仍然处在可交易的主线生命周期中。

因此，本次设计是在策略4现有基础上新增「热点生命周期跟踪池」：

```text
热点首次确认
  -> 进入 120 天跟踪池
  -> 每次策略4扫描/回测日更新题材和龙头状态
  -> 只要未失效，允许从跟踪池生成二波候选
```

## 2. 目标

### 2.1 必须实现

1. 基于当前策略4继续增强，不新建策略5，不替换策略4原入口。
2. 新增热点题材生命周期跟踪池，默认跟踪 120 自然日。
3. 新增龙头股票生命周期跟踪池，跟随热点题材一起更新。
4. 当前热点源和历史 K 线反推源都可以把题材/龙头加入跟踪池。
5. 策略4扫描时，除了即时热点，也要评估跟踪池内未失效的题材/龙头。
6. 策略4回测时必须按日期顺序重放跟踪池，禁止使用未来热点、未来成分股、未来个股 K 线。
7. 候选旧字段保持兼容，只允许新增字段，不删除或改名旧字段。
8. 不修改策略1、策略2、策略3。
9. 前端能清楚展示「即时热点候选」和「跟踪池二波候选」的来源差异。

### 2.2 不做范围

- 不做自动交易。
- 不做机器学习预测。
- 不用未来数据补过去的热点池。
- 不为了扩大候选数量放宽策略4现有核心风控。
- 不把 `WATCH_HOT` / `NOISE_TOPIC` 直接当作可买候选。
- 不修改策略1、策略2、策略3扫描入口、表结构或候选页面。

## 3. 当前策略4现状

### 3.1 入口和调用链

实时扫描入口：

```text
server.py
  POST /api/strategy4/scans
    -> strategy4.scanner.scan_strategy4_all()
      -> TopicSourceService.fetch_topics()
      -> derive_hot_topics_for_date()
      -> merge_topics()
      -> db.replace_strategy4_hot_topics()
      -> _build_leaders_and_candidates_from_topics()
        -> TopicSourceService.fetch_topic_members()
        -> derive_leaders_for_topic()
        -> _load_strategy4_daily_data()
        -> HotLeaderSecondWaveEngine.evaluate_at()
        -> score_leader_candidate()
        -> db.replace_strategy4_leaders()
        -> db.upsert_strategy4_candidate()
```

回测入口：

```text
strategy4.backtester.run_strategy4_snapshot_backtest()
  -> _snapshot_task_for_exact_date()
  -> _derived_snapshots_for_date_cached()
  -> merge_topics() / merge_leaders()
  -> _select_topics_for_experiment()
  -> topic_index_context_from_history()
  -> topic_index_context_passes_filters()
  -> _evaluate_leader_snapshot()
  -> HotLeaderSecondWaveEngine.evaluate_at()
  -> calculate_strategy4_execution_outcome()
```

### 3.2 已有核心文件

| 文件 | 当前职责 |
|---|---|
| `strategy4/scanner.py` | 策略4扫描编排、即时热点/派生热点融合、龙头评估、候选入库 |
| `strategy4/backtester.py` | 策略4历史快照回测和参数实验 |
| `strategy4/derived_topic_detector.py` | 基于行业/题材 K 线反推历史热点 |
| `strategy4/derived_leader_detector.py` | 基于成分股 K 线反推历史龙头 |
| `strategy4/topic_index_service.py` | 行业/题材指数 K 线缓存、拉取、历史截断 |
| `strategy4/topic_index_analyzer.py` | 板块趋势、突破、量能、风险、阶段判断 |
| `strategy4/topic_index_filters.py` | 策略4候选共享板块过滤 |
| `strategy4/engine.py` | 单只龙头二波判断入口 |
| `scanner/db.py` | 策略4热点、龙头、候选、题材指数、成员表 |
| `server.py` | 策略4 API 和任务中心入口 |

### 3.3 已有数据表

当前已有：

- `strategy4_hot_topics`
- `strategy4_leaders`
- `strategy4_candidates`
- `strategy4_topic_index_ohlc`
- `strategy4_topic_index_fetch_status`
- `strategy4_topic_members`
- `strategy4_derived_hot_topics`
- `strategy4_derived_leaders`

本次新增跟踪池表应与这些表并存，不替代它们。

## 4. 核心设计：热点生命周期跟踪池

### 4.1 总体模型

新增两个事实表和一个审计表：

```text
strategy4_tracked_topics
strategy4_tracked_leaders
strategy4_tracking_events
```

含义：

- `strategy4_tracked_topics`：某个行业/题材从首次确认热点开始，到失效/过期前的生命周期状态。
- `strategy4_tracked_leaders`：某个题材下的龙头，从首次确认到回踩、二波、失效/过期的生命周期状态。
- `strategy4_tracking_events`：每天更新跟踪池时记录状态变化、触发原因和风险原因，方便回测审计和前端解释。

### 4.2 生命周期阶段

题材生命周期：

| 状态 | 含义 |
|---|---|
| `ACTIVE_HOT` | 最近刚确认热点，处于强关注期 |
| `COOLING_WATCH` | 热度回落但未破坏，等待龙头回踩 |
| `SECOND_WAVE_WATCH` | 题材进入修复/二波观察期 |
| `RISK_REPAIR` | 题材风险偏高，但未彻底失效，只能观察 |
| `INVALIDATED` | 题材趋势破坏，不再允许生成可买候选 |
| `EXPIRED` | 超过最大跟踪周期，自动过期 |

龙头生命周期：

| 状态 | 含义 |
|---|---|
| `LEADER_ACTIVE` | 龙头第一波仍强 |
| `PULLBACK_TRACKING` | 龙头进入健康回踩观察 |
| `SECOND_WAVE_READY` | 龙头满足二波候选条件 |
| `LOCKED_WATCH` | 一字板/缩量连板，关注但当前不可交易 |
| `INVALIDATED` | 龙头破位、走弱或风险收益失效 |
| `EXPIRED` | 超过跟踪周期或题材过期 |

### 4.3 时间窗口

默认使用自然日统计生命周期年龄，交易判断仍基于有效 K 线：

| 窗口 | 默认 | 处理方式 |
|---|---:|---|
| 强关注期 | 1-20 自然日 | 允许更高热度权重，重点识别第一波和早期回踩 |
| 黄金二波期 | 21-60 自然日 | 最适合识别健康回踩后的二次启动 |
| 延长期 | 61-120 自然日 | 只保留趋势未破坏、盈亏比优秀的候选 |
| 过期 | >120 自然日 | 默认不再生成候选 |

配置建议：

```yaml
strategy4:
  tracking:
    enabled: true
    max_calendar_days: 120
    strong_attention_days: 20
    golden_second_wave_days: 60
    allow_extension_days: 120
    expire_without_leader_days: 30
```

## 5. 入池规则

### 5.1 题材入池

题材满足以下任一条件时进入或刷新跟踪池：

1. `live_external` 评分后状态为 `CONFIRMED_HOT` 或 `LOCKED_HOT_TOPIC`。
2. `historical_kline_derived` 评分后状态为 `CONFIRMED_HOT`。
3. 已在跟踪池中的题材再次被任一来源确认，刷新 `last_confirmed_date`、`peak_hot_score` 和来源证据。

不入池：

- `NOISE_TOPIC`
- `UNOBSERVED_TOPIC_INDEX`
- 只有 `WATCH_HOT` 且没有趋势/突破/量能确认的题材

### 5.2 龙头入池

龙头满足以下任一条件时进入或刷新跟踪池：

1. 即时扫描或历史反推中 `leader.status == LEADER_CONFIRMED`。
2. 题材已入池，成分股在题材内相对强度排名靠前，且满足最低龙头分。
3. 已在跟踪池中的龙头再次被确认，刷新 `last_confirmed_date`、`peak_leader_score`、`first_wave_high`。

不入池：

- 日线数据缺失且不是明确停牌。
- 龙头分不足且没有相对强度证据。
- 个股已触发硬失效条件。

## 6. 每日更新逻辑

每次策略4扫描或回测评估日，执行以下步骤：

```text
1. 生成当前即时热点/龙头快照
2. 生成当前 historical_kline_derived 热点/龙头快照
3. 合并快照并写入原有 strategy4_hot_topics / leaders
4. 用合并快照更新 tracking pool
5. 对 tracking pool 中未失效题材执行生命周期更新
6. 对 tracking pool 中未失效龙头执行回踩/二波/风控更新
7. 从即时快照和 tracking pool 两路生成候选
8. 候选去重，保留来源和解释字段
```

### 6.1 题材更新指标

每个跟踪题材在评估日读取 `strategy4_topic_index_ohlc` 中 `date <= evaluation_date` 的数据，计算：

- `topic_return_5d`
- `topic_return_20d`
- `topic_return_60d`
- `drawdown_from_high_20`
- `drawdown_from_high_since_detected`
- `topic_index_phase`
- `topic_index_trend_score`
- `topic_index_breakout_score`
- `topic_index_volume_score`
- `topic_index_risk_flags`

优先复用 `analyze_topic_index()`，不要在跟踪池里重复实现另一套板块分析。

### 6.2 龙头更新指标

每个跟踪龙头在评估日读取 `daily_ohlc` 中 `date <= evaluation_date` 的数据，计算：

- `return_5d`
- `return_20d`
- `leader_rs_10d`
- `leader_rs_20d`
- `first_wave_high`
- `pullback_pct_from_first_wave_high`
- `pullback_days`
- `support_price`
- `stop_loss`
- `target_price`
- `risk_ratio`
- `reward_risk_ratio`
- `second_wave_signal`

优先复用：

- `HotLeaderSecondWaveEngine.evaluate_at()`
- `evaluate_first_wave()`
- `evaluate_pullback()`
- `evaluate_second_wave()`
- `evaluate_risk_reward()`

## 7. 失效规则

### 7.1 题材失效

题材出现以下任一情况，应标记为 `INVALIDATED`，不再生成可买候选：

1. `topic_index_phase == WEAK_NOISE` 连续出现。
2. 题材指数跌破 MA60，且 MA20 斜率转弱。
3. 从首次确认后的高点回撤超过 20%。
4. `topic_index_risk_flags` 中出现放量破位、连续下跌等高风险信号。
5. 连续 30 天没有任何可观察龙头，且题材未再次确认。

超过 `max_calendar_days=120` 标记为 `EXPIRED`。

### 7.2 龙头失效

龙头出现以下任一情况，应标记为 `INVALIDATED`：

1. 跌破关键支撑或止损位。
2. 第一波高点后回撤超过 45%。
3. 连续新低，且成交量没有萎缩修复。
4. 20 日相对题材强度明显转负。
5. 放量破位、大阴实体扩大。
6. 风险收益比长期不合格。
7. 所属题材已经 `INVALIDATED` 或 `EXPIRED`。

超过题材最大跟踪期，龙头同步 `EXPIRED`。

## 8. 候选生成规则

### 8.1 即时热点候选

保留当前策略4逻辑：

- 当前题材必须是 `CONFIRMED_HOT` 或 `LOCKED_HOT_TOPIC`。
- 板块指数通过 `topic_index_context_passes_filters()`。
- 龙头必须 `LEADER_CONFIRMED`。
- `HotLeaderSecondWaveEngine.evaluate_at()` 必须通过。
- 风险收益通过。

### 8.2 跟踪池候选

从跟踪池生成候选时，必须满足：

1. 题材状态是 `ACTIVE_HOT`、`COOLING_WATCH` 或 `SECOND_WAVE_WATCH`。
2. 题材未触发失效规则。
3. 龙头状态是 `PULLBACK_TRACKING` 或 `SECOND_WAVE_READY`。
4. 龙头 `HotLeaderSecondWaveEngine.evaluate_at()` 当前通过。
5. 板块指数仍通过基础过滤：
   - 阶段属于 `EARLY_ACCELERATION`、`MAIN_TREND`、`PULLBACK_REPAIR`。
   - `drawdown_from_high_20` 不超过配置阈值。
   - 不是 `WEAK_NOISE` 或 `HIGH_RISK_CLIMAX`。
6. 风险收益比达标。

延长期 61-120 天应更严格：

- `reward_risk_ratio >= 2.0`
- `risk_ratio <= 0.12`
- 龙头 20 日相对题材强度不能明显为负。
- 题材不能处于 `RISK_REPAIR`。

### 8.3 候选去重

同一任务内同一 `code + topic_id` 只保留一条候选。

如果即时热点和跟踪池同时命中：

- `candidate_origin = merged_current_and_tracking`
- 保留即时热点分、跟踪池年龄、首次确认日期。

如果只有跟踪池命中：

- `candidate_origin = tracking_pool`
- 必须输出跟踪原因和最近一次题材确认日期，避免用户误以为是当天最热题材。

## 9. 数据结构设计

### 9.1 `strategy4_tracked_topics`

建议字段：

| 字段 | 含义 |
|---|---|
| `id` | 主键 |
| `topic_id` | 题材唯一 ID |
| `topic_name` | 题材名称 |
| `topic_type` | 行业/概念 |
| `first_detected_date` | 首次确认热点日期 |
| `last_confirmed_date` | 最近一次被热点源确认日期 |
| `last_evaluated_date` | 最近一次生命周期更新日期 |
| `age_calendar_days` | 生命周期自然日 |
| `tracking_status` | 生命周期状态 |
| `peak_hot_score` | 生命周期内最高热点分 |
| `latest_hot_score` | 最新热点分 |
| `topic_index_phase` | 最新板块阶段 |
| `topic_index_latest_date` | 最新板块 K 线日期 |
| `source_modes` | 来源列表 JSON |
| `membership_mode` | 成分股口径 |
| `invalid_reason` | 失效原因 |
| `risk_flags` | 风险标记 JSON |
| `raw_snapshot` | 审计 JSON |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |

唯一约束建议：

```text
UNIQUE(topic_id)
```

### 9.2 `strategy4_tracked_leaders`

建议字段：

| 字段 | 含义 |
|---|---|
| `id` | 主键 |
| `topic_id` | 所属题材 |
| `topic_name` | 题材名称 |
| `code` | 股票代码 |
| `name` | 股票名称 |
| `first_detected_date` | 首次确认为龙头日期 |
| `last_confirmed_date` | 最近一次确认为龙头日期 |
| `last_evaluated_date` | 最近一次评估日期 |
| `tracking_status` | 龙头生命周期状态 |
| `peak_leader_score` | 最高龙头分 |
| `latest_leader_score` | 最新龙头分 |
| `first_wave_high` | 第一波高点 |
| `first_wave_high_date` | 第一波高点日期 |
| `pullback_pct` | 当前回踩幅度 |
| `pullback_days` | 当前回踩天数 |
| `support_price` | 支撑位 |
| `stop_loss` | 止损位 |
| `target_price` | 目标位 |
| `risk_ratio` | 风险比 |
| `reward_risk_ratio` | 盈亏比 |
| `candidate_origin` | 来源 |
| `membership_mode` | 成分股口径 |
| `invalid_reason` | 失效原因 |
| `risk_flags` | 风险标记 JSON |
| `raw_snapshot` | 审计 JSON |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |

唯一约束建议：

```text
UNIQUE(topic_id, code)
```

### 9.3 `strategy4_tracking_events`

建议字段：

| 字段 | 含义 |
|---|---|
| `id` | 主键 |
| `evaluation_date` | 评估日期 |
| `task_id` | 扫描/回测任务 ID |
| `entity_type` | `topic` / `leader` |
| `topic_id` | 题材 ID |
| `code` | 股票代码，可空 |
| `previous_status` | 前状态 |
| `new_status` | 新状态 |
| `event_type` | `ENTER_POOL` / `REFRESH` / `STATUS_CHANGE` / `INVALIDATE` / `EXPIRE` / `CANDIDATE` |
| `reason` | 原因 |
| `metrics_snapshot` | 指标 JSON |
| `created_at` | 创建时间 |

## 10. 输出字段设计

策略4候选新增字段，不删除旧字段：

| 字段 | 含义 |
|---|---|
| `candidate_origin` | `current_hot` / `tracking_pool` / `merged_current_and_tracking` |
| `tracking_topic_status` | 题材跟踪状态 |
| `tracking_leader_status` | 龙头跟踪状态 |
| `topic_first_detected_date` | 题材首次确认日期 |
| `topic_last_confirmed_date` | 题材最近确认日期 |
| `leader_first_detected_date` | 龙头首次确认日期 |
| `leader_last_confirmed_date` | 龙头最近确认日期 |
| `tracking_age_days` | 跟踪池年龄 |
| `tracking_phase` | `strong_attention` / `golden_second_wave` / `extension` |
| `tracking_reasons` | 跟踪池命中原因 JSON |
| `tracking_risk_flags` | 跟踪池风险提示 JSON |
| `invalid_conditions` | 未入选/失效条件 JSON |

前端展示建议：

- 策略4候选列表新增「来源」列。
- 策略4结果页新增「跟踪池」Tab。
- 候选详情展示「首次热点日期」「最近热点确认」「跟踪天数」「二波阶段」。
- 跟踪池 Tab 支持按状态过滤：全部、二波观察、已失效、已过期。

## 11. 代码修改计划

### 11.1 新增模块

```text
strategy4/tracking_models.py
strategy4/tracking_service.py
strategy4/tracking_rules.py
strategy4/tracking_backtest.py
```

职责：

- `tracking_models.py`：生命周期状态常量和 dataclass。
- `tracking_rules.py`：题材/龙头状态迁移、失效、过期、候选资格判断。
- `tracking_service.py`：扫描时更新 DB 跟踪池、生成候选补充来源。
- `tracking_backtest.py`：历史回测中按日期顺序重放跟踪池，避免污染生产 DB。

### 11.2 修改文件

| 文件 | 修改内容 |
|---|---|
| `strategy4/config.py` | 新增 `tracking` 配置段和校验 |
| `scanner/db.py` | 新增三张跟踪池表、CRUD、兼容迁移 |
| `strategy4/scanner.py` | 即时快照生成后更新跟踪池；候选来源增加 tracking pool |
| `strategy4/backtester.py` | 新增跟踪池历史重放模式；报告区分 current vs tracking |
| `server.py` | 新增跟踪池 API；任务详情可返回新增候选字段 |
| `web/src/pages/Strategy4Results.vue` | 新增跟踪池 Tab 和候选来源展示 |
| `web/src/services/api.js` | 新增跟踪池 API 调用 |
| `tests/test_strategy4_*.py` | 补充配置、DB、扫描、回测、API 测试 |

### 11.3 谨慎处理点

- 不要改策略1/2/3入口。
- 不要把跟踪池候选写入其他策略表。
- 不要删除 `strategy4_candidates` 旧字段。
- 不要让回测的跟踪池写入生产跟踪池表，除非显式使用临时 DB 或任务隔离。
- 不要使用当前实时热点倒推过去日期。

## 12. 回测设计

### 12.1 回测模式

新增「跟踪池回放」：

```text
for evaluation_date in trading_dates:
  derived_topics = derive_hot_topics_for_date(evaluation_date)
  derived_leaders = derive_leaders_for_topic(topic, evaluation_date)
  tracking_pool.update(evaluation_date, derived_topics, derived_leaders)
  tracking_candidates = tracking_pool.evaluate_candidates(evaluation_date)
  calculate NEXT_OPEN outcome
```

要求：

- 所有题材指数和个股 K 线都必须 `date <= evaluation_date`。
- 入场仍然使用 `NEXT_OPEN`。
- 一字板/T字板不可成交规则保持现有口径。
- 报告必须区分即时候选和跟踪池候选。

### 12.2 对比指标

报告至少输出：

- 评估天数
- 入池题材数
- 入池龙头数
- 即时热点机会数
- 跟踪池机会数
- 入场数
- 目标命中
- 止损命中
- 平均收益
- Profit Factor
- 平均盈亏比
- 最大连续亏损
- 月度分布
- 题材集中度
- 跟踪年龄分布：1-20、21-60、61-120

### 12.3 验收底线

跟踪池不是为了机械增加候选。验收应满足：

- 不出现未来数据泄漏。
- 不把过期/失效题材生成候选。
- 跟踪池候选能解释首次热点日期和当前入选原因。
- 新增候选的盈亏比不能明显劣于即时候选。
- 候选数量增加时，最大连续亏损和月度集中度不能明显恶化。

## 13. API 和前端设计

### 13.1 新增 API

建议新增：

```text
GET /api/strategy4/tracking/topics
GET /api/strategy4/tracking/leaders
GET /api/strategy4/tracking/events
GET /api/strategy4/tasks/{task_id}/tracking-candidates
```

参数建议：

- `status`
- `topic_id`
- `code`
- `page`
- `page_size`
- `include_expired`

### 13.2 前端展示

策略4结果页建议 Tab：

1. 二波候选
2. 热点题材
3. 龙头股票
4. 跟踪池
5. 任务日志

跟踪池列表字段：

- 题材/股票
- 首次确认日期
- 最近确认日期
- 跟踪天数
- 生命周期状态
- 当前阶段
- 最新板块阶段
- 回踩幅度
- 盈亏比
- 风险提示

候选列表新增明显标签：

- `当前热点`
- `跟踪池二波`
- `当前热点 + 跟踪池`

## 14. 测试计划

### 14.1 单元测试

新增或扩展：

```text
tests/test_strategy4_tracking_rules.py
tests/test_strategy4_tracking_db.py
tests/test_strategy4_tracking_service.py
tests/test_strategy4_tracking_backtester.py
```

覆盖：

1. `CONFIRMED_HOT` 题材进入跟踪池。
2. `NOISE_TOPIC` 不入池。
3. 已入池题材再次确认会刷新 `last_confirmed_date`。
4. 超过 120 天自动 `EXPIRED`。
5. 题材跌破/高回撤标记 `INVALIDATED`。
6. 龙头进入 `PULLBACK_TRACKING`。
7. 龙头满足二波时进入 `SECOND_WAVE_READY`。
8. 龙头跌破止损标记 `INVALIDATED`。
9. 延长期候选执行更严格盈亏比过滤。
10. 候选去重时保留 `merged_current_and_tracking` 来源。

### 14.2 集成测试

覆盖：

1. 策略4扫描后生成跟踪池记录。
2. 即时热点消失后，未失效跟踪池仍能生成候选。
3. 失效题材不能生成候选。
4. 回测按日期重放跟踪池，不使用未来 K 线。
5. 策略1、策略2、策略3测试不受影响。
6. 老策略4 API 仍能返回旧字段。

### 14.3 前端测试

覆盖：

1. 策略4结果页能展示候选来源标签。
2. 跟踪池 Tab 能加载题材和龙头。
3. 旧任务没有跟踪池字段时页面不报错。
4. 过滤状态切换正常。

### 14.4 推荐验证命令

```bash
python -m pytest tests/test_strategy4_* -q
python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py --ignore=tests/test_yfinance_hist.py
python -m compileall scanner strategy2 strategy3 strategy4 server.py -q
npm --prefix web test -- --run
npm --prefix web run build
```

## 15. 风险点

1. **候选变多但质量下降**：跟踪池会扩大时间维度，必须用失效规则和盈亏比控制。
2. **过期热点继续出候选**：必须强制 `max_calendar_days=120` 和失效状态过滤。
3. **未来数据泄漏**：回测跟踪池必须只读取 `date <= evaluation_date`。
4. **成分股幸存者偏差**：当前历史成员可能是 `current_members_proxy`，报告和前端必须提示。
5. **重复候选**：即时热点和跟踪池可能同时命中，必须按 `task_id + topic_id + code` 去重。
6. **状态迁移不可解释**：必须写 `strategy4_tracking_events`，否则后续很难解释为什么入选或失效。
7. **回测污染生产跟踪池**：回测建议使用内存状态或任务隔离，不要无条件写生产 tracking 表。
8. **策略4参数过拟合**：跟踪池上线后必须先跑对比回测，不直接升级正式默认参数。

## 16. 推荐实施顺序

1. 先补 DB 表和 CRUD，写单元测试。
2. 新增 `tracking_rules.py`，用测试锁定生命周期状态迁移。
3. 新增 `tracking_service.py`，接入扫描但先只写跟踪池，不产出候选。
4. 接入跟踪池候选生成，新增候选来源字段，保持旧字段兼容。
5. 改造回测，增加跟踪池历史重放和对比报告。
6. 增加 API 和前端跟踪池 Tab。
7. 跑专项测试、全量后端测试、前端测试和 build。
8. 用真实本地数据跑一轮策略4回测，生成验收报告。

## 17. Goal 提示语

```text
/goal 按双角色闭环流程开发策略4热点生命周期跟踪池。

开发文档：
D:/game/claude/dry-stable-low-risk-entry-strategy/.claude/worktrees/strategy4-hot-leader-second-wave/docs/superpowers/specs/2026-07-03-strategy4-hot-topic-lifecycle-tracking-pool-design.md

要求：
1. 先阅读 AGENTS.md、CLAUDE.md、上述设计文档，以及策略4当前代码和测试。
2. 基于当前策略4继续增强，不新建独立策略，不修改策略1、策略2、策略3。
3. 新增热点题材和龙头生命周期跟踪池，默认跟踪 120 自然日。
4. 当前 live_external 和 historical_kline_derived 两种来源都可以把题材/龙头加入跟踪池。
5. 策略4扫描时，除了即时热点候选，也要评估未失效的跟踪池题材/龙头，并能生成 tracking_pool 候选。
6. 策略4回测时必须按 evaluation_date 顺序重放跟踪池，所有行业/题材 K 线、成分股、个股 K 线都只能使用 date <= evaluation_date 的数据，禁止未来数据泄漏。
7. 新增字段可以加入 strategy4_candidates，但不得删除、改名旧字段，不得破坏旧 API 和前端旧任务展示。
8. 新增 DB 表必须兼容旧库，使用非破坏性迁移。
9. 前端策略4结果页增加跟踪池 Tab，并在候选列表明显展示候选来源：当前热点、跟踪池二波、当前热点+跟踪池。
10. 回测报告必须区分即时热点机会和跟踪池机会，输出入池题材数、入池龙头数、机会数、入场数、PF、平均收益、平均盈亏比、最大连续亏损、月度分布、题材集中度、跟踪年龄分布。
11. 先写测试再实现，至少覆盖跟踪池入池、刷新、失效、过期、候选生成、去重、回测无未来数据、旧字段兼容。
12. 运行验证命令：
    - python -m pytest tests/test_strategy4_* -q
    - python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py --ignore=tests/test_yfinance_hist.py
    - python -m compileall scanner strategy2 strategy3 strategy4 server.py -q
    - npm --prefix web test -- --run
    - npm --prefix web run build
13. 开发完成后切换为审核专家角色验收，过滤低等级问题，修复所有中高等级问题后再提交。
14. 允许 git add / commit / push；如果 push 失败，如实报告，不要反复重试。

交付标准：
1. 策略4扫描入口和旧输出兼容。
2. 跟踪池能持续跟踪 120 天内未失效热点和龙头。
3. 已失效或过期题材/龙头不会生成候选。
4. 回测无未来数据泄漏。
5. 前端能清楚看出候选来自当前热点还是跟踪池。
6. 有完整测试和真实验证报告。
```

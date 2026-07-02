# 策略4历史K线反推热点与龙头双源融合设计

## 1. 背景

策略4当前定位是「热点龙头二波」：先识别市场热点行业/题材，再识别热点里的龙头，最后判断第一波、回踩、二次启动和收益比。

现有实现已经具备：

- `strategy4/topic_source.py`：通过 AkShare 同花顺行业/概念摘要和成分股接口获取实时热点与成员。
- `strategy4/topic_index_source.py` / `strategy4/topic_index_service.py`：拉取并缓存真实行业/概念指数 K 线。
- `strategy4/topic_index_analyzer.py`：从板块 K 线计算趋势、突破、量能、风险和阶段。
- `strategy4/topic_scoring.py`：在实时摘要评分基础上叠加板块 K 线确认。
- `strategy4/scanner.py`：策略4扫描入口，保存热点、龙头、候选。
- `strategy4/backtester.py`：基于已有热点/龙头快照做历史回放；缺少历史热点快照时标记 `UNOBSERVED_TOPIC_SNAPSHOT`。

当前关键问题是：策略4回测和历史重放仍依赖已经持久化过的历史热点快照。如果某天没有策略4实时扫描快照，即使本地已有行业/概念指数 K 线和成分股个股 K 线，也不能反推那一天哪些板块正在变热、哪些股票是龙头。

这不是个股历史 K 线不足的问题，而是「每日热点/龙头快照」没有被历史化。为解决这个缺口，本设计在保留现有实时外部热点源的前提下，新增一套 `historical_kline_derived` 来源：完全使用 `evaluation_date` 当日及之前的真实行业/概念 K 线、成分股 K 线和本地数据库数据，反推每日热点与龙头，然后与现有实时来源统一融合。

---

## 2. 目标

本次目标是在策略4基础上增强，不新建策略，不替代现有实时热点源。

必须实现：

1. 新增历史 K 线反推热点来源 `historical_kline_derived`。
2. 保留现有实时外部来源 `live_external`。
3. 扫描和回测中两个来源可以同时运行，最终输出统一热点、龙头、候选结构。
4. 历史反推只能使用 `date <= evaluation_date` 的行业/概念 K 线和个股 K 线。
5. 反推热点必须基于真实 `strategy4_topic_index_ohlc`，禁止使用当前摘要、未来数据或个股等权代理伪造板块指数。
6. 反推龙头必须基于题材成分股的真实 `daily_ohlc`。
7. 没有历史成分股版本时，可以使用当前真实成分股列表作为成员 universe，但必须标记 `membership_mode=current_members_proxy`，并在报告和前端提示存在成员幸存者偏差。
8. 融合后不得删除或改名现有策略4旧字段，避免破坏前端和旧任务详情。
9. 不修改策略1、策略2、策略3核心规则。

不做范围：

- 不做机器学习预测。
- 不把策略4结果写入其他策略表。
- 不用当前热点快照倒推过去。
- 不为了回测样本数量伪造热点。
- 不在本阶段升级正式交易参数，参数升级必须基于后续可复现实验报告。

---

## 3. 现状调用链

### 3.1 实时扫描链路

当前策略4扫描链路为：

```text
server.py
  POST /api/strategy4/scans
    -> strategy4.scanner.scan_strategy4_all()
      -> TopicSourceService.fetch_topics()
      -> score_hot_topic(raw_topic)
      -> TopicIndexService.ensure_topic_index_context()
      -> score_hot_topic(raw_topic, topic_index_context)
      -> db.replace_strategy4_hot_topics()
      -> _build_leaders_and_candidates_from_topics()
        -> TopicSourceService.fetch_topic_members()
        -> _load_strategy4_daily_data()
        -> HotLeaderSecondWaveEngine.evaluate_at()
        -> score_leader_candidate()
        -> db.replace_strategy4_leaders()
        -> db.upsert_strategy4_candidate()
```

### 3.2 当前回测链路

当前回测链路为：

```text
strategy4.backtester.run_strategy4_snapshot_backtest()
  -> _snapshot_task_for_exact_date(evaluation_date)
  -> db.get_strategy4_hot_topics(snapshot_task_id)
  -> db.get_strategy4_leaders(snapshot_task_id)
  -> _topic_index_context_for_backtest(topic, evaluation_date)
  -> _evaluate_leader_snapshot()
  -> HotLeaderSecondWaveEngine.evaluate_at()
```

如果某个 `evaluation_date` 没有策略4快照，当前回测会记录：

```text
UNOBSERVED_TOPIC_SNAPSHOT
```

本设计新增的历史反推层要补上这个缺口：当没有已有快照时，用历史可观察的行业/概念 K 线和成分股 K 线生成一个可审计的 derived snapshot。

---

## 4. 新架构

### 4.1 双来源模型

策略4热点和龙头来源统一分为三类：

| 来源 | 含义 | 使用场景 |
|---|---|---|
| `live_external` | 现有 AkShare 同花顺行业/概念摘要、名称、成分股来源 | 实时扫描、当天任务 |
| `historical_kline_derived` | 基于历史行业/概念 K 线和成员股 K 线反推热点/龙头 | 历史回测、补齐无快照日期、实时扫描辅助确认 |
| `merged` | 两个来源统一合并后的最终输出 | 前端、候选、任务详情、回测机会 |

### 4.2 总体数据流

```text
Strategy4 scan/backtest
  -> LiveExternalTopicSource
      -> TopicSourceService.fetch_topics()
      -> TopicSourceService.fetch_topic_members()

  -> HistoricalKlineDerivedTopicSource
      -> TopicIndexHotnessDetector
      -> TopicMemberUniverseProvider
      -> LeaderKlineDetector

  -> TopicSnapshotMerger
  -> LeaderSnapshotMerger
  -> HotLeaderSecondWaveEngine
  -> save unified topics/leaders/candidates
```

### 4.3 推荐新增模块

```text
strategy4/derived_topic_source.py
strategy4/derived_topic_detector.py
strategy4/derived_leader_detector.py
strategy4/topic_member_cache.py
strategy4/snapshot_merge.py
```

职责划分：

- `derived_topic_source.py`：对外提供 `fetch_topics_for_date(evaluation_date)` 和 `fetch_leaders_for_topic(...)`。
- `derived_topic_detector.py`：从 `strategy4_topic_index_ohlc` 计算每日热点候选。
- `derived_leader_detector.py`：从题材成员股 `daily_ohlc` 计算每日龙头候选。
- `topic_member_cache.py`：维护题材成分股缓存和成员 universe。
- `snapshot_merge.py`：合并实时来源和历史反推来源，去重、保留来源证据、输出统一结构。

---

## 5. 历史K线反推热点

### 5.1 输入数据

反推热点只允许读取：

- `strategy4_topic_index_ohlc` 中 `date <= evaluation_date` 的真实行业/概念 K 线。
- `strategy4_topic_index_fetch_status` 中对应拉取审计。
- 题材成员列表缓存，用于后续扩散度和龙头验证。
- 成员股 `daily_ohlc` 中 `date <= evaluation_date` 的历史 K 线。

禁止读取：

- `evaluation_date` 之后的行业/概念 K 线。
- `evaluation_date` 之后的个股 K 线。
- 当前实时热点摘要来代表过去某天热点。
- 当前涨幅榜或当前资金流来补过去的历史快照。

### 5.2 热点指标

对每个题材在 `evaluation_date` 截断窗口内计算：

| 指标 | 说明 |
|---|---|
| `topic_return_1d` | 板块 1 日涨幅 |
| `topic_return_3d` | 板块 3 日涨幅 |
| `topic_return_5d` | 板块 5 日涨幅 |
| `topic_return_10d` | 板块 10 日涨幅 |
| `topic_return_20d` | 板块 20 日涨幅 |
| `topic_return_60d` | 板块 60 日涨幅 |
| `amount_ratio_1_20` | 当日成交额 / 20 日均额 |
| `amount_ratio_5_20` | 5 日均额 / 20 日均额 |
| `new_high_20` | 是否创 20 日新高 |
| `new_high_60` | 是否创 60 日新高 |
| `drawdown_from_high_20` | 距 20 日高点回撤 |
| `topic_index_phase` | `EARLY_ACCELERATION` / `MAIN_TREND` / `PULLBACK_REPAIR` / `HIGH_RISK_CLIMAX` / `WEAK_NOISE` |
| `topic_index_risk_flags` | 放量破位、连续下跌、高位长上影等风险 |

现有 `analyze_topic_index()` 已经覆盖趋势、突破、量能、风险和阶段，第一版应优先复用它，避免在新模块里重复造另一套板块状态判断。

### 5.3 热点评分

历史反推热点评分建议满分 100：

| 维度 | 分值 | 推荐判断 |
|---|---:|---|
| 趋势强度 | 25 | `close > ma20`、`ma20_slope > 0`、`return_20d > 0` |
| 近期加速 | 20 | `return_5d >= 5%` 或 `return_10d >= 8%` |
| 突破新高 | 20 | `new_high_20`、`new_high_60`、接近高点 |
| 量能扩散 | 15 | `amount_ratio_5_20 >= 1.2` 或 `amount_ratio_1_20 >= 1.5` |
| 回撤健康 | 10 | `drawdown_from_high_20 <= 8%` |
| 成分股扩散 | 10 | 成员上涨家数、强势股数量、涨停/接近涨停数量 |

风险扣分：

| 风险 | 扣分 |
|---|---:|
| `close_below_ma20` | -8 |
| `drawdown_from_high_20 > 12%` | -8 |
| 近 5 日连续 3 天下跌 | -5 |
| 放量大阴或长上影冲高回落 | -5 |

推荐状态：

| 状态 | 条件 |
|---|---|
| `CONFIRMED_HOT` | derived score >= 75，且阶段不是 `WEAK_NOISE` / `HIGH_RISK_CLIMAX` |
| `WATCH_HOT` | derived score 60-74，或处于 `PULLBACK_REPAIR` |
| `NOISE_TOPIC` | derived score < 60，或风险信号过重 |
| `UNOBSERVED_TOPIC_INDEX` | 题材 K 线不足或缺失 |

### 5.4 输出结构

`historical_kline_derived` 输出应尽量兼容当前 `score_hot_topic()` 输入：

```python
{
    "topic_id": "concept:机器人概念",
    "topic_name": "机器人概念",
    "topic_type": "concept",
    "source": "historical_kline_derived",
    "snapshot_time": "2026-06-25T15:00:00",
    "return_1d": 0.012,
    "return_3d": 0.035,
    "return_5d": 0.081,
    "amount_ratio": 1.45,
    "net_inflow": None,
    "breadth_ratio": 0.66,
    "leading_stock_code": "000000",
    "leading_stock_name": "示例股票",
    "derived_hot_score": 82.5,
    "topic_index_context": {...},
    "source_modes": ["historical_kline_derived"],
    "membership_mode": "current_members_proxy"
}
```

注意：

- `net_inflow` 在纯 K 线反推中可能不可观察，不能伪造。
- `breadth_ratio` 可以由成分股 K 线计算。
- `membership_mode` 必须写入，不能隐藏成员口径。

---

## 6. 历史K线反推龙头

### 6.1 成分股 universe

优先顺序：

1. 已有历史成员快照：`membership_mode=historical_members_snapshot`。
2. 当前真实成分股缓存：`membership_mode=current_members_proxy`。
3. 外部成员接口失败且无缓存：`membership_mode=unobserved_members`，该题材不能生成正式 derived leader，只能标记不可观察。

第一版如果没有历史成员快照表，可以实现当前成员缓存，但必须：

- 在热点、龙头、回测报告中显示 `current_members_proxy`。
- 不把这类样本标记为高可信基线。
- 后续如果补齐历史成员表，能平滑切换。

建议新增成员缓存表：

```sql
CREATE TABLE IF NOT EXISTS strategy4_topic_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id TEXT NOT NULL,
    topic_name TEXT NOT NULL,
    topic_type TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    source TEXT NOT NULL,
    membership_snapshot_date TEXT NOT NULL,
    membership_mode TEXT NOT NULL,
    raw_snapshot TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

唯一约束：

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_s4_topic_members_unique
ON strategy4_topic_members(topic_id, code, membership_snapshot_date, source);
```

### 6.2 龙头指标

对题材成员股在 `evaluation_date` 前的 K 线计算：

| 指标 | 说明 |
|---|---|
| `stock_return_1d/3d/5d/10d/20d` | 个股周期涨幅 |
| `leader_rs_5d/10d/20d` | 个股涨幅 - 板块涨幅 |
| `amount_rank_in_topic` | 成员股成交额排名 |
| `return_rank_in_topic` | 成员股涨幅排名 |
| `new_high_20` | 是否创 20 日新高 |
| `near_limit_up_count_10d` | 近 10 日涨停或接近涨停次数 |
| `strong_day_count_10d` | 近 10 日强势日数量 |
| `first_wave_return` | 第一波涨幅 |
| `pullback_pct` | 从阶段高点回撤 |
| `second_wave_signal_count` | 二次启动信号数量 |

### 6.3 龙头评分

历史反推龙头评分建议满分 100：

| 维度 | 分值 | 推荐判断 |
|---|---:|---|
| 板块内涨幅排名 | 25 | 1/3/5/10 日涨幅排前列 |
| 相对板块强弱 | 20 | `leader_rs_10d >= 5%`，`leader_rs_20d >= 8%` |
| 成交额承载 | 15 | 题材内成交额排名靠前 |
| 涨停/强阳辨识度 | 15 | 涨停、接近涨停、大阳线、连续强势 |
| 第一波强度 | 15 | 第一波涨幅达标 |
| 二波可交易性 | 10 | 回踩健康、不是极端高潮 |

状态建议：

| 状态 | 条件 |
|---|---|
| `DERIVED_CORE_LEADER` | leader score >= 85 且相对板块强 |
| `DERIVED_BACKUP_LEADER` | leader score 75-84 |
| `DERIVED_NO_BUY_POINT` | 龙头成立但无二波买点 |
| `DERIVED_REJECTED` | 非龙头或数据不足 |

### 6.4 与现有引擎衔接

derived leader 不直接跳过现有交易判断。它只负责生成热点和龙头上下文，最终仍调用：

```text
HotLeaderSecondWaveEngine.evaluate_at()
```

这样可以保留现有第一波、回踩、二波、收益比逻辑，避免新来源绕过策略4主引擎。

---

## 7. 双源融合规则

### 7.1 题材去重键

题材统一键：

```text
topic_key = "{topic_type}:{normalized_topic_name}"
```

第一版同源闭环优先，不强行做复杂跨源别名。需要跨源合并时，只通过别名表或明确映射，不在业务代码里散落硬编码替换。

### 7.2 题材融合

同一题材来自两个来源时：

```python
{
    "snapshot_source": "merged",
    "source_modes": ["live_external", "historical_kline_derived"],
    "live_hot_score": 88.0,
    "derived_hot_score": 82.5,
    "hot_topic_score": 90.0,
    "merge_confidence": "high",
    "merge_reasons": [
        "live_external_confirmed",
        "topic_index_derived_confirmed"
    ],
    "merge_warnings": []
}
```

融合原则：

1. 两源都确认热点：`merge_confidence=high`，保留最高分排序，但展示两源证据。
2. 实时源确认、derived 弱：降级为 `WATCH_HOT` 或保留 `CONFIRMED_HOT` 但加风险提示，不能静默忽略 derived 风险。
3. derived 确认、实时源缺失：允许进入观察和回测候选，但标记 `derived_only`。
4. 两源冲突且 derived 出现 `WEAK_NOISE` / `HIGH_RISK_CLIMAX`：不得直接作为 `BUYABLE_SECOND_WAVE`。
5. 任一来源不可观察：保留可观察来源结果，并在 `merge_warnings` 说明。

### 7.3 龙头融合

同一 `topic_key + code` 来自两个来源时：

- 合并 `leader_strength_score`、`tradability_score`、`leader_type`。
- 保留 `live_leader_score`、`derived_leader_score`。
- 保留 `membership_mode`。
- 保留相对板块强弱和题材 K 线阶段。
- 不重复写入同一个任务同一题材同一股票。

如果 live leader 和 derived leader 不同：

- live leader 保留为外部识别龙头。
- derived leader 保留为 K 线反推龙头。
- 前端以来源标签区分。
- 候选排序以最终交易质量和收益比为准。

### 7.4 候选融合

候选最终仍由 `HotLeaderSecondWaveEngine.evaluate_at()` 决定是否进入 `BUYABLE_SECOND_WAVE`。

要求：

- 不能只因为 derived score 高就绕过二波判断。
- 不能只因为 live source 热就绕过板块 K 线风险。
- 默认 `BUYABLE_SECOND_WAVE` 至少需要一个可观察热点来源确认，且不能有严重 derived 风险。

---

## 8. 数据库和字段设计

### 8.1 新增审计表

建议新增 derived 审计表，便于回测溯源，同时不破坏现有统一输出表：

```sql
CREATE TABLE IF NOT EXISTS strategy4_derived_hot_topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT,
    evaluation_date TEXT NOT NULL,
    topic_id TEXT NOT NULL,
    topic_name TEXT NOT NULL,
    topic_type TEXT NOT NULL,
    source TEXT NOT NULL,
    membership_mode TEXT NOT NULL,
    derived_hot_score REAL NOT NULL,
    status TEXT NOT NULL,
    topic_index_latest_date TEXT,
    topic_index_phase TEXT,
    topic_index_context TEXT,
    breadth_snapshot TEXT,
    reasons TEXT,
    warnings TEXT,
    raw_snapshot TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

```sql
CREATE TABLE IF NOT EXISTS strategy4_derived_leaders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT,
    evaluation_date TEXT NOT NULL,
    topic_id TEXT NOT NULL,
    topic_name TEXT NOT NULL,
    topic_type TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    source TEXT NOT NULL,
    membership_mode TEXT NOT NULL,
    derived_leader_score REAL NOT NULL,
    leader_type TEXT,
    status TEXT NOT NULL,
    leader_rs_5d REAL,
    leader_rs_10d REAL,
    leader_rs_20d REAL,
    return_rank_in_topic INTEGER,
    amount_rank_in_topic INTEGER,
    raw_snapshot TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### 8.2 扩展现有统一输出表

现有 `strategy4_hot_topics`、`strategy4_leaders`、`strategy4_candidates` 保持为前端和 API 的统一输出表。建议新增可空字段：

```text
snapshot_source
source_modes_json
live_hot_score
derived_hot_score
live_leader_score
derived_leader_score
merge_confidence
merge_warnings
membership_mode
derived_evaluation_date
```

迁移要求：

- 只用 `_ensure_column()` 风格新增列。
- 不删除旧字段。
- 旧任务缺失新字段时前端显示 `--` 或 `未观察`。

---

## 9. 扫描流程改造

### 9.1 实时扫描

实时扫描变为：

```text
scan_strategy4_all()
  1. 计算 target_trade_date。
  2. live_external 拉取实时行业/概念摘要。
  3. historical_kline_derived 使用 target_trade_date 反推热点。
  4. merge topics。
  5. 对 merged topics 召回/反推 leaders。
  6. merge leaders。
  7. 对 merged leaders 调用 HotLeaderSecondWaveEngine.evaluate_at()。
  8. 保存 derived 审计表和统一输出表。
  9. 前端展示来源标签与融合置信度。
```

实时扫描注意事项：

- 如果当前时间未到收盘确认时间，derived source 默认使用上一个完整交易日。
- 如果行业/概念 K 线最新日期落后于 target trade date，则 derived source 标记 `stale_topic_index`。
- live source 失败时，不影响 derived source 尝试。
- derived source 失败时，不影响 live source 展示，但候选可信度下降。

### 9.2 任务中心重新扫描

任务中心里的重新扫描必须同样走策略4统一扫描链路，不能只跑 live source。

重新扫描要求：

- 复用当前配置。
- 重新计算 derived source。
- 原任务如为旧版本缺少 derived 字段，不应报错。
- 新任务的任务详情中能看到 `source_modes` 和 `membership_mode`。

---

## 10. 回测流程改造

### 10.1 回测优先级

回测每个 `evaluation_date` 的来源优先级：

1. 如果存在真实历史策略4快照：读取 `live_external` 快照，并同时计算 `historical_kline_derived` 快照，合并后回放。
2. 如果不存在真实历史策略4快照：只使用 `historical_kline_derived` 生成可审计快照。
3. 如果没有题材 K 线或成员 K 线：标记 `UNOBSERVED_TOPIC_SNAPSHOT` 或 `UNOBSERVED_DERIVED_MEMBERS`，不得生成虚假机会。

### 10.2 替换当前不可观察逻辑

当前 `strategy4/backtester.py` 注释和逻辑强调不重构缺失快照。本次开发后应调整为：

```text
Missing live external snapshots are not fatal when historical_kline_derived is enabled.
The backtester may reconstruct derived snapshots only from observable topic index
and member stock OHLC data truncated to evaluation_date.
```

不能改成“任何缺快照都直接乐观生成机会”。缺行业/概念 K 线或成员股 K 线时仍必须不可观察。

### 10.3 回测报告新增字段

报告必须输出：

- `live_snapshot_days`
- `derived_snapshot_days`
- `merged_snapshot_days`
- `unobserved_topic_index_days`
- `unobserved_members_days`
- `current_members_proxy_days`
- `derived_only_opportunities`
- `live_and_derived_confirmed_opportunities`
- 每个机会的 `snapshot_source`、`source_modes`、`membership_mode`

---

## 11. API 和前端展示

### 11.1 API 字段

策略4 topics / leaders / candidates API 新增字段：

```text
snapshotSource
sourceModes
liveHotScore
derivedHotScore
liveLeaderScore
derivedLeaderScore
mergeConfidence
mergeWarnings
membershipMode
derivedEvaluationDate
topicIndexPhase
topicIndexLatestDate
leaderRs5d
leaderRs10d
leaderRs20d
```

字段缺失时必须兼容旧任务。

### 11.2 前端展示

策略4结果页需要在热点和龙头列表中增加简洁来源标签：

- `外部热点`
- `K线反推`
- `双源确认`
- `成员代理`
- `成员历史快照`
- `不可观察`

候选详情需要展示：

- 该候选来自哪些来源。
- 行业/概念 K 线是否确认热点。
- 龙头是否由成员股 K 线反推确认。
- 是否使用 `current_members_proxy`。
- 如果被 derived 风险降级，显示降级原因。

前端原则：

- 不删除现有列。
- 不改变旧任务 URL 上下文。
- 新字段缺失时显示 `--`。
- 用标签和 tooltip 解释，不把列表做得过重。

---

## 12. 配置设计

建议新增配置：

```yaml
strategy4:
  source_modes:
    live_external_enabled: true
    historical_kline_derived_enabled: true
    merge_mode: union_with_confidence

  derived_source:
    enabled: true
    topic_top_n: 20
    max_topics_per_day: 30
    max_leaders_per_topic: 5
    min_topic_hot_score: 60
    min_confirmed_topic_hot_score: 75
    min_topic_index_rows: 60
    min_amount_ratio_5_20: 1.0
    min_breadth_ratio: 0.55
    min_member_count: 5
    allow_current_members_proxy: true
    current_members_proxy_trust_level: experimental

  merge_policy:
    buyable_requires_observed_source: true
    block_buyable_on_derived_weak_noise: true
    block_buyable_on_derived_high_risk_climax: true
    allow_derived_only_watch: true
    allow_derived_only_buyable: true
```

校验要求：

- `topic_top_n > 0`。
- `max_topics_per_day >= topic_top_n`。
- `max_leaders_per_topic > 0`。
- `min_topic_index_rows >= 20`，推荐默认 60。
- `min_breadth_ratio` 在 0 到 1 之间。
- `merge_mode` 第一版只支持 `union_with_confidence`。

---

## 13. 测试计划

### 13.1 单元测试

新增或扩展：

```text
tests/test_strategy4_derived_topic_detector.py
tests/test_strategy4_derived_leader_detector.py
tests/test_strategy4_topic_member_cache.py
tests/test_strategy4_snapshot_merge.py
tests/test_strategy4_backtester.py
```

必须覆盖：

1. 只使用 `date <= evaluation_date` 的题材 K 线。
2. 强趋势、突破、放量的题材可被 derived source 识别为 `CONFIRMED_HOT`。
3. 放量破位、跌破 MA20、高位退潮题材被降级或排除。
4. 成分股扩散度能从成员股 K 线计算。
5. 成员股数据不足时返回 `UNOBSERVED_DERIVED_MEMBERS`。
6. 当前成员代理模式输出 `membership_mode=current_members_proxy`。
7. 龙头相对板块强弱计算正确。
8. live 和 derived 同题材合并不重复。
9. live 强、derived 弱时产生 `merge_warnings`。
10. derived only 时保存 `snapshot_source=historical_kline_derived`。
11. `HotLeaderSecondWaveEngine.evaluate_at()` 仍是最终交易候选判断入口。

### 13.2 数据库测试

必须覆盖：

1. `strategy4_topic_members` 幂等写入。
2. `strategy4_derived_hot_topics` 可按日期、task_id 查询。
3. `strategy4_derived_leaders` 同一题材同一股票不重复。
4. 统一输出表新增字段兼容旧库。
5. `raw_snapshot` 中 date/datetime 可 JSON 序列化。

### 13.3 回测测试

必须覆盖：

1. 无 live 快照但有 topic index + member OHLC 时，可生成 derived snapshot。
2. 无 topic index 时标记 `UNOBSERVED_TOPIC_INDEX`。
3. 无成员列表时标记 `UNOBSERVED_DERIVED_MEMBERS`。
4. 回测不会读取 `evaluation_date` 之后的 K 线。
5. live + derived 双源时合并后只产生一份候选。
6. 回测报告输出 derived 覆盖率、成员代理天数和来源分布。

### 13.4 前端测试

必须覆盖：

1. 策略4结果页显示来源标签。
2. 旧任务缺失新字段时不崩溃。
3. `current_members_proxy` 有明确提示。
4. derived 风险降级原因能展示。
5. 候选详情显示 source modes 和 leader relative strength。

### 13.5 验证命令

后端专项：

```bash
python -m pytest tests/test_strategy4_* -q
python -m compileall scanner strategy4 server.py -q
```

常规回归：

```bash
python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py --ignore=tests/test_yfinance_hist.py
```

前端：

```bash
npm --prefix web test -- --run
npm --prefix web run build
```

真实外部数据源验证只在用户授权时手工运行。

---

## 14. 风险点

### 14.1 成员幸存者偏差

如果没有历史成分股快照，使用当前成分股列表回看过去会产生偏差。

控制方式：

- 必须写入 `membership_mode=current_members_proxy`。
- 报告不能把这类样本标记为完全可信。
- 前端必须提示。
- 后续可以引入历史成员快照表或每日成员缓存来降低偏差。

### 14.2 题材名称映射

同花顺、东方财富、内部 topic_id 名称可能不一致。

控制方式：

- 第一版同源闭环优先。
- 不在业务逻辑里写散落的硬编码映射。
- 需要跨源时通过 alias 表处理。

### 14.3 derived source 过度乐观

纯 K 线反推可能识别“技术走强但市场叙事不强”的板块。

控制方式：

- 保留 live source。
- 前端显示来源。
- `derived_only` 候选单独统计。
- 参数升级报告必须分来源看 PF、机会数和回撤。

### 14.4 性能压力

每日对全部题材和全部成分股计算可能较慢。

控制方式：

- 先根据 topic index K 线筛选 Top N 题材。
- 对 Top N 题材再计算成员股。
- 缓存 topic index context 和成员 universe。
- 控制 `max_topics_per_day`、`max_leaders_per_topic`。

### 14.5 未来函数

这是本功能最高风险点。

硬要求：

- 所有 derived 指标函数必须接收 `evaluation_date`。
- DB 查询必须支持 `end_date=evaluation_date`。
- 单元测试必须构造未来大涨数据，验证不会影响当日判断。

---

## 15. 推荐实施顺序

1. 先补配置解析和字段兼容，不改变现有扫描行为。
2. 新增 `topic_member_cache.py` 和成员缓存表。
3. 新增 `derived_topic_detector.py`，只从 `strategy4_topic_index_ohlc` 反推热点。
4. 新增 `derived_leader_detector.py`，从成员股 `daily_ohlc` 反推龙头。
5. 新增 `snapshot_merge.py`，合并 live 和 derived。
6. 改造 `strategy4/scanner.py`，实时扫描双源融合。
7. 改造 `strategy4/backtester.py`，无 live 快照时使用 derived snapshot。
8. 补充 DB/API/前端字段展示。
9. 跑策略4专项测试和回归测试。
10. 用真实本地数据生成一份 derived 覆盖率和候选差异报告。

---

## 16. 验收标准

完成后必须满足：

1. 策略4实时扫描可以同时使用 `live_external` 和 `historical_kline_derived`。
2. 策略4回测在缺少 live 快照时，可以用历史 K 线生成 derived snapshot。
3. derived snapshot 全部数据均来自 `evaluation_date` 及之前。
4. 缺行业/概念 K 线时明确输出 `UNOBSERVED_TOPIC_INDEX`。
5. 缺成员列表或成员 K 线时明确输出 `UNOBSERVED_DERIVED_MEMBERS`。
6. 使用当前成员代理时明确输出 `membership_mode=current_members_proxy`。
7. 前端能看出候选来自外部热点、K 线反推还是双源确认。
8. 旧策略4任务和旧前端字段兼容。
9. 不影响策略1、策略2、策略3。
10. 回测报告能区分 live only、derived only、merged confirmed 的机会表现。

---

## 17. 给开发AI的执行要求

请严格遵守：

1. 先阅读 `AGENTS.md`、`CLAUDE.md`、策略4原始设计文档、板块 K 线数据层设计文档和本文档。
2. 只增强策略4，不修改策略1、策略2、策略3核心逻辑。
3. 不删除现有 `live_external` 数据源。
4. 不删除或重命名策略4旧字段。
5. 新增 derived source 时必须保证所有指标截断到 `evaluation_date`。
6. 禁止用当前实时热点快照伪造历史热点。
7. 禁止用未来 K 线判断过去热点和龙头。
8. 缺数据必须输出不可观察原因，不得静默生成机会。
9. 当前成员代理必须显式标记 `current_members_proxy`。
10. 先写测试，再接入扫描和回测。
11. 开发后切换为审核角色，重点审查未来函数、成员偏差、双源冲突、旧字段兼容和跨策略隔离。

---

## 18. `/goal` 提示语

```text
/goal 在当前 strategy4 worktree 中开发策略4「历史K线反推热点/龙头 + 现有实时热点源双源融合」：先阅读 AGENTS.md、CLAUDE.md、docs/superpowers/specs/2026-07-01-strategy4-hot-leader-second-wave-design.md、docs/superpowers/specs/2026-07-02-strategy4-topic-index-kline-data-design.md、docs/superpowers/specs/2026-07-02-strategy4-historical-kline-derived-hot-leader-design.md 和当前 strategy4 实现。保留现有 live_external 热点/成分股来源，新增 historical_kline_derived 来源，基于 strategy4_topic_index_ohlc 的真实行业/概念K线和 daily_ohlc 的成分股K线，在 evaluation_date 当日及之前反推每日热点题材和龙头股票；新增成员缓存、derived 热点/龙头检测、双源融合、来源审计字段、回测无快照日期 derived snapshot 生成、API/前端来源标签展示。不得使用未来数据，不得用当前实时摘要伪造历史，不得使用个股等权代理替代真实板块K线；没有历史成员快照时允许 current_members_proxy，但必须在 DB、报告和前端明确标记；缺题材K线或成员K线必须输出 UNOBSERVED_TOPIC_INDEX / UNOBSERVED_DERIVED_MEMBERS。最终候选仍必须经过 HotLeaderSecondWaveEngine.evaluate_at()，不得绕过策略4旧入口；不得修改策略1/2/3核心规则，不得删除策略4旧字段。按 TDD 开发，补齐 tests/test_strategy4_*、回测无未来函数测试、前端展示测试，运行策略4专项、compileall、必要前端测试，最后提交并推送当前分支。
```

# 策略4板块/行业/概念K线数据层增强设计

## 1. 背景与现状

策略4「热点龙头二波」当前已经实现独立扫描、热点题材快照、龙头快照、二波候选、策略4回测框架和真实大盘指数缓存。

但当前策略4仍存在一个关键数据缺口：

- `strategy4/topic_source.py` 主要读取同花顺行业/概念摘要、名称和成分股。
- `strategy4/topic_scoring.py` 主要基于当日摘要字段评分，例如 `return_1d`、`return_3d`、`return_5d`、`amount_ratio`、`net_inflow`、`breadth_ratio`。
- `strategy4/backtester.py` 已在报告中识别 `topic_index_ohlc` 不存在时为 `UNOBSERVED_TOPIC_INDEX`。
- 当前没有真实行业/概念/板块指数历史K线持久化层，不能可靠判断题材本身的趋势、突破、回踩、量能扩散和阶段位置。

这会导致两个问题：

1. 扫描时热点判断偏依赖当日截面快照，无法充分判断板块是否真实走强。
2. 回测时缺少历史板块K线，只能把题材指数标记为不可观察，不能负责任地用参数实验升级正式策略。

因此，本阶段必须为策略4新增真实板块/行业/概念K线数据层。数据必须来自真实外部行情源或本地已持久化缓存，不允许用当前摘要、个股等权代理或未来数据倒推历史。

---

## 2. 开发目标

本次目标是在策略4基础上增强，不新建独立策略。

必须实现：

1. 新增策略4专用板块/行业/概念指数K线数据模型和持久化表。
2. 接入真实同花顺 / 东方财富板块、行业、概念历史K线数据。
3. 支持按题材名称、题材类型、数据源拉取和缓存历史K线。
4. 扫描策略4时，对进入观察池的热点题材补齐最近一段板块K线。
5. 用板块K线增强热点评分、板块趋势阶段判断和龙头相对板块强弱判断。
6. 回测策略4时，只允许使用 `evaluation_date` 当日及之前的板块K线。
7. 缺少板块K线时必须标记 `UNOBSERVED_TOPIC_INDEX`，不得伪造。
8. 前端展示题材K线最新日期、数据源、可观察状态、板块趋势确认结果。
9. 补齐单元测试、数据库测试、扫描集成测试和回测无未来函数测试。

不做范围：

- 不修改策略1、策略2、策略3核心规则。
- 不把策略4候选写入其他策略表。
- 不使用虚拟板块指数、个股等权代理或当前快照倒推历史。
- 不为了提高候选数量放宽策略4核心风控。
- 不做自动交易。

---

## 3. 当前策略4调用链

当前扫描入口：

```text
server.py
  POST /api/strategy4/scans
    -> strategy4.scanner.scan_strategy4_all()
      -> TopicSourceService.fetch_topics()
      -> score_hot_topic()
      -> db.replace_strategy4_hot_topics()
      -> _build_leaders_and_candidates_from_topics()
        -> TopicSourceService.fetch_topic_members()
        -> _load_strategy4_daily_data()
        -> HotLeaderSecondWaveEngine.evaluate_at()
        -> score_leader_candidate()
        -> db.replace_strategy4_leaders()
        -> db.upsert_strategy4_candidate()
```

当前回测入口：

```text
strategy4.backtester.run_strategy4_snapshot_backtest()
  -> _snapshot_task_for_exact_date()
  -> db.get_strategy4_hot_topics()
  -> db.get_strategy4_leaders()
  -> _evaluate_leader_snapshot()
  -> HotLeaderSecondWaveEngine.evaluate_at()
  -> calculate_strategy4_execution_outcome()
```

本次增强后的核心变化：

```text
TopicSourceService.fetch_topics()
  -> TopicIndexKlineService.ensure_topic_index_ohlc()
  -> TopicIndexAnalyzer.analyze()
  -> score_hot_topic(snapshot, config, topic_index_context)
  -> leader relative strength vs real topic index
```

回测必须变为：

```text
run_strategy4_snapshot_backtest()
  -> load topic snapshot
  -> load topic_index_ohlc <= evaluation_date
  -> if missing: UNOBSERVED_TOPIC_INDEX
  -> evaluate topic and leader only with historical observable topic index
```

---

## 4. 数据源设计

### 4.1 数据源优先级

策略4板块K线使用真实数据源，建议优先级：

1. 同花顺板块/行业/概念历史K线。
2. 东方财富板块/行业/概念历史K线。
3. 本地已缓存的 `strategy4_topic_index_ohlc`。

实现要求：

- 先做适配层能力探测，确认当前环境 AkShare 暴露的同花顺和东方财富历史K线接口名称、参数和字段。
- 不要把未经验证的接口调用散落在业务代码中。
- 统一封装到策略4数据源适配层，例如 `strategy4/topic_index_source.py`。
- 同花顺与东方财富字段、单位、代码口径不同，必须分别 normalize。
- 两个来源同时存在时，优先使用配置指定的数据源；默认可按 `ths -> eastmoney -> cache` 兜底。

### 4.2 题材身份映射

题材身份不能只靠名称裸字符串，因为同花顺和东方财富的概念/行业名称可能不同。

建议统一身份：

```text
topic_key = "{topic_type}:{normalized_topic_name}"
```

字段建议：

- `topic_id`：策略4内部题材ID，例如 `concept:机器人概念`。
- `topic_name`：展示名称。
- `topic_type`：`concept` / `industry` / `sector`。
- `source`：`akshare_ths` / `akshare_eastmoney`。
- `source_topic_code`：数据源侧板块代码，可为空。
- `source_topic_name`：数据源侧原始名称。

如果需要跨源映射，新增别名表，不要在业务代码里写死名称替换：

```text
strategy4_topic_aliases
  topic_id
  source
  source_topic_code
  source_topic_name
  alias_name
  confidence
  updated_at
```

第一版可不实现人工维护页面，但数据库设计要允许后续补充。

---

## 5. 数据库设计

### 5.1 新增表：`strategy4_topic_index_ohlc`

建议使用策略4前缀，避免和已有 `market_index_ohlc` 混淆。

```sql
CREATE TABLE IF NOT EXISTS strategy4_topic_index_ohlc (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id TEXT NOT NULL,
    topic_name TEXT NOT NULL,
    topic_type TEXT NOT NULL,
    source TEXT NOT NULL,
    source_topic_code TEXT,
    source_topic_name TEXT,
    date TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL DEFAULT 0,
    amount REAL DEFAULT 0,
    turnover REAL DEFAULT 0,
    change_pct REAL DEFAULT 0,
    fetched_at TEXT NOT NULL,
    data_version TEXT DEFAULT 'v1',
    raw_snapshot TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

索引：

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_s4_topic_index_unique
ON strategy4_topic_index_ohlc(topic_id, source, date);

CREATE INDEX IF NOT EXISTS idx_s4_topic_index_topic_date
ON strategy4_topic_index_ohlc(topic_id, date);

CREATE INDEX IF NOT EXISTS idx_s4_topic_index_source_name
ON strategy4_topic_index_ohlc(source, source_topic_name);
```

### 5.2 新增表：`strategy4_topic_index_fetch_status`

用于审计数据拉取失败、空数据、字段异常。

```sql
CREATE TABLE IF NOT EXISTS strategy4_topic_index_fetch_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id TEXT NOT NULL,
    topic_name TEXT NOT NULL,
    topic_type TEXT NOT NULL,
    source TEXT NOT NULL,
    source_topic_code TEXT,
    source_topic_name TEXT,
    start_date TEXT,
    end_date TEXT,
    status TEXT NOT NULL,
    latest_date TEXT,
    rows_count INTEGER DEFAULT 0,
    error_code TEXT,
    error_message TEXT,
    fetched_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

状态建议：

- `completed`
- `empty`
- `source_failed`
- `normalize_failed`
- `invalid_ohlc`
- `partial`

### 5.3 兼容迁移要求

- 使用 `CREATE TABLE IF NOT EXISTS`。
- 新增列必须用项目现有 `_ensure_column()` 风格。
- 不做破坏性迁移。
- 不删除旧 `strategy4_hot_topics`、`strategy4_leaders`、`strategy4_candidates` 字段。
- 如果需要给旧表补充字段，只能新增可空字段。

建议给 `strategy4_hot_topics` 新增可空字段：

```text
topic_index_source
topic_index_latest_date
topic_index_rows
topic_index_observed
topic_index_status
topic_index_trend_score
topic_index_breakout_score
topic_index_volume_score
topic_index_risk_penalty
topic_index_phase
```

这些字段只是增强展示和解释，不得破坏旧结果读取。

---

## 6. 板块K线标准化规则

### 6.1 输入字段归一

不同数据源字段可能不同，归一后必须至少输出：

```python
{
    "date": "YYYY-MM-DD",
    "open": float,
    "high": float,
    "low": float,
    "close": float,
    "volume": float,
    "amount": float,
    "turnover": float,
    "change_pct": float,
}
```

### 6.2 数据合法性

必须校验：

- `date` 可解析。
- `open/high/low/close` 都大于 0。
- `high >= max(open, close, low)`。
- `low <= min(open, close, high)`。
- 同一题材同一来源同一天只保留一条。
- 日期升序入库。

发现非法K线时：

- 不写入非法行。
- 写入 `strategy4_topic_index_fetch_status.status='invalid_ohlc'`。
- 保留错误原因。
- 扫描中该题材的 `topic_index_status` 标记为不可用或部分可用。

### 6.3 日期和未来函数

扫描：

- 默认拉取最近 120 到 250 个交易日。
- 判断最新数据是否覆盖最近一个完整交易日时，复用项目已有交易日新鲜度思路。

回测：

- 任何指标只能使用 `date <= evaluation_date` 的板块K线。
- 不允许用 `evaluation_date` 之后的K线计算均线、突破、新高、成交额放大。
- 若 `evaluation_date` 当天板块K线缺失，但前一完整交易日存在，可按配置决定是否降级为 `stale_topic_index`；默认回测应标记为 `UNOBSERVED_TOPIC_INDEX`，避免乐观偏差。

---

## 7. 板块K线指标设计

### 7.1 趋势强度

建议计算：

- `topic_return_1d`
- `topic_return_3d`
- `topic_return_5d`
- `topic_return_10d`
- `topic_return_20d`
- `topic_return_60d`
- `ma5`
- `ma10`
- `ma20`
- `ma60`
- `ma20_slope`
- `ma60_slope`
- `above_ma5`
- `above_ma10`
- `above_ma20`
- `above_ma60`

推荐判断：

- 强势启动：`return_5d >= 5%` 且 `close > ma10`。
- 主升趋势：`close > ma20` 且 `ma20_slope > 0`。
- 中期偏强：`return_60d > 0` 且 `close > ma60`。

### 7.2 突破和新高

建议计算：

- `new_high_20`
- `new_high_60`
- `breakout_20`
- `distance_to_high_20`
- `distance_to_high_60`
- `drawdown_from_high_20`
- `drawdown_from_high_60`

推荐判断：

- `breakout_20=true`：收盘价突破过去20日最高收盘或最高价。
- `new_high_60=true`：创60日新高，说明不是短暂反抽。
- `drawdown_from_high_20 <= 8%`：热点未明显退潮。

### 7.3 量能扩散

建议计算：

- `amount_ratio_5_20`
- `amount_ratio_1_20`
- `amount_ma5`
- `amount_ma20`
- `volume_ratio_5_20`

推荐判断：

- `amount_ratio_5_20 >= 1.3`：板块量能有效放大。
- `amount_ratio_1_20 >= 1.5`：当日明显增量。
- 涨停锁仓场景下，若板块涨幅强、宽度强，但个别龙头缩量，不应扣板块热度。

### 7.4 风险和退潮

建议计算：

- `range_5`
- `upper_shadow_ratio`
- `down_days_5`
- `large_down_day_count_5`
- `close_below_ma10`
- `close_below_ma20`
- `volume_down_break`

风险信号：

- 放量跌破MA10或MA20。
- 近5日连续下跌超过3天。
- 高位长上影并放量。
- 板块指数从20日高点回撤超过12%。
- 龙头仍强但板块已经退潮，候选应降级为观察。

### 7.5 板块阶段分类

建议输出：

```text
EARLY_ACCELERATION      初期加速
MAIN_TREND              主升趋势
PULLBACK_REPAIR         热点回踩修复
HIGH_RISK_CLIMAX        高潮高风险
WEAK_NOISE              弱噪音
UNOBSERVED_TOPIC_INDEX  板块K线不可观察
```

---

## 8. 热点评分增强方案

当前 `hot_topic_score` 由摘要快照计算，建议保留旧分数，并新增板块K线确认层。

### 8.1 新增评分项

建议新增：

| 字段 | 分值 | 含义 |
|---|---:|---|
| `topic_index_trend_score` | 0-20 | 板块趋势强度 |
| `topic_index_breakout_score` | 0-15 | 突破、新高、接近前高 |
| `topic_index_volume_score` | 0-15 | 板块量能放大 |
| `topic_index_risk_penalty` | 0 到 -20 | 退潮信号扣分 |

第一版可以不改变旧 `hot_topic_score` 满分结构，采用增强上下文：

```text
enhanced_hot_topic_score = old_hot_topic_score
                         + topic_index_confirm_bonus
                         - topic_index_risk_penalty
```

为了兼容旧前端：

- `hot_topic_score` 可以继续保存最终用于排序的分数。
- `raw_snapshot` 中保留 `legacy_hot_topic_score`。
- 新增字段保存板块K线分项。

### 8.2 入选规则

推荐：

- `CONFIRMED_HOT`：旧摘要强信号达标，且板块K线不是 `WEAK_NOISE` 或 `HIGH_RISK_CLIMAX`。
- `LOCKED_HOT_TOPIC`：存在锁仓龙头，且板块K线趋势未破坏。
- `WATCH_HOT`：摘要强但板块K线不足，或板块处于回踩修复。
- `NOISE_TOPIC`：摘要信号少，或板块K线弱、退潮、放量破位。
- `UNOBSERVED_TOPIC_INDEX`：板块K线缺失，不直接作为买入依据，可进入观察或降级。

### 8.3 风控原则

不能因为板块K线缺失就假设热点成立。

建议默认：

- 实时扫描：板块K线缺失时可展示 `WATCH_HOT`，但不进入 `BUYABLE_SECOND_WAVE`，除非配置开启 `allow_unobserved_topic_index_for_live_scan`。
- 回测：板块K线缺失必须记录 `UNOBSERVED_TOPIC_INDEX`，不参与正式参数证明。

---

## 9. 龙头相对板块强弱增强

当前龙头强弱里的 `relative_strength_vs_topic` 主要来自摘要里的 `topic_return_1d`。

增强后应使用真实板块K线：

```text
leader_rs_5  = stock_return_5d  - topic_return_5d
leader_rs_10 = stock_return_10d - topic_return_10d
leader_rs_20 = stock_return_20d - topic_return_20d
```

建议规则：

- 龙头一波阶段：`leader_rs_10 >= 8%` 或 `leader_rs_20 >= 12%`。
- 回踩阶段：个股回踩时，板块不能同步放量破位。
- 二波阶段：个股二波启动时，板块至少处于 `MAIN_TREND` / `PULLBACK_REPAIR` / `EARLY_ACCELERATION`，不能是 `WEAK_NOISE`。
- 如果板块创新高但龙头不跟，龙头降级为观察。
- 如果龙头强但板块退潮，二波候选降级为 `HOT_TOPIC_NO_BUY_POINT`。

输出建议新增到 `strategy4_leaders.raw_snapshot` 或字段：

- `topic_return_5d`
- `topic_return_10d`
- `topic_return_20d`
- `leader_rs_5d`
- `leader_rs_10d`
- `leader_rs_20d`
- `topic_index_phase`
- `topic_index_risk_flags`

---

## 10. 扫描流程改造

### 10.1 新增服务

建议新增模块：

```text
strategy4/topic_index_source.py
strategy4/topic_index_analyzer.py
strategy4/topic_index_service.py
```

职责：

- `topic_index_source.py`：调用同花顺 / 东方财富历史K线接口并 normalize。
- `topic_index_service.py`：缓存命中判断、拉取、入库、失败审计。
- `topic_index_analyzer.py`：计算趋势、突破、量能、风险、阶段。

### 10.2 新扫描流程

```text
scan_strategy4_all()
  1. 拉取题材摘要。
  2. 先用摘要召回 watch_hot_topic_top_n。
  3. 对观察池题材逐个 ensure topic index K线。
  4. 计算 topic_index_context。
  5. score_hot_topic(snapshot, cfg, topic_index_context)。
  6. 保存热点题材快照，包含板块K线状态。
  7. 召回题材成分股和龙头。
  8. 拉取龙头个股日线。
  9. 使用真实 topic_index_context 计算龙头相对板块强弱。
  10. 执行第一波、回踩、二波、收益比判断。
  11. 保存龙头和候选。
```

### 10.3 失败降级

单个题材板块K线拉取失败：

- 不影响其他题材扫描。
- `strategy4_topic_index_fetch_status` 记录失败。
- 该题材 `topic_index_observed=false`。
- 若旧摘要分足够强，可进入 `WATCH_HOT`，但默认不进入正式二波候选。

所有题材板块K线拉取失败：

- 扫描任务仍可完成热点摘要和龙头观察。
- 任务 stats 中增加 `topic_index_failed_count`。
- 前端明确展示“板块K线不可观察，本次策略4候选可信度下降”。

---

## 11. 回测流程改造

### 11.1 核心原则

策略4回测必须是可观察历史回放：

- 使用历史策略4热点快照。
- 使用 `daily_ohlc` 个股历史日线。
- 使用 `market_index_ohlc` 大盘指数历史日线。
- 使用 `strategy4_topic_index_ohlc` 题材指数历史日线。
- 所有数据必须截断到 `evaluation_date`。

### 11.2 不可观察处理

当某个回测日存在热点快照，但对应题材没有历史K线：

```text
reason_code = UNOBSERVED_TOPIC_INDEX
```

回测报告必须输出：

- 不可观察题材数。
- 不可观察日期数。
- 题材K线覆盖率。
- 使用的 topic index source。
- 每个机会的 `topic_index_latest_date`。

### 11.3 参数实验要求

新增实验维度：

- `min_topic_index_trend_score`
- `min_topic_index_breakout_score`
- `min_topic_amount_ratio_5_20`
- `max_topic_drawdown_from_high_20`
- `allow_topic_phase`
- `min_leader_rs_10d`
- `min_leader_rs_20d`

但第一版正式参数升级必须谨慎：

- 数据覆盖不足时，只能输出观察结论。
- 不允许用单日热点快照升级生产参数。
- 不允许用当前板块数据倒推过去。

---

## 12. API 和前端展示

### 12.1 新增后端接口

建议新增：

```http
GET /api/strategy4/topics/{topicId}/index-ohlc
GET /api/strategy4/tasks/{taskId}/topics/{topicId}/index-context
```

如果暂不新增接口，也至少应在现有 topics API 中返回：

- `topic_index_source`
- `topic_index_latest_date`
- `topic_index_rows`
- `topic_index_observed`
- `topic_index_status`
- `topic_index_phase`
- `topic_index_trend_score`
- `topic_index_breakout_score`
- `topic_index_volume_score`
- `topic_index_risk_penalty`

### 12.2 前端展示

策略4结果页热点题材榜新增简洁字段：

- 板块K线：`已观察 / 不可观察 / 拉取失败 / 数据过旧`
- 最新K线日期
- 数据源：同花顺 / 东方财富
- 板块阶段
- 趋势分
- 突破分
- 量能分
- 风险提示

候选详情新增：

- 板块近5日、10日、20日涨幅。
- 龙头相对板块强弱。
- 板块阶段。
- 板块风险信号。
- 为什么该热点支持或不支持二波买点。

前端原则：

- 不删除旧字段。
- 不改变旧候选列表核心展示。
- 新字段缺失时显示“未观察”，不能报错。

---

## 13. 配置设计

新增配置建议：

```yaml
strategy4:
  topic_index:
    enabled: true
    preferred_sources: ["akshare_ths", "akshare_eastmoney"]
    history_days: 250
    min_required_rows: 60
    live_cache_ttl_minutes: 30
    after_close_cache_ttl_hours: 24
    require_for_buyable_candidate: true
    allow_unobserved_for_watch: true
    max_fetch_topics_per_scan: 30
    source_retry_attempts: 2
  topic_index_filters:
    min_trend_score: 8
    min_breakout_score: 0
    min_amount_ratio_5_20: 1.0
    max_drawdown_from_high_20: 0.12
    allowed_phases:
      - EARLY_ACCELERATION
      - MAIN_TREND
      - PULLBACK_REPAIR
  leader_relative_strength:
    min_rs_10d: 0.05
    min_rs_20d: 0.08
```

校验要求：

- 数字范围必须校验。
- `history_days >= min_required_rows`。
- `preferred_sources` 只能包含已实现 source。
- `require_for_buyable_candidate` 默认 true。

---

## 14. 测试计划

### 14.1 单元测试

新增或扩展：

```text
tests/test_strategy4_topic_index_source.py
tests/test_strategy4_topic_index_db.py
tests/test_strategy4_topic_index_analyzer.py
tests/test_strategy4_backtester.py
tests/test_strategy4_db_api.py
tests/test_strategy4_validation.py
```

必须覆盖：

1. 同花顺字段 normalize。
2. 东方财富字段 normalize。
3. 非法OHLC被拒绝并记录状态。
4. `save/get_strategy4_topic_index_ohlc` 往返。
5. 同一题材同一来源同一天幂等覆盖。
6. 指标计算只使用传入窗口。
7. `UNOBSERVED_TOPIC_INDEX` 不会被当成有效热点确认。
8. 回测只读取 `date <= evaluation_date`。
9. 龙头相对板块强弱计算正确。
10. 策略1、策略2、策略3隔离测试继续通过。

### 14.2 集成测试

必须覆盖：

1. Mock 题材摘要 + Mock 题材K线 + Mock 成分股，策略4扫描能保存热点、龙头、候选。
2. 单个题材K线源失败，不影响其他题材。
3. 全部题材K线源失败，任务给出明确统计和前端可展示状态。
4. 历史回测中缺失题材K线时标记 `UNOBSERVED_TOPIC_INDEX`。
5. 历史回测中未来题材K线不会进入指标。

### 14.3 前端测试

必须覆盖：

1. 策略4结果页能展示板块K线状态。
2. 新字段缺失时不崩溃。
3. 题材K线失败时展示错误或不可观察。
4. 候选详情显示板块阶段和相对强弱。

### 14.4 验证命令

后端专项：

```bash
python -m pytest tests/test_strategy4_* -q
python -m compileall scanner strategy4 server.py -q
```

全量常规：

```bash
python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py --ignore=tests/test_yfinance_hist.py
```

前端：

```bash
npm --prefix web test -- --run
npm --prefix web run build
```

外部真实数据源验证仅手工运行，不纳入常规CI：

```bash
python -m pytest tests/test_strategy4_topic_index_source.py -v -m external
```

---

## 15. 实施步骤

### Phase 1：数据源能力探测和接口封装

1. 检查当前 AkShare 版本可用的同花顺 / 东方财富板块历史K线接口。
2. 封装 `TopicIndexSource`，统一返回标准K线。
3. 为 source normalize 写 mock 单元测试。

完成标准：

- 不依赖业务扫描即可独立拉取并 normalize 板块K线。
- 接口失败有明确错误码。

### Phase 2：数据库和缓存

1. 新增 `strategy4_topic_index_ohlc`。
2. 新增 `strategy4_topic_index_fetch_status`。
3. 新增保存、查询、覆盖、按日期截断读取函数。
4. 补齐数据库往返测试。

完成标准：

- 同一题材同一来源同一天幂等。
- 查询支持 `end_date` 和 `max_rows`。

### Phase 3：板块K线指标和阶段判断

1. 新增 `TopicIndexAnalyzer`。
2. 计算趋势、突破、量能、风险、阶段。
3. 单元测试覆盖强趋势、突破、退潮、不可观察。

完成标准：

- 输入历史K线，输出稳定的 context dict。
- 数据不足时输出 `INSUFFICIENT_TOPIC_INDEX_ROWS`。

### Phase 4：扫描集成

1. 在题材摘要召回后补齐题材K线。
2. `score_hot_topic()` 支持可选 `topic_index_context`。
3. 保存热点题材时写入板块K线状态和分项。
4. 龙头评分使用真实板块收益计算相对强弱。
5. `BUYABLE_SECOND_WAVE` 默认要求板块K线可观察且阶段不弱。

完成标准：

- 策略4扫描结果能说明每个热点的板块K线来源、最新日期、阶段。
- 缺失板块K线不会静默生成可买候选。

### Phase 5：回测集成

1. 回测按 `evaluation_date` 读取题材K线。
2. 缺失时记录 `UNOBSERVED_TOPIC_INDEX`。
3. 报告输出覆盖率和不可观察统计。
4. 参数实验可加入板块趋势过滤。

完成标准：

- 回测不再使用当前题材摘要倒推历史。
- 有真实题材K线时可以验证板块趋势过滤效果。

### Phase 6：前端展示

1. 策略4热点榜展示板块K线状态。
2. 候选详情展示板块阶段和龙头相对板块强弱。
3. 配置页展示 topic index 配置。

完成标准：

- 用户能一眼看出策略4是否真的使用了板块K线。
- 数据不可观察时页面明确提示。

---

## 16. 验收标准

必须满足：

1. `strategy4_topic_index_ohlc` 有真实板块/行业/概念K线数据。
2. 策略4扫描会为观察池题材拉取或复用板块K线。
3. 策略4热点评分能使用板块趋势、突破、量能和风险信息。
4. 龙头相对板块强弱使用真实板块K线计算。
5. 回测只使用 `evaluation_date` 及之前的板块K线。
6. 缺失板块K线时明确输出 `UNOBSERVED_TOPIC_INDEX`。
7. 前端能展示板块K线状态和最新日期。
8. 策略1、策略2、策略3测试不受影响。
9. 不再出现“topic_index_ohlc 0 行但仍升级正式参数”的情况。

---

## 17. 风险点

### 17.1 数据源字段和接口不稳定

同花顺 / 东方财富接口字段可能随 AkShare 版本变化。

要求：

- source 层集中适配。
- 单元测试用固定 mock 行覆盖 normalize。
- 真实数据源测试只手工运行。

### 17.2 题材名称跨源不一致

同一题材在不同源名称可能不同。

要求：

- 第一版不要强行跨源合并。
- 优先同源闭环：同花顺摘要配同花顺K线，东方财富摘要配东方财富K线。
- 后续再通过 alias 表做跨源合并。

### 17.3 数据缺失导致候选骤减

如果强制要求板块K线可观察，候选可能减少。

要求：

- 实时扫描允许观察态展示。
- 正式买入候选默认要求板块K线可观察。
- 前端要解释“不可观察所以降级”，不是静默消失。

### 17.4 回测样本不足

历史热点快照仍可能不足。

要求：

- 报告必须区分“没有历史题材快照”和“没有题材K线”。
- 不允许用样本不足的结果升级正式参数。

### 17.5 过拟合风险

板块K线指标增加后，参数空间变大。

要求：

- 先固定少量核心阈值。
- 参数实验必须输出机会数、PF、平均盈亏比、月度分布、不可观察率。
- 数据不足时只输出观察结论。

---

## 18. 给修复/开发AI的执行要求

请严格遵守：

1. 先阅读 `AGENTS.md`、`CLAUDE.md`、策略4原始设计文档和本文档。
2. 只增强策略4，不修改策略1、策略2、策略3核心策略规则。
3. 先写测试，再实现数据源、数据库、指标、扫描、回测、前端。
4. 板块K线必须来自真实同花顺 / 东方财富数据源或本地缓存。
5. 禁止使用当前摘要、个股等权代理或未来数据倒推历史板块K线。
6. 缺失数据必须明确标记 `UNOBSERVED_TOPIC_INDEX`。
7. 所有回测指标必须截断到 `evaluation_date`。
8. 新增字段必须兼容旧策略4结果。
9. 不得把策略4结果写入策略1、策略2、策略3表。
10. 开发完成后以审核专家角色检查数据真实性、未来函数、跨策略隔离和前端可解释性。

---

## 19. 推荐 /goal 提示语

```text
/goal 在当前 strategy4 worktree 中开发策略4「热点龙头二波」板块/行业/概念K线数据层增强：先阅读 AGENTS.md、CLAUDE.md、docs/superpowers/specs/2026-07-01-strategy4-hot-leader-second-wave-design.md、docs/superpowers/specs/2026-07-02-strategy4-topic-index-kline-data-design.md 和当前 strategy4 实现；实现真实同花顺/东方财富行业、概念、板块指数K线数据接入、标准化、持久化、缓存、失败审计、热点K线指标分析、策略4热点评分增强、龙头相对板块强弱判断、策略4回测无未来函数使用 topic index K线；缺失数据必须标记 UNOBSERVED_TOPIC_INDEX，不得伪造或用当前数据倒推历史；不得修改策略1/2/3核心规则，不得破坏策略4旧字段兼容；完成后补齐后端、前端、回测测试，运行策略4专项和本地回归，提交并推送当前分支。
```

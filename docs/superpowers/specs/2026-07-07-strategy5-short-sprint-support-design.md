# 策略5短线强势冲刺股盘整支撑策略设计

> 来源：整理自外部文档 `C:/Users/pp/Desktop/开发文档.md`。
> 当前阶段：只整理设计文档，不修改策略代码。
> 关键原则：保留本项目原有数据获取方式，不引入 westock-data、westock-mcp、外部 JSON 文件流水线；策略判断逻辑按本文档落地。

参考实现代码已阅读：

- `C:/Users/pp/WorkBuddy/2026-07-05-13-16-53/analyze.py`
- `C:/Users/pp/WorkBuddy/2026-07-05-13-16-53/score_report.py`
- `C:/Users/pp/WorkBuddy/2026-07-05-13-16-53/save_candidates.py`

口径确认：

- 策略判断以 `analyze.py` 为准。
- `score_report.py` 只负责评分和报告，其中 HTML 的筛选条件说明存在简化描述，不能作为策略阈值来源。
- `save_candidates.py` 是静态候选池写盘脚本，不能迁入本项目作为正式数据获取方式。

## 1. 目标

策略5定位为“短线强势冲刺股 · 盘整支撑策略”，用于筛选已经具备短线强度、靠近阶段新高、经过短期盘整，并且仍贴近 MA5/MA10/MA20/MA50 支撑的股票。

策略目标不是寻找低位启动股，也不是策略4的热点龙头二波，而是从全市场或本地股票池中找出：

- 中长期趋势向上；
- 近期有短线强度或单日异动；
- 近 20 日接近或创 120 日高点；
- 盘整不过度失控；
- 当前价格仍贴近均线支撑；
- 具备“重点候选 / 观察候选 / 排除”的明确分层。

## 2. 数据获取方式

### 2.1 原外部文档的数据方式

外部文档原始实现采用三段式文件流水线：

1. 使用 `westock-mcp tool_filter` 粗筛候选池；
2. 使用 `westock-data node` 脚本逐股拉取 K 线；
3. 使用 `filter_candidates.json`、`screening_results.json`、Excel/HTML 文件传递和展示结果。

这些数据获取方式只作为原始策略背景，不应直接迁入本项目。

参考实现中 `analyze.py` 通过 `node index.js kline <code> --period day --limit 1100 --raw` 拉取 K 线，并假设接口返回最新在前，随后反转为时间升序。项目实现时应直接读取本项目统一日线结构，保持输入为时间升序：`data[0]` 最早，`data[-1]` 为评估日。

### 2.2 本项目必须保留的数据方式

策略5在本项目中应沿用现有扫描体系：

- 股票池：复用 `scanner.stock_pool.get_a_stock_pool(config)`。
- 日线数据：复用 `scanner.daily_data_service.fetch_with_retry()`。
- 生产日线源：继续使用 `baidu`、`sina`、`tencent`，不得重新引入 `yfinance` 或 westock。
- 本地缓存：复用 `scanner.db.get_ohlc()` / `scanner.db.save_ohlc()`。
- 数据新鲜度：复用 `build_cache_freshness_context()`，按最近一个完整交易日判断缓存是否可用。
- 数据源锁：复用 `scanner.data_source.DataSourceManager`，避免同一数据源并发冲突。
- 失败处理：三源全部失败时，股票进入失败列表；不得用旧缓存产出新扫描结果。
- 回测：默认只读本地 `daily_ohlc` 和 `stock_pool`，不得调用外部行情源。

也就是说，策略5只新增策略判断、持久化、API、前端展示和测试，不新增独立行情获取链路。

字段映射要求：

| 原参考实现字段 | 本项目日线字段 | 说明 |
|---|---|---|
| `last` | `close` | 收盘价 |
| `high` | `high` | 最高价 |
| `low` | `low` | 最低价 |
| `volume` | `volume` | 成交量 |
| `amount` | `turnover` 或 `amount` | 成交额，优先使用 `turnover`，无则兼容 `amount` |
| `date` | `date` | 交易日期 |

不得为了适配策略5修改共享数据服务返回字段。字段兼容应在策略5指标层完成。

## 3. 策略5候选池粗筛

外部文档的候选池粗筛表达式为：

- `ClosePrice > MA250`
- `MA120 > MA250`
- `TurnoverValue > 20亿`
- 市场范围为沪深。

在本项目中不使用 MCP 粗筛文件。建议实现为策略5扫描过程中的本地预过滤：

1. 先从 `get_a_stock_pool(config)` 获取全市场股票池；
2. 对每只股票用本项目数据源获取日线；
3. 在策略5引擎内部或扫描器内执行等价粗筛；
4. 粗筛失败股票记录为 `scanned/skipped`，并写入稳定 `status_reason`。

粗筛和精筛的成交额阈值不同是正常的：

- 粗筛：最近可用成交额或候选表达式口径 `> 20亿`；
- 精筛：60/30/10 日均成交额分别使用 F5-F7。

## 4. 策略5核心数据窗口

策略5需要至少 500 个交易日用于长期历史过滤，同时至少 250 根 K 线用于 MA250。

建议参数：

| 参数 | 推荐默认值 | 说明 |
|---|---:|---|
| `kline_days` | 1100 | 原外部文档取最近 1100 根日线 |
| `minimum_kline_days` | 260 | 少于 260 无法稳定计算 MA250，直接数据不足 |
| `minimum_trading_days` | 500 | F1，上市/交易天数过滤 |
| `ma_periods` | 5/10/20/50/100/120/250 | 均线集合 |

如果项目当前全市场扫描默认只拉取 350/500 根 K 线，策略5需要独立配置更长的 `kline_days`，但仍通过 `fetch_with_retry(kline_days=...)` 获取，不另建数据源。

## 5. 硬过滤 F1-F11

任一硬过滤失败，股票不进入候选结果。建议每个失败原因使用稳定英文码，便于前端展示和回测漏斗统计。

| 编号 | 条件 | 阈值 | 建议失败码 |
|---|---|---:|---|
| F1 | 交易天数 | `trading_days >= 500` | `TRADING_DAYS_LT_500` |
| F2 | 均线可计算 | MA5/10/20/50/100/120/250 全部可算 | `MA_CALC_FAILED` |
| F3 | 年线之上 | `close > MA250` | `CLOSE_LE_MA250` |
| F4 | 长趋势 | `MA120 > MA250` | `MA120_LE_MA250` |
| F5 | 60 日均额 | `avg_amount_60d > 20亿` | `AVG60D_LE_20YI` |
| F6 | 30 日均额 | `avg_amount_30d > 15亿` | `AVG30D_LE_15YI` |
| F7 | 10 日均额 | `avg_amount_10d > 10亿` | `AVG10D_LE_10YI` |
| F8 | 短线强度 | 见第 6 节 | `SHORT_TERM_STRENGTH_FAILED` |
| F9 | 新高确认 | 见第 7 节 | `NEW_HIGH_FAILED` |
| F10 | 盘整期 | 见第 8 节 | 见第 8 节 |
| F11 | 中期支撑 | `close >= MA50 * 0.92` | `CLOSE_LT_MA50_0_92` |

成交额统一使用日线中的 `turnover` 字段；若数据源字段为 `amount`，应在数据适配层或策略5指标计算中统一兼容，但不得改变共享日线服务的字段语义。

## 6. F8 短线强度

满足任意一条即通过。无论是否通过，都应输出 `recent_5d_return`、`recent_10d_return`、`recent_20d_return` 和 `strength_trigger`。

| 条件 | 阈值 | `strength_trigger` |
|---|---:|---|
| 20 日涨幅 | `ret_20d >= 0.20` | `ret_20d` |
| 10 日涨幅 | `ret_10d >= 0.12` | `ret_10d` |
| 5 日涨幅 | `ret_5d >= 0.08` | `ret_5d` |
| 单日异动 | 近 20 日存在单日涨幅 `>= 0.07` 且成交量 `>= V20 * 1.8` | `single_day_surge` |

计算口径：

- `ret_n = (close[-1] - close[-(n+1)]) / close[-(n+1)]`
- `V20 = mean(volume[-20:])`

## 7. F9 新高确认

满足任意一条即通过。

| 条件 | 阈值 | `high_trigger` |
|---|---:|---|
| 接近 120 日高点 | `max(close[-20:]) >= max(close[-120:]) * 0.98` | `near_120d_high` |
| 创 120 日新高 | `max(close[-20:]) >= max(close[-120:])` | `new_120d_high` |

应输出：

- `near_120d_high_ratio = max(close[-20:]) / max(close[-120:])`
- `close_20d_high`
- `close_120d_high`
- `high_trigger`

参考实现 `analyze.py` 内部会计算 `high_trigger`，但最终 `result` 未持久化该字段。项目实现时建议补充输出 `high_trigger`，用于前端解释和回测审计。

## 8. F10 盘整期

设计原则：极端失控直接淘汰，中间风险区间只打标签。

### 8.1 直接淘汰条件

| 指标 | 计算 | 失败阈值 | 建议失败码 |
|---|---|---:|---|
| 5 日振幅 | `(max(high[-5:]) - min(low[-5:])) / close[-6]` | `> 0.22` | `AMP5D_GT_22PCT` |
| 10 日振幅 | `(max(high[-10:]) - min(low[-10:])) / close[-11]` | `> 0.45` | `AMP10D_GT_45PCT` |
| 20 日回撤 | `(close[-1] - max(close[-20:])) / max(close[-20:])` | `< -0.30` | `DRAWDOWN_GT_30PCT` |
| 5 日最大单日跌幅 | `min(recent_5_daily_returns)` | `< -0.08` | `MAX_DECLINE_LT_NEG8PCT` |
| 放量下跌 | 近 5 日存在日收益 `<= -0.07` 且成交量 `>= V20 * 1.5` | 命中即淘汰 | `CONSOLIDATION_VOLUME_UP_DECLINE` |

### 8.2 风险标签

这些标签不直接淘汰，只用于展示、评分和分类辅助。

| 标签字段 | 条件 | 标签 |
|---|---|---|
| `range_5_tag` | `amp_5d <= 0.12` | `LOW_5D_VOLATILITY` |
| `range_5_tag` | `0.12 < amp_5d <= 0.18` | `HIGH_5D_VOLATILITY` |
| `range_5_tag` | `0.18 < amp_5d <= 0.22` | `EXTREME_5D_VOLATILITY_OBSERVE` |
| `range_10_tag` | `amp_10d <= 0.25` | `NORMAL_10D_CONSOLIDATION` |
| `range_10_tag` | `0.25 < amp_10d <= 0.35` | `HIGH_10D_VOLATILITY` |
| `range_10_tag` | `0.35 < amp_10d <= 0.45` | `EXTREME_10D_VOLATILITY_OBSERVE` |
| `pullback_tag` | `drawdown_20d >= -0.10` | `STRONG_NEAR_HIGH` |
| `pullback_tag` | `-0.15 <= drawdown_20d < -0.10` | `HEALTHY_PULLBACK` |
| `pullback_tag` | `-0.22 <= drawdown_20d < -0.15` | `DEEP_PULLBACK` |
| `pullback_tag` | `-0.30 <= drawdown_20d < -0.22` | `EXTREME_PULLBACK_OBSERVE` |
| `risk_tags` | `daily_return <= -0.07` | `BIG_DROP_TODAY` |

进入高波动、深回撤或当日大跌区间时，也应同步写入 `warn_tags`。

## 9. 支撑状态判定

支撑状态按优先级匹配，命中即返回。核心原则是均线必须在当前价格下方或极近，不能把价格上方很远的均线当支撑。

| 优先级 | 状态 | 条件 | `main_support_ma` |
|---:|---|---|---|
| 1 | `SPRINT_MA5_SUPPORT` | `close >= MA5` 且 `abs(close - MA5) / close <= 0.03` | `MA5` |
| 2 | `SPRINT_MA10_SUPPORT` | `close >= MA10` 且 `abs(close - MA10) / close <= 0.04` | `MA10` |
| 3 | `SPRINT_MA20_SUPPORT` | `close >= MA20 * 0.96` 且 `abs(close - MA20) / close <= 0.06` | `MA20` |
| 4 | `SPRINT_MA50_TESTING` | `close >= MA50 * 0.92` 且 `abs(close - MA50) / close <= 0.08` | `MA50` |
| 5 | `SPRINT_FAILED` | 以上都不满足 | `None` |

注意：外部文档指出原 Excel 条件说明曾和实际代码不一致。项目实现时必须以本节规则为准，并保证前端/文档/测试描述一致。

## 10. 支撑评分

`support_score` 为 0-10 分，反映当前价贴近主支撑的质量。

| 状态 | 距离条件 | 分数 |
|---|---|---:|
| `SPRINT_MA5_SUPPORT` | `dist <= 0.01` | 10 |
| `SPRINT_MA5_SUPPORT` | `dist <= 0.02` | 9 |
| `SPRINT_MA5_SUPPORT` | 其他 | 8 |
| `SPRINT_MA10_SUPPORT` | `dist <= 0.01` | 9 |
| `SPRINT_MA10_SUPPORT` | `dist <= 0.03` | 8 |
| `SPRINT_MA10_SUPPORT` | 其他 | 7 |
| `SPRINT_MA20_SUPPORT` | `dist <= 0.02` | 7 |
| `SPRINT_MA20_SUPPORT` | `dist <= 0.04` | 6 |
| `SPRINT_MA20_SUPPORT` | 其他 | 5 |
| `SPRINT_MA50_TESTING` | 任意 | 4 |
| `SPRINT_FAILED` | 任意 | 0 |

`dist = abs(close - main_support_ma_value) / close`。

## 11. 三级分类规则

分类前先执行直接排除。排除后再判定重点候选和观察候选。

### 11.1 直接排除

出现任一情况直接排除：

- `support_status == SPRINT_FAILED`
- `close < MA50 * 0.92`
- `has_volume_up_decline == true`
- `amp_5d > 0.22`
- `amp_10d > 0.45`
- `drawdown_20d < -0.30`

### 11.2 重点候选

`candidate_type = KEY_CANDIDATE`，`classification = highlight`。必须同时满足：

- `support_status` 属于 `SPRINT_MA5_SUPPORT`、`SPRINT_MA10_SUPPORT`、`SPRINT_MA20_SUPPORT`；
- 不含 `BIG_DROP_TODAY`；
- `support_score >= 8`。

### 11.3 观察候选

`candidate_type = WATCH_CANDIDATE`，`classification = observe`。在非重点候选前提下，满足任一：

- `support_status == SPRINT_MA50_TESTING`
- `support_status == SPRINT_MA20_SUPPORT` 且 `daily_return <= -0.07`
- `support_status == SPRINT_MA20_SUPPORT` 且 `support_score < 8`
- `0.18 < amp_5d <= 0.22`
- `0.35 < amp_10d <= 0.45`
- `-0.30 < drawdown_20d <= -0.22`

既不是重点也不是观察，则 `candidate_type = REJECTED`，不写入候选列表。

## 12. 评分模型

评分用于排序和前端展示，不作为硬过滤。总分 100。

| 维度 | 分值 | 内容 |
|---|---:|---|
| 技术信号 | 35 | 均线排列、支撑状态、贴近度、均线斜率 |
| 资金强度 | 30 | 成交额基数、量能趋势、一致性 |
| 趋势强度 | 20 | 距年线、MA120-MA250 缺口、距 MA50 |
| 支撑质量 | 15 | 支撑分、MA20/MA50 斜率 |

### 12.1 技术信号

- `alignment_score`：`MA5>MA10>MA20>MA50>MA100>MA250` 中相邻关系成立比例乘 10，满分 10。
- `state_score`：MA5=12、MA10=10、MA20=7、MA50=4、其他=0。
- `proximity_score`：`max(0, 5 - main_dist * 100)`，满分 5。
- `slope_score`：正斜率时 `min(8, (ma20_slope/5 + ma50_slope/10) * 2)`；含负时 `max(0, (ma20_slope + ma50_slope) * 2)`，满分 8。

### 12.2 资金强度

- `turnover_score = min(15, log10(max(avg60, 1)) * 5)`
- `trend_score = min(8, max(0, (avg10 / avg60 - 0.8) * 10))`
- `consistency = min(7, avg30 / avg60 * 5)`

### 12.3 趋势强度

- 距年线：`(close - MA250) / MA250 * 100`，大于 100 得 5，大于 50 得 10，大于 20 得 8，其他得 6。
- 长短线缺口：`min(5, ((MA120 - MA250) / MA250 * 100) / 5)`。
- 距 MA50：`min(5, max(0, ((close - MA50) / MA50 * 100) / 3))`。

### 12.4 支撑质量

- `sq_score`：优先使用 `support_score`，`min(12, support_score)`。
- `ma20_slope_score = min(4, ma20_slope / 2)`，仅正斜率计分。
- `ma50_slope_score = min(3, ma50_slope / 2)`，仅正斜率计分。

## 13. 输出字段

策略5候选结果至少应包含以下字段，便于前端、回测和审查定位：

| 字段 | 含义 |
|---|---|
| `code` / `name` | 股票代码 / 名称 |
| `evaluation_date` | 策略评估日期 |
| `close` / `daily_return` / `change_pct` | 收盘价、当日收益率、涨跌幅 |
| `trading_days` | 可用交易日数量 |
| `avg_turnover_60d` / `avg_turnover_30d` / `avg_turnover_10d` | 60/30/10 日平均成交额，单位亿元 |
| `ma5` / `ma10` / `ma20` / `ma50` / `ma100` / `ma120` / `ma250` | 均线 |
| `distance_to_ma5` / `distance_to_ma10` / `distance_to_ma20` | 距离均线比例 |
| `recent_5d_return` / `recent_10d_return` / `recent_20d_return` | 近期涨幅 |
| `drawdown_from_20d_high` | 距 20 日最高收盘回撤 |
| `amplitude_5d` / `amplitude_10d` | 5/10 日振幅 |
| `support_status` / `main_support_ma` / `support_score` | 支撑状态、主支撑均线、支撑评分 |
| `candidate_type` / `classification` | `KEY_CANDIDATE`/`WATCH_CANDIDATE` 与 `highlight`/`observe` |
| `range_5_tag` / `range_10_tag` / `pullback_tag` | 风险标签 |
| `risk_tags` / `warn_tags` | 风险和警告标签 |
| `near_120d_high_ratio` / `close_20d_high` / `close_120d_high` | 新高确认相关字段 |
| `strength_trigger` / `high_trigger` | 短线强度和新高触发来源 |
| `ma20_slope_5d` / `ma50_slope_10d` | 均线斜率 |
| `max_decline_5d` / `v20` | 盘整风险指标 |
| `technical_score` / `capital_score` / `trend_score` / `support_quality_score` / `total_score` | 四维评分和总分 |
| `reject_reasons` / `score_reasons` | 排除原因和评分原因 |
| `data_source` / `kline_latest_date` / `kline_fetched_at` / `quote_status` | 数据来源审计字段 |

不得删除或改变其他策略已有字段。策略5应使用独立候选表或独立 `strategy_type` 区分，不得写入策略1/2/3/4 的候选表。

## 14. 建议代码结构

后续真正开发时，建议独立新增 `strategy5/` 包，不复用策略1/2/3/4 的策略判断模块。

建议文件：

- `strategy5/models.py`：Strategy5Indicators、Strategy5Score、Strategy5Evaluation。
- `strategy5/indicators.py`：均线、涨幅、振幅、成交额、斜率、标签计算。
- `strategy5/filters.py`：F1-F11 硬过滤。
- `strategy5/support.py`：支撑状态和支撑评分。
- `strategy5/scorer.py`：四维评分。
- `strategy5/engine.py`：唯一策略入口 `ShortSprintSupportEngine.evaluate_at()`。
- `strategy5/scanner.py`：全市场扫描，复用 `fetch_with_retry()`。
- `strategy5/backtester.py`：本地 DB 回测，只读 `daily_ohlc`。
- `strategy5/validation.py`：配置解析和参数校验。
- `tests/test_strategy5_*.py`：单元、集成、隔离和回归测试。

策略5扫描入口应和策略3/4 类似，创建独立 `STRATEGY_5_SHORT_SPRINT_SUPPORT` 类型，避免跨策略任务混淆。

## 15. 配置建议

建议新增 `strategy5` 配置段，所有关键阈值可配置，但默认值应与本文档一致。

```yaml
strategy5:
  enabled: true
  kline_days: 1100
  minimum_kline_days: 260
  minimum_trading_days: 500
  min_avg_amount_60d_yi: 20
  min_avg_amount_30d_yi: 15
  min_avg_amount_10d_yi: 10
  strength_ret_20d: 0.20
  strength_ret_10d: 0.12
  strength_ret_5d: 0.08
  single_day_surge_return: 0.07
  single_day_surge_volume_ratio: 1.8
  near_120d_high_ratio: 0.98
  max_amp_5d: 0.22
  max_amp_10d: 0.45
  max_drawdown_20d: -0.30
  max_decline_5d: -0.08
  volume_down_return: -0.07
  volume_down_ratio: 1.5
  ma50_min_ratio: 0.92
  key_candidate_min_support_score: 8
```

## 16. 测试计划

### 16.1 单元测试

- 均线计算：MA5/10/20/50/100/120/250。
- 字段适配：本项目 `close/turnover` 能正确映射参考实现 `last/amount` 口径。
- F8：20 日、10 日、5 日涨幅和单日异动四种触发。
- F9：接近 120 日高点、创 120 日新高、失败场景。
- F10：5 日振幅、10 日振幅、20 日回撤、最大单日跌幅、放量下跌。
- 支撑状态：MA5/MA10/MA20/MA50/FAILED 的优先级和互斥。
- 支撑评分：所有边界值。
- 分类：重点、观察、排除。
- 评分：四维分数和总分。

### 16.2 集成测试

- 策略5扫描使用本项目 `fetch_with_retry()`，不调用 westock。
- 三源全部失败时进入失败列表。
- 数据不足时返回稳定失败码，不抛未捕获异常。
- 候选写入策略5独立表，不污染其他策略候选。
- 策略5 API 使用 `strategy_type` 隔离，跨策略任务返回 mismatch。
- 前端策略5页面能显示重点/观察分层、风险标签和评分。

### 16.3 回测测试

- 回测只读本地 DB。
- 按 evaluation_date 截断数据，禁止未来数据泄漏。
- 评分仅排序，不反向影响硬过滤。
- 零候选是合法结果，但必须生成完整汇总。

### 16.4 回归测试

建议命令：

```bash
python -m pytest tests/test_strategy5_* -q
python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py
python -m compileall scanner strategy2 strategy3 strategy4 strategy5 server.py -q
npm.cmd --prefix web test -- --run
npm.cmd --prefix web run build
```

## 17. 风险点

1. **数据天数不足**：策略5要求 `>=500` 个交易日，当前部分扫描配置可能只取 350 根。实现时要为策略5单独配置足够的 `kline_days`，但不能影响策略1-4。
2. **成交额字段口径**：本项目日线字段可能是 `turnover`，外部文档写 `amount`。实现时需要统一字段读取，避免全部流动性过滤误判。
3. **粗筛方式变化**：原文档依赖 MCP 候选池，本项目应从股票池和本地/在线日线推导，候选数量可能不同。这是数据入口差异，不是策略规则差异。
4. **支撑规则必须严格按优先级**：MA5 命中后不得继续降级为 MA10/MA20，否则分类会漂移。
5. **评分不能替代硬过滤**：评分只排序，不得让硬过滤失败的股票重新进入候选。
6. **策略隔离**：策略5不得导入策略1形态识别，也不得改策略2/3/4 的规则。
7. **外部文档旧描述冲突**：Excel 条件说明里旧版支撑口径不应照搬，本文第 9 节为项目实现准绳。
8. **参考实现输出缺口**：`high_trigger` 在 `analyze.py` 中计算但未写入结果。项目实现应补齐该字段，不视为破坏兼容。
9. **报告文案不能反向定义策略**：`score_report.py` 的 HTML 条件摘要把部分观察阈值写得更严格，例如 5 日振幅 `<=18%`、10 日振幅 `<=35%`、20 日回撤 `<=22%`。实际策略允许更宽区间进入观察，并通过风险标签区分。

## 18. 后续执行顺序

1. 先新增策略5模型、配置和参数校验。
2. 用 TDD 实现指标计算、F1-F11 硬过滤、支撑状态和分类。
3. 新增策略5扫描器，复用现有日线数据服务。
4. 新增数据库独立表和 API。
5. 新增前端策略5结果页和配置项。
6. 新增本地 DB 回测。
7. 跑专项测试、全量后端回归、前端测试和构建。
8. 最后用真实本地数据跑一轮扫描/回测，输出策略5验收报告。

## 19. 自检结论

- 数据获取方式已从外部 westock/MCP 流水线改写为本项目现有 `stock_pool + daily_data_service + daily_ohlc`。
- 策略规则完整覆盖外部文档 F1-F11、短线强度、新高确认、盘整、支撑状态、风险标签、三级分类和四维评分。
- 文档明确了不得修改策略1-4、不得引入新行情源、不得污染旧候选表。
- 当前仅新增项目文档，未开始代码实现。

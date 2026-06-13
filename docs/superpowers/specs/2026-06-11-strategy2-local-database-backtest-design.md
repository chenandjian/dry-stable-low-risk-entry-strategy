# 开发方案文档：策略2本地数据库短线回测

## 1. 需求背景

### 1.1 当前问题

策略2「极致量干价稳」已经具备独立全市场扫描能力，但目前无法回答以下关键问题：

- 策略2在历史数据中能否持续找到股票？
- 平均每天能够找到多少机会？
- 历史入选后，未来3、5、10、20个交易日表现如何？
- 策略2的评分等级、风险等级和趋势证据与后续收益是否相关？
- 当前数据库中哪些股票因历史数据不足无法回测？

### 1.2 用户目标

新增策略2独立回测功能，使用数据库中现有日线数据进行全市场历史选股回放，并提供单只股票历史命中查询。

回测必须：

- 只读取本地数据库 `daily_ohlc`。
- 禁止请求任何外部数据源补充数据。
- 使用策略2唯一评估入口，确保扫描与回测判断逻辑一致。
- 使用短线3/5/10/20日观察周期。
- 在前端明确展示无法回测或数据不足的股票。

### 1.3 业务价值

- 验证策略2是否具备真实历史选股能力。
- 识别策略过滤过严、机会过少或候选质量不足的问题。
- 为后续调整评分、风险和趋势规则提供量化依据。
- 避免依赖主观查看少量股票判断策略有效性。

---

## 2. 需求目标

### 2.1 必须实现

- 新增策略2独立全市场历史回测模块。
- 新增策略2单只股票历史命中查询。
- 回测只读取本地 `daily_ohlc`，严禁调用外部数据源。
- 每个历史判断日执行历史时点流动性过滤。
- 每个历史判断日调用 `ExtremeDryStableStrategyEngine.evaluate_at()`。
- 不允许未来数据泄漏。
- 使用3/5/10/20个交易日短线观察周期。
- 同一股票连续命中合并为一次机会。
- 连续10个交易日未命中后再次命中，才生成新机会。
- 记录 `SUCCESS / FAILED / UNRESOLVED / UNOBSERVED`。
- 回测任务、机会明细和数据不足股票独立持久化。
- 新增异步回测接口、进度查询和历史任务查询。
- 新增策略2独立回测前端页面。
- 扫描和策略2回测互斥运行。
- 提供完整测试和回归验证。

### 2.2 可选增强

- 回测结果导出CSV。
- 按行业、市场板块分组统计。
- 多个历史回测任务结果对比。

可选增强不作为本期验收阻塞项。

### 2.3 不做范围

- 不为回测请求百度、新浪、腾讯、yfinance或其他外部数据源。
- 不新增回测专用策略判断逻辑。
- 不修改策略2现有评分、趋势、风险和否决规则。
- 不修改策略1回测逻辑。
- 不模拟资金曲线、仓位管理、手续费和滑点。
- 不实现自动交易。
- 不重构无关模块。

---

## 3. 默认假设

1. 策略2唯一判断入口为 `ExtremeDryStableStrategyEngine.evaluate_at()`。
2. 当前数据库通常保存约350个交易日的日线数据。
3. 回测读取任务启动时的真实策略2配置；当前配置为 `strategy_window_days=350`、`minimum_required_days=250`。
4. 历史判断日至少拥有 `minimum_required_days` 日数据即可执行，最多向策略2引擎传入 `strategy_window_days` 日数据。
5. 回测未来最长观察周期为20个交易日。
6. 当前单只股票约350日数据时，最多约有 `350 - 250 = 100` 个信号判断日，其中约80个判断日具备完整20日未来观察。
7. 数据库日线按股票代码和交易日期唯一存储。
8. 当前worktree存在其他未提交修改，开发不得覆盖或回退这些修改。
9. 回测只验证选股信号后续表现，不模拟真实组合资金占用。
10. 回测任务启动时冻结完整配置快照；任务运行和历史查看均以该快照解释结果。

---

## 4. 产品设计方案

### 4.1 用户使用流程

1. 用户进入“策略2回测”页面。
2. 用户选择回测开始日期、结束日期。
3. 用户选择全市场或输入指定股票代码。
4. 用户可设置最多测试股票数，用于快速验证。
5. 用户点击“开始回测”。
6. 系统验证当前没有扫描或其他策略2回测任务运行。
7. 系统只从本地数据库读取股票池和日线数据。
8. 系统异步执行历史时点策略2判断。
9. 前端展示任务进度、机会数和数据不足股票数。
10. 回测完成后展示汇总报告、机会明细和数据不足股票列表。
11. 用户可进入单只股票详情，查看该股票历史命中机会。

### 4.2 页面展示要求

#### 回测参数区

- 开始日期。
- 结束日期。
- 股票范围：全市场或指定股票。
- 最多测试股票数。
- 本地数据库说明：回测不会请求外部数据源。
- 启动回测按钮。

#### 任务进度区

- 任务状态。
- 当前处理股票。
- 总股票数。
- 已处理股票数。
- 已发现机会数。
- 数据不足股票数。
- 失败股票数。
- 已耗时。

#### 汇总报告

- 测试股票数。
- 发现机会的股票数。
- 总机会数。
- 平均每个评估日发现机会数。
- 完整观察机会数。
- `UNOBSERVED`机会数。
- 数据不足股票数。
- 数据异常股票数。

#### 3/5/10/20日表现

每个观察周期展示：

- 已观察样本数。
- 成功数和成功率。
- 失败数和失败率。
- 未决数。
- 未观察数。
- 平均和中位期末收益。
- 平均和中位最大上涨。
- 平均和中位最大回撤。
- 平均达到目标天数。
- 平均触发止损天数。

#### 机会明细

- 股票代码、名称。
- 首次命中日、最后命中日。
- 连续命中天数。
- 首次命中分数、区间最高分。
- 入选价、止损价、风险比。
- 趋势证据分。
- 3/5/10/20日结果与表现。

#### 数据不足股票

- 股票代码、名称。
- 数据库已有交易日数量。
- 最早和最晚交易日期。
- 回测所需最少数据量。
- 实际可评估日期范围。
- 原因代码和可理解说明。

### 4.3 交互规则

- 扫描运行时禁止启动策略2回测。
- 策略2回测运行时禁止启动任一扫描或新的回测。
- 页面刷新后恢复运行状态和进度。
- 历史回测任务和结果可以重复查看。
- 单只股票异常不终止整体任务。
- 用户请求日期超出本地覆盖范围时，按实际数据范围执行并展示覆盖警告。
- 数据库完全没有日线数据时拒绝创建任务，并返回明确错误。
- 全市场回测默认 `maxStocks=200` 作为快速验证；用户主动选择后才能取消限制运行全市场。
- 启动前展示预计股票数、预计历史判断次数和耗时较长提示。

---

## 5. 技术架构方案

### 5.1 总体架构

```text
前端策略2回测页面
  → 策略2回测API
  → 异步回测任务管理
  → 读取本地 stock_pool + daily_ohlc
  → 历史时点流动性过滤
  → ExtremeDryStableStrategyEngine.evaluate_at()
  → 连续信号去重
  → 3/5/10/20日短线表现计算
  → 持久化任务、机会和数据不足股票
  → 汇总报告与前端展示
```

### 5.2 新增模块

建议新增：

```text
strategy2/backtester.py
strategy2/backtest_models.py
```

职责：

- `backtester.py`
  - 全市场和单股历史回放。
  - 历史时点流动性过滤。
  - 调用策略2唯一引擎。
  - 连续机会去重。
  - 未来短线表现计算。
  - 汇总统计。

- `backtest_models.py`
  - 回测机会。
  - 周期表现。
  - 回测汇总。
  - 数据不足股票。

禁止：

- `strategy2/backtester.py` 导入或调用策略1判断模块。
- 在回测器中复制策略2评分和趋势判断代码。
- 从数据源模块获取数据。

### 5.3 数据流设计

1. API接收回测参数。
2. 后端验证日期、股票范围和运行冲突。
3. 后端读取并校验当前完整配置，生成不可变 `config_snapshot`。
4. 后端检查数据库是否存在日线数据。
5. 创建策略2回测任务并保存配置快照。
6. 后台线程读取本地股票池。
7. 针对每只股票读取全部本地日线。
8. 计算该股票实际可评估日期范围。
9. 对每个历史判断日执行：
   - 截取判断日及之前数据。
   - 历史数据少于配置快照中的 `minimum_required_days` 时跳过该判断日。
   - 历史数据超过 `strategy_window_days` 时，仅保留最近 `strategy_window_days`。
   - 校验策略窗口。
   - 使用判断日及之前数据执行流动性过滤。
   - 调用策略2唯一引擎。
   - 记录历史命中。
10. 将连续命中合并为机会。
11. 使用判断日之后数据计算3/5/10/20日表现。
12. 保存机会和数据不足股票。
13. 汇总任务统计。
14. 前端查询并展示结果。

### 5.4 无未来数据泄漏要求

- 策略判断只允许使用 `decision_date` 及之前数据。
- 流动性过滤只允许使用 `decision_date` 及之前数据。
- 策略2引擎输入不得包含未来数据。
- 未来数据只能用于计算信号产生后的表现。
- 回测测试必须证明未来价格变化不会影响历史判断结果。

---

## 6. 回测日期与数据覆盖规则

### 6.1 日期范围

用户可选择开始和结束日期。

系统必须计算：

```text
requested_start_date
requested_end_date
actual_start_date
actual_end_date
```

实际日期范围受本地数据覆盖和策略窗口限制。

### 6.2 最低数据要求

```text
minimum_history_days = config_snapshot.strategy2.minimum_required_days
maximum_strategy_window_days = config_snapshot.strategy2.strategy_window_days
max_forward_days = 20
minimum_days_for_any_judgment = minimum_history_days
minimum_days_for_one_complete_20d_observation =
    minimum_history_days + max_forward_days
```

当前真实配置示例：

```text
minimum_required_days = 250
strategy_window_days = 350
max_forward_days = 20

至少250日即可产生历史判断。
判断日之前超过350日时，最多使用最近350日。
至少270日才可能产生一个拥有完整20日未来观察的机会。
```

回测不得新增固定120日专用窗口。否则回测结果无法代表当前扫描策略。

### 6.3 数据不足分类

#### `NO_LOCAL_DATA`

- 数据库没有该股票任何日线数据。

#### `INSUFFICIENT_HISTORY_DATA`

- 股票全部本地数据少于配置快照中的 `minimum_required_days`。
- 无法执行任何策略2历史判断。

#### `LIMITED_EVALUATION_RANGE`

- 股票至少存在一个可判断日期，但完整可评估日期较少。
- 允许执行回测，并展示实际可评估范围。

#### `INVALID_LOCAL_DATA`

- 本地日线字段或数值非法，无法执行回测。

### 6.4 判断日级数据不足

以下情况只跳过当前历史判断日，不将整只股票标记为数据不足：

- 当前判断日之前历史数据少于 `minimum_required_days`。
- 策略2引擎返回 `INSUFFICIENT_TREND_DATA`。
- 策略2引擎返回其他判断日级数据不足原因。

股票级 `INSUFFICIENT_HISTORY_DATA` 仅在请求区间内不存在任何可执行判断日时记录。

### 6.5 禁止外部拉取

回测代码不得：

- 调用 `fetch_with_retry()`。
- 调用百度、新浪、腾讯、yfinance等数据源。
- 调用用于自动补充覆盖范围的 `ensure_backtest_data()`。
- 因数据不足而静默请求网络。

必须直接调用：

```text
db.get_ohlc(code)
```

### 6.6 性能预期

以当前数据库约4973只股票、每只最多350日数据、最少250日历史数据、最大未来观察期20日估算：

- 每只股票最多约有100个可执行历史判断日。
- 每只股票约有80个判断日具备完整的20日未来观察数据。
- 快速模式200只股票，最多约执行20000次策略引擎判断，其中约16000次可完成全部未来收益观察。
- 全市场模式最多约执行497300次策略引擎判断，其中约397840次可完成全部未来收益观察。
- 实际数量受停牌、上市天数、请求回测日期范围和数据库缺失数据影响。
- 不承诺固定运行时长；前端必须展示预计判断次数、已完成判断次数、已处理股票数和实时进度。

---

## 7. 历史时点流动性过滤

### 7.1 执行规则

对每个历史判断日：

```text
history_data = 判断日及之前的数据
passes_liquidity_filter(history_data, liquidity_config)
```

只有通过历史时点流动性过滤，才调用策略2引擎。

`liquidity_config` 必须来自任务的 `config_snapshot`，不得在任务执行途中重新读取 `config.yaml`。

### 7.2 统计要求

回测报告记录：

- 总历史评估日数。
- 因历史数据不足跳过的判断日数。
- 因 `INSUFFICIENT_TREND_DATA` 跳过的判断日数。
- 因流动性过滤跳过的评估日数。
- 实际调用策略2引擎的评估日数。

### 7.3 禁止行为

- 不允许使用最新日线对历史判断日执行流动性过滤。
- 不允许先使用全局当前流动性过滤筛掉整只股票，再回测历史。

---

## 8. 连续命中机会去重

### 8.1 去重规则

同一股票连续命中时，合并为一次机会：

- 首次命中日作为信号日。
- 连续命中期间不生成新机会。
- 股票连续10个交易日未命中后，再次命中才生成新机会。

### 8.2 机会字段

每次机会至少保存：

- `first_detected_date`
- `last_detected_date`
- `consecutive_hit_days`
- `first_score`
- `max_score`
- `entry_close`
- `stop_loss`
- `risk_ratio`
- `level`
- `trend_type`
- `trend_evidence_score`
- 首次命中时的完整策略2评估摘要

`evaluation_snapshot` 格式必须明确为：

```text
首次命中时 `_build_strategy2_discovery()` 返回结构的完整JSON序列化结果
```

不得直接序列化Python dataclass对象。快照至少包含量干价稳指标、评分、风险、趋势证据和评估日期，用于历史解释和前端展示。

### 8.3 冷却期精确定义

对同一股票：

```text
missed_trading_days = 当前判断日索引 - 上次命中日索引 - 1
```

- `missed_trading_days < 10`：属于原机会，不创建新机会。
- `missed_trading_days >= 10`：创建新机会。

休市日和自然日不计入冷却期。

---

## 9. 短线表现与结果判定

### 9.1 观察周期

```text
3 / 5 / 10 / 20 个交易日
```

完全移除60日统计。

### 9.2 周期表现

每个观察周期记录：

```text
end_return =
    第N个未来交易日收盘价 / 入选日收盘价 - 1

max_upside =
    未来N个交易日最高价 / 入选日收盘价 - 1

max_drawdown =
    未来N个交易日最低价 / 入选日收盘价 - 1
```

### 9.3 成功、失败、未决和未观察

目标价：

```text
target_price = entry_close × 1.05
```

止损价：

```text
使用首次命中时策略2评估结果中的 stop_loss
```

结果：

- `SUCCESS`
  - 观察期内最高价达到目标价。
  - 且目标触发之前没有触发止损价。

- `FAILED`
  - 达到目标价前先触发止损价。

- `UNRESOLVED`
  - 观察期内既未达到目标价，也未触发止损价。

- `UNOBSERVED`
  - 判断日之后不足对应观察周期数据。
  - 不计入该周期成功率和失败率。

### 9.4 同日目标与止损同时触发

日线数据无法确认盘中先后顺序。

采用保守规则：

```text
同一交易日同时达到目标价和止损价 → FAILED
```

### 9.5 达成天数

记录：

- `days_to_target`
- `days_to_stop`

均使用未来交易日序号，从1开始。

---

## 10. 数据库设计方案

### 10.1 新增回测任务表

```sql
CREATE TABLE IF NOT EXISTS strategy2_backtest_tasks (
    id                       TEXT PRIMARY KEY,
    status                   TEXT NOT NULL DEFAULT 'running',
    requested_start_date     TEXT,
    requested_end_date       TEXT,
    actual_start_date        TEXT,
    actual_end_date          TEXT,
    scope_type               TEXT NOT NULL,
    requested_codes          TEXT,
    max_stocks               INTEGER,
    config_snapshot          TEXT NOT NULL,
    estimated_evaluations    INTEGER DEFAULT 0,
    completed_evaluations    INTEGER DEFAULT 0,
    total_stocks             INTEGER DEFAULT 0,
    processed_stocks         INTEGER DEFAULT 0,
    stocks_with_opportunities INTEGER DEFAULT 0,
    opportunities_count      INTEGER DEFAULT 0,
    insufficient_stocks_count INTEGER DEFAULT 0,
    failed_stocks_count      INTEGER DEFAULT 0,
    started_at               TEXT,
    finished_at              TEXT,
    elapsed_seconds          REAL,
    error                    TEXT
);
```

### 10.2 新增回测机会表

```sql
CREATE TABLE IF NOT EXISTS strategy2_backtest_opportunities (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id               TEXT NOT NULL,
    code                  TEXT NOT NULL,
    name                  TEXT,
    first_detected_date   TEXT NOT NULL,
    last_detected_date    TEXT NOT NULL,
    consecutive_hit_days  INTEGER NOT NULL,
    first_score           INTEGER NOT NULL,
    max_score             INTEGER NOT NULL,
    level                 TEXT,
    entry_close           REAL NOT NULL,
    stop_loss             REAL NOT NULL,
    risk_ratio            REAL,
    trend_type            TEXT,
    trend_evidence_score  INTEGER,
    evaluation_snapshot   TEXT,
    horizon_3             TEXT,
    horizon_5             TEXT,
    horizon_10            TEXT,
    horizon_20            TEXT,
    created_at            TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (task_id) REFERENCES strategy2_backtest_tasks(id)
);
```

`horizon_3/5/10/20` 使用结构化JSON保存周期表现。

`config_snapshot` 保存任务启动时的完整有效配置JSON。任务执行过程中不得重新读取并使用更新后的 `config.yaml` 参数；策略执行实际使用快照中的 `strategy2`、`liquidity` 和相关数据配置。

`evaluation_snapshot` 保存首次命中时 `_build_strategy2_discovery()` 的完整JSON结果。

### 10.3 新增数据不足股票表

```sql
CREATE TABLE IF NOT EXISTS strategy2_backtest_insufficient_stocks (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id              TEXT NOT NULL,
    code                 TEXT NOT NULL,
    name                 TEXT,
    reason_code          TEXT NOT NULL,
    available_days       INTEGER DEFAULT 0,
    required_days        INTEGER DEFAULT 0,
    earliest_date        TEXT,
    latest_date          TEXT,
    actual_start_date    TEXT,
    actual_end_date      TEXT,
    detail               TEXT,
    FOREIGN KEY (task_id) REFERENCES strategy2_backtest_tasks(id)
);
```

### 10.4 索引

```sql
CREATE INDEX IF NOT EXISTS idx_s2_backtest_task_status
ON strategy2_backtest_tasks(status, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_s2_backtest_opportunity_task
ON strategy2_backtest_opportunities(task_id, first_detected_date);

CREATE INDEX IF NOT EXISTS idx_s2_backtest_opportunity_stock
ON strategy2_backtest_opportunities(task_id, code, first_detected_date);

CREATE INDEX IF NOT EXISTS idx_s2_backtest_insufficient_task
ON strategy2_backtest_insufficient_stocks(task_id, reason_code);
```

### 10.5 数据兼容

- 仅新增表和索引。
- 不修改策略1回测表。
- 不修改现有扫描任务和候选表。
- 数据库初始化使用现有兼容式创建方式。

---

## 11. 接口设计方案

### 11.1 启动回测

```http
POST /api/strategy2/backtests
```

请求：

```json
{
  "startDate": "2025-08-01",
  "endDate": "2026-05-01",
  "codes": [],
  "maxStocks": 200
}
```

规则：

- `codes`为空表示全市场。
- 指定股票时只测试指定代码。
- `maxStocks`默认200，用于快速验证策略是否能找到股票。
- 用户主动选择全市场模式时才允许传入 `null`。
- 数据只从数据库读取。
- 创建任务前返回或展示预计评估次数。

### 11.2 查询当前回测状态

```http
GET /api/strategy2/backtests/status
```

### 11.3 查询历史任务

```http
GET /api/strategy2/backtests
```

### 11.4 查询回测任务和汇总

```http
GET /api/strategy2/backtests/{taskId}
```

### 11.5 查询机会明细

```http
GET /api/strategy2/backtests/{taskId}/opportunities
```

支持参数：

```text
code
level
horizon
result
limit
offset
```

### 11.6 查询数据不足股票

```http
GET /api/strategy2/backtests/{taskId}/insufficient-stocks
```

### 11.7 查询单只股票历史命中

```http
GET /api/strategy2/backtests/{taskId}/stocks/{code}
```

返回该股票所有机会、周期表现和数据覆盖信息。

### 11.8 冲突响应

扫描或回测任务正在运行时返回HTTP 409：

```json
{
  "error": "TASK_CONFLICT",
  "message": "当前已有扫描或策略2回测任务正在运行",
  "runningTaskId": "..."
}
```

---

## 12. 可以实施的代码方案

### 12.1 任务一：回测模型和纯计算

新增：

- `strategy2/backtest_models.py`
- `strategy2/backtester.py`
- `tests/test_strategy2_backtester.py`

优先实现纯函数：

```text
calculate_horizon_performance()
merge_consecutive_signals()
aggregate_backtest_report()
```

测试：

- 3/5/10/20日表现。
- 成功、失败、未决、未观察。
- 同日目标和止损同时触发时判失败。
- 10个交易日冷却边界。
- 聚合统计排除 `UNOBSERVED`。

### 12.2 任务二：历史回放核心

实现：

```text
run_strategy2_backtest()
run_strategy2_stock_backtest()
```

要求：

- 只调用 `db.get_ohlc()`。
- 每个判断日执行历史时点流动性过滤。
- 每个判断日调用策略2唯一引擎。
- 禁止导入数据源模块。
- 禁止未来数据泄漏。
- 数据不足股票返回结构化结果。
- 判断日级 `INSUFFICIENT_TREND_DATA` 只跳过该日期，不能提前终止该股票。
- 使用任务启动时的 `config_snapshot` 构造策略2引擎和流动性配置。
- 每完成一只股票立即持久化机会、数据不足信息和任务进度。

### 12.3 任务三：数据库持久化

修改：

- `scanner/db.py`
- 相关数据库测试

要求：

- 新增三张回测表及索引。
- 提供任务、机会、数据不足股票CRUD。
- 保证JSON序列化和反序列化。
- 分批写入，避免任务结束前结果全部丢失。

### 12.4 任务四：异步API和任务互斥

修改：

- `server.py`
- API测试

要求：

- 新增策略2回测API。
- 回测使用独立运行状态。
- 扫描与回测双向互斥。
- 单股异常不中断整体任务。
- 页面刷新后可查询当前任务。
- 启动接口返回预计评估次数。

### 12.5 任务五：前端回测页面

新增：

- `web/src/pages/Strategy2Backtest.vue`

修改：

- `web/src/router/index.js`
- `web/src/components/TopNav.vue`
- `web/src/composables/useApi.js`
- 相关页面测试

要求：

- 参数输入和本地数据库提示。
- 默认快速测试200只，用户明确选择后才能全市场运行。
- 启动前展示预计评估次数和耗时提示。
- 异步进度。
- 汇总报告。
- 3/5/10/20日统计。
- 机会明细。
- 数据不足股票列表。
- 单只股票历史命中详情。

### 12.6 任务六：独立性与回归

- 策略2回测只能导入策略2判断和共享数据库/流动性基础模块。
- 不得导入策略1引擎。
- 不得导入任何数据源获取模块。
- 增加扫描与回测同一判断日结果一致性测试。

---

## 13. 日志与异常处理方案

### 13.1 必须记录

- 回测任务创建、开始、完成、失败。
- 回测参数和策略2配置快照。
- 预计和已完成策略判断次数。
- 每100只股票的进度。
- 数据不足和无本地数据统计。
- 单股回测异常。
- 扫描与回测冲突。

### 13.2 异常处理

- 单股异常记录后继续。
- 数据库无任何日线时拒绝任务。
- 日期范围非法时返回HTTP 400。
- 指定股票不存在时记录 `NO_LOCAL_DATA`。
- 任务级异常标记失败并保留已写入结果。
- 禁止因数据不足请求外部数据源。

---

## 14. 测试方案

### 14.1 单元测试

- 周期表现计算。
- 成功/失败/未决/未观察。
- 同日目标止损冲突。
- 连续信号合并。
- 10交易日冷却边界。
- 汇总统计。

### 14.2 历史回放测试

- 判断日输入只包含当日及之前数据。
- 未来价格变化不影响历史判断。
- 历史时点流动性过滤。
- 流动性过滤使用任务配置快照，不受任务启动后的配置修改影响。
- 只调用策略2唯一引擎。
- 扫描和回测同一判断日结果一致。
- 回测不调用数据源模块。
- 250至349日历史数据可执行判断，最多向引擎传入350日。
- `INSUFFICIENT_TREND_DATA` 只跳过当前判断日。

### 14.3 数据覆盖测试

- 完全无数据：`NO_LOCAL_DATA`。
- 少于策略窗口：`INSUFFICIENT_HISTORY_DATA`。
- 可回测但完整范围较短：`LIMITED_EVALUATION_RANGE`。
- 无效数据：`INVALID_LOCAL_DATA`。
- 靠近数据末尾信号产生 `UNOBSERVED`。

### 14.4 数据库与接口测试

- 三张表创建和兼容初始化。
- JSON字段正确读写。
- 回测任务启动、状态、历史列表和详情。
- 机会分页和单股查询。
- 数据不足股票查询。
- 扫描和回测互斥。

### 14.5 前端测试

- 参数校验。
- 默认快速测试200只和全市场二次确认。
- 预计评估次数和耗时提示。
- 启动回测和进度恢复。
- 汇总报告。
- 3/5/10/20日表现。
- 机会明细。
- 数据不足股票列表。
- 本地数据库提示。
- 错误和空状态。

### 14.6 回归测试

- 策略2扫描行为不变。
- 策略2唯一引擎行为不变。
- 策略1回测不受影响。
- 扫描任务和结果页面不受影响。
- 全量后端测试通过。
- 前端测试和构建通过。

---

## 15. 验收标准

1. 用户可以从前端启动策略2全市场或指定股票回测。
2. 回测只读取本地数据库，绝不请求外部数据源。
3. 历史判断使用策略2唯一引擎，无未来数据泄漏。
4. 每个历史判断日执行历史时点流动性过滤。
5. 连续命中使用10交易日冷却规则合并。
6. 完整统计3/5/10/20日短线表现。
7. 成功、失败、未决和未观察分类正确。
8. 回测任务和结果可持久化并在页面刷新后查看。
9. 数据不足股票在前端独立展示。
10. 扫描和回测互斥运行。
11. 单只股票历史命中可查询。
12. 策略2扫描、策略1和现有功能不受影响。
13. 全量测试和前端构建通过。
14. 回测任务使用启动时配置快照，之后修改配置不改变历史任务语义。
15. 至少250日即可判断、最多使用350日的窗口行为与扫描一致。

---

## 16. 给 Claude Code / Codex 的执行指令

请严格按照本文档开发策略2本地数据库短线回测功能。

1. 先阅读策略2唯一引擎、扫描器、数据库层、策略1回测模式和现有前端页面。
2. 使用测试驱动开发，先编写失败测试。
3. 回测判断必须调用 `ExtremeDryStableStrategyEngine.evaluate_at()`。
4. 回测任务启动时冻结完整配置快照，策略引擎和流动性过滤均使用该快照。
5. 至少 `minimum_required_days` 即可判断，最多使用 `strategy_window_days`，保持与扫描一致。
6. `INSUFFICIENT_TREND_DATA` 只跳过当前判断日。
7. 回测只允许调用 `db.get_ohlc()`读取日线。
8. 严禁调用任何外部数据源或自动补拉函数。
9. 每个历史判断日必须执行历史时点流动性过滤。
10. 严格防止未来数据泄漏。
11. 只统计3/5/10/20日，不增加60日统计。
12. 使用10个未命中交易日作为新机会冷却边界。
13. 同日目标和止损同时触发时按失败处理。
14. `UNOBSERVED`不得计入成功率或失败率。
15. `evaluation_snapshot` 保存首次命中的完整 `_build_strategy2_discovery()` JSON。
16. 默认快速测试200只，全市场运行需要用户明确选择。
17. 不修改策略2现有评分、趋势、风险和否决规则。
18. 不修改策略1回测逻辑。
19. 数据库只允许兼容式新增表和索引。
20. 不覆盖或回退当前worktree中的已有未提交修改。
21. 每完成一个模块运行对应测试。
22. 最终运行策略2测试、全量后端测试、前端测试和前端构建。
23. 将开发过程、测试结果和遗留问题追加到 `operations-log.md`。
24. 完成后提交代码并报告修改文件、接口、数据库变更和测试结果。

---

## 17. AI开发提示语

```text
请开发策略2“本地数据库短线回测”完整功能。

工作目录：
D:\game\claude\dry-stable-low-risk-entry-strategy\.claude\worktrees\strategy2-extreme-dry-stable

开发依据：
docs/superpowers/specs/2026-06-11-strategy2-local-database-backtest-design.md

核心目标：
使用本地daily_ohlc历史数据，验证策略2历史上能否找出股票，以及入选后3/5/10/20个交易日的短线表现。

强制要求：
1. 回测只读取本地数据库，禁止请求百度、新浪、腾讯、yfinance或任何外部数据源。
2. 每个历史判断日只能使用当日及之前数据。
3. 每个判断日执行历史时点流动性过滤。
4. 策略判断必须调用ExtremeDryStableStrategyEngine.evaluate_at()，禁止复制策略判断代码。
5. 回测启动时冻结完整config_snapshot，策略和流动性过滤都必须使用快照参数。
6. 当前配置至少250日即可判断，最多使用350日；禁止固定使用120日回测窗口。
7. INSUFFICIENT_TREND_DATA只跳过当前判断日，不标记整只股票数据不足。
8. evaluation_snapshot保存首次命中时完整_build_strategy2_discovery() JSON。
9. 默认快速测试200只，全市场运行需要用户明确选择，并展示预计评估次数和耗时提示。
10. 观察周期只使用3/5/10/20日，完全移除60日。
11. 同一股票连续命中合并；连续10个交易日未命中后再次命中才算新机会。
12. 成功：先达到+5%且此前未触发策略止损。
13. 失败：达到+5%前先触发策略止损。
14. 未决：观察期内目标和止损均未触发。
15. 未来数据不足时标记UNOBSERVED，不计入成功率或失败率。
16. 同一天目标和止损同时触发时按FAILED处理。
17. 新增异步回测任务、数据库持久化、API和独立前端页面。
18. 数据不足或无本地数据的股票必须在前端单独列出。
19. 扫描与回测必须双向互斥。
20. 不修改策略2现有评分、趋势、风险和否决规则。
21. 不修改策略1，不覆盖当前worktree已有未提交修改。

实施方式：
- 使用测试驱动开发，先写失败测试。
- 每完成一个任务运行对应测试。
- 最终运行策略2测试、全量后端测试、前端测试和前端构建。
- 将执行过程和测试结果追加到operations-log.md。
- 完成后提交代码，并报告修改文件、数据库/API变更和测试结果。

直接开始执行，不需要再次确认文档中已经明确的事项。
```

---

## 18. 最终交付物

1. 策略2独立本地数据库回测模块。
2. 回测模型和汇总计算。
3. 回测任务、机会和数据不足股票数据库表。
4. 异步回测API和任务互斥。
5. 策略2回测前端页面。
6. 单只股票历史命中查询。
7. 完整后端、接口和前端测试。
8. 全量测试与构建结果。

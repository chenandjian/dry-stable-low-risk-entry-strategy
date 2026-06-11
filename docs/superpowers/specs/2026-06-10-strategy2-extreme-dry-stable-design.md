# 开发方案文档：策略2「极致量干价稳」独立全市场扫描

## 1. 需求背景

### 1.1 当前问题

项目当前只有一条正式扫描策略链路，扫描结果由 `CupHandleStrategyEngine` 统一判断，核心依赖杯柄/VCP 形态、现有量干价稳分析及现有决策规则。

现需新增策略2「极致量干价稳」：

- 独立扫描全部股票，不要求股票先满足杯柄或 VCP 形态。
- 独立计算量干、价稳、关键支撑、止损和风险比。
- 不调用、不复用策略1的形态检测、评分、分析或决策结论。
- 与策略1使用独立配置、扫描入口、候选结果、API 和前端结果视图。
- 继续共享股票池、日线数据源、日线存储、流动性过滤和全市场扫描互斥能力。

### 1.2 用户痛点

- 现有策略将形态判断作为前置条件，无法发现没有杯柄/VCP形态、但已经出现极致缩量和价格稳定的股票。
- 两种策略如果共享候选结果或判断模块，结果含义会混淆，无法确认股票因哪套规则入选。
- 策略2计算窗口、候选等级、风险规则需要独立配置和展示，不能被策略1配置隐式影响。

### 1.3 业务目标

建立第二条可独立运行、独立解释、独立演进的选股链路，在保持数据采集基础设施复用的前提下，扩大对低风险量价机会的覆盖。

### 1.4 预期效果

用户可以分别启动策略1或策略2扫描。策略2会对通过全局流动性过滤的股票执行独立量价判断，并在独立页面展示评分、等级、关键支撑、买入区间、止损和风险比。

---

## 2. 需求目标

### 2.1 必须实现

- 新增策略2独立配置区，配置不能与策略1混用。
- 新增策略2独立全市场扫描入口和扫描编排。
- 策略2扫描全部股票，不依赖杯柄/VCP识别结果。
- 复用现有股票池、三数据源、日线数据库和全局流动性过滤。
- 新增策略2独立走势趋势过滤，只收录上涨或横盘股票，下降趋势股票强制排除。
- 新增策略2独立指标、评分、一票否决、风险计算和结果模型。
- `key_support` 使用不含评估日的前10个交易日最低收盘价。
- 策略2候选结果写入独立数据表。
- 扫描任务可区分策略1和策略2。
- 任一全市场扫描运行时，禁止启动另一全市场扫描。
- 新增策略2独立 API 和前端结果页面。
- 前端配置页明确展示独立的“策略2：极致量干价稳”配置分区。
- 为核心计算、扫描互斥、存储、接口和前端流程补充测试。

### 2.2 可选增强

- 在策略2结果页面提供 CSV 导出。
- 支持按等级、风险比、总分、量干分、价稳分筛选和排序。
- 支持对策略2历史任务重新评估。

可选增强不作为本期验收阻塞项。

### 2.3 不做范围

- 本期不开发策略2回测功能。
- 不为策略2识别杯柄、VCP 或其他形态。
- 不调用策略1的 `CupHandleStrategyEngine`、形态检测、现有量干价稳评分或决策模块。
- 不修改策略1的评分和入选规则。
- 不将策略2候选写入现有 `candidates` 表。
- 不允许策略1和策略2全市场扫描同时运行。
- 不重构无关页面、模块或整体项目架构。
- 不新增独立股票池、独立数据源实现或重复日线存储。

---

## 3. 默认假设

1. 开发基线为 `multi-source-daily-kline` 工作树当前代码结构。
2. 正式开发在独立 Git worktree 和 `codex/` 前缀分支中完成。
3. 策略1指项目现有杯柄/VCP统一策略链路；策略2指本开发文档定义的极致量干价稳策略。
4. “完全独立”指策略判断、配置、候选存储、接口和结果展示独立；股票池、数据采集、日线存储、流动性过滤、任务基础能力允许共享。
5. 日线拉取天数继续使用全局 `liquidity.min_listing_days`。
6. 策略2计算仅使用最近 `strategy2.strategy_window_days` 个有效交易日。
7. 策略2首期各评分项阈值和一票否决阈值固定在策略2代码中；候选最低分、最大风险比等已确认参数允许配置。
8. 策略2使用评估日收盘数据形成当日结果，所有计算严禁读取评估日之后的数据。
9. 数据源按现有三数据源机制运行，策略2不改变数据源优先级、标准化格式和入库方式。
10. SQLite 结构变更只允许兼容式新增表、字段和索引，不执行破坏性迁移。

---

## 4. 产品设计方案

### 4.1 用户使用流程

1. 用户进入策略配置页。
2. 用户在“策略2：极致量干价稳”独立分区设置策略计算天数、最低数据天数、候选最低分和最大风险比等参数。
3. 用户进入扫描控制台，点击“启动策略2扫描”。
4. 系统检查是否已有策略1或策略2全市场扫描正在运行。
5. 若无冲突，系统创建类型为 `STRATEGY_2_EXTREME_DRY_STABLE` 的扫描任务。
6. 系统获取股票池，按现有机制拉取并入库日线数据。
7. 系统执行全局流动性过滤，再执行策略2独立计算。
8. 前端持续展示策略2任务进度和实时发现。
9. 扫描完成后，用户进入策略2结果页查看候选。
10. 用户打开策略2候选详情，查看评分明细、风险位置和命中规则。

### 4.2 页面展示要求

#### 扫描控制台

- “启动策略1扫描”按钮。
- “启动策略2扫描”按钮。
- 当前运行策略名称。
- 任务状态、总股票数、已处理数、跳过数、失败数、候选数和进度。
- 策略2实时发现项展示：股票代码、名称、总分、等级、风险比。

#### 策略配置页

新增独立视觉分区“策略2：极致量干价稳”，至少展示：

- 是否启用。
- 策略计算天数。
- 最低有效数据天数。
- 候选最低分。
- 最大风险比。
- 支撑位回看天数。
- 买入区间最大溢价。
- 止损缓冲比例。

分区中需明确提示：

- 日线拉取天数使用全局配置。
- 策略2不使用杯柄/VCP判断。
- 策略2本期不支持回测。

#### 策略2结果页

- 任务选择器及任务状态。
- 总候选数和各等级数量。
- 股票代码、名称、总分、等级。
- 量干分、价稳分。
- V3、V5、V10、V20、V5/V20、60日成交量分位。
- 5日涨跌幅、5日振幅、5日收盘区间。
- 当前收盘价、关键支撑、买入区间、止损价、风险比。
- 命中的评分项。

策略2结果页不显示杯柄/VCP、形态分、突破状态等策略1字段。

### 4.3 交互规则

- 任一全市场扫描运行时，两个策略的启动按钮均禁用。
- 重复启动请求不创建新任务，返回当前运行任务信息。
- 策略2未启用时，启动请求返回可理解的错误提示。
- 页面刷新后，通过任务状态接口恢复当前任务进度。
- 单只股票失败不终止整体任务。
- 扫描完成或失败后停止轮询。
- 策略1和策略2结果入口、结果文案和字段必须明确区分。

---

## 5. 技术架构方案

### 5.1 总体架构

采用“共享基础设施，策略业务完全独立”的方案。

```text
共享层
股票池 → 三数据源 → 日线标准化/入库 → 全局流动性过滤 → 全局扫描互斥
                                                   ├─ 策略1现有链路
                                                   └─ 策略2独立链路
```

共享层允许复用：

- `scanner.stock_pool`
- `scanner.data_source`
- 百度、新浪、腾讯数据源
- `scanner.db` 中股票池、日线、任务和任务股票基础能力
- `scanner.liquidity_filter.passes_liquidity_filter`
- 全市场扫描互斥状态

策略2禁止依赖：

- `scanner.strategy_engine.CupHandleStrategyEngine`
- `scanner.pattern_detector`
- 策略1使用的 VCP 检测逻辑
- `analyzer.dry_stable`
- `analyzer.volume_dry`
- `analyzer.price_stable`
- `analyzer.pattern_score`
- `analyzer.decision`
- 策略1现有候选结果和结论

### 5.2 模块设计

新增独立 Python 包：

```text
strategy2/
  __init__.py
  models.py
  indicators.py
  scorer.py
  rejection.py
  risk.py
  engine.py
  scanner.py
```

模块职责：

- `models.py`：策略2输入校验结果、指标结果、评分结果、风险结果和最终评估结果的数据模型。
- `indicators.py`：只负责从策略窗口计算指标，不负责判断是否入选。
- `scorer.py`：只负责量干50分、价稳50分及等级计算。
- `rejection.py`：只负责执行一票否决规则并返回稳定错误码。
- `risk.py`：只负责关键支撑、买入区间、止损和风险比计算。
- `trend.py`：只负责策略2走势趋势指标、趋势分类和下降趋势过滤。
- `engine.py`：策略2唯一评估入口，组合上述模块并输出最终结果。
- `scanner.py`：策略2全市场扫描编排，不包含指标和评分实现。

为避免策略2导入 `scanner.engine` 后间接加载策略1判断模块，应将可复用的数据拉取编排提取到共享基础模块，例如：

```text
scanner/daily_data_service.py
```

该模块只包含数据源链、互斥、重试和统一 `FetchResult`，不得包含任何策略判断。策略1与策略2扫描器均从该共享模块调用数据拉取能力。

### 5.3 数据流设计

1. 前端调用策略2启动接口。
2. 后端验证 `strategy2.enabled` 和策略2配置。
3. 后端检查全局扫描互斥状态。
4. 后端创建带 `strategy_type` 的扫描任务并保存任务股票。
5. 策略2扫描器从共享日线服务拉取 `min_listing_days` 日数据。
6. 日线按现有统一格式入库。
7. 使用完整拉取数据执行现有全局流动性过滤。
8. 从数据尾部截取最近 `strategy2.strategy_window_days` 日。
9. 若有效数据少于 `strategy2.minimum_required_days`，明确跳过。
10. 策略2执行独立走势趋势判断，确认下降趋势时强制跳过。
11. 策略2引擎计算量干价稳指标、评分、否决规则和风险信息。
12. 满足入选条件的结果写入 `strategy2_candidates`。
13. 任务进度写入现有任务跟踪结构。
14. 前端轮询状态并展示独立结果。

### 5.4 状态设计

复用现有任务状态，新增 `strategy_type` 区分任务归属。

任务类型：

- `STRATEGY_1_CUP_HANDLE`
- `STRATEGY_2_EXTREME_DRY_STABLE`

任务状态：

- `running`：任务正在执行；禁止启动任一新的全市场扫描。
- `completed`：任务正常结束，允许查看候选结果。
- `failed`：任务级异常终止，展示错误原因。
- `interrupted`：服务中断后发现未完成任务，可按现有恢复机制处理。

单股状态沿用 `task_stocks`：

- `pending`
- `fetching`
- `skipped`
- `scanned`
- `candidate`
- `failed`

策略2常用 `status_reason` 稳定错误码：

- `INSUFFICIENT_LISTING_DATA`
- `LIQUIDITY_FILTER_REJECTED`
- `DOWNTREND_FILTERED`
- `INSUFFICIENT_STRATEGY_DATA`
- `INVALID_MARKET_DATA`
- `REJECT_VOLUME_DRY_PRICE_DROP`
- `REJECT_HEAVY_VOLUME_DROP`
- `REJECT_RANGE_TOO_WIDE`
- `REJECT_SUPPORT_BROKEN`
- `REJECT_RECENT_SURGE`
- `RISK_RATIO_TOO_HIGH`
- `SCORE_BELOW_THRESHOLD`
- `ALL_DATA_SOURCES_FAILED`
- `STRATEGY2_EVALUATION_ERROR`

### 5.5 策略2核心计算

#### 数据要求

- 拉取窗口：`liquidity.min_listing_days`，默认沿用现有值。
- 计算窗口：`strategy2.strategy_window_days`，默认120。
- 最低有效数据：`strategy2.minimum_required_days`，默认60。
- `strategy_window_days` 必须不小于 `minimum_required_days`。
- `strategy_window_days` 必须不大于 `min_listing_days`。

#### 指标定义

在评估日 `T` 及之前的数据上计算：

```text
V3  = 最近3日平均成交量
V5  = 最近5日平均成交量
V10 = 最近10日平均成交量
V20 = 最近20日平均成交量
volume_ratio_5_20 = V5 / V20

range_5 = (最近5日最高价 - 最近5日最低价) / 最近5日最低价
close_range_5 = (最近5日最高收盘价 - 最近5日最低收盘价) / 最近5日最低收盘价
return_5 = 当前收盘价 / 5日前收盘价 - 1
return_3 = 当前收盘价 / 3日前收盘价 - 1
daily_return = 当日收盘价 / 前一日收盘价 - 1

MA20 = 最近20日收盘价简单移动平均
MA60 = 最近60日收盘价简单移动平均
MA20_SLOPE = 当前MA20 / 5个交易日前MA20 - 1
RETURN_20 = 当前收盘价 / 20个交易日前收盘价 - 1
```

60日成交量分位要求：

- 对最近60个交易日的成交量计算分位。
- 指标输出至少包含最近5日最低成交量在60日窗口中的百分位。
- 数据不足60日但达到最低有效数据时，以实际可用窗口计算，并在结果中记录实际分位窗口天数。

#### 走势趋势前置过滤

走势趋势判断属于策略2前置强制过滤，不参与量干价稳100分评分。

仅当以下四项同时满足时，股票被判定为下降趋势：

```text
current_close < MA20
MA20 < MA60
MA20_SLOPE < 0
RETURN_20 < -5%
```

趋势类型：

- `DOWNTREND`：四项条件全部满足，强制排除并记录 `DOWNTREND_FILTERED`。
- `UPTREND_OR_SIDEWAYS`：未同时满足四项条件，允许继续执行策略2评分。

约束：

- 趋势判断只使用评估日及之前的数据。
- 趋势过滤在流动性过滤之后、量干价稳评分之前执行。
- 不因短期一两日下跌直接判定为下降趋势。
- 候选详情展示趋势类型、MA20、MA60、MA20斜率和20日涨跌幅。

#### 量干评分，满分50

- `V5 / V20 <= 0.60`：+10。
- `V5 / V20 <= 0.50`：额外 +10。
- `V3 < V5 < V10 < V20`：+10。
- 最近5日中至少一天成交量处于近60日成交量的最低20%：+10。
- `return_5 >= -3%`：+10。

#### 价稳评分，满分50

- `range_5 <= 5%`：+10。
- `range_5 <= 3%`：额外 +10。
- `close_range_5 <= 3%`：+10。
- 最近5日不存在单日跌幅低于 `-3%`：+10。
- 当前收盘价不低于 `key_support`：+10。

#### 等级

- `70-79`：普通观察。
- `80-89`：重点观察。
- `90-94`：极致量干价稳。
- `95-100`：终极状态。

#### 关键支撑与风险

```text
key_support = 不包含评估日T的前10个交易日最低收盘价
buy_zone_low = key_support
buy_zone_high = key_support × (1 + buy_zone_max_premium)
stop_loss = key_support × (1 - stop_loss_buffer)
risk_ratio = (current_close - stop_loss) / current_close
```

约束：

- `key_support` 计算必须排除评估日，避免“当前价永远不低于支撑”的失效规则。
- `risk_ratio <= 3%`：低风险。
- `3% < risk_ratio <= 5%`：风险可接受。
- `risk_ratio > 5%`：排除。

#### 一票否决

- 量干但 `return_5 < -5%`。
- 最近5日任一单日跌幅 `<= -4%`，且该日成交量大于 `V20`。
- `range_5 > 8%`。
- 当前收盘价低于 `key_support`。
- `return_3 >= 8%`。

#### 最终入选条件

必须同时满足：

- 总分 `>= strategy2.candidate_min_score`，默认70。
- 趋势类型为 `UPTREND_OR_SIDEWAYS`。
- 未触发任何一票否决。
- 风险比 `<= strategy2.max_risk_ratio`，默认0.05。

---

## 6. 数据库设计方案

### 6.1 修改 `scan_tasks`

兼容式新增字段：

```sql
ALTER TABLE scan_tasks ADD COLUMN strategy_type TEXT DEFAULT 'STRATEGY_1_CUP_HANDLE';
```

旧任务自动按策略1解释，不修改旧记录。

新增索引：

```sql
CREATE INDEX IF NOT EXISTS idx_scan_tasks_strategy_started
ON scan_tasks(strategy_type, started_at DESC);
```

### 6.2 新增 `strategy2_candidates`

```sql
CREATE TABLE IF NOT EXISTS strategy2_candidates (
    id                         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id                    TEXT NOT NULL,
    code                       TEXT NOT NULL,
    name                       TEXT NOT NULL,
    evaluation_date            TEXT NOT NULL,
    total_score                INTEGER NOT NULL,
    level                      TEXT NOT NULL,
    volume_dry_score           INTEGER NOT NULL,
    price_stable_score         INTEGER NOT NULL,
    current_close              REAL NOT NULL,
    v3                         REAL,
    v5                         REAL,
    v10                        REAL,
    v20                        REAL,
    volume_ratio_5_20          REAL,
    volume_percentile          REAL,
    volume_percentile_days     INTEGER,
    range_5                    REAL,
    close_range_5              REAL,
    return_3                   REAL,
    return_5                   REAL,
    trend_type                TEXT NOT NULL,
    ma20                       REAL,
    ma60                       REAL,
    ma20_slope                 REAL,
    return_20                  REAL,
    key_support                REAL NOT NULL,
    buy_zone_low               REAL NOT NULL,
    buy_zone_high              REAL NOT NULL,
    stop_loss                  REAL NOT NULL,
    risk_ratio                 REAL NOT NULL,
    risk_level                 TEXT NOT NULL,
    score_reasons              TEXT,
    reject_reasons             TEXT,
    data_source                TEXT,
    created_at                 TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (task_id) REFERENCES scan_tasks(id),
    UNIQUE (task_id, code)
);
```

JSON数组字段 `score_reasons` 和 `reject_reasons` 使用 JSON 字符串存储，并通过统一序列化函数读写。

### 6.3 索引设计

```sql
CREATE INDEX IF NOT EXISTS idx_strategy2_candidates_task_score
ON strategy2_candidates(task_id, total_score DESC);

CREATE INDEX IF NOT EXISTS idx_strategy2_candidates_task_risk
ON strategy2_candidates(task_id, risk_ratio ASC);
```

### 6.4 数据兼容方案

- 使用与现有 `_ensure_scan_task_columns()` 一致的兼容式字段检查。
- 旧数据库首次启动时自动创建策略2候选表和索引。
- 旧 `scan_tasks.strategy_type` 为空时，API 层按 `STRATEGY_1_CUP_HANDLE` 返回。
- 不迁移、不复制、不删除现有 `candidates` 数据。
- 不修改 `daily_ohlc` 数据格式。

---

## 7. 接口设计方案

### 7.1 新增接口

#### 启动策略2扫描

```http
POST /api/strategy2/scans
```

成功返回：

```json
{
  "taskId": "20260610-153000",
  "strategyType": "STRATEGY_2_EXTREME_DRY_STABLE",
  "status": "running"
}
```

扫描冲突返回 HTTP 409：

```json
{
  "error": "SCAN_ALREADY_RUNNING",
  "message": "当前已有全市场扫描任务正在运行",
  "runningTaskId": "20260610-152000",
  "runningStrategyType": "STRATEGY_1_CUP_HANDLE"
}
```

#### 查询策略2扫描状态

```http
GET /api/strategy2/scans/status
```

```json
{
  "running": true,
  "taskId": "20260610-153000",
  "strategyType": "STRATEGY_2_EXTREME_DRY_STABLE",
  "stats": {
    "totalStocks": 5000,
    "processed": 1200,
    "skipped": 300,
    "failed": 8,
    "candidatesFound": 15
  }
}
```

#### 查询策略2任务

```http
GET /api/strategy2/tasks
```

只返回 `strategy_type = STRATEGY_2_EXTREME_DRY_STABLE` 的任务。

#### 查询策略2候选

```http
GET /api/strategy2/candidates?task_id={taskId}
```

默认按总分降序、风险比升序返回。

#### 查询策略2候选详情

```http
GET /api/strategy2/candidates/{code}?task_id={taskId}
```

返回候选完整指标、评分原因和风险信息。该接口只读取已保存的策略2结果，不调用策略1重新分析。

### 7.2 修改接口

现有策略1启动接口保持兼容，但创建任务时明确写入：

```text
strategy_type = STRATEGY_1_CUP_HANDLE
```

现有全局扫描状态返回中增加 `strategyType`，前端据此显示当前运行策略。

配置接口支持读取和保存 `strategy2` 配置段，并执行后端校验。

### 7.3 接口兼容要求

- 保留现有策略1接口路径和返回字段。
- 新字段只做向后兼容式增加。
- 策略2接口不得从现有 `candidates` 表读取数据。
- 非策略2任务 ID 请求策略2候选接口时返回 HTTP 404 或明确的任务类型错误。

---

## 8. 可以实施的代码方案

### 8.1 后端代码方案

#### 需要新增的模块

- `strategy2/models.py`
- `strategy2/indicators.py`
- `strategy2/scorer.py`
- `strategy2/rejection.py`
- `strategy2/risk.py`
- `strategy2/trend.py`
- `strategy2/engine.py`
- `strategy2/scanner.py`
- `scanner/daily_data_service.py`
- 对应测试文件

#### 需要修改的模块

- `config.yaml`：新增 `strategy2` 配置段。
- `scanner/db.py`：新增任务类型字段、策略2候选表及 CRUD。
- `scanner/engine.py`：改用共享日线服务，保持策略1行为不变。
- `server.py`：新增策略2接口和全局扫描互斥的策略类型信息。
- 前端 API、路由、导航、扫描控制台、配置页。

#### 策略2配置

```yaml
strategy2:
  enabled: true
  strategy_window_days: 120
  minimum_required_days: 60
  candidate_min_score: 70
  max_risk_ratio: 0.05
  support_lookback_days: 10
  buy_zone_max_premium: 0.03
  stop_loss_buffer: 0.03
```

后端必须校验：

- `minimum_required_days >= 60`
- `strategy_window_days >= minimum_required_days`
- `strategy_window_days <= liquidity.min_listing_days`
- `candidate_min_score` 在 `[0, 100]`
- `max_risk_ratio` 在 `(0, 1)`
- `support_lookback_days >= 2`
- 买入溢价和止损缓冲在合理范围 `(0, 0.20]`

#### 唯一策略评估入口

```text
ExtremeDryStableStrategyEngine.evaluate_at(data, code, name)
1. 只保留评估日及之前的数据。
2. 校验数据长度、排序、字段和值。
3. 截取 strategy_window_days。
4. 计算策略2指标。
5. 执行走势趋势判断；下降趋势直接返回 `DOWNTREND_FILTERED`。
6. 计算 key_support 和风险指标。
7. 计算量干分、价稳分和总分。
8. 执行一票否决规则。
9. 判断总分和风险比是否达标。
10. 返回 Strategy2Evaluation。
```

`Strategy2Evaluation` 至少包含：

```text
passed
status_reason
indicators
volume_dry_score
price_stable_score
total_score
level
score_reasons
reject_reasons
risk
trend
```

#### 独立性约束

- `strategy2/` 下任何文件不得导入策略1判断模块。
- 策略2测试增加导入边界检查，扫描 `strategy2/` 的导入语句。
- 共享模块不得导入 `strategy2` 或任何策略1判断模块。
- `strategy2/scanner.py` 只协调共享数据能力和策略2引擎。

#### 扫描编排

```text
scan_strategy2_all()
1. 获取或接收股票池。
2. 保存 task_stocks。
3. 使用共享日线服务拉取 min_listing_days。
4. 使用完整拉取窗口执行全局流动性过滤。
5. 调用 ExtremeDryStableStrategyEngine.evaluate_at() 执行趋势过滤和策略判断。
6. 下降趋势时写入 `DOWNTREND_FILTERED` 并继续下一只股票。
7. candidate 时 upsert 到 strategy2_candidates。
8. 未入选时写入稳定 status_reason。
9. 单股异常时标记 failed 并继续。
10. 汇总任务统计并完成任务。
```

#### 并发控制

- 继续使用单一全局扫描运行状态，不为策略2创建第二套可并行状态。
- 创建任务前检查内存运行状态和数据库运行任务。
- 任一策略任务为 `running` 时，另一策略启动请求返回 HTTP 409。
- 数据源互斥、重试和释放锁沿用共享日线服务。
- `strategy2_candidates` 使用 `(task_id, code)` 唯一约束保证幂等写入。

#### 缓存策略

- 策略2沿用现有日线数据库持久化。在线拉取成功时数据与数据库历史合并保存。
- 全部在线源失败时直接标记失败，不进行缓存新鲜度判断，不使用缓存扫描。
- 流动性过滤使用完整拉取窗口。
- 策略2计算只使用策略窗口，不能因缓存中数据更多而扩大计算范围。
- 三数据源均失败时，直接标记股票失败（`ALL_DATA_SOURCES_FAILED`），不使用缓存继续扫描。缓存仅在在线拉取成功后用于合并与持久化。

### 8.2 前端代码方案

#### 页面状态

策略2扫描状态至少包含：

```js
{
  taskId: null,
  strategyType: 'STRATEGY_2_EXTREME_DRY_STABLE',
  running: false,
  totalStocks: 0,
  processed: 0,
  skipped: 0,
  failed: 0,
  candidatesFound: 0,
  discoveries: []
}
```

#### 扫描控制台

- 将单一启动按钮调整为两个明确命名的策略启动按钮。
- 两个按钮调用不同启动接口。
- 轮询全局状态后，根据 `strategyType` 显示当前运行策略。
- 任一任务运行时两个按钮同时禁用。
- 策略2发现卡片不得引用杯柄/VCP字段。

#### 配置页

- 保留现有全局基础参数和策略1参数。
- 新增独立策略2分区，绑定 `config.strategy2`。
- 保存 payload 时明确包含 `strategy2`。
- 增加策略2窗口与 `min_listing_days` 的前端校验。
- 不将策略2字段放入 `decision`、`volume_dry`、`price_stable` 等策略1配置段。

#### 策略2结果页

- 新增路由和导航入口。
- 通过策略2独立接口加载任务和候选。
- 展示策略2等级、评分、指标和风险字段。
- 支持按总分、风险比排序。
- 页面空状态明确提示“当前策略2任务没有候选”，不显示策略1结果。

---

## 9. 日志与异常处理方案

### 9.1 必须记录的日志

- 策略2任务创建、开始、完成、失败日志。
- 任务 ID、策略类型、配置摘要和策略窗口。
- 数据源尝试、回退、缓存使用和全部失败日志。
- 单股数据不足、流动性过滤、评分不足、一票否决和风险超限原因。
- 单股趋势分类、趋势指标和下降趋势过滤原因。
- 策略2候选写入失败日志。
- 全局扫描冲突日志。
- 非法配置拒绝日志。

### 9.2 异常处理

- 单只股票异常不得导致整体任务失败。
- 数据必须按日期升序整理；重复日期按现有标准化逻辑处理。
- 必需字段缺失、非数字、非正价格或负成交量时，返回 `INVALID_MARKET_DATA`。
- `V20 = 0` 等无法计算比率的情况不得抛出除零异常，应按无效数据排除。
- 无法获得足够历史数据计算关键支撑时，返回 `INSUFFICIENT_STRATEGY_DATA`。
- 数据源全部失败时返回 `ALL_DATA_SOURCES_FAILED`，不使用本地缓存。
- 任务级异常必须保存 traceback 到日志，并将任务标记为 `failed`。
- 前端显示用户可理解的错误文案，同时保留稳定错误码用于排查。

---

## 10. 测试方案

### 10.1 单元测试

#### 指标测试

- V3/V5/V10/V20 计算正确。
- V5/V20 边界值 `0.60`、`0.50` 正确计分。
- `V3 < V5 < V10 < V20` 严格不等式正确。
- 60日成交量分位正确；不足60日时记录实际窗口。
- `range_5`、`close_range_5`、`return_3`、`return_5` 正确。
- 指标只使用评估日及之前数据。

#### 评分测试

- 量干满分50、价稳满分50、总分不超过100。
- 累加评分项正确。
- 70、80、90、95分等级边界正确。
- 命中评分项可解释且稳定。

#### 趋势过滤测试

- 当前价低于MA20、MA20低于MA60、MA20斜率为负且20日跌幅低于-5%时，判定为 `DOWNTREND`。
- 四个下降条件缺少任意一项时，判定为 `UPTREND_OR_SIDEWAYS`。
- 下降趋势返回 `DOWNTREND_FILTERED`，且不进入量干价稳评分。
- 上涨和横盘股票允许继续评分。
- MA20、MA60、MA20斜率和20日涨跌幅只使用评估日及之前的数据。

#### 否决规则测试

- `return_5 < -5%` 否决。
- 放量单日跌幅 `<= -4%` 否决。
- `range_5 > 8%` 否决。
- 当前价低于 `key_support` 否决。
- `return_3 >= 8%` 否决。
- 多个否决原因可同时返回。

#### 风险测试

- `key_support` 明确排除评估日。
- 买入区间、止损价、风险比正确。
- 风险比3%和5%边界正确。
- 风险比超过5%不入选。

#### 独立性测试

- `strategy2/` 不导入策略1判断模块。
- 修改或 mock 策略1判断结果不会影响策略2结果。
- 策略2不读取现有 `candidates` 表。

### 10.2 接口测试

- 启动策略2扫描成功。
- 策略2禁用时拒绝启动。
- 配置非法时拒绝启动。
- 策略1运行中启动策略2返回409。
- 策略2运行中启动策略1返回409。
- 重复启动策略2返回当前运行任务。
- 状态接口返回正确策略类型和进度。
- 任务接口只返回策略2任务。
- 候选列表和详情只返回策略2候选。
- 使用策略1任务 ID 查询策略2结果时明确拒绝。
- 配置接口可保存和读取策略2配置。

### 10.3 集成测试

1. 创建策略2任务。
2. 获取股票池。
3. 三数据源按现有机制参与日线获取。
4. 日线按统一格式入库。
5. 执行全局流动性过滤。
6. 截取策略2计算窗口。
7. 执行策略2独立走势趋势过滤。
8. 对上涨或横盘股票执行策略2独立评估并写入候选。
9. API 查询任务和候选。
10. 前端展示策略2结果。

额外验证：

- 单股数据源失败不影响后续股票。
- 单股策略异常不影响整体任务。
- 候选重复发现时保持幂等。
- 旧数据库升级后策略1和策略2均可运行。

### 10.4 前端测试

- 配置页明确区分策略1和策略2。
- 策略2配置保存、刷新和校验。
- 点击策略2启动按钮。
- 策略1运行时策略2按钮禁用。
- 策略2运行时策略1按钮禁用。
- 页面刷新后恢复当前策略名称和进度。
- 策略2结果页展示正确字段。
- 策略2结果页展示趋势类型和趋势指标。
- 空结果、接口失败、任务失败提示。
- 策略2页面不显示杯柄/VCP字段。

### 10.5 回归测试

- 策略1扫描结果和判断逻辑不变。
- 现有策略1接口仍可使用。
- 现有 `candidates` 数据仍可展示。
- 三数据源、缓存、流动性过滤行为不变。
- 现有回测功能不受影响。
- 配置页原有参数仍可保存。
- 旧任务缺少 `strategy_type` 时按策略1展示。
- 前端构建通过。

### 10.6 建议验证命令

```bash
python -m pytest tests/ -v
cd web && npm run build
```

实现阶段应优先运行策略2新增测试和相关回归测试，最终再运行全量测试。

---

## 11. 验收标准

1. 用户可以独立启动策略2全市场扫描。
2. 策略2扫描全部股票池，并继续使用全局流动性过滤。
3. 策略2不依赖任何策略1判断结果。
4. 策略2配置、任务类型、候选表、API 和结果页面独立。
5. 策略2使用独立 `strategy_window_days`，日线拉取继续使用 `min_listing_days`。
6. `key_support` 使用不含评估日的前10个交易日最低收盘价。
7. 只有非下降趋势、总分不低于70、无一票否决且风险比不高于5%的股票入选。
8. 任一全市场扫描运行时，另一策略不能启动。
9. 单股失败不中断整体任务，失败原因可追踪。
10. 策略1现有判断、结果、接口和回测不受影响。
11. 核心规则、接口、集成流程和前端交互均有测试。
12. 全量后端测试和前端构建通过。

---

## 12. 给 Claude Code / Codex 的执行指令

请严格按照本文档执行开发。

1. 必须在独立 Git worktree 和 `codex/` 前缀分支中开发。
2. 先阅读当前项目结构和相关测试，再开始修改。
3. 至少参考现有全市场扫描编排、数据库兼容迁移、配置页保存校验三类实现模式。
4. 使用测试驱动方式逐步实现策略2核心计算。
5. 优先抽取真正共享的数据拉取基础能力，不把策略2接入策略1判断模块。
6. `strategy2/` 不得导入策略1形态、评分、分析或决策模块。
7. 不重构无关模块，不删除已有业务逻辑。
8. 数据库只允许兼容式新增表、字段和索引。
9. 每完成一个模块后运行对应测试。
10. 所有关键逻辑必须有明确错误码、日志和测试。
11. 所有计算必须限制在评估日及之前，防止未来数据泄漏。
12. 如文档与现有代码冲突，以最小改动保持现有功能为原则，但不得破坏策略2独立边界。
13. 开发完成后运行全量后端测试和前端构建。
14. 如实记录执行结果、失败和遗留问题。

建议实施顺序：

1. 建立策略2模型、指标、评分、否决和风险计算测试。
2. 实现策略2唯一评估入口及独立性测试。
3. 抽取共享日线数据服务并完成策略1回归测试。
4. 扩展数据库任务类型和策略2候选存储。
5. 实现策略2扫描器和全局互斥。
6. 实现策略2 API。
7. 实现前端配置、扫描入口和独立结果页。
8. 执行全量测试、构建和人工验收。

---

## 13. 最终交付物

开发完成后，需要交付：

1. 独立 worktree、分支名称和提交记录。
2. 修改文件清单。
3. 策略2核心规则和独立边界说明。
4. 新增配置项说明。
5. 新增及修改接口说明。
6. 数据库变更说明。
7. 数据拉取和缓存复用说明。
8. 前端页面与交互变更说明。
9. 测试命令和测试结果。
10. 策略1回归验证结果。
11. 已知遗留问题和后续优化建议。

---

## 14. 已确认决策记录

1. 策略2独立扫描全部股票，不以前置杯柄/VCP识别为条件。
2. 策略2共享基础设施，但业务判断链路完全独立。
3. 策略2使用独立扫描入口、任务类型、候选结果、API 和前端视图。
4. 策略1与策略2分别启动，但同一时间只允许一个全市场扫描任务。
5. 策略2本期不开发回测。
6. 策略2使用现有全局流动性过滤。
7. 策略2新增独立 `strategy_window_days` 和 `minimum_required_days`。
8. `key_support` 使用不包含评估日的前10个交易日最低收盘价。
9. 风险比超过5%时强制排除。
10. 入选要求为总分至少70、无一票否决、风险比不超过5%。
11. 前端配置页必须明确区分策略2配置。
12. 开发必须新建独立 worktree 分支。
13. 策略2新增独立走势趋势过滤；下降趋势强制排除，只允许上涨或横盘股票进入候选。

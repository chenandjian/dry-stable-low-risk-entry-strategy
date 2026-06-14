# 开发方案文档：策略1历史回测实验与正式策略优化

## 1. 需求背景

### 1.1 当前问题

策略1是当前项目最早的核心策略，定位为 A 股杯柄结构和 VCP 机会扫描。现有代码已经具备：

- 全市场扫描：`scanner/engine.py`
- 统一策略入口：`CupHandleStrategyEngine.evaluate_at()`
- 杯柄识别：`scanner/pattern_detector.py`
- 杯柄/VCP评分与干稳低吸分析：`scanner/scorer.py`、`analyzer/*`
- 批量历史回测：`scanner/backtester.py`
- 单股杯柄回测：`scanner/single_stock_backtest.py`
- 前端扫描与单股回测页面

但策略1当前优化能力还不够完整，主要问题是：

- 批量回测仍偏离“可信基线 + 实验对比 + 正式升级”的闭环。
- 当前回测没有像策略2一样保存任务级 `config_snapshot`、`experiment_snapshot`、可信度状态和对比结果。
- 当前 `scanner/backtester.py` 仍包含 60 日观察口径，不完全贴合用户短线操作偏好。
- 当前回测统计更偏基础收益统计，缺少对杯体、柄部、突破、VCP、量干、价稳、风险、市场环境等维度的系统分组研究。
- 参数建议目前较粗，只分析杯深和分数阈值，不能支撑正式策略参数调整。
- 策略1正式参数调整需要基于历史数据研究，而不是凭直觉直接改 `config.yaml`。

### 1.2 用户痛点

- 不知道当前杯柄/VCP策略选出的股票后续表现是否稳定。
- 不知道哪些参数真正影响收益和止损率。
- 不知道应该调杯体深度、柄部深度、评分门槛、干稳门槛，还是风险门槛。
- 不希望只看单只股票或少量样本主观调参。
- 希望参考策略2的优化方式：先通过历史数据回测研究，再形成优化策略，最后由 Codex 直接启用正式版本。

### 1.3 业务目标

本次目标不是直接修改策略1，而是先建设策略1的可信历史回测和实验优化体系，然后由 Codex 根据数据研究结果决定正式策略参数，并在满足证据门槛后直接启用策略1优化版本。

完整闭环：

```text
建设策略1可信回测
→ 建设策略1实验层
→ 运行全市场可信基线
→ 运行多组实验任务
→ 分析历史数据和分组表现
→ Codex 确定正式优化参数
→ 修改策略1正式配置或规则
→ 运行测试和回归
→ 交付优化后的策略1正式策略文档
→ 直接启用为策略1正式版本
```

### 1.4 预期效果

- 策略1拥有与策略2类似的可信回测、实验对比和正式升级流程。
- 用户不需要手动决定最终参数。
- Codex 可以基于历史回测数据自主决定策略1优化参数。
- 正式启用后必须输出优化后的策略文档，明确所有参数名、参数值、证据和回滚方案。

---

## 2. 需求目标

### 2.1 必须实现

- 新增策略1可信回测任务体系。
- 策略1回测必须只读取本地数据库 `daily_ohlc`，禁止因回测数据不足请求外部数据源。
- 策略1回测必须调用唯一策略入口 `CupHandleStrategyEngine.evaluate_at()`。
- 保存回测任务、股票状态、原始信号、合并机会、数据不足股票和汇总统计。
- 保存 `config_snapshot`、`experiment_snapshot`、策略版本和数据版本。
- 支持基线任务可信度状态：
  - `TRUSTED_BASELINE`
  - `EXPERIMENTAL`
  - `LEGACY_UNTRUSTED`
  - `INCOMPLETE`
- 支持策略1实验参数，不直接污染正式扫描配置。
- 支持实验任务与可信基线任务对比。
- 支持按杯体、柄部、突破、VCP、评分、干稳、风险、市场环境分组统计。
- 支持 Codex 根据实验结果直接调整策略1正式配置或正式规则。
- 正式策略启用后必须交付优化后的策略1正式策略文档。

### 2.2 可选增强

- 参数网格批量实验。
- 多任务排行榜。
- 行业、板块、市值分组。
- CSV 导出。
- 组合收益曲线。
- 手续费、印花税、滑点模拟。

可选增强不作为本期验收阻塞项。

### 2.3 不做范围

- 不修改策略2。
- 不把策略2的量干价稳参数直接套到策略1。
- 不复制 `CupHandleStrategyEngine.evaluate_at()` 形成第二份策略1代码。
- 不在回测中调用百度、新浪、腾讯、yfinance、AKShare 或任何外部数据源。
- 不基于旧的非可信回测结果直接调整正式策略。
- 不在没有测试、证据和回滚方案时启用正式版本。
- 不实现自动交易。

---

## 3. 默认假设

1. 策略1正式判断入口是 `CupHandleStrategyEngine.evaluate_at()`。
2. 策略1包含完整杯柄和 VCP-only 补位机会。
3. `data.scan_window_days` 控制扫描策略窗口。
4. `data.backtest_window_days` 控制回测判断窗口。
5. `liquidity.min_listing_days` 控制日线拉取天数、上市天数检查和流动性过滤。
6. 当前用户偏短线操作，策略1优化重点观察 3/5/10/20 个交易日，不把 60 日作为核心成功口径。
7. 策略1回测判断日只能使用判断日及以前数据。
8. 未来行情只用于计算信号产生后的表现，不得进入策略判断。
9. 可信基线和实验任务必须使用相同股票范围、日期范围、执行模型和数据版本。
10. 用户已授权 Codex：策略1优化完成后，可以直接作为策略1正式版本启用，不需要再次确认具体参数。
11. 策略1开发必须使用独立 worktree 和独立分支，不得在 `strategy2-extreme-dry-stable` worktree 中开发。

### 3.1 开发分支与 Worktree 流程

本需求属于策略1独立回测实验和正式策略优化，必须按主流隔离开发流程新建独立 worktree。

推荐分支：

```text
codex/strategy1-backtest-experiment-optimization
```

推荐 worktree 路径：

```text
D:\game\claude\dry-stable-low-risk-entry-strategy\.claude\worktrees\strategy1-backtest-experiment-optimization
```

禁止在以下 worktree 中开发策略1：

```text
D:\game\claude\dry-stable-low-risk-entry-strategy\.claude\worktrees\strategy2-extreme-dry-stable
```

实现阶段开始前必须先检查：

```powershell
git rev-parse --show-toplevel
git rev-parse --git-dir
git rev-parse --git-common-dir
git branch --show-current
git status --short
```

如果当前已经在 linked worktree 中：

- 若分支是策略1专属分支，可以继续。
- 若分支是策略2或其他功能分支，必须切换到策略1独立 worktree。

进入策略1 worktree 后，先运行基线验证，再开发：

```powershell
python -m pytest tests/test_backtester.py tests/test_cuphandle_strategy_engine.py tests/test_single_stock_backtest.py -q
```

如果时间允许，再运行：

```powershell
python -m pytest tests -q
```

前端改动前后需要运行：

```powershell
cd web
npm run build
```

提交规则：

- 策略1文档、策略1功能代码、策略1正式启用应尽量分开提交。
- 不提交策略2无关改动。
- 不提交其他 worktree 目录内容。
- 如果主工作区已有其他 worktree 显示 dirty，不处理、不回退，除非它直接阻塞策略1开发。

### 3.2 股票数据来源与复制规则

策略1回测实验使用现有已存储股票数据，不重新请求外部行情源。开发开始后，必须从策略2 worktree 的数据目录复制 SQLite 数据快照到策略1独立 worktree。

源数据目录：

```text
D:\game\claude\dry-stable-low-risk-entry-strategy\.claude\worktrees\strategy2-extreme-dry-stable\data
```

目标数据目录：

```text
D:\game\claude\dry-stable-low-risk-entry-strategy\.claude\worktrees\strategy1-backtest-experiment-optimization\data
```

必须复制的文件：

```text
cuphandle.db
cuphandle.db-wal
cuphandle.db-shm
```

复制要求：

1. `cuphandle.db`、`cuphandle.db-wal`、`cuphandle.db-shm` 必须作为同一个 SQLite 快照一起复制，不能只复制主库文件。
2. 复制前优先停止正在写入源数据库的后端、扫描或回测进程，避免复制到不一致的 WAL 状态。
3. 如果无法确认源库处于静止状态，必须使用 SQLite backup API 或等效一致性备份方式生成快照。
4. `test_prog_debug.db` 不是全市场策略1回测数据源，除非后续明确要求调试单测，否则不要复制或使用。
5. 策略1 worktree 的 `config.yaml` 必须指向本地复制后的数据库：`data.database_path: ./data/cuphandle.db`。
6. 策略1回测、实验、正式参数研究只允许读取目标 worktree 下复制出的本地库。
7. 禁止在策略1回测实验过程中调用百度、新浪、腾讯、yfinance、AKShare、Tushare 或任何外部行情源补数据。
8. 数据不足的股票必须进入回测任务的“数据不足/不可观察”明细，并在前端或任务详情中列出，不得静默触发在线拉取。
9. 策略1回测新增表、实验任务表和汇总表只能写入策略1 worktree 的复制库，禁止写回 `strategy2-extreme-dry-stable\data` 源库。

每个策略1回测任务必须记录数据快照信息：

- 源数据库路径。
- 快照复制时间。
- `daily_ohlc` 最大交易日期。
- 股票池数量。
- `daily_ohlc` 行数。
- 可选：`cuphandle.db` 文件大小或 hash。

---

## 4. 产品设计方案

### 4.1 用户使用流程

1. 用户进入“策略1回测优化”页面。
2. 用户选择回测日期范围和股票范围。
3. 用户先运行“可信基线”任务。
4. 系统使用当前正式策略1配置执行全市场历史回测。
5. 基线完成后，用户或 Codex 启动实验任务。
6. 实验任务只改变实验参数，不直接修改正式扫描配置。
7. 系统生成基线和实验对比。
8. Codex 分析结果，确定正式策略优化参数。
9. Codex 修改正式策略1配置或规则。
10. 系统运行测试和必要回归。
11. Codex 输出优化后的策略1正式策略文档。
12. 优化策略直接启用为策略1正式版本。

### 4.2 页面展示要求

#### 回测任务区

- 任务 ID。
- 任务类型：`BASELINE / EXPERIMENT`。
- 可信度状态。
- 策略版本。
- 数据版本。
- 请求区间。
- 实际评估区间。
- 股票范围。
- 处理进度。
- 原始信号数。
- 合并机会数。
- 数据不足股票数。
- 失败股票数。

#### 实验配置区

实验模式开启后展示：

- `EXPERIMENTAL` 标识。
- “实验不会影响正式扫描规则”的提示。
- 评分门槛实验。
- 杯体结构实验。
- 柄部结构实验。
- 突破确认实验。
- 干稳低吸实验。
- 风险收益实验。
- 执行模型实验。

#### 对比分析区

展示基线 vs 实验：

- 机会数变化。
- 实际入场数变化。
- 3/5/10/20 日成功率变化。
- 平均实际收益变化。
- 中位实际收益变化。
- 止损率变化。
- 假突破率变化。
- 跑赢市场比例变化。
- 按月份、形态类型、分数段、风险段、市场环境分组表现。

### 4.3 交互规则

- 实验任务必须显示 `EXPERIMENTAL`。
- 基线任务必须实验关闭。
- 只有完整性通过的新任务才能标记 `TRUSTED_BASELINE`。
- 对比接口必须校验可比性，不可比较时不得展示误导性差值。
- 正式策略启用后，页面必须展示当前策略1版本和优化说明链接。

---

## 5. 技术架构方案

### 5.1 总体架构

```text
前端策略1回测优化页
  -> 策略1回测 API
  -> strategy1 backtest service
  -> 读取本地 stock_pool + daily_ohlc
  -> 历史时点流动性过滤
  -> CupHandleStrategyEngine.evaluate_at()
  -> 保存原始信号
  -> 合并连续机会
  -> 计算 NEXT_OPEN 执行与 3/5/10/20 日表现
  -> 实验过滤与分组统计
  -> 基线对比
  -> 正式策略升级
  -> 优化后策略文档
```

### 5.2 涉及模块

建议新增：

- `scanner/strategy1_backtest_models.py`
- `scanner/strategy1_backtester.py`
- `scanner/strategy1_backtest_service.py`
- `scanner/strategy1_backtest_experiments.py`
- `docs/superpowers/specs/YYYY-MM-DD-strategy1-optimized-strategy-parameters.md`

建议修改：

- `scanner/db.py`
- `server.py`
- `web/src/pages/StrategyConfig.vue`
- `web/src/pages/SingleStockBacktest.vue`
- `web/src/pages/TaskCenter.vue`
- 新增或扩展策略1回测页面

### 5.3 唯一策略入口

策略判断必须使用：

```python
evaluation = CupHandleStrategyEngine(config_snapshot).evaluate_at(
    strategy_data,
    code=code,
    name=name,
    market_data=market_window,
)
```

调用方只负责：

- 准备历史窗口。
- 准备市场环境窗口。
- 调用策略引擎。
- 保存结果。
- 计算未来表现。

调用方不得重复实现：

- 杯柄识别。
- VCP 判断。
- 评分门槛。
- dry-stable 决策。
- 候选准入。
- 突破排除。

### 5.4 回测数据流

1. 后端创建策略1回测任务。
2. 冻结 `config_snapshot` 和 `experiment_snapshot`。
3. 从本地 `stock_pool` 获取股票范围。
4. 从本地 `daily_ohlc` 获取股票历史日线。
5. 对每个历史判断日：
   - 取判断日及以前数据。
   - 检查是否满足 `backtest_window_days`。
   - 截取最后 `backtest_window_days`。
   - 使用判断日及以前市场指数数据。
   - 执行历史时点流动性过滤。
   - 调用 `CupHandleStrategyEngine.evaluate_at()`。
   - 保存通过的原始信号。
   - 保存未通过原因统计。
6. 对原始信号做机会合并。
7. 使用下一交易日开盘作为默认模拟入场。
8. 计算 3/5/10/20 日短线表现。
9. 生成汇总、漏斗、分组统计和市场基准对比。

### 5.5 状态设计

任务状态：

- `created`
- `running`
- `completed`
- `completed_with_errors`
- `interrupted`
- `failed`
- `canceled`

可信度状态：

- `TRUSTED_BASELINE`
- `EXPERIMENTAL`
- `LEGACY_UNTRUSTED`
- `INCOMPLETE`

机会执行状态：

- `SIGNAL_ONLY`
- `ENTERED`
- `NO_ENTRY_ABOVE_BUY_ZONE`
- `NO_ENTRY_GAP_BELOW_STOP`
- `UNOBSERVED_ENTRY`
- `NO_ENTRY_CONFIRMATION`

结果状态：

- `TARGET`
- `STOP`
- `TIME_EXIT`
- `UNRESOLVED`
- `UNOBSERVED`

---

## 6. 策略1实验设计方案

### 6.1 实验原则

- 所有实验参数先作用于回测实验层。
- 实验关闭时必须等同正式策略1基线。
- 实验任务不得标记为 `TRUSTED_BASELINE`。
- 实验结论必须与可信基线同条件比较。
- 正式策略升级必须输出最终参数和证据。

### 6.2 实验一：形态评分门槛

候选参数：

```yaml
experiment:
  minimum_total_score: null | 60 | 70 | 80
```

研究问题：

- 当前策略1实际候选门槛是否过松。
- 高分候选是否显著降低假突破率。
- 高分候选是否导致机会数过少。

### 6.3 实验二：杯体结构参数

候选参数：

```yaml
experiment:
  cup_min_depth: null | 0.12 | 0.15
  cup_max_depth: null | 0.33 | 0.40 | 0.45
  cup_min_duration: null | 35 | 50
  cup_max_duration: null | 120 | 180
  max_lip_deviation: null | 0.05 | 0.08 | 0.12
  min_bottom_roundness: null | 0.15 | 0.20
```

研究问题：

- 杯太浅是否没有足够洗盘。
- 杯太深是否弱势或修复时间不足。
- 杯口偏差是否影响后续突破质量。
- 圆弧底比例是否能降低假形态。

### 6.4 实验三：柄部结构参数

候选参数：

```yaml
experiment:
  handle_min_duration: null | 5 | 8
  handle_max_duration: null | 20 | 30
  handle_max_depth: null | 0.10 | 0.12 | 0.18
  handle_max_vs_right_rally: null | 0.33 | 0.50
```

研究问题：

- 柄部过短是否容易假突破。
- 柄部过深是否代表抛压未释放。
- 柄部回撤占右侧上涨过高是否降低成功率。

### 6.5 实验四：突破确认

候选参数：

```yaml
experiment:
  breakout:
    mode: NONE | PRICE_ONLY | PRICE_AND_VOLUME | NEAR_PIVOT
    buffer_pct: null | 0.01 | 0.02 | 0.03
    volume_multiplier: null | 1.2 | 1.5 | 2.0
```

研究问题：

- 策略1应该偏低吸观察，还是等待突破确认。
- 放量突破是否真的提升短线表现。
- 价格接近 pivot 但未突破是否更适合作为观察候选。

### 6.6 实验五：干稳低吸门槛

候选参数：

```yaml
experiment:
  decision:
    min_pattern_score: null | 8 | 10 | 13
    min_volume_dry_score: null | 6 | 7 | 8 | 9
    min_price_stable_score: null | 5 | 6 | 7
    allowed_verdict_keys:
      - BUY_LOW
      - WATCH_BREAKOUT
      - WAIT_ENTRY
```

研究问题：

- 当前允许的候选状态是否过宽。
- `WAIT_ENTRY` 是否应该保留为正式候选。
- 高量干/高价稳是否显著改善短线表现。

### 6.7 实验六：风险收益门槛

候选参数：

```yaml
experiment:
  risk:
    max_risk_percent: null | 6 | 8 | 10
    low_buy_max_risk_percent: null | 4 | 6
    min_rr1: null | 1.5 | 2.0 | 2.5
    max_chase_pct: null | 3 | 5
```

研究问题：

- 风险更小是否能提高收益质量。
- RR1 过高是否导致候选过少或目标不现实。
- 追高过滤是否能降低回撤。

### 6.8 实验七：形态类型分组

机会类型：

- `CUP_HANDLE`
- `VCP_ONLY`
- `LOW_BUY`
- `WATCH_BREAKOUT`
- `WAIT_ENTRY`

初期只分组统计，不直接过滤。若某类长期显著弱于基线，后续可升级为正式过滤或降权。

### 6.9 实验八：执行模型和短线退出

执行模型：

```yaml
experiment:
  execution_model: NEXT_OPEN | SIGNAL_CLOSE_DIAGNOSTIC
  time_exit_days: null | 3 | 5 | 10
```

要求：

- 可信基线默认使用 `NEXT_OPEN`。
- `SIGNAL_CLOSE_DIAGNOSTIC` 只用于诊断，不作为正式结论。
- 时间退出不覆盖更早触发的目标或止损。

---

## 7. 数据库设计方案

### 7.1 新增策略1回测任务表

```sql
CREATE TABLE IF NOT EXISTS strategy1_backtest_tasks (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    credibility_status TEXT,
    requested_start_date TEXT,
    requested_end_date TEXT,
    actual_evaluation_start_date TEXT,
    actual_evaluation_end_date TEXT,
    observation_data_end_date TEXT,
    scope_type TEXT,
    requested_codes TEXT,
    max_stocks INTEGER,
    config_snapshot TEXT NOT NULL,
    experiment_snapshot TEXT,
    baseline_task_id TEXT,
    comparison_summary_json TEXT,
    strategy_engine_version TEXT,
    backtest_engine_version TEXT,
    data_revision_version TEXT,
    data_revision_id TEXT,
    execution_model TEXT,
    total_stocks INTEGER DEFAULT 0,
    processed_stocks INTEGER DEFAULT 0,
    failed_stocks_count INTEGER DEFAULT 0,
    insufficient_stocks_count INTEGER DEFAULT 0,
    raw_signals_count INTEGER DEFAULT 0,
    opportunities_count INTEGER DEFAULT 0,
    summary_json TEXT,
    started_at TEXT,
    finished_at TEXT,
    elapsed_seconds REAL,
    error TEXT
);
```

### 7.2 新增股票状态表

```sql
CREATE TABLE IF NOT EXISTS strategy1_backtest_task_stocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT,
    status TEXT NOT NULL,
    available_days INTEGER DEFAULT 0,
    required_days INTEGER DEFAULT 0,
    earliest_date TEXT,
    latest_date TEXT,
    actual_start_date TEXT,
    actual_end_date TEXT,
    raw_signals_count INTEGER DEFAULT 0,
    opportunities_count INTEGER DEFAULT 0,
    evaluation_days INTEGER DEFAULT 0,
    filtered_days INTEGER DEFAULT 0,
    error_code TEXT,
    error_detail TEXT,
    UNIQUE(task_id, code)
);
```

### 7.3 新增原始信号表

```sql
CREATE TABLE IF NOT EXISTS strategy1_backtest_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT,
    evaluation_date TEXT NOT NULL,
    evaluation_index INTEGER NOT NULL,
    pattern_kind TEXT,
    score INTEGER,
    cup_depth_pct REAL,
    cup_duration INTEGER,
    handle_depth_pct REAL,
    handle_duration INTEGER,
    lip_deviation_pct REAL,
    is_breakout INTEGER DEFAULT 0,
    is_volume_breakout INTEGER DEFAULT 0,
    breakout_price REAL,
    volume_dry_score INTEGER,
    price_stable_score INTEGER,
    pattern_score_20 INTEGER,
    verdict_key TEXT,
    risk_percent REAL,
    rr1 REAL,
    entry_zone_low REAL,
    entry_zone_high REAL,
    stop_loss REAL,
    target_1 REAL,
    target_2 REAL,
    baseline_passed INTEGER DEFAULT 1,
    experiment_passed INTEGER DEFAULT 1,
    experiment_filter_reason TEXT,
    evaluation_snapshot TEXT NOT NULL,
    UNIQUE(task_id, code, evaluation_date)
);
```

### 7.4 新增机会表

```sql
CREATE TABLE IF NOT EXISTS strategy1_backtest_opportunities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT,
    first_signal_id INTEGER,
    last_signal_id INTEGER,
    signal_count INTEGER DEFAULT 0,
    first_detected_date TEXT NOT NULL,
    last_detected_date TEXT NOT NULL,
    pattern_kind TEXT,
    first_score INTEGER,
    max_score INTEGER,
    entry_date TEXT,
    entry_price REAL,
    exit_date TEXT,
    exit_price REAL,
    exit_reason TEXT,
    realized_return REAL,
    mark_to_market_end_return REAL,
    holding_days INTEGER,
    available_forward_days INTEGER DEFAULT 0,
    horizon_3 TEXT,
    horizon_5 TEXT,
    horizon_10 TEXT,
    horizon_20 TEXT,
    market_context_json TEXT,
    evaluation_snapshot TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(task_id, code, first_detected_date, pattern_kind)
);
```

### 7.5 数据兼容

- 所有表使用 `CREATE TABLE IF NOT EXISTS`。
- 旧 `scanner.backtester` 输出 JSON 不迁移。
- 旧扫描任务不伪装为可信基线。
- 新策略1正式回测任务必须有版本和快照。

---

## 8. 接口设计方案

### 8.1 创建策略1回测任务

```http
POST /api/strategy1/backtests
```

请求：

```json
{
  "startDate": "2025-08-01",
  "endDate": "2026-05-01",
  "codes": [],
  "maxStocks": null,
  "executionModel": "NEXT_OPEN",
  "baselineTaskId": null,
  "experiment": {
    "enabled": false
  }
}
```

返回：

```json
{
  "taskId": "s1bt-20260614-120000-a1b2c3",
  "status": "created",
  "credibilityStatus": "TRUSTED_BASELINE",
  "estimatedStocks": 5000,
  "estimatedEvaluations": 500000
}
```

### 8.2 实验预览

```http
POST /api/strategy1/backtests/experiments/preview
```

用途：

- 校验实验配置。
- 返回标准化配置。
- 返回风险提示。

### 8.3 查询任务详情

```http
GET /api/strategy1/backtests/{taskId}
```

必须返回：

- 任务状态。
- 可信度状态。
- 配置快照。
- 实验快照。
- 版本信息。
- 汇总统计。
- 分组统计。
- 对比摘要。

### 8.4 查询机会

```http
GET /api/strategy1/backtests/{taskId}/opportunities?limit=100&offset=0
```

支持过滤：

- `code`
- `patternKind`
- `verdictKey`
- `scoreRange`
- `result10`
- `exitReason`

### 8.5 查询原始信号

```http
GET /api/strategy1/backtests/{taskId}/signals?code=600000
```

### 8.6 查询任务股票

```http
GET /api/strategy1/backtests/{taskId}/stocks?status=FAILED
```

### 8.7 基线对比

```http
GET /api/strategy1/backtests/{taskId}/comparison?baselineTaskId=s1bt-...
```

不可比较时返回原因：

- `DATA_REVISION_MISMATCH`
- `DATE_RANGE_MISMATCH`
- `STOCK_SCOPE_MISMATCH`
- `EXECUTION_MODEL_MISMATCH`
- `STRATEGY_VERSION_MISMATCH`

---

## 9. 可以实施的代码方案

### 9.1 后端代码方案

#### 新增模型

文件：

```text
scanner/strategy1_backtest_models.py
```

包含：

- `Strategy1BacktestSignal`
- `Strategy1BacktestOpportunity`
- `Strategy1HorizonPerformance`
- `Strategy1BacktestSummary`
- `Strategy1ExperimentConfig`

#### 新增回测器

文件：

```text
scanner/strategy1_backtester.py
```

核心函数：

```text
run_strategy1_stock_backtest()
run_strategy1_backtest()
calculate_strategy1_execution_outcome()
merge_strategy1_signals()
aggregate_strategy1_backtest_summary()
```

关键要求：

- 只读取本地日线。
- 只调用 `CupHandleStrategyEngine.evaluate_at()`。
- 保存原始信号。
- 使用完整可评估交易日序列合并机会。
- 默认下一交易日开盘入场。
- 支持 3/5/10/20 日表现。
- 不再把 60 日作为核心观察周期。

#### 新增实验模块

文件：

```text
scanner/strategy1_backtest_experiments.py
```

职责：

- 标准化实验参数。
- 校验实验参数。
- 应用实验过滤。
- 构造分组标签。
- 计算市场环境统计。
- 输出过滤原因。

#### 新增任务服务

文件：

```text
scanner/strategy1_backtest_service.py
```

职责：

- 创建任务。
- 恢复任务。
- 取消任务。
- 重试失败股票。
- 生成任务汇总。
- 生成基线对比。
- 计算数据版本。

#### 修改数据库层

文件：

```text
scanner/db.py
```

新增：

- `_ensure_strategy1_backtest_tables()`
- `create_strategy1_backtest_task()`
- `update_strategy1_backtest_task()`
- `get_strategy1_backtest_task()`
- `save_strategy1_backtest_signal()`
- `save_strategy1_backtest_opportunity()`
- `replace_strategy1_stock_backtest_result()`
- `build_strategy1_backtest_summary()`
- `compare_strategy1_backtest_tasks()`

#### 修改服务接口

文件：

```text
server.py
```

新增策略1回测 API，注意与策略2回测互斥：

- 策略1扫描运行时禁止启动策略1回测。
- 策略2扫描运行时禁止启动策略1回测。
- 任一回测运行时禁止启动新的扫描或回测。

### 9.2 前端代码方案

新增页面建议：

```text
web/src/pages/Strategy1Backtest.vue
```

页面包含：

- 基线任务启动。
- 实验任务启动。
- 实验参数面板。
- 任务历史。
- 机会列表。
- 原始信号追溯。
- 基线对比。
- 分组统计。

修改：

- `web/src/router/index.js`
- `web/src/components/TopNav.vue`
- `web/src/composables/useApi.js`
- `web/src/pages/StrategyConfig.vue`

前端必须显示：

- `TRUSTED_BASELINE`
- `EXPERIMENTAL`
- 实验不影响正式扫描提示。
- 正式启用后的策略版本说明。

---

## 10. 日志与异常处理方案

### 10.1 必须记录的日志

- 策略1回测任务创建。
- 配置快照。
- 实验快照。
- 数据版本。
- 股票池来源。
- 实际评估区间。
- 原始信号数量。
- 机会数量。
- 失败股票明细。
- 基线对比结果。
- 正式策略启用原因。
- 回滚方案。

### 10.2 异常处理

- 单只股票失败不终止整体任务。
- 判断日异常必须计数和记录。
- 数据不足股票进入单独列表。
- 汇总失败时任务不得标记完整成功。
- 对比不可比时不展示差值。
- 正式策略启用前若测试失败，禁止启用。

---

## 11. 测试方案

### 11.1 单元测试

- 策略1实验配置标准化。
- 实验参数越界校验。
- 杯体深度过滤。
- 柄部深度过滤。
- 评分门槛过滤。
- 干稳门槛过滤。
- 风险门槛过滤。
- 原始信号保存。
- 机会合并。
- 下一交易日开盘执行。
- 目标/止损/时间退出优先级。
- 市场环境分组。

### 11.2 数据库测试

- 新表创建。
- 旧数据库兼容。
- 任务快照保存。
- 原始信号唯一约束。
- 机会唯一约束。
- 单股重试幂等。
- 汇总 JSON 保存。
- 对比摘要保存。

### 11.3 接口测试

- 创建基线任务。
- 创建实验任务。
- 查询任务详情。
- 查询机会。
- 查询原始信号。
- 查询失败股票。
- 实验预览。
- 基线对比。
- 不可比较任务拒绝对比。
- 任务互斥。

### 11.4 集成测试

1. 构造本地股票池和日线。
2. 创建策略1可信基线。
3. 生成杯柄和 VCP 两类机会。
4. 保存原始信号和合并机会。
5. 创建实验任务。
6. 验证实验过滤生效。
7. 验证基线对比。
8. 模拟中断恢复。
9. 验证无重复写入。

### 11.5 前端测试

- 实验模式开关。
- 参数 payload。
- `EXPERIMENTAL` 标识。
- 基线任务选择。
- 对比结果展示。
- 分组统计展示。
- 数据不足股票展示。
- 正式策略版本说明展示。

### 11.6 回归测试

- 策略1正式扫描默认行为在实验关闭时不变。
- 策略2不受影响。
- 单股回测不受破坏。
- 配置页保存正常。
- 后端全量测试通过。
- 前端测试和构建通过。

---

## 12. 验收标准

1. 策略1可以创建可信基线回测任务。
2. 策略1可以创建实验回测任务。
3. 策略1回测只读取本地数据库。
4. 策略1回测只调用统一策略入口。
5. 原始信号、机会、股票状态和汇总可追溯。
6. 实验关闭时等同正式基线。
7. 实验任务明确标记 `EXPERIMENTAL`。
8. 基线对比可识别可比与不可比任务。
9. 策略1分组统计足以支撑参数研究。
10. Codex 可以根据实验结果直接决定正式策略参数。
11. 正式策略启用前测试必须通过。
12. 正式策略启用后必须交付优化后的策略1正式策略文档。
13. 最终交付必须明确是否已作为策略1正式版本启用。

---

## 13. 策略1正式优化授权与启用流程

### 13.1 用户授权

用户已授权 Codex：

- 可以基于历史数据回测和实验结果决定策略1正式优化参数。
- 可以修改策略1正式配置参数。
- 可以修改策略1正式扫描过滤规则。
- 可以更新策略1前端配置展示。
- 可以在优化完成后直接作为策略1正式版本启用。
- 不需要用户再次确认具体参数数值。

### 13.2 正式启用前置条件

必须同时满足：

1. 有新的策略1全市场可信基线任务。
2. 基线任务为 `TRUSTED_BASELINE`。
3. 至少有一个可比较实验任务。
4. 对比结果显示明确改善。
5. 改善不能只依赖单一月份或极少数股票。
6. 已形成策略升级建议。
7. 已有回滚方案。
8. 测试通过。

### 13.3 正式启用后必须交付

新增文档：

```text
docs/superpowers/specs/YYYY-MM-DD-strategy1-optimized-strategy-parameters.md
```

文档必须包含：

- 策略版本号。
- 生效日期。
- 是否已启用为策略1正式版本。
- 启用提交或版本号。
- 最终参数表。
- 参数旧值和新值。
- 正式过滤规则。
- 杯体规则。
- 柄部规则。
- VCP规则。
- 干稳低吸规则。
- 风险收益规则。
- 可信基线任务 ID。
- 实验任务 ID。
- 核心对比结果。
- 分组表现。
- 不采用参数及原因。
- 已知风险。
- 回滚方案。
- 后续观察指标。

---

## 14. 给 Claude Code / Codex 的执行指令

请严格按照本文档执行策略1历史回测实验与正式策略优化。

执行要求：

1. 先阅读当前策略1扫描、统一策略入口、批量回测、单股回测、数据库和前端代码。
2. 实现前必须新建独立策略1 worktree，推荐分支 `codex/strategy1-backtest-experiment-optimization`。
3. 禁止在 `strategy2-extreme-dry-stable` worktree 中开发策略1。
4. 新 worktree 创建后先运行策略1相关基线测试。
5. 参考策略2 Phase 2 的实验闭环，但不得照搬策略2参数。
6. 策略1回测必须调用 `CupHandleStrategyEngine.evaluate_at()`。
7. 策略1回测禁止访问外部数据源。
8. 先实现可信回测和实验层，再运行基线和实验任务。
9. 实验关闭时必须等同正式基线。
10. 实验开启时必须标记 `EXPERIMENTAL`。
11. 被实验过滤的原始信号必须可追溯。
12. 使用测试驱动开发。
13. 每完成一个模块运行对应测试。
14. 最终运行后端全量测试、前端测试和前端构建。
15. 将过程、测试结果、实验任务、策略决策和启用结果写入 `operations-log.md`。
16. 用户已授权：当证据充分且测试通过后，可以直接启用策略1正式优化版本。
17. 正式启用后必须交付优化后的策略1正式策略文档。

---

## 15. AI 开始开发提示语

### 15.1 策略1回测实验能力开发提示语

```text
请开发策略1“历史回测实验与策略优化评估”功能。

工作目录：
D:\game\claude\dry-stable-low-risk-entry-strategy\.claude\worktrees\strategy1-backtest-experiment-optimization

开发依据：
docs/superpowers/specs/2026-06-14-strategy1-backtest-experiment-optimization-design.md

核心定位：
本次先建设策略1可信回测和实验优化能力，不是凭感觉直接改策略参数。策略1是杯柄/VCP + 干稳低吸 + 风险收益组合策略，必须围绕策略1自身结构做实验，不得照搬策略2的量干价稳规则。

强制要求：
1. 先确认当前目录是策略1独立 worktree，分支建议为 codex/strategy1-backtest-experiment-optimization。
2. 禁止在 strategy2-extreme-dry-stable worktree 中开发策略1。
3. 从 D:\game\claude\dry-stable-low-risk-entry-strategy\.claude\worktrees\strategy2-extreme-dry-stable\data 复制 cuphandle.db、cuphandle.db-wal、cuphandle.db-shm 到策略1 worktree 的 data 目录，作为策略1回测实验本地数据快照。
4. 确认策略1 worktree 的 config.yaml 使用 data.database_path: ./data/cuphandle.db。
5. 复制数据前优先停止写入源库的进程；无法确认静止时，使用 SQLite backup API 或等效一致性备份方式。
6. 先阅读 scanner/strategy_engine.py、scanner/engine.py、scanner/backtester.py、scanner/single_stock_backtest.py、scanner/db.py、server.py、config.yaml 和策略2 Phase 2 文档。
7. 新增策略1回测模型、回测器、任务服务和实验模块。
8. 回测必须只读取本地 stock_pool 和 daily_ohlc，禁止请求百度、新浪、腾讯、yfinance、AKShare、Tushare 或任何外部数据源。
9. 数据不足的股票必须写入数据不足明细并在前端或任务详情列出，不得静默联网补数据。
10. 策略判断必须调用 CupHandleStrategyEngine.evaluate_at()，禁止复制策略判断代码。
11. 保存 config_snapshot、experiment_snapshot、策略版本、数据版本和数据快照信息。
12. 保存原始信号、合并机会、股票状态、数据不足股票和汇总统计。
13. 支持 TRUSTED_BASELINE、EXPERIMENTAL、LEGACY_UNTRUSTED、INCOMPLETE。
14. 支持评分门槛、杯体结构、柄部结构、突破确认、干稳低吸、风险收益、执行模型和时间退出实验。
15. 实验关闭时必须等同正式基线。
16. 实验开启时必须标记 EXPERIMENTAL。
17. 被实验过滤的原始信号必须保存并记录过滤原因。
18. 默认执行模型使用 NEXT_OPEN。
19. 核心观察周期为 3/5/10/20 日，不把 60 日作为核心成功口径。
20. 增加基线对比接口，必须校验数据版本、策略版本、日期范围、股票范围和执行模型一致性。
21. 前端增加策略1回测实验页面或等效入口，展示实验参数、EXPERIMENTAL 标识、基线对比和分组统计。
22. 不修改策略2，不重构无关模块。
23. 使用测试驱动开发，覆盖实验配置、信号保存、机会合并、执行模型、数据库兼容、API 和前端展示。
24. 最终运行后端全量测试、前端测试和前端构建，并把结果写入 operations-log.md。

直接开始实施，不需要再次确认本文档已明确的事项。
```

### 15.2 端到端开发、实验、策略优化与正式启用提示语

```text
请按照以下要求，完整执行策略1可信回测实验能力开发、历史数据研究、正式策略优化决策和正式版本启用。

工作目录：
D:\game\claude\dry-stable-low-risk-entry-strategy\.claude\worktrees\strategy1-backtest-experiment-optimization

核心文档：
docs/superpowers/specs/2026-06-14-strategy1-backtest-experiment-optimization-design.md

第零阶段：创建独立 worktree
1. 不要在主工作区或 strategy2-extreme-dry-stable worktree 中直接开发。
2. 新建独立策略1 worktree：
   D:\game\claude\dry-stable-low-risk-entry-strategy\.claude\worktrees\strategy1-backtest-experiment-optimization
3. 推荐分支：
   codex/strategy1-backtest-experiment-optimization
4. 从策略2 worktree 复制已有股票数据库快照到策略1 worktree：
   源目录：
   D:\game\claude\dry-stable-low-risk-entry-strategy\.claude\worktrees\strategy2-extreme-dry-stable\data
   目标目录：
   D:\game\claude\dry-stable-low-risk-entry-strategy\.claude\worktrees\strategy1-backtest-experiment-optimization\data
   必须复制：
   cuphandle.db
   cuphandle.db-wal
   cuphandle.db-shm
5. 复制前优先停止写入源库的后端、扫描或回测进程；无法确认静止时，使用 SQLite backup API 或等效一致性备份方式。
6. 不复制 test_prog_debug.db 作为全市场策略1回测数据源。
7. 确认策略1 worktree 的 config.yaml 使用：
   data.database_path: ./data/cuphandle.db
8. 进入 worktree 后先运行：
   python -m pytest tests/test_backtester.py tests/test_cuphandle_strategy_engine.py tests/test_single_stock_backtest.py -q
9. 如果基线测试失败，先记录并判断是否为既有失败，不要直接开始大规模修改。

第一阶段：开发策略1可信回测和实验能力
1. 新增策略1回测模型、回测器、任务服务、实验模块、数据库表和 API。
2. 回测只读取策略1 worktree 中复制的本地数据库，不访问外部数据源。
3. 回测只调用 CupHandleStrategyEngine.evaluate_at()。
4. 保存任务快照、实验快照、版本、数据快照、原始信号、机会、股票状态和汇总。
5. 数据不足股票写入明细，并在前端或任务详情列出，不触发在线补数据。
6. 支持 TRUSTED_BASELINE 和 EXPERIMENTAL。
7. 支持基线对比。
8. 前端提供策略1回测实验入口。

第二阶段：运行验证
1. 运行策略1相关单元测试。
2. 运行后端全量测试。
3. 运行前端测试。
4. 运行前端构建。
5. 验证实验关闭等同正式基线。
6. 验证实验任务为 EXPERIMENTAL。
7. 验证对比接口可识别不可比任务。
8. 将结果写入 operations-log.md。

第三阶段：运行策略1可信基线
1. 使用最新代码运行策略1全市场基线回测。
2. experiment.enabled=false。
3. 默认执行模型 NEXT_OPEN。
4. 任务完成后确认 status=completed。
5. 任务 credibility_status=TRUSTED_BASELINE。
6. 记录基线 task_id。
7. 如果基线任务失败或完整性校验失败，先修复，不得进入优化。

第四阶段：运行策略1实验任务
至少运行以下实验：
1. minimum_total_score = 70 / 80。
2. cup_max_depth = 0.33 / 0.40。
3. handle_max_depth = 0.10 / 0.12。
4. min_volume_dry_score = 7 / 8 / 9。
5. min_price_stable_score = 6 / 7。
6. max_risk_percent = 6 / 8。
7. min_rr1 = 1.5 / 2.0 / 2.5。
8. breakout.mode = NEAR_PIVOT / PRICE_AND_VOLUME。
9. time_exit_days = 3 / 5 / 10。

所有实验任务必须与基线使用相同日期、股票范围、执行模型和数据版本，并且 comparison 返回 comparable=true。

第五阶段：分析并确定优化策略
由 Codex 自主完成策略分析和正式策略决策，用户已授权不需要再次确认具体参数。

分析至少包括：
1. 机会数变化。
2. 实际入场数变化。
3. 3/5/10/20 日成功率。
4. 平均实际收益。
5. 中位实际收益。
6. 止损率。
7. 假突破率。
8. 跑赢市场比例。
9. 按月份分组。
10. 按 CUP_HANDLE / VCP_ONLY 分组。
11. 按 BUY_LOW / WATCH_BREAKOUT / WAIT_ENTRY 分组。
12. 按杯体深度、柄部深度、总分、量干分、价稳分、风险比分组。
13. 不采用参数的原因。

决策原则：
1. 不采用只在单一月份有效的参数。
2. 不采用机会数下降过度但收益改善不足的参数。
3. 不采用止损率没有改善且平均收益不稳定的参数。
4. 优先选择收益改善、止损下降、假突破下降、机会数仍可接受的组合。
5. 对只能改善展示或交易建议的参数，不强行作为硬过滤。

第六阶段：正式启用策略1优化版本
用户已授权：当实验结果支持正式升级，并且完成策略升级建议、测试验证和优化后策略文档后，可以直接把优化策略作为策略1正式版本启用，不需要再次确认具体参数。

正式启用要求：
1. 修改策略1正式 config.yaml 参数或正式扫描规则。
2. 更新策略1配置页或策略说明展示。
3. 补充或更新测试。
4. 运行后端全量测试、前端测试和前端构建。
5. 在 operations-log.md 记录启用原因、基线任务 ID、实验任务 ID、最终参数、测试结果和回滚方案。
6. 不修改策略2。
7. 不引入第二份策略1判断代码。
8. 不在测试失败、证据不足或回滚方案缺失时启用正式版本。

第七阶段：交付优化后的策略1正式策略文档
正式启用后，必须新增：
docs/superpowers/specs/YYYY-MM-DD-strategy1-optimized-strategy-parameters.md

文档必须包含：
1. 策略版本号。
2. 生效日期。
3. 是否已启用为策略1正式版本。
4. 启用提交或版本号。
5. 最终参数表，包含参数名、旧值、新值、生效位置、调整原因。
6. 正式杯体规则。
7. 正式柄部规则。
8. 正式 VCP 规则。
9. 正式评分门槛。
10. 正式干稳低吸门槛。
11. 正式风险收益规则。
12. 可信基线任务 ID。
13. 实验任务 ID。
14. 核心对比结果。
15. 分组表现。
16. 不采用参数及原因。
17. 已知风险和适用边界。
18. 回滚触发条件。
19. 回滚参数清单。
20. 回滚验证方式。
21. 后续观察指标。

最终交付必须说明：
1. 策略1回测实验功能是否完成。
2. 可信基线 task_id。
3. 实验 task_id 列表。
4. 最终启用的策略1正式参数。
5. 修改文件清单。
6. 数据库变更说明。
7. API 变更说明。
8. 前端变更说明。
9. 测试结果。
10. 优化后策略文档路径。
11. 是否已作为策略1正式版本启用。
12. 回滚方式。

直接开始执行，不需要再次确认本文档已经明确的事项。
```

---

## 16. 最终交付物

开发完成后，需要交付：

1. 修改文件清单。
2. 策略1可信回测功能说明。
3. 策略1实验参数说明。
4. 数据库变更说明。
5. API 变更说明。
6. 前端变更说明。
7. 基线任务 ID。
8. 实验任务 ID 列表。
9. 历史数据研究结论。
10. 最终启用的策略1正式参数。
11. 测试结果说明。
12. 优化后的策略1正式策略文档。
13. 是否已启用为策略1正式版本。
14. 回滚方案。

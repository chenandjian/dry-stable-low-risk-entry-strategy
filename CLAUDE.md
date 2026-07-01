# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

CupHandleScan — A股杯柄结构（Cup & Handle）自动扫描系统。Python 3.10+。

## Commands

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行单个测试文件
python -m pytest tests/test_data_source.py -v

# 运行单个测试函数
python -m pytest tests/test_data_source.py::test_acquire_release_single_source -v

# 安装依赖
pip install -r requirements.txt

# CLI: 全市场扫描 / 单只分析 / Web 服务 / 调度 / 回测
python main.py scan
python main.py analyze 600036
python main.py serve --port 8080
python main.py schedule
python main.py backtest --sample 10

# 前端开发（worktree 中优先用 --prefix，避免在仓库根目录找 package.json）
npm --prefix web install
npm --prefix web run dev -- --host 127.0.0.1
npm --prefix web run build
npm --prefix web run preview
```

## Architecture

```
入口层:    main.py (CLI)  /  server.py (FastAPI)  /  scheduler/scheduler.py
引擎层:    scanner/engine.py (策略1多线程扫描调度)
           scanner/strategy_engine.py (策略1统一入口 — CupHandleStrategyEngine)
           strategy2/scanner.py (策略2多线程扫描编排)
           strategy2/engine.py (策略2唯一入口 — ExtremeDryStableStrategyEngine)
数据层:    scanner/db.py (SQLite 持久化)
           scanner/data_source.py (互斥锁管理 — baidu/sina/tencent)
           scanner/daily_data_service.py (共享三源拉取 — fetch_with_retry / FetchResult)
           scanner/sina_source.py / tencent_source.py / baidu_source.py (HTTP抓取)
           scanner/stock_pool.py (股票池)
算法层:    scanner/pattern_detector.py (杯柄识别 · 仅策略1)
           scanner/liquidity_filter.py (流动性过滤 · 策略1+2共享)
           scanner/scorer.py (杯柄评分 0-100 · 仅策略1)
           strategy2/indicators.py (策略2指标 — V3/V5/V10/V20/分位/range/return)
           strategy2/scorer.py (策略2评分 — 量干50 + 价稳50 + 等级)
           strategy2/rejection.py (策略2一票否决 — 5条规则)
           strategy2/risk.py (策略2风险 — key_support/买入区间/止损/风险比)
           strategy2/trend.py (策略2趋势 — V2 价格路径+120日长期确认，11项证据评分)
分析层:    analyzer/dry_stable.py → analyze_dry_stable() 串联全部分析 · 仅策略1
             ├─ analyzer/volume_dry.py (量干评分 0-12)
             ├─ analyzer/price_stable.py (价稳评分 0-10)
             ├─ analyzer/pattern_score.py (形态评分 0-20, 杯柄/VCP择优)
             ├─ analyzer/key_prices.py (关键价格/入场区间)
             ├─ analyzer/risk_reward.py (风险收益比 + 仓位建议)
             ├─ analyzer/invalid_rules.py (形态失效条件)
             ├─ analyzer/market_env.py (大盘环境评估)
             └─ analyzer/decision.py (7 状态决策)
回测层:    scanner/backtester.py (策略1批量历史回测)
           scanner/single_stock_backtest.py (单股杯柄回测)
           strategy2/backtester.py (策略2本地数据库短线回测 · 只读本地 DB)
           strategy2/backtest_models.py (策略2回测数据模型)
指标层:    scanner/index_source.py (大盘指数数据)
输出层:    output/csv_writer.py / json_writer.py
策略2层:   strategy2/models.py (数据模型 — 5 个 dataclass)
           strategy2/indicators.py (指标计算)
           strategy2/scorer.py (量干价稳评分)
           strategy2/rejection.py (一票否决)
           strategy2/risk.py (风险计算)
           strategy2/engine.py (引擎入口)
           strategy2/scanner.py (扫描编排)
前端:      web/ (Vue 3 + lightweight-charts · 深色金融终端风格)
```

**核心设计决策:**

- **数据源互斥锁：** 两个扫描线程不能同时请求同一个数据源（新浪/腾讯）。`DataSourceManager` 用 `threading.Lock(blocking=False)` 实现非阻塞互斥。线程取不到锁时 sleep 0.1s 后重试。
- **扫描 fresh-first：** 点击开始扫描默认重新拉取个股日线；缓存只用于合并历史和详情展示，主备数据源都失败时不能用旧缓存生成扫描结果。
- **腾讯源纯源化：** `fetch_tencent_daily()` 为纯腾讯源，失败返回 None。回退逻辑统一在引擎层 `_fetch_with_retry` 处理，数据源函数内部不再偷偷切源。
- **扫描任务追踪：** `scan_tasks` 记录任务级统计，`task_stocks` 记录每只股票的 `pending/fetching/scanned/skipped/failed/candidate`、失败原因、数据源尝试和最新 K 线日期。
- **任务系统适用范围：** `/api/scan/start` 发起的扫描完整使用 `scan_tasks/task_stocks/_running`、失败重拉和恢复；`main.py scan` 与 `scheduler` 直接调用 `scan_all(config)`，不完全等价于 server-managed task。
- **候选去重：** 同一任务内候选按 `(task_id, code)` 唯一；内存层用 code 字典去重，数据库层用唯一索引/upsert，前端按 code 归并。
- **全局扫描互斥：** server API 启动扫描前同时检查 `_running` 和 DB 中 `status='running'` 的任务；CLI/scheduler 路径未完整纳入这套互斥语义。
- **失败重拉：** `/api/scan/tasks/{task_id}/retry-failed` 只处理原任务 `failed` 股票，使用 `retry_policy='failed_only'` 重跑完整个股扫描逻辑。
- **行情拉取回退：** 主数据源 → 备用数据源；任一 fresh 源成功后才与缓存合并并保存。双源都失败时不能用旧缓存产出扫描结果。AKShare 仅用于获取股票池，不用于 OHLC 数据。
- **单只失败不中断：** 全市场扫描中，单只股票异常（超时/解析错误/停牌）记录日志后跳过，不中断整体任务。
- **数据源锁必须释放：** `try...finally` 确保异常路径也释放锁。
- **配置文件驱动：** 主要扫描阈值（杯体深度、柄部回撤、流动性等）在 `config.yaml` 中可调；部分策略阈值仍硬编码，新增配置项前先确认代码已接入。
- **形态评分维度：** 杯体结构 35 + 柄部结构 25 + 成交量结构 20 + 前置趋势 10 + 突破确认 10 = 100 分。
- **A股配色：** 红涨绿跌。金色仅用于 ≥80 分 A 级信号。
- **SQLite 持久化：** 数据存储于 `data/cuphandle.db`（stock_pool, daily_ohlc, scan_tasks, candidates）。线程级连接 + WAL 模式。
- **新浪 API：** `quotes.sina.cn/cn/api/jsonp_v2.php/data/CN_MarketDataService.getKLineData` — 返回 JSONP 需手动解析。腾讯源失败返回 None，回退逻辑统一在引擎层处理。
- **VCP 补位：** `pattern_detector.py` 不检测 VCP；VCP 逻辑在 `analyzer/pattern_score.py`。`engine.py` 可在杯柄未命中但 VCP 评分足够时生成候选。
- **统一策略入口：** `CupHandleStrategyEngine.evaluate_at()` 是所有业务入口的唯一策略判断点。扫描（`scan_all` / `re_evaluate_task`）、CLI（`cmd_analyze`）、候选详情（`/api/candidate/{code}`）、批量回测（`run_backtest`）、单股回测均通过该入口。`evaluation.passed` 是唯一候选资格结论，调用方不得重复实现评分门槛、形态类型、决策状态或突破排除规则。
- **窗口职责分离：** `liquidity.min_listing_days` 仅控制数据拉取天数与上市天数检查；`data.scan_window_days`（默认 250）仅控制扫描策略计算窗口；`data.backtest_window_days`（默认 250）仅控制回测策略计算窗口。三个字段由 `resolve_strategy_windows(config)` 统一解析与校验：缺失时固定默认 250，必须为 `int >= 30`，`scan_window_days <= min_listing_days`，拒绝 0/浮点/字符串/布尔。
- **市场数据截断：** `select_market_window(market_data, decision_date)` 按股票判断日期过滤市场指数，防止未来数据泄漏。全部 6 个策略入口统一使用，`decision_date = strategy_data[-1]["date"]`。
- **配置 API 校验：** `PUT /api/config` 保存前和 `/api/scan/start` 启动前均执行 `resolve_strategy_windows()`，非法配置返回 HTTP 400，不写文件也不创建任务。
- **`daily_kline_days` 已废弃：** 不再作为业务拉取配置读取。扫描拉取天数仅由 `liquidity.min_listing_days` 控制。
- **策略2独立边界：** `strategy2/` 包完全不导入策略1的形态检测、评分、分析或决策模块。共享层（stock_pool、data_source、liquidity_filter、db 基础能力、daily_data_service）允许复用。策略2结果写入独立表 `strategy2_candidates`，不写入 `candidates`。
- **策略2 双策略全局互斥：** 同一时间只允许一个全市场扫描（策略1或策略2）。任一扫描 `running` 时，另一策略启动返回 HTTP 409 含 `strategyType` 和 `runningTaskId`。`_running` 状态新增 `strategy_type`，`scan_tasks.strategy_type` 区分 `STRATEGY_1_CUP_HANDLE` / `STRATEGY_2_EXTREME_DRY_STABLE`。
- **策略2 评分体系（满分100）：** 量干 50 分（V5/V20≤0.60:+10, ≤0.50:+10, V3<V5<V10<V20:+10, 量处60日最低20%:+10, return_5≥-3%:+10）+ 价稳 50 分（range_5≤5%:+10, ≤3%:+10, close_range_5≤3%:+10, 无单日跌幅<-3%:+10, 收盘≥支撑:+10）。等级：70-79普通观察/80-89重点观察/90-94极致量干价稳/95-100终极状态。
- **策略2 一票否决（5条）：** return_5<-5%、放量(>V20)单日跌幅≤-4%、range_5>8%、收盘<key_support、return_3≥8%。任一触发即排除。
- **策略2 key_support：** 不含评估日 T 的前10个交易日最低收盘价。禁止包含评估日自身（否则"当前价永远不低于支撑"规则失效）。
- **策略2 入选条件：** 总分≥70（可配）、无否决、风险比≤5%（可配）。风险比=(收盘-止损)/收盘，≤3%低风险/≤5%可接受/>5%排除。
- **策略2 本期不做：** 回测、重新评估、CSV导出。策略2不使用杯柄/VCP形态判断。

## Key Files

| File                                 | Purpose                                                                                                                                                                       |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `config.yaml`                        | 所有可调参数（市场/流动性/杯体/柄部/突破/评分/输出/调度/数据库）                                                                                                              |
| `scanner/db.py`                      | SQLite 数据库层 — 连接管理 + 5 表 CRUD                                                                                                                                        |
| `scanner/data_source.py`             | `DataSourceManager` — 新浪+腾讯双源互斥锁                                                                                                                                     |
| `scanner/sina_source.py`             | `fetch_sina_daily(code, days)` → `list[dict] \| None`                                                                                                                         |
| `scanner/tencent_source.py`          | `fetch_tencent_daily(code, days)` → `list[dict] \| None`（纯腾讯源，回退由引擎层处理）                                                                                        |
| `scanner/pattern_detector.py`        | `detect_cup_handle(data, config)` → `CupHandleResult`；只负责杯柄检测                                                                                                         |
| `scanner/scorer.py`                  | `score_cup_handle(result)` / `score_cup_handle_advanced(result, data)` → `int` (0-100)                                                                                        |
| `scanner/engine.py`                  | `scan_all(config)` — 多线程全市场扫描主循环                                                                                                                                   |
| `scanner/strategy_engine.py`         | `CupHandleStrategyEngine.evaluate_at()` — 唯一策略判断入口；`select_strategy_window()` / `select_market_window()` — 共享窗口截断；`resolve_strategy_windows()` — 统一配置校验 |
| `scanner/backtester.py`              | `run_backtest(stocks, fetch_fn, config)` — 批量历史回测                                                                                                                       |
| `scanner/single_stock_backtest.py`   | `run_single_stock_cuphandle_backtest(...)` — 单股杯柄回测                                                                                                                     |
| `analyzer/volume_dry.py`             | `score_volume_dry(data)` → `VolumeDryResult` (0-10)                                                                                                                           |
| `analyzer/price_stable.py`           | `score_price_stable(data)` → `PriceStableResult` (0-10)                                                                                                                       |
| `analyzer/pattern_score.py`          | `score_pattern(result, data)` → `PatternScoreResult` (0-20, 杯柄/VCP 择优；VCP 识别在这里)                                                                                    |
| `analyzer/key_prices.py`             | `calculate_key_prices(...)` → `KeyPricesResult` (入场区间/支点/止损/目标)                                                                                                     |
| `analyzer/risk_reward.py`            | `calculate_risk_reward(...)` → `RiskRewardResult`                                                                                                                             |
| `analyzer/dry_stable.py`             | `analyze_dry_stable(result, data, market_data)` → `dict` — 串联全部 8 个分析模块                                                                                              |
| `analyzer/decision.py`               | `make_dry_stable_decision(...)` → `DryStableDecision` — 最终买入判决                                                                                                          |
| `analyzer/market_env.py`             | `assess_market_environment(market_data)` → `MarketEnvResult`                                                                                                                  |
| `analyzer/invalid_rules.py`          | `find_invalid_conditions(...)` → `list[str]`                                                                                                                                  |
| `scanner/index_source.py`            | `fetch_market_index_daily(code)` → `list[dict]` (复用新浪源)                                                                                                                  |
| `server.py`                          | FastAPI API + 扫描任务编排 — CORS/lifespan、恢复中断任务、失败重拉、配置读写、策略2 API                                                                                       |
| `scanner/daily_data_service.py`      | 共享四数据源拉取服务 — `fetch_with_retry()` / `FetchResult` / 锁/重试/缓存合并                                                                                                |
| `strategy2/models.py`                | 策略2数据模型 — `Strategy2Indicators` / `Score` / `Risk` / `Evaluation`                                                                                                       |
| `strategy2/indicators.py`            | 策略2指标计算 — V3/V5/V10/V20、分位、range、return                                                                                                                            |
| `strategy2/scorer.py`                | 策略2量干价稳评分 + 等级                                                                                                                                                      |
| `strategy2/rejection.py`             | 策略2一票否决 — 5 条规则返回稳定错误码                                                                                                                                        |
| `strategy2/risk.py`                  | 策略2风险 — `compute_key_support()` / `compute_risk()`                                                                                                                        |
| `strategy2/trend.py`                 | 策略2趋势过滤 V2 — `evaluate_trend()` 价格路径+120日长期确认，8短中+3长期=11项证据                                                                                            |
| `strategy2/engine.py`                | 策略2唯一入口 — `ExtremeDryStableStrategyEngine.evaluate_at()`                                                                                                                |
| `strategy2/scanner.py`               | 策略2全市场扫描编排 — `scan_strategy2_all()`                                                                                                                                  |
| `web/src/pages/ScannerConsole.vue`   | 前端首页 — 双策略启动按钮                                                                                                                                                     |
| `web/src/pages/Strategy2Results.vue` | 策略2结果页 — 任务选择器 + 候选表（总分/等级/量干/价稳/风险比/支撑/止损）                                                                                                     |
| `web/src/pages/StrategyConfig.vue`   | 策略配置页 — 含策略2独立金色分区（7参数+启停开关）                                                                                                                            |

## Design Specs

- 扫描可靠性设计: `docs/superpowers/specs/2026-06-04-scan-start-and-results-reliability-design.md`
- 扫描可靠性实施计划: `docs/superpowers/plans/2026-06-04-scan-start-and-results-reliability.md`
- 系统设计: `docs/superpowers/specs/2026-06-03-cuphandle-scan-design.md`
- Phase 1 计划: `docs/superpowers/plans/2026-06-03-cuphandle-scan-phase1.md`
- 原始开发需求: `docs/DEVELOPMENT_DOC.md` (杯柄扫描) + `docs/dry-stable-low-risk-entry-strategy.md` (干稳低吸策略)
- 前端设计需求: `docs/art.md`

## Gotchas

- **`PRAGMA table_info`**: 返回 `(cid, name, type, ...)`，取列名用 `d[1]`，不是 `d[0]`。`db.py` 中 `get_candidates` 和 `get_candidate` 用错了会返回整数 key。
- **旧库迁移**: 新增 SQLite 列时用 `PRAGMA table_info(...)[d[1]]` 检查后 `ALTER TABLE ADD COLUMN`；旧 `task_stocks(task_id, idx, code, name, scanned)` 表可能已存在，不能只 `CREATE TABLE IF NOT EXISTS` 后直接建依赖新列的索引。
- **扫描统计语义**: `failed` 不能混入 `skipped`；最终 stats 应从 `db.refresh_scan_task_counts(task_id)` 汇总，避免多线程计数漂移。
- **source busy**: 数据源锁忙是瞬时状态，应 requeue 并设置上限（`data.source_busy_max_retries`），不能立即标记真实拉取失败，也不能无限重试。
- **前端构建**: 新 worktree 通常没有 `web/node_modules`，先 `npm --prefix web install`；构建成功可能仍有 Vite CJS/大 chunk 警告。
- **进程管理**: Windows 下 `taskkill //F //IM python.exe`（双斜杠），单斜杠会解析失败。服务重启前必须确保所有旧 Python 进程已死，否则旧代码继续跑在新端口上。
- **新浪 API**: 返回 JSONP 格式 `data([...]);`，需要手动 `text[5:-2]` 后解析 JSON。
- **Scan 线程崩溃**: `server.py` 中 scan 线程的 `except` 现已含 `traceback.format_exc()`，但需检查日志才能看到。`_running["stats"]` 为空即扫描未正常启动。
- **config.yaml 中的假参数**: `data.cache_dir`、`data.start_date`、`cup.filter_v_shape`、`output.csv/json/charts`、`scheduler.webhook_url` 等键存在于 yaml 但代码中未使用。新增配置项前先确认代码已接入。
- **config.yaml 缺失的有效参数**: `data.source_busy_max_retries`（默认 3）代码中已使用但 config.yaml 中未声明，可通过 yaml 覆盖。
- **scheduler cron 解析不完整**: `scheduler/scheduler.py` 只解析 cron 表达式的 minute、hour、day_of_week 三个字段；day_of_month 和 month 被忽略（默认 `*`）。含日/月限制的表达式（如 `"30 15 1 * 1-5"`）无法正确限制为每月第一天。
- **CLI analyze 统一入口**: `main.py analyze` 已改为通过 `CupHandleStrategyEngine.evaluate_at()` 执行分析，窗口截取使用 `select_strategy_window()`，市场数据截断使用 `select_market_window()`。不再直接调用 `detect_cup_handle()` / `score_cup_handle_advanced()` / `analyze_dry_stable()`。
- **Backtester 统一引擎**: `scanner/backtester.py` 和 `scanner/single_stock_backtest.py` 均使用 `CupHandleStrategyEngine.evaluate_at()`，与扫描路径共享同一套策略规则。
- **配置 API 会改写文件**: `PUT /api/config` 会 deep-merge 请求并直接重写根目录 `config.yaml`；调试配置变化时不要只看 git diff。
- **前端实时状态是轮询**: 当前 Vue UI 主要轮询 `/api/scan/status`；`/ws/scan` 存在但前端未使用，且服务端在收到客户端消息后才发送状态快照。
- **FastAPI 不托管构建产物**: `server.py` 只提供 API/WS，没有 mount `web/dist` 或 SPA history fallback；`npm --prefix web run preview` 也没有 dev server 的 `/api`/`/ws` proxy 配置。

## Recent Changes (2026-06-07 ~ 2026-06-09)

### 数据源拉取

- **3 线程 + try_acquire_any**: worker_count=3，每线程抢空闲数据源。`DataSourceManager.try_acquire_any()` 随机 shuffle 后返回首个未锁定的源。不同线程自然分散到 baidu/sina/tencent。
- **腾讯源修复**: volume 从手转股（×100），turnover 补回 ×100。最新一天用 `qt` 实时成交额。
- **百度源加入锁管理**: 之前只有 sina/tencent 有锁，baidu 绕过互斥。已统一。
- **日线窗口统一**: `db.get_ohlc(max_rows=kline_days)` 和 `_merge_data(max_rows=kline_days)` 确保所有股票分析数据长度一致。

### 策略评分系统

- **量干增强**: 缩量阴跌封顶、低位缩量封顶、放量滞涨封顶。输出 raw_score/caps/warnings/reject_reasons。
- **价稳增强**: 收盘紧致度、收盘位置辅助指标、MA20 天数制、支撑跌破封顶。
- **ATR 止损校验**: `risk_reward.py` 验证 risk_pct >= ATR14 × 1.2，过近则 warning。
- **7 状态决策系统**: `decision.py` 输出 REJECT / WAIT_VOLUME / WAIT_STABLE / WAIT_ENTRY / WAIT_RR / WATCH_BREAKOUT / BUY_LOW。`CANDIDATE_KEYS` 和 `REJECT_KEYS` 在 `strategy_engine.py` 定义，扫描和回测共用。
- **所有决策阈值可配**: `config.yaml` decision 段 + 前端决策规则区。
- **VCP 支持**: 回测和扫描均接受 VCP 形态。`vcp_contractions` 字段显示 T 数。前端形态分行显示杯柄/VCP 各自得分。

### 数据与配置

- **DB 诊断字段**: candidates 表新增 verdict_key / positive_factors / warnings / reject_reasons / raw_* / score_caps 列，自动迁移。
- **回测窗口独立配置**: `data.backtest_window_days` 独立于扫描的 `min_listing_days`，前端可配。
- **重新扫描策略**: 已完成任务可点「重新扫描策略」按钮，用当前配置重跑策略不重拉数据。
- **`daily_kline_days` 优先级**: 已从 config.yaml 移除显式值（否则 `or min_listing_days` 永远短路），`min_listing_days`（日线拉取天数）现在是主控参数。
- **指数数据源**: 创建专用 `_fetch_sina_index_raw()`，默认符号 `sh000001`（上证指数），不再复用个股代码映射。`config.yaml` 新增 `market_environment.index_symbol`。
- **真实 RR1**: `target_1` 使用真实上方压力位（pivot/近期高点/平台顶），不再人工构造 2R 导致 RR1 恒为 2。找不到真实压力位时 RR1=0 → WAIT_RR。
- **ATR 止损校验**: `RiskRewardResult.stop_too_close` 结构化状态，触发时阻塞 BUY_LOW 并返回 WAIT_ENTRY。
- **Pivot 双边距离**: 新增 `near_pivot_below_pct` 下限（默认 10%），远低于 Pivot 不再误判为 WATCH_BREAKOUT。
- **VCP 统一引擎**: `StrategyEngine.evaluate_at()` 不再在杯柄未命中时提前返回，统一运行 VCP 分析。移除 `engine.py` 中的重复 VCP 逻辑。
- **历史回测统一引擎**: `backtester.py` 使用 `CupHandleStrategyEngine` + 逐日大盘数据切片，防止未来数据泄漏。
- **数据源链顺序**: `_fetch_with_retry` 按 config 顺序迭代（baidu→sina→tencent），busy→跳过不标记为失败，主源用 `retry_attempts` 备源用 `fallback_attempts`。全部 busy→requeue，全部 fail→None。`FetchResult.source_errors` 保留各源失败详情。
- **历史回测真实止损**: `BacktestResult` 保存策略实际 `stop_loss`/`entry_zone`/`pattern_kind`，`_calc_forward` 使用真实止损而非 `breakout_price*0.95`。`min_score` 参数恢复生效。
- **VCP 身份模型**: `CupHandleResult.pattern_kind`（cup_handle/vcp），序列化含 `patternKind`，去重按 patternKind 分支避免 VCP 与杯柄碰撞。
- **最近阻力**: `_find_real_target()` 用 swing high 确认找最近上方阻力，不再用最远高点冒充。

### 前端

- **TaskCenter**: 「查看结果」带 task_id 跳转，ResultsRadar 预选对应任务。
- **StockDetail**: 诊断信息（warnings/caps/reject）、VCP T 数、URL 保持 task_id 上下文。
- **TopNav**: 手动 `isActive()` 替代 `router-link` 的 `active-class`。
- **回测页**: 表格列改为首次发现/最后确认/类型/分数/决策/回撤。日期支持手动输入+日历选择+格式校验，股票代码必填校验。回测数据不足时显示黄色覆盖警告而非报错。
- **回测数据拉取**: `_estimate_fetch_days` 上限 2000 天防 API 超限，数据覆盖不足时返回 partial 模式自动调整可用区间。
- **量干评分升级**: 总分 10→12，核心维度 A/B/C 各 3 分，D/E 各 1.5 分。决策阈值按比例上调。前端 slider 同步更新。
- **Baidu API 被限**: 百度 403 封禁，`_parse_payload` 加类型检查优雅降级，日志仅首次 WARNING，后续静默 fallback 到 sina/tencent。
- **外部数据源测试**: `tests/test_akshare_hist.py` (东财可用/腾讯bug)、`tests/test_tushare_hist.py` (需付费)。
- **安全**: 清理了 tushare 测试文件中的硬编码 token。

### 扫描 vs 回测一致性

所有入口共用 `CupHandleStrategyEngine.evaluate_at()` 和 `select_market_window()`。扫描路径使用 `scan_window_days` 截取策略数据，回测路径使用 `backtest_window_days`。当 `scan_window_days == backtest_window_days` 且输入数据、市场数据相同时，核心策略结果（passed / score / pattern_kind / verdict_key / key_pattern_type / stop_loss / entry_zone）完全一致。四类场景（杯柄/VCP/突破排除/策略拒绝）均有自动化测试覆盖。

### Gotchas（新增）

- **`upsert_candidate` 静默失败**: `on_progress` 中 upsert 异常会被 scan worker 吞掉，导致 candidates 表缺失但 task_stocks 有标记。已加 try/except + 扫描完成后自动 re_evaluate 兜底。
- **`scan_all` candidate_by_code 丢失**: 扫描中进度回调标记了候选但 `scan_all` 返回值可能为空。服务端扫描完成后检测 task_stocks 候选数 > 0 时自动触发 `re_evaluate_task` 同步。
- **并发 == 串行试源 + 锁自然分摊**: 不是"同一只股票并发拉多个源先到先得"，也不是"线程绑源"。每只股票串行试源，不同线程因锁竞争自然使用不同源。生产源为 baidu/sina/tencent，worker_count < 源数量时记录警告。
- **单股回测数据独立于扫描**: `ensure_backtest_data` 用默认 `max_rows=0`（不限），回测窗口由用户输入日期决定，不受 `kline_days` 限制。
- **Baidu API 403**: 百度已于 2026-06-09 封禁该接口。代码保留 baidu 在 source chain 首位，封禁期间快速失败静默跳过，解封即自动恢复。日志首次输出 WARNING，后续静默。
- **量干评分满分 12**: 历史代码中硬编码的 volume_dry 阈值（如 `>= 7` 表示观察）需注意现在满分是 12 而非 10。决策默认值已同步更新。

### Gotchas（2026-06-10 新增）

- **回测不可观察数据 ≠ 默认值**: `BacktestResult` 的 `hit_*`/`false_breakout_*` 默认 `None`（不是 `False`），`ret_*` 默认 `None`。未来数据不足时这些字段不被设置，聚合统计自动排除。新增代码中禁止使用 `False` 或 `0` 作为"无数据"的默认值。
- **`summarize_by_verdict` 返回 `avg_ret_10d=None`**: 没有可观察收益时返回 `None` 而非 `0.0`。前端/输出层需要处理 `None`（建议显示 `--`）。新增 `observed_10d_count` 字段。
- **数据源兼容字段一致性**: `fallback_source`/`fallback_attempts`/`fallback_error` 必须指向同一个源。主源失败备用源成功时，主源错误也已回填。使用 `_apply_source_compatibility_fields()` 统一 helper，不要在成功/失败路径分别拼接。
- **VCP ID 依赖真实收缩日期**: 不再使用滑动窗口边界，改用 `_find_vcp_contractions()` 返回的 `high_idx`/`low_idx` 生成 `vcpStartDate`/`vcpEndDate`。两个相邻窗口的同一 VCP 必须生成相同 ID。
- **候选排除已突破**: `is_breakout` 排除规则已收敛到 `CupHandleStrategyEngine._candidate_rules()`（severity=high）。所有入口通过 `evaluation.passed` 统一判断，不再需要在调用方重复检查。
- **第一止盈 = 最近阻力位**: `target_1` 取 pivot（杯口上方，未突破时）和最近 120 天 swing high 中的最小值，不再是人工构造的 2R。找不到上方阻力时 `target_1=0` 导致 `rr1=0` → WAIT_RR。

### Gotchas（2026-06-10 统一策略窗口与入口）

- **唯一策略入口**: 所有业务路径必须通过 `CupHandleStrategyEngine.evaluate_at()` 判断候选。禁止在任何调用方重复实现 `score >= threshold`、`verdict_key in CANDIDATE_KEYS`、`not result.is_breakout` 等规则。`evaluation.passed` 是唯一结论。
- **窗口配置统一解析**: 后端业务代码禁止直接读取 `config.get("data", {}).get("scan_window_days")` 或 `or 250`。必须使用 `resolve_strategy_windows(config)` 获取 `StrategyWindows` 实例。该函数拒绝 0、负数、浮点、字符串、布尔值，缺失时固定默认 250。
- **市场数据必须截断**: 所有策略入口传入市场数据前必须调用 `select_market_window(market_data, strategy_data[-1]["date"])`。直接传入完整市场数据会导致未来数据泄漏，破坏扫描与回测一致性。测试 mock 必须返回完整数据，由业务代码负责截断。
- **`daily_kline_days` 不再控制拉取**: 扫描和重新分析的拉取天数仅由 `liquidity.min_listing_days` 控制。代码中不应再出现 `data_cfg.get("daily_kline_days")`。
- **`--min-score` 已废弃**: `main.py backtest --min-score` 仅作为报告展示过滤，不参与策略候选判断。下一版本删除。
- **批量回测 `window_min` 已废弃**: `run_backtest()` 不再接受 `window_min` 参数。策略窗口由 `backtest_window_days` 控制，未来收益观察期固定为 `min_forward_days = 60`。
- **`_call_backtest_fetch`**: 批量回测通过该 helper 向数据源传入 `backtest_window_days + 60`，使用 `inspect.signature` 兼容有/无 `days` 参数的数据源函数。
- **回测循环边界**: `range(backtest_window_days, n - min_forward_days + 1)`，`+1` 确保数据长度恰好 `窗口+60` 时仍执行一次判断。
- **单股回测市场数据**: `run_single_stock_cuphandle_backtest()` 支持 `market_data` 参数注入，未注入时自动拉取并按判断日期截断。

### Gotchas（2026-06-26 yfinance 剔除）

- **yfinance 已从生产日线源剔除**: 根因是 yfinance 最新日 OHLC 可能与 sina/tencent 明显不一致，曾污染 `daily_ohlc`。生产源链、锁、默认配置、前端配置和依赖均只保留 `baidu`、`sina`、`tencent`。
- **显式 yfinance 配置应失败**: `_daily_fetch_fn("yfinance")` 必须抛 `Unknown daily data source`，不要为兼容旧配置重新注册 yfinance。
- **历史污染修复**: `tools/data_repair/repair_invalid_ohlc.py --refetch-yfinance-sourced --apply` 用三源重新拉取 `task_stocks` 中曾由 yfinance 成功写入的股票，并替换本地 `daily_ohlc`。
- **任务恢复不再限定错误类型**: `get_interrupted_task()` 匹配所有 `finished_at IS NULL` 的 failed/cancelled 任务。`mark_dead_tasks_as_failed()` 额外重置崩溃任务的 fetching 股票。代码 bug 导致的失败也可自动恢复。

## Recent Changes (2026-06-10 策略2)

### 策略2「极致量干价稳」

- **独立包 `strategy2/`**: 10 个模块 — models / indicators / scorer / rejection / risk / trend / engine / scanner / backtester / backtest_models。完全不依赖策略1的形态检测/评分/分析/决策。
- **共享日线服务**: `scanner/daily_data_service.py` 从 engine.py 提取多源拉取/重试/缓存逻辑（默认 baidu/sina/tencent），策略1、策略2和策略3共用。
- **数据库扩展**: `scan_tasks.strategy_type` 字段，`strategy2_candidates` 独立表，`strategy2_backtest_tasks/signals/opportunities/task_stocks/insufficient_stocks` 5 张回测表，兼容式迁移。
- **策略2 API**: 扫描 5 个端点 + 回测 10 个端点（启动/状态/列表/详情/机会/信号/股票状态/恢复/重试/取消）。
- **前端**: 策略2结果页、配置分区、双策略按钮、回测页（`Strategy2Backtest.vue`）。
- **测试**: 策略2核心 + 趋势 V2 35 项 + 回测 21 项。后端全量 508 项。前端 vitest 25 项。
- **修复轮次**: 11 轮代码审查 + 趋势 V1→V2 + Phase 1 回测可信度修复（信号合并/原子持久化/NEXT_OPEN/完整性校验/两阶段最终化）。
- **配置**: `config.yaml` 新增 `strategy2` 段（8 参数），前端可独立配置和校验。

### Gotchas（2026-06-10 策略2）

- **策略2 禁止导入策略1 模块**: `strategy2/` 不得导入 `scanner.pattern_detector`、`scanner.strategy_engine`、`analyzer.*` 等策略1判断模块。测试 `test_strategy2_independence.py` 通过 AST 扫描所有 `strategy2/*.py` 验证此规则。新增 strategy2 代码时不要添加对策略1形态/分析模块的 import。
- **策略2 候选独立存储**: 策略2候选写入 `strategy2_candidates` 表，不写入 `candidates` 表。前端策略2结果页通过 `/api/strategy2/candidates` 读取。API `/api/candidates` 仍只返回策略1候选。
- **`scan_tasks.strategy_type`**: 新任务自动写入 `STRATEGY_1_CUP_HANDLE` 或 `STRATEGY_2_EXTREME_DRY_STABLE`。旧任务该字段为 NULL，API 层按策略1解释。`get_scan_tasks()` 返回结果自动补默认值。
- **策略2 配置校验**: `ExtremeDryStableStrategyEngine.__init__()` 构造时即校验所有配置参数（窗口≥最低天数、最低≥60、支撑回看≥2、分数0-100、风险比0-1、溢价/缓冲0-0.2）。非法配置直接 `raise ValueError`。
- **策略2 key_support 排除评估日**: `compute_key_support(data, lookback_days)` 内部执行 `data[:-1]`，确保 T 日自身不参与最低收盘价计算。单日数据（无历史）返回 None → `INSUFFICIENT_STRATEGY_DATA`。
- **策略2 前端独立**: 策略2结果页不显示杯柄/VCP/突破/形态分等字段。扫描控制台双按钮分别调用不同 API（`/api/scan/start` vs `POST /api/strategy2/scans`）。任一策略运行时两个按钮同时禁用。
- **策略2 前端配置 API**: `StrategyConfig.vue` 保存 payload 包含 `strategy2` 段，后端 `PUT /api/config` 通过 `_deep_merge` 写入 `config.yaml`。前端校验窗口天数关系和范围同步后端 `ValueError` 检查。
- **策略2 趋势过滤 V2**: `evaluate_trend()` 使用价格路径+120日长期确认。必要条件：`close < MA20 AND MA20 < MA60`。8 项短中期证据 + 3 项长期证据，总分 ≥6 且 short≥4 且 long≥1 → DOWNTREND。禁止使用 RETURN_60/RETURN_120 端点收益。少于 120 日数据返回 `INSUFFICIENT_TREND_DATA` 并排除。趋势过滤在评分/风险/否决之前执行。重新评估后移除不再符合条件的旧候选，同步更新 `task_stocks` 状态。
- **趋势 V2 数据库字段**: `strategy2_candidates` 表兼容式新增 15 个趋势字段。旧候选空字段兼容显示 `--`。
- **策略2回测**: `replace_strategy2_stock_backtest_result()` 原子替换单股结果（事务化）。`build_strategy2_backtest_summary()` 从 DB 完整明细生成汇总。`validate_strategy2_backtest_integrity()` 校验任务完整性。两阶段最终化：先写聚合字段→再校验→更新可信度。取消使用 `threading.Event`，工作线程每只股票前检查。
- **策略2回测数据源**: 回测只读 `db.get_ohlc()` + `db.get_stock_pool()`，禁止调用 AKShare/百度/新浪/腾讯。`data_snapshot_date` 精确到秒，过滤 ohlc。
- **策略2本地数据优先**: 策略2实验、正式参数升级和验收分析默认只使用本地 `stock_pool` / `daily_ohlc`。没有用户明确要求时，不重新拉取百度/新浪/腾讯/AKShare/Tushare 数据。
- **外部数据源测试分离**: `test_akshare_hist.py`、`test_tushare_hist.py` 等真实网络测试仅手工按需运行；常规回归使用本地数据库测试和 mock 测试。
- **策略2回测执行模型**: 默认 `NEXT_OPEN`——信号日次日开盘入场，目标=入场价×1.05，止损=前10日最低收盘价×0.97。同日触发按 FAILED。未入场标记 `UNOBSERVED_ENTRY`/`NO_ENTRY_GAP_BELOW_STOP`/`NO_ENTRY_ABOVE_BUY_ZONE`。
- **策略2回测信号合并**: 使用 `evaluation_index + eval_results` 计算冷却期，10 个计入冷却期的未命中交易日拆分新机会。冷却期计入: LIQUIDITY/DOWNTREND/REJECTION/SCORE/RISK；不计入: INSUFFICIENT_DATA/INVALID_DATA/EVALUATION_ERROR。
- **策略2 Volume Percentile 窗口弹性**: 日线数据不足 60 天但 ≥ `minimum_required_days` 时，`volume_percentile_days` 取实际可用窗口天数，不强制 60。评分阈值 `≤20%` 不变。

### Gotchas（2026-06-11 策略2 验收修复）

- **全源失败不使用缓存**: 三数据源全部在线失败时，`fetch_with_retry()` 直接返回 `data=None`，股票标记 `failed / ALL_DATA_SOURCES_FAILED`。不使用本地缓存继续扫描。在线拉取成功时仍可与数据库历史合并并持久化。
- **三源收敛**: 生产数据源为 `baidu / sina / tencent`（可通过 `config.yaml` 的 `data.daily_sources` 配置，但不得包含 yfinance）。`mootdx_source.py` 和 yfinance 生产源均已删除。
- **跨策略执行隔离**: `_require_task_strategy(task_id, expected)` 统一校验。策略2 task_id 进入策略1 retry/re-evaluate/candidates 返回 `TASK_STRATEGY_MISMATCH` (400)。策略1 task_id 进入策略2 同理。
- **历史任务上下文**: URL `?task=` 参数是历史页面唯一任务上下文。`routeTaskId` / `isHistoricalMode` 两种互斥模式。`watch(route.query.task)` 支持 A→B→A→none 切换。历史任务策略类型从任务 API 返回，不依赖当前运行状态。
- **viewContext 竞态防护**: `beginViewContext()` 每次导航创建新 context。所有 async 函数在 `await` 后用 `isCurrentViewContext(context)` 校验防止 stale response 覆盖新任务。
- **单飞 poll session**: `activePollSession.inFlight` 防止重叠轮询。`clearPollTimer()` 仅停止 timer，正常完成时保留 session 以完成终态刷新。`invalidatePolling()` 用于任务切换和组件卸载，立即失效旧 session。
- **终态 session 生命周期**: `finalizeCompletedPoll` 在 finally 中调用 `resetPollSession()`。stale 时立即退出不写页面。接口失败时记录到 `refreshFailures[]`，继续执行其他独立刷新，始终写完成日志。
- **历史终态 summary**: `loadFailures` 接受 `applySummary` 参数（默认 false）。历史终态传 `applySummary: true` 以应用持久化的 processed/failed/candidate/latestTradeDate/stockPoolSource。
- **前端 vitest 约束**: `vi.useFakeTimers()` 与 Vue `setInterval` 不兼容。轮询相关测试应使用 deferred promise 构造异步时序，不依赖 fake timer 推进。组件测试使用 `ScanEngineStub` 精确断言 summary props。
- **策略2 scan_tasks.strategy_type**: 旧任务为 NULL → API 层默认按策略1。`get_task_strategy_type()` 返回 NULL 仅表示任务不存在。

## Design Specs（新增）

- 第三~六轮代码复查报告: `docs/reviews/2026-06-09-bug-fix-recheck-round*.md`
- 最终复查: `docs/reviews/2026-06-09-bug-fix-final-recheck.md`
- 统一策略窗口与入口设计: `docs/superpowers/specs/2026-06-10-scan-window-unified-strategy-design.md`
- 统一策略入口确认决策: `docs/superpowers/specs/2026-06-10-scan-window-unified-strategy-decisions.md`
- BUG 复查: `docs/reviews/2026-06-10-scan-window-unified-strategy-code-review.md`
- RECHECK 复查: `docs/reviews/2026-06-10-scan-window-unified-strategy-recheck.md`
- FINAL 复查: `docs/reviews/2026-06-10-scan-window-unified-strategy-final-recheck.md`
- COMPLETION 复查: `docs/reviews/2026-06-10-scan-window-unified-strategy-completion-recheck.md`
- ACCEPTANCE 复查: `docs/reviews/2026-06-10-scan-window-unified-strategy-acceptance-recheck.md`
- FINAL-COMPLETION 验收: `docs/reviews/2026-06-10-scan-window-unified-strategy-final-completion.md`
- yfinance 四源并发设计已作废，仅作为历史背景: `docs/superpowers/specs/2026-06-10-yfinance-four-source-daily-kline-design.md`
- 策略2趋势过滤V2: `docs/superpowers/specs/2026-06-11-strategy2-path-and-120d-trend-filter-v2.md`
- 策略2本地数据库短线回测: `docs/superpowers/specs/2026-06-11-strategy2-local-database-backtest-design.md`
- 策略2回测可信度修复: `docs/superpowers/specs/2026-06-12-strategy2-backtest-correctness-and-strategy-optimization-design.md`
- 策略2极致量干价稳设计: `docs/superpowers/specs/2026-06-10-strategy2-extreme-dry-stable-design.md`
- 策略2极致量干价稳实施计划: `docs/superpowers/plans/2026-06-10-strategy2-extreme-dry-stable.md`
- 策略2修复审核文档: `docs/reviews/2026-06-10-strategy2-*.md` / `2026-06-11-strategy2-*.md`
- 最终第三方审核指南: `docs/reviews/2026-06-11-strategy2-final-third-party-review-guide.md`

## .gitignore Policy

向 `.gitignore` 新增条目前，先告知用户确认。当前已忽略: Python 产物、虚拟环境、IDE 配置、`output_data/`、`logs/`、`cache/`、`data/`、`node_modules/`、`.superpowers/`。

# Git Safety Rules

Claude may read files, modify files, and run tests.

Allowed Git commands:

- git status
- git diff
- git log
- git branch
- git show
- git add
- git commit
- git push

Codex/Claude may automatically `git add`, `git commit`, and `git push` after verified development work. Do not push only when the user explicitly says not to push.

Never run destructive commands unless I explicitly approve the exact command:

- git reset --hard
- git clean -fd
- git clean -fdx
- git checkout .
- git restore .
- rm -rf

Before any commit or push:

1. Show or inspect git status.
2. Stage only files related to the current task unless the user explicitly asks to include more.
3. Summarize the change in the final response.

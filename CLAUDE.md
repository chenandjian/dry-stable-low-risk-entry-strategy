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
引擎层:    scanner/engine.py (3 线程扫描调度)
数据层:    scanner/db.py (SQLite 持久化)
           scanner/data_source.py (互斥锁管理 — baidu/sina/tencent)
           scanner/sina_source.py / tencent_source.py / baidu_source.py (HTTP抓取)
           scanner/stock_pool.py (股票池)
算法层:    scanner/pattern_detector.py (杯柄识别)
           scanner/liquidity_filter.py (流动性过滤)
           scanner/scorer.py (评分 0-100)
分析层:    analyzer/dry_stable.py → analyze_dry_stable() 串联全部分析
             ├─ analyzer/volume_dry.py (量干评分 0-10)
             ├─ analyzer/price_stable.py (价稳评分 0-10)
             ├─ analyzer/pattern_score.py (形态评分 0-20, 杯柄/VCP择优)
             ├─ analyzer/key_prices.py (关键价格/入场区间)
             ├─ analyzer/risk_reward.py (风险收益比 + 仓位建议)
             ├─ analyzer/invalid_rules.py (形态失效条件)
             ├─ analyzer/market_env.py (大盘环境评估)
             └─ analyzer/decision.py (7 状态决策：REJECT/WAIT_VOLUME/WAIT_STABLE/WAIT_ENTRY/WAIT_RR/WATCH_BREAKOUT/BUY_LOW)
回测层:    scanner/backtester.py (历史回测)
指标层:    scanner/index_source.py (大盘指数数据)
输出层:    output/csv_writer.py / json_writer.py
前端:      web/ (Vue 3 + lightweight-charts · 深色金融终端风格；ECharts 依赖存在但当前 web/src 未使用)
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

## Key Files

| File | Purpose |
|---|---|
| `config.yaml` | 所有可调参数（市场/流动性/杯体/柄部/突破/评分/输出/调度/数据库） |
| `scanner/db.py` | SQLite 数据库层 — 连接管理 + 5 表 CRUD |
| `scanner/data_source.py` | `DataSourceManager` — 新浪+腾讯双源互斥锁 |
| `scanner/sina_source.py` | `fetch_sina_daily(code, days)` → `list[dict] \| None` |
| `scanner/tencent_source.py` | `fetch_tencent_daily(code, days)` → `list[dict] \| None`（纯腾讯源，回退由引擎层处理） |
| `scanner/pattern_detector.py` | `detect_cup_handle(data, config)` → `CupHandleResult`；只负责杯柄检测 |
| `scanner/scorer.py` | `score_cup_handle(result)` / `score_cup_handle_advanced(result, data)` → `int` (0-100) |
| `scanner/engine.py` | `scan_all(config)` — 双线程全市场扫描主循环 |
| `scanner/backtester.py` | `run_backtest(stocks, fetch_fn, config)` — 历史回测 |
| `analyzer/volume_dry.py` | `score_volume_dry(data)` → `VolumeDryResult` (0-10) |
| `analyzer/price_stable.py` | `score_price_stable(data)` → `PriceStableResult` (0-10) |
| `analyzer/pattern_score.py` | `score_pattern(result, data)` → `PatternScoreResult` (0-20, 杯柄/VCP 择优；VCP 识别在这里) |
| `analyzer/key_prices.py` | `calculate_key_prices(...)` → `KeyPricesResult` (入场区间/支点/止损/目标) |
| `analyzer/risk_reward.py` | `calculate_risk_reward(...)` → `RiskRewardResult` |
| `analyzer/dry_stable.py` | `analyze_dry_stable(result, data, market_data)` → `dict` — 串联全部 8 个分析模块 |
| `analyzer/decision.py` | `make_dry_stable_decision(...)` → `DryStableDecision` — 最终买入判决 |
| `analyzer/market_env.py` | `assess_market_environment(market_data)` → `MarketEnvResult` |
| `analyzer/invalid_rules.py` | `find_invalid_conditions(...)` → `list[str]` |
| `scanner/index_source.py` | `fetch_market_index_daily(code)` → `list[dict]` (复用新浪源) |
| `server.py` | FastAPI API + 扫描任务编排 — CORS/lifespan、恢复中断任务、失败重拉、配置读写 |
| `web/src/pages/ScannerConsole.vue` | 前端首页 — 机会雷达控制台 |

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
- **CLI analyze 与扫描不等价**: `main.py analyze` 在杯柄未命中时直接返回，不会像 `engine.py` 那样继续把 VCP-only 机会提升为候选。
- **Backtester 非线上扫描镜像**: `scanner/backtester.py` 使用滑窗 + 基础杯柄检测/评分做历史评估，不完整复刻 server/engine 的任务追踪、fresh-first、VCP-only 候选提升等逻辑。
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

### 前端

- **TaskCenter**: 「查看结果」带 task_id 跳转，ResultsRadar 预选对应任务。
- **StockDetail**: 诊断信息（warnings/caps/reject）、VCP T 数、URL 保持 task_id 上下文。
- **TopNav**: 手动 `isActive()` 替代 `router-link` 的 `active-class`。
- **回测页**: 表格列改为首次发现/最后确认/类型/分数/决策/回撤。日期支持手动输入+日历选择+格式校验，股票代码必填校验。回测数据不足时显示黄色覆盖警告而非报错。
- **回测数据拉取**: `_estimate_fetch_days` 上限 2000 天防 API 超限，数据覆盖不足时返回 partial 模式自动调整可用区间。

### 扫描 vs 回测一致性

两者共用同一套策略引擎、决策规则、候选过滤常量。唯一差异：扫描用 `min_listing_days` 控制窗口，回测用 `backtest_window_days`（默认均为 250）。

### Gotchas（新增）

- **`upsert_candidate` 静默失败**: `on_progress` 中 upsert 异常会被 scan worker 吞掉，导致 candidates 表缺失但 task_stocks 有标记。已加 try/except + 扫描完成后自动 re_evaluate 兜底。
- **`scan_all` candidate_by_code 丢失**: 扫描中进度回调标记了候选但 `scan_all` 返回值可能为空。服务端扫描完成后检测 task_stocks 候选数 > 0 时自动触发 `re_evaluate_task` 同步。
- **并发 == 串行试源 + 锁自然分摊**: 不是"同一只股票并发拉 3 个源先到先得"，也不是"线程绑源"。每只股票串行试源，不同线程因锁竞争自然使用不同源。
- **单股回测数据独立于扫描**: `ensure_backtest_data` 用默认 `max_rows=0`（不限），回测窗口由用户输入日期决定，不受 `kline_days` 限制。

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

Do not run git add, git commit, git push, git pull, git merge, or git rebase unless I explicitly ask.

Never run destructive commands unless I explicitly approve the exact command:

- git reset --hard
- git clean -fd
- git clean -fdx
- git checkout .
- git restore .
- rm -rf

Before any commit:

1. Show git status.
2. Show the files to be committed.
3. Summarize the changes.
4. Wait for my confirmation.

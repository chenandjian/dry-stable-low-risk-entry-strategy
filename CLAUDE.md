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
引擎层:    scanner/engine.py (双线程扫描调度)
数据层:    scanner/db.py (SQLite 持久化)
           scanner/data_source.py (互斥锁管理)
           scanner/sina_source.py / tencent_source.py (HTTP抓取)
           scanner/stock_pool.py (股票池)
算法层:    scanner/pattern_detector.py (杯柄识别)
           scanner/liquidity_filter.py (流动性过滤)
           scanner/scorer.py (评分 0-100)
分析层:    analyzer/volume_dry.py (量干评分 0-10)
           analyzer/price_stable.py (价稳评分 0-10)
           analyzer/pattern_score.py (形态评分 0-20)
           analyzer/key_prices.py + risk_reward.py (关键价格/仓位)
回测层:    scanner/backtester.py (历史回测)
输出层:    output/csv_writer.py / json_writer.py
前端:      web/ (Vue 3 + ECharts · 深色金融终端风格)
```

**核心设计决策:**

- **数据源互斥锁：** 两个扫描线程不能同时请求同一个数据源（新浪/腾讯）。`DataSourceManager` 用 `threading.Lock(blocking=False)` 实现非阻塞互斥。线程取不到锁时 sleep 0.1s 后重试。
- **扫描 fresh-first：** 点击开始扫描默认重新拉取个股日线；缓存只用于合并历史和详情展示，主备数据源都失败时不能用旧缓存生成扫描结果。
- **腾讯源内置新浪回退：** `fetch_tencent_daily()` 内部可能请求新浪；在扫描线程中调用腾讯源时也要考虑新浪锁，避免绕过 `DataSourceManager`。
- **扫描任务追踪：** `scan_tasks` 记录任务级统计，`task_stocks` 记录每只股票的 `pending/fetching/scanned/skipped/failed/candidate`、失败原因、数据源尝试和最新 K 线日期。
- **候选去重：** 同一任务内候选按 `(task_id, code)` 唯一；内存层用 code 字典去重，数据库层用唯一索引/upsert，前端按 code 归并。
- **全局扫描互斥：** 任意时刻只允许一个扫描过程（全量、失败重拉、调度、恢复）；启动前同时检查 `_running` 和 DB 中 `status='running'` 的任务。
- **失败重拉：** `/api/scan/tasks/{task_id}/retry-failed` 只处理原任务 `failed` 股票，使用 `retry_policy='failed_only'` 重跑完整个股扫描逻辑。
- **三级回退：** 主数据源 → 备用数据源 → 本地缓存。AKShare 仅用于获取股票池，不用于OHLC数据。
- **单只失败不中断：** 全市场扫描中，单只股票异常（超时/解析错误/停牌）记录日志后跳过，不中断整体任务。
- **数据源锁必须释放：** `try...finally` 确保异常路径也释放锁。
- **配置文件驱动：** 所有阈值（杯体深度、柄部回撤、流动性等）在 `config.yaml` 中可调。
- **形态评分维度：** 杯体结构 35 + 柄部结构 25 + 成交量结构 20 + 前置趋势 10 + 突破确认 10 = 100 分。
- **A股配色：** 红涨绿跌。金色仅用于 ≥80 分 A 级信号。
- **SQLite 持久化：** 数据存储于 `data/cuphandle.db`（stock_pool, daily_ohlc, scan_tasks, candidates）。线程级连接 + WAL 模式。
- **新浪 API：** `quotes.sina.cn/cn/api/jsonp_v2.php/data/CN_MarketDataService.getKLineData` — 返回 JSONP 需手动解析。腾讯 API 不可用时内部回退到新浪。

## Key Files

| File | Purpose |
|---|---|
| `config.yaml` | 所有可调参数（市场/流动性/杯体/柄部/突破/评分/输出/调度/数据库） |
| `scanner/db.py` | SQLite 数据库层 — 连接管理 + 5 表 CRUD |
| `scanner/data_source.py` | `DataSourceManager` — 新浪+腾讯双源互斥锁 |
| `scanner/sina_source.py` | `fetch_sina_daily(code, days)` → `list[dict] \| None` |
| `scanner/tencent_source.py` | `fetch_tencent_daily(code, days)` → `list[dict] \| None`（内部回退新浪） |
| `scanner/pattern_detector.py` | `detect_cup_handle(data, config)` → `CupHandleResult` |
| `scanner/scorer.py` | `score_cup_handle(result)` / `score_cup_handle_advanced(result, data)` → `int` (0-100) |
| `scanner/engine.py` | `scan_all(config)` — 双线程全市场扫描主循环 |
| `scanner/backtester.py` | `run_backtest(stocks, fetch_fn, config)` — 历史回测 |
| `analyzer/volume_dry.py` | `score_volume_dry(data)` → `VolumeDryResult` (0-10) |
| `analyzer/price_stable.py` | `score_price_stable(data)` → `PriceStableResult` (0-10) |
| `analyzer/risk_reward.py` | `calculate_risk_reward(...)` → `RiskRewardResult` |
| `server.py` | FastAPI 服务 — CORS + lifespan + 历史持久化 |
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

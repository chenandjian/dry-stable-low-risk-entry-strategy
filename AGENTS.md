# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

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

# 前端开发
cd web && npm install && npm run dev

# 前端构建
cd web && npm run build
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
- **三级回退：** 主数据源 → 备用数据源 → 本地缓存。AKShare 仅用于获取股票池，不用于OHLC数据。
- **单只失败不中断：** 全市场扫描中，单只股票异常（超时/解析错误/停牌）记录日志后跳过，不中断整体任务。
- **数据源锁必须释放：** `try...finally` 确保异常路径也释放锁。
- **配置文件驱动：** 所有阈值（杯体深度、柄部回撤、流动性等）在 `config.yaml` 中可调。
- **形态评分维度：** 杯体结构 35 + 柄部结构 25 + 成交量结构 20 + 前置趋势 10 + 突破确认 10 = 100 分。
- **A股配色：** 红涨绿跌。金色仅用于 ≥80 分 A 级信号。
- **SQLite 持久化：** 数据存储于 `data/cuphandle.db`（stock_pool, daily_ohlc, scan_tasks, candidates）。线程级连接 + WAL 模式。
- **新浪 API：** `quotes.sina.cn/cn/api/jsonp_v2.php/data/CN_MarketDataService.getKLineData` — 返回 JSONP 需手动解析。腾讯 API 不可用时内部回退到新浪。

## Key Files

| File                               | Purpose                                                                                |
| ---------------------------------- | -------------------------------------------------------------------------------------- |
| `config.yaml`                      | 所有可调参数（市场/流动性/杯体/柄部/突破/评分/输出/调度/数据库）                       |
| `scanner/db.py`                    | SQLite 数据库层 — 连接管理 + 5 表 CRUD                                                 |
| `scanner/data_source.py`           | `DataSourceManager` — 新浪+腾讯双源互斥锁                                              |
| `scanner/sina_source.py`           | `fetch_sina_daily(code, days)` → `list[dict] \| None`                                  |
| `scanner/tencent_source.py`        | `fetch_tencent_daily(code, days)` → `list[dict] \| None`（内部回退新浪）               |
| `scanner/pattern_detector.py`      | `detect_cup_handle(data, config)` → `CupHandleResult`                                  |
| `scanner/scorer.py`                | `score_cup_handle(result)` / `score_cup_handle_advanced(result, data)` → `int` (0-100) |
| `scanner/engine.py`                | `scan_all(config)` — 双线程全市场扫描主循环                                            |
| `scanner/backtester.py`            | `run_backtest(stocks, fetch_fn, config)` — 历史回测                                    |
| `analyzer/volume_dry.py`           | `score_volume_dry(data)` → `VolumeDryResult` (0-10)                                    |
| `analyzer/price_stable.py`         | `score_price_stable(data)` → `PriceStableResult` (0-10)                                |
| `analyzer/risk_reward.py`          | `calculate_risk_reward(...)` → `RiskRewardResult`                                      |
| `server.py`                        | FastAPI 服务 — CORS + lifespan + 历史持久化                                            |
| `web/src/pages/ScannerConsole.vue` | 前端首页 — 机会雷达控制台                                                              |

## Design Specs

- 系统设计: `docs/superpowers/specs/2026-06-03-cuphandle-scan-design.md`
- Phase 1 计划: `docs/superpowers/plans/2026-06-03-cuphandle-scan-phase1.md`
- 原始开发需求: `docs/DEVELOPMENT_DOC.md` (杯柄扫描) + `docs/dry-stable-low-risk-entry-strategy.md` (干稳低吸策略)
- 前端设计需求: `docs/art.md`

## Gotchas

- **`PRAGMA table_info`**: 返回 `(cid, name, type, ...)`，取列名用 `d[1]`，不是 `d[0]`。`db.py` 中 `get_candidates` 和 `get_candidate` 用错了会返回整数 key。
- **进程管理**: Windows 下 `taskkill //F //IM python.exe`（双斜杠），单斜杠会解析失败。服务重启前必须确保所有旧 Python 进程已死，否则旧代码继续跑在新端口上。
- **新浪 API**: 返回 JSONP 格式 `data([...]);`，需要手动 `text[5:-2]` 后解析 JSON。
- **Scan 线程崩溃**: `server.py` 中 scan 线程的 `except` 现已含 `traceback.format_exc()`，但需检查日志才能看到。`_running["stats"]` 为空即扫描未正常启动。
- **config.yaml 中的假参数**: `data.cache_dir`、`data.start_date`、`cup.filter_v_shape`、`output.csv/json/charts`、`scheduler.webhook_url` 等键存在于 yaml 但代码中未使用。新增配置项前先确认代码已接入。

## .gitignore Policy

向 `.gitignore` 新增条目前，先告知用户确认。当前已忽略: Python 产物、虚拟环境、IDE 配置、`output_data/`、`logs/`、`cache/`、`data/`、`node_modules/`、`.superpowers/`。

# Git Safety Rules

Codex may read files, modify files, and run tests.

Never run destructive commands unless I explicitly approve the exact command:

- git reset --hard
- git clean -fd
- git clean -fdx
- git checkout .
- git restore .
- rm -rf

## 8. 开发哲学

| instruction                                      | notes        |
| ------------------------------------------------ | ------------ |
| 必须坚持渐进式迭代，保持每次改动可编译、可验证   | 小步快跑     |
| 必须在实现前研读既有代码或文档，吸收现有经验     | 学习优先     |
| 必须保持务实态度，优先满足真实需求而非理想化设计 | 实用主义     |
| 必须选择表达清晰的实现，拒绝炫技式写法           | 可读性优先   |
| 必须偏向简单方案，避免过度架构或早期优化         | 简单优于复杂 |
| 必须遵循既有代码风格，包括导入顺序、命名与格式化 | 保持一致性   |

**简单性定义**：

- 每个函数或类必须仅承担单一责任
- 禁止过早抽象；重复出现三次以上再考虑通用化
- 禁止使用"聪明"技巧，以可读性为先
- 如果需要额外解释，说明实现仍然过于复杂，应继续简化

**项目集成原则**：

- 必须寻找至少 3 个相似特性或组件，理解其设计与复用方式
- 必须识别项目中通用模式与约定，并在新实现中沿用
- 必须优先使用既有库、工具或辅助函数
- 必须遵循既有测试编排，沿用断言与夹具结构
- 必须使用项目现有构建系统，不得私自新增脚本
- 必须使用项目既定的测试框架与运行方式
- 必须使用项目的格式化/静态检查设置

## 9. 行为准则

| instruction                                                | notes        |
| ---------------------------------------------------------- | ------------ |
| 自主规划和决策，仅在真正需要用户输入时才询问               | 最大化自主性 |
| 基于观察和分析做出最终判断和决策                           | 自主决策     |
| 充分分析和思考后再执行，避免盲目决策                       | 深思熟虑     |
| 禁止假设或猜测，所有结论必须援引代码或文档证据             | 证据驱动     |
| 如实报告执行结果，包括失败和问题，记录到 operations-log.md | 透明记录     |
| 在实现复杂任务前完成详尽规划并记录                         | 规划先行     |
| 对复杂任务维护 TODO 清单并及时更新进度                     | 进度跟踪     |
| 保持小步交付，确保每次提交处于可用状态                     | 质量保证     |
| 主动学习既有实现的优缺点并加以复用或改进                   | 持续改进     |
| 连续三次失败后必须暂停操作，重新评估策略                   | 策略调整     |

**极少数例外需要用户确认的情况**（仅以下场景）：

- 删除核心配置文件（package.json、tsconfig.json、.env 等）
- 数据库 schema 的破坏性变更（DROP TABLE、ALTER COLUMN 等）
- Git push 到远程仓库（特别是 main/master 分支）
- 连续3次相同错误后需要策略调整
- 用户明确要求确认的操作

**默认自动执行**（无需确认）：

- 所有文件读写操作
- 代码编写、修改、重构
- 文档生成和更新
- 测试执行和验证
- 依赖安装和包管理
- Git 操作（add、commit、diff、status、 push等）
- 构建和编译操作
- 工具调用（code-index、exa、grep、find 等）
- 按计划执行的所有步骤
- 错误修复和重试（最多3次）

**判断原则**：

- 如果不在"极少数例外"清单中 → 自动执行
- 如有疑问 → 自动执行（而非询问）
- 宁可执行后修复，也不要频繁打断工作流程

---

**协作原则总结**：

- 我规划，我决策
- 我观察，我判断
- 我执行，我验证
- 遇疑问，评估后决策或询问用户

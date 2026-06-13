# AGENTS.md

本文件约束 Codex 在当前 worktree 中的开发行为。项目事实、历史决策和更完整的 Gotchas 以同目录 `CLAUDE.md` 为准；开始非简单任务前必须先读 `CLAUDE.md`，再读相关设计文档、代码和测试。若文档、代码、测试冲突，以当前代码和可复现实验为最终依据，并同步修正文档。

## Codex 双角色闭环流程

以后在 Codex 中开发，按这个标准流程执行：

1. 先阅读设计文档、`CLAUDE.md`、相关代码、数据模型和测试。
2. 以程序员角色开发，保持小步提交、可编译、可验证。
3. 开发完成后切换为审核专家角色验收，重点看业务正确性、数据一致性、缓存/并发、边界条件和回归风险。
4. 发现中/高等级问题后，切回程序员角色修复。
5. 再次验收，循环直到没有中/高等级问题。
6. 遇到无法判断或无法安全修复的问题，向用户提问。
7. 验证通过后自动 `git add`、`git commit`、`git push`；如果用户明确说不要 push，或网络 push 失败，则保留本地提交并如实报告。

Bug 修复优先使用 TDD：先写能稳定复现问题的失败测试，再做最小修复，最后运行专项和回归测试。

## Project

CupHandleScan 是 Python 3.10+ 的 A 股扫描系统，当前 worktree 包含两套独立策略：

- 策略1：杯柄/VCP 扫描，统一入口 `scanner/strategy_engine.py::CupHandleStrategyEngine.evaluate_at()`。
- 策略2：极致量干价稳扫描，统一入口 `strategy2/engine.py::ExtremeDryStableStrategyEngine.evaluate_at()`。

策略2不得导入策略1的形态检测、评分、分析或决策模块。允许复用共享数据层、流动性过滤、SQLite 基础能力和 `scanner/daily_data_service.py`。

## Commands

后端常规验证：

```bash
python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py --ignore=tests/test_yfinance_hist.py
python -m pytest tests/test_strategy2_backtester.py -v
python -m compileall scanner strategy2 server.py -q
```

前端命令必须从仓库/worktree 根目录使用 `--prefix`：

```bash
npm --prefix web install
npm --prefix web test -- --run
npm --prefix web run build
```

真实外部数据源测试仅手工按需运行，不纳入常规回归：

```bash
python -m pytest tests/test_akshare_hist.py -v
python -m pytest tests/test_tushare_hist.py -v
python -m pytest tests/test_yfinance_hist.py -v
```

## Architecture

```text
入口: main.py / server.py / scheduler/scheduler.py
策略1: scanner/engine.py + scanner/strategy_engine.py
策略2: strategy2/scanner.py + strategy2/engine.py
共享数据: scanner/db.py + scanner/daily_data_service.py + scanner/data_source.py
策略2回测: strategy2/backtester.py + strategy2/backtest_models.py + server.py 回测任务编排
前端: web/ Vue 3 + lightweight-charts
```

关键边界：

- `CupHandleStrategyEngine.evaluate_at()` 是策略1唯一候选判断入口；调用方不得重复实现评分门槛、形态类型、决策状态或突破排除规则。
- `ExtremeDryStableStrategyEngine.evaluate_at()` 是策略2唯一判断入口；策略2不使用杯柄/VCP形态判断。
- `scan_tasks.strategy_type` 区分 `STRATEGY_1_CUP_HANDLE` 与 `STRATEGY_2_EXTREME_DRY_STABLE`。
- 策略2候选写入 `strategy2_candidates`，不得写入策略1的 `candidates`。
- 策略2 API、任务、候选、回测结果必须与策略1隔离，跨策略 task_id 应返回 `TASK_STRATEGY_MISMATCH`。

## Strategy2 数据与回测规则

- 策略2扫描、实验、正式参数升级、验收分析和回测默认只使用本地 `stock_pool` / `daily_ohlc`。
- 没有用户明确要求时，不重新拉取 Baidu/Sina/Tencent/yfinance/AKShare/Tushare 数据。
- 三数据源或多数据源全部在线失败时，不使用旧缓存产出扫描结果；股票应标记为失败并保留失败原因。
- 回测只读本地 DB，禁止调用任何外部行情源。
- `NEXT_OPEN` 是可信基线执行模型，不得改回信号日收盘成交。
- 同一股票两个命中之间累计 10 个有效未命中交易日后，才拆分为新机会。
- 原始信号和机会必须可追溯；单股重跑必须原子替换且幂等。
- `strategy2_backtest_task_stocks` 是逐股状态、进度、漏斗和审计的事实来源。
- 任务必须保存原配置快照、股票范围、数据快照日期和数据版本；恢复/重试不得使用最新配置或变化后的数据。
- 只有状态为 `completed`、全部股票终态、汇总完整且无失败/评估异常的任务可以成为 `TRUSTED_BASELINE`。
- `CANCELED`、`INTERRUPTED`、`FAILED`、`completed_with_errors` 均不得成为可信基线。
- 完整执行但零机会是合法结果，必须生成完整零值汇总。

## Strategy2 规则边界

- 评分体系：量干 50 + 价稳 50，总分 100。
- 一票否决：`return_5<-5%`、放量下跌、`range_5>8%`、收盘低于 `key_support`、`return_3>=8%`。
- `key_support` 不含评估日 T，只取 T 之前的历史窗口。
- 入选条件：总分达到配置阈值、无否决、风险比不超过配置阈值。
- 趋势过滤 V2 在评分/风险/否决之前执行；少于 120 日趋势数据时返回 `INSUFFICIENT_TREND_DATA` 并排除。
- Phase 1 回测可信度修复不得顺手改变策略2评分、趋势、否决、风险规则和信号语义。

## Database Rules

- SQLite 使用线程级连接和 WAL。
- `PRAGMA table_info` 取列名必须用 `d[1]`。
- 兼容迁移使用 `_ensure_column()`；不得执行破坏性 schema 变更。
- 逐股信号、机会、任务股票终态必须在同一事务中写入。
- 新增任务字段必须兼容旧库；旧任务不可被错误升级为可信基线。
- `replace_strategy2_stock_backtest_result()` 必须保持单股结果原子替换。
- `build_strategy2_backtest_summary()` 汇总应从 DB 完整明细生成，不依赖易漂移的内存计数。

## Frontend Rules

- worktree 中前端命令使用 `npm --prefix web ...`。
- 策略2结果页不显示杯柄/VCP/突破/形态分等策略1字段。
- 扫描控制台双策略按钮分别调用 `/api/scan/start` 和 `POST /api/strategy2/scans`。
- 任一策略运行时两个启动按钮应同时禁用。
- 历史任务上下文以 URL `?task=` 为准；异步响应必须防 stale context 覆盖当前页面。
- 轮询终态刷新失败时，应保留能成功加载的数据，并明确展示刷新失败信息。

## Git Safety

允许在验证后自动执行：

- `git status`
- `git diff`
- `git log`
- `git branch`
- `git show`
- `git add`
- `git commit`
- `git push`

禁止在未获得用户对精确命令的明确批准时执行：

- `git reset --hard`
- `git clean -fd`
- `git clean -fdx`
- `git checkout .`
- `git restore .`
- `rm -rf`

不得覆盖或回退用户已有修改。向 `.gitignore` 新增条目前先告知用户确认。

## Worktree Merge Flow

正常 worktree 开发完成后：

1. 在 worktree 中确认 `git status`、运行必要测试并提交当前分支。
2. 回到主仓库 main，确认不会覆盖用户未提交修改。
3. 合并 worktree 分支到 main。
4. 在 main 上至少运行与改动相关的轻量验证；涉及代码时运行完整门禁。
5. push main；如果 push 失败，不要反复纠缠，报告本地已合并和失败原因。

## Delivery

最终回复必须包含：

- 修改文件与核心变化。
- 已运行命令及真实结果。
- 未验证部分与残余风险。
- commit hash。
- push 是否成功；如果失败，说明失败原因。

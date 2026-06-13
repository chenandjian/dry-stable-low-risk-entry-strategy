# AGENTS.md

本文件约束 Codex 在本仓库中的开发行为。项目事实以同目录 `CLAUDE.md`、当前代码和测试为准；三者冲突时，先验证代码与测试，再同步文档。

## Project

CupHandleScan 是 Python 3.10+ 的 A 股扫描系统，包含两套独立策略：

- 策略1：杯柄/VCP 扫描，统一入口 `scanner/strategy_engine.py::CupHandleStrategyEngine.evaluate_at()`
- 策略2：极致量干价稳扫描，统一入口 `strategy2/engine.py::ExtremeDryStableStrategyEngine.evaluate_at()`

策略2不得导入策略1的形态检测、评分、分析或决策模块。共享数据层、流动性过滤和 SQLite 基础能力可以复用。

## Commands

```bash
python -m pytest tests/ -v
python -m pytest tests/test_strategy2_backtester.py -v
python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py --ignore=tests/test_yfinance_hist.py
python -m compileall scanner strategy2 server.py -q

npm --prefix web install
npm --prefix web test -- --run
npm --prefix web run build
```

worktree 中运行前端命令必须使用 `npm --prefix web ...`，避免在错误目录寻找 `package.json`。

## Architecture

```text
入口: main.py / server.py / scheduler/scheduler.py
策略1: scanner/engine.py + scanner/strategy_engine.py
策略2: strategy2/scanner.py + strategy2/engine.py
共享数据: scanner/db.py + scanner/daily_data_service.py + scanner/data_source.py
策略2回测: strategy2/backtester.py + strategy2/backtest_models.py + server.py 回测任务编排
前端: web/ Vue 3 + lightweight-charts
```

## Current Strategy2 Backtest Invariants

- 回测只读取本地 `stock_pool` 和 `daily_ohlc`，禁止请求任何外部数据源。
- 策略2实验、正式参数升级和验收分析均优先使用本地股票数据；没有用户明确要求时，不重新拉取百度/新浪/腾讯/yfinance/AKShare/Tushare 数据。
- 外部数据源验证脚本仅手工按需运行；常规回归使用本地数据库测试和 mock 测试。
- `NEXT_OPEN` 是 Phase 1 可信基线执行模型；不得改回信号日收盘成交。
- 同一股票两个命中之间累计 10 个有效未命中交易日后，才拆分为新机会。
- 原始信号和机会必须可追溯；单股重跑必须原子替换且幂等。
- `strategy2_backtest_task_stocks` 是逐股状态、进度、漏斗和审计的事实来源。
- 任务必须保存原配置快照、股票范围、数据快照日期和数据版本；恢复/重试不得使用最新配置或变化后的数据。
- 只有状态为 `completed`、全部股票终态、汇总完整且无失败/评估异常的任务可以成为 `TRUSTED_BASELINE`。
- `CANCELED`、`INTERRUPTED`、`FAILED`、`completed_with_errors` 均不得成为可信基线。
- 完整执行但零机会是合法结果，必须生成完整零值汇总。
- 本轮 Phase 1 修复不得修改策略2评分、趋势、否决、风险规则和信号语义。

## Database Rules

- SQLite 使用线程级连接和 WAL。
- `PRAGMA table_info` 列名取 `d[1]`。
- 兼容迁移使用 `_ensure_column()`；不得执行破坏性 schema 变更。
- 逐股信号、机会、任务股票终态必须在同一事务中写入。
- 新增任务字段必须兼容旧库；旧任务不可被错误升级为可信基线。

## Workflow

1. 先阅读需求、相关设计/复查文档、入口、调用链、数据模型和测试。
2. 复杂任务先维护实施计划和 TODO。
3. Bug 修复先定位根因，并先写能稳定复现问题的失败测试。
4. 小步修改；不做无关重构，不改变公共契约或策略语义。
5. 每个模块修改后运行对应专项测试，完成前运行全量门禁。
6. 如实将重要执行结果、失败和风险记录到 `operations-log.md`。
7. 修改完成并验证后自动执行 `git add` ， `git commit` ，`git push`。

## Git Safety

禁止在未获得用户对精确命令的明确批准时执行：

- `git reset --hard`
- `git clean -fd`
- `git clean -fdx`
- `git checkout .`
- `git restore .`
- `rm -rf`

不得覆盖或回退用户已有修改。向 `.gitignore` 新增条目前先告知用户确认。

## Verification And Delivery

完成代码修改后必须报告：

- 修改文件与根因修复方式
- 数据库/API/兼容性影响
- 已运行命令及真实结果
- 未验证部分与残余风险

不能运行测试时必须明确说明原因；不得用“应该可以”代替验证结果。

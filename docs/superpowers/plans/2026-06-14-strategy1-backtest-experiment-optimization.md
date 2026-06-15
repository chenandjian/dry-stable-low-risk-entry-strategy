# Strategy1 Backtest Experiment Optimization 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 为策略1建设可信本地历史回测、实验对比和后续正式参数优化基础。

**架构：** 新增 Strategy1 专属回测模型、实验层、回测器和任务服务，复用 `CupHandleStrategyEngine.evaluate_at()` 作为唯一策略判断入口。数据库新增 `strategy1_backtest_*` 表保存任务、股票状态、原始信号、合并机会和汇总，API/前端提供任务启动、详情、机会、信号、股票状态、实验预览与基线对比入口。

**技术栈：** Python 3.10+、SQLite、FastAPI、Vue 3、pytest、Vitest。

---

## 文件结构

- 创建 `scanner/strategy1_backtest_models.py`：策略1回测 dataclass 与 horizon 模型。
- 创建 `scanner/strategy1_backtest_experiments.py`：实验配置标准化、过滤与机会分组纯函数。
- 创建 `scanner/strategy1_backtester.py`：本地 DB 日线逐股回放、信号生成、机会合并、NEXT_OPEN 和 3/5/10/20 表现。
- 创建 `scanner/strategy1_backtest_service.py`：任务创建/运行/最终化、数据版本和引擎版本校验。
- 修改 `scanner/db.py`：兼容创建策略1回测表，保存/查询任务、股票、信号、机会、汇总和对比。
- 修改 `server.py`：新增 `/api/strategy1/backtests*` API。
- 修改 `web/src/composables/useApi.js`：新增策略1回测 API helper。
- 新增 `web/src/pages/Strategy1Backtest.vue` 并修改路由/导航。
- 新增后端测试 `tests/test_strategy1_backtest_experiments.py`、`tests/test_strategy1_backtest_db_api.py`、`tests/test_strategy1_backtester.py`。
- 新增前端测试 `web/src/pages/__tests__/Strategy1Backtest.actions.test.js`。

## 任务

### 任务 1：实验配置和模型

- [ ] 写失败测试：`tests/test_strategy1_backtest_experiments.py` 覆盖默认 disabled、camel/snake 入参、越界校验、分数/杯体/柄部/风险过滤原因。
- [ ] 实现 `scanner/strategy1_backtest_models.py` 和 `scanner/strategy1_backtest_experiments.py`。
- [ ] 运行 `python -m pytest tests/test_strategy1_backtest_experiments.py -q`。

### 任务 2：纯回测计算

- [ ] 写失败测试：`tests/test_strategy1_backtester.py` 覆盖 NEXT_OPEN、3/5/10/20 horizon、时间退出优先级、连续信号合并、实验关闭等同基线。
- [ ] 实现 `scanner/strategy1_backtester.py` 的纯函数与单股回放。
- [ ] 运行 `python -m pytest tests/test_strategy1_backtester.py -q`。

### 任务 3：数据库持久化

- [ ] 写失败测试：`tests/test_strategy1_backtest_db_api.py` 覆盖表创建、任务快照、信号/机会保存、单股原子替换、汇总和对比不可比原因。
- [ ] 修改 `scanner/db.py` 增加策略1回测表和 CRUD。
- [ ] 运行 `python -m pytest tests/test_strategy1_backtest_db_api.py -q`。

### 任务 4：任务服务和 API

- [ ] 写失败测试：启动基线任务、启动实验任务、预览实验、详情、机会、信号、股票状态、对比。
- [ ] 实现 `scanner/strategy1_backtest_service.py` 和 `server.py` 端点。
- [ ] 运行 `python -m pytest tests/test_strategy1_backtest_db_api.py -q`。

### 任务 5：前端入口

- [ ] 写前端失败测试：实验开关、payload、EXPERIMENTAL 标识、对比结果、任务详情。
- [ ] 新增 `Strategy1Backtest.vue`，更新 `useApi.js`、路由和顶部导航。
- [ ] 运行 `npm --prefix web test -- --run`。

### 任务 6：验收与提交

- [ ] 运行策略1专项：`python -m pytest tests/test_backtester.py tests/test_cuphandle_strategy_engine.py tests/test_single_stock_backtest.py tests/test_strategy1_backtest_experiments.py tests/test_strategy1_backtester.py tests/test_strategy1_backtest_db_api.py -q`。
- [ ] 运行编译：`python -m compileall scanner strategy2 server.py -q`。
- [ ] 运行前端构建：`npm --prefix web run build`。
- [ ] 更新 `operations-log.md`。
- [ ] 审核中高风险问题，修复后提交。

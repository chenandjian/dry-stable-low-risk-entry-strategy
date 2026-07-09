# 策略6强势 VCP 尾部候选池实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 按 `strong-vcp-stock-selection-strategy.md` 新增独立策略6，完成扫描、候选持久化、API、前端结果页和配置入口。

**架构：** 策略6新增独立 `strategy6/` 包，单股判断入口为 `StrongVcpTailEngine.evaluate_at()`；扫描编排复用共享日线服务和 `scan_tasks/task_stocks`，候选写入独立 `strategy6_candidates` 表；前端新增策略6结果页和配置项。

**技术栈：** Python dataclass + SQLite 兼容迁移 + FastAPI + Vue 3 + Vitest + pytest。

---

## 文件结构

- 创建：`strategy6/__init__.py`，导出策略6类型和引擎。
- 创建：`strategy6/models.py`，定义指标、启动、支撑、尾部、交易计划、评分、评估结果。
- 创建：`strategy6/validation.py`，定义默认配置和校验。
- 创建：`strategy6/indicators.py`，归一化日线并计算基础指标。
- 创建：`strategy6/limit_up.py`，实现主板/创业板/科创板涨停和一字板判断。
- 创建：`strategy6/strong_start.py`，识别启动类型、启动等级和新高确认。
- 创建：`strategy6/support.py`，计算支撑状态、关键支撑、支撑区间和支撑测试。
- 创建：`strategy6/dry_tail.py`，判断尾部价稳量干和放量下跌。
- 创建：`strategy6/pressure.py`，识别上方压力和长上影风险。
- 创建：`strategy6/trade_plan.py`，计算买入区、止损、目标和盈亏比。
- 创建：`strategy6/scorer.py`，计算五段评分。
- 创建：`strategy6/filters.py`，执行硬过滤、候选分层和生命周期状态。
- 创建：`strategy6/engine.py`，串联全部模块。
- 创建：`strategy6/scanner.py`，全市场扫描编排。
- 修改：`scanner/db.py`，新增 `strategy6_candidates` 表、upsert/get/detail、JSON反序列化。
- 修改：`server.py`，新增策略6 API、运行状态、任务恢复发现映射、跨策略校验。
- 修改：`config.yaml`，新增 `strategy6` 默认配置。
- 修改：`web/src/composables/useApi.js`，新增策略6 API helper。
- 修改：`web/src/components/TopNav.vue`、`web/src/components/ScanEngine.vue`、`web/src/pages/ScannerConsole.vue`、`web/src/pages/TaskCenter.vue`、`web/src/router/index.js`、`web/src/pages/StrategyConfig.vue`。
- 创建：`web/src/pages/Strategy6Results.vue`。
- 创建：`tests/test_strategy6_limit_up.py`、`tests/test_strategy6_core_rules.py`、`tests/test_strategy6_db_api.py`、`tests/test_strategy6_scanner.py`。
- 创建：`web/src/pages/__tests__/Strategy6Results.test.js`。

## 任务 1：核心模型与涨停判断

- [ ] 编写 `tests/test_strategy6_limit_up.py`，覆盖主板10%、创业板/科创板20%、一字板、触板未封。
- [ ] 运行 `python -m pytest tests/test_strategy6_limit_up.py -q`，预期导入失败。
- [ ] 创建 `strategy6/limit_up.py` 和基础 `strategy6/__init__.py`。
- [ ] 运行测试，预期通过。
- [ ] Commit：`feat: add strategy6 limit up rules`。

## 任务 2：单股核心评估

- [ ] 编写 `tests/test_strategy6_core_rules.py`，用构造日线验证强启动、支撑、尾部价稳量干、交易计划、RR2过滤、放量下跌排除。
- [ ] 运行该测试，预期导入失败或字段缺失。
- [ ] 创建 `models/validation/indicators/strong_start/support/dry_tail/pressure/trade_plan/scorer/filters/engine`。
- [ ] 运行 `python -m pytest tests/test_strategy6_core_rules.py -q`，预期通过。
- [ ] Commit：`feat: add strategy6 evaluation engine`。

## 任务 3：数据库与 API

- [ ] 编写 `tests/test_strategy6_db_api.py`，验证独立候选表、跨策略 mismatch、候选详情。
- [ ] 运行测试，预期缺少 DB/API。
- [ ] 修改 `scanner/db.py` 和 `server.py`。
- [ ] 运行 `python -m pytest tests/test_strategy6_db_api.py -q`，预期通过。
- [ ] Commit：`feat: add strategy6 persistence and api`。

## 任务 4：扫描编排

- [ ] 编写 `tests/test_strategy6_scanner.py`，验证全源失败标记 failed、成功候选写入 `strategy6_candidates`。
- [ ] 运行测试，预期缺少 scanner。
- [ ] 创建 `strategy6/scanner.py` 并接入 server 启动接口。
- [ ] 运行 `python -m pytest tests/test_strategy6_scanner.py -q`，预期通过。
- [ ] Commit：`feat: add strategy6 scanner`。

## 任务 5：前端入口和结果页

- [ ] 编写 `web/src/pages/__tests__/Strategy6Results.test.js`，验证候选表展示关键字段。
- [ ] 运行 `npm --prefix web test -- --run Strategy6Results`，预期失败。
- [ ] 修改前端 API helper、导航、扫描控制台、任务中心、配置页和新增结果页。
- [ ] 运行 `npm --prefix web test -- --run` 和 `npm --prefix web run build`，预期通过。
- [ ] Commit：`feat: add strategy6 frontend`。

## 任务 6：验收与回归

- [ ] 运行 `python -m pytest tests/test_strategy6_*.py -q`。
- [ ] 运行 `python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py --ignore=tests/test_yfinance_hist.py`。
- [ ] 运行 `python -m compileall strategy6 scanner server.py -q`。
- [ ] 运行 `npm --prefix web test -- --run`。
- [ ] 运行 `npm --prefix web run build`。
- [ ] 审核是否存在中高等级问题，修复后再跑验证。
- [ ] Commit/push。

## 自检

- 规格中的涨停、强启动、支撑、尾部量干、交易计划、评分、分层、DB/API/前端均有对应任务。
- 市场/板块真实过滤和跨日生命周期按设计列为二期，不在本计划伪实现。
- 所有策略6候选路径独立，不写入策略1-5候选表。


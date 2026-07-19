# 策略6稳定箱体尾部路径实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 在不改动策略6原有尾部价稳量干函数和扫描入口的前提下，新增稳定箱体路径与K线紧密排列质量确认，并补齐配置、持久化、报告、前端展示和测试。

**架构：** 保留 `strategy6/dry_tail.py::evaluate_dry_tail()` 作为原路径唯一实现；新增 `strategy6/box_tail.py` 计算箱体窗口和紧密排列。引擎分别保存原路径与箱体路径结果，通过 OR 决定尾部通过、通过 max 决定尾部分数；兼容旧调用时箱体路径默认为关闭/未命中。

**技术栈：** Python 3.10+、dataclasses、SQLite、FastAPI、Vue 3、Vitest、pytest。

---

### 任务1：锁定原路径兼容性

**文件：**
- 测试：`tests/test_strategy6_box_tail_integration.py`

- [x] 编写失败测试，固定关闭 `box_tail.enabled` 时原 `dry_tail`、评分、拒绝原因和候选分层不变。
- [x] 运行 `python -m pytest tests/test_strategy6_box_tail_integration.py -q`，确认因新配置/字段缺失而失败。
- [x] 后续每轮实现后重跑该测试，确保原路径兼容。

### 任务2：实现稳定箱体和紧密排列纯计算

**文件：**
- 创建：`strategy6/box_tail.py`
- 修改：`strategy6/models.py`
- 测试：`tests/test_strategy6_box_tail.py`
- 测试：`tests/test_strategy6_compact_kline.py`

- [x] 先写窗口枚举、边界、独立下沿测试、跌破、中枢、量缩、位置和评分失败测试。
- [x] 实现 `evaluate_box_tail()`、`count_independent_box_low_tests()`、`calculate_kline_overlap_ratio()` 等纯函数。
- [x] 先写实体、收盘集中、重叠、跳空、ATR和放量下跌失败测试。
- [x] 实现紧密排列判定与0-10独立评分；不得参与箱体硬通过条件。
- [x] 验证最佳窗口排序为质量分、时长、宽度、量缩比。

### 任务3：接入双路径与配置

**文件：**
- 修改：`strategy6/engine.py`
- 修改：`strategy6/scorer.py`
- 修改：`strategy6/filters.py`
- 修改：`strategy6/validation.py`
- 修改：`config.yaml`
- 测试：`tests/test_strategy6_box_tail_integration.py`
- 测试：`tests/test_scheduler_config_api.py`

- [x] 先写 ORIGINAL/BOX/BOTH/NONE 和 max 非累加测试。
- [x] 引擎继续原样调用 `evaluate_dry_tail()`，并行新增 `evaluate_box_tail()`。
- [x] 硬过滤仅在两条路径都失败时应用原尾部拒绝；其他原有硬过滤不变。
- [x] 评分按实际命中路径取值；`BOTH` 取较高分，失败箱体不得抬高原结果；候选阈值和RR规则不变。
- [x] 增加嵌套 `box_tail`/`compact_kline` 默认配置、范围及顺序校验。

### 任务4：补齐持久化、报告和前端

**文件：**
- 修改：`scanner/db.py`
- 修改：`strategy6/models.py`
- 修改：`strategy6/report.py`
- 修改：`web/src/pages/StrategyConfig.vue`
- 修改：`web/src/pages/Strategy6Results.vue`
- 测试：`tests/test_strategy6_db_api.py`
- 测试：`tests/test_strategy6_report.py`
- 测试：`web/src/pages/__tests__/StrategyConfig.scheduler.test.js`
- 测试：`web/src/pages/__tests__/Strategy6Results.test.js`

- [x] 先写候选字典、SQLite迁移/往返和报表列失败测试。
- [x] 使用兼容迁移新增所有箱体、双路径、紧密排列列；列表字段使用JSON序列化。
- [x] 报表展示 `box_tail.enabled`、窗口、状态、评分和紧密排列指标。
- [x] 先写前端配置保存和结果详情/导出失败测试，再补充控件和展示。

### 任务5：验证、审核和交付

**文件：**
- 修改：`AGENTS.md`
- 修改：`CLAUDE.md`
- 创建：`docs/reviews/2026-07-11-strategy6-box-tail-path-validation.md`

- [x] 运行策略6专项pytest和前端专项Vitest。
- [x] 运行后端全量回归、compileall、前端全量测试和生产构建。
- [x] 审核原路径差异、窗口未来数据、分数重复、SQLite兼容和配置关闭行为。
- [x] 修复全部中高问题并重新验证。
- [x] 记录真实验证结果和残余风险；提交与推送按项目交付流程执行。

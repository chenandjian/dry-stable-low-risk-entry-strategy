# 策略6历史正式候选VCP持续观察池实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将策略6 VCP板块收紧为同一VCP生命周期内曾经成为正式候选的持续观察池。

**架构：** 新增独立的历史资格评估模块，使用当前正式策略对本轮VCP起点以来的真实日线逐日 `as-of` 重放。扫描器只对当前VCP有效的股票调用该模块，并把资格证据保存到候选表；前端按结构资格和历史资格交集展示。

**技术栈：** Python 3、SQLite、Vue 3、Vitest、pytest。

---

## 文件结构

- 新增 `strategy6/vcp_history.py`：历史正式候选资格的逐日重放与短路判断。
- 修改 `strategy6/models.py`：增加历史资格证据字段和序列化。
- 修改 `strategy6/scanner.py`：在当前VCP有效后接入历史资格判断。
- 修改 `scanner/db.py`：兼容迁移、写入和读取新增证据字段。
- 修改 `strategy6/report.py`：持续观察记录必须同时满足结构与历史资格。
- 修改 `web/src/pages/Strategy6Results.vue`：过滤VCP板块并展示历史证据。
- 修改 `web/src/utils/strategy6Labels.js`：新增字段值的中文标签。
- 修改策略6后端、数据库和前端测试。

### 任务1：历史资格评估器

**文件：**
- 创建：`strategy6/vcp_history.py`
- 创建：`tests/test_strategy6_vcp_history.py`

- [x] 编写失败测试：本轮起点前的候选不能构成资格，本轮内候选可以构成资格，当前日候选可以构成资格，逐日评估不得看到未来行。
- [x] 运行 `python -m pytest tests/test_strategy6_vcp_history.py -q`，确认因模块缺失失败。
- [x] 实现 `evaluate_vcp_candidate_history(...)`，按日期倒序、关闭VCP观察器、命中后短路，返回日期、候选类型、分数和来源。
- [x] 重跑专项测试并确认通过。

### 任务2：模型、数据库和报告语义

**文件：**
- 修改：`strategy6/models.py`
- 修改：`scanner/db.py`
- 修改：`strategy6/report.py`
- 修改：`tests/test_strategy6_db_api.py`
- 修改：`tests/test_strategy6_report.py`

- [x] 编写失败测试：新增字段可完整往返；纯VCP有效但历史不合格的记录不能成为VCP持续观察记录。
- [x] 运行相关测试确认正确失败。
- [x] 增加兼容字段迁移、序列化和严格交集判断，旧库缺失字段时默认不具备历史资格。
- [x] 重跑数据库与报告测试确认通过。

### 任务3：扫描接入和性能边界

**文件：**
- 修改：`strategy6/scanner.py`
- 修改：`tests/test_strategy6_scanner.py`

- [x] 编写失败测试：仅当前VCP有效时调用历史重放；不合格记录不写入VCP观察行；合格记录保存历史证据；退出审计仍只针对上一轮真实持续观察记录。
- [x] 运行扫描专项测试确认失败。
- [x] 接入历史资格评估器，复用当前股票和指数数据，保持正式候选持久化流程不变。
- [x] 重跑扫描测试确认通过。

### 任务4：前端过滤和证据展示

**文件：**
- 修改：`web/src/pages/Strategy6Results.vue`
- 修改：`web/src/utils/strategy6Labels.js`
- 修改：`web/src/pages/__tests__/Strategy6Results.test.js`

- [x] 编写失败测试：只有 `vcp_observation_eligible && vcp_history_qualified` 才显示；历史日期、等级、分数和来源可见；正式候选区顺序不变。
- [x] 运行 `npm.cmd --prefix web test -- --run Strategy6Results` 确认失败。
- [x] 实现前端交集过滤和证据列，保留旧字段和导出兼容。
- [x] 重跑前端专项测试确认通过。

### 任务5：真实数据验收与回归

**文件：**
- 新增：`docs/reviews/2026-07-16-strategy6-historical-candidate-vcp-tracking-validation.md`

- [x] 使用本地真实个股和真实指数数据逐日验证 `002281`，预期33个池内交易日且最后一天为2026-06-30。
- [x] 验证 `300276` 本轮VCP起点后没有正式候选，因此当前不进入持续观察池。
- [x] 运行策略6专项测试、后端完整回归、编译检查、前端全量测试和构建。
- [x] 以审核专家角色检查未来数据、旧库迁移、并发性能、退出审计和策略1至策略5隔离；修复全部中高等级问题。
- [x] 只暂存本功能文件，提交并推送当前分支，不包含用户已有报告改动。

# TickFlow 免费与认证模式实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 增加默认免费的 TickFlow 人工访问模式，确保免费模式始终调用 `TickFlow.free()`，认证模式才使用保留的 API Key。

**架构：** `tickflow_data.client` 定义并校验访问模式，SDK 构造只根据显式模式分支。扫描准备、全量刷新和新鲜度检查在任务启动时传递模式；配置 API 补齐默认值并触发 scheduler 重载；Vue 页面提供人工单选且不根据 Key 状态推断模式。

**技术栈：** Python、FastAPI、TickFlow SDK、Vue 3、Vitest、pytest。

---

### 任务 1：客户端严格模式契约

**文件：**
- 修改：`tickflow_data/client.py`
- 测试：`tests/test_tickflow_client.py`

- [ ] 编写失败测试：默认/显式免费模式即使存在 Key 也只调用 `TickFlow.free()`；认证模式只调用 `TickFlow(api_key=...)`；非法模式报错。
- [ ] 运行 `python -m pytest tests/test_tickflow_client.py -q`，确认测试因缺少模式参数失败。
- [ ] 新增 `FREE_ACCESS_MODE`、`AUTHENTICATED_ACCESS_MODE`、`resolve_tickflow_access_mode()`，并让 `TickFlowBatchClient(access_mode=...)` 严格分支构造 SDK。
- [ ] 重跑客户端测试，确认全部通过且不存在自动降级。

### 任务 2：后端配置和调用链

**文件：**
- 修改：`scanner/data_acquisition.py`
- 修改：`tickflow_data/freshness.py`
- 修改：`tickflow_data/web_task.py`
- 修改：`server.py`
- 测试：`tests/test_data_acquisition.py`
- 测试：`tests/test_tickflow_freshness.py`
- 测试：`tests/test_tickflow_web_task.py`
- 测试：`tests/test_kline_history_api.py`
- 测试：`tests/test_scheduler_config_api.py`

- [ ] 编写失败测试：三条运行入口传递 `free`/`authenticated`；GET 旧配置补齐 `free`；PUT 接受两种模式、拒绝非法模式、保存后重载 scheduler 且保留 Key。
- [ ] 运行后端专项测试，确认当前实现没有模式参数或配置校验。
- [ ] 在所有客户端工厂调用中传递任务启动时解析的 `access_mode`；后台状态只记录非敏感模式，不记录 Key。
- [ ] 在配置 API 中补齐、校验和保存 `tickflow_access_mode`，模式或 Key 变化均重载 scheduler。
- [ ] 重跑后端专项测试并确认通过。

### 任务 3：前端人工选择

**文件：**
- 修改：`web/src/pages/StrategyConfig.vue`
- 测试：`web/src/pages/__tests__/StrategyConfig.scheduler.test.js`

- [ ] 编写失败测试：默认免费；免费模式隐藏 Key 并提交 `free`；认证模式显示 Key 并提交 `authenticated`；已配置状态不得自动切换模式。
- [ ] 运行 `npm.cmd --prefix web test -- --run StrategyConfig.scheduler`，确认测试失败。
- [ ] 增加模式单选和条件展示；保留现有 Key 脱敏、空白保留及替换逻辑。
- [ ] 重跑前端专项测试并确认通过。

### 任务 4：双角色闭环验收

- [ ] 运行 TickFlow 与配置专项测试。
- [ ] 运行 `python -m compileall scanner strategy2 strategy3 strategy4 strategy5 strategy6 tickflow_data server.py -q`。
- [ ] 运行后端完整测试，排除真实外部源测试。
- [ ] 运行 `npm.cmd --prefix web test -- --run` 和 `npm.cmd --prefix web run build`。
- [ ] 审核默认行为、模式漂移、自动降级、密钥泄漏和用户脏文件误提交；修复全部中高等级问题。
- [ ] 仅暂存本功能文件，提交并推送当前分支。

## 自检结果

- 规格中的默认免费、严格人工选择、保留 Key、无自动降级、四类入口一致性、脱敏和测试均有对应任务。
- `access_mode` 在客户端、扫描、全量任务和新鲜度检查中统一命名。
- 不修改 `config.yaml`，避免覆盖用户现有配置改动；旧配置由运行时补齐默认免费模式。

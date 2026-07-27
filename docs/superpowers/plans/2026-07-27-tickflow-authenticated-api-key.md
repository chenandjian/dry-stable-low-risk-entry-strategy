# TickFlow 认证密钥实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将 TickFlow 全部运行入口切换为显式 API Key 认证，并在策略配置页提供不会回显明文、空值保存保留旧密钥的配置能力。

**架构：** `tickflow_data.client` 统一负责密钥解析和 SDK 构造，扫描预取、全量刷新、数据新鲜度检查只传递任务启动时的密钥快照。`/api/config` 在合并配置前处理密钥更新语义，在返回前深拷贝并脱敏；Vue 配置页只维护空白密码输入与“已配置”状态，不保存后端明文。

**技术栈：** Python 3.10+、FastAPI、PyYAML、TickFlow Python SDK、Vue 3、Vitest。

---

## 文件结构

- 修改 `tickflow_data/client.py`：默认密钥、优先级解析、认证 SDK 构造。
- 修改 `scanner/data_acquisition.py`：扫描批量预取传递配置密钥。
- 修改 `tickflow_data/web_task.py`：全量刷新在启动时捕获密钥，后台线程只使用内存参数。
- 修改 `tickflow_data/freshness.py`：只读新鲜度探测传递配置密钥。
- 修改 `server.py`：配置读写脱敏与三条 TickFlow 调用链注入。
- 修改 `web/src/pages/StrategyConfig.vue`：密码输入、显示切换、已配置状态和空值保留。
- 修改后端及前端相关测试：覆盖密钥优先级、无免费模式、脱敏、保留/替换、调用链和 UI 请求体。

### 任务 1：认证客户端契约

- [ ] 在 `tests/test_tickflow_client.py` 增加失败测试：显式参数优先于环境变量、环境变量优先于默认值、空白值回落默认值、SDK 始终收到 `api_key` 且不调用 `TickFlow.free()`。
- [ ] 运行 `python -m pytest tests/test_tickflow_client.py -q`，确认新测试因缺少认证解析失败。
- [ ] 在 `tickflow_data/client.py` 实现 `DEFAULT_TICKFLOW_API_KEY`、`resolve_tickflow_api_key()` 和 `TickFlowBatchClient(api_key=...)`，只接受可转为非空认证结果的字符串，不校验前缀。
- [ ] 重跑客户端测试并确认通过。

### 任务 2：后端配置安全语义

- [ ] 在 `tests/test_scheduler_config_api.py` 增加失败测试：GET 不泄漏密钥并返回 `tickflow_api_key_configured`；PUT 缺失或空白密钥保留旧值；非空值替换并去空格；非字符串返回 400 且文件不变。
- [ ] 运行对应测试，确认当前接口会泄漏或覆盖密钥。
- [ ] 在 `server.py` 增加仅作用于请求副本的密钥预处理和响应深拷贝脱敏；派生状态不得写入 YAML。
- [ ] 重跑配置 API 测试并确认通过。

### 任务 3：全部 TickFlow 入口使用认证

- [ ] 在 `tests/test_data_acquisition.py`、`tests/test_tickflow_freshness.py`、`tests/test_kline_history_api.py` 和相关 Web 任务测试中增加失败断言，验证扫描、全量刷新、新鲜度检查均把同一配置密钥传给客户端工厂。
- [ ] 运行新增测试，确认调用参数尚未传递。
- [ ] 修改 `scanner/data_acquisition.py`、`tickflow_data/web_task.py`、`tickflow_data/freshness.py`、`server.py`：任务启动时解析密钥并传入客户端；任务状态、进度 JSON、Markdown 报告和异常文本不得包含密钥。
- [ ] 重跑专项测试并检查序列化状态中不存在 `api_key` 或实际密钥。

### 任务 4：前端密码配置

- [ ] 在 `web/src/pages/__tests__/StrategyConfig.scheduler.test.js` 增加失败测试：密码输入默认空白、显示已配置状态、显示/隐藏切换、空白保存不提交字段、非空保存提交去空格后的密钥且成功后清空输入。
- [ ] 运行 `npm.cmd --prefix web test -- --run StrategyConfig.scheduler`，确认测试失败。
- [ ] 修改 `web/src/pages/StrategyConfig.vue`：在数据获取模式区域加入密码控件；保存时移除派生状态，空白密钥从请求体省略；成功后只更新已配置状态，不保留明文。
- [ ] 重跑前端专项测试并确认通过。

### 任务 5：闭环验收

- [ ] 运行后端专项测试：`python -m pytest tests/test_tickflow_client.py tests/test_tickflow_freshness.py tests/test_data_acquisition.py tests/test_kline_history_api.py tests/test_scheduler_config_api.py -q`。
- [ ] 运行编译检查：`python -m compileall scanner strategy6 tickflow_data server.py -q`。
- [ ] 运行前端完整测试和构建：`npm.cmd --prefix web test -- --run`、`npm.cmd --prefix web run build`。
- [ ] 以审核专家角色检查：明文泄漏、空值误覆盖、后台任务读取漂移、调度器旧配置、legacy 模式回归和用户脏文件误提交。
- [ ] 修复所有中高等级发现并重复验证，随后仅暂存本计划涉及文件，提交并推送当前分支。

## 自检结果

- 规格覆盖：默认密钥、无前缀校验、三条调用链、GET 脱敏、PUT 保留/替换、前端密码控件、调度重载、安全日志均有对应任务。
- 类型一致：统一使用 `api_key: str | None`，客户端工厂继续通过关键字参数构造，便于测试替身兼容。
- 边界确认：不修改 `config.yaml` 的用户现有改动；默认值由运行时代码提供，用户首次保存新值后才写入配置文件。

# TickFlow 认证 Key 配置设计

> **版本说明：** 本文的“统一认证模式”结论已被 `2026-07-27-tickflow-free-auth-mode-design.md` 取代。当前规则是人工选择 `free` 或 `authenticated`，默认严格使用 `TickFlow.free()`。

## 1. 目标

将 TickFlow 从“环境变量存在则认证、否则自动免费模式”升级为统一认证模式，并允许用户在前端策略配置页维护 API Key。

本次覆盖：

- 策略扫描前 TickFlow 批量行情准备
- TickFlow 全市场重新拉取
- TickFlow 个股与四个指数的新鲜度测试
- TickFlow CLI 的默认认证行为
- 后端配置读取、保存与脱敏
- 前端策略配置页

不修改传统多数据源模式、TickFlow 批量参数、前复权口径、入库逻辑和策略1至策略6判断规则。

## 2. 配置模型

新增配置：

```yaml
data:
  tickflow_api_key: <完整认证Key>
```

Key解析优先级：

1. 调用方显式传入的 `api_key`
2. 环境变量 `TICKFLOW_API_KEY`
3. 用户指定的项目默认 Key

Key仅做以下校验：

- 类型必须为字符串
- 去除首尾空格后不能为空

不校验固定前缀，避免上游认证格式变化导致客户端误拒绝。

## 3. TickFlow 客户端

`TickFlowBatchClient` 新增可选 `api_key` 构造参数。创建 SDK 时统一执行：

```python
TickFlow(api_key=resolved_api_key)
```

禁止继续调用 `TickFlow.free()`。没有可用 Key 时抛出不包含 Key 内容的 `TickFlowClientError`。

客户端错误、重试日志和任务状态只能说明认证缺失或认证失败，不得拼接、记录或返回 API Key。

## 4. 调用链传递

### 4.1 扫描前批量准备

`prepare_scan_daily_data()` 从当前配置解析 Key，在创建 `TickFlowBatchClient` 时显式传入。测试注入的 `client_factory` 必须继续兼容并能验证收到的 Key。

### 4.2 全市场重拉

启动 `/api/tickflow/full-refresh` 时读取配置并解析 Key，将 Key 作为任务启动快照传给 `TickFlowFullRefreshManager`。后台线程使用启动时快照，不在运行中重新读取配置，避免任务前后批次使用不同认证身份。

任务状态、进度JSON和Markdown报告不得持久化 Key。

### 4.3 新鲜度测试

`/api/tickflow/freshness-check` 使用当前配置解析 Key并传给 `check_tickflow_freshness()`。返回结构保持兼容，错误字段不得包含 Key。

### 4.4 CLI

CLI保持现有命令参数兼容。未显式注入客户端时，由 `TickFlowBatchClient` 按“环境变量 > 项目默认值”认证，不增加可能出现在进程列表中的明文命令行参数。

## 5. 配置 API 安全语义

### 5.1 GET `/api/config`

禁止返回真实 `data.tickflow_api_key`。响应中的 `data` 使用：

```json
{
  "tickflow_api_key": "",
  "tickflow_api_key_configured": true
}
```

`tickflow_api_key_configured` 表示当前配置、环境变量或项目默认值中至少有一个可用认证Key。

脱敏必须在复制后的响应对象上执行，不得修改内存中的原配置。

### 5.2 PUT `/api/config`

- 请求未包含 `tickflow_api_key`：保留现值。
- 请求包含空字符串或纯空白：保留现值。
- 请求包含非空字符串：去除首尾空格后替换并持久化。
- 请求包含非字符串非空值：HTTP 400，且不得写配置文件。
- `tickflow_api_key_configured` 是只读派生字段，后端保存前必须移除。

保存新 Key 后必须立即重载 scheduler，因为定时任务会持有注册时的配置对象。下一次定时扫描使用新 Key；已经运行的全量任务继续使用启动快照。

## 6. 前端设计

在策略配置页“日线数据获取模式”下增加：

- `TickFlow API Key` 密码输入框
- 显示/隐藏按钮
- “已配置”或“未配置”状态提示

页面加载时输入框始终为空，不展示后端真实值。保存规则：

- 未输入新值：payload中省略 `tickflow_api_key`，保留后端配置。
- 输入新值：发送去除首尾空格后的新值。
- 保存成功：立即清空输入框，并把状态更新为“已配置”。

重置页面配置时同样不得取得或展示真实 Key。

## 7. 默认值与兼容性

- 旧配置没有 `data.tickflow_api_key` 时，运行时使用用户指定默认 Key。
- 传统多数据源模式不要求 TickFlow Key，也不创建 TickFlow 客户端。
- 现有环境变量继续支持，便于CLI和部署环境覆盖项目默认值。
- 已注入 fake SDK 的单元测试不要求真实 Key，也不得发起网络请求。

## 8. 测试要求

### 后端单元测试

1. 客户端使用显式 Key构造 `TickFlow(api_key=...)`。
2. 显式 Key优先于环境变量，环境变量优先于项目默认值。
3. 不存在任何 `TickFlow.free()` 调用路径。
4. Key缺失/非法时错误不泄漏原值。
5. 扫描准备、全量重拉、新鲜度测试均传递正确 Key。
6. 全量任务状态和进度数据不包含 Key。

### 配置 API 测试

1. GET不返回完整 Key，只返回配置状态。
2. PUT空值保留原 Key。
3. PUT新值替换并去除首尾空格。
4. PUT非字符串值返回400且不写文件。
5. 只读状态字段不进入 `config.yaml`。

### 前端测试

1. 配置页显示密码框和已配置状态。
2. 加载后密码框为空。
3. 未输入Key时保存payload不包含Key。
4. 输入新Key时正确提交，且不要求固定前缀。
5. 保存成功后清空输入框并显示已配置。
6. 显示/隐藏按钮只改变输入类型，不修改值。

## 9. 验收标准

1. 三条Web运行路径和CLI均使用认证SDK。
2. 代码中不存在运行时免费模式回退。
3. 前端可以安全替换Key，但无法读取原Key。
4. API响应、日志、状态、进度和报告均不泄漏Key。
5. TickFlow与传统多源模式切换行为保持不变。
6. 后端专项测试、完整策略相关回归、前端测试与构建通过。

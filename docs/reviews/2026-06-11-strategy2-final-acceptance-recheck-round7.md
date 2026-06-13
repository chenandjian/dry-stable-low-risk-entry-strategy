# 代码问题检查报告

## 1. 检查范围

- 审核分支：`codex/strategy2-extreme-dry-stable-design`
- 审核提交：`fc00da2 fix(strategy2): round6 — completed task summary, unified error handling, vitest 11 tests`
- 对比基线：`7b95046`
- 重点检查：
  - Round6 问题是否真实修复
  - 已完成历史任务首次加载 summary
  - 历史运行任务完成后的最终刷新
  - Strategy1 / Strategy2 历史任务 URL 切换隔离
  - 非 404、网络异常和状态查询异常
  - 前端测试是否能真实阻止回归
  - Strategy2 算法、三数据源和全源失败规则是否回归

---

## 2. 总体结论

`fc00da2` 已正确修复上一轮三个问题：

- 已完成历史任务首次打开时会通过 `refreshTaskContext()` 应用持久化 summary。
- 404、非 404 和 `getTaskStocks()` 网络异常已使用不同错误提示。
- 已增加历史任务 A→B、运行→完成和加载错误测试。

Strategy2 指标、评分、否决规则、风险计算和三数据源直接失败规则本轮未修改；后端重点测试、后端全量测试、前端测试和构建均通过。

但本轮仍不能最终验收通过。当前剩余一个真实跨策略串线风险：历史任务 URL 连续快速切换时，旧请求的慢响应可以覆盖新任务页面。现有测试全部使用顺序完成的请求，无法发现该竞态。

此外，Round6 新增的 summary 测试断言仍然过弱：测试名称声称验证 summary，但只断言失败面板或请求次数。删除 `applyTaskSummary()` 后，这些测试仍可能通过。

---

## 3. 问题清单

| 编号 | 问题 | 严重程度 | 影响范围 | 是否必须修复 |
| --- | --- | --- | --- | --- |
| ROUND7-S2-001 | 历史任务快速切换时旧异步响应可覆盖新任务，造成跨策略上下文串线 | 高 | Strategy1 / Strategy2 历史任务、候选、失败列表、summary | 是 |
| ROUND7-S2-002 | 历史任务状态查询异常未统一处理，首次打开可能产生未处理 Promise rejection | 中 | 历史任务首次加载、运行态识别、错误展示 | 是 |
| ROUND7-S2-003 | Round6 新增 summary 测试断言过弱，不能真实保护修复 | 中 | 前端回归可信度 | 是 |

---

## 4. 详细问题分析

### ROUND7-S2-001：历史任务快速切换时旧异步响应可覆盖新任务

#### 问题现象

用户快速切换历史任务，例如：

```text
Strategy1 任务 A → Strategy2 任务 B
```

如果 A 的接口响应较慢、B 的接口响应较快，页面可能先正确显示 B，随后被 A 的迟到响应覆盖。

最终可能出现：

- URL 是任务 B，但 `scanProgress.taskId` 变成任务 A。
- URL 是 Strategy2 任务，但显示 Strategy1 候选和“重新拉取”按钮。
- URL 是 Strategy1 任务，但显示 Strategy2 候选。
- summary、失败列表和候选来自不同任务。

#### 涉及模块

- `web/src/pages/ScannerConsole.vue:306`
- `web/src/pages/ScannerConsole.vue:315`
- `web/src/pages/ScannerConsole.vue:320`
- `web/src/pages/ScannerConsole.vue:351`
- `web/src/pages/ScannerConsole.vue:597`

#### 证据链

URL watcher 每次变化都会独立启动一个异步切换：

```js
watch(
  () => route.query.task,
  async (newTask, oldTask) => {
    await switchTaskContext(id || null)
  },
)
```

`switchTaskContext()` 和 `refreshTaskContext()` 没有请求版本号、取消信号或当前 route 校验：

```js
const data = await getTaskStocks(taskId, ...)
scanProgress.taskId = taskId
activeStrategyType.value = data.strategy_type
failures.value = data.stocks || []
applyTaskSummary(data.summary)
await loadResults()
```

因此，任何已经发出的旧请求在返回后都会无条件修改共享页面状态。`stopPolling()` 只能停止定时器，不能取消已经在途的 `getTaskStocks()`、`getScanStatus()` 或候选请求。

现有 A→B 测试等待 A 完成后才切换 B，只覆盖顺序路径，没有构造 A 慢、B 快的响应顺序。

#### 触发条件

1. 用户连续点击两个历史任务，或浏览器前进/后退快速改变 `?task=`。
2. 第一个任务请求比第二个任务请求更慢。
3. 两个任务属于不同策略时，影响最明显。

#### 影响

这是数据展示正确性问题，不只是短暂闪烁。用户可能基于错误任务的候选、失败原因和统计作出判断，并可能对错误的 Strategy1 任务点击“重新拉取”。

#### 修复建议

使用单调递增的上下文版本号，确保只有最新切换可以提交状态。不要仅在函数开始时检查 route，必须在每个 `await` 后、写入共享状态前检查。

建议实现：

```js
let taskContextVersion = 0

function isCurrentTaskContext(taskId, version) {
  return version === taskContextVersion
    && String(route.query.task || '') === String(taskId || '')
}

async function switchTaskContext(newTaskId) {
  const version = ++taskContextVersion
  stopPolling()
  resetTaskView()
  scanError.value = ''

  if (!newTaskId) {
    await loadLiveTask(version)
    return
  }

  const ok = await refreshTaskContext(newTaskId, version)
  if (!ok || !isCurrentTaskContext(newTaskId, version)) return

  try {
    const status = await getScanStatus()
    if (!isCurrentTaskContext(newTaskId, version)) return
    if (status.running && status.task_id === newTaskId) {
      applyStats(status, { applyTaskId: false })
      scanning.value = true
      pollTimer = setInterval(pollStatus, 1000)
    }
  } catch (e) {
    if (isCurrentTaskContext(newTaskId, version)) {
      scanError.value = '任务状态查询失败'
    }
  }
}
```

`refreshTaskContext()` 必须先把响应保存在局部变量中，确认版本仍有效后再一次性提交：

```js
async function refreshTaskContext(taskId, version = taskContextVersion) {
  try {
    const data = await getTaskStocks(taskId, { status: 'failed', page_size: 50, page: 1 })
    if (!isCurrentTaskContext(taskId, version)) return false

    if (!data.ok) {
      scanError.value = data.error === 'TASK_NOT_FOUND'
        ? `任务不存在：${taskId}`
        : '历史任务加载失败'
      return false
    }

    scanProgress.taskId = taskId
    activeStrategyType.value = data.strategy_type
    failures.value = data.stocks || []
    failuresTotal.value = data.total || 0
    applyTaskSummary(data.summary)

    await loadResults(taskId, data.strategy_type, version)
    return isCurrentTaskContext(taskId, version)
  } catch (e) {
    if (isCurrentTaskContext(taskId, version)) {
      scanError.value = '历史任务加载失败'
    }
    return false
  }
}
```

推荐同时让 `loadResults()` 接收明确的 `taskId`、`strategyType` 和 `version`，禁止它在异步过程中依赖可能已变化的全局 `scanProgress.taskId` 与 `activeStrategyType`。

不要通过禁用 URL 切换或增加固定延迟规避问题。

#### 验证方式

新增组件竞态测试：

1. 使用两个可手动 resolve 的 Promise。
2. 打开任务 A，保持 A 的 `getTaskStocks()` pending。
3. 切换到任务 B，让 B 立即返回 Strategy2 summary、失败列表和候选。
4. 确认页面显示 B。
5. 再 resolve A。
6. 断言页面仍只显示 B，`A-fail`、A 候选和 Strategy1 重试按钮均不能出现。
7. 再增加 B 慢、切换到无 task 的 live 模式场景，旧 B 响应不得覆盖 live 模式。

---

### ROUND7-S2-002：历史任务状态查询异常未统一处理

#### 问题现象

首次直接打开历史任务时：

```js
await refreshTaskContext(taskId)
const status = await getScanStatus()
```

如果任务详情成功，但 `/api/scan/status` 网络失败或返回无法解析的数据，`loadHistoricalTask()` 没有 `try/catch`。`onMounted()` 会收到未处理 rejection，页面没有明确状态查询错误提示，后续初始化也可能被中断。

#### 涉及模块

- `web/src/pages/ScannerConsole.vue:554`
- `web/src/pages/ScannerConsole.vue:559`
- `web/src/pages/ScannerConsole.vue:582`

#### 触发条件

- 历史任务详情接口可用，但状态接口短暂失败。
- 后端重启过程中直接打开历史任务链接。
- 状态接口响应不是合法 JSON。

#### 影响

- 已加载的历史数据与运行状态无法明确区分。
- 页面没有告诉用户状态查询失败。
- `onMounted()` 后续的时钟初始化可能不执行。

#### 修复建议

将历史状态查询放入 `try/catch`，并与 ROUND7-S2-001 的上下文版本校验一起实现：

```js
async function loadHistoricalTask(taskId) {
  const version = ++taskContextVersion
  const ok = await refreshTaskContext(taskId, version)
  if (!ok || !isCurrentTaskContext(taskId, version)) return false

  try {
    const status = await getScanStatus()
    if (!isCurrentTaskContext(taskId, version)) return false
    if (status.running && status.task_id === taskId) {
      applyStats(status, { applyTaskId: false })
      scanning.value = true
      pollTimer = setInterval(pollStatus, 1000)
    }
  } catch (e) {
    if (isCurrentTaskContext(taskId, version)) {
      scanError.value = '任务状态查询失败，已显示最近保存结果'
    }
  }
  return true
}
```

状态查询失败时应保留已经成功加载的历史 summary、候选和失败列表，不要清空它们。

#### 验证方式

- `getTaskStocks()` 成功，`getScanStatus()` reject。
- 页面保留该历史任务的候选、summary 和失败列表。
- 页面显示“任务状态查询失败，已显示最近保存结果”。
- 不产生未处理 Promise rejection。

---

### ROUND7-S2-003：新增 summary 测试断言过弱

#### 问题现象

测试：

```text
completed historical task applies persisted summary on initial load
```

只断言：

```js
expect(wrapper.text()).toContain('失败股票')
```

失败面板由 `failuresTotal = data.total` 驱动，与 `applyTaskSummary(data.summary)` 无关。即使删除 `applyTaskSummary()`，该测试仍可能通过。

测试：

```text
historical running task refreshes final summary after completion
```

只断言 `getTaskStocks()` 调用至少两次，没有断言最终 `processed=100`、候选数、失败数或最新交易日已显示。

#### 涉及模块

- `web/src/pages/__tests__/ScannerConsole.history-task.test.js:116`
- `web/src/pages/__tests__/ScannerConsole.history-task.test.js:129`
- `web/src/pages/__tests__/ScannerConsole.history-task.test.js:135`
- `web/src/pages/__tests__/ScannerConsole.history-task.test.js:164`

#### 影响

Round6 的核心修复未来被删除或破坏时，测试仍可能全部通过，造成错误的最终验收结论。

#### 修复建议

让测试断言用户真正看到的 summary。推荐为 `ScanEngine` 增加轻量测试 stub，直接暴露 props：

```js
const ScanEngineStub = {
  props: ['scanned', 'total', 'skipped', 'failed', 'candidates', 'latestTradeDate', 'stockPoolSource'],
  template: `
    <div data-test="scan-summary">
      {{ scanned }}/{{ total }} skipped={{ skipped }} failed={{ failed }}
      candidates={{ candidates }} latest={{ latestTradeDate }} source={{ stockPoolSource }}
    </div>
  `,
}
```

挂载时注册该 stub，然后精确断言：

```js
expect(wrapper.get('[data-test="scan-summary"]').text()).toContain('100/100')
expect(wrapper.get('[data-test="scan-summary"]').text()).toContain('failed=2')
expect(wrapper.get('[data-test="scan-summary"]').text()).toContain('candidates=3')
expect(wrapper.get('[data-test="scan-summary"]').text()).toContain('latest=2026-06-10')
expect(wrapper.get('[data-test="scan-summary"]').text()).toContain('source=akshare')
```

运行→完成测试必须断言初始 `80/100` 变为最终 `100/100`，并断言最终候选、失败和最新交易日，而不只是请求次数。

同时增加 ROUND7-S2-001 的延迟响应竞态测试。

---

## 5. 已确认修复完成

- 已完成历史任务首次打开会应用持久化 summary。
- `refreshTaskContext()` 已区分任务不存在、后端错误和网络异常。
- 首次历史加载和 query 切换已复用主要任务上下文加载逻辑。
- 历史运行任务完成后会再次读取目标任务最终 summary。
- 有效任务 A→B 的顺序切换会清理 A 并显示 B。
- Strategy2 历史任务不显示 Strategy1 重试按钮。
- Strategy2 全部在线数据源失败时直接标记失败，不使用缓存。
- Strategy2 生产数据源仍为 `baidu`、`sina`、`tencent`。
- Strategy2 算法代码本轮未修改，重点算法测试和全量回归通过。

---

## 6. 建议修复顺序

1. 为历史任务上下文增加单调递增版本号或等价的 stale-response 防护。
2. 修改 `refreshTaskContext()`，只允许当前版本提交 summary、失败列表、策略类型和候选。
3. 修改 `loadResults()`，显式接收 taskId、strategyType 和版本，避免读取变化中的全局状态。
4. 为 `loadHistoricalTask()` 的状态查询增加异常处理。
5. 增加 A 慢、B 快的跨策略竞态测试。
6. 增加历史任务切回 live 模式时旧响应不得覆盖的测试。
7. 将 summary 测试改为精确断言 ScanEngine props。
8. 执行完整验收门禁。

---

## 7. 给修复 AI 的执行要求

请严格按以下要求修复：

1. 只修改历史任务上下文切换、状态查询错误处理和对应前端测试。
2. 不修改 Strategy2 指标、评分、否决规则、风险计算、候选门槛和窗口规则。
3. 不修改 Strategy1 策略算法。
4. 不修改数据库结构或后端任务 API 字段。
5. 不恢复缓存兜底、mootdx 或 yfinance；生产数据源保持 `baidu`、`sina`、`tencent`。
6. 不使用固定延迟、防抖或禁用导航掩盖竞态；必须阻止 stale response 提交共享状态。
7. 每个异步任务上下文请求在写入页面状态前必须验证自己仍是最新上下文。
8. 状态查询失败时保留已经成功加载的历史结果，并显示明确提示。
9. 测试必须使用可控 Promise 构造乱序响应，不能只测试顺序切换。
10. summary 测试必须精确断言 processed、total、failed、candidates、latestTradeDate 和 stockPoolSource。
11. 不重构无关页面、组件和 API。

---

## 8. 回归测试清单

- 直接打开已完成 Strategy1 历史任务，summary 正确。
- 直接打开已完成 Strategy2 历史任务，summary 正确。
- 历史运行任务完成后最终 summary、候选和失败列表正确。
- 顺序切换 Strategy1 A→Strategy2 B 后只显示 B。
- A 请求慢、B 请求快时，A 的迟到响应不能覆盖 B。
- Strategy2 B 请求慢、切回 live 模式后，B 的迟到响应不能覆盖 live。
- 切换到不存在任务后旧状态清空并显示任务不存在。
- 非 404 错误显示历史任务加载失败。
- 任务详情成功但状态查询失败时保留历史数据并显示状态查询提示。
- 历史 Strategy2 不显示 Strategy1 重试按钮。
- Strategy2 三源全部失败直接标记失败，不使用缓存。
- Strategy2 指标、评分、否决规则和风险计算测试全部通过。

---

## 9. 不建议修改的内容

- 不修改 Strategy2 算法。
- 不修改 Strategy1 算法。
- 不修改三数据源顺序。
- 不修改候选表和任务表结构。
- 不调整前端整体 UI 风格。
- 不修改已通过的失败诊断持久化逻辑。
- 不修改后端任务隔离接口。

---

## 10. 最终交付标准

1. 任意顺序和速度的历史任务 URL 切换都不会出现旧响应覆盖新任务。
2. Strategy1 与 Strategy2 的候选、失败列表、summary 和操作按钮不会串线。
3. 历史任务状态查询异常有明确提示，且不清空已加载结果。
4. 测试真实构造异步乱序响应并阻止竞态回归。
5. summary 测试精确验证用户看到的最终统计。
6. Strategy2 算法和三源直接失败规则不发生回归。
7. 全部验收命令通过。

---

## 11. 本轮验证结果

```text
Strategy2 重点后端验收：
176 passed

后端全量：
426 passed

前端 Vitest：
1 file / 11 tests passed

前端 build：
通过

compileall：
通过

git diff --check：
通过

工作树：
干净
```

测试全部通过不代表本轮可以最终验收，因为 ROUND7-S2-001 是现有异步控制流可直接确认的竞态，当前测试没有构造乱序响应；ROUND7-S2-003 说明现有 summary 测试无法真实保护 Round6 核心修复。

---

## 12. 可直接发送给修复 AI 的指令

请修复文档：

`docs/reviews/2026-06-11-strategy2-final-acceptance-recheck-round7.md`

目标是一次性修复 `ROUND7-S2-001` 至 `ROUND7-S2-003`。

执行要求：

1. 先阅读完整审核文档和 `web/src/pages/ScannerConsole.vue`，确认异步历史任务上下文切换链路。
2. 使用上下文版本号、请求令牌或等价机制，保证旧任务的迟到响应不能修改当前页面状态。
3. `getTaskStocks()`、候选加载和 `getScanStatus()` 每次 `await` 后都必须验证上下文仍有效。
4. `loadResults()` 不得在异步请求期间依赖可能变化的全局 taskId/strategyType。
5. 状态查询失败时保留已加载历史结果并显示明确错误。
6. 使用可控 Promise 新增 A 慢 B 快、B 慢切回 live 的竞态测试。
7. 使用 ScanEngine stub 精确断言 summary，不允许只断言失败面板或请求次数。
8. 不修改任何策略算法、数据库结构、后端 API 契约或数据源规则。
9. 修复完成后执行：

```bash
python -m pytest tests/test_strategy2_acceptance_fixes.py tests/test_strategy2_final_fixes.py tests/test_strategy2_bug_fixes.py tests/test_strategy2_engine.py tests/test_strategy2_indicators.py tests/test_strategy2_scorer.py tests/test_strategy2_rejection.py tests/test_strategy2_risk.py -q
python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py
cd web && npm.cmd test -- --run
cd web && npm.cmd run build
python -m compileall strategy2 scanner server.py -q
git diff --check
```

10. 交付时说明每个问题修改了哪些函数、增加了哪些测试，并提供全部命令结果。

---

## 13. 最终一次性修复实施方案

本节是给修复 AI 的主执行方案。前面的章节用于解释问题，本节规定具体怎么改。请优先按本节实施，不要重新设计另一套并发控制方案。

### 13.1 本次允许修改的文件

必须修改：

- `web/src/pages/ScannerConsole.vue`
- `web/src/pages/__tests__/ScannerConsole.history-task.test.js`

原则上不需要修改：

- `web/src/composables/useApi.js`
- `server.py`
- `scanner/`
- `strategy2/`
- 数据库结构
- 配置文件

如果修复 AI 判断必须修改允许范围之外的文件，应先说明现有方案为什么无法完成；不能直接扩大修改范围。

### 13.2 修复后的唯一并发规则

页面中存在两种视图上下文：

```text
历史任务上下文：route.query.task = 某个 task_id
实时任务上下文：route.query.task 为空
```

每次从一个上下文切换到另一个上下文时，只创建一个新的 `viewContext`：

```js
{
  epoch: 递增整数,
  taskId: 标准化后的任务 ID；实时模式为空字符串,
}
```

任何异步函数在修改以下共享状态前，都必须确认自己的 `viewContext` 仍然有效：

- `scanProgress`
- `activeStrategyType`
- `discoveries`
- `failures`
- `failuresTotal`
- `scanError`
- `scanning`
- `pollTimer`
- `logLines`

失效请求可以自然完成，但不能再修改页面状态、启动轮询、停止新轮询或添加日志。

### 13.3 第一步：增加统一上下文令牌

在 `pollTimer`、`clockTimer`、`lastLogScanned` 附近增加：

```js
let viewContextEpoch = 0
let pollRequestEpoch = 0
let activeViewContext = { epoch: 0, taskId: '' }

function normalizeTaskId(taskId) {
  return String(taskId || '')
}

function beginViewContext(taskId) {
  viewContextEpoch += 1
  pollRequestEpoch += 1
  activeViewContext = {
    epoch: viewContextEpoch,
    taskId: normalizeTaskId(taskId),
  }
  return { ...activeViewContext }
}

function captureCurrentViewContext() {
  return { ...activeViewContext }
}

function isCurrentViewContext(context) {
  return Boolean(context)
    && context.epoch === activeViewContext.epoch
    && context.taskId === activeViewContext.taskId
    && context.taskId === normalizeTaskId(route.query.task)
}
```

关键要求：

1. `beginViewContext()` 只能由统一页面切换入口调用。
2. `refreshTaskContext()`、`loadHistoricalTask()` 和 `loadLiveTask()` 内部禁止再次递增 `viewContextEpoch`。
3. 同一次页面切换的所有异步函数必须传递同一个 context。
4. `normalizeTaskId()` 必须统一处理 `undefined`、`null` 和空字符串。
5. `captureCurrentViewContext()` 必须复制 `activeViewContext`，不能用“旧 epoch + 新 route”临时拼接 context。

### 13.4 第二步：让停止轮询同时使在途轮询失效

将 `stopPolling()` 修改为：

```js
function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  pollRequestEpoch += 1
  scanning.value = false
}
```

为什么必须递增 `pollRequestEpoch`：

- `clearInterval()` 只能阻止下一次调用。
- 已经执行到 `await getScanStatus()` 的旧轮询不会被取消。
- 如果不使其失效，它返回后仍可能覆盖新任务状态，甚至调用 `stopPolling()` 清除新任务的轮询 timer。

### 13.5 第三步：拆分候选“获取”和“提交”

当前 `loadResults()` 在异步请求完成后直接写 `discoveries`，并依赖可能已变化的全局 `scanProgress.taskId` 和 `activeStrategyType`。必须改为显式参数。

建议新增纯获取函数：

```js
async function fetchMappedResults(taskId, strategyType) {
  const isS2 = strategyType === 'STRATEGY_2_EXTREME_DRY_STABLE'

  if (isS2) {
    const res = await getStrategy2Candidates(taskId)
    return (res.candidates || []).map(c => ({
      code: c.code,
      name: c.name,
      score: c.total_score || 0,
      rating: c.level || '',
      status: c.level || '',
      detail: `量干${c.volume_dry_score || 0} 价稳${c.price_stable_score || 0} 风险${((c.risk_ratio || 0) * 100).toFixed(1)}%`,
    }))
  }

  const params = taskId ? { task_id: taskId } : {}
  const data = await getCandidates(params)
  return (data.candidates || []).map(c => ({
    code: c.code,
    name: c.name,
    score: c.score || 0,
    rating: c.score >= 80 ? 'strong' : c.score >= 70 ? 'medium' : 'weak',
    status: statusFor(c),
    detail: formatDetail(c),
  }))
}
```

再将 `loadResults()` 改为接收显式上下文：

```js
async function loadResults({ taskId, strategyType, context } = {}) {
  const targetTaskId = normalizeTaskId(taskId)
  const targetStrategyType = strategyType || activeStrategyType.value

  try {
    const candidates = await fetchMappedResults(targetTaskId, targetStrategyType)
    if (context && !isCurrentViewContext(context)) return false

    discoveries.value = dedupeDiscoveries(candidates)
    updateMetrics()
    return true
  } catch (e) {
    if (!context || isCurrentViewContext(context)) {
      console.error('Load results failed:', e)
    }
    return false
  }
}
```

必须满足：

- 历史任务调用时始终显式传 `taskId` 和 `strategyType`。
- 请求返回后先检查 context，再写 `discoveries`。
- Strategy1 和 Strategy2 的请求选择不能依赖异步期间可能变化的全局状态。

### 13.6 第四步：重写 `refreshTaskContext()`

建议完整替换为以下结构：

```js
async function refreshTaskContext(context) {
  const taskId = context.taskId

  try {
    const data = await getTaskStocks(taskId, {
      status: 'failed',
      page_size: 50,
      page: 1,
    })

    if (!isCurrentViewContext(context)) return false

    if (!data.ok) {
      scanError.value = data.error === 'TASK_NOT_FOUND'
        ? `任务不存在：${taskId}`
        : '历史任务加载失败'
      return false
    }

    scanProgress.taskId = taskId
    activeStrategyType.value = data.strategy_type
    failures.value = data.stocks || []
    failuresTotal.value = data.total || 0
    applyTaskSummary(data.summary)

    await loadResults({
      taskId,
      strategyType: data.strategy_type,
      context,
    })

    return isCurrentViewContext(context)
  } catch (e) {
    if (isCurrentViewContext(context)) {
      scanError.value = '历史任务加载失败'
      console.error('Load historical task failed:', e)
    }
    return false
  }
}
```

注意事项：

1. 参数必须是完整 context，而不是只有 `taskId`。
2. `getTaskStocks()` 返回后立即检查 context。
3. 只有当前 context 可以显示错误。
4. 旧请求失败时不能覆盖新页面上的 `scanError`。
5. `loadResults()` 返回后再次检查 context。

### 13.7 第五步：统一历史任务和实时任务切换入口

将 `switchTaskContext()` 作为唯一创建 context 的入口。建议替换为：

```js
async function switchTaskContext(newTaskId) {
  stopPolling()
  resetTaskView()
  scanError.value = ''

  const context = beginViewContext(newTaskId)

  if (context.taskId) {
    await loadHistoricalTask(context)
  } else {
    await loadLiveTask(context)
  }
}
```

然后修改首次加载和 watcher：

```js
onMounted(async () => {
  try {
    await switchTaskContext(routeTaskId.value || null)
  } finally {
    updateTime()
    clockTimer = setInterval(updateTime, 1000)
  }
})

watch(
  () => route.query.task,
  async (newTask, oldTask) => {
    const id = normalizeTaskId(newTask)
    if (id !== normalizeTaskId(oldTask)) {
      await switchTaskContext(id || null)
    }
  },
)
```

必须删除或停止使用以下重复路径：

- `onMounted()` 直接调用 `loadHistoricalTask(taskId)`
- `onMounted()` 直接调用 `loadLiveTask()`
- 任何其他自行递增 context 的入口

这样可以保证一次导航只创建一个 context。

### 13.8 第六步：重写 `loadHistoricalTask()`

建议替换为：

```js
async function loadHistoricalTask(context) {
  const ok = await refreshTaskContext(context)
  if (!ok || !isCurrentViewContext(context)) return false

  try {
    const status = await getScanStatus()
    if (!isCurrentViewContext(context)) return false

    if (status.running && status.task_id === context.taskId) {
      applyStats(status, { applyTaskId: false })
      scanning.value = true
      pollTimer = setInterval(pollStatus, 1000)
    }
  } catch (e) {
    if (isCurrentViewContext(context)) {
      scanError.value = '任务状态查询失败，已显示最近保存结果'
      console.error('Load historical task status failed:', e)
    }
  }

  return isCurrentViewContext(context)
}
```

关键行为：

- 状态查询失败时保留刚刚加载成功的 summary、候选和失败列表。
- 状态查询失败不能让 `onMounted()` 中断时钟初始化。
- 旧任务状态响应不能启动新任务页面的轮询。

### 13.9 第七步：保护实时任务加载

`loadLiveTask()` 同样会跨越多个 `await`，也必须使用 context。最低要求：

```js
async function loadLiveTask(context) {
  try {
    const status = await getScanStatus()
    if (!isCurrentViewContext(context)) return false

    applyStats(status)
    if (status.strategyType) {
      activeStrategyType.value = status.strategyType
    }

    const taskId = normalizeTaskId(status.task_id)
    const strategyType = status.strategyType || activeStrategyType.value

    if (taskId) {
      await loadFailures({ taskId, context })
      if (!isCurrentViewContext(context)) return false
    }

    await loadResults({ taskId, strategyType, context })
    if (!isCurrentViewContext(context)) return false

    if (status.running) {
      scanning.value = true
      pollTimer = setInterval(pollStatus, 1000)
    }
    return true
  } catch (e) {
    if (isCurrentViewContext(context)) {
      scanError.value = '实时任务加载失败'
      console.error('Check live status failed:', e)
    }
    return false
  }
}
```

不得让历史任务的迟到响应在用户切回实时模式后覆盖实时页面。

### 13.10 第八步：保护失败列表请求

将 `loadFailures()` 改为显式参数：

```js
async function loadFailures({ taskId, context } = {}) {
  const targetTaskId = normalizeTaskId(taskId)
  if (!targetTaskId) return false

  try {
    const data = await getTaskStocks(targetTaskId, {
      status: 'failed',
      page_size: 50,
      page: 1,
    })

    if (context && !isCurrentViewContext(context)) return false
    if (!data.ok) return false

    failures.value = data.stocks || []
    failuresTotal.value = data.total || 0
    if (data.strategy_type) {
      activeStrategyType.value = data.strategy_type
    }
    return true
  } catch (e) {
    if (!context || isCurrentViewContext(context)) {
      console.error('Load failures failed:', e)
    }
    return false
  }
}
```

`loadMoreFailures()` 也必须在请求前捕获当前 taskId 和 context，并在追加数据前校验：

```js
async function loadMoreFailures() {
  const context = captureCurrentViewContext()
  const taskId = scanProgress.taskId
  if (!taskId) return

  const nextPage = Math.floor(failures.value.length / 50) + 1
  const data = await getTaskStocks(taskId, {
    status: 'failed',
    page_size: 50,
    page: nextPage,
  })

  if (!isCurrentViewContext(context) || scanProgress.taskId !== taskId) return
  if (data.stocks?.length) {
    failures.value = [...failures.value, ...data.stocks]
  }
  failuresTotal.value = data.total || failuresTotal.value
}
```

### 13.11 第九步：保护轮询并阻止轮询乱序回写

这是一次性修复中最容易遗漏的部分。

当前 `setInterval(pollStatus, 1000)` 允许前一次请求未完成时启动下一次请求。旧轮询响应可能晚于新轮询响应返回，导致进度倒退；任务切换后，旧轮询还可能停止新任务轮询。

在 `pollStatus()` 开始时捕获：

```js
async function pollStatus() {
  const context = captureCurrentViewContext()
  const requestEpoch = ++pollRequestEpoch

  try {
    const status = await getScanStatus()

    if (!isCurrentViewContext(context)) return
    if (requestEpoch !== pollRequestEpoch) return

    // 原有状态处理逻辑
  } catch (e) {
    if (isCurrentViewContext(context) && requestEpoch === pollRequestEpoch) {
      scanError.value = '状态查询失败'
      console.error(e)
    }
  }
}
```

在 `pollStatus()` 内部每个额外 `await` 后仍要检查 `isCurrentViewContext(context)`：

```js
const ok = await refreshTaskContext(context)
if (!ok || !isCurrentViewContext(context)) return
```

必须特别修改以下分支：

1. 历史任务状态不匹配后刷新最终任务数据的分支。
2. `!status.running && scanning.value` 的完成分支。
3. 轮询末尾加载失败列表的分支。

建议完成分支结构：

```js
if (!status.running && scanning.value) {
  stopPolling()

  if (context.taskId) {
    const ok = await refreshTaskContext(context)
    if (!ok || !isCurrentViewContext(context)) return
  } else {
    await loadResults({
      taskId: scanProgress.taskId,
      strategyType: activeStrategyType.value,
      context,
    })
    if (!isCurrentViewContext(context)) return

    await loadFailures({
      taskId: scanProgress.taskId,
      context,
    })
    if (!isCurrentViewContext(context)) return
  }

  addLog('found', `扫描完成 · 发现 ${scanProgress.candidates} 个候选 · 跳过 ${scanProgress.skipped} · 失败 ${scanProgress.failed}`)
  return
}
```

注意：`stopPolling()` 会使旧轮询 request epoch 失效，但不会改变 `viewContextEpoch`，因此完成分支后续应使用 `isCurrentViewContext(context)` 判断页面是否仍是同一上下文。

### 13.12 第十步：保护用户操作请求的迟到响应

`handleRetryFailed()` 也会在 `await` 后修改共享页面状态。用户点击重试后如果切换到其他任务，旧重试响应不能让新任务页面进入扫描状态。

最低修复要求：

1. 发请求前捕获当前 context。
2. 请求返回后先检查用户是否仍在预期页面上下文。
3. 如果用户已经切换到其他历史任务，旧操作响应不能设置 `scanning`、`scanProgress.taskId`、`activeStrategyType` 或启动轮询。

以 `handleRetryFailed()` 为例：

```js
async function handleRetryFailed() {
  const context = captureCurrentViewContext()
  const taskId = scanProgress.taskId
  if (!taskId) return

  const res = await retryFailedStocks(taskId)
  if (!isCurrentViewContext(context) || scanProgress.taskId !== taskId) return

  if (!res.ok || res.error) {
    scanError.value = res.statusCode === 409
      ? `扫描已在运行中：${res.running_task_id || '--'}`
      : (res.error || '重拉失败股票失败')
    return
  }
  if (res.retry_count === 0) {
    scanError.value = '没有需要重拉的失败股票'
    return
  }

  scanning.value = true
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = setInterval(pollStatus, 1000)
}
```

不要尝试取消已经提交到后端的重试操作；本次要求是避免迟到响应污染当前页面。

`handleStartScan()` 和 `handleStartStrategy2Scan()` 本轮不要求改动。它们涉及主动从历史模式切换到实时模式，若未经完整测试直接套用历史 context 校验，可能导致后端已启动但前端没有进入轮询。本轮不要扩大到启动流程。

### 13.13 第十一步：检查所有旧调用点

修改函数签名后，必须使用以下命令查找遗漏调用点：

```bash
rg -n "refreshTaskContext|loadHistoricalTask|loadLiveTask|loadResults|loadFailures|loadMoreFailures|pollStatus|switchTaskContext" web/src/pages/ScannerConsole.vue
```

逐项确认：

| 函数 | 必须接收或捕获的内容 |
| --- | --- |
| `switchTaskContext` | 创建唯一 context |
| `loadHistoricalTask` | 接收 context |
| `refreshTaskContext` | 接收 context |
| `loadLiveTask` | 接收 context |
| `loadResults` | 显式 taskId、strategyType、context |
| `loadFailures` | 显式 taskId、context |
| `loadMoreFailures` | 捕获 taskId 和 context |
| `pollStatus` | 捕获 context 和 poll request epoch |
| `handleRetryFailed` | 捕获 taskId 和 context |

禁止保留旧式调用：

```js
await refreshTaskContext(taskId)
await loadResults()
await loadFailures()
await loadLiveTask()
```

历史或轮询链路中的调用必须携带明确上下文。

---

## 14. 最终一次性测试实施方案

### 14.1 增加统一测试工具

在测试文件顶部增加：

```js
function deferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

async function flushUi() {
  await Promise.resolve()
  await nextTick()
  await Promise.resolve()
  await nextTick()
}
```

增加用于精确读取 ScanEngine props 的 stub：

```js
const ScanEngineStub = {
  props: [
    'running', 'scanned', 'total', 'skipped', 'failed',
    'candidates', 'latestTradeDate', 'stockPoolSource',
  ],
  template: `
    <div data-test="scan-summary">
      running={{ running }}
      processed={{ scanned }}
      total={{ total }}
      skipped={{ skipped }}
      failed={{ failed }}
      candidates={{ candidates }}
      latest={{ latestTradeDate }}
      source={{ stockPoolSource }}
    </div>
  `,
}
```

修改挂载方法：

```js
function mountPage() {
  return mount(ScannerConsole, {
    global: {
      stubs: {
        ScanEngine: ScanEngineStub,
        'router-link': true,
        'router-view': true,
      },
    },
  })
}
```

### 14.2 修复已完成历史任务 summary 测试

必须将原来的弱断言：

```js
expect(wrapper.text()).toContain('失败股票')
```

替换为精确断言：

```js
const summary = wrapper.get('[data-test="scan-summary"]').text()
expect(summary).toContain('processed=100')
expect(summary).toContain('total=100')
expect(summary).toContain('skipped=0')
expect(summary).toContain('failed=2')
expect(summary).toContain('candidates=3')
expect(summary).toContain('latest=2026-06-10')
expect(summary).toContain('source=akshare')
```

同时断言：

```js
expect(mockApi.getStrategy2Candidates).toHaveBeenCalledWith('s2-completed')
expect(mockApi.getCandidates).not.toHaveBeenCalledWith({ task_id: 's2-completed' })
```

### 14.3 修复运行→完成测试

必须验证真实状态变化，而不只是请求次数：

1. 首次 summary 为 `processed=80`、`total=100`。
2. 推进 fake timer。
3. 最终 summary 为 `processed=100`。
4. 最终 `failed`、`candidates`、`latest` 与数据库 summary 一致。
5. 页面出现一次完成日志。

参考断言：

```js
expect(wrapper.get('[data-test="scan-summary"]').text()).toContain('processed=80')

await vi.advanceTimersByTimeAsync(1000)
await flushUi()

const summary = wrapper.get('[data-test="scan-summary"]').text()
expect(summary).toContain('processed=100')
expect(summary).toContain('failed=5')
expect(summary).toContain('candidates=3')
expect(summary).toContain('latest=2026-06-10')
expect(wrapper.text()).toContain('扫描完成')
```

### 14.4 新增 A 慢、B 快竞态测试

必须新增以下测试，不允许只测试顺序切换：

```js
it('late task A response cannot overwrite newer task B context', async () => {
  const taskA = deferred()

  mockRoute.query = { task: 'task-a' }
  mockApi.getTaskStocks.mockImplementation(taskId => {
    if (taskId === 'task-a') return taskA.promise
    if (taskId === 'task-b') {
      return Promise.resolve({
        ok: true,
        total: 1,
        strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE',
        stocks: [{ code: '222222', name: 'B-fail', status: 'failed' }],
        summary: {
          total_stocks: 20,
          processed: 20,
          failed: 1,
          candidate: 5,
          latest_trade_date: '2026-06-10',
          stock_pool_source: 'akshare',
        },
      })
    }
    throw new Error(`unexpected task ${taskId}`)
  })
  mockApi.getStrategy2Candidates.mockResolvedValue({
    candidates: [{ code: '222222', name: 'B-candidate', total_score: 88 }],
  })

  wrapper = mountPage()
  await flushUi()

  mockRoute.query = { task: 'task-b' }
  await flushUi()

  expect(wrapper.text()).toContain('B-fail')
  expect(wrapper.text()).toContain('B-candidate')

  taskA.resolve({
    ok: true,
    total: 1,
    strategy_type: 'STRATEGY_1_CUP_HANDLE',
    stocks: [{ code: '111111', name: 'A-fail', status: 'failed' }],
    summary: { total_stocks: 10, processed: 10, failed: 1, candidate: 0 },
  })
  await flushUi()

  expect(wrapper.text()).toContain('B-fail')
  expect(wrapper.text()).toContain('B-candidate')
  expect(wrapper.text()).not.toContain('A-fail')
  expect(wrapper.text()).not.toContain('重新拉取')
  expect(mockApi.getCandidates).not.toHaveBeenCalledWith({ task_id: 'task-a' })
})
```

如果测试实现中 B 候选不直接显示名称，可改为断言 B 候选对应的卡片或 mock 调用，但必须证明 A 的迟到响应没有提交。

### 14.5 新增历史任务慢响应后切回 live 的测试

场景：

1. 打开 Strategy2 历史任务 B，保持 `getTaskStocks('task-b')` pending。
2. 将 query 切换为空。
3. live 状态返回 Strategy1 任务和 live 候选。
4. 再 resolve B。
5. B 不得覆盖 live 页面。

至少断言：

- live 候选仍存在。
- B 失败股票不出现。
- B 的 Strategy2 候选不出现。
- 页面不错误隐藏 Strategy1 的可用操作。
- 迟到 B 响应不能改变 live summary。

### 14.6 新增旧轮询响应不得覆盖新任务测试

必须覆盖已经发出的 `pollStatus()`：

1. 打开运行中的历史任务 A，使轮询启动。
2. 让一次 A 的 `getScanStatus()` 轮询请求保持 pending。
3. 切换到已完成任务 B，并成功显示 B。
4. 再返回 A 的旧轮询响应。
5. 断言 B 的 summary、候选和失败列表不变。
6. 断言旧 A 轮询没有清除或重启 B 的错误轮询。

这个测试用于保护 `pollRequestEpoch`，不能省略。

### 14.7 新增状态查询失败保留历史结果测试

测试步骤：

1. `getTaskStocks()` 返回成功的历史 summary、失败列表。
2. 对应候选接口返回成功。
3. `getScanStatus()` reject。
4. 断言历史 summary、候选和失败列表仍显示。
5. 断言显示：

```text
任务状态查询失败，已显示最近保存结果
```

6. 测试不能产生未处理 rejection。

### 14.8 测试数量要求

现有前端测试为 11 个。本轮至少新增或强化：

- 强化已完成 summary：1 个
- 强化运行→完成：1 个
- A 慢 B 快：1 个
- 历史慢响应→live：1 个
- 旧轮询迟到：1 个
- 状态查询失败保留结果：1 个

最终 Vitest 应至少为：

```text
1 file / 15 tests passed
```

如果通过合并测试导致数量少于 15，交付说明中必须明确每个上述场景由哪个测试覆盖。

---

## 15. 修复完成后的静态检查

修复 AI 在运行测试前必须先做以下静态核对。

### 15.1 不允许出现的调用

```bash
rg -n "refreshTaskContext\\([^c]|loadHistoricalTask\\([^c]|loadLiveTask\\(\\)|loadResults\\(\\)|loadFailures\\(\\)" web/src/pages/ScannerConsole.vue
```

目标：历史任务和轮询链路中不再存在不带 context 的旧式调用。

### 15.2 必须出现的保护

```bash
rg -n "viewContextEpoch|pollRequestEpoch|isCurrentViewContext|beginViewContext" web/src/pages/ScannerConsole.vue
```

目标：

- 每个关键异步状态写入函数都能找到 context 校验。
- `stopPolling()` 会使在途 poll 失效。
- `pollStatus()` 同时校验 view context 和 poll request epoch。

### 15.3 修改范围核对

```bash
git diff --name-only
```

预期主要只有：

```text
web/src/pages/ScannerConsole.vue
web/src/pages/__tests__/ScannerConsole.history-task.test.js
```

审核文档或操作日志可以更新，但不得出现策略算法、数据库或后端 API 改动。

---

## 16. 最终验收命令与预期结果

按顺序执行，任何一步失败都不能宣称修复完成。

```bash
# 1. 前端竞态与 summary 测试
cd web
npm.cmd test -- --run

# 2. 前端生产构建
npm.cmd run build
cd ..

# 3. Strategy2 重点后端回归
python -m pytest tests/test_strategy2_acceptance_fixes.py tests/test_strategy2_final_fixes.py tests/test_strategy2_bug_fixes.py tests/test_strategy2_engine.py tests/test_strategy2_indicators.py tests/test_strategy2_scorer.py tests/test_strategy2_rejection.py tests/test_strategy2_risk.py -q

# 4. 后端完整离线回归
python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py

# 5. 编译与 diff 检查
python -m compileall strategy2 scanner server.py -q
git diff --check
git status --short
```

最低预期：

```text
Vitest：至少 15 passed，0 failed
前端 build：通过
Strategy2 重点后端：至少 176 passed，0 failed
后端全量：至少 426 passed，0 failed
compileall：通过
git diff --check：无输出
```

---

## 17. 修复 AI 最终回复模板

修复 AI 完成后必须按以下格式回复，避免只说“已修复”：

```markdown
## 修复结果

### ROUND7-S2-001
- 修改函数：
- stale response 防护方式：
- 如何保证旧 poll 不覆盖新任务：
- 新增测试：

### ROUND7-S2-002
- 修改函数：
- 状态查询失败时页面行为：
- 新增测试：

### ROUND7-S2-003
- 原弱断言替换为：
- summary 精确断言字段：
- 新增竞态测试：

### 未修改内容
- Strategy1/Strategy2 算法未修改
- 数据库结构未修改
- 后端 API 契约未修改
- 数据源仍为 baidu/sina/tencent
- 全源失败仍直接失败，不使用缓存

### 验证结果
- Vitest：
- 前端 build：
- Strategy2 重点后端：
- 后端全量：
- compileall：
- git diff --check：
- git status --short：

### 提交信息
- Commit Hash：
- 修改文件列表：
```

只有上述内容完整、所有命令通过，并且修改范围符合要求，才可以交付下一轮最终验收。

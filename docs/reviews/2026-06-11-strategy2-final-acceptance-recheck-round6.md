# 代码问题检查报告

## 1. 检查范围

- 审核分支：`codex/strategy2-extreme-dry-stable-design`
- 审核提交：`7b95046 fix(strategy2): round5 — history completion state, query switch cleanup, vitest upgrades, doc sync`
- 对比基线：`6f04564`
- 重点检查：
  - Round5 问题是否真实修复
  - 历史任务首次打开、轮询完成、URL query 切换
  - Strategy1 / Strategy2 历史任务上下文隔离
  - 失败股票与最终 summary 展示
  - 三数据源与全源失败不使用缓存规则
  - 前后端测试是否真实覆盖声称修复的场景

---

## 2. 总体结论

Round5 的主要运行时代码修复方向正确：

- 历史运行任务完成后，`pollStatus()` 已不再直接跳过最终刷新。
- query 切换前已清空旧任务统计、候选、失败列表和策略类型。
- busy 超限诊断测试已精确断言主要字段。
- Strategy2 主设计文档和共享日线服务已统一为三数据源。
- 全部在线数据源失败后直接失败，不使用缓存继续扫描。
- Strategy2 算法代码在本次提交中未修改，未发现新的策略算法回归。

但本轮仍不能最终验收通过。

当前剩余一个真实用户可见 bug：直接打开已经完成的历史任务时，后端返回的完整 summary 没有应用到页面，扫描统计仍显示为 0。

另外，Round5 要求的历史完成态测试和有效任务 A 切换到有效任务 B 的测试并未真实完成；query 切换加载异常时还会把所有 HTTP 错误错误显示成“任务不存在”，网络异常则可能没有页面错误提示。

---

## 3. 问题清单

| 编号 | 问题 | 严重程度 | 影响范围 | 是否必须修复 |
| --- | --- | --- | --- | --- |
| ROUND6-S2-001 | 直接打开已完成历史任务时未应用任务 summary，统计显示为 0 | 高 | 历史任务统计 / 用户判断 | 是 |
| ROUND6-S2-002 | query 切换加载失败时错误语义不准确，网络异常未处理 | 中 | 历史任务切换 / 错误展示 | 是 |
| ROUND6-S2-003 | 历史完成态与有效任务 A→B 测试仍未真实实现 | 中 | 前端回归可信度 | 是 |

---

## 4. 详细问题分析

### ROUND6-S2-001：直接打开已完成历史任务时未应用任务 summary

#### 问题现象

用户直接打开一个已经完成的历史任务：

```text
/?task=completed-task-id
```

页面能够加载该任务的候选和失败股票，但扫描引擎区域中的以下统计仍可能显示为 0：

- 已处理
- 总股票数
- 跳过
- 失败
- 候选
- 最新交易日
- 股票池来源

#### 涉及模块

- `web/src/pages/ScannerConsole.vue:545`
- `web/src/pages/ScannerConsole.vue:552`
- `web/src/pages/ScannerConsole.vue:563`
- `web/src/pages/ScannerConsole.vue:566`

#### 证据链

任务股票接口已经返回完整 summary：

```js
{
  strategy_type,
  stocks,
  total,
  summary
}
```

`refreshTaskContext()` 正确应用了 summary：

```js
applyTaskSummary(data.summary)
```

但页面首次加载历史任务使用的是另一套重复实现 `loadHistoricalTask()`：

```js
activeStrategyType.value = data.strategy_type
failures.value = data.stocks || []
failuresTotal.value = data.total || 0
await loadResults()
```

该函数没有调用：

```js
applyTaskSummary(data.summary)
```

随后只有在目标任务当前仍处于运行状态时，才会通过 `applyStats()` 更新统计：

```js
if (status.running && status.task_id === taskId) {
  applyStats(status, { applyTaskId: false })
}
```

因此，已完成历史任务不会进入该分支，统计保持初始值 0。

#### 触发条件

1. 任务已经完成。
2. 用户刷新浏览器，或直接访问带 `?task=` 的历史任务链接。
3. 当前该任务不再运行。

#### 影响

- 用户看到候选或失败股票，但页面同时显示“已处理 0 / 总数 0”。
- 用户可能误判历史任务没有真正执行。
- TaskCenter、历史详情和扫描控制台对同一任务显示不一致。

#### 修复建议

最低风险修复：

在 `loadHistoricalTask()` 成功读取任务后立即增加：

```js
applyTaskSummary(data.summary)
```

推荐修复：

不要继续维护两套历史任务加载流程。让首次加载和 query 切换共同调用同一任务上下文加载函数，确保以下行为只有一份实现：

1. 清理旧任务状态。
2. 调用 `getTaskStocks()`。
3. 应用 `strategy_type`、失败列表和 summary。
4. 加载正确策略的候选。
5. 检查目标任务是否仍在运行。
6. 决定是否启动轮询。

可以保留 `switchTaskContext()` 作为统一入口，并让 `onMounted()` 在历史模式下调用它；或让 `loadHistoricalTask()` 内部复用 `refreshTaskContext()`。

不要在多个函数中分别手动复制 summary、失败列表和策略类型恢复逻辑。

#### 验证方式

新增真实组件测试：

1. 设置 URL 为 `?task=completed-s2`。
2. `getTaskStocks()` 返回：

```js
{
  ok: true,
  strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE',
  stocks: [{ code: '000001', status: 'failed' }],
  total: 2,
  summary: {
    total_stocks: 100,
    processed: 100,
    skipped: 7,
    failed: 2,
    candidate: 3,
  },
}
```

3. `getScanStatus()` 返回 `running=false`。
4. 断言页面显示 `100 / 100`、失败 2、候选 3。
5. 断言 Strategy2 候选接口被调用，Strategy1 候选接口未被调用。

---

### ROUND6-S2-002：query 切换加载失败时错误语义不准确

#### 问题现象

当前 query 切换路径中，只要 `refreshTaskContext()` 返回 false，就统一显示：

```text
任务不存在：<task-id>
```

这会把后端 500、权限错误、响应解析失败等非 404 错误也误报成任务不存在。

如果 `getTaskStocks()` 因网络异常直接抛出异常，`switchTaskContext()` 和 watcher 没有捕获该异常，页面可能不显示明确错误。

#### 涉及模块

- `web/src/pages/ScannerConsole.vue:306`
- `web/src/pages/ScannerConsole.vue:340`
- `web/src/pages/ScannerConsole.vue:348`
- `web/src/pages/ScannerConsole.vue:605`
- `web/src/composables/useApi.js:33`

#### 证据链

`refreshTaskContext()` 只返回布尔值，不负责设置错误：

```js
const data = await getTaskStocks(...)
if (!data.ok) return false
```

`switchTaskContext()` 将所有 false 都解释成任务不存在：

```js
if (!ok) {
  scanError.value = `任务不存在：${newTaskId}`
  return
}
```

而 `getTaskStocks()` 没有捕获网络异常，`fetch()` 失败时会直接抛出。

#### 触发条件

- 切换 query 时后端返回非 404 错误。
- 后端服务不可用或网络请求失败。
- 返回内容无法解析为 JSON。

#### 影响

- 用户收到错误原因错误的提示。
- 网络异常可能只出现在控制台，页面没有可执行信息。
- 后续排查容易误认为任务 ID 错误。

#### 修复建议

让 `refreshTaskContext()` 统一负责加载错误语义：

```js
async function refreshTaskContext(taskId) {
  try {
    const data = await getTaskStocks(taskId, { status: 'failed', page_size: 50, page: 1 })
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
    await loadResults()
    return true
  } catch (e) {
    scanError.value = '历史任务加载失败'
    console.error('Load historical task failed:', e)
    return false
  }
}
```

然后删除 `switchTaskContext()` 中无条件设置“任务不存在”的逻辑。

历史任务完成分支中，只有 `refreshTaskContext()` 成功后才写入“扫描完成”日志；刷新失败时应保留明确错误，不要生成成功日志。

#### 验证方式

补充测试：

- query 切换到不存在任务：显示“任务不存在”。
- query 切换时接口返回 `ok=false/error=INTERNAL_ERROR`：显示“历史任务加载失败”。
- query 切换时 `getTaskStocks()` reject：显示“历史任务加载失败”，且旧任务状态已清空。

---

### ROUND6-S2-003：关键前端测试仍未真实实现

#### 问题现象

当前前端共有 7 个通过测试，但其中名为：

```text
historical running task refreshes final summary after completion
```

的测试没有触发一次轮询，也没有让状态从 running 变为 completed。

Round5 明确要求的：

```text
query change from task A to task B reloads B and clears A
```

仍未实现。

#### 涉及模块

- `web/src/pages/__tests__/ScannerConsole.history-task.test.js:116`
- `web/src/pages/__tests__/ScannerConsole.history-task.test.js:137`

#### 证据链

历史完成态测试中：

- `getScanStatus()` 始终返回 `running=true`。
- 没有使用 `mockResolvedValueOnce()` 返回完成态。
- 没有调用 `vi.advanceTimersByTimeAsync(1000)`。
- 没有断言 `getTaskStocks()` 在完成后再次调用。
- 没有断言最终 summary、最终失败列表或完成日志。

因此测试名称与实际验证内容不一致。

当前 query 测试只覆盖：

```text
有效任务 A → 不存在任务
```

没有覆盖：

```text
有效任务 A → 有效任务 B
```

所以无法证明切换到另一个合法任务时，策略类型、候选接口、失败列表和 summary 都正确切换。

#### 影响

- ROUND6-S2-001 这种直接可见的统计 bug 未被测试发现。
- 历史完成态逻辑未来回归时，现有测试仍可能全部通过。
- Strategy1 与 Strategy2 之间的合法任务切换仍缺少运行时保护。

#### 修复建议

将当前历史完成态测试改为真实状态序列：

```js
mockApi.getScanStatus
  .mockResolvedValueOnce({
    running: true,
    task_id: 's2-running-hist',
    strategyType: 'STRATEGY_2_EXTREME_DRY_STABLE',
    stats: { processed: 80, total_stocks: 100 },
  })
  .mockResolvedValueOnce({
    running: false,
    task_id: null,
    stats: {},
  })
```

让 `getTaskStocks()` 首次返回运行中 summary，完成刷新时返回最终 summary；然后：

```js
await vi.advanceTimersByTimeAsync(1000)
```

至少断言：

- `getTaskStocks('s2-running-hist', ...)` 调用至少两次。
- 最终显示 processed=100、failed、candidate。
- 最终失败股票已更新。
- 页面出现完成日志。
- 没有加载其他任务。

增加有效任务 A→B 测试：

1. A 为 Strategy1，包含 `A-fail` 和 A 候选。
2. B 为 Strategy2，包含 `B-fail` 和 B 候选。
3. 修改响应式 `mockRoute.query` 从 A 到 B。
4. 断言 A 的失败、候选和重试按钮全部消失。
5. 断言 B 的失败、候选和 summary 显示。
6. 断言调用 `getStrategy2Candidates('task-b')`，不使用 Strategy1 候选接口加载 B。

增加已完成历史任务首次加载 summary 测试，以直接保护 ROUND6-S2-001。

---

## 5. 已确认修复完成

- Round5 历史任务完成分支不再在最终刷新前直接 return。
- query 切换前会清理旧任务主要可见状态。
- 未使用的 `lastKnownTaskId` 已删除。
- busy 超限保存并测试主源、备源、错误和完整 `source_errors`。
- Strategy2 生产数据源为 `baidu`、`sina`、`tencent`。
- Strategy2 全部在线数据源失败时不使用缓存扫描。
- 主设计文档和共享服务注释已与三源直接失败规则一致。
- 本轮提交未改动 Strategy2 指标、评分、拒绝规则和风险计算公式。

---

## 6. 建议修复顺序

1. 修复已完成历史任务首次加载不应用 summary。
2. 统一 `refreshTaskContext()` 的错误处理语义。
3. 让历史任务首次加载和 query 切换复用同一上下文恢复逻辑。
4. 修复历史完成态测试，使其真实推进定时器并返回完成态。
5. 增加完成历史任务首次加载 summary 测试。
6. 增加有效任务 A→B 的策略切换测试。
7. 增加非 404 和网络异常测试。
8. 执行完整验收门禁。

---

## 7. 给修复 AI 的执行要求

1. 不修改 Strategy2 指标、评分、拒绝规则、风险计算和候选门槛。
2. 不修改数据库结构和任务 API 响应字段。
3. 不恢复缓存兜底、mootdx 或 yfinance。
4. 不删除历史任务轮询。
5. 不通过隐藏统计解决问题，必须应用后端返回的真实 summary。
6. 不保留两套语义不同的历史任务恢复逻辑。
7. 前端测试必须真实推进 fake timer，不能只使用与测试名称不符的静态断言。
8. 不重构无关页面和组件。

---

## 8. 回归测试清单

- 直接打开已完成 Strategy1 历史任务，summary 正确。
- 直接打开已完成 Strategy2 历史任务，summary 正确。
- 历史运行任务完成后最终 summary、候选和失败列表正确。
- 有效任务 A→有效任务 B 后只显示 B。
- 有效任务 A→不存在任务后旧状态清空并显示任务不存在。
- query 加载返回非 404 错误时显示历史任务加载失败。
- query 加载网络异常时显示历史任务加载失败。
- 历史 Strategy2 不显示 Strategy1 重试按钮。
- Strategy2 三源全部失败直接标记失败，不使用缓存。
- Strategy2 指标、评分、拒绝规则和风险计算测试全部通过。

---

## 9. 不建议修改的内容

- 不修改 Strategy2 算法。
- 不修改 Strategy1 算法。
- 不修改三数据源顺序。
- 不修改候选表和任务表结构。
- 不调整前端整体 UI 风格。
- 不修改已通过的失败诊断持久化逻辑。

---

## 10. 最终交付标准

1. 已完成历史任务首次打开时统计不再显示为 0。
2. 历史运行任务完成后无需刷新浏览器即可看到最终结果。
3. query 在任意两个合法任务之间切换时不串数据。
4. 404、后端错误和网络异常显示正确错误语义。
5. 前端测试真实覆盖首次加载、轮询完成和 A→B 切换。
6. Strategy2 算法和三源直接失败规则不发生回归。
7. 全部验收命令通过。

---

## 11. 本轮验证结果

```text
重点后端验收：
61 passed

后端全量：
426 passed

前端 Vitest：
1 file / 7 tests passed

前端 build：
通过

compileall：
通过

git diff --check：
通过

工作树：
干净
```

测试全部通过不代表本轮可以最终验收，因为 ROUND6-S2-001 可由静态控制流直接确认，且现有测试没有覆盖该路径。


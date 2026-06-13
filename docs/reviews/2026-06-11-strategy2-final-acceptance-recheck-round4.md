# 代码问题检查报告

## 1. 检查范围

- 审核提交：`b43cdcc fix(strategy2): round3 — API 404, source diagnostics, history isolation, terminal tests, source cleanup`
- 对比基线：`948b284`
- 重点检查 Round 3 六项修复要求、扫描完成态、历史任务切换、前端运行时测试和三数据源规则同步。

---

## 2. 总体结论

本轮后端核心修复基本正确：

- 不存在任务股票接口已返回 404。
- 策略2失败记录已保存完整主备源诊断。
- 六终态测试已精确断言状态、原因和回调。
- 后台测试线程 warning 已消除。
- 默认全量测试不再收集外网诊断脚本。
- mootdx/yfinance 已从生产代码和默认测试中删除。

但仍不能最终验收通过。剩余实际功能问题是：扫描完成后，状态接口不再携带任务与统计，前端会把最终统计重置为 0；历史运行任务完成时还会跳过最终结果刷新。前端运行时测试和业务规则文档也没有按上一轮方案完成。

---

## 3. 问题清单

| 编号 | 问题 | 严重程度 | 影响范围 | 必须修复 |
| --- | --- | --- | --- | --- |
| ROUND4-S2-001 | 扫描完成后前端最终统计归零，历史运行任务完成后不刷新最终结果 | 高 | 扫描进度 / 失败数 / 候选数 / 历史任务 | 是 |
| ROUND4-S2-002 | ScannerConsole 不监听 URL task 参数变化，同组件切换历史任务会显示旧数据 | 中 | 浏览器前进后退 / 历史任务切换 | 是 |
| ROUND4-S2-003 | 前端运行时测试未实现，`npm run test` 直接失败 | 中 | 前端回归可信度 | 是 |
| ROUND4-S2-004 | Strategy2 设计文档和共享日线服务注释仍描述四源与失败缓存兜底 | 中 | 业务规则一致性 / 后续开发 | 是 |
| ROUND4-S2-005 | 完整数据源诊断的新行为缺少精确回归断言 | 低 | 回归保护 | 是 |

---

## 4. 详细问题分析

### ROUND4-S2-001：扫描完成后最终统计归零，历史运行任务不刷新最终结果

#### 问题现象

实时扫描完成后，扫描引擎展示的已处理、失败、跳过、候选等统计会被重置为 0。

若用户打开的是一个仍在运行的历史任务链接，该任务完成后，页面会停止轮询，但不会重新加载最终候选和失败股票。

#### 涉及模块

- `server.py:455`
- `server.py:506`
- `web/src/pages/ScannerConsole.vue:279`
- `web/src/pages/ScannerConsole.vue:284`
- `web/src/pages/ScannerConsole.vue:287`
- `web/src/pages/ScannerConsole.vue:288`
- `web/src/pages/ScannerConsole.vue:300`
- `web/src/pages/ScannerConsole.vue:316`

#### 证据链

任务运行期间 `/api/scan/status` 返回完整统计：

```json
{
  "running": true,
  "task_id": "running-s2",
  "stats": {
    "processed": 10,
    "failed": 2,
    "candidates_found": 3
  }
}
```

任务完成并执行 `_clear_running()` 后，同一接口返回：

```json
{
  "running": false,
  "task_id": null,
  "strategyType": null,
  "stats": {}
}
```

前端 `pollStatus()` 在判断完成前先调用 `applyStats()`；`applyStats()` 对不存在的字段使用 `|| 0`，因此将统计全部归零。

历史模式还先执行：

```js
if (isHistoricalMode.value && status.task_id !== routeTaskId.value) {
  scanning.value = false
  clearInterval(...)
  return
}
```

任务完成后 `status.task_id` 为 `null`，必然进入该分支并提前返回，最终 `loadResults()` 和 `loadFailures()` 不会执行。

#### 影响

- 用户看到的最终扫描统计不准确。
- 完成日志可能显示“候选 0、失败 0”。
- 最后一个轮询周期产生的候选或失败可能不会展示。
- 历史任务链接在运行转完成时状态不完整。

#### 修复建议

为任务上下文接口返回完整 summary，前端在完成或任务不匹配时按目标 task_id 主动恢复最终状态。

修改 `GET /api/scan/tasks/{task_id}/stocks`，增加：

```python
summary = db.refresh_scan_task_counts(task_id)
return {
    ...,
    "summary": summary,
}
```

保持现有 `total` 含义不变：带 `status=failed` 时仍表示失败股票总数。

前端新增统一方法：

```js
function applyTaskSummary(summary = {}) {
  scanProgress.scanned = summary.processed ?? summary.scanned ?? 0
  scanProgress.total = summary.total_stocks ?? 0
  scanProgress.skipped = summary.skipped ?? 0
  scanProgress.failed = summary.failed ?? summary.failed_count ?? 0
  scanProgress.candidates = summary.candidate
    ?? summary.candidates_count
    ?? 0
  scanProgress.latestTradeDate = summary.latest_trade_date ?? ''
  scanProgress.stockPoolSource = summary.stock_pool_source ?? ''
}
```

新增统一任务恢复函数，必须按指定任务加载：

```js
async function refreshTaskContext(taskId) {
  const data = await getTaskStocks(taskId, {
    status: 'failed',
    page_size: 50,
    page: 1,
  })
  if (!data.ok) return false

  scanProgress.taskId = taskId
  activeStrategyType.value = data.strategy_type
  failures.value = data.stocks || []
  failuresTotal.value = data.total || 0
  applyTaskSummary(data.summary)
  await loadResults()
  return true
}
```

`pollStatus()` 调整顺序：

1. 如果 `status.running` 且任务匹配，再应用实时状态。
2. 如果当前页面正在跟踪的任务已经不再运行，使用保存的 `scanProgress.taskId` 或 `routeTaskId` 调用 `refreshTaskContext()`。
3. 刷新最终任务上下文后再停止轮询和写完成日志。
4. 不得把空 `stats` 写入页面。

`applyStats()` 应使用 `??` 保留缺失字段的旧值，而不是无条件 `|| 0`：

```js
scanProgress.scanned = stats.processed ?? stats.scanned ?? scanProgress.scanned
```

#### 必须验证

1. 实时策略1完成后最终统计不归零。
2. 实时策略2完成后最终统计不归零。
3. 历史策略2任务从运行转完成后加载最终候选和失败列表。
4. 完成日志中的统计与数据库 summary 一致。
5. 最后一个轮询周期新增的失败股票仍能显示。

---

### ROUND4-S2-002：URL task 参数变化不会重新加载任务

#### 问题现象

`routeTaskId` 是 computed，但页面仅在 `onMounted()` 中调用一次 `loadHistoricalTask()`。

Vue Router 在仅 query 参数变化时通常复用同一个 `ScannerConsole` 组件。因此通过浏览器前进/后退，或从 `?task=A` 切换到 `?task=B` 时：

- URL 已变为任务 B。
- 页面仍显示任务 A 的失败股票和候选。

#### 涉及模块

- `web/src/pages/ScannerConsole.vue:104`
- `web/src/pages/ScannerConsole.vue:117`
- `web/src/pages/ScannerConsole.vue:469`
- `web/src/pages/ScannerConsole.vue:514`

#### 修复建议

引入 `watch`，并统一清理轮询及页面任务状态：

```js
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function switchTaskContext(taskId) {
  stopPolling()
  discoveries.value = []
  failures.value = []
  failuresTotal.value = 0
  scanError.value = ''

  if (taskId) {
    await loadHistoricalTask(taskId)
  } else {
    await loadLiveTask()
  }
}

watch(routeTaskId, async (newTaskId, oldTaskId) => {
  if (newTaskId === oldTaskId) return
  await switchTaskContext(newTaskId)
})
```

需要防止从历史页面点击“开始扫描”时 `router.replace()` 与启动逻辑并发重复加载。可采用一个明确的 `switchingToNewScan` 标记，或让启动函数只负责导航，等待 watcher 完成后再启动。不要依赖未验证的执行顺序。

#### 必须验证

- `?task=A` → `?task=B` 后展示 B。
- 浏览器后退回 A 后展示 A。
- `?task=A` → 无 task 后进入实时模式。
- 历史页面点击启动新扫描不会创建重复轮询或加载旧任务。

---

### ROUND4-S2-003：前端运行时测试未实现

#### 问题现象

上一轮明确要求添加最小化 Vitest 运行时测试，但本提交未修改：

- `web/package.json`
- `web/package-lock.json`
- 任何前端测试文件

执行：

```bash
npm run test
```

实际结果：

```text
npm error Missing script: "test"
```

`npm run build` 通过只能证明模板可编译，不能证明历史任务状态切换正确。

#### 修复建议

最小化引入：

- `vitest`
- `@vue/test-utils`
- `jsdom`

增加：

```json
"test": "vitest run"
```

新增 `web/src/pages/__tests__/ScannerConsole.history-task.test.js`，至少覆盖：

1. 当前运行 S1，打开历史 S2，不能被 S1 覆盖。
2. 当前运行 S2，打开历史 S1，候选请求携带目标 task_id。
3. 跟踪任务完成后，从 task summary 恢复最终统计和失败列表。
4. 历史任务完成时不因 `/api/scan/status` 返回 task_id=null 而跳过最终刷新。
5. query 从任务 A 切换到 B。
6. 不存在任务显示明确错误。
7. 历史 S2 不显示策略1重试按钮。

测试必须 mount 真实 `ScannerConsole.vue`，mock API 和 router；不能只测试独立辅助函数。

---

### ROUND4-S2-004：设计文档仍与实际业务规则冲突

#### 问题现象

以下文件没有在本提交中修改：

- `docs/superpowers/specs/2026-06-10-strategy2-extreme-dry-stable-design.md`
- `scanner/daily_data_service.py`

仍包含：

- “四数据源”
- “百度、新浪、腾讯、yfinance”
- “四数据源均失败时允许使用新鲜缓存”
- “数据源全部失败且无新鲜缓存时才失败”
- 共享日线服务为“四数据源链”

这与用户确认的规则冲突：

> 生产源仅 baidu/sina/tencent；全部在线源失败时直接标记失败，不使用缓存。

#### 影响

后续 AI 或开发者可能依据当前主设计文档重新引入 yfinance 或缓存兜底。

#### 修复建议

更新 Strategy2 主设计文档中的所有现行规则：

- 四数据源 → 三数据源。
- 删除 yfinance 作为正式源。
- 全部失败使用新鲜缓存 → 全部在线源失败直接标记失败，不使用缓存扫描。
- 日线缓存只用于成功在线拉取后的历史合并/持久化，不作为全源失败兜底。

更新 `scanner/daily_data_service.py` 顶部注释：

```python
"""共享日线数据拉取服务 — 从三数据源链逐级拉取、合并历史数据并入库。

全部在线数据源失败时返回 data=None，不使用本地缓存继续扫描。
"""
```

不要求改写历史归档设计文档，但当前 Strategy2 主设计文档必须与现状一致。

---

### ROUND4-S2-005：数据源诊断行为缺少精确回归断言

#### 问题现象

代码已正确保存：

- primary/fallback source
- primary/fallback attempts
- primary/fallback error
- source_errors

直接复现确认字段正确。

但新增六终态测试仅构造这些字段，没有断言数据库最终保存的字段；也没有覆盖：

- 数据源 busy 超限诊断。
- `fetch_with_retry()` 直接抛异常且 `fetch_result=None`。
- 成功获取后 scanned/skipped/candidate 保存源诊断。

#### 修复建议

补充三个小型测试：

1. `ALL_DATA_SOURCES_FAILED` 精确断言全部诊断字段和 JSON。
2. busy 超限断言状态、原因和诊断。
3. `fetch_with_retry` 直接抛异常，断言最终为 `STRATEGY2_EVALUATION_ERROR` 且没有 `UnboundLocalError`。

在六终态的 candidate 场景中，必须显式断言：

```python
assert row["status_reason"] is None
```

当前测试在 expected_reason 为 None 时跳过原因断言。

---

## 5. 建议修复顺序

1. 扩展任务股票接口返回 summary。
2. 重构 ScannerConsole 的完成态恢复与 pollStatus 顺序。
3. 增加 query task watcher。
4. 添加 Vitest 运行时测试，先证明上述前端行为。
5. 补充源诊断测试。
6. 同步 Strategy2 主设计文档与共享服务注释。
7. 执行完整验收门禁。

---

## 6. 给修复 AI 的执行要求

1. 不修改策略算法、评分和候选规则。
2. 不恢复缓存兜底、mootdx 或 yfinance。
3. 不改变现有 `total` 字段的分页语义；新增独立 `summary`。
4. 不以“保留上一次轮询数字”代替从数据库恢复最终精确 summary。
5. 不只补测试，必须先修复真实前端完成态。
6. 前端测试必须 mount 真实组件。
7. 不重构无关页面和后端接口。

---

## 7. 回归测试清单

- 不存在任务股票接口返回 404。
- 合法任务返回 strategy_type、失败分页 total 和完整 summary。
- 实时扫描完成后最终统计不归零。
- 历史运行任务完成后刷新最终候选和失败列表。
- query task A/B 切换正确。
- 历史 S2 不显示重试按钮。
- 全源失败保存完整诊断且不使用缓存。
- busy 超限保存诊断。
- 默认全量测试无网络失败和线程 warning。
- `npm run test` 与 `npm run build` 均通过。
- Strategy2 主设计文档只描述三源和全源失败直接失败。

---

## 8. 不建议修改的内容

- 不要修改策略2计算模块。
- 不要修改策略1评分和扫描结果。
- 不要恢复已删除的数据源文件。
- 不要删除失败股票面板。
- 不要调整整体 UI 样式。
- 不要新建另一套任务状态存储。

---

## 9. 最终交付标准

1. 扫描完成后的最终统计来自目标任务数据库 summary。
2. 历史任务从运行转完成后结果完整刷新。
3. URL task 变化后页面上下文同步变化。
4. 前端运行时测试真实存在并通过。
5. 数据源诊断有精确测试保护。
6. 主设计文档与三源/不使用缓存规则一致。
7. 后端全量、前端测试、构建、compileall 和 diff check 全部通过。

---

## 10. 本轮验证结果

```text
重点后端回归：
57 passed

六终态：
6 passed

线程 warning 门禁：
17 passed，0 warning

默认全量：
422 passed

compileall：
通过

前端 build：
通过

前端 test：
失败，Missing script: "test"

API 404：
通过

完整数据源失败诊断：
直接复现通过

完成态复现：
运行中返回完整 task_id/stats；
完成后返回 task_id=null、stats={}；
前端当前逻辑会归零或提前返回。

diff check：
通过
```

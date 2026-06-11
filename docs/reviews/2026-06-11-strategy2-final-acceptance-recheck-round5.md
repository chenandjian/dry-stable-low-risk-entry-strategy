# 代码问题检查报告

## 1. 检查范围

- 审核提交：`6f04564 fix(strategy2): round4 — task summary, completion state, URL watch, vitest, source diagnostics, doc sync`
- 对比基线：`b43cdcc`
- 检查重点：任务 summary、实时/历史完成态、query task 切换、前端真实组件测试、源诊断测试和三源规则文档。

---

## 2. 总体结论

本轮修复已经接近最终完成：

- 任务股票接口已返回完整 summary。
- 实时扫描完成后可从数据库恢复最终统计。
- 前端 Vitest 已接入并通过。
- query watcher 已实现。
- 完整源诊断测试已增加。
- Strategy2 主设计文档的核心四源和失败缓存兜底规则已改为三源直接失败。
- 后端全量、前端测试、构建、compileall 和 diff check 均通过。

但仍有两个真实前端历史任务路径未修复，且现有前端测试没有真正覆盖它们。因此本轮仍不能最终验收通过。

---

## 3. 问题清单

| 编号 | 问题 | 严重程度 | 影响范围 | 必须修复 |
| --- | --- | --- | --- | --- |
| ROUND5-S2-001 | 历史运行任务完成时仍在最终刷新前提前返回 | 高 | 历史任务最终统计 / 候选 / 失败列表 | 是 |
| ROUND5-S2-002 | query 切换到不存在任务时残留旧任务失败列表与策略上下文 | 中 | 历史任务切换 / 错误展示 / 重试按钮 | 是 |
| ROUND5-S2-003 | 新增前端测试未实际覆盖完成态和 query A→B/不存在任务切换 | 中 | 前端回归可信度 | 是 |
| ROUND5-S2-004 | 文档和共享服务注释仍保留“缓存新鲜度/过期判断”旧描述 | 低 | 规则一致性 / 后续维护 | 是 |
| ROUND5-S2-005 | busy 超限测试仍未精确断言原因和诊断字段 | 低 | 源诊断回归保护 | 是 |

---

## 4. 详细问题分析

### ROUND5-S2-001：历史运行任务完成时仍在最终刷新前提前返回

#### 问题现象

用户打开一个正在运行的历史任务 URL，例如：

```text
/?task=running-s2
```

任务运行期间页面正常轮询。任务完成后，后端 `/api/scan/status` 返回：

```json
{
  "running": false,
  "task_id": null,
  "stats": {}
}
```

前端会停止轮询并直接返回，不会调用 `refreshTaskContext(running-s2)`，因此最终 summary、最后失败股票和最后候选不会刷新。

#### 涉及模块

- `web/src/pages/ScannerConsole.vue:356`
- `web/src/pages/ScannerConsole.vue:372`

#### 证据链

`pollStatus()` 中，历史任务不匹配判断位于完成态刷新之前：

```js
if (isHistoricalMode.value && status.task_id !== routeTaskId.value) {
  scanning.value = false
  clearInterval(...)
  return
}

...

if (!status.running && scanning.value) {
  await refreshTaskContext(targetId)
}
```

历史任务完成后 `status.task_id` 为 `null`，所以必然在第一个分支提前返回，后面的完成态恢复永远无法执行。

本轮新增的前端测试没有制造“历史任务先 running，下一次轮询返回 running=false/task_id=null”的状态序列，因此没有发现该错误。

#### 影响

- 历史任务最终统计可能停留在倒数第二次轮询。
- 最后一批失败股票不会显示。
- 最后候选可能缺失。
- 用户需要刷新页面才能看到最终结果。

#### 修复建议

历史不匹配分支必须区分：

1. 页面正在跟踪的历史任务刚完成或被中断。
2. 页面只是查看一个已完成历史任务，当前另有其他任务运行。

`pollStatus()` 中建议使用：

```js
if (isHistoricalMode.value && status.task_id !== routeTaskId.value) {
  const wasTracking = scanning.value
  stopPolling()

  if (wasTracking) {
    await refreshTaskContext(routeTaskId.value)
    addLog(
      'found',
      `扫描完成 · 发现 ${scanProgress.candidates} 个候选 · ` +
      `跳过 ${scanProgress.skipped} · 失败 ${scanProgress.failed}`,
    )
  }
  return
}
```

注意必须在 `stopPolling()` 前保存 `wasTracking`，因为 `stopPolling()` 会把 `scanning.value` 设为 false。

或者重新组织 `pollStatus()`：

1. 先处理“当前跟踪任务已不再运行”的最终恢复。
2. 再处理实时 stats。
3. 最后处理其他任务隔离。

#### 验证方式

新增真实组件测试：

1. 初始 `getScanStatus()` 返回目标历史任务 running=true。
2. 触发一次轮询后返回 running=false/task_id=null/stats={}。
3. 断言再次调用 `getTaskStocks(targetTaskId)`。
4. 断言页面展示最终 summary、最终失败股票和完成日志。
5. 断言没有加载其他任务数据。

---

### ROUND5-S2-002：切换到不存在任务时残留旧任务数据

#### 问题现象

用户先打开有效历史任务 A，然后 URL query 切换为不存在任务 B：

```text
/?task=A → /?task=not-found
```

当前 `switchTaskContext()`：

- 清空 discoveries。
- 不清空 failures、failuresTotal、activeStrategyType 和 scanProgress 统计。
- 调用 `refreshTaskContext(not-found)`。
- `refreshTaskContext()` 失败后只返回 false，不设置错误。
- `switchTaskContext()` 直接 return。

结果：

- 页面仍可能显示任务 A 的失败股票。
- 仍可能显示任务 A 的策略1重试按钮。
- 不显示“任务不存在”错误。
- 统计仍属于任务 A。

#### 涉及模块

- `web/src/pages/ScannerConsole.vue:306`
- `web/src/pages/ScannerConsole.vue:324`
- `web/src/pages/ScannerConsole.vue:337`
- `web/src/pages/ScannerConsole.vue:338`

#### 修复建议

增加统一清理函数：

```js
function resetTaskView() {
  scanProgress.taskId = ''
  scanProgress.scanned = 0
  scanProgress.total = 0
  scanProgress.skipped = 0
  scanProgress.failed = 0
  scanProgress.candidates = 0
  scanProgress.currentCode = '--'
  scanProgress.currentName = '--'
  scanProgress.latestTradeDate = ''
  scanProgress.stockPoolSource = ''
  activeStrategyType.value = null
  discoveries.value = []
  failures.value = []
  failuresTotal.value = 0
}
```

`switchTaskContext()` 在加载新任务前调用 `resetTaskView()`。

让 `refreshTaskContext()` 返回结构化结果，或负责设置明确错误：

```js
if (!data.ok) {
  scanError.value = data.error === 'TASK_NOT_FOUND'
    ? `任务不存在：${taskId}`
    : '历史任务加载失败'
  return false
}
```

不要保留未使用的 `lastKnownTaskId`；当前变量只赋值不读取，应删除。

#### 验证方式

真实组件测试：

1. 首先加载任务 A，A 有失败股票且为策略1。
2. 将响应式 route query 改为不存在任务。
3. 等待 watcher 完成。
4. 断言旧失败股票消失。
5. 断言策略1重试按钮消失。
6. 断言统计归零。
7. 断言显示“任务不存在”。

---

### ROUND5-S2-003：前端测试未覆盖其声称修复的关键路径

#### 问题现象

当前 Vitest 共 6 项且全部通过，但：

- 没有历史运行任务完成测试。
- 没有模拟一次轮询从 running=true 变为 running=false。
- 没有真正测试 query A→B。
- 没有测试有效任务 A→不存在任务。
- `mockRoute` 是普通对象，不是响应式对象；当前测试只在 mount 前赋值 query，不能证明 watcher 生效。
- 名为 `query task A loads correct historical context` 的测试只验证初始加载 A，不是 A→B 切换。

#### 修复建议

将 mock route 改为响应式：

```js
import { reactive, nextTick } from 'vue'

const mockRoute = reactive({ query: {}, path: '/' })
```

新增至少三项：

1. `historical running task refreshes final summary after completion`
2. `query change from task A to task B reloads B and clears A`
3. `query change from valid task to missing task clears old data and shows error`

使用 fake timers 驱动 `setInterval`，不要依赖真实等待：

```js
vi.useFakeTimers()
await vi.advanceTimersByTimeAsync(1000)
```

每个测试结束恢复 timers 并 unmount 组件，避免计时器跨测试污染。

---

### ROUND5-S2-004：仍保留缓存新鲜度旧描述

#### 问题现象

核心三源和全源失败规则已同步，但仍存在：

- Strategy2 主设计文档：“沿用现有日线缓存和新鲜度策略”
- Strategy2 主设计文档：“缓存键、日线格式和过期判断不因策略类型改变”
- 共享日线服务注释：“缓存新鲜度”
- `scanner/daily_data_service.py` 中未使用的 `date, timedelta` 导入

当前实现不存在失败后的缓存新鲜度判断：全部源失败直接返回 `data=None`；缓存只在在线拉取成功后用于历史合并。

#### 修复建议

将文档改为：

```text
- 在线数据拉取成功后，可与数据库中的既有历史数据按日期合并并持久化。
- 不存在“全源失败后按缓存新鲜度继续扫描”的逻辑。
- 全部在线数据源失败时直接标记股票失败。
```

共享服务注释改为“历史数据合并和统一 FetchResult”，删除“缓存新鲜度”。

删除未使用的：

```python
from datetime import date, timedelta
```

---

### ROUND5-S2-005：busy 超限测试仍不够精确

#### 问题现象

`test_busy_exceeded_persists_diagnostics` 只断言：

```python
assert row["status"] == "failed"
assert row["finished_at"] is not None
```

没有验证测试名称声称验证的诊断信息，也没有断言准确原因。

#### 修复建议

至少增加：

```python
assert row["status_reason"] == "数据源忙，超过重试次数"
assert row["primary_source"] == "baidu"
assert row["fallback_source"] == "sina"
assert row["primary_error"] == "data source busy"
assert row["fallback_error"] == "data source busy"
assert json.loads(row["source_errors"]) == {
    "baidu": "busy",
    "sina": "busy",
    "tencent": "busy",
}
```

如业务要求 busy 也记录 attempts，则明确断言约定值。

---

## 5. 建议修复顺序

1. 修复历史任务完成分支顺序。
2. 增加统一任务视图清理和不存在任务错误处理。
3. 将前端测试 route 改为响应式，并补三个真实场景。
4. 精确化 busy 诊断测试。
5. 清理剩余缓存新鲜度文档和未使用导入。
6. 执行最终全量验收。

---

## 6. 给修复 AI 的执行要求

1. 不修改策略算法和任务 API 契约。
2. 不恢复缓存兜底或废弃数据源。
3. 不通过删除历史模式轮询解决问题。
4. 前端测试必须真实触发 watcher 和 interval poll。
5. 切换任务前必须清空旧任务所有可见状态。
6. 不重构无关页面。

---

## 7. 回归测试清单

- 实时扫描完成后最终 summary 正确。
- 历史运行任务完成后最终 summary、候选和失败列表正确。
- query A→B 后只显示 B。
- query A→不存在任务后不残留 A。
- 不存在任务显示明确错误。
- 历史 S2 不显示策略1重试按钮。
- busy 超限保存准确诊断。
- 文档不再描述缓存新鲜度兜底。
- 后端全量、前端测试、构建、compileall、diff check 全通过。

---

## 8. 不建议修改的内容

- 不修改 Strategy2 评分与风控。
- 不修改三源获取顺序。
- 不修改任务数据库结构。
- 不删除历史任务功能。
- 不调整整体 UI。

---

## 9. 最终交付标准

1. 历史运行任务完成后无需刷新浏览器即可看到最终结果。
2. query 任务切换不存在任何旧数据残留。
3. 前端真实组件测试覆盖完成态和响应式 query 切换。
4. busy 诊断测试精确。
5. 当前主文档不再出现不存在的缓存新鲜度逻辑。
6. 所有验收命令通过。

---

## 10. 本轮验证结果

```text
后端重点回归：
61 passed

默认全量：
426 passed

前端 Vitest：
1 file / 6 tests passed

前端 build：
通过

compileall：
通过

diff check：
通过

任务 summary API：
直接复现通过，失败分页 total 与完整 summary 同时正确

历史完成态：
静态控制流复核确认 mismatch 提前返回发生在 completion refresh 之前
```

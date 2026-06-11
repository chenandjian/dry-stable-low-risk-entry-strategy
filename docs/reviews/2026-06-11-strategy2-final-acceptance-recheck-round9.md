# 代码问题检查报告

## 1. 检查范围

- 审核分支：`codex/strategy2-extreme-dry-stable-design`
- 代码审核基线：`ba85084 fix(strategy2): round8 — single-flight poll session, 17 vitest tests, review guide update`
- 当前 HEAD：`a08caae docs: update final third-party review guide — Round 8, 17 vitest, 426 backend`
- 生产代码重点文件：`web/src/pages/ScannerConsole.vue`
- 按用户要求，本报告过滤低等级问题。

核对结果：

- `a08caae` 相对 `ba85084` 只修改审核文档。
- `web/src/pages/ScannerConsole.vue` 在 `ba85084..a08caae` 之间没有变化。
- 因此，本轮实际验收的生产代码状态就是 `ba85084` 中的 `ScannerConsole.vue`。
- 测试覆盖不足不再单独列为项目问题，只作为生产问题的修复验收要求。

---

## 2. 总体结论

本轮验收仍不能通过。

`ba85084` 在 `ScannerConsole.vue` 中引入 single-flight poll session 后，正常完成流程会先调用 `stopPolling()`。该函数立即执行 `resetPollSession()`，使当前正在执行的 `pollStatus()` 所持有的 `session` 失效。

完成流程随后继续检查：

```js
isCurrentPollSession(session)
```

该检查必然失败，导致 live 扫描完成时跳过最终失败股票刷新和完成日志；历史运行任务完成时跳过完成日志。

这是当前唯一需要阻止验收的中/高等级生产代码问题。

---

## 3. 问题清单

| 编号 | 问题 | 严重程度 | 影响范围 | 是否必须修复 |
| --- | --- | --- | --- | --- |
| ROUND9-S2-001 | 正常完成流程提前失效当前 poll session，导致终态刷新不完整 | 高 | `ScannerConsole.vue`、最终失败股票展示、完成日志、终态一致性 | 是 |

---

## 4. 详细问题分析

### ROUND9-S2-001：正常完成流程提前失效当前 poll session

#### 问题位置

涉及 `web/src/pages/ScannerConsole.vue`：

- `resetPollSession()`
- `isCurrentPollSession()`
- `stopPolling()`
- `pollStatus()`
- `loadResults()`
- `loadFailures()`

#### 证据链

`pollStatus()` 开始执行时保存当前 session：

```js
const session = activePollSession
if (session.inFlight) return
session.inFlight = true
```

`stopPolling()` 不仅清除 timer，还会替换当前 session：

```js
function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  resetPollSession()
  scanning.value = false
}
```

`resetPollSession()` 创建新对象：

```js
function resetPollSession() {
  activePollSession = {
    epoch: activePollSession.epoch + 1,
    inFlight: false,
  }
  return activePollSession
}
```

`isCurrentPollSession()` 使用对象身份判断：

```js
function isCurrentPollSession(session) {
  return session === activePollSession
}
```

所以在同一次 `pollStatus()` 内调用 `stopPolling()` 后：

```js
isCurrentPollSession(session)
```

必然为 `false`。

#### 触发路径一：live 扫描正常完成

当前代码：

```js
if (!status.running && scanning.value) {
  stopPolling()
  if (context.taskId) {
    ...
  } else {
    await loadResults({
      taskId: scanProgress.taskId,
      strategyType: activeStrategyType.value,
      context,
      pollSession: session,
    })
    if (!isCurrentViewContext(context) || !isCurrentPollSession(session)) return

    await loadFailures({
      taskId: scanProgress.taskId,
      context,
      pollSession: session,
    })
    if (!isCurrentViewContext(context) || !isCurrentPollSession(session)) return
  }
  addLog('found', ...)
}
```

实际执行顺序：

1. 状态接口返回 `running=false`。
2. `stopPolling()` 调用 `resetPollSession()`。
3. 当前 `session` 立即失效。
4. `loadResults()` 当前未声明 `pollSession` 参数，因此可能仍更新候选。
5. `loadResults()` 返回后，`isCurrentPollSession(session)` 必然为 `false`。
6. `pollStatus()` 提前返回。
7. `loadFailures()` 不执行。
8. “扫描完成”日志不写入。

用户可见后果：

- 扫描结束时新产生的失败股票不会显示。
- 数据源全部失败的股票可能只体现在失败数量中，失败列表仍是旧数据。
- 页面没有完成日志。
- 候选、失败数量和失败股票列表可能处于不同终态。

#### 触发路径二：历史运行任务正常完成

当前代码：

```js
if (context.taskId && status.task_id !== context.taskId) {
  const wasTracking = scanning.value
  stopPolling()
  if (wasTracking) {
    const ok = await refreshTaskContext(context)
    if (!ok || !isCurrentViewContext(context) || !isCurrentPollSession(session)) return
    addLog('found', ...)
  }
  return
}
```

`refreshTaskContext()` 可以刷新最终 summary、候选和失败列表，但 `stopPolling()` 已经使当前 session 失效，因此后续检查必然提前返回，“扫描完成”日志不会写入。

#### 根本原因

当前将两个不同语义合并在 `stopPolling()` 中：

1. 停止后续 timer tick。
2. 立即作废当前正在执行的异步 poll。

不同场景需要不同处理：

| 场景 | 停止 timer | 立即作废当前 session |
| --- | --- | --- |
| 当前任务正常完成，需要执行最终刷新 | 是 | 否 |
| 用户切换任务 | 是 | 是 |
| 从历史页面切回 live | 是 | 是 |
| 组件卸载 | 是 | 是 |

---

## 5. 一次性修复方案

### 步骤一：拆分 timer 停止和 session 失效

建议实现两个职责明确的函数：

```js
function clearPollTimer() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  scanning.value = false
}

function invalidatePolling() {
  clearPollTimer()
  resetPollSession()
}
```

允许按项目命名风格调整名字，但必须保留语义区分。

### 步骤二：修正调用规则

以下场景调用 `invalidatePolling()`：

- `switchTaskContext()` 开始切换任务时。
- route task 变化导致放弃旧上下文时。
- 组件卸载时。
- 任何明确放弃当前异步结果的场景。

以下场景只调用 `clearPollTimer()`：

- 当前 live 任务正常完成，需要继续执行最终候选、失败列表和日志刷新。
- 当前历史运行任务正常完成，需要继续执行最终详情刷新和完成日志。

### 步骤三：最终刷新结束后再失效 session

建议抽取统一终态收尾函数，避免两个完成分支再次出现不同生命周期：

```js
async function finalizeCompletedPoll({ context, session, historical }) {
  clearPollTimer()

  try {
    if (historical) {
      const ok = await refreshTaskContext(context)
      if (!ok || !isCurrentViewContext(context) || !isCurrentPollSession(session)) {
        return false
      }
    } else {
      const resultsOk = await loadResults({
        taskId: scanProgress.taskId,
        strategyType: activeStrategyType.value,
        context,
        pollSession: session,
      })
      if (!resultsOk || !isCurrentViewContext(context) || !isCurrentPollSession(session)) {
        return false
      }

      const failuresOk = await loadFailures({
        taskId: scanProgress.taskId,
        context,
        pollSession: session,
      })
      if (!failuresOk || !isCurrentViewContext(context) || !isCurrentPollSession(session)) {
        return false
      }
    }

    addLog(
      'found',
      `扫描完成 · 发现 ${scanProgress.candidates} 个候选 · 跳过 ${scanProgress.skipped} · 失败 ${scanProgress.failed}`,
    )
    return true
  } finally {
    if (isCurrentPollSession(session)) {
      resetPollSession()
    }
  }
}
```

可以不完全照抄该结构，但必须保证：

1. 正常完成时先停止后续 timer。
2. 当前 session 在最终刷新完成前保持有效。
3. 每个异步结果写入前验证 context/session。
4. 最终刷新结束后再失效 session。

### 步骤四：为 `loadResults()` 补齐 session 防护

当前调用传入了 `pollSession`，但 `loadResults()` 的参数签名会忽略它：

```js
async function loadResults({ taskId, strategyType, context } = {})
```

修改为：

```js
async function loadResults({ taskId, strategyType, context, pollSession } = {}) {
  const targetTaskId = normalizeTaskId(taskId)
  const targetStrategyType = strategyType || activeStrategyType.value

  try {
    const candidates = await fetchMappedResults(targetTaskId, targetStrategyType)
    if (context && !isCurrentViewContext(context)) return false
    if (pollSession && !isCurrentPollSession(pollSession)) return false

    discoveries.value = dedupeDiscoveries(candidates)
    updateMetrics()
    return true
  } catch (e) {
    if (
      (!context || isCurrentViewContext(context))
      && (!pollSession || isCurrentPollSession(pollSession))
    ) {
      console.error('Load results failed:', e)
    }
    return false
  }
}
```

### 步骤五：组件卸载时失效旧 session

当前 `onUnmounted()` 只清除 timer。建议使用立即失效语义，避免卸载后的 pending poll 继续处理：

```js
onUnmounted(() => {
  invalidatePolling()
  if (clockTimer) clearInterval(clockTimer)
})
```

该项用于保证修复后的生命周期完整，但不单独作为问题项。

---

## 6. 修复时禁止采用的方案

- 不要删除 `isCurrentPollSession()` 校验。
- 不要让 `stopPolling()` 保持模糊语义，并在调用点通过特殊条件绕过。
- 不要通过延长轮询间隔或增加固定 sleep 解决。
- 不要修改 Strategy1 / Strategy2 算法、评分、过滤或风险规则。
- 不要修改后端任务 schema 或数据库。
- 不要重构无关前端模块。

---

## 7. 必须补充的验收测试

测试是 ROUND9-S2-001 的验收要求，不单独作为项目问题。

### 测试一：live 扫描完成后完整刷新终态

必须验证：

1. live 扫描处于 running。
2. 完成前失败列表为空。
3. 状态接口返回 `running=false`。
4. 最终失败接口返回一只 `ALL_DATA_SOURCES_FAILED` 股票。
5. 页面显示最终失败股票。
6. 页面显示最终候选。
7. 页面显示“扫描完成”日志。
8. summary、候选和失败列表一致。

### 测试二：历史运行任务完成后完整刷新

必须验证：

1. 历史任务从 running 变为 completed。
2. 最终 summary 更新。
3. 最终失败列表更新。
4. 最终候选更新。
5. 页面显示“扫描完成”日志。

### 测试三：任务切换仍立即作废旧 session

必须使用 deferred promise 真实构造：

1. 任务 A 的 poll 请求 pending。
2. 切换任务 B。
3. resolve A 的旧响应。
4. A 不得覆盖 B。
5. A 不得停止 B 的轮询。

### 测试四：慢请求保持 single-flight

必须使用 deferred promise 真实构造：

1. poll 请求保持 pending。
2. 推进多个轮询间隔。
3. pending 期间没有新状态请求。
4. resolve 后响应正常应用。
5. 下一轮 timer 才开始新请求。

---

## 8. 给修复 AI 的提示语

```text
请根据 docs/reviews/2026-06-11-strategy2-final-acceptance-recheck-round9.md 修复 ROUND9-S2-001。

代码审核基线是 ba85084。实际影响项目运行的生产文件是：
web/src/pages/ScannerConsole.vue

本轮只修复这一个高等级生产问题，不要修改策略评分、过滤、风险规则、后端 schema 或无关模块。

核心要求：
1. 将“停止后续 poll timer”和“立即失效当前 poll session”拆成两个明确动作。
2. 正常完成流程只能先停止 timer，必须保持当前 session 有效，直到最终候选、最终失败列表和完成日志全部刷新。
3. 任务切换和组件卸载仍必须立即失效旧 session。
4. loadResults 和 loadFailures 在写共享状态前都必须校验 viewContext 和可选 pollSession。
5. 使用真实 deferred promise 补充 live 完成、历史任务完成、旧 poll 迟到和慢请求 single-flight 测试。
6. 不要通过删除 session 校验、增加 sleep 或延长轮询间隔绕过问题。

修复完成后，逐项说明：
- ScannerConsole.vue 修改了哪些函数。
- 正常完成和任务切换分别使用什么 session 生命周期。
- 每个新增测试真实构造了什么异步时序。
- 所有验收命令的实际结果。
```

---

## 9. 回归验证命令

```bash
cd web
npm test -- --run
npm run build

cd ..
python -m pytest tests/test_strategy2_acceptance_fixes.py tests/test_strategy2_final_fixes.py tests/test_strategy2_bug_fixes.py tests/test_strategy2_engine.py tests/test_strategy2_indicators.py tests/test_strategy2_scorer.py tests/test_strategy2_rejection.py tests/test_strategy2_risk.py -q
python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py
python -m pytest tests/test_strategy2_acceptance_fixes.py tests/test_strategy2_final_fixes.py tests/test_strategy2_recheck_fixes.py -W error::pytest.PytestUnhandledThreadExceptionWarning -q
python -m compileall scanner strategy2 server.py -q
git diff --check
git status --short
```

---

## 10. 本轮已执行验证

| 验证项 | 结果 |
| --- | --- |
| `npm.cmd test -- --run` | 17 passed |
| `npm.cmd run build` | 通过 |
| Strategy2 聚焦后端测试 | 176 passed |
| 后端离线全量测试 | 426 passed |
| 线程异常 warning 门禁 | 61 passed |
| `python -m compileall scanner strategy2 server.py -q` | 通过 |
| `git diff --check` | 通过 |

现有测试与构建虽然通过，但未覆盖 `stopPolling()` 在正常完成分支中提前失效当前 session 的执行路径。该问题可以由 `ScannerConsole.vue` 的控制流直接证明。

---

## 11. 最终交付标准

只有同时满足以下条件，才能最终验收：

1. live 扫描完成后最终失败股票和完成日志稳定显示。
2. 历史运行任务完成后 summary、候选、失败列表和完成日志一致。
3. 正常完成流程不会提前失效当前 poll session。
4. 任务切换和组件卸载仍能立即阻止旧响应写入。
5. `loadResults()` 和 `loadFailures()` 均受 context/session 防护。
6. 第 7 节四类异步场景均有真实测试。
7. 第 9 节所有验证命令全部通过。

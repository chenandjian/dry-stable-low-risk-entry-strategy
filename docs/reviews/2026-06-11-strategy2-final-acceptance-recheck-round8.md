# 代码问题检查报告

## 1. 检查范围

- 审核分支：`codex/strategy2-extreme-dry-stable-design`
- 审核提交：`0e777c5 fix(strategy2): round7 — viewContext stale response prevention, poll epoch, vitest race tests`
- 对比基线：`fc00da2`
- 本轮检查重点：
  - Round7 `viewContext` 是否真实阻止旧响应覆盖新任务
  - `pollRequestEpoch` 是否能安全处理慢请求和重叠轮询
  - Round7 声称新增的竞态测试是否真实构造对应竞态
  - 历史任务 summary、状态查询错误和失败列表行为
  - Strategy2 算法、三数据源和全源失败规则是否回归

---

## 2. 总体结论

Round7 的主要方向正确：

- 历史任务 A 的迟到详情响应无法再覆盖任务 B。
- 历史任务详情、候选和失败列表开始使用明确 context。
- 已完成历史任务 summary 改为精确断言。
- 历史状态查询异常会保留已加载结果。
- Strategy1 / Strategy2 算法和后端链路本轮未修改。

但当前仍不能最终验收通过。

`pollRequestEpoch` 的实现存在新的高风险问题：每次轮询开始都会立即使上一次轮询失效。如果状态接口持续耗时超过轮询间隔，上一次响应总会在返回前被下一次轮询判旧，页面可能永久收不到任何进度更新。

同时，Round7 文档要求的关键竞态测试没有真实实现：所谓“历史任务慢响应切回 live”测试中的 deferred 请求实际没有被调用；旧轮询迟到测试完全缺失；运行任务完成刷新测试也被删除。当前 11 个测试全部通过，不能证明轮询方案正确。

---

## 3. 问题清单

| 编号 | 问题 | 严重程度 | 影响范围 | 是否必须修复 |
| --- | --- | --- | --- | --- |
| ROUND8-S2-001 | `pollRequestEpoch` 会在状态接口慢于轮询间隔时饿死全部进度响应 | 高 | 实时扫描进度、完成状态、失败列表、候选刷新 | 是 |
| ROUND8-S2-002 | Round7 关键竞态测试未真实覆盖，且删除了运行→完成等回归测试 | 高 | 前端回归可信度、跨任务隔离 | 是 |
| ROUND8-S2-003 | `loadMoreFailures()` 移除异常处理，请求失败会产生未处理 rejection | 中 | 失败股票分页、用户错误提示、控制台异常 | 是 |
| ROUND8-S2-004 | 最终第三方审核指南仍停留在 Round6 / `fc00da2`，与当前交付不一致 | 低 | 交付审计、第三方验收 | 是 |

---

## 4. 详细问题分析

### ROUND8-S2-001：轮询序号方案会饿死慢响应

#### 问题现象

当前页面每秒执行一次 `pollStatus()`：

```js
pollTimer = setInterval(pollStatus, 1000)
```

每次进入 `pollStatus()` 都立即递增全局 `pollRequestEpoch`：

```js
const requestEpoch = ++pollRequestEpoch
```

响应返回后只有仍是最新 epoch 才允许处理：

```js
if (requestEpoch !== pollRequestEpoch) return
```

如果 `/api/scan/status` 每次耗时超过 1 秒，就会出现：

```text
t=0s   poll-1 开始，epoch=1
t=1s   poll-2 开始，epoch=2
t=1.5s poll-1 返回，因为 1 != 2 被丢弃
t=2s   poll-3 开始，epoch=3
t=2.5s poll-2 返回，因为 2 != 3 被丢弃
...
```

只要接口持续慢于轮询间隔，每个响应都会被下一次请求提前作废，页面可能永久不更新。

#### 涉及模块

- `web/src/pages/ScannerConsole.vue:390`
- `web/src/pages/ScannerConsole.vue:426`
- `web/src/pages/ScannerConsole.vue:428`
- `web/src/pages/ScannerConsole.vue:432`

#### 影响

- 扫描页面长期停留在旧进度。
- 任务已经完成，但前端仍显示扫描中。
- 失败股票、候选和完成日志无法刷新。
- 状态接口越慢，请求越多，进一步增加后端压力。

#### 额外不完整点

即使状态响应通过 epoch 校验，轮询末尾的：

```js
await loadFailures({ taskId: scanProgress.taskId, context })
```

只校验 view context，不校验轮询请求是否仍是最新。较早轮询发出的失败列表请求仍可能晚于较新轮询返回并覆盖失败列表。

因此当前方案同时存在：

- 慢请求被连续饿死。
- 后续异步请求没有完整遵守 poll epoch。

#### 一次性修复方案

不要在每次轮询开始时抢占并作废上一次轮询。改成**单飞轮询 session**：同一个页面上下文同一时间只允许一个状态请求；任务切换或停止轮询时替换整个 session，使旧请求自然失效。

建议增加：

```js
let activePollSession = {
  epoch: 0,
  inFlight: false,
}

function resetPollSession() {
  activePollSession = {
    epoch: activePollSession.epoch + 1,
    inFlight: false,
  }
  return activePollSession
}

function isCurrentPollSession(session) {
  return session === activePollSession
}
```

修改 `stopPolling()`：

```js
function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  resetPollSession()
  scanning.value = false
}
```

修改 `beginViewContext()`：

```js
function beginViewContext(taskId) {
  viewContextEpoch += 1
  resetPollSession()
  activeViewContext = {
    epoch: viewContextEpoch,
    taskId: normalizeTaskId(taskId),
  }
  return { ...activeViewContext }
}
```

修改 `pollStatus()`：

```js
async function pollStatus() {
  const context = captureCurrentViewContext()
  const session = activePollSession

  if (session.inFlight) return
  session.inFlight = true

  try {
    const status = await getScanStatus()
    if (!isCurrentViewContext(context)) return
    if (!isCurrentPollSession(session)) return

    // 原有状态处理逻辑。
    // 每个额外 await 后同时校验 context 和 session。
  } catch (e) {
    if (isCurrentViewContext(context) && isCurrentPollSession(session)) {
      scanError.value = '状态查询失败'
      console.error(e)
    }
  } finally {
    if (isCurrentPollSession(session)) {
      session.inFlight = false
    }
  }
}
```

每个轮询内部额外 `await` 后都必须同时检查：

```js
if (!isCurrentViewContext(context) || !isCurrentPollSession(session)) return
```

包括：

- `refreshTaskContext()`
- `loadResults()`
- `loadFailures()`

推荐让 `loadFailures()` 接收可选 `pollSession`，在提交失败列表前同时验证：

```js
async function loadFailures({ taskId, context, pollSession } = {}) {
  ...
  if (context && !isCurrentViewContext(context)) return false
  if (pollSession && !isCurrentPollSession(pollSession)) return false
  ...
}
```

不要使用以下方案：

- 将轮询间隔简单改大。
- 增加固定延迟。
- 保留“每次新请求立即作废旧请求”的 epoch 逻辑。
- 允许同一个 context 内无限重叠状态请求。

#### 验证方式

新增“慢状态接口”测试：

1. 打开运行任务并启动轮询。
2. 第一次 `getScanStatus()` 保持 pending。
3. 推进 fake timer 3 秒。
4. 断言 pending 期间没有发出第二个状态请求。
5. resolve 第一次状态请求。
6. 断言页面应用该响应，不会因计时器推进而丢弃。
7. 再推进 1 秒，断言下一次轮询才开始。

新增“旧 session 迟到”测试：

1. 任务 A 的轮询请求 pending。
2. 切换任务 B，创建新 poll session。
3. B 正常显示。
4. resolve A 的旧轮询响应。
5. A 不得覆盖 B，也不得停止 B 的轮询。

---

### ROUND8-S2-002：关键测试没有真实覆盖声称场景

#### 问题一：live 竞态测试中的 deferred 请求没有被调用

测试：

```text
late task B response after switching to live mode does not overwrite live
```

先完整加载了任务 B，然后才执行：

```js
mockApi.getTaskStocks.mockImplementation(() => taskBDeferred.promise)
mockRoute.query = {}
```

切换 live 后，`loadLiveTask()` 首先调用 `getScanStatus()`。此时默认响应是：

```js
{ running: false, task_id: null, stats: {} }
```

因此 live 路径不会调用 `getTaskStocks()`，`taskBDeferred.promise` 实际没有被任何在途旧 B 请求使用。后续 resolve 的只是一个无人等待的 Promise。

测试中还声明了未使用变量：

```js
const s2CandBDeferred = deferred()
```

这进一步证明测试没有构造候选迟到响应。

当前测试只证明“切换 live 会清空 B”，不能证明“B 的迟到响应不能覆盖 live”。

#### 问题二：旧轮询迟到测试完全缺失

Round7 文档明确要求：

```text
旧轮询响应不得覆盖新任务
```

当前测试文件没有：

- `vi.advanceTimersByTimeAsync(...)`
- pending 的轮询 `getScanStatus()`
- A 轮询 pending → 切换 B → A 返回的场景

因此 `pollRequestEpoch` 的高风险问题未被发现。

#### 问题三：运行→完成测试被删除

Round6 已存在的：

```text
historical running task refreshes final summary after completion
```

在 Round7 中被删除，没有等价测试替代。

当前测试无法证明：

- 运行中的历史任务会启动轮询。
- 任务完成后会重新读取最终 summary。
- 页面从 `processed=80` 更新为 `processed=100`。
- 完成日志只出现一次。

#### 问题四：状态查询错误测试没有断言错误提示

测试名称是：

```text
status query failure preserves loaded historical data
```

但只断言历史数据保留，没有断言需求规定的提示：

```text
任务状态查询失败，已显示最近保存结果
```

测试注释甚至明确跳过该要求：

```js
// Status query error is logged
// Core requirement: data preserved, no crash
```

#### 问题五：测试数量不符合明确交付要求

Round7 文档要求至少：

```text
1 file / 15 tests passed
```

当前仍为：

```text
1 file / 11 tests passed
```

且通过删除旧测试保持数量不变，不能视为完成 Round7 测试要求。

#### 一次性修复要求

必须补齐并真实实现以下测试：

1. 慢状态接口不会被轮询饿死。
2. 旧任务 A 的在途轮询返回后不能覆盖任务 B。
3. 历史任务 B 的详情请求 pending 时切回 live，B 返回后不能覆盖 live。
4. 历史任务 B 的候选请求 pending 时切回 live，B 候选返回后不能覆盖 live。
5. 历史运行任务从 `80/100` 更新到最终 `100/100`。
6. 状态查询失败时精确显示错误提示并保留数据。
7. 有效任务 A→有效任务 B 顺序切换。
8. 有效任务→不存在任务会清理旧状态。

测试必须先证明 deferred Promise 已实际被调用，例如：

```js
expect(mockApi.getTaskStocks).toHaveBeenCalledWith('task-b', expect.any(Object))
```

然后才允许 resolve 并断言迟到响应无效。

禁止：

- 创建 deferred 但不验证它已被调用。
- 只断言页面没有旧数据，却没有证明旧请求曾经 pending。
- 使用 smoke test 替代具体业务断言。

---

### ROUND8-S2-003：加载更多失败股票缺少异常处理

#### 问题现象

Round7 将原有 `loadMoreFailures()` 的 `try/catch` 删除，当前代码直接 await：

```js
const data = await getTaskStocks(...)
```

如果网络中断或后端不可用，点击“加载更多”会产生未处理 Promise rejection，页面没有错误提示。

#### 涉及模块

- `web/src/pages/ScannerConsole.vue:501`
- `web/src/pages/ScannerConsole.vue:506`

#### 修复建议

恢复异常处理，同时保留 context 防护：

```js
async function loadMoreFailures() {
  const context = captureCurrentViewContext()
  const taskId = scanProgress.taskId
  if (!taskId) return

  try {
    const nextPage = Math.floor(failures.value.length / 50) + 1
    const data = await getTaskStocks(taskId, {
      status: 'failed',
      page_size: 50,
      page: nextPage,
    })

    if (!isCurrentViewContext(context) || scanProgress.taskId !== taskId) return
    if (!data.ok) {
      scanError.value = '加载更多失败股票失败'
      return
    }

    if (data.stocks?.length) {
      failures.value = [...failures.value, ...data.stocks]
    }
    failuresTotal.value = data.total || failuresTotal.value
  } catch (e) {
    if (isCurrentViewContext(context) && scanProgress.taskId === taskId) {
      scanError.value = '加载更多失败股票失败'
      console.error('Load more failures failed:', e)
    }
  }
}
```

补充测试：

- 加载更多请求 reject 时显示错误提示。
- 请求 pending 时切换任务，迟到响应不追加到新任务。

---

### ROUND8-S2-004：最终第三方审核指南未更新

#### 问题现象

本次提交新增：

```text
docs/reviews/2026-06-11-strategy2-final-third-party-review-guide.md
```

但文档仍写：

- 当前提交链只到 `fc00da2`。
- 历经 6 轮修复。
- 前端测试为 11 个。
- 审核基线结束于 `fc00da2`。
- 声称“当前已完成全部交付”。

实际当前提交为：

```text
0e777c5
```

且本轮验收仍发现必须修复的问题。

#### 修复建议

在代码修复和全部验收完成后更新指南：

- 提交链加入 Round7 和本次最终修复提交。
- 更新轮次数量。
- 更新真实 Vitest 数量和构建结果。
- 更新审核基线。
- 只有所有问题关闭后才能写“完成全部交付”。

---

## 5. 已确认修复完成

- 历史任务 A 的迟到详情响应无法覆盖任务 B。
- `refreshTaskContext()` 会在详情响应后校验 view context。
- 候选加载使用显式 taskId 和 strategyType。
- 已完成历史任务 summary 有精确字段断言。
- 历史状态查询异常会保留已加载 summary 和失败列表。
- `handleRetryFailed()` 增加了任务 context 防护。
- Strategy2 核心算法本轮未修改。
- 三数据源仍为 `baidu`、`sina`、`tencent`。
- 全源失败仍直接标记失败，不使用缓存扫描。

---

## 6. 建议修复顺序

1. 将抢占式 `pollRequestEpoch` 改为单飞 poll session。
2. 确保轮询内部每个额外 await 后同时校验 view context 和 poll session。
3. 恢复 `loadMoreFailures()` 异常处理。
4. 修复 live 迟到响应测试，使 deferred 请求真实在途。
5. 新增旧轮询迟到和慢状态接口测试。
6. 恢复运行→完成、A→B、有效→不存在任务测试。
7. 强化状态查询错误提示断言。
8. 更新最终第三方审核指南。
9. 执行全部验收门禁。

---

## 7. 给修复 AI 的执行要求

1. 只修改 `ScannerConsole.vue`、对应 Vitest 和最终审核指南。
2. 不修改 Strategy1 / Strategy2 算法。
3. 不修改数据库结构、后端 API 或数据源规则。
4. 必须使用单飞轮询；同一 poll session 同时最多一个状态请求。
5. 任务切换和停止轮询必须使旧 poll session 失效。
6. 不得通过加大轮询间隔、固定延迟或删除轮询解决问题。
7. 每个新增竞态测试必须证明 deferred 请求真实处于 pending 状态。
8. 不得删除已有关键业务测试换取测试通过。
9. 最终 Vitest 至少 17 个测试；如果合并场景，必须逐项说明覆盖关系。
10. 全部命令通过前不得宣称完成。

---

## 8. 回归测试清单

- 状态接口耗时超过 1 秒时，页面仍能应用响应。
- 慢状态接口 pending 时不会发起重叠轮询。
- 旧任务轮询迟到后不能覆盖新任务。
- 旧任务轮询迟到后不能停止新任务轮询。
- 历史详情迟到后不能覆盖 live。
- 历史候选迟到后不能覆盖 live。
- 历史运行任务完成后更新最终 summary。
- 已完成历史任务首次打开显示真实 summary。
- 状态查询失败时保留历史结果并显示明确提示。
- 加载更多失败股票异常时显示错误提示。
- 加载更多请求迟到后不追加到新任务。
- A→B 顺序切换不串数据。
- 有效任务→不存在任务清理旧数据。
- Strategy2 三源全部失败直接失败，不使用缓存。
- Strategy2 核心算法和 Strategy1 回归全部通过。

---

## 9. 最终验收命令

```bash
cd web
npm.cmd test -- --run
npm.cmd run build
cd ..

python -m pytest tests/test_strategy2_acceptance_fixes.py tests/test_strategy2_final_fixes.py tests/test_strategy2_bug_fixes.py tests/test_strategy2_engine.py tests/test_strategy2_indicators.py tests/test_strategy2_scorer.py tests/test_strategy2_rejection.py tests/test_strategy2_risk.py -q
python -m pytest tests/test_strategy2_acceptance_fixes.py tests/test_strategy2_final_fixes.py tests/test_strategy2_recheck_fixes.py -W error::pytest.PytestUnhandledThreadExceptionWarning -q
python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py
python -m compileall scanner strategy2 server.py -q
git diff --check
git status --short
```

最低预期：

```text
Vitest：至少 17 passed，0 failed
前端 build：通过
Strategy2 重点后端：至少 176 passed
线程 warning 门禁：61 passed，0 warnings
后端全量：至少 426 passed
compileall：通过
git diff --check：无输出
```

---

## 10. 本轮验证结果

```text
审核提交：
0e777c5

修改范围：
ScannerConsole.vue、ScannerConsole.history-task.test.js、审核文档

前端 Vitest：
11 passed

前端 build：
通过

Strategy2 重点后端：
176 passed

线程 warning 门禁：
61 passed

后端全量：
426 passed

compileall：
通过

git diff --check：
通过

工作树：
干净
```

测试通过不能覆盖本轮发现的静态并发缺陷。ROUND8-S2-001 可由轮询时序直接证明；ROUND8-S2-002 可由测试代码中未使用 deferred、缺少 timer 推进和删除原测试直接确认。

---

## 11. 可直接发送给修复 AI 的指令

请严格按照：

```text
docs/reviews/2026-06-11-strategy2-final-acceptance-recheck-round8.md
```

修复 `ROUND8-S2-001` 至 `ROUND8-S2-004`。

核心要求：

1. 将当前抢占式 `pollRequestEpoch` 改成单飞 poll session。
2. 保证慢于轮询间隔的状态响应仍会被应用。
3. 保证任务切换后旧 poll session 的迟到响应完全失效。
4. 修复测试，确保每个 deferred 请求真实被调用并处于 pending。
5. 补回旧轮询迟到、运行→完成、A→B、有效→不存在任务等测试。
6. 恢复 `loadMoreFailures()` 异常处理并补测试。
7. 更新最终第三方审核指南，不得继续声称当前 Round7 已最终交付。
8. 不修改任何策略算法、数据库、后端 API 或数据源规则。
9. 执行第 9 节所有验收命令并提供真实结果。

交付时必须说明：

- poll session 的具体结构和失效机制。
- 如何避免慢请求饿死。
- 每个新增竞态测试如何证明请求真实在途。
- 修改文件列表。
- Commit Hash。
- 全部验收命令结果。

# Round10 修复计划审核报告

## 1. 审核结论

当前计划方向正确，但**暂不建议直接执行**。需要补充两项中等级遗漏后再开发：

| 编号 | 计划遗漏 | 严重程度 | 必须修订 |
| --- | --- | --- | --- |
| PLAN-001 | 历史任务终态仍无法准确识别候选刷新失败，且失败股票请求失败会阻止候选刷新 | 中 | 是 |
| PLAN-002 | 重写 `[20]`、`[21]` 后会丢失旧 poll 隔离和 single-flight 的真实回归测试 | 中 | 是 |

低等级问题已过滤。

---

## 2. 已确认正确的计划内容

以下内容可以保留：

1. `finalizeCompletedPoll()` 中先校验 context/session；stale 时立即返回且不写页面。
2. 单个接口失败时记录到 `refreshFailures`，继续执行其他独立刷新。
3. 有效 context/session 下，任务完成后始终写完成日志。
4. 有部分刷新失败时设置 `scanError` 并写错误日志。
5. `finally` 中继续执行 `resetPollSession()`。
6. `[18]`、`[19]` 必须真实推进 timer 触发完成流程。
7. 候选刷新失败和失败股票刷新失败必须分别测试。

---

## 3. 必须修订的问题

### PLAN-001：历史任务终态失败仍未被正确处理

#### 当前代码行为

历史任务完成时调用：

```js
const ok = await refreshTaskContext(context)
```

但 `refreshTaskContext()` 内部行为是：

```js
const data = await getTaskStocks(...)
...
await loadResults(...)
return isCurrentViewContext(context)
```

存在两个问题：

1. `getTaskStocks()` 失败时，函数直接进入 catch 或返回，历史候选不会继续刷新。
2. `loadResults()` 返回 `false` 时，其结果被忽略；只要 context 仍有效，`refreshTaskContext()` 仍返回 `true`。

因此，仅在 `finalizeCompletedPoll()` 外层维护 `refreshFailures` 无法满足计划目标：

- 历史候选刷新失败不会被记录，也不会显示警告。
- 历史失败股票刷新失败会阻止候选刷新。

#### 修订要求

正常历史页面初次加载仍可保留 `refreshTaskContext()`，但**历史任务终态刷新**必须拆分为独立步骤，或让 `refreshTaskContext()` 返回每个步骤的结构化结果。

推荐新增专用函数：

```js
async function refreshCompletedHistoricalTask({ context, session }) {
  const refreshFailures = []
  const taskId = context.taskId

  const failuresOk = await loadHistoricalFailuresAndSummary({
    taskId,
    context,
    pollSession: session,
  })
  if (!isCurrentViewContext(context) || !isCurrentPollSession(session)) {
    return { stale: true, refreshFailures: [] }
  }
  if (!failuresOk) refreshFailures.push('历史任务详情')

  const resultsOk = await loadResults({
    taskId,
    strategyType: activeStrategyType.value,
    context,
    pollSession: session,
  })
  if (!isCurrentViewContext(context) || !isCurrentPollSession(session)) {
    return { stale: true, refreshFailures: [] }
  }
  if (!resultsOk) refreshFailures.push('最终候选')

  return { stale: false, refreshFailures }
}
```

或者修改 `refreshTaskContext()` 返回：

```js
{
  stale: false,
  detailsOk: true,
  resultsOk: false,
}
```

但不能继续只返回一个无法区分步骤结果的布尔值。

必须保证：

- 历史失败股票/summary 刷新失败后，仍尝试刷新历史候选。
- 历史候选刷新失败后，已成功刷新的失败股票/summary 保留。
- 任一失败均进入 `refreshFailures` 并向用户提示。
- stale 时立即退出且不写警告或完成日志。

---

### PLAN-002：不能用接口失败测试替换旧 poll 与 single-flight 测试

计划当前将：

- `[20]` 改为候选刷新失败。
- `[21]` 改为失败股票刷新失败。

这样会再次丢失以下关键回归保护：

- 任务切换后旧 poll 迟到响应不得覆盖新任务。
- 慢状态请求 pending 期间不得发出重叠 poll。

这两项直接保护 Round8/9 的核心 session 生命周期，不能删除。

#### 修订后的测试编号建议

| 测试 | 场景 |
| --- | --- |
| `[18]` | live running → completed，验证最终候选、失败股票、完成日志 |
| `[19]` | 历史 running → mismatch/completed，验证最终 summary、候选、失败股票、完成日志 |
| `[20]` | 旧 poll 真正 pending → 切换任务 → 旧响应不覆盖新任务 |
| `[21]` | 状态请求真正 pending → 推进多个 timer 间隔 → 无重叠请求 |
| `[22]` | live 候选终态刷新失败，但失败股票仍显示，完成日志与警告存在 |
| `[23]` | live 失败股票终态刷新失败，但候选仍显示，完成日志与警告存在 |
| `[24]` | 历史候选刷新失败，但失败股票/summary 仍显示，完成日志与警告存在 |
| `[25]` | 历史失败股票/summary 刷新失败，但候选仍显示，完成日志与警告存在 |

---

## 4. 测试实现注意事项

### 必须使用精确调用序列

页面挂载时已经会调用候选和失败股票接口。若直接使用：

```js
mockApi.getCandidates.mockRejectedValue(...)
```

异常可能发生在初始加载阶段，而不是终态刷新阶段，测试会验证错路径。

必须使用按调用顺序的 mock：

```js
mockApi.getCandidates
  .mockResolvedValueOnce({ candidates: [] }) // 初始 live 加载
  .mockRejectedValueOnce(new Error('final candidates failed')) // 终态刷新
```

失败股票接口同理：

```js
mockApi.getTaskStocks
  .mockResolvedValueOnce(initialFailures)
  .mockRejectedValueOnce(new Error('final failures failed'))
```

### `[18]` live 完成测试

必须：

1. 初始 `getScanStatus()` 返回 running。
2. 挂载并确认 timer 已启动。
3. 将下一次状态设置为 completed。
4. 推进 `1000ms`。
5. 断言最终候选、失败股票和完成日志。

### `[19]` 历史完成测试

必须：

1. 初始历史详情与状态返回 running。
2. 下一次状态返回 task mismatch 或 completed。
3. 最终详情与候选使用下一次 mock 返回。
4. 推进 timer。
5. 断言最终 summary、候选、失败股票和完成日志。

### `[20]` 旧 poll 迟到测试

必须在切换任务前执行：

```js
await vi.advanceTimersByTimeAsync(1000)
expect(mockApi.getScanStatus).toHaveBeenCalledTimes(expectedCount)
```

确保旧 poll 已真实进入 deferred pending，再切换任务。

### `[21]` single-flight 测试

必须：

1. 下一次状态请求返回 deferred promise。
2. 推进多个轮询间隔。
3. 使用调用次数断言 pending 期间没有新增请求。
4. resolve 后确认响应被应用。
5. 再推进一个间隔，确认下一次 poll 才开始。

---

## 5. 修订后的执行计划

1. 保留现有 `clearPollTimer()`、`invalidatePolling()` 和 session 生命周期。
2. 调整 `finalizeCompletedPoll()`，区分 stale 与接口失败。
3. live 终态候选和失败股票分别刷新，互不短路。
4. 拆分历史终态详情/失败股票与候选刷新，互不短路。
5. 有效 session 下始终写完成日志；部分失败时额外写用户可见警告。
6. 保留并真实重写旧 poll 与 single-flight 测试。
7. 新增 live 与历史两类部分刷新失败测试。
8. 运行全部前端、后端、构建和静态门禁。

---

## 6. 给修复 AI 的修订提示语

```text
你提交的 Round10 修复计划方向正确，但执行前必须按
docs/reviews/2026-06-11-strategy2-round10-fix-plan-review.md
补齐 PLAN-001 和 PLAN-002。

关键修订：
1. 不仅要修 live 分支；历史终态也必须将失败股票/summary 与候选拆开刷新，任何一个失败都不能阻止另一个。
2. refreshTaskContext 当前会忽略 loadResults(false)，不能直接用其单个布尔返回值判断历史终态是否完整。
3. 保留 `[20]` 旧 poll pending 隔离测试和 `[21]` single-flight 测试，不能用接口失败测试替换。
4. 将接口失败测试新增为 `[22]-[25]`，同时覆盖 live 和历史任务。
5. 所有失败测试必须使用 mockResolvedValueOnce / mockRejectedValueOnce 精确命中终态刷新调用，不能误测初始加载。
6. stale 时立即退出；有效 session 下部分接口失败时继续其他刷新、写完成日志，并显示明确警告。

不要修改策略算法、评分、过滤、风险规则、后端 schema 或无关模块。
```

---

## 7. 最终计划验收标准

修订后的计划必须明确回答：

1. live 候选失败后，失败股票是否继续刷新？
2. live 失败股票失败后，候选是否保留？
3. 历史候选失败后，失败股票和 summary 是否继续刷新？
4. 历史失败股票/summary 失败后，候选是否继续刷新？
5. stale 与接口失败如何被可靠区分？
6. 旧 poll 隔离与 single-flight 测试是否保留并真实构造？
7. 测试如何保证异常发生在终态刷新而非初始加载？

# 代码问题检查报告

## 1. 检查范围

- 修复前基线：`ccc53fe`
- 本轮审核提交：`7610c5f fix(strategy2): round10 — finalizeCompletedPoll distinguishes stale vs interface failure`
- 重点生产文件：`web/src/pages/ScannerConsole.vue`
- 关联测试：`web/src/pages/__tests__/ScannerConsole.history-task.test.js`
- 按要求过滤低等级问题，仅记录中、高等级问题。

---

## 2. 总体结论

Round10 已正确修复 live 终态部分刷新失败的核心控制流：

- stale context/session 会立即退出。
- 候选刷新失败后仍会尝试失败股票刷新。
- 失败股票刷新失败不会撤销已成功刷新的候选。
- 有效 session 下会写完成日志与用户可见警告。

但本轮仍不能验收通过。

历史任务完成分支从 `refreshTaskContext()` 改为 `loadFailures()` 后，没有再调用 `applyTaskSummary()`。历史运行任务完成时，失败股票和候选可以刷新，但页面的最终 `processed`、`failed`、`candidates`、`latestTradeDate`、`stockPoolSource` 等 summary 字段仍停留在运行中状态。

同时，新增的终态与部分失败测试多数只验证初始页面加载，没有真正触发 `finalizeCompletedPoll()`，因此 25 个测试全部通过也未发现该高等级回归。

---

## 3. 问题清单

| 编号 | 问题 | 严重程度 | 影响范围 | 是否必须修复 |
| --- | --- | --- | --- | --- |
| ROUND11-S2-001 | 历史任务完成后不再应用最终 summary，页面持续显示运行中的旧进度 | 高 | 历史任务终态、进度、失败数、候选数、交易日期、数据源 | 是 |
| ROUND11-S2-002 | 新增终态及部分失败测试未真实触发目标路径，无法保护修复 | 中 | 前端回归可信度、终态一致性、竞态保护 | 是 |

---

## 4. 详细问题分析

### ROUND11-S2-001：历史任务完成后不再应用最终 summary

#### 问题位置

`web/src/pages/ScannerConsole.vue`

Round9 历史终态使用：

```js
const ok = await refreshTaskContext(context)
```

`refreshTaskContext()` 会执行：

```js
applyTaskSummary(data.summary)
```

Round10 改为：

```js
const failOk = await loadFailures({
  taskId: context.taskId,
  context,
  pollSession: session,
})
```

但 `loadFailures()` 只更新：

```js
failures.value = data.stocks || []
failuresTotal.value = data.total || 0
activeStrategyType.value = data.strategy_type
```

它不会调用：

```js
applyTaskSummary(data.summary)
```

#### 触发条件

1. 用户打开一个仍在运行的历史任务，例如当前显示 `processed=80/100`。
2. 页面启动该历史任务的轮询。
3. 后端任务完成，状态接口不再返回该任务。
4. `pollStatus()` 进入历史 mismatch/completed 分支。
5. `finalizeCompletedPoll({ historical: true })` 执行最终刷新。

#### 实际结果

- 最终失败股票列表可能更新。
- 最终候选可能更新。
- 完成日志可能写入。
- 但 summary 仍保持旧值，例如 `processed=80/100`。
- 最终 `failed`、`candidates`、`latestTradeDate`、`stockPoolSource` 也可能保持旧值。
- 完成日志使用的数字同样可能来自旧 summary。

#### 用户影响

页面会同时显示：

- “扫描完成”日志。
- 仍未完成的旧进度，例如 `80/100`。

这会造成直接的任务状态矛盾，影响用户判断扫描是否完整、失败股票数量是否可信。

#### 根本原因

为了让历史详情与候选独立刷新，Round10 绕过了 `refreshTaskContext()`；但新的历史详情刷新只复用了 `loadFailures()`，遗漏了同一接口响应中的 `summary`。

---

## 5. ROUND11-S2-001 一次性修复方案

### 推荐最小改动

给 `loadFailures()` 增加显式的 `applySummary` 可选参数，默认关闭，避免影响 live 轮询中的现有行为：

```js
async function loadFailures({
  taskId,
  context,
  pollSession,
  applySummary = false,
} = {}) {
  const targetTaskId = normalizeTaskId(taskId)
  if (!targetTaskId) return false

  try {
    const data = await getTaskStocks(targetTaskId, {
      status: 'failed',
      page_size: 50,
      page: 1,
    })

    if (context && !isCurrentViewContext(context)) return false
    if (pollSession && !isCurrentPollSession(pollSession)) return false
    if (!data.ok) return false

    failures.value = data.stocks || []
    failuresTotal.value = data.total || 0

    if (data.strategy_type) {
      activeStrategyType.value = data.strategy_type
    }
    if (applySummary) {
      applyTaskSummary(data.summary)
    }

    return true
  } catch (e) {
    if (
      (!context || isCurrentViewContext(context))
      && (!pollSession || isCurrentPollSession(pollSession))
    ) {
      console.error('Load failures failed:', e)
    }
    return false
  }
}
```

历史终态调用时显式启用：

```js
const failOk = await loadFailures({
  taskId: context.taskId,
  context,
  pollSession: session,
  applySummary: true,
})
```

live 轮询及普通失败列表刷新保持默认：

```js
applySummary: false
```

### 为什么只在历史终态启用

- live 任务的当前进度由状态接口 `applyStats(status)` 驱动。
- 历史任务最终 summary 必须来自持久化任务详情接口。
- 明确参数可以避免普通失败列表请求意外覆盖实时进度。

### 必须保持的行为

1. `loadFailures()` 在写 summary 前仍必须完成 context/session 校验。
2. 历史 summary 刷新失败后，仍尝试候选刷新。
3. 历史候选刷新失败后，已成功更新的 summary 和失败股票必须保留。
4. 部分失败仍写完成日志和明确警告。
5. 不要恢复使用会短路候选刷新的旧 `refreshTaskContext()` 终态流程。

---

## 6. ROUND11-S2-002：测试没有真实触发目标路径

### 当前测试问题

#### `[13] historical running→completed`

测试名称声称从 running 到 completed，但当前只完成初始挂载并断言 `processed=80`，没有推进 timer，也没有返回最终 summary。

#### `[18] live completion`

只验证初始 live 加载后失败股票存在，没有让状态从 running 变为 completed，也没有断言完成日志。

#### `[19] historical completion`

只验证初始历史任务 `processed=80`，没有推进 timer 触发 mismatch/completed。

#### `[22]` 至 `[25]` 部分刷新失败测试

这些测试没有设置任何终态接口异常，也没有触发 `finalizeCompletedPoll()`：

- 没有 `mockRejectedValueOnce()`。
- 没有推进 timer 进入 completed。
- 没有断言完成日志。
- 没有断言用户可见警告。

因此它们没有验证标题所描述的失败场景。

#### `[21] single-flight`

已经使用 deferred，但断言：

```js
expect(pollCalls).toBeLessThanOrEqual(2)
```

过于宽松。single-flight 的核心应是 pending 期间只出现一个 poll 请求；必须记录推进 timer 前的基准调用次数并精确断言没有新增重叠请求。

---

## 7. 必须重写的验收测试

### `[18]` live 正常完成

1. 初始状态返回 running。
2. 挂载页面并确认 timer 已启动。
3. 下一次状态返回 completed。
4. 候选和失败股票终态接口返回最终数据。
5. 推进 1000ms。
6. 断言最终候选、失败股票、完成日志。

### `[19]` 历史任务正常完成

必须直接保护 ROUND11-S2-001：

1. 初始详情 summary 返回 `processed=80`。
2. 初始状态返回 running 且 task id 匹配。
3. 最终详情 summary 返回：

```js
{
  total_stocks: 100,
  processed: 100,
  failed: 5,
  candidate: 4,
  scanned: 93,
  skipped: 2,
  latest_trade_date: '2026-06-10',
  stock_pool_source: 'akshare',
}
```

4. 下一次状态返回 task mismatch/completed。
5. 推进 1000ms。
6. 精确断言：
   - `processed=100`
   - `failed=5`
   - `candidates=4`
   - `latest=2026-06-10`
   - `source=akshare`
   - 最终失败股票
   - 最终候选
   - “扫描完成”日志

### `[22]` live 候选终态刷新失败

使用精确调用顺序：

```js
mockApi.getCandidates
  .mockResolvedValueOnce({ candidates: [] })
  .mockRejectedValueOnce(new Error('final candidates failed'))
```

必须断言：

- 最终失败股票仍显示。
- 完成日志存在。
- “最终候选刷新失败”警告存在。

### `[23]` live 失败股票终态刷新失败

初始失败列表请求成功，终态请求失败：

```js
mockApi.getTaskStocks
  .mockResolvedValueOnce(initialFailures)
  .mockRejectedValueOnce(new Error('final failures failed'))
```

必须断言：

- 最终候选仍显示。
- 完成日志存在。
- “最终失败股票刷新失败”警告存在。

### `[24]` 历史候选终态刷新失败

必须断言：

- 最终 summary 已更新到 100/100。
- 最终失败股票显示。
- 完成日志存在。
- “最终候选刷新失败”警告存在。

### `[25]` 历史详情终态刷新失败

必须断言：

- 最终候选仍显示。
- 完成日志存在。
- “历史任务详情刷新失败”警告存在。

### `[20]` 和 `[21]`

- 保留真实旧 poll pending 隔离测试。
- single-flight pending 期间必须精确断言请求调用次数没有增加。

---

## 8. 给修复 AI 的提示语

```text
请根据 docs/reviews/2026-06-11-strategy2-final-acceptance-recheck-round11.md
修复 ROUND11-S2-001 和 ROUND11-S2-002。

本轮重点文件：
- web/src/pages/ScannerConsole.vue
- web/src/pages/__tests__/ScannerConsole.history-task.test.js

核心要求：
1. 历史任务终态刷新失败股票时，必须同时应用该响应中的最终 summary。
2. 推荐给 loadFailures 增加默认关闭的 applySummary 参数，仅历史终态调用显式启用。
3. 保持候选与历史详情独立刷新；任一失败不能阻止另一个。
4. 保持 stale context/session 立即退出、部分接口失败显示完成日志和警告的 Round10 行为。
5. `[18]`、`[19]`、`[22]-[25]` 必须真实推进 timer 进入 finalizeCompletedPoll。
6. 失败测试必须使用 mockResolvedValueOnce / mockRejectedValueOnce，让异常精确发生在终态刷新，而不是初始加载。
7. `[19]` 必须断言历史最终 processed、failed、candidates、latestTradeDate 和 stockPoolSource。
8. `[21]` 必须精确断言 pending 期间没有重叠状态请求。
9. 不要修改策略算法、评分、过滤、风险规则、后端 schema 或无关模块。

完成后报告：
- 历史终态 summary 从哪个响应应用。
- applySummary 在哪些调用点启用。
- 每个测试真实构造的异步时序。
- 全部验收命令的实际结果。
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

## 10. 本轮验证结果

| 验证项 | 结果 |
| --- | --- |
| 前端测试 | 25 passed |
| 前端生产构建 | 通过 |
| Strategy2 聚焦后端测试 | 176 passed |
| 后端离线全量测试 | 426 passed |
| 线程异常 warning 门禁 | 61 passed |
| Python 编译检查 | 通过 |
| `git diff --check ccc53fe..HEAD` | 通过 |

现有测试全部通过，但 ROUND11-S2-001 可以由生产代码控制流直接证明；ROUND11-S2-002 解释了该问题为何没有被测试发现。

---

## 11. 最终交付标准

1. 历史运行任务完成后 summary 更新为最终持久化值。
2. 历史最终失败股票、候选、summary 和完成日志保持一致。
3. live 与历史部分刷新失败均继续执行其他独立刷新。
4. stale 响应仍不能写入当前页面。
5. 用户能看到完成状态和部分刷新失败警告。
6. 终态、失败和 single-flight 测试真实执行对应异步路径。
7. 第 9 节所有命令全部通过。

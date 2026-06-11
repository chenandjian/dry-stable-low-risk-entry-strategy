# 代码问题检查报告

## 1. 检查范围

- 修复前基线：`ba85084`
- 本轮审核提交：`ccc53fe fix(strategy2): round9 — split stopPolling into clearPollTimer + invalidatePolling, finalizeCompletedPoll`
- 重点生产文件：`web/src/pages/ScannerConsole.vue`
- 关联测试：`web/src/pages/__tests__/ScannerConsole.history-task.test.js`
- 按要求过滤低等级问题，仅记录中、高等级问题。

---

## 2. 总体结论

Round9 原高等级问题已经修复：

- 正常完成流程只清除 poll timer，不再提前失效当前 session。
- 任务切换与组件卸载会立即失效旧 session。
- `loadResults()` 已增加 `pollSession` 写入防护。
- live 与历史任务完成流程已统一进入 `finalizeCompletedPoll()`。

但本轮仍不能最终验收通过。

当前 `finalizeCompletedPoll()` 在最终候选或失败列表接口任意一次失败时会直接返回。此时扫描已经停止、session 随后失效，但页面不会显示完成日志，也不会显示终态刷新失败提示。候选刷新失败还会阻止失败股票刷新。

本轮仅发现一个中等级生产问题。

---

## 3. 问题清单

| 编号 | 问题 | 严重程度 | 影响范围 | 是否必须修复 |
| --- | --- | --- | --- | --- |
| ROUND10-S2-001 | 终态刷新接口失败时静默退出，并短路其他终态数据刷新 | 中 | `ScannerConsole.vue`、最终失败股票、候选、完成状态提示 | 是 |

---

## 4. 详细问题分析

### ROUND10-S2-001：终态刷新接口失败时静默退出

#### 问题位置

`web/src/pages/ScannerConsole.vue` 的 `finalizeCompletedPoll()`：

```js
const resultsOk = await loadResults(...)
if (!resultsOk || !isCurrentViewContext(context) || !isCurrentPollSession(session)) return false

const failuresOk = await loadFailures(...)
if (!failuresOk || !isCurrentViewContext(context) || !isCurrentPollSession(session)) return false

addLog('found', `扫描完成 ...`)
```

#### 触发条件

扫描任务已经正常完成，但最终刷新阶段发生以下任一情况：

- 候选接口短暂超时或返回失败。
- 失败股票接口短暂超时或返回失败。
- 后端重启、网络闪断或单个终态接口暂时不可用。

#### 实际执行结果

如果 `loadResults()` 返回 `false`：

1. `finalizeCompletedPoll()` 立即返回。
2. `loadFailures()` 不再执行。
3. 最终失败股票不会刷新。
4. 完成日志不会写入。
5. `finally` 中失效当前 session。
6. poll timer 已经停止，不会自动重试。
7. `loadResults()` 仅写控制台日志，页面没有错误提示。

如果 `loadFailures()` 返回 `false`：

1. 候选可能已刷新。
2. 最终失败股票仍为旧数据。
3. 完成日志不会写入。
4. session 失效且不再自动重试。
5. 页面没有终态刷新失败提示。

#### 用户影响

- 用户可能看到旧的失败股票列表，但不知道数据未刷新成功。
- 候选接口失败会连带阻止失败股票刷新，两个互相独立的数据区域被错误串联。
- 页面既不显示“扫描完成”，也不显示“最终结果刷新失败”，任务状态不明确。
- 用户可能误判数据源全部失败的股票数量和明细。

#### 根本原因

当前使用同一个布尔值 `false` 表示两类完全不同的结果：

1. context/session 已失效，必须立即停止写入。
2. 当前 context/session 仍有效，但某个终态接口请求失败。

第二类失败不应该被当成 stale response；它应该继续尝试刷新其他独立数据，并向用户显示明确警告。

---

## 5. 一次性修复方案

### 修复原则

1. context/session 失效时立即返回，禁止旧响应写入。
2. 单个终态接口失败时，不得阻止其他独立终态接口刷新。
3. 任务已经完成时，应显示完成日志。
4. 如果终态数据未全部刷新成功，必须同时显示明确警告。
5. 不要恢复轮询，也不要删除现有 session 防护。

### 推荐修改方式

修改 live 终态刷新逻辑，分别执行候选与失败列表刷新，并在每次 `await` 后先判断 context/session 是否仍有效。

示例：

```js
async function finalizeCompletedPoll({ context, session, historical }) {
  const refreshFailures = []

  try {
    if (historical) {
      const ok = await refreshTaskContext(context)
      if (!isCurrentViewContext(context) || !isCurrentPollSession(session)) return false
      if (!ok) refreshFailures.push('历史任务详情')
    } else {
      const resultsOk = await loadResults({
        taskId: scanProgress.taskId,
        strategyType: activeStrategyType.value,
        context,
        pollSession: session,
      })
      if (!isCurrentViewContext(context) || !isCurrentPollSession(session)) return false
      if (!resultsOk) refreshFailures.push('最终候选')

      const failuresOk = await loadFailures({
        taskId: scanProgress.taskId,
        context,
        pollSession: session,
      })
      if (!isCurrentViewContext(context) || !isCurrentPollSession(session)) return false
      if (!failuresOk) refreshFailures.push('最终失败股票')
    }

    addLog(
      'found',
      `扫描完成 · 发现 ${scanProgress.candidates} 个候选 · 跳过 ${scanProgress.skipped} · 失败 ${scanProgress.failed}`,
    )

    if (refreshFailures.length) {
      const message = `扫描已完成，但${refreshFailures.join('、')}刷新失败，请刷新页面重试`
      scanError.value = message
      addLog('error', message)
      return false
    }

    return true
  } finally {
    if (isCurrentPollSession(session)) {
      resetPollSession()
    }
  }
}
```

允许调整文案和实现结构，但必须满足：

- `loadResults()` 失败后仍尝试 `loadFailures()`。
- stale context/session 仍立即退出。
- 有效 session 下的接口失败必须显示用户可见错误。
- 即使部分终态数据刷新失败，也要明确告知任务已经完成。
- 最终 session 仍在 `finally` 中失效。

### 可选增强

可以让 `loadResults()` / `loadFailures()` 返回结构化状态，例如：

```js
{ ok: false, reason: 'request_failed' }
{ ok: false, reason: 'stale' }
```

这样可以更清楚地区分请求失败和旧响应失效。但若布尔返回值配合每次 await 后的 context/session 校验已经足够清晰，不需要为此过度重构。

---

## 6. 必须补充或修正的验收测试

当前新增的 `[18]`、`[19]`、`[20]`、`[21]` 测试均通过，但没有真正触发标题描述的关键异步路径：

- `[18]` 没有让 live 状态从 running 变为 completed。
- `[19]` 没有推进 timer 触发历史任务完成。
- `[20]` 没有在切换任务前推进 timer，使旧 poll 真正进入 pending。
- `[21]` 没有 deferred pending 请求，也没有验证请求调用次数。

这些测试缺口不单独列为生产问题，但必须在本轮修复中补齐，否则无法证明终态和 session 生命周期正确。

### 必测场景一：候选终态刷新失败

1. live 任务从 running 变为 completed。
2. `getCandidates()` 抛出异常。
3. `getTaskStocks()` 正常返回最终失败股票。
4. 断言最终失败股票仍然显示。
5. 断言页面显示扫描已完成。
6. 断言页面显示“最终候选刷新失败”警告。

### 必测场景二：失败股票终态刷新失败

1. live 任务从 running 变为 completed。
2. 候选接口正常返回。
3. 失败股票接口抛出异常或返回失败。
4. 断言最终候选正常显示。
5. 断言页面显示扫描已完成。
6. 断言页面显示“最终失败股票刷新失败”警告。

### 必测场景三：真正的 live 完成路径

1. 初始 live 状态为 running。
2. 推进 fake timer。
3. 下一次状态返回 completed。
4. 断言最终候选、失败股票、summary 和完成日志全部显示。

### 必测场景四：真正的历史完成路径

1. 历史任务初始 running。
2. 推进 fake timer。
3. 状态返回任务已结束。
4. 断言历史最终数据和完成日志全部显示。

### 必测场景五：真正的旧 poll 迟到与 single-flight

- 使用 deferred promise。
- 先推进 timer，确认 poll 已开始并 pending。
- pending 期间推进多个间隔，断言没有重叠状态请求。
- 切换任务后 resolve 旧响应，断言旧响应不覆盖新任务。

---

## 7. 给修复 AI 的提示语

```text
请根据 docs/reviews/2026-06-11-strategy2-final-acceptance-recheck-round10.md 修复 ROUND10-S2-001。

修复前基线为 ba85084，本轮审核提交为 ccc53fe。
生产代码只需要重点修改 web/src/pages/ScannerConsole.vue，并同步修正对应前端测试。

核心要求：
1. 保留 Round9 已正确实现的 clearPollTimer / invalidatePolling / pollSession 生命周期。
2. finalizeCompletedPoll 中，候选刷新失败不能阻止失败股票刷新。
3. 每个 await 后先检查 context/session；只有 stale 时立即退出。
4. 当前 context/session 有效但终态接口失败时，必须显示用户可见警告。
5. 即使部分终态数据刷新失败，也必须明确显示任务已经完成。
6. 使用真实 timer 推进和 deferred promise 重写测试 [18]-[21]，不能只写结构性注释。
7. 不要修改策略算法、评分、过滤、风险规则、后端 schema 或无关模块。

完成后说明：
- finalizeCompletedPoll 如何区分 stale 与接口失败。
- 单个终态接口失败时，其他终态接口是否继续执行。
- 每个新增测试实际构造了什么异步时序。
- 所有验收命令的实际结果。
```

---

## 8. 回归验证命令

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

## 9. 本轮验证结果

| 验证项 | 结果 |
| --- | --- |
| 前端测试 | 21 passed |
| 前端生产构建 | 通过 |
| Strategy2 聚焦后端测试 | 176 passed |
| 后端离线全量测试 | 426 passed |
| 线程异常 warning 门禁 | 61 passed |
| Python 编译检查 | 通过 |
| `git diff --check ba85084..HEAD` | 通过 |

---

## 10. 最终交付标准

1. Round9 的 session 生命周期修复保持有效。
2. 候选终态刷新失败不会阻止失败股票刷新。
3. 失败股票终态刷新失败不会隐藏已成功刷新的候选。
4. 部分终态刷新失败时，用户同时看到任务完成状态和明确警告。
5. 旧 context/session 仍不能写入页面状态。
6. `[18]` 至 `[21]` 使用真实异步时序验证对应行为。
7. 第 8 节所有命令全部通过。

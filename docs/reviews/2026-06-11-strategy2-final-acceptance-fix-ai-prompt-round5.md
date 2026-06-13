# Strategy2 第五轮最终收尾修复指令

请修复 `docs/reviews/2026-06-11-strategy2-final-acceptance-recheck-round5.md` 的全部问题。本轮仅允许修改 ScannerConsole 历史完成态、任务切换清理、对应前端测试、busy 诊断测试及剩余文档注释。

## 1. 修复历史运行任务完成态

当前 `pollStatus()` 在历史任务 mismatch 分支中提前 return，导致历史任务完成后不执行最终 `refreshTaskContext()`。

修改 `web/src/pages/ScannerConsole.vue`：

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

要求：

- 必须在 stopPolling 前保存 `wasTracking`。
- 历史任务完成后重新加载目标任务 summary、候选和失败股票。
- 不能加载当前运行的其他任务。
- 不得删除历史任务轮询能力。

## 2. 修复 query 切换旧状态残留

新增统一清理：

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

`switchTaskContext()` 加载新任务前必须调用该函数。

`refreshTaskContext()` 失败时必须设置：

```js
scanError.value = data.error === 'TASK_NOT_FOUND'
  ? `任务不存在：${taskId}`
  : '历史任务加载失败'
```

删除未使用的 `lastKnownTaskId`。

## 3. 补真实前端测试

修改 `web/src/pages/__tests__/ScannerConsole.history-task.test.js`：

- 将 `mockRoute` 改为 `reactive()`。
- 每个测试 unmount 组件。
- 涉及轮询时使用 fake timers，并在结束后恢复。

必须增加：

1. `historical running task refreshes final summary after completion`
   - 初始目标任务 running=true。
   - 下一次 poll 返回 running=false/task_id=null。
   - 断言最终再次请求目标任务。
   - 断言最终失败数、候选数和完成日志。

2. `query change from task A to task B reloads B and clears A`
   - mount 后响应式修改 query。
   - 断言调用 B。
   - 断言页面不再显示 A。

3. `query change from valid task to missing task clears old state`
   - A 有失败股票和策略1重试按钮。
   - 切换到 missing。
   - 断言旧失败股票、重试按钮、统计全部消失。
   - 断言显示任务不存在。

当前仅验证初始 task A 的测试不能作为 A→B watcher 测试。

## 4. 精确化 busy 诊断测试

修改 `tests/test_strategy2_acceptance_fixes.py` 的 busy 超限测试，断言：

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

## 5. 清理剩余缓存新鲜度旧描述

修改：

- `docs/superpowers/specs/2026-06-10-strategy2-extreme-dry-stable-design.md`
- `scanner/daily_data_service.py`

删除不存在的：

- “沿用现有日线缓存和新鲜度策略”
- “缓存过期判断”
- “缓存新鲜度”

明确：

- 在线拉取成功后，允许与数据库历史数据合并并持久化。
- 全部在线源失败后直接失败，不进行缓存新鲜度判断，不使用缓存扫描。

删除 `scanner/daily_data_service.py` 未使用的：

```python
from datetime import date, timedelta
```

## 6. 禁止事项

- 不修改策略算法、任务 API 或数据库结构。
- 不恢复缓存兜底、mootdx 或 yfinance。
- 不删除历史任务轮询。
- 不使用普通非响应式 mock 冒充 query watcher 测试。
- 不使用真实 sleep 等待前端轮询。
- 不重构无关模块。

## 7. 必须执行的验收

```bash
python -m pytest tests/test_strategy2_acceptance_fixes.py tests/test_strategy2_final_fixes.py tests/test_strategy2_recheck_fixes.py -W error::pytest.PytestUnhandledThreadExceptionWarning -q
python -m pytest tests/ -q
python -m compileall scanner strategy2 server.py -q

cd web
npm run test
npm run build
cd ..

rg -n "缓存新鲜度|缓存和新鲜度策略|缓存.*过期判断" docs/superpowers/specs/2026-06-10-strategy2-extreme-dry-stable-design.md scanner/daily_data_service.py
git diff --check
git status --short
```

预期：

- 后端全部通过，无线程 warning。
- 前端真实组件测试包含并通过三个新增场景。
- build 和 compileall 通过。
- `rg` 无旧规则命中。
- diff check 无输出。

## 8. 交付报告

报告：

1. 修复前后提交 Hash。
2. ROUND5-S2-001 至 005 修改文件和测试。
3. 历史任务完成时最终恢复执行顺序。
4. query 切换失败时如何清除旧状态。
5. 前端测试名称和精确通过数。
6. 后端全量、前端测试、build、compileall 和 diff check 结果。
7. 缓存新鲜度旧描述检索结果。
8. 未完成项必须为空。

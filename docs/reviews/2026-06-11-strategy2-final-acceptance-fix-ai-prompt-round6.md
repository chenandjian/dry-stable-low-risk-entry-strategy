# Strategy2 第六轮最终收尾修复指令

请严格修复：

`docs/reviews/2026-06-11-strategy2-final-acceptance-recheck-round6.md`

目标是一次完成 ROUND6-S2-001 至 ROUND6-S2-003，并完成最终验收。

## 1. 必须先确认

修复前执行：

```bash
git status --short
git log --oneline -5
```

确认当前基线包含：

```text
7b95046 fix(strategy2): round5 — history completion state, query switch cleanup, vitest upgrades, doc sync
```

不要覆盖用户已有未提交修改。

---

## 2. 修复已完成历史任务首次加载 summary

文件：

```text
web/src/pages/ScannerConsole.vue
```

当前 `loadHistoricalTask()` 成功加载任务后没有执行：

```js
applyTaskSummary(data.summary)
```

必须修复，使用户直接打开：

```text
/?task=<completed-task-id>
```

时能够显示后端返回的真实：

- processed
- total_stocks
- skipped
- failed
- candidate
- latest_trade_date
- stock_pool_source

推荐方案：

- 历史任务首次加载和 query 切换复用同一任务上下文恢复逻辑。
- 避免 `loadHistoricalTask()` 与 `refreshTaskContext()` 分别维护 summary、失败列表和策略类型。

最低要求：

```js
applyTaskSummary(data.summary)
```

必须在已完成任务路径执行。

---

## 3. 统一历史任务加载错误语义

让 `refreshTaskContext(taskId)` 负责完整错误处理：

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

要求：

- 删除 `switchTaskContext()` 中将所有失败统一写成“任务不存在”的逻辑。
- 404 显示“任务不存在”。
- 非 404 和网络异常显示“历史任务加载失败”。
- 切换加载失败时旧任务统计、候选、失败列表和策略类型保持已清空状态。
- 历史完成态最终刷新失败时不得写入成功完成日志。

---

## 4. 补真实前端测试

文件：

```text
web/src/pages/__tests__/ScannerConsole.history-task.test.js
```

### 4.1 已完成历史任务首次加载 summary

新增测试：

```text
completed historical task applies persisted summary on initial load
```

要求：

- URL 初始为 completed Strategy2 任务。
- `getTaskStocks()` 返回非零 summary。
- `getScanStatus()` 返回 `running=false`。
- 断言页面显示真实 processed/total、failed、candidate。
- 断言 Strategy2 候选接口被调用。

### 4.2 历史运行任务真实完成

重写当前：

```text
historical running task refreshes final summary after completion
```

必须让状态真实变化：

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

必须推进轮询：

```js
await vi.advanceTimersByTimeAsync(1000)
```

必须断言：

- 目标任务上下文至少加载两次。
- 最终 summary 已显示。
- 最终失败列表已显示。
- 完成日志已显示。
- 未加载其他任务。

### 4.3 有效任务 A 切换到有效任务 B

新增测试：

```text
query change from task A to task B reloads B and clears A
```

要求：

- A 使用 Strategy1，带 A 候选、A 失败股票和重试按钮。
- B 使用 Strategy2，带 B 候选、B 失败股票和不同 summary。
- 响应式修改 `mockRoute.query` 从 A 到 B。
- 断言 A 的候选、失败股票和重试按钮消失。
- 断言 B 的候选、失败股票和 summary 出现。
- 断言 B 使用 `getStrategy2Candidates('task-b')`。

### 4.4 错误语义

增加：

- 非 404 返回显示“历史任务加载失败”。
- `getTaskStocks()` reject 时显示“历史任务加载失败”。
- 两种情况下旧任务数据均已清空。

所有测试必须：

- 使用响应式 route。
- 使用 fake timers。
- 使用 `flushPromises()` 或等价可靠方式等待异步完成。
- 每个测试 unmount。
- 每个测试恢复 timers。

---

## 5. 禁止事项

- 不修改 Strategy2 指标、评分、拒绝规则、风险计算和候选门槛。
- 不修改 Strategy1 策略。
- 不修改数据库结构或任务 API 契约。
- 不恢复缓存兜底、mootdx 或 yfinance。
- 不删除历史任务轮询。
- 不通过降低断言强度让测试通过。
- 不保留名称声称“完成态”但不推进轮询的假覆盖测试。
- 不重构无关模块。

---

## 6. 必须执行的验收

```bash
python -m pytest tests/test_strategy2_acceptance_fixes.py tests/test_strategy2_final_fixes.py tests/test_strategy2_recheck_fixes.py -W error::pytest.PytestUnhandledThreadExceptionWarning -q
python -m pytest tests/ -q
python -m compileall scanner strategy2 server.py -q

cd web
npm.cmd run test
npm.cmd run build
cd ..

rg -n "mootdx|yfinance|四数据源|全部失败.*缓存|新鲜缓存" scanner/daily_data_service.py strategy2 config.yaml docs/superpowers/specs/2026-06-10-strategy2-extreme-dry-stable-design.md
git diff --check
git status --short
```

预期：

- 重点后端测试全部通过，无线程 warning。
- 后端全量全部通过。
- 前端测试包含并通过本指令要求的新场景。
- 前端 build 通过。
- compileall 通过。
- Strategy2 生产链不出现 mootdx/yfinance。
- 不出现全源失败后使用缓存的实现或文档规则。
- diff check 无输出。
- 除本轮预期修改外无额外文件变更。

---

## 7. 交付报告要求

修复完成后报告：

1. 修复提交 Hash。
2. ROUND6-S2-001 至 ROUND6-S2-003 对应修改文件。
3. 已完成历史任务首次加载时 summary 的恢复顺序。
4. 历史运行任务完成时最终刷新的执行顺序。
5. 404、非 404 和网络异常分别显示什么。
6. 新增或重写的前端测试名称。
7. 重点后端、后端全量、前端测试、build、compileall、检索和 diff check 的精确结果。
8. 确认 Strategy2 算法、数据库结构、三源规则未被修改。
9. 未完成项必须为空。


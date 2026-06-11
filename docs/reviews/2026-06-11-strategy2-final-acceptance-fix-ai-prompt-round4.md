# Strategy2 第四轮最终验收：一次性修复指令

请修复 `docs/reviews/2026-06-11-strategy2-final-acceptance-recheck-round4.md` 中的全部问题。本轮改动应严格限定在任务 summary、ScannerConsole 状态恢复、前端运行时测试、源诊断测试和规则文档同步。

## 1. 不可改变的规则

1. 生产日线源仅 `baidu / sina / tencent`。
2. 全部在线源失败时直接标记股票失败，不使用缓存扫描。
3. 不修改策略1/策略2算法、评分、阈值和候选规则。
4. URL 的 task 参数是历史页面唯一任务上下文。
5. 最终统计必须来自数据库中的目标任务 summary。

## 2. 第一步：任务股票接口返回完整 summary

修改 `server.py` 的 `GET /api/scan/tasks/{task_id}/stocks`：

```python
summary = db.refresh_scan_task_counts(task_id)
count = summary.get(status, 0) if status else summary["total_stocks"]
return {
    "task_id": task_id,
    "strategy_type": s_type,
    "stocks": stocks,
    "total": count,
    "summary": summary,
    "page": page,
    "page_size": page_size,
}
```

要求：

- 保留当前 404 行为。
- 保留带 status 时 `total` 表示该状态总数的行为。
- `summary` 必须包含 total_stocks、processed、scanned、skipped、failed、candidate/candidates_count、latest_trade_date 和 stock_pool_source。
- 增加 API 测试验证 completed/running S1/S2 的 summary。

## 3. 第二步：修复 ScannerConsole 完成态

修改 `web/src/pages/ScannerConsole.vue`。

新增：

```js
function applyTaskSummary(summary = {}) {
  scanProgress.scanned = summary.processed ?? summary.scanned ?? 0
  scanProgress.total = summary.total_stocks ?? 0
  scanProgress.skipped = summary.skipped ?? 0
  scanProgress.failed = summary.failed ?? summary.failed_count ?? 0
  scanProgress.candidates =
    summary.candidate ?? summary.candidates_count ?? 0
  scanProgress.latestTradeDate = summary.latest_trade_date ?? ''
  scanProgress.stockPoolSource = summary.stock_pool_source ?? ''
}
```

新增统一恢复函数：

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

重写 `pollStatus()` 的核心顺序：

1. `status.running === true` 且任务匹配时，应用实时 stats。
2. `status.running === false` 且页面之前正在扫描时，使用保存的目标 task_id 调用 `refreshTaskContext()`。
3. 历史模式发现 status.task_id 不匹配时，也必须先刷新历史目标任务，再停止轮询，不能直接 return。
4. 完成日志必须在最终 summary 应用后写入。
5. 空 `stats` 不能覆盖现有数字。

修改 `applyStats()`，使用 `??` 保留缺失字段：

```js
scanProgress.scanned =
  stats.processed ?? stats.scanned ?? scanProgress.scanned
```

其他统计字段同理。

## 4. 第三步：监听 URL task 变化

引入 Vue `watch`，增加统一的 `stopPolling()` 和 `switchTaskContext()`。

必须支持：

- task A → task B。
- 浏览器后退 B → A。
- task A → 无 task 实时模式。
- 历史页面点击启动新扫描时不会创建重复轮询或继续加载旧任务。

不得只依赖 `onMounted()`。

## 5. 第四步：添加前端运行时测试

修改：

- `web/package.json`
- `web/package-lock.json`

添加：

- `vitest`
- `@vue/test-utils`
- `jsdom`
- `"test": "vitest run"`

新增：

```text
web/src/pages/__tests__/ScannerConsole.history-task.test.js
```

测试必须 mount 真实 `ScannerConsole.vue` 并 mock API/router，至少覆盖：

1. 当前 S1 不覆盖历史 S2。
2. 当前 S2 不覆盖历史 S1。
3. 历史任务完成后应用最终 summary 并刷新结果。
4. `/api/scan/status` 完成后返回 task_id=null 时不跳过最终刷新。
5. query task A → B 后展示 B。
6. 不存在任务显示错误且不展示其他任务数据。
7. 历史 S2 不显示策略1重试按钮。

## 6. 第五步：补源诊断测试

修改 `tests/test_strategy2_acceptance_fixes.py`：

- 全源失败精确断言 primary/fallback source、attempts、errors 和 source_errors JSON。
- busy 超限精确断言终态和诊断。
- `fetch_with_retry()` 直接抛异常，断言最终为 `STRATEGY2_EVALUATION_ERROR`，没有 `UnboundLocalError`。
- candidate 场景显式断言 `status_reason is None`。

## 7. 第六步：同步规则文档

修改：

- `docs/superpowers/specs/2026-06-10-strategy2-extreme-dry-stable-design.md`
- `scanner/daily_data_service.py`

要求：

- 当前 Strategy2 主设计文档中的四源全部改为三源。
- 删除 yfinance 作为正式数据源。
- 删除全部源失败后使用新鲜缓存继续扫描的规则。
- 明确全部在线源失败直接返回 data=None，并将股票标记失败。
- 明确缓存/数据库历史仅在在线拉取成功后用于合并与持久化。

## 8. 禁止事项

- 不要修改策略算法。
- 不要恢复缓存兜底、mootdx 或 yfinance。
- 不要改变 `total` 的分页语义。
- 不要仅保留最后一次轮询数字冒充最终准确统计。
- 不要只添加辅助函数单测；必须 mount 真实前端组件。
- 不要重构无关模块。

## 9. 必须执行的验收

```bash
python -m pytest tests/test_strategy2_acceptance_fixes.py tests/test_strategy2_final_fixes.py tests/test_strategy2_recheck_fixes.py -W error::pytest.PytestUnhandledThreadExceptionWarning -q
python -m pytest tests/ -q
python -m compileall scanner strategy2 server.py -q

cd web
npm run test
npm run build
cd ..

rg -n "四数据源|百度、新浪、腾讯、yfinance|全部失败.*新鲜缓存|数据源全部失败且无新鲜缓存" docs/superpowers/specs/2026-06-10-strategy2-extreme-dry-stable-design.md scanner/daily_data_service.py
git diff --check
git status --short
```

预期：

- 后端测试全部通过，无线程 warning。
- 前端运行时测试和构建全部通过。
- `rg` 对旧规则无命中。
- diff check 无输出。

## 10. 交付报告要求

交付时报告：

1. 修复前后提交 Hash。
2. ROUND4-S2-001 至 005 对应修改文件和测试。
3. 扫描完成后如何按目标 task_id 恢复最终 summary。
4. 历史任务 query 切换如何处理。
5. 前端运行时测试名称和精确通过数。
6. 后端全量测试、compileall、build 和 diff check 结果。
7. 三源/不使用缓存规则全文检索结果。
8. 未完成项必须为空。

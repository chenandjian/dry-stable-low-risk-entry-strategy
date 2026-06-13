# 代码问题检查报告

## 1. 检查范围

本次审核基于最新提交：

- 当前提交：`948b284 fix(strategy2): round2 acceptance — fix failure panel scope, history context, source convergence, terminal tests`
- 对比基线：`c14b974`
- 工作树：`strategy2-extreme-dry-stable`

重点检查：

- 策略2失败股票前端展示与历史任务入口
- 历史任务与当前运行任务的状态隔离
- 三数据源全部失败后的失败记录完整性
- 通用任务股票接口的任务存在性校验
- 六种终态测试、跨策略测试和后台线程生命周期
- `baidu / sina / tencent` 三数据源收敛
- 后端全量测试、前端构建、编译和 diff 质量门禁

---

## 2. 总体结论

`948b284` 已修复上一轮确认的失败面板作用域错误、策略2历史失败入口缺失、任务股票接口缺少 `strategy_type`、生产扫描链仍注册 mootdx/yfinance 等问题。

但本轮仍不能最终验收通过。当前剩余问题主要集中在“历史任务上下文”和“失败诊断可信度”：

1. 打开历史任务失败链接时，如果另一个扫描正在运行，页面会被当前运行任务覆盖，显示错误任务的失败股票、候选和重试按钮。
2. 策略2确实记录了所有数据源失败，但丢失了 `primary_attempts / fallback_attempts / primary_error / fallback_error`，前端会错误显示主源、备源均尝试 `0` 次。
3. 不存在的任务 ID 被 `/api/scan/tasks/{task_id}/stocks` 静默解释为策略1任务并返回 200。
4. 六终态测试没有断言每种场景的准确终态，跨策略测试还会遗留后台线程异常；目前测试可在行为错误时假通过。
5. 三数据源生产链已收敛，但旧模块、旧测试和设计文档仍保留四源/缓存回退描述，完整 pytest 仍会收集外网诊断脚本并失败。

---

## 3. 问题清单

| 编号 | 问题 | 严重程度 | 影响范围 | 是否必须修复 |
| --- | --- | --- | --- | --- |
| ROUND3-S2-001 | 历史任务页面会被当前运行任务覆盖，且策略1历史候选未按 task_id 查询 | 高 | 历史失败查看 / 候选展示 / 重试按钮 | 是 |
| ROUND3-S2-002 | 策略2失败记录丢失拉取次数和主备源错误 | 中 | 失败详情 / 故障定位 / 用户判断 | 是 |
| ROUND3-S2-003 | 不存在任务被任务股票接口当成策略1并返回 200 | 中 | API 语义 / 前端错误上下文 | 是 |
| ROUND3-S2-004 | 验收测试可假通过，并遗留后台线程异常 | 中 | 回归可信度 / CI 稳定性 | 是 |
| ROUND3-S2-005 | 三数据源收敛未完成文档、旧模块和测试清理 | 中 | 后续维护 / 全量测试 / 需求一致性 | 是 |
| ROUND3-S2-006 | 最新提交仍有两个 EOF 空白错误 | 低 | diff 质量门禁 | 是 |

---

## 4. 详细问题分析

### ROUND3-S2-001：历史任务页面会被当前运行任务覆盖

#### 问题现象

用户从策略2历史结果页点击“查看失败股票”后，若系统此刻正运行另一个任务：

- 页面可能显示当前运行任务的失败股票，而不是链接中的历史任务。
- 历史策略2任务可能按策略1加载候选。
- 历史策略2任务可能错误显示策略1专用“重新拉取”按钮。
- 历史策略1任务的候选列表未按目标任务过滤，会加载全局/最新候选。

#### 涉及模块

- `web/src/pages/ScannerConsole.vue:271`
- `web/src/pages/ScannerConsole.vue:273`
- `web/src/pages/ScannerConsole.vue:334`
- `web/src/pages/ScannerConsole.vue:352`
- `web/src/pages/ScannerConsole.vue:368`
- `web/src/pages/ScannerConsole.vue:375`
- `web/src/pages/ScannerConsole.vue:454`
- `web/src/pages/ScannerConsole.vue:463`

#### 证据链

1. 路由先把查询参数写入 `scanProgress.taskId`。
2. 页面随后无条件调用全局 `/api/scan/status`。
3. `applyStats()` 使用 `status.task_id || scanProgress.taskId`，因此只要另一个任务正在运行，查询参数任务 ID 就被覆盖。
4. `status.strategyType` 也会先写入 `activeStrategyType`。
5. `loadFailures()` 只有在 `activeStrategyType` 为空时才使用目标任务返回的 `strategy_type`，因此不会纠正错误策略类型。
6. 策略1结果加载调用 `getCandidates()`，没有传入目标 `task_id`。

#### 触发条件

1. 存在历史任务 A。
2. 当前正在运行任务 B。
3. 用户打开 `/?task=A&status=failed`。

#### 影响

这是任务上下文串线。用户看到的失败原因、候选结果和可执行按钮可能属于另一个任务，属于核心正确性问题。

#### 修复建议

历史任务路由和实时扫描模式必须分开处理：

1. 当 URL 存在 `task` 参数时，`queryTaskId` 必须是页面唯一任务上下文，不能被全局运行任务覆盖。
2. 首先调用目标任务接口获取 `strategy_type`，再加载该任务失败股票和候选。
3. 只有当 `/api/scan/status` 返回的 `task_id === queryTaskId` 时，才应用实时状态并启动轮询。
4. `loadFailures()` 在历史任务模式下必须用后端返回值覆盖 `activeStrategyType`，不能使用 `!activeStrategyType` 防护。
5. 策略1候选查询必须调用 `getCandidates({ task_id: scanProgress.taskId })`。
6. 对不存在任务显示明确错误，不要回退到当前任务或全局候选。

建议代码结构：

```js
const historicalTaskId = computed(() => route.query.task || '')

async function loadHistoricalTask(taskId) {
  scanProgress.taskId = taskId

  const taskData = await getTaskStocks(taskId, {
    status: 'failed',
    page_size: 50,
    page: 1,
  })
  if (taskData.error) throw new Error(taskData.error)

  activeStrategyType.value = taskData.strategy_type
  failures.value = taskData.stocks || []
  failuresTotal.value = taskData.total || 0
  await loadResults()

  const status = await getScanStatus()
  if (status.running && status.task_id === taskId) {
    applyStats(status)
    scanning.value = true
    pollTimer = setInterval(pollStatus, 1000)
  }
}
```

`loadResults()` 的策略1分支：

```js
const data = await getCandidates(
  scanProgress.taskId ? { task_id: scanProgress.taskId } : {}
)
```

#### 验证方式

必须增加前端运行时测试或可重复浏览器验收：

1. 当前运行策略1，打开历史策略2失败链接：仍显示历史策略2失败股票，不显示“重新拉取”。
2. 当前运行策略2，打开历史策略1失败链接：仍显示历史策略1失败股票，并显示策略1重试按钮。
3. 当前无任务运行，打开历史策略1和策略2链接：候选与失败股票均来自指定任务。
4. 打开不存在任务：显示任务不存在，不显示当前任务数据。

---

### ROUND3-S2-002：策略2失败记录丢失拉取次数和主备源错误

#### 问题现象

策略2股票在三个数据源全部失败后，前端失败列表会显示：

```text
主源 0 · 备源 0
```

展开详情时 `primary_error` 和 `fallback_error` 也为空，尽管真实请求已经发生并失败。

#### 涉及模块

- `strategy2/scanner.py:87`
- `strategy2/scanner.py:139`
- `strategy2/scanner.py:147`
- `scanner/daily_data_service.py:32`
- `web/src/pages/ScannerConsole.vue:89`

#### 证据链

`FetchResult` 已包含：

- `primary_attempts`
- `fallback_attempts`
- `primary_error`
- `fallback_error`
- `source_errors`

但策略2 `_finish_stock()` 只接受并保存 `source_errors`，没有保存其余诊断字段。

直接复现结果：

```python
{
  "status": "failed",
  "status_reason": "ALL_DATA_SOURCES_FAILED",
  "primary_source": "baidu",
  "fallback_source": "tencent",
  "primary_attempts": 0,
  "fallback_attempts": 0,
  "primary_error": None,
  "fallback_error": None,
  "source_errors": "{\"baidu\":\"attempts=2 error=baidu-error\",...}"
}
```

#### 触发条件

- 三数据源全部失败。
- 所有数据源持续 busy，超过重试上限。

#### 影响

失败股票虽然可见，但摘要信息错误，会让用户误判系统没有真正请求数据源，也降低日志和前端故障定位价值。

#### 修复建议

不要在各失败分支重复拼字段。为 `_finish_stock()` 增加 `fetch_result` 参数，统一展开并写入完整诊断信息：

```python
def _finish_stock(
    code,
    name,
    status,
    status_reason=None,
    error_detail=None,
    kline_latest_date=None,
    fetch_result=None,
):
    source_fields = {}
    if fetch_result is not None:
        source_fields = {
            "primary_source": fetch_result.primary_source,
            "fallback_source": fetch_result.fallback_source,
            "primary_attempts": fetch_result.primary_attempts,
            "fallback_attempts": fetch_result.fallback_attempts,
            "primary_error": fetch_result.primary_error,
            "fallback_error": fetch_result.fallback_error,
            "source_errors": encode_source_errors(fetch_result.source_errors),
        }

    db.update_task_stock(
        task_id,
        code,
        status=status,
        status_reason=status_reason,
        error_detail=error_detail,
        kline_latest_date=kline_latest_date,
        finished_at=_now(),
        **source_fields,
    )
```

以下终态至少应传入 `fetch_result`：

- `ALL_DATA_SOURCES_FAILED`
- 数据源 busy 超过重试次数
- 流动性过滤拒绝
- scanned
- candidate
- 候选持久化失败
- 策略评估异常（已经完成数据获取时）

#### 验证方式

1. 模拟 baidu/sina/tencent 各失败 2 次。
2. 数据库记录必须保存三个源的 `source_errors`。
3. `primary_attempts` 和 `fallback_attempts` 必须反映兼容字段定义，不能固定为 0。
4. 前端摘要和展开详情必须显示真实次数与错误。
5. busy 超限也必须保留源诊断。

---

### ROUND3-S2-003：不存在任务被任务股票接口当成策略1

#### 问题现象

请求不存在任务：

```http
GET /api/scan/tasks/not-found/stocks?status=failed
```

当前返回：

```json
{
  "task_id": "not-found",
  "strategy_type": "STRATEGY_1_CUP_HANDLE",
  "stocks": [],
  "total": 0
}
```

HTTP 状态为 `200`。

#### 涉及模块

- `server.py:506`
- `server.py:514`
- `scanner/db.py:614`

#### 可能原因

接口使用：

```python
s_type = db.get_task_strategy_type(task_id) or "STRATEGY_1_CUP_HANDLE"
```

`None` 同时表示“任务不存在”，却被当成旧任务的策略1兼容值。

#### 影响

错误链接或已删除任务会被前端当成合法策略1任务，可能继续加载全局策略1候选并显示错误操作按钮。

#### 修复建议

接口应复用明确任务存在性校验：

```python
s_type = db.get_task_strategy_type(task_id)
if s_type is None:
    return JSONResponse(
        {"error": "TASK_NOT_FOUND", "task_id": task_id},
        status_code=404,
    )
```

旧数据库中实际存在但 `strategy_type IS NULL` 的任务，已经由 `db.get_task_strategy_type()` 映射为策略1，不会受影响。

`useApi.getTaskStocks()` 也应返回 `ok/statusCode`，让前端可以区分合法空列表与 404。

#### 验证方式

- 不存在任务返回 404 `TASK_NOT_FOUND`。
- 存在的旧 NULL 策略任务仍返回策略1。
- 存在的策略2任务返回策略2。
- 合法但无失败股票的任务返回 200 和空列表。

---

### ROUND3-S2-004：验收测试可假通过，并遗留后台线程异常

#### 问题现象

六终态参数化测试看似覆盖：

- candidate
- scanned
- skipped
- all-sources-failed
- persist-failed
- evaluation-error

但它只断言状态不是 `fetching`，没有断言每个场景的准确状态和原因。任何场景错误落到另一个终态时，测试仍可通过。

此外，定向测试结果为 `53 passed`，但出现：

```text
PytestUnhandledThreadExceptionWarning
sqlite3.OperationalError: no such table: task_stocks
```

原因是策略1重试测试启动真实后台线程，测试结束后临时数据库被销毁，线程仍在访问数据库。

#### 涉及模块

- `tests/test_strategy2_acceptance_fixes.py:310`
- `tests/test_strategy2_acceptance_fixes.py:371`
- `tests/test_strategy2_acceptance_fixes.py:400`
- `tests/test_strategy2_acceptance_fixes.py:405`
- `tests/test_strategy2_acceptance_fixes.py:407`
- `tests/test_strategy2_final_fixes.py:75`

#### 修复建议

六终态测试参数必须包含准确预期：

```python
@pytest.mark.parametrize(
    "setup,expected_status,expected_reason",
    [
        ("candidate", "candidate", None),
        ("scanned", "scanned", expected_scanned_reason),
        ("skipped", "skipped", "LIQUIDITY_FILTER_REJECTED"),
        ("fail", "failed", "ALL_DATA_SOURCES_FAILED"),
        ("persist_fail", "failed", "STRATEGY2_CANDIDATE_PERSIST_FAILED"),
        ("crash", "failed", "STRATEGY2_EVALUATION_ERROR"),
    ],
)
```

每个用例必须断言：

- 准确 `status`
- 准确 `status_reason`
- `finished_at`
- summary 中对应终态计数恰好为 1
- `processed` 进度回调恰好发送一次
- 非目标终态计数为 0

删除裸 `pass` 和无意义的 `time.sleep(0.1)`。

策略1重试测试应 mock 扫描函数，并等待后台线程完成后再退出测试：

```python
done = threading.Event()

def fake_scan_all(*args, **kwargs):
    done.set()
    return {"candidates": [], "stats": {"processed": 1}}

monkeypatch.setattr(server_mod, "scan_all", fake_scan_all)
res = client.post("/api/scan/tasks/s1-task/retry-failed")
assert done.wait(timeout=2)
```

还必须补充真实前端运行时测试，覆盖 ROUND3-S2-001 的历史任务上下文。仅 `vite build` 不能证明页面行为正确。

#### 验证方式

```bash
python -m pytest tests/test_strategy2_acceptance_fixes.py tests/test_strategy2_final_fixes.py -W error::pytest.PytestUnhandledThreadExceptionWarning -q
```

预期：

- 全部通过
- 无未处理线程异常
- 六终态测试在任意终态被故意改错时会失败

---

### ROUND3-S2-005：三数据源收敛未完成文档、旧模块和测试清理

#### 问题现象

生产扫描链已经只接受：

- baidu
- sina
- tencent

直接验证表明 mootdx/yfinance 均被 `_daily_fetch_fn()` 拒绝。

但仓库仍保留：

- `scanner/mootdx_source.py`
- `scanner/yfinance_source.py`
- `tests/test_mootdx_source.py`
- `tests/test_yfinance_source.py`
- `tests/test_yfinance_hist.py`

设计文档仍多次描述“四数据源”和“全部失败后允许使用新鲜缓存”，与用户已确认的业务规则冲突。

`scanner/daily_data_service.py` 顶部注释也仍写“四数据源链”。

完整测试结果：

```text
4 failed, 450 passed
```

失败项为外网/本机环境诊断测试：

- `tests/test_akshare_hist.py::test_dongcai`
- `tests/test_tushare_hist.py::test_pro_daily`
- `tests/test_tushare_hist.py::test_old_api`
- `tests/test_yfinance_hist.py::test_yfinance_daily`

#### 影响

- 后续 AI 可能依据旧设计文档重新引入 yfinance 或缓存回退。
- `requirements.txt` 已移除 yfinance，但测试仍依赖它，干净环境测试边界不一致。
- 默认 `pytest tests/` 无法作为稳定验收门禁。

#### 修复建议

1. 删除已经明确剔除的 mootdx/yfinance 生产模块和对应单元测试；若必须保留研究代码，移到不会被生产和默认 pytest 收集的独立实验目录，并明确标注非生产。
2. 删除 `tests/test_yfinance_hist.py`。
3. 将 akshare/tushare 外网诊断脚本移出默认测试收集范围，或增加明确 integration marker 并让默认命令排除。
4. 更新 `docs/superpowers/specs/2026-06-10-strategy2-extreme-dry-stable-design.md`：
   - 所有“四数据源”改为三数据源。
   - 删除 yfinance。
   - 将“全部失败使用新鲜缓存”改为“全部在线数据源失败直接标记股票失败，不使用缓存”。
5. 更新 `scanner/daily_data_service.py` 模块注释。

#### 验证方式

```bash
rg -n "mootdx|yfinance|四数据源|全部失败.*缓存" scanner strategy2 tests docs/superpowers/specs
python -m pytest tests/ -q
```

预期：

- 不再出现生产/测试/设计中的废弃数据源描述。
- 默认全量测试不访问外网且全部通过。

---

### ROUND3-S2-006：最新提交存在 EOF 空白错误

#### 问题现象

```bash
git diff --check HEAD~1..HEAD
```

返回：

```text
docs/reviews/2026-06-10-strategy2-final-acceptance-fix-ai-prompt-round2.md:80: new blank line at EOF.
docs/reviews/2026-06-10-strategy2-final-acceptance-recheck-round2.md:421: new blank line at EOF.
```

#### 修复建议

删除两个文档末尾多余空行，确保文件仅以一个换行结束。

#### 验证方式

```bash
git diff --check
git diff --check HEAD~1..HEAD
```

两条命令均应无输出。

---

## 5. 建议修复顺序

1. 修复 ROUND3-S2-001，保证历史任务上下文绝不串线。
2. 修复 ROUND3-S2-002 和 ROUND3-S2-003，保证失败诊断和 API 语义可信。
3. 修复 ROUND3-S2-004，先让测试能准确捕获回归且不泄漏线程。
4. 完成 ROUND3-S2-005 三数据源、文档和测试边界收敛。
5. 修复 ROUND3-S2-006 并执行最终质量门禁。

---

## 6. 给修复 AI 的执行要求

1. 不要修改策略2评分公式、阈值、风险计算和候选判定规则。
2. 不要修改策略1和策略2的业务隔离原则。
3. 不要恢复任何缓存兜底；全部在线数据源失败必须直接标记失败。
4. 日线生产数据源只能是 `baidu / sina / tencent`。
5. 历史任务路由中的 `task` 参数必须优先于全局运行任务状态。
6. 不要通过隐藏前端字段解决诊断字段为 0 的问题，必须修复后端持久化。
7. 不要用宽松断言、裸 `pass`、固定 sleep 或忽略 warning 让测试通过。
8. 不要重构无关模块，不要调整整体 UI 风格。
9. 修复后更新设计文档和必要注释，避免业务规则再次漂移。
10. 最终必须执行完整验收命令，并报告精确结果。

---

## 7. 回归测试清单

- 策略2三源全部失败后直接标记 failed，不使用缓存。
- 失败股票前端显示中文原因、三源错误、真实主备源次数。
- 数据源 busy 超限后也保留完整诊断。
- 历史策略2任务在策略1运行期间仍显示自己的失败股票和候选。
- 历史策略1任务在策略2运行期间仍显示自己的失败股票和候选。
- 历史策略2任务不显示策略1重试按钮。
- 历史策略1任务显示重试按钮，且只重试该任务失败股票。
- 不存在任务返回 404，不加载全局候选。
- 六种终态分别落到准确状态和原因。
- 每个终态发送一次 processed 进度。
- 定向测试无后台线程 warning。
- 默认全量 pytest 不访问外网并全部通过。
- 前端构建通过。
- diff check 无输出。

---

## 8. 不建议修改的内容

- 不要修改策略2量干、价稳、风险比和总分计算。
- 不要修改候选分数阈值。
- 不要恢复 mootdx、yfinance 或缓存兜底。
- 不要删除失败股票展示功能。
- 不要让策略2使用策略1重试接口。
- 不要引入大型前端框架或重做页面。
- 不要修改无关数据库表结构。

---

## 9. 最终交付标准

修复完成后必须同时满足：

1. 历史任务页面始终绑定 URL 指定任务，不受其他运行任务影响。
2. 策略1和策略2历史候选、失败股票、按钮均按任务和策略隔离。
3. 三数据源全部失败后不使用缓存，失败记录包含完整源诊断。
4. 不存在任务返回 404。
5. 六终态测试准确断言状态、原因和 processed 回调。
6. 测试无后台线程异常。
7. 默认全量 pytest、compileall、前端 build 和 diff check 全部通过。
8. 文档、代码、依赖和测试都只描述/使用 baidu、sina、tencent。

---

## 本轮验证结果

```text
定向策略2测试：
53 passed, 1 PytestUnhandledThreadExceptionWarning

六终态测试：
6 passed
但测试未断言每种场景的准确终态，当前通过不构成充分证明

离线测试（排除 3 个外网诊断文件）：
449 passed, 1 第三方 DeprecationWarning

完整测试：
450 passed, 4 failed, 1 warning
4 个失败均来自默认收集的外网/环境诊断测试

compileall：
通过

前端构建：
通过

生产数据源映射：
baidu/sina/tencent accepted
mootdx/yfinance rejected

不存在任务接口复现：
错误地返回 200 + STRATEGY_1_CUP_HANDLE

策略2失败诊断复现：
source_errors 有值，但 primary/fallback attempts 为 0，errors 为 None

提交范围 diff check：
2 个 EOF 空白错误
```

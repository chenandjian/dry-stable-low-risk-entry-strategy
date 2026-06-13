# Strategy2 第三轮最终验收：一次性修复执行方案

请严格按照本文档顺序执行，修复
`docs/reviews/2026-06-11-strategy2-final-acceptance-recheck-round3.md`
中的全部问题。

目标不是让现有测试勉强通过，而是一次性修正任务上下文、失败诊断、API 语义、测试可信度和三数据源边界。完成全部步骤并通过最后的验收门禁后，才可以交付。

---

## 一、不可改变的业务规则

1. 生产日线数据源只能是 `baidu / sina / tencent`。
2. 三个在线数据源全部失败时，股票必须直接标记为 `failed`，绝不使用本地缓存继续扫描。
3. 策略1和策略2的任务、候选、失败股票及可执行操作必须严格隔离。
4. URL 中存在 `task` 参数时，页面展示的唯一任务上下文必须是该历史任务。
5. 当前正在运行的其他任务不能覆盖历史任务页面。
6. 策略2不支持策略1的“重新拉取失败股票”操作。
7. 不得修改策略2评分、阈值、风险比、策略窗口或候选判断规则。
8. 不得通过隐藏错误、删除字段、宽松断言、忽略 warning 或固定 sleep 伪造修复完成。

---

## 二、总体实施顺序

必须按以下顺序修复，避免前后端契约反复修改：

1. 修复后端任务股票接口的 404 语义。
2. 修复策略2完整数据源诊断持久化。
3. 修复前端历史任务上下文和候选查询。
4. 补齐精确后端回归测试。
5. 增加最小化前端运行时测试。
6. 消除后台测试线程泄漏。
7. 完成三数据源代码、测试和文档收敛。
8. 修复文档空白并执行完整质量门禁。

每完成一个阶段，先运行该阶段定向测试；定向测试失败时不要继续后续阶段。

---

## 三、阶段 1：修复任务股票接口的任务存在性语义

### 修改文件

- `server.py`
- `web/src/composables/useApi.js`
- `tests/test_strategy2_acceptance_fixes.py` 或新建同类 API 测试文件

### 1.1 修改后端接口

修改：

```text
GET /api/scan/tasks/{task_id}/stocks
```

当前错误实现：

```python
s_type = db.get_task_strategy_type(task_id) or "STRATEGY_1_CUP_HANDLE"
```

必须改为先验证任务存在，再查询股票和统计：

```python
@app.get("/api/scan/tasks/{task_id}/stocks")
async def get_task_stocks(
    task_id: str,
    status: str = None,
    page: int = 1,
    page_size: int = 100,
):
    s_type = db.get_task_strategy_type(task_id)
    if s_type is None:
        return JSONResponse(
            {"error": "TASK_NOT_FOUND", "task_id": task_id},
            status_code=404,
        )

    page = max(page, 1)
    page_size = min(max(page_size, 1), 500)
    offset = (page - 1) * page_size
    stocks = db.get_task_stocks(
        task_id,
        status=status,
        limit=page_size,
        offset=offset,
    )
    summary = db.summarize_task_stocks(task_id)
    count = summary.get(status, 0) if status else summary["total_stocks"]
    return {
        "task_id": task_id,
        "strategy_type": s_type,
        "stocks": stocks,
        "total": count,
        "page": page,
        "page_size": page_size,
    }
```

注意：

- `db.get_task_strategy_type()` 已经将“实际存在但 strategy_type 为 NULL 的旧任务”映射成策略1。
- 因此 `None` 只表示任务不存在，不能再使用 `or STRATEGY_1`。
- 必须在查询 `task_stocks` 和 summary 前完成任务存在性判断。

### 1.2 修改前端 API 包装

修改 `useApi.getTaskStocks()`，返回 HTTP 状态：

```js
async function getTaskStocks(taskId, params = {}) {
  const qs = new URLSearchParams(params).toString()
  const url = `${API_BASE}/scan/tasks/${taskId}/stocks${qs ? '?' + qs : ''}`
  const res = await fetch(url)
  const body = await res.json()
  return { ...body, ok: res.ok, statusCode: res.status }
}
```

不要让调用方只能通过空列表猜测任务是否存在。

### 1.3 必须增加的后端测试

至少增加以下四项：

```python
def test_task_stocks_unknown_task_returns_404(...):
    response = client.get("/api/scan/tasks/not-found/stocks")
    assert response.status_code == 404
    assert response.json()["error"] == "TASK_NOT_FOUND"

def test_task_stocks_existing_legacy_null_type_returns_s1(...):
    # 创建任务后手工把 strategy_type 更新为 NULL
    response = client.get(f"/api/scan/tasks/{task_id}/stocks")
    assert response.status_code == 200
    assert response.json()["strategy_type"] == "STRATEGY_1_CUP_HANDLE"

def test_task_stocks_existing_s2_returns_s2(...):
    assert response.json()["strategy_type"] == "STRATEGY_2_EXTREME_DRY_STABLE"

def test_task_stocks_existing_empty_failure_list_is_not_404(...):
    response = client.get(f"/api/scan/tasks/{task_id}/stocks?status=failed")
    assert response.status_code == 200
    assert response.json()["stocks"] == []
    assert response.json()["total"] == 0
```

### 阶段验收

```bash
python -m pytest tests/test_strategy2_acceptance_fixes.py -q
```

---

## 四、阶段 2：修复策略2完整数据源诊断持久化

### 修改文件

- `strategy2/scanner.py`
- `tests/test_strategy2_acceptance_fixes.py`

### 2.1 重构统一终态函数

当前 `_finish_stock()` 只保存 `source_errors`，导致主备源、尝试次数和兼容错误字段丢失。

将签名改为接收完整 `fetch_result`：

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
    summary = db.refresh_scan_task_counts(task_id)
    if progress_callback:
        progress_callback(
            "scanning",
            summary["processed"],
            summary["total_stocks"],
            f"{code} {name}",
        )
```

### 2.2 避免异常分支引用未初始化变量

在每只股票进入 `try` 前初始化：

```python
fetch_result = None
```

推荐位置：

```python
code = stock["code"]
stock_name = stock.get("name", "")
fetch_result = None
try:
    ...
```

否则 `db.update_task_stock(status="fetching")` 或 `fetch_with_retry()` 自身抛异常时，`except` 分支如果传入 `fetch_result` 会产生 `UnboundLocalError`，掩盖原始异常。

### 2.3 所有终态统一传入 fetch_result

以下调用都必须传 `fetch_result=fetch_result`：

- 数据源 busy 超过重试次数 → `failed`
- `ALL_DATA_SOURCES_FAILED` → `failed`
- 流动性过滤拒绝 → `skipped`
- 候选保存失败 → `failed`
- 候选 → `candidate`
- 未通过策略 → `scanned`
- 策略评估异常 → `failed`

示例：

```python
_finish_stock(
    code,
    stock_name,
    "failed",
    status_reason="ALL_DATA_SOURCES_FAILED",
    fetch_result=fetch_result,
)
```

删除调用方手工传入的：

```python
source_errors=encode_source_errors(fetch_result.source_errors)
```

避免存在两套诊断写入方式。

### 2.4 不要改变的行为

- 不要恢复缓存。
- 不要改变 `fetch_with_retry()` 的三源调用顺序。
- 不要改变终态名称。
- 不要吞掉数据库写入异常。
- 不要为了显示次数修改前端为固定值。

### 2.5 必须增加的测试

构造包含完整字段的 `FetchResult`：

```python
FetchResult(
    data=None,
    primary_source="baidu",
    fallback_source="tencent",
    primary_attempts=2,
    fallback_attempts=2,
    primary_error="baidu failed",
    fallback_error="tencent failed",
    source_errors={
        "baidu": "attempts=2 error=baidu failed",
        "sina": "attempts=2 error=sina failed",
        "tencent": "attempts=2 error=tencent failed",
    },
)
```

断言数据库记录：

```python
assert row["status"] == "failed"
assert row["status_reason"] == "ALL_DATA_SOURCES_FAILED"
assert row["primary_source"] == "baidu"
assert row["fallback_source"] == "tencent"
assert row["primary_attempts"] == 2
assert row["fallback_attempts"] == 2
assert row["primary_error"] == "baidu failed"
assert row["fallback_error"] == "tencent failed"
assert json.loads(row["source_errors"]) == expected_source_errors
```

还必须测试：

- busy 超限保存诊断。
- candidate/scanned/skipped 保存成功源信息。
- `fetch_with_retry()` 在返回结果前直接抛异常时，最终状态为 `failed / STRATEGY2_EVALUATION_ERROR`，且不会出现 `UnboundLocalError`。

### 阶段验收

```bash
python -m pytest tests/test_strategy2_acceptance_fixes.py -q
```

---

## 五、阶段 3：彻底修复前端历史任务上下文串线

### 修改文件

- `web/src/pages/ScannerConsole.vue`
- `web/src/composables/useApi.js`
- 前端运行时测试文件

### 3.1 明确页面的两种互斥模式

页面只能处于以下一种模式：

1. **历史任务模式**：URL 存在 `route.query.task`，页面只展示该任务。
2. **实时任务模式**：URL 不存在 task，页面跟随当前运行任务。

增加稳定变量：

```js
const routeTaskId = computed(() => String(route.query.task || ''))
const isHistoricalMode = computed(() => Boolean(routeTaskId.value))
```

### 3.2 禁止 applyStats 切换历史任务 ID

当前：

```js
scanProgress.taskId = status.task_id || scanProgress.taskId
```

这是历史任务被当前任务覆盖的根因。

将 `applyStats()` 改为只负责应用统计；任务切换由调用方明确控制：

```js
function applyStats(status, { applyTaskId = true } = {}) {
  const stats = status.stats || {}
  if (applyTaskId && status.task_id) {
    scanProgress.taskId = status.task_id
  }
  ...
}
```

历史任务模式调用时必须使用：

```js
applyStats(status, { applyTaskId: false })
```

并且只有 `status.task_id === routeTaskId.value` 时才允许调用。

### 3.3 新增统一历史任务加载函数

不要再通过策略1任务列表猜测任务类型。通用任务股票接口已经能返回准确 `strategy_type`。

实现：

```js
async function loadHistoricalTask(taskId) {
  scanProgress.taskId = taskId
  scanning.value = false
  activeStrategyType.value = null
  scanError.value = ""

  const data = await getTaskStocks(taskId, {
    status: "failed",
    page_size: 50,
    page: 1,
  })

  if (!data.ok) {
    failures.value = []
    failuresTotal.value = 0
    discoveries.value = []
    scanError.value = data.error === "TASK_NOT_FOUND"
      ? `任务不存在：${taskId}`
      : "历史任务加载失败"
    return false
  }

  activeStrategyType.value = data.strategy_type
  failures.value = data.stocks || []
  failuresTotal.value = data.total || 0

  await loadResults()

  const status = await getScanStatus()
  if (status.running && status.task_id === taskId) {
    applyStats(status, { applyTaskId: false })
    scanning.value = true
    pollTimer = setInterval(pollStatus, 1000)
  }
  return true
}
```

### 3.4 重写 onMounted 流程

必须先分流历史/实时模式：

```js
onMounted(async () => {
  if (routeTaskId.value) {
    await loadHistoricalTask(routeTaskId.value)
  } else {
    await loadLiveTask()
  }

  updateTime()
  clockTimer = setInterval(updateTime, 1000)
})
```

`loadLiveTask()` 才允许：

- 调用全局 `getScanStatus()`。
- 使用 `status.task_id` 更新页面任务 ID。
- 使用 `status.strategyType` 更新策略类型。
- 启动全局轮询。

删除历史任务通过 `getScanTasks()` 猜策略类型的旧逻辑。

### 3.5 修复 pollStatus

历史任务模式下，只允许轮询相同任务：

```js
async function pollStatus() {
  const status = await getScanStatus()

  if (
    isHistoricalMode.value
    && status.task_id !== routeTaskId.value
  ) {
    scanning.value = false
    if (pollTimer) clearInterval(pollTimer)
    return
  }

  applyStats(status, { applyTaskId: !isHistoricalMode.value })
  ...
}
```

不能把另一个任务的 discoveries、失败数或策略类型写入历史页面。

### 3.6 修复 loadFailures

历史模式加载目标任务时，后端返回的策略类型必须覆盖当前值：

```js
if (data.strategy_type) {
  activeStrategyType.value = data.strategy_type
}
```

删除：

```js
&& !activeStrategyType.value
```

同时处理 `!data.ok`，不能把 404 当成合法空失败列表。

### 3.7 修复策略1历史候选查询

当前策略1分支调用无参数 `getCandidates()`，会获取全局/最新候选。

改为：

```js
const params = scanProgress.taskId
  ? { task_id: scanProgress.taskId }
  : {}
const data = await getCandidates(params)
```

策略2继续调用：

```js
getStrategy2Candidates(scanProgress.taskId)
```

### 3.8 重新开始扫描时清空历史上下文

如果用户在历史任务页面点击开始新扫描，应先导航回无 task 参数页面，避免新任务仍处于历史模式：

```js
if (routeTaskId.value) {
  await router.replace({ path: "/", query: {} })
}
```

然后再启动扫描。策略1和策略2启动函数都要处理。

### 3.9 前端运行时测试方案

当前前端没有测试框架。为一次性完成验收，采用最小化方案：

- 添加 `vitest`、`@vue/test-utils`、`jsdom` 到 `devDependencies`。
- 在 `web/package.json` 增加 `"test": "vitest run"`。
- 只新增与本问题相关的测试，不扩展到无关页面。

建议新增：

```text
web/src/pages/__tests__/ScannerConsole.history-task.test.js
```

至少测试：

1. 当前运行策略1，URL 指向历史策略2：页面保留历史策略2任务 ID；显示策略2失败；不显示“重新拉取”。
2. 当前运行策略2，URL 指向历史策略1：页面保留历史策略1任务 ID；策略1候选请求携带该 task_id；显示“重新拉取”。
3. URL 指向不存在任务：显示“任务不存在”；不请求候选；不显示当前任务数据。
4. 当前运行任务 ID 与 URL 历史任务 ID 相同时：允许应用实时进度。
5. 当前运行任务 ID 与 URL 不同时：禁止应用实时进度和 discoveries。

mock `useApi()`、`useRoute()` 和 `useRouter()`，断言实际调用参数和渲染结果，不要只测试独立字符串函数。

### 阶段验收

```bash
cd web
npm run test
npm run build
```

---

## 六、阶段 4：让六终态测试真正能抓住错误

### 修改文件

- `tests/test_strategy2_acceptance_fixes.py`

### 4.1 参数必须包含准确预期

改成：

```python
@pytest.mark.parametrize(
    "setup,expected_status,expected_reason",
    [
        ("candidate", "candidate", None),
        ("scanned", "scanned", EXPECTED_SCANNED_REASON),
        ("skipped", "skipped", "LIQUIDITY_FILTER_REJECTED"),
        ("fail", "failed", "ALL_DATA_SOURCES_FAILED"),
        (
            "persist_fail",
            "failed",
            "STRATEGY2_CANDIDATE_PERSIST_FAILED",
        ),
        ("crash", "failed", "STRATEGY2_EVALUATION_ERROR"),
    ],
)
```

`EXPECTED_SCANNED_REASON` 必须基于当前引擎真实返回值确定，禁止用 `is not None` 或包含关系替代准确断言。

### 4.2 收集 progress_callback

```python
events = []

def on_progress(stage, current, total, detail, discovery=None):
    events.append({
        "stage": stage,
        "current": current,
        "total": total,
        "detail": detail,
        "discovery": discovery,
    })
```

调用扫描器时传入回调。

### 4.3 每个场景必须断言

```python
assert row["status"] == expected_status
assert row["status_reason"] == expected_reason
assert row["finished_at"] is not None

assert summary[expected_status] == 1
for other_status in {"candidate", "scanned", "skipped", "failed"} - {expected_status}:
    assert summary[other_status] == 0

processed_events = [e for e in events if e["stage"] == "scanning"]
assert len(processed_events) == 1
assert processed_events[0]["current"] == 1
assert processed_events[0]["total"] == 1
```

候选场景还要断言恰好一个 discovery 回调；其他五种场景不得发送 discovery。

### 4.4 删除无效代码

删除：

- `pass  # handled by config below`
- `import time`
- `time.sleep(0.1)`
- `status != "fetching"` 这种过于宽松、不能证明准确终态的核心断言

可以保留 `status != fetching` 作为附加断言，但不能替代准确状态断言。

### 阶段验收

```bash
python -m pytest tests/test_strategy2_acceptance_fixes.py::TestSixTerminalStatesParametrized -vv
```

---

## 七、阶段 5：消除后台测试线程泄漏

### 修改文件

- `tests/test_strategy2_final_fixes.py`
- 如确有必要，小范围修改 `server.py` 以提高可测试性，但不能改变生产异步行为

### 问题根因

`test_strategy1_retry_still_works` 调用真实重试接口。接口启动 daemon 后台线程后立即返回，pytest 随后销毁 `tmp_path` 数据库，后台线程继续访问已销毁/已切换的数据库，产生：

```text
PytestUnhandledThreadExceptionWarning
sqlite3.OperationalError: no such table: task_stocks
```

### 修复步骤

1. 在测试中 mock 实际扫描执行函数，不访问外网，不运行真实扫描器。
2. 使用 `threading.Event` 确认后台执行函数已经完成。
3. 测试退出前等待事件完成。
4. 断言接口不是策略不匹配错误，并断言 mock 扫描函数收到目标失败股票。
5. 测试后调用 `_clear_running()` 清理服务内存状态。

示例：

```python
done = threading.Event()
received = {}

def fake_scan_all(config, progress_callback=None, task_id=None, stocks=None, **kwargs):
    received["task_id"] = task_id
    received["stocks"] = stocks
    done.set()
    return {
        "candidates": [],
        "stats": {
            "total_stocks": len(stocks or []),
            "processed": len(stocks or []),
            "failed": 0,
            "skipped": 0,
            "candidates_found": 0,
        },
    }

monkeypatch.setattr(server_mod, "scan_all", fake_scan_all)

response = client.post("/api/scan/tasks/s1-task/retry-failed")
assert response.status_code == 200
assert done.wait(timeout=2), "retry worker did not finish"
assert received["task_id"] == "s1-task"
assert [s["code"] for s in received["stocks"]] == ["000001"]
server_mod._clear_running()
```

如果 `server.py` 实际导入别名不同，必须 mock `retry_failed_stocks()` 运行时真正调用的符号，而不是错误模块路径。

### 阶段验收

```bash
python -m pytest tests/test_strategy2_final_fixes.py -W error::pytest.PytestUnhandledThreadExceptionWarning -q
```

必须 0 warning 通过。

---

## 八、阶段 6：完成三数据源和默认测试边界收敛

### 修改/删除范围

生产日线数据源只允许：

```text
baidu
sina
tencent
```

### 6.1 删除废弃数据源代码和测试

删除：

- `scanner/mootdx_source.py`
- `scanner/yfinance_source.py`
- `tests/test_mootdx_source.py`
- `tests/test_yfinance_source.py`
- `tests/test_yfinance_hist.py`

删除前先使用 `rg` 确认没有生产导入。不要删除 AKShare 股票池能力；AKShare 不是生产 OHLC 数据源。

### 6.2 移动外网诊断脚本

以下文件是人工数据源诊断脚本，不应被默认 pytest 收集：

- `tests/test_akshare_hist.py`
- `tests/test_tushare_hist.py`

推荐移动到：

```text
tools/data_source_diagnostics/akshare_hist.py
tools/data_source_diagnostics/tushare_hist.py
```

要求：

- 文件名不以 `test_` 开头。
- 不进入默认 pytest。
- 保留人工运行入口和用途说明。
- 不要通过在测试中捕获所有异常然后 `pass` 来伪造通过。

### 6.3 更新注释和设计文档

修改：

- `scanner/daily_data_service.py`
- `docs/superpowers/specs/2026-06-10-strategy2-extreme-dry-stable-design.md`

逐处替换：

- “四数据源” → “三数据源”
- 删除 yfinance/mootdx 作为生产源的描述
- “全部失败时允许使用新鲜缓存” → “全部在线数据源失败时直接标记股票失败，不使用缓存”

注意：

- 可以保留“成功在线拉取后与本地历史数据合并并入库”的行为说明。
- 必须删除的是“全部在线源失败后使用缓存继续扫描”的行为。
- 不要误删数据库 OHLC 持久化和成功拉取后的历史合并。

### 6.4 增加边界测试

保留并加强以下断言：

```python
assert DEFAULT_DAILY_SOURCES == ["baidu", "sina", "tencent"]

with pytest.raises(ValueError):
    _daily_fetch_fn("mootdx")

with pytest.raises(ValueError):
    _daily_fetch_fn("yfinance")
```

还应增加配置测试，确认 `config.yaml` 只包含三源。

### 阶段验收

```bash
rg -n "mootdx|yfinance|四数据源|全部失败.*缓存" scanner strategy2 tests docs/superpowers/specs
python -m pytest tests/ -q
```

`rg` 允许命中的内容只能是明确证明废弃源被拒绝的测试，不能存在生产导入、配置项或错误设计描述。

---

## 九、阶段 7：修复 diff 和文档质量门禁

删除以下文件末尾多余空行：

- `docs/reviews/2026-06-10-strategy2-final-acceptance-fix-ai-prompt-round2.md`
- `docs/reviews/2026-06-10-strategy2-final-acceptance-recheck-round2.md`

确保所有新增/修改文本文件：

- 没有行尾空格。
- 文件末尾只有一个换行。
- 没有多余空白行。

验证：

```bash
git diff --check
```

注意：最终修复提交生成后，应检查本次完整修复范围，不要只检查旧提交：

```bash
git diff --check <修复前提交>..HEAD
```

---

## 十、最终测试矩阵

### 后端 API

| 场景 | 预期 |
| --- | --- |
| 不存在任务查询 stocks | 404 `TASK_NOT_FOUND` |
| 旧 NULL 策略任务查询 stocks | 200 + Strategy1 |
| Strategy2 任务查询 stocks | 200 + Strategy2 |
| 合法任务无失败股票 | 200 + 空列表 + total=0 |

### 策略2终态

| 场景 | status | status_reason |
| --- | --- | --- |
| 候选 | candidate | `None` |
| 非候选正常评估 | scanned | 引擎返回的准确原因 |
| 流动性过滤 | skipped | `LIQUIDITY_FILTER_REJECTED` |
| 三源全部失败 | failed | `ALL_DATA_SOURCES_FAILED` |
| 候选保存失败 | failed | `STRATEGY2_CANDIDATE_PERSIST_FAILED` |
| 策略评估异常 | failed | `STRATEGY2_EVALUATION_ERROR` |

每个终态必须：

- 有 `finished_at`。
- summary 只增加对应终态。
- 恰好发送一次 scanning/processed 回调。
- 仅 candidate 发送 discovery。

### 前端历史任务

| URL 任务 | 当前运行任务 | 预期 |
| --- | --- | --- |
| 历史 S2 | 当前 S1 | 保留 S2 上下文，不显示重试 |
| 历史 S1 | 当前 S2 | 保留 S1 上下文，候选按 task_id 查询 |
| 历史 S2 | 同一 S2 正在运行 | 允许实时更新该任务 |
| 不存在任务 | 任意 | 显示任务不存在，不展示其他任务数据 |

### 数据源诊断

| 场景 | 预期 |
| --- | --- |
| 三源全部失败 | failed，不使用缓存，保存三源错误 |
| busy 超限 | failed，保存次数和错误 |
| 在线源成功 | 可合并已有历史并保存成功源诊断 |

---

## 十一、最终验收命令

所有命令必须执行并报告精确结果：

```bash
# 1. 精确终态和 API 测试
python -m pytest tests/test_strategy2_acceptance_fixes.py -q

# 2. 后台线程必须无 warning
python -m pytest tests/test_strategy2_final_fixes.py -W error::pytest.PytestUnhandledThreadExceptionWarning -q

# 3. 策略2全部重点回归
python -m pytest tests/test_strategy2_acceptance_fixes.py tests/test_strategy2_final_fixes.py tests/test_strategy2_recheck_fixes.py -W error::pytest.PytestUnhandledThreadExceptionWarning -q

# 4. 默认全量测试，不得访问外网，不得失败
python -m pytest tests/ -q

# 5. Python 编译
python -m compileall scanner strategy2 server.py -q

# 6. 前端运行时测试和构建
cd web
npm run test
npm run build
cd ..

# 7. 三数据源和规则全文检查
rg -n "mootdx|yfinance|四数据源|全部失败.*缓存" scanner strategy2 tests docs/superpowers/specs

# 8. 代码质量
git diff --check
git status --short
```

如果任一命令失败，不得宣称完成。

---

## 十二、禁止事项

- 不要修改策略2算法和评分规则。
- 不要恢复缓存兜底。
- 不要恢复 mootdx/yfinance。
- 不要删除 AKShare 股票池能力。
- 不要让策略2走策略1重试接口。
- 不要把历史任务页面重定向到当前运行任务。
- 不要使用裸 `pass`、宽松状态断言、固定 sleep 或忽略 warning。
- 不要将外网诊断测试改成永远通过；应移出默认 pytest。
- 不要大规模重构无关模块。
- 不要调整整体 UI 风格。
- 不要删除失败股票展示及其详细错误信息。

---

## 十三、交付报告格式

修复完成后必须按以下格式报告：

```markdown
# Strategy2 Round 3 修复交付报告

## 1. 提交信息
- 修复前提交：
- 修复后提交：

## 2. 问题修复映射
| 问题编号 | 修改文件 | 修复说明 | 对应测试 |
| --- | --- | --- | --- |
| ROUND3-S2-001 | ... | ... | ... |

## 3. 历史任务隔离说明
- URL task 如何成为唯一上下文：
- 如何防止当前运行任务覆盖：
- 策略1/策略2候选如何按任务加载：

## 4. 数据源失败诊断
- 保存字段：
- 三源全部失败行为：
- busy 超限行为：

## 5. 测试结果
- 定向测试：
- 线程 warning 门禁：
- 默认全量测试：
- 前端运行时测试：
- 前端构建：
- compileall：
- diff check：

## 6. 全文检索结果
- mootdx/yfinance：
- 四数据源旧描述：
- 全部失败使用缓存旧描述：

## 7. 未完成项
- 必须为空；如不为空，不得宣称最终完成。
```

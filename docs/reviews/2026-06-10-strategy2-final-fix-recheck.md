# Strategy2 修复后最终复审与一次性修复方案

## 1. 检查范围

本次复审针对提交：

- 当前提交：`d20dc4b fix(strategy2): resolve all 7 recheck issues (RECHECK-S2-001~007)`
- 对比基线：`136e48f fix(strategy2): resolve all 11 bugs from code audit (BUG-S2-001~011)`

重点检查范围：

- Strategy1 / Strategy2 任务与 API 隔离
- Strategy2 扫描终态、进度回调和候选持久化
- 扫描控制台刷新恢复与 Strategy2 结果页
- 多数据源全部失败后的缓存回退
- 上一轮 `RECHECK-S2-001~007` 修复结果
- 后端测试、前端构建和真实接口复现

---

## 2. 总体结论

上一轮七个问题中的数据窗口校验、ISO 日期校验、未知任务类型拒绝、Strategy2 候选接口类型校验等主要修复已经生效。

但当前版本仍不能作为最终完成版本。最严重的问题是：通用“失败重试”和“重新评估”接口仍接受 Strategy2 任务，其中失败重试会把 Strategy2 任务直接送入 Strategy1 扫描器，并把运行中策略类型设置成 `STRATEGY_1_CUP_HANDLE`。这会造成任务状态、候选结果和实际执行策略不一致。

此外还存在候选终态没有发送 processed 进度、页面刷新时先加载错误策略结果、Strategy2 结果页不读取任务链接、长假缓存被错误拒绝、Strategy1 任务列表混入运行中的 Strategy2 任务等问题。

建议完成本报告中的五项修复后，再进行最终验收。

---

## 3. 上一轮问题复核结果

| 上一轮编号 | 复核结论 | 说明 |
| --- | --- | --- |
| RECHECK-S2-001 | 部分修复 | 模板变量作用域已修复，状态轮询可恢复策略类型；首次刷新顺序和结果页任务链接仍未修复 |
| RECHECK-S2-002 | 部分修复 | 已拒绝未来日期，但固定三天规则仍错误拒绝长假期间的最新交易日缓存 |
| RECHECK-S2-003 | 部分修复 | Strategy2 候选接口和 DB 历史任务已隔离；重试、重评、Strategy1 候选及运行中任务列表仍未隔离 |
| RECHECK-S2-004 | 已修复 | 策略窗口外的无效前缀数据不再阻断策略评估 |
| RECHECK-S2-005 | 已修复 | Scanner 使用完整配置；未知中断任务类型会失败退出，不再默认执行 Strategy1 |
| RECHECK-S2-006 | 部分修复 | 失败、跳过、普通扫描已统一回调；候选成功路径仍缺少 processed 回调 |
| RECHECK-S2-007 | 已修复 | 日期现使用 `date.fromisoformat()` 校验并按解析结果判断顺序 |

---

## 4. 问题清单

| 编号 | 问题 | 严重程度 | 影响范围 | 是否必须修复 |
| --- | --- | --- | --- | --- |
| FINAL-S2-001 | Strategy2 任务仍可进入 Strategy1 重试、重评和候选接口 | 高 | 策略正确性、任务状态、候选数据 | 是 |
| FINAL-S2-002 | Strategy2 候选成功路径缺少 processed 进度回调 | 高 | 扫描进度、前端状态、任务完成判断 | 是 |
| FINAL-S2-003 | 前端刷新恢复和 Strategy2 结果页任务链接仍不完整 | 中 | 用户看到的结果、刷新恢复、任务导航 | 是 |
| FINAL-S2-004 | 缓存新鲜度固定为三自然日，长假期间错误拒绝有效缓存 | 中 | 数据回退能力、全市场扫描完整性 | 是 |
| FINAL-S2-005 | Strategy1 任务列表会混入当前运行中的 Strategy2 任务 | 中 | 任务中心、操作入口、策略隔离 | 是 |

---

## 5. 详细问题分析

### FINAL-S2-001：Strategy2 任务仍可进入 Strategy1 重试、重评和候选接口

#### 问题现象

使用 Strategy2 任务 ID 调用以下 Strategy1 接口时，服务端没有拒绝：

- `POST /api/scan/tasks/{task_id}/retry-failed`
- `POST /api/scan/tasks/{task_id}/re-evaluate`
- `GET /api/candidates?task_id={task_id}`

真实接口复现结果：

```text
POST /api/scan/tasks/s2-failed/retry-failed
200 {"task_id":"s2-failed","status":"retry_started","retry_count":1}
运行中 strategy_type = STRATEGY_1_CUP_HANDLE

POST /api/scan/tasks/s2-failed/re-evaluate
200 {"task_id":"s2-failed","status":"re_evaluating"}

GET /api/candidates?task_id=s2-failed
200 {"candidates":[],"total":0}
```

#### 涉及模块

- `server.py:488`：`retry_failed_stocks`
- `server.py:537`：`re_evaluate_task_endpoint`
- `server.py:581`：`get_candidates`
- `scanner/db.py:614`：`get_task_strategy_type`

#### 原因

三个接口都没有在执行前校验任务的 `strategy_type`。

其中失败重试调用：

```python
_set_running(task_id, "failed_only")
scan_all(config, task_id=task_id, stocks=stocks, retry_policy="failed_only")
```

`_set_running` 默认策略类型是 Strategy1，`scan_all` 也是 Strategy1 扫描器，因此 Strategy2 任务会被错误送入 Strategy1。

#### 影响

- Strategy2 失败股票会按 Strategy1 规则重扫。
- 同一任务 ID 下可能出现策略类型、候选表和执行逻辑互相矛盾。
- 重评会调用仅适用于 Strategy1 的 `re_evaluate_task`。
- 前端收到空结果而不是明确的策略类型错误，掩盖调用错误。

#### 一次性修复方案

在 `server.py` 增加统一任务类型校验函数，所有绑定具体策略的接口必须复用：

```python
def _require_task_strategy(task_id: str, expected: str):
    actual = db.get_task_strategy_type(task_id)
    if actual is None:
        return None, JSONResponse(
            {"error": "TASK_NOT_FOUND", "task_id": task_id},
            status_code=404,
        )
    if actual != expected:
        return None, JSONResponse(
            {
                "error": "TASK_STRATEGY_MISMATCH",
                "task_id": task_id,
                "expected_strategy_type": expected,
                "actual_strategy_type": actual,
            },
            status_code=400,
        )
    return actual, None
```

应用到：

1. `GET /api/candidates?task_id=...`：只接受 Strategy1。
2. Strategy1 候选详情接口：只接受 Strategy1。
3. `POST /api/scan/tasks/{task_id}/re-evaluate`：只接受 Strategy1。设计文档明确 Strategy2 重评不在范围内，因此 Strategy2 必须返回明确错误，不得静默调用 Strategy1。
4. `POST /api/scan/tasks/{task_id}/retry-failed`：
   - 推荐按任务类型分发到对应扫描器；
   - 如果当前尚未实现 Strategy2 失败重试，则明确返回 `400/409 STRATEGY2_RETRY_NOT_SUPPORTED`；
   - 绝对不能回退到 Strategy1。
5. `GET /api/strategy2/candidates` 和详情接口继续只接受 Strategy2。

不要仅在前端隐藏按钮，后端必须独立防御。

#### 验证方式

为每个策略绑定接口增加参数化 API 测试：

```python
@pytest.mark.parametrize("url,method", [
    ("/api/candidates?task_id=s2-task", "get"),
    ("/api/scan/tasks/s2-task/re-evaluate", "post"),
    ("/api/scan/tasks/s2-task/retry-failed", "post"),
])
def test_strategy1_endpoints_reject_strategy2_task(...):
    ...
    assert response.status_code in (400, 409)
    assert response.json()["error"] in {
        "TASK_STRATEGY_MISMATCH",
        "STRATEGY2_RETRY_NOT_SUPPORTED",
    }
```

同时验证 Strategy1 正常路径不受影响。

---

### FINAL-S2-002：Strategy2 候选成功路径缺少 processed 进度回调

#### 问题现象

当股票成为 Strategy2 候选时，数据库最终统计中的 `processed` 会增加，但回调只发送 `discovery`，不会发送 `scanning` processed 进度。

真实复现回调：

```text
[("discovery", 1, 1)]
```

没有对应的：

```text
("scanning", 1, 1)
```

#### 涉及模块

- `strategy2/scanner.py:87`：`_finish_stock`
- `strategy2/scanner.py:189-204`：候选成功分支
- `tests/test_strategy2_recheck_fixes.py:277`：当前进度测试

#### 原因

失败、跳过、普通扫描路径都调用 `_finish_stock()`；候选路径单独调用 `db.update_task_stock(status="candidate")`，随后只发送 discovery 回调。

当前测试只检查源码字符串中是否存在 `progress_callback`：

```python
source = inspect.getsource(scan_strategy2_all)
assert "progress_callback" in source
```

该测试不能证明每个终态都发送 processed 回调。

#### 影响

- 前端处理数量可能落后于数据库真实状态。
- 最后一只股票为候选时，用户可能只看到候选发现，处理进度未到 100%。
- 回调驱动的任务状态与最终 DB 汇总不一致。

#### 一次性修复方案

让统一终态函数支持候选状态，并在候选持久化成功后调用：

```python
db.upsert_strategy2_candidate(task_id, discovery)

with candidate_lock:
    candidate_by_code[code] = evaluation

_finish_stock(
    code,
    "candidate",
    kline_latest_date=latest_trade_date,
)

if progress_callback:
    progress_callback(
        "discovery",
        len(candidate_by_code),
        len(stocks),
        f"{code} {stock.get('name', '')}",
        discovery,
    )
```

候选状态只更新一次，不要保留原有重复的 `db.update_task_stock(status="candidate")`。

建议让 `_finish_stock` 接收 `stock_name`，不要依赖 worker 闭包中的可变 `stock` 变量：

```python
def _finish_stock(code, name, status, ...):
    ...
    progress_callback("scanning", ..., f"{code} {name}")
```

#### 验证方式

删除源码检查式测试，改成真实行为测试，分别模拟：

- candidate
- scanned
- skipped
- failed
- candidate persistence failed

每个终态都必须断言：

1. 数据库状态正确。
2. 至少收到一次 `stage == "scanning"` 回调。
3. `current` 单调递增且最终等于 `total`。
4. candidate 额外收到一次 discovery 回调。
5. 同一股票不会重复增加 processed。

---

### FINAL-S2-003：前端刷新恢复和 Strategy2 结果页任务链接仍不完整

#### 问题现象

扫描控制台刷新时，`onMounted` 先执行 `loadResults()`，之后才请求扫描状态并获知当前策略类型。

因此在 Strategy2 扫描期间刷新页面，首次结果请求仍按 Strategy1 执行；策略类型要等下一次轮询才恢复，而且恢复后没有立即重新加载 Strategy2 结果。

另外，`Strategy2Results.vue` 加载任务列表后没有读取 `route.query.task`，从任务中心跳转到带任务 ID 的 Strategy2 结果页时，不会自动选择和加载该任务。

#### 涉及模块

- `web/src/pages/ScannerConsole.vue:404`：`onMounted`
- `web/src/pages/ScannerConsole.vue:302`：`loadResults`
- `web/src/pages/Strategy2Results.vue`：`mounted`
- `tests/test_strategy2_recheck_fixes.py`：前端契约测试

#### 原因

`activeStrategyType` 只在 `pollStatus()` 中恢复；首次 mounted 状态请求仅执行 `applyStats(status)`，没有先设置策略类型。

现有后端契约测试断言过弱：

```python
assert "strategyType" in data or data.get("running")
```

只要 `running=True`，即使 `strategyType` 缺失或错误也会通过。

#### 一次性修复方案

调整 `ScannerConsole.vue` mounted 顺序：

```javascript
onMounted(async () => {
  const queryTaskId = route.query.task

  try {
    const status = await getScanStatus()
    applyStats(status)
    activeStrategyType.value = status.strategyType || null

    if (queryTaskId) {
      scanProgress.taskId = queryTaskId
    }

    await loadResults()
    await loadFailures()

    if (status.running) {
      scanning.value = true
      pollTimer = setInterval(pollStatus, 1000)
    }
  } catch (e) {
    console.error("Check status on mount failed:", e)
  }
  ...
})
```

`Strategy2Results.vue` 使用 `useRoute()` 或 Options API 的 `this.$route`：

```javascript
const queryTaskId = this.$route.query.task
if (queryTaskId && this.tasks.some(t => t.id === queryTaskId)) {
  this.selectedTaskId = queryTaskId
  await this.loadCandidates()
}
```

如果任务不存在或策略类型不匹配，应显示明确错误，不要默默展示空列表。

#### 验证方式

增加前端组件测试或端到端测试：

1. 后端返回运行中的 Strategy2。
2. 刷新 ScannerConsole。
3. 首次候选请求必须是 Strategy2 API，不能先请求 Strategy1 候选。
4. 打开 `/strategy2/results?task=<s2-task>`。
5. 页面应自动选中该任务并加载候选。
6. 后端契约测试改为严格断言：

```python
assert data["running"] is True
assert data["strategyType"] == "STRATEGY_2_EXTREME_DRY_STABLE"
```

---

### FINAL-S2-004：缓存新鲜度固定为三自然日，长假期间错误拒绝有效缓存

#### 问题现象

当前 `_is_cache_fresh` 使用：

```python
return (today - latest_date).days <= 3
```

在国庆、春节等长假期间，缓存日期虽然是最近一个真实交易日，仍会因为超过三自然日被判定为过期。

复现：

```text
today = 2026-10-08
latest cache date = 2026-09-30
_is_cache_fresh(...) = False
```

#### 涉及模块

- `scanner/daily_data_service.py:195`：`_is_cache_fresh`
- `scanner/daily_data_service.py:145`：全部数据源失败后的缓存回退
- `tests/test_strategy2_recheck_fixes.py:149-190`

#### 原因

代码用自然日差近似交易日新鲜度，没有交易日历，也没有区分交易日盘中、收盘后、周末和长假。

#### 影响

长假期间或长假后数据源暂时失败时，系统会拒绝本应可用的最新交易日缓存，导致股票被标记为数据源全部失败，降低扫描完整性。

#### 一次性修复方案

不要继续增加固定自然日阈值。应定义“当前时点期望的最新交易日”，再比较缓存日期。

推荐实现：

```python
def expected_latest_trade_date(now, trading_calendar) -> date:
    # 交易日收盘前，最新完整日线应为上一交易日
    # 交易日收盘后，最新完整日线应为当天
    # 周末或节假日，应为最近一个交易日
    ...

def _is_cache_fresh(cached, *, now=None, trading_calendar=None) -> bool:
    latest = date.fromisoformat(cached[-1]["date"])
    expected = expected_latest_trade_date(now or datetime.now(), trading_calendar)
    return latest == expected
```

交易日历应使用项目已有能力或轻量、可配置的交易日集合，不要在每只股票扫描时请求远程日历。至少应允许测试注入 `is_trading_day` / `previous_trading_day`。

如果本轮暂时无法接入交易日历，必须把规则抽成可注入函数，并显式配置假期；不要保留“3 天覆盖节假日”的错误注释。

#### 验证方式

增加以下测试：

- 周五收盘后接受周五缓存。
- 周一开盘前接受上周五缓存。
- 周一收盘后拒绝上周五缓存。
- 周末接受上周五缓存。
- 国庆长假期间接受 9 月 30 日缓存。
- 国庆后首个交易日收盘前接受 9 月 30 日缓存。
- 国庆后首个交易日收盘后要求当天缓存。
- 未来日期始终拒绝。
- 所有数据源失败时，`fetch_with_retry()` 对新鲜缓存返回 `from_cache=True`。
- 所有数据源失败时，过期缓存返回 `data=None`。

---

### FINAL-S2-005：Strategy1 任务列表会混入当前运行中的 Strategy2 任务

#### 问题现象

`GET /api/scan/tasks` 已对数据库历史任务筛选 Strategy1，但会无条件把内存中的当前运行任务插入列表。

真实复现：

```text
当前运行任务：
id = live-s2
strategy_type = STRATEGY_2_EXTREME_DRY_STABLE

GET /api/scan/tasks
200 {"tasks":[{"id":"live-s2", ...}]}
```

#### 涉及模块

- `server.py:431`：`list_tasks`
- `server.py:455`：Strategy1 DB 历史任务筛选

#### 原因

首段逻辑只判断 `_running["running"]`，未判断 `_running["strategy_type"]`。

#### 影响

- Strategy1 任务中心显示 Strategy2 任务。
- 用户可能从错误页面触发重试、重评等 Strategy1 操作。
- API 返回内容没有 `strategy_type`，前端无法自行区分。

#### 一次性修复方案

只有当前运行任务是 Strategy1 时，才添加到 `/api/scan/tasks`：

```python
if (
    _running["running"]
    and _running.get("strategy_type", "STRATEGY_1_CUP_HANDLE")
        == "STRATEGY_1_CUP_HANDLE"
):
    ...
```

同时建议任务列表每项都返回 `strategy_type`，避免后续页面误判。

`/api/strategy2/tasks` 同样应负责展示 Strategy2 当前运行任务，且不能混入 Strategy1。

#### 验证方式

增加 API 测试：

1. 内存中运行 Strategy2 时，`GET /api/scan/tasks` 不包含该任务。
2. 内存中运行 Strategy1 时，`GET /api/strategy2/tasks` 不包含该任务。
3. 两类历史任务分别只出现在对应列表。
4. 列表项包含正确的 `strategy_type`。

---

## 6. 建议修复顺序

1. 先修复 FINAL-S2-001，彻底阻止跨策略执行。
2. 修复 FINAL-S2-005，保证任务入口和任务列表隔离。
3. 修复 FINAL-S2-002，统一所有股票终态和进度回调。
4. 修复 FINAL-S2-003，完成页面刷新恢复与任务链接。
5. 修复 FINAL-S2-004，建立可测试的交易日缓存规则。
6. 补齐真实行为测试，最后运行全量回归与前端构建。

---

## 7. 给修复 AI 的执行要求

请严格按以下要求修复：

1. 不要重构无关模块，不要修改 Strategy1 或 Strategy2 的评分、否决和风险计算规则。
2. 所有策略绑定接口必须在后端校验 `task_id` 对应的 `strategy_type`。
3. Strategy2 不支持的操作必须返回明确错误，绝不能默认执行 Strategy1。
4. 不要使用前端隐藏按钮代替后端校验。
5. 所有股票终态必须通过统一函数更新 DB 和 processed 进度。
6. 测试必须调用真实函数或真实 API，不要使用源码字符串检查代替行为验证。
7. 缓存新鲜度必须基于“期望最新交易日”，不要继续使用固定自然日阈值。
8. 保持现有接口兼容；新增错误响应时使用稳定错误码。
9. 修复后运行完整测试、离线测试、`compileall`、前端 build 和 `git diff --check`。
10. 在交付说明中逐项列出 FINAL-S2-001~005 的修改文件、测试名称和验证结果。

---

## 8. 回归测试清单

- Strategy2 任务不能调用 Strategy1 重试接口。
- Strategy2 任务不能调用 Strategy1 重评接口。
- Strategy2 任务不能调用 Strategy1 候选列表或详情接口。
- Strategy1 任务不能调用 Strategy2 候选列表或详情接口。
- Strategy1 正常重试与重评仍可用。
- Strategy2 候选、普通扫描、跳过、失败、持久化失败都发送 processed 回调。
- 最后一只股票为候选时，进度最终达到总数。
- Strategy2 扫描中刷新 ScannerConsole，首次加载即使用 Strategy2 API。
- `/strategy2/results?task=<id>` 自动选择并加载指定任务。
- Strategy1 任务列表不显示运行中的 Strategy2 任务。
- Strategy2 任务列表不显示运行中的 Strategy1 任务。
- 周末、盘前、盘后和长假缓存新鲜度正确。
- 全部数据源失败时只回退到真正新鲜的缓存。
- 未知中断任务类型仍会失败退出。
- 策略窗口外无效数据不影响窗口内评估。
- 非 ISO 日期、未来日期和逆序日期继续被拒绝。

---

## 9. 不建议修改的内容

- 不要修改 Strategy2 量干、价稳、等级、否决和风险规则。
- 不要修改 Strategy1 杯柄识别与评分规则。
- 不要合并 Strategy1 和 Strategy2 候选表。
- 不要移除全局扫描互斥。
- 不要通过扩大缓存自然日阈值掩盖长假问题。
- 不要引入大型新框架。
- 不要大规模调整前端 UI 风格。

---

## 10. 本次验证记录

已执行：

```text
python -m pytest tests/test_strategy2_recheck_fixes.py tests/test_strategy2_bug_fixes.py tests/test_strategy2_engine.py tests/test_server_scan_api.py -q
结果：87 passed

python -m pytest tests -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_yfinance_hist.py --ignore=tests/test_tushare_hist.py
结果：417 passed

python -m pytest tests -q
结果：421 passed, 1 failed
唯一失败：tests/test_yfinance_hist.py，外部 Yahoo Finance 429 限流

python -m compileall strategy2 scanner server.py -q
结果：通过

cd web && npm.cmd run build
结果：通过

git diff --check 136e48f..HEAD
结果：通过
```

---

## 11. 最终交付标准

修复完成后必须满足：

1. 任意 Strategy2 任务 ID 都不能误入 Strategy1 执行链。
2. 任意 Strategy1 任务 ID 都不能误入 Strategy2 查询或执行链。
3. 所有股票终态的数据库 processed 数和进度回调一致。
4. 页面刷新后首次请求就使用正确策略的数据接口。
5. Strategy2 任务链接能直接打开指定任务结果。
6. 长假期间能够正确使用最近交易日缓存。
7. 新增测试必须真实覆盖行为，不能只检查源码文本。
8. 离线测试全部通过；全量测试除明确外部数据源故障外无失败。
9. 前端构建、Python 编译和 diff 检查全部通过。


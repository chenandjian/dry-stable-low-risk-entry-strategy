# Strategy2 最终验收复审报告

## 1. 检查范围

本次验收针对：

- 功能修复提交：`1f8e3d5 fix(strategy2): final isolation — cross-strategy execution blocked, progress, frontend, cache`
- 审核指南提交：`b427df1 docs: add final third-party code review guide for strategy2`
- 上一轮修复基线：`d20dc4b`
- 审核说明：`docs/reviews/2026-06-10-strategy2-final-third-party-review-guide.md`

重点检查：

- Strategy1 / Strategy2 执行和查询隔离
- Strategy2 所有扫描终态及进度回调
- 全数据源失败处理与禁止缓存回退
- 数据源范围是否符合用户确认的三数据源约束
- 前端刷新恢复和 Strategy2 任务结果加载
- 新增测试是否真实证明修复有效
- Strategy1 回归、离线全量测试和前端构建

---

## 2. 总体结论

**本次验收不通过。**

本轮已经正确修复以下内容：

- 带 `task_id` 的 Strategy1 / Strategy2 候选接口类型校验。
- Strategy2 任务不能再调用 Strategy1 重试和重新评估。
- Strategy1 / Strategy2 任务列表已按策略隔离，并返回 `strategy_type`。
- Strategy2 candidate 成功路径会发送 processed 回调。
- 策略窗口和日期结构校验保持正常。
- ScannerConsole 已调整为先获取运行策略，再加载结果。
- Strategy2Results 已支持 `?task=<id>` 自动选择任务。

但仍有五项问题阻止最终交付：

1. Strategy2 全数据源失败和普通异常路径会因为 `_finish_stock()` 参数缺失再次崩溃，股票永久停留在 `fetching`。
2. Strategy1 实时候选列表和详情接口仍会泄漏 Strategy2 discovery。
3. 用户已明确决定：所有数据源失败时禁止回退本地缓存，股票必须直接标记为失败；当前代码仍会尝试缓存回退。
4. 当前默认数据源仍包含 yfinance，代码仍注册 mootdx，不符合用户确认的仅 `baidu/sina/tencent` 范围。
5. 最终修复测试存在关键场景直接 `pass`、只测 candidate 不测其他终态等问题，导致代码有真实 bug 时仍显示 443 个离线测试全部通过。
6. 前端只能部分显示失败股票，Strategy2 历史失败不可稳定查看，失败原因和失败总数展示也不完整。

---

## 3. 问题清单

| 编号 | 问题 | 严重程度 | 影响范围 | 是否必须修复 |
| --- | --- | --- | --- | --- |
| ACCEPT-S2-001 | Strategy2 失败终态处理再次抛错，股票永久停在 fetching | 高 | 扫描完整性、任务进度、失败记录 | 是 |
| ACCEPT-S2-002 | Strategy1 实时 API 泄漏 Strategy2 discovery | 高 | 策略隔离、候选展示、详情页 | 是 |
| ACCEPT-S2-003 | 全数据源失败后仍会回退本地缓存，不符合最新业务决定 | 高 | 数据可信度、扫描失败状态 | 是 |
| ACCEPT-S2-004 | 实际数据源范围不符合仅使用三数据源的确认要求 | 中 | 数据一致性、外部依赖、限流风险 | 是 |
| ACCEPT-S2-005 | 最终修复测试存在假通过，不能证明全部终态和缓存行为 | 中 | 回归防护、验收可信度 | 是 |
| ACCEPT-S2-006 | 前端失败股票展示不完整，Strategy2 历史失败缺少可靠入口 | 中 | 用户定位失败、数据源故障判断 | 是 |

---

## 4. 详细问题分析

### ACCEPT-S2-001：Strategy2 失败终态处理再次抛错，股票永久停在 fetching

#### 问题现象

当所有数据源均失败时，Strategy2 worker 不能把股票标记为 `failed`，而是在线程中连续抛出两次 `TypeError`。

真实复现结果：

```text
Strategy2 error scanning 000001:
scan_strategy2_all.<locals>._finish_stock() missing 1 required positional argument: 'status'

Exception in thread Thread-1 (worker):
TypeError: scan_strategy2_all.<locals>._finish_stock() missing 1 required positional argument: 'status'

result.stats:
processed=0, failed=0, skipped=0

task_stocks:
status=fetching, finished_at=None

callbacks=[]
```

#### 涉及模块

- `strategy2/scanner.py:87`：`_finish_stock(code, name, status, ...)`
- `strategy2/scanner.py:146`：全部数据源失败路径
- `strategy2/scanner.py:216`：worker 通用异常路径
- `tests/test_strategy2_final_fixes.py:214`：当前仅测试 candidate 路径

#### 原因

`_finish_stock` 新增了必填 `name` 参数，但以下两处调用仍使用旧签名：

```python
_finish_stock(code, "failed", status_reason="ALL_DATA_SOURCES_FAILED", ...)
```

```python
_finish_stock(code, "failed",
              status_reason="STRATEGY2_EVALUATION_ERROR", ...)
```

第一个调用把 `"failed"` 当成 `name`，缺少 `status`，抛出 `TypeError`。随后进入 `except`，第二个调用再次以同样方式抛错，线程最终退出。

线程异常不会传播给主线程，`scan_strategy2_all()` 仍会返回一个看似正常、但 `processed=0` 的结果。

#### 触发条件

- 所有数据源拉取失败且不是 transient busy。
- Strategy2 评估过程中抛出任意异常。
- 终态更新函数自身抛错。

#### 影响

- 股票永久停在 `fetching`，没有失败原因和结束时间。
- processed 无法达到 total，前端进度可能永远不完整。
- 扫描函数主线程仍返回，任务可能被错误标记为已完成。
- 用户无法通过失败列表定位或重试这些股票。

#### 修复建议

修复两个遗漏调用：

```python
_finish_stock(
    code,
    stock_name,
    "failed",
    status_reason="ALL_DATA_SOURCES_FAILED",
    source_errors=encode_source_errors(fetch_result.source_errors),
)
```

```python
_finish_stock(
    code,
    stock_name,
    "failed",
    status_reason="STRATEGY2_EVALUATION_ERROR",
    error_detail=str(e),
)
```

同时建议在 worker 最外层增加防御，确保终态记录失败时不会静默结束：

```python
except Exception:
    logger.exception("Strategy2 worker crashed for %s", code)
    try:
        _finish_stock(...)
    except Exception:
        logger.exception("Failed to persist terminal state for %s", code)
```

不要吞掉异常后假装 processed 已完成。若最终无法写入终态，扫描结果必须包含 worker error，并使任务状态为 failed。

#### 验证方式

新增真实行为测试：

1. 所有数据源返回失败。
2. 执行 `scan_strategy2_all(worker_count=1)`。
3. 断言股票状态为 `failed`，不是 `fetching`。
4. 断言 `status_reason == "ALL_DATA_SOURCES_FAILED"`。
5. 断言 processed 为 1。
6. 断言收到 scanning 回调。
7. 模拟 `engine.evaluate_at()` 抛异常，重复验证 `STRATEGY2_EVALUATION_ERROR`。

---

### ACCEPT-S2-002：Strategy1 实时 API 泄漏 Strategy2 discovery

#### 问题现象

带 `task_id` 的跨策略查询已经被拒绝，但在 Strategy2 扫描运行期间，不带 `task_id` 调用 Strategy1 接口仍会返回 Strategy2 discovery。

真实复现：

```text
当前运行：
strategy_type = STRATEGY_2_EXTREME_DRY_STABLE
discoveries = [{"code":"999999","name":"S2-only","total_score":88}]

GET /api/candidates
200，返回 Strategy2 discovery

GET /api/candidate/999999
200，返回被强行映射成 Strategy1 字段的伪详情，score=0
```

#### 涉及模块

- `server.py:621`：`get_candidates`
- `server.py:730`：`get_candidate`
- `server.py:1107`：`strategy2_candidates`

#### 原因

Strategy1 实时接口只检查 `_running["running"]`，没有检查运行策略类型：

```python
elif _running["running"]:
    ds = _running.get("stats", {}).get("discoveries") or []
    return {"candidates": ds, "total": len(ds)}
```

详情接口同样会从任意运行策略的 discovery 中查找：

```python
ds = (...) if _running.get("running") else []
```

#### 影响

- Strategy1 结果雷达可能展示 Strategy2 候选。
- Strategy1 详情页会把 Strategy2 discovery 映射成大量零值字段。
- “跨策略隔离”只覆盖了显式任务 ID，没有覆盖实时内存状态。
- 后续调用者无法判断返回数据属于哪种策略。

#### 修复建议

Strategy1 实时 discovery 只能在当前运行策略为 Strategy1 时使用：

```python
is_running_s1 = (
    _running.get("running")
    and _running.get("strategy_type") == "STRATEGY_1_CUP_HANDLE"
)
```

`get_candidates()`：

```python
elif is_running_s1:
    ...
else:
    cands = db.get_candidates()
```

`get_candidate()`：

```python
if not c and is_running_s1:
    # only search Strategy1 discoveries
```

Strategy2 实时数据继续只通过 `/api/strategy2/candidates` 返回。

#### 验证方式

新增 API 测试：

- 运行 Strategy2 时，`GET /api/candidates` 不包含 Strategy2 discovery。
- 运行 Strategy2 时，`GET /api/candidate/{s2-code}` 返回 404，而不是伪 Strategy1 详情。
- 运行 Strategy1 时，上述两个接口仍能返回 Strategy1 discovery。
- 运行 Strategy1 时，Strategy2 实时接口不返回 Strategy1 discovery。

---

### ACCEPT-S2-003：全数据源失败后仍会回退本地缓存

#### 最新业务决定

用户已明确选择以下规则：

> 数据源全部失败时不使用缓存，直接将股票标记为失败。

因此不再需要判断缓存是否“新鲜”，也不需要处理交易日、盘前盘后、周末或长假。

#### 问题现象

当前 `fetch_with_retry()` 在所有在线数据源失败后，仍会读取本地缓存并在判断为新鲜时返回：

```python
if cached and _is_cache_fresh(cached):
    return FetchResult(
        data=cached,
        fallback_source="cache",
        from_cache=True,
        ...
    )
```

这与最新业务决定冲突。

#### 涉及模块

- `scanner/daily_data_service.py`：`fetch_with_retry` 的缓存回退分支
- `scanner/daily_data_service.py`：`_is_cache_fresh`、`expected_latest_trade_date` 等仅服务于回退的逻辑
- `tests/test_strategy2_final_fixes.py`：缓存新鲜度测试

#### 原因

共享数据服务仍把本地缓存视为在线数据源全部失败后的可用兜底，导致扫描可能在用户不知情的情况下使用历史数据继续执行策略。

#### 影响

- 数据源全部失败时，系统仍可能使用旧缓存产生策略候选。
- 股票不会被标记为 `ALL_DATA_SOURCES_FAILED`，掩盖真实数据源故障。
- 用户无法确认扫描结果是否基于本次在线拉取数据。

#### 修复建议

删除所有在线数据源失败后的缓存回退分支：

```python
# All sources failed: never use cached OHLC for a new scan.
return _build_all_failed_result(chain, source_errors)
```

处理要求：

1. 在线数据源成功时，仍允许把新数据与历史缓存合并并保存；这不属于失败回退。
2. 在线数据源全部失败时，返回 `FetchResult(data=None, ...)`。
3. Strategy1 和 Strategy2 扫描器收到 `data=None` 后，都必须把股票标记为失败并记录 `ALL_DATA_SOURCES_FAILED`。
4. 若 `_is_cache_fresh`、`expected_latest_trade_date`、`_default_is_trading_day` 不再有其他调用，应删除这些死代码及相关导入。
5. 删除盘前、盘后、周末、长假缓存新鲜度测试，改为禁止回退测试。

#### 验证方式

测试必须包含真实断言：

- 数据库存在缓存且所有在线源失败时，`fetch_with_retry().data is None`。
- 数据库存在缓存且所有在线源失败时，`from_cache is False`。
- Strategy1 收到全源失败结果后，将股票标记为 failed。
- Strategy2 收到全源失败结果后，将股票标记为 failed。
- 在线源成功时，仍可与历史缓存合并、保存并返回最新数据。

---

### ACCEPT-S2-004：实际数据源范围不符合仅使用三数据源的确认要求

#### 问题现象

用户此前已经明确：

> mootdx 已经被剔除，目前只使用 `"baidu", "sina", "tencent"`。

但当前代码和配置仍包含：

- `config.yaml` 默认启用 `yfinance`。
- `DEFAULT_DAILY_SOURCES` 包含 `yfinance`。
- `DataSourceManager` 注册 `yfinance` 锁。
- `daily_data_service.py` 和 `engine.py` 仍导入并注册 `mootdx`。
- `requirements.txt` 仍包含 `mootdx` 和 `yfinance`。

#### 涉及模块

- `config.yaml:12-16`
- `scanner/daily_data_service.py:17-25, 48-53`
- `scanner/engine.py:559-568`
- `scanner/data_source.py:16-21`
- `requirements.txt`
- 相关 mootdx / yfinance 测试

#### 影响

- 全市场扫描会实际调用用户未确认的数据源。
- yfinance 限流会增加失败和等待时间。
- mootdx 仍作为可选择源存在，不能称为“已经剔除”。
- 数据源范围与审核前提不一致。

#### 修复建议

按用户确认范围统一收敛到：

```python
["baidu", "sina", "tencent"]
```

需要同步处理：

1. `config.yaml` 删除默认 `yfinance`。
2. 两处 `DEFAULT_DAILY_SOURCES` 统一为三个源。
3. DataSourceManager 只注册三个源。
4. 从通用日线扫描链中删除 mootdx / yfinance 映射和导入。
5. 如果 mootdx / yfinance 文件要保留作实验工具，必须与生产扫描链完全隔离，并从默认依赖和生产测试中移除。
6. 更新设计文档和审核指南中的“四数据源”描述。

不要只修改 `config.yaml`；否则代码仍允许错误配置重新启用未批准数据源。

#### 验证方式

- 断言默认数据源严格等于 `["baidu", "sina", "tencent"]`。
- 断言 `_daily_fetch_fn("mootdx")` 和 `_daily_fetch_fn("yfinance")` 返回明确 unsupported 错误。
- 断言 DataSourceManager 不包含 mootdx / yfinance。
- 全仓搜索生产路径不再引用 mootdx / yfinance。

---

### ACCEPT-S2-005：最终修复测试存在假通过

#### 问题现象

审核指南宣称：

- 缓存测试仍围绕新鲜度展开，没有验证最新决定的“禁止失败回退”。
- 5 种扫描终态全部发送 processed。
- `git diff --check` 通过。

实际情况：

- 周一收盘后测试直接 `pass`，没有验证任何行为。
- 终态测试只覆盖 candidate，没有覆盖 all-sources-failed 和 evaluation exception。
- 上一轮旧测试仍使用源码字符串检查。
- `git diff --check d20dc4b..b427df1` 仍报告审核文档 EOF 空行。
- 离线套件通过时，ACCEPT-S2-001 和 ACCEPT-S2-003 仍真实存在。

#### 涉及模块

- `tests/test_strategy2_final_fixes.py`
- `tests/test_strategy2_recheck_fixes.py`
- `docs/reviews/2026-06-10-strategy2-final-third-party-review-guide.md`

#### 修复建议

1. 删除所有用于关键行为验证的 `pass`。
2. 删除 `inspect.getsource()` 式行为测试，改为调用真实函数。
3. 对 candidate/scanned/skipped/failed/persist-failed/evaluation-error 分别测试。
4. API 测试必须断言稳定错误码，而不是宽泛接受 `(400, 404, 409)`。
5. 测试名称、指南声明和真实覆盖必须一致。
6. 使用提交范围执行 diff 检查：

```bash
git diff --check d20dc4b..HEAD
```

#### 验证方式

故意回退任意一个修复时，对应测试必须失败。尤其应验证：

- 删除 `_finish_stock` 的 `stock_name` 参数会使测试失败。
- 恢复任何全源失败缓存回退分支时，对应测试必须失败。
- Strategy1 API 返回 S2 discovery 会使隔离测试失败。

---

### ACCEPT-S2-006：前端失败股票展示不完整，Strategy2 历史失败缺少可靠入口

#### 当前已有能力

扫描控制台已有失败股票面板：

```vue
<div class="panel failure-panel" v-if="scanProgress.taskId && failures.length > 0">
  <span>失败股票 · {{ failures.length }}</span>
  ...
  <span>{{ f.code }}</span>
  <span>{{ f.name }}</span>
  <span>{{ f.status_reason || f.error_detail || '--' }}</span>
</div>
```

后端 `GET /api/scan/tasks/{task_id}/stocks?status=failed` 会返回：

- 股票代码和名称
- `status_reason`
- `error_detail`
- `source_errors`
- 主源、备用源和尝试次数

因此，当扫描器正确把股票标记为 failed 后，当前扫描控制台可以显示失败股票。

#### 剩余问题

1. `loadFailures()` 固定使用 `page_size: 20`，但标题显示 `failures.length`，失败超过 20 只时会把“当前加载数量”误当成“真实失败总数”。
2. `ALL_DATA_SOURCES_FAILED` 会直接显示英文错误码，用户看不到明确中文含义。
3. `source_errors` 没有展示，用户无法确认百度、新浪、腾讯分别为何失败。
4. Strategy2 历史任务结果页没有失败列表入口；离开扫描控制台后，用户难以重新查看失败股票。
5. Strategy2 失败面板仍显示“重新拉取”按钮，但当前重试接口只支持 Strategy1，点击后会返回策略类型不匹配。
6. 失败原因优先显示 `status_reason`，当其为通用错误码时，具体的 `error_detail` 可能被隐藏。

#### 涉及模块

- `web/src/pages/ScannerConsole.vue`：失败列表与重试按钮
- `web/src/pages/Strategy2Results.vue`：Strategy2 历史任务结果页
- `web/src/pages/TaskCenter.vue`：Strategy1 历史任务失败入口
- `web/src/composables/useApi.js`：任务股票查询
- `server.py`：`GET /api/scan/tasks/{task_id}/stocks`

#### 修复建议

前端必须让用户明确看到：

```text
000001 平安银行
状态：数据拉取失败，未使用本地缓存
百度：请求超时
新浪：HTTP 456
腾讯：返回空数据
```

具体要求：

1. 增加稳定错误码到中文文案的映射：

```javascript
const FAILURE_REASON_LABELS = {
  ALL_DATA_SOURCES_FAILED: '所有数据源拉取失败，未使用本地缓存',
  STRATEGY2_EVALUATION_ERROR: '策略计算失败',
  STRATEGY2_CANDIDATE_PERSIST_FAILED: '候选结果保存失败',
}
```

2. 保留并可展开查看原始 `error_detail` 和 `source_errors`，不要只显示通用错误码。
3. 使用 API 返回的 `total` 显示真实失败总数，例如：

```text
失败股票 · 137
当前显示 1-20
```

4. 支持分页或“加载更多”，不能永久只展示前 20 条。
5. Strategy2Results 增加当前任务的失败数量和“查看失败股票”区域，使用通用任务股票 API 查询。
6. Strategy2 尚不支持失败重试时，隐藏“重新拉取”按钮或显示明确的“不支持重试”；不得调用 Strategy1 重试接口。
7. 扫描过程中每当 failed 增加时，失败列表应自动刷新；扫描完成后仍可查看。

#### 验证方式

- 模拟一只 `ALL_DATA_SOURCES_FAILED` 股票，前端显示“所有数据源拉取失败，未使用本地缓存”。
- 展开失败详情，显示百度、新浪、腾讯各自失败原因。
- 模拟 35 只失败股票，标题显示 35，并可查看第 21-35 只。
- Strategy2 扫描中能看到失败股票。
- Strategy2 扫描完成、刷新页面或从结果页重新进入后，仍能看到历史失败股票。
- Strategy2 失败列表不显示可调用 Strategy1 的重试按钮。
- Strategy1 原有失败重试功能保持可用。

---

## 5. 建议修复顺序

1. 修复 ACCEPT-S2-001，避免扫描任务产生永久 fetching 股票。
2. 修复 ACCEPT-S2-002，完成实时内存路径的策略隔离。
3. 修复 ACCEPT-S2-003，删除全源失败缓存回退和不再需要的新鲜度逻辑。
4. 修复 ACCEPT-S2-004，统一生产数据源范围。
5. 修复 ACCEPT-S2-005，补齐能够捕获上述问题的回归测试。
6. 修复 ACCEPT-S2-006，确保失败股票和数据源错误对用户完整可见。
7. 最后重新执行完整验收。

---

## 6. 给修复 AI 的执行要求

1. 不要修改 Strategy1 / Strategy2 的评分、否决、风险和选股规则。
2. 不要重构无关模块。
3. 修复所有 `_finish_stock` 调用并真实覆盖每种终态。
4. Strategy1 内存 discovery 只能来自 Strategy1，Strategy2 同理。
5. 所有在线数据源失败时禁止使用缓存，必须返回失败结果。
6. 生产扫描数据源严格限制为 `baidu/sina/tencent`。
7. 禁止用 `pass`、源码字符串检查或宽泛状态码断言证明关键修复。
8. 修复后逐项提供 ACCEPT-S2-001~005 的代码和测试证据。
9. 前端必须展示失败股票、中文失败原因、各数据源错误和真实失败总数。

---

## 7. 回归测试清单

- Strategy2 全数据源失败后股票状态为 failed。
- Strategy2 评估异常后股票状态为 failed。
- 所有终态 processed 最终等于 total。
- Strategy1 实时列表不返回 Strategy2 discovery。
- Strategy1 实时详情不返回 Strategy2 discovery。
- Strategy2 实时接口不返回 Strategy1 discovery。
- 带 task_id 的跨策略接口继续返回明确类型错误。
- 数据库存在缓存时，全源失败仍直接标记股票失败。
- 前端显示“所有数据源拉取失败，未使用本地缓存”。
- 前端可查看百度、新浪、腾讯各自失败原因。
- 失败超过 20 只时显示真实总数并支持继续查看。
- Strategy2 历史任务可重新查看失败股票。
- Strategy2 不显示错误的 Strategy1 重试按钮。
- 默认生产数据源严格为 baidu、sina、tencent。
- Strategy1 和 Strategy2 任务列表继续隔离。
- 策略窗口外坏数据继续不影响 Strategy2。
- 前端 build 通过。
- 离线全量测试全部通过。

---

## 8. 不建议修改的内容

- 不要修改策略评分阈值。
- 不要修改 Strategy2 等级划分。
- 不要修改风险计算公式。
- 不要合并两种策略候选表。
- 不要重新启用 mootdx 或 yfinance 生产扫描链。
- 不要保留或重新引入全源失败缓存回退。
- 不要引入大型框架。

---

## 9. 本次验证记录

```text
python -m pytest tests/test_strategy2_final_fixes.py -v
结果：26 passed
结论：测试存在假通过，不能证明验收通过

python -m pytest tests/test_strategy2_recheck_fixes.py tests/test_strategy2_bug_fixes.py tests/test_strategy2_engine.py tests/test_server_scan_api.py -q
结果：87 passed

python -m pytest tests -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_yfinance_hist.py --ignore=tests/test_tushare_hist.py
结果：443 passed

python -m pytest tests -q
结果：446 passed, 2 failed
外部失败：东财代理连接失败、Yahoo Finance 429 限流

python -m compileall strategy2 scanner server.py -q
结果：通过

cd web && npm.cmd run build
结果：通过，built in 1.64s

git diff --check d20dc4b..b427df1
结果：失败，上一轮审核文档存在 new blank line at EOF
```

真实反例：

```text
Strategy2 全数据源失败：
股票最终状态 fetching
processed=0
worker TypeError

数据库存在缓存且所有在线数据源失败：
当前代码仍可能回退缓存；最新业务决定要求直接失败

运行 Strategy2 时调用 Strategy1 API：
/api/candidates 返回 Strategy2 discovery
/api/candidate/{s2-code} 返回 200 伪 Strategy1 详情
```

---

## 10. 最终交付标准

修复完成后必须满足：

1. Strategy2 任意失败路径都不会留下 fetching 股票。
2. 所有终态都发送 processed 回调，最终 processed 等于 total。
3. 两种策略的实时 discovery、任务 ID、任务列表和详情完全隔离。
4. 所有在线数据源失败时不使用缓存，股票直接标记为失败。
5. 生产扫描只使用 baidu、sina、tencent。
6. 关键测试无 `pass`、无源码字符串替代行为验证。
7. 离线全量测试全部通过。
8. 前端构建、compileall 和提交范围 diff 检查全部通过。
9. 用户能够在前端查看全部失败股票及清晰失败原因。

# 策略2修复复审报告与最终修复方案

## 1. 复审范围

本次复审针对提交：

```text
136e48f fix(strategy2): resolve all 11 bugs from code audit (BUG-S2-001~011)
```

基线为：

```text
82e337a docs: add third-party code review guide for strategy2
```

复审依据：

- `docs/superpowers/specs/2026-06-10-strategy2-extreme-dry-stable-design.md`
- `docs/reviews/2026-06-10-strategy2-code-audit-and-one-pass-fix-plan.md`
- 修复提交新增的 `tests/test_strategy2_bug_fixes.py`
- 真实 API、scanner、engine、缓存和前端运行路径

---

## 2. 总体结论

修复提交已经正确解决了最近 5 日首日跌幅漏判、`V20=0` 入选、候选持久化顺序、JSON 数组反序列化和默认候选排序等问题。

但该提交尚未达到“BUG-S2-001 至 BUG-S2-011 全部完成”的交付标准。当前仍有 **7 个需要修复的问题**：

- 高：4 个
- 中：3 个

主要原因是新增测试大量集中在辅助函数和 DB 层，没有覆盖 lifespan 恢复分派、策略2 API 任务类型校验、scanner 真实配置校验、缓存真实回退、失败进度回调和前端运行时行为。

---

## 3. 上一轮问题复核状态

| 原编号 | 复核结论 | 说明 |
| --- | --- | --- |
| BUG-S2-001 | 部分修复 | 已按已知策略类型分派恢复；未知类型仍默认交给策略1，且没有真实 lifespan 分派测试 |
| BUG-S2-002 | 部分修复 | 指标计算使用策略窗口；但窗口外无效行情仍会让整个评估失败 |
| BUG-S2-003 | 已修复 | 最近 5 日使用 6 行数据计算 5 个涨跌变化 |
| BUG-S2-004 | 已修复 | `V20 <= 0` 会返回 `INVALID_MARKET_DATA` |
| BUG-S2-005 | 部分修复 | OHLC 数值与顺序校验已增强；日期字符串本身仍未验证 |
| BUG-S2-006 | 部分修复 | 保存配置和启动 API 已校验；scanner 最终防线仍未使用完整配置 |
| BUG-S2-007 | 部分修复 | 默认策略1候选已隔离；任务列表和策略2 API task_id 校验仍未隔离 |
| BUG-S2-008 | 修复不正确 | 增加了缓存回退，但新鲜度规则会接受未来数据并误拒绝周末/节假日缓存 |
| BUG-S2-009 | 部分修复 | 候选持久化顺序已修复；失败和跳过路径仍不发送进度回调 |
| BUG-S2-010 | 未完整修复 | 页面刷新策略类型恢复、完成后结果加载和策略2详情行仍有问题 |
| BUG-S2-011 | 已修复 | JSON 字段反序列化和稳定排序已实现 |

---

## 4. 剩余问题清单

| 编号 | 问题 | 严重程度 | 是否必须修复 |
| --- | --- | --- | --- |
| RECHECK-S2-001 | 策略2前端刷新恢复和结果详情存在运行时错误 | 高 | 是 |
| RECHECK-S2-002 | 缓存新鲜度会接受未来数据并误拒绝有效交易日缓存 | 高 | 是 |
| RECHECK-S2-003 | 策略任务/API 类型隔离仍不完整 | 高 | 是 |
| RECHECK-S2-004 | 窗口外无效行情仍影响策略窗口评估 | 高 | 是 |
| RECHECK-S2-005 | scanner 和中断恢复缺少最终配置/任务类型防线 | 中 | 是 |
| RECHECK-S2-006 | 失败和跳过路径不发送进度回调 | 中 | 是 |
| RECHECK-S2-007 | 日期只按字符串排序，没有验证真实日期格式 | 中 | 是 |

---

## 5. 详细问题与修复方案

### RECHECK-S2-001：策略2前端刷新恢复和结果详情存在运行时错误

#### 问题现象

1. 页面刷新时，如果后端正在运行策略2，前端只设置 `scanning=true`，没有从 `status.strategyType` 恢复 `activeStrategyType`。
2. 后续轮询会把策略2 discovery 按策略1字段解析。
3. 策略2扫描完成时，`loadResults()` 主动使用空数组覆盖实时发现。
4. Strategy2Results 的详情行引用了 `v-for` 作用域外的 `c`。

#### 证据

`ScannerConsole.vue`：

- `activeStrategyType` 只在手动点击启动按钮时赋值。
- mounted 中获取 `getScanStatus()` 后，没有执行：

```js
activeStrategyType.value = status.strategyType
```

- 策略2完成后执行：

```js
const data = isS2 ? { candidates: [] } : await getCandidates()
```

会清空实时发现。

`Strategy2Results.vue`：

```vue
<tr v-for="c in candidates" ...>
...
</tr>
<tr v-if="expandedCode === c.code" class="detail-row">
```

第二个 `tr` 不是第一个 `tr` 的子节点，无法访问其 `c`。前端生产构建不会发现此类作用域运行时错误。

#### 触发条件

- 策略2扫描运行时刷新扫描控制台。
- 策略2扫描完成。
- 策略2结果页存在至少一个候选。

#### 影响

- 策略2实时发现显示为 0 分或错误字段。
- 扫描完成后控制台候选消失。
- 策略2结果页可能在渲染候选时抛出运行时异常，详情无法打开。

#### 修复建议

1. `applyStats(status)` 或 `pollStatus()` 中统一恢复：

```js
if (status.strategyType) {
  activeStrategyType.value = status.strategyType
}
```

2. mounted 首次查询状态后必须立即恢复策略类型，再加载对应结果。
3. 策略2完成后必须二选一：
   - 调用 `getStrategy2Candidates(scanProgress.taskId)` 加载持久化结果；
   - 或导航到 `/strategy2/results?task=...`。
4. Strategy2Results 使用 `<template v-for>` 包裹主行和详情行：

```vue
<template v-for="c in candidates" :key="c.code">
  <tr>...</tr>
  <tr v-if="expandedCode === c.code">...</tr>
</template>
```

5. 页面 mounted 时读取 `route.query.task`，自动选择目标策略2任务并加载候选。

#### 必须新增测试

- 前端组件测试：刷新恢复 `STRATEGY_2_EXTREME_DRY_STABLE` 后，discovery 使用 `total_score`。
- 策略2扫描完成后，控制台不会加载策略1候选或清空策略2结果。
- 两个候选可分别展开详情，不出现 `c is not defined`。

---

### RECHECK-S2-002：缓存新鲜度会接受未来数据并误拒绝有效交易日缓存

#### 问题现象

`_is_cache_fresh()` 使用“自然日差值不超过 2 天”判断新鲜度：

```python
return (today - latest_date).days <= 2
```

该条件没有下界，因此未来日期的缓存会被判定为新鲜；同时周一读取上周五缓存时相差 3 天，会被判定过期。

#### 最小复现

```text
future_cache_fresh= True
```

#### 影响

- 错误或未来日期缓存可能进入策略计算，造成未来数据泄漏。
- 周末、长周末和法定节假日后的有效最近交易日缓存会被错误拒绝。
- 新增测试只验证 `FetchResult.from_cache` 字段存在，没有调用 `_is_cache_fresh()` 或 `fetch_with_retry()`。

#### 修复建议

不要使用固定自然日差值。

推荐实现一个可测试的新鲜度策略：

1. 缓存最新日期必须满足 `latest_date <= today`，未来日期一律拒绝。
2. 根据当前时间和最近应有交易日判断：
   - 交易日收盘前，可接受上一交易日。
   - 交易日收盘后，应优先要求当日；如业务允许延迟，规则必须显式配置。
   - 周末和节假日，应接受最近交易日。
3. 如果项目暂时没有交易日历，至少实现工作日回退并保留节假日配置入口；不得继续用固定两天。
4. `fetch_with_retry()` 的缓存回退测试必须 mock 当前日期/时间，验证最终 `FetchResult`。

#### 必须新增测试

- 未来日期缓存拒绝。
- 周一读取上周五缓存可接受。
- 周末读取周五缓存可接受。
- 长假场景按配置或交易日历判断。
- 全源失败 + 新鲜缓存返回 `from_cache=True`。
- 全源失败 + 过期缓存返回 `data=None`。

---

### RECHECK-S2-003：策略任务/API 类型隔离仍不完整

#### 问题现象

- `/api/scan/tasks` 仍返回所有策略任务，并对策略2任务调用策略1候选查询。
- `/api/strategy2/candidates?task_id=<策略1任务>` 返回空列表 HTTP 200，没有明确拒绝。
- 策略2详情接口对错误策略 task_id 仅表现为普通 404，没有稳定任务类型错误。

#### 最小复现

```text
s2_list_with_s1_task= {'candidates': [], 'total': 0}
generic_task_types= ['STRATEGY_2_EXTREME_DRY_STABLE', 'STRATEGY_1_CUP_HANDLE']
```

#### 影响

- 策略1任务中心仍混入策略2任务。
- API 调用方无法区分“任务类型错误”和“该任务没有候选”。
- BUG-S2-007 只修复了默认候选查询，没有完成接口级隔离。

#### 修复建议

1. 在 DB 层新增或复用：

```python
get_scan_task(task_id)
get_task_strategy_type(task_id)
get_scan_tasks(strategy_type=...)
```

2. `/api/scan/tasks` 默认只返回策略1及旧 NULL 任务。
3. 策略2列表和详情端点在读取候选前统一验证 task_id：
   - 任务不存在：404 `TASK_NOT_FOUND`
   - 类型错误：400 或 404 `TASK_STRATEGY_MISMATCH`
4. 如果策略1候选接口允许 task_id，也应拒绝策略2任务 ID。

#### 必须新增测试

- 策略1任务列表不包含策略2。
- 策略2任务列表不包含策略1和 NULL 旧任务。
- 策略1 task_id 查询策略2列表和详情明确返回类型错误。
- 策略2 task_id 查询策略1候选明确返回类型错误。

---

### RECHECK-S2-004：窗口外无效行情仍影响策略窗口评估

#### 问题现象

引擎先对完整输入执行 `validate_ohlc_data(data)`，再截取 `strategy_window_days`。因此策略窗口外的一条无效价格仍会让评估失败。

#### 最小复现

输入 121 行，最近 120 行有效，仅把窗口外第一行 `close` 改为 0：

```text
invalid_prefix_outside_window= False INVALID_MARKET_DATA
```

新增测试名为 `test_window_truncation_excludes_bad_outside_data`，但测试前缀使用的是合法价格 99，并没有覆盖“坏数据”。

#### 影响

- 缓存中较早的异常历史记录会错误阻断当前策略窗口。
- “策略2只使用最近 strategy_window_days 个有效交易日”的边界仍不完整。

#### 修复建议

区分两类校验：

1. 为了可靠截取尾部窗口，对完整输入只做列表结构、日期存在、日期可解析、严格升序和重复检查。
2. 截取 `strategy_data = data[-strategy_window_days:]`。
3. 对 `strategy_data` 做完整 OHLC 数值、关系和成交量校验。

这样既能保证尾部窗口选择正确，也不会让窗口外数值异常影响策略结果。

#### 必须新增测试

- 窗口外 `close=0` 不影响评估。
- 窗口外缺失 `high` 不影响评估。
- 窗口内同样异常仍返回 `INVALID_MARKET_DATA`。
- 完整输入日期倒序或重复仍返回 `INVALID_MARKET_DATA`。

---

### RECHECK-S2-005：scanner 和中断恢复缺少最终配置/任务类型防线

#### 问题现象

1. `scan_strategy2_all()` 从完整配置中取出 `strategy2_cfg` 后构造引擎：

```python
engine = ExtremeDryStableStrategyEngine(strategy2_cfg)
```

因此引擎看不到真实 `liquidity.min_listing_days`。

2. 未知 `strategy_type` 在 lifespan 中默认通过策略1恢复。

#### 最小复现

`strategy_window_days=120`、`min_listing_days=100` 的完整配置直接调用 scanner，当前被接受：

```text
scanner_invalid_cross_config=accepted
```

#### 影响

- 绕过 API、自动恢复或未来其他入口可使用无效跨配置关系启动扫描。
- 未知任务类型可能被错误送入策略1，造成数据污染。

#### 修复建议

1. scanner 构造引擎时传完整配置：

```python
engine = ExtremeDryStableStrategyEngine(config)
```

或在 scanner 开始处显式调用 `resolve_strategy2_config(config)`。
2. lifespan 只允许：
   - `STRATEGY_1_CUP_HANDLE`
   - `STRATEGY_2_EXTREME_DRY_STABLE`
3. 未知类型必须标记任务失败，错误码使用 `UNKNOWN_STRATEGY_TYPE`，不得默认执行。
4. 新增真实 lifespan 测试，而不只是测试 `get_interrupted_task()` 返回字段。

#### 必须新增测试

- 直接调用 scanner 时，窗口大于 `min_listing_days` 立即抛出配置错误，且不处理任何股票。
- lifespan 中断策略1只调用 `scan_all`。
- lifespan 中断策略2只调用 `scan_strategy2_all`。
- 未知任务类型不调用任何 scanner。

---

### RECHECK-S2-006：失败和跳过路径不发送进度回调

#### 问题现象

scanner 在以下路径更新数据库后直接 `continue`，没有调用 `progress_callback`：

- 数据源忙超过重试次数。
- 所有数据源失败。
- 流动性过滤跳过。
- 候选持久化失败。
- worker 顶层异常。

#### 最小复现

单只股票数据源失败：

```text
failed_progress_callbacks= []
final_stats.processed=1
```

数据库最终统计正确，但实时回调没有通知该股票已处理。

#### 影响

- WebSocket 或未来依赖回调的调用方进度会停滞。
- 服务端内存状态可能长期落后于数据库状态。
- BUG-S2-009 修复方案要求的“所有终态更新 processed”没有完成。

#### 修复建议

新增单一终态辅助函数，例如：

```python
def finish_stock(code, status, reason=None, ...):
    db.update_task_stock(...)
    summary = db.refresh_scan_task_counts(task_id)
    progress_callback(
        "scanning",
        summary["processed"],
        summary["total_stocks"],
        detail,
    )
```

所有 `scanned/skipped/failed/candidate` 终态都通过该函数完成。进度值必须来自 DB 汇总，不要维护不包含失败/跳过的独立 `scanned_count`。

#### 必须新增测试

- failed、skipped、scanned、candidate、持久化失败路径都发送一次终态进度。
- processed 单调递增，最终等于 total。
- 多线程情况下不会发生进度倒退。

---

### RECHECK-S2-007：日期只按字符串排序，没有验证真实日期格式

#### 问题现象

`validate_ohlc_data()` 只检查 date 是非空字符串，并使用字符串大小判断顺序。类似 `bad-001` 的值会通过校验。

#### 最小复现

```text
non_date_strings= None
```

#### 影响

- 非日期字符串可成为 `evaluation_date`。
- 缓存新鲜度、排序和结果查询可能在后续失败。

#### 修复建议

- 使用 `datetime.date.fromisoformat(date)` 验证标准 `YYYY-MM-DD`。
- 使用解析后的 date 对象检查严格升序。
- 日期解析失败统一返回 `INVALID_MARKET_DATA`。

#### 必须新增测试

- `bad-001`、`2026-13-01`、空白字符串均拒绝。
- 合法 ISO 日期严格升序通过。

---

## 6. 建议一次性修复顺序

1. 修复任务类型和配置最终防线：RECHECK-S2-003、005。
2. 修复缓存新鲜度：RECHECK-S2-002。
3. 拆分结构校验与策略窗口值校验：RECHECK-S2-004、007。
4. 统一 scanner 终态处理与进度：RECHECK-S2-006。
5. 修复前端刷新恢复、结果加载和详情模板：RECHECK-S2-001。
6. 补齐真实路径测试并执行全部验证。

---

## 7. 给修复 AI 的执行要求

1. 只修复本报告 RECHECK-S2-001 至 RECHECK-S2-007，不要重做已经确认完成的评分和否决逻辑。
2. 不要修改策略1业务规则、策略2评分阈值、等级和风险公式。
3. 每个问题必须先增加能够在 `136e48f` 上失败的测试。
4. 测试必须覆盖真实入口：
   - lifespan
   - API endpoint
   - `scan_strategy2_all`
   - `fetch_with_retry`
   - 前端组件运行时
5. 不要用“字段存在测试”替代行为测试。
6. 修复完成后删除审核文档第 16 行尾随空格，确保 `git diff --check` 通过。

---

## 8. 回归验证清单

必须执行：

```bash
python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_yfinance_hist.py --ignore=tests/test_tushare_hist.py
python -m compileall strategy2 scanner server.py -q
cd web && npm run build
git diff --check
```

还必须进行前端运行时验证：

- 策略2扫描运行时刷新 ScannerConsole。
- 策略2扫描完成后确认候选仍可见或正确跳转。
- Strategy2Results 至少使用两个候选，分别展开详情。

---

## 9. 最终交付标准

1. RECHECK-S2-001 至 RECHECK-S2-007 全部有真实路径测试。
2. 未来缓存不可能被使用，周末/节假日缓存按明确规则处理。
3. 策略1和策略2任务/API 完全隔离。
4. scanner、API 和中断恢复使用同一策略2配置契约。
5. 窗口外数值异常不影响窗口内策略，窗口内异常仍被拒绝。
6. 所有股票终态都会推动实时 processed 进度。
7. 页面刷新、完成和结果详情均可正常运行。
8. 离线测试、编译、前端构建和 `git diff --check` 全部通过。

---

## 10. 本次复审验证结果

### 已确认修复

- 最近 5 日第一天放量大跌可以被否决。
- `V20=0` 数据不会入选。
- 策略2 JSON 原因字段返回数组。
- 候选排序包含风险比与代码稳定排序。
- 候选持久化失败不会先广播候选。

### 直接复现结果

```text
invalid_prefix_outside_window= False INVALID_MARKET_DATA
future_cache_fresh= True
s2_list_with_s1_task= {'candidates': [], 'total': 0}
generic_task_types= ['STRATEGY_2_EXTREME_DRY_STABLE', 'STRATEGY_1_CUP_HANDLE']
scanner_invalid_cross_config=accepted
failed_progress_callbacks= []
non_date_strings= None
```

### 自动化与构建

- 针对性复审测试：`78 passed`
- 离线全量测试：`396 passed`
- 完整测试：`400 passed, 1 failed`
  - 失败项：外部东财接口连接中断。
- Python compileall：通过
- 前端生产构建：通过，但构建不能发现本报告指出的 Vue 运行时作用域错误。
- `git diff --check 82e337a..HEAD`：失败
  - 原因：上一份审核文档第 16 行存在尾随空格。

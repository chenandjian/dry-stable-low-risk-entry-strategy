# 代码问题修复第五轮复查报告

> 本报告已被最终复查报告 `2026-06-09-bug-fix-final-recheck.md` 替代。请以最终复查报告中的结论和修复要求为准。

## 1. 检查范围

本次复查聚焦第四轮剩余问题：

* 不可观察周期是否完整排除出回测统计
* 多源失败兼容字段是否与 `source_errors` 一致
* VCP 稳定 ID 测试是否真正覆盖断言路径

继续遵循用户确认：BUG-008 不再作为问题。

---

## 2. 总体结论

第四轮主要问题已完成大部分修复：

* `hit_*`、`false_breakout_*` 已改为 `bool | None`。
* 聚合命中率、假突破率、分数分层已排除不可观察样本。
* 多源全部失败和全部忙碌时，兼容字段已有回填逻辑。
* VCP 测试增加了结构日期断言和防空保护。

当前仍有三个明确的数据一致性问题：

1. 按判定汇总仍把不可观察收益当成 0。
2. 主源失败、备用源成功时，主源兼容字段仍为空。
3. 混合“失败 + 忙碌”场景中，`fallback_source` 与 `fallback_error` 可能指向不同数据源。

---

## 3. 问题清单

| 编号 | 问题 | 严重程度 | 影响范围 | 是否必须修复 |
| --- | --- | --- | --- | --- |
| ROUND5-001 | 按判定汇总将不可观察收益当成 0 | 高 | 回测策略判定收益统计 | 是 |
| ROUND5-002 | 主源失败、备用源成功时主源兼容字段为空 | 中 | 数据源质量统计、任务详情 | 是 |
| ROUND5-003 | 混合失败/忙碌时备用源名称与错误不一致 | 中 | 故障定位、接口一致性 | 是 |
| ROUND5-004 | 部分 VCP ID 测试仍保留条件断言路径 | 低 | 防回归能力 | 建议修复 |

---

## 4. 详细问题分析

### ROUND5-001：按判定汇总将不可观察收益当成 0

#### 问题现象

`summarize_by_verdict()` 仍使用：

```python
grouped[verdict]["returns"].append(ret_10d or 0.0)
```

当 `ret_10d=None` 时，会被转换成 `0.0` 并进入平均收益分母。

#### 代码证据

* `scanner/backtester.py:335-338`

#### 已执行复现实验

输入两个相同判定样本：

* 样本一：`ret_10d=10.0`
* 样本二：`ret_10d=None`

当前结果：

```text
count=2
avg_ret_10d=5.0
```

正确的可观察 10 日平均收益应为 `10.0`，不可观察样本不应作为 0 收益参与计算。

#### 影响

* 越靠近回测结束日期的候选越多，按判定平均收益被压低得越严重。
* 不同判定类型若出现时间分布不同，横向比较会失真。

#### 修复建议

1. 仅当 `ret_10d is not None` 时加入 `returns`。
2. 保留总候选数 `count`，并新增 `observed_10d_count`。
3. 当没有可观察收益时，`avg_ret_10d` 应为 `None`，不要伪装成 0。

#### 验证方式

一个 `10%` 收益样本加一个不可观察样本，结果应为：

```text
count=2
observed_10d_count=1
avg_ret_10d=10.0
```

---

### ROUND5-002：主源失败、备用源成功时主源兼容字段为空

#### 问题现象

`_build_all_failed_result()` 只在全部失败时回填兼容字段。备用源成功返回路径仍只写入成功源的尝试次数，没有根据 `source_errors` 回填主源失败信息。

#### 代码证据

* `scanner/engine.py:612-619`：成功返回路径。
* `scanner/engine.py:657-692`：兼容字段回填仅用于全部失败结果。

#### 已执行复现实验

模拟：

* `baidu` 尝试 2 次后超时
* `sina` 第 1 次成功

当前结果：

```text
primary_source=baidu
primary_attempts=0
primary_error=None
fallback_source=sina
fallback_attempts=1
source_errors={"baidu": "attempts=2 error=timeout"}
```

#### 影响

主数据源真实失败被隐藏。只查询兼容字段时，会误认为主源未尝试且未失败。

#### 修复建议

成功返回前，根据 `source_errors[chain[0]]` 回填 `primary_attempts` 和 `primary_error`。备用源成功字段继续记录实际成功源和尝试次数。

---

### ROUND5-003：混合失败/忙碌时备用源名称与错误不一致

#### 问题现象

全部失败结果初始化时将 `fallback_source` 固定为 `chain[-1]`。之后代码从最后一个实际失败源回填 `fallback_attempts` 和 `fallback_error`，但通常不会同步修改 `fallback_source`。

#### 代码证据

* `scanner/engine.py:663-667`：`fallback_source=chain[-1]`
* `scanner/engine.py:675-682`：从最后实际失败源回填错误，但只在 `fallback_source == chain[0]` 时修改源名称。

#### 已执行复现实验

模拟：

* `baidu` 失败
* `sina` 失败
* `tencent` 锁忙

当前结果：

```text
fallback_source=tencent
fallback_attempts=3
fallback_error=sina failed
```

错误来自新浪，但源名称显示腾讯。

#### 影响

任务详情和数据源质量统计会把错误归因给错误的数据源。

#### 修复建议

找到最后一个实际失败源后，必须同时设置：

* `fallback_source`
* `fallback_attempts`
* `fallback_error`

忙碌源仍保留在 `source_errors` 中，不应冒充最后实际失败源。

---

### ROUND5-004：部分 VCP ID 测试仍保留条件断言路径

#### 问题现象

VCP 测试已有明显改善，但仍有测试只保证“至少一个窗口/数据集产生 VCP”，核心相同或不同 ID 断言位于：

```python
if has_vcp_a and has_vcp_b:
```

如果只有一侧产生 VCP，测试仍能通过而不验证稳定 ID。

#### 涉及测试

* `tests/test_single_stock_backtest.py::test_vcp_identity_stable_across_adjacent_detection_days`
* `tests/test_single_stock_backtest.py::test_vcp_identity_differs_for_different_structures`

#### 修复建议

测试必须明确断言两侧都产生目标 VCP，再无条件比较 `_build_pattern_entry()` 生成的 `patternId` 和 `_pattern_identity()`。

---

## 5. 已确认修复完成

以下项目本轮确认完成：

* 不可观察周期的 `hit_*` 和 `false_breakout_*` 默认使用 `None`。
* 总体命中率、假突破率和止损率排除 `None`。
* 分数分层命中率和平均收益排除不可观察样本。
* 多源全部失败时回填兼容字段。
* 多源全部忙碌时兼容错误标记为 `data source busy`。
* VCP 使用真实收缩结构日期生成 ID。
* 数据库迁移、错误详情 JSON、市场数据注入继续保持有效。
* BUG-008 继续按用户确认排除。

---

## 6. 建议修复顺序

1. 修复按判定汇总的不可观察收益处理。
2. 修复备用源成功时主源兼容字段回填。
3. 修复混合失败/忙碌场景的备用源名称一致性。
4. 收紧 VCP ID 测试断言。

---

## 7. 最终修复实施方案

本节是给修复 AI 的直接执行方案。目标是一次完成剩余问题，不再在成功路径、失败路径和测试之间留下不同语义。

### 7.1 修复 ROUND5-001：统一不可观察收益统计语义

#### 需要修改的文件

* `scanner/backtester.py`
* `tests/test_dry_stable_backtester.py`
* `tests/test_backtester.py`

#### 数据语义

必须明确区分：

| 值 | 含义 |
| --- | --- |
| `ret_10d=None` | 没有完整 10 日观察数据，不可计算 |
| `ret_10d=0.0` | 有完整 10 日数据，实际收益为 0 |
| `ret_10d>0` / `<0` | 有完整观察数据的正/负收益 |

禁止使用 `ret_10d or 0.0`，因为它会同时混淆 `None` 和真实的 `0.0`。

#### 推荐实现

修改 `summarize_by_verdict()`，每个判定组同时维护：

```python
{
    "count": 0,
    "observed_10d_count": 0,
    "returns": [],
}
```

推荐逻辑：

```python
def summarize_by_verdict(rows: list) -> dict:
    grouped = {}
    for row in rows:
        verdict = row.get("verdict", "未知") if isinstance(row, dict) else getattr(row, "verdict", "未知")
        ret_10d = row.get("ret_10d") if isinstance(row, dict) else getattr(row, "ret_10d", None)
        key = verdict or "未知"

        group = grouped.setdefault(
            key,
            {"count": 0, "observed_10d_count": 0, "returns": []},
        )
        group["count"] += 1
        if ret_10d is not None:
            group["observed_10d_count"] += 1
            group["returns"].append(ret_10d)

    return {
        key: {
            "count": value["count"],
            "observed_10d_count": value["observed_10d_count"],
            "avg_ret_10d": (
                round(sum(value["returns"]) / len(value["returns"]), 2)
                if value["returns"]
                else None
            ),
        }
        for key, value in grouped.items()
    }
```

#### 兼容性要求

* 保留已有 `count` 和 `avg_ret_10d` 字段。
* 新增 `observed_10d_count`。
* 没有可观察数据时，推荐 `avg_ret_10d=None`，明确表示不可计算。
* 检查前端或输出层是否假设 `avg_ret_10d` 一定是数字；若需要兼容显示，应在展示层将 `None` 显示为 `--`，不要在数据层改成 0。

#### 必须新增的测试

在 `tests/test_dry_stable_backtester.py` 增加：

1. 一个 `10.0` 加一个 `None`：
   * `count == 2`
   * `observed_10d_count == 1`
   * `avg_ret_10d == 10.0`
2. 一个真实 `0.0` 加一个 `None`：
   * `observed_10d_count == 1`
   * `avg_ret_10d == 0.0`
3. 全部为 `None`：
   * `count` 保留真实候选数量
   * `observed_10d_count == 0`
   * `avg_ret_10d is None`
4. 同时覆盖字典输入和 `BacktestResult` 输入。

---

### 7.2 修复 ROUND5-002/003：统一数据源兼容字段构建

#### 需要修改的文件

* `scanner/engine.py`
* `tests/test_engine_fresh_fetch.py`

#### 核心原则

不要继续分别在“备用源成功”和“全部失败”路径手动拼接兼容字段。应提供一个统一 helper，根据完整源链、实际结果和 `source_errors` 生成兼容字段。

兼容字段语义必须固定：

| 字段 | 语义 |
| --- | --- |
| `primary_source` | 配置链首源 |
| `primary_attempts` | 首源实际网络尝试次数；只忙碌则为 0 |
| `primary_error` | 首源最终错误；只忙碌则为 `data source busy` |
| `fallback_source` | 最后一个实际成功或实际失败的非主源；若不存在则等于主源 |
| `fallback_attempts` | `fallback_source` 的实际网络尝试次数；忙碌为 0 |
| `fallback_error` | `fallback_source` 的最终错误；成功时为 `None` |
| `source_errors` | 所有出现过失败或忙碌的数据源完整详情 |

#### 推荐重构

保留 `_parse_source_error_entry()`，新增统一 helper，例如：

```python
def _apply_source_compatibility_fields(
    result: FetchResult,
    chain: list[str],
    source_errors: dict[str, str],
    *,
    selected_source: str | None,
    selected_attempts: int = 0,
) -> FetchResult:
    ...
```

参数语义：

* `selected_source`：
  * 成功时为实际成功数据源。
  * 全部失败时为最后一个实际网络失败源。
  * 全部忙碌时为 `None`。
* `selected_attempts`：成功数据源的实际尝试次数；失败场景可从 `source_errors` 解析。

推荐逻辑：

```python
primary = chain[0]
result.primary_source = primary

primary_entry = source_errors.get(primary)
if primary_entry:
    attempts, error = _parse_source_error_entry(primary_entry)
    result.primary_attempts = attempts
    result.primary_error = "data source busy" if primary_entry == "busy" else error
elif selected_source == primary:
    result.primary_attempts = selected_attempts
    result.primary_error = None

if selected_source and selected_source != primary:
    result.fallback_source = selected_source
    result.fallback_attempts = selected_attempts
    result.fallback_error = None if result.data is not None else parsed_selected_error
else:
    result.fallback_source = primary
    result.fallback_attempts = 0
    result.fallback_error = None
```

对于全部失败场景，先从反向源链中找到最后一个 `entry != "busy"` 的源作为 `selected_source`。如果所有源都忙碌：

```python
result.primary_error = "data source busy"
result.fallback_source = chain[-1] if len(chain) > 1 else chain[0]
result.fallback_attempts = 0
result.fallback_error = "data source busy"
```

#### 成功返回路径必须修改

当前 `_fetch_with_retry()` 在 `if data:` 中直接构造 `FetchResult`。修改为：

1. 先构造成功结果，设置 `data`、`source_errors`。
2. 调用统一 helper。
3. 返回 helper 处理后的结果。

伪代码：

```python
result = FetchResult(
    data=merged,
    primary_source=chain[0],
    fallback_source=ds_name,
    source_errors=source_errors,
)
return _apply_source_compatibility_fields(
    result,
    chain,
    source_errors,
    selected_source=ds_name,
    selected_attempts=used_attempts,
)
```

这样主源失败、备用源成功时：

```text
primary_source=baidu
primary_attempts=2
primary_error=timeout
fallback_source=sina
fallback_attempts=1
fallback_error=None
```

#### 全部失败路径必须修改

`_build_all_failed_result()` 不应预先将 `fallback_source` 固定为 `chain[-1]` 后只修改错误。它必须先确定最后实际失败源，再同步写入源名称、尝试次数和错误。

目标示例：

```text
baidu=失败
sina=失败
tencent=忙碌
```

应输出：

```text
primary_source=baidu
primary_error=baidu failed
fallback_source=sina
fallback_error=sina failed
source_errors.tencent=busy
```

#### 必须新增的测试矩阵

在 `tests/test_engine_fresh_fetch.py` 增加参数化测试或等价独立测试：

| 场景 | 预期 |
| --- | --- |
| 主源第一次成功 | primary 成功字段正确；fallback 不伪造失败 |
| 主源失败、第二源成功 | primary 记录失败；fallback 指向第二源且 error=None |
| 主源忙碌、第二源成功 | primary_error=`data source busy`；fallback 指向第二源 |
| 主源失败、第二源失败、第三源成功 | primary 指向首源失败；fallback 指向第三源成功 |
| 主源失败、第二源失败、第三源忙碌 | fallback 指向第二源失败，不指向第三源 |
| 三源全部失败 | primary/最后失败备用源与错误一致 |
| 三源全部忙碌 | attempts 均为 0，错误为 `data source busy` |

每个测试都必须同时断言：

* `primary_source/attempts/error`
* `fallback_source/attempts/error`
* `source_errors`

---

### 7.3 修复 ROUND5-004：让 VCP ID 测试无条件覆盖核心路径

#### 需要修改的文件

* `tests/test_single_stock_backtest.py`

#### 当前测试问题

测试中仍存在：

```python
assert has_vcp_a or has_vcp_b
if has_vcp_a and has_vcp_b:
    ...
```

这意味着只有一个窗口识别出 VCP 时，核心稳定性断言不会执行。

#### 推荐测试方式

不要通过完整策略引擎结果间接等待 VCP 出现。直接测试负责生成 identity 的输入和输出，保证测试目标单一。

##### 测试一：同一 VCP 在相邻窗口 ID 相同

1. 构造明确能够被 `_find_vcp_contractions()` 识别的基础窗口。
2. 相邻窗口仅追加不会改变收缩结构的平稳 K 线。
3. 对两个窗口调用 `_find_vcp_contractions()`。
4. 无条件断言两个窗口均至少有 2 个收缩结构。
5. 构造两个 VCP evaluation，分别调用 `_build_pattern_entry()`。
6. 无条件断言：

```python
assert entry_a["patternId"] == entry_b["patternId"]
assert _pattern_identity(entry_a) == _pattern_identity(entry_b)
assert entry_a["vcpStartDate"] == entry_b["vcpStartDate"]
assert entry_a["vcpEndDate"] == entry_b["vcpEndDate"]
```

##### 测试二：不同 VCP ID 不同

1. 构造两个明确不同的收缩结构。
2. 无条件断言两组数据均产生收缩结构。
3. 分别调用 `_build_pattern_entry()`。
4. 无条件断言：

```python
assert entry_a["patternId"] != entry_b["patternId"]
assert _pattern_identity(entry_a) != _pattern_identity(entry_b)
```

#### 禁止的测试写法

* 禁止 `if both_detected:` 后才执行核心断言。
* 禁止只检查 `_find_vcp_contractions()` 日期，不检查最终 `_build_pattern_entry()`。
* 禁止只检查两个手工 tuple，而不检查生产函数 `_pattern_identity()`。

---

### 7.4 推荐执行步骤

修复 AI 应严格按以下小步顺序执行：

1. 先新增 `summarize_by_verdict()` 的失败测试。
2. 修复判定汇总，并单独运行回测测试。
3. 新增完整数据源兼容字段测试矩阵。
4. 提取统一兼容字段 helper，同时接入成功和全部失败路径。
5. 重写 VCP ID 测试，确保核心断言无条件执行。
6. 运行针对性测试。
7. 运行离线全量测试。
8. 运行编译检查。
9. 最后检查 `git diff`，确认未修改 BUG-008、评分制和无关模块。

---

### 7.5 精确验收命令

```bash
python -m pytest tests/test_dry_stable_backtester.py tests/test_backtester.py -q
python -m pytest tests/test_engine_fresh_fetch.py tests/test_scan_task_tracking.py -q
python -m pytest tests/test_single_stock_backtest.py -q
python -m pytest tests -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_yfinance_hist.py
python -m compileall analyzer scanner main.py server.py tests -q
```

---

### 7.6 一次性完成判定

只有同时满足以下条件，才可声明本轮修复完成：

1. `summarize_by_verdict()` 不再包含 `ret_10d or 0.0`。
2. 返回结果包含 `observed_10d_count`。
3. 无可观察收益时 `avg_ret_10d` 不伪装成 0。
4. 主源失败、备用源成功时，主源错误兼容字段完整。
5. 任意结果中的 `fallback_source` 与 `fallback_error` 指向同一源。
6. `source_errors` 保留所有失败和忙碌详情。
7. VCP 相同/不同结构测试均无条件执行最终 identity 断言。
8. 上述精确验收命令全部通过。

---

## 8. 给修复 AI 的执行要求

1. 不要处理 BUG-008。
2. 不要重新启用 mootdx。
3. 不可观察收益不能作为 0 进入任何统计。
4. `primary_source/primary_error` 和 `fallback_source/fallback_error` 必须分别指向同一数据源。
5. 测试必须无条件执行核心断言，不允许只验证一侧产生数据。
6. 优先提取统一的数据源兼容字段 helper，不要在多个返回路径复制回填逻辑。
7. 保持现有接口字段兼容，只允许新增 `observed_10d_count`。

---

## 9. 回归测试清单

* 按判定汇总排除 `ret_10d=None`
* 按判定汇总返回总数与有效观察数
* 主源失败备用源成功时主源兼容字段正确
* 最后源忙碌、前一备用源失败时备用源名称与错误一致
* 全部失败兼容字段与 `source_errors` 一致
* 相邻窗口两侧均明确产生 VCP 并生成相同 ID
* 两个不同结构均明确产生 VCP 并生成不同 ID

---

## 10. 验证结果

针对性测试：

```bash
python -m pytest tests/test_backtester.py tests/test_engine_fresh_fetch.py tests/test_single_stock_backtest.py tests/test_scan_task_tracking.py tests/test_dry_stable_backtester.py -q
```

结果：`65 passed`。

离线全量测试：

```bash
python -m pytest tests -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_yfinance_hist.py
```

结果：`161 passed`。

编译检查：

```bash
python -m compileall analyzer scanner main.py server.py tests -q
```

结果：通过。

---

## 11. 最终交付标准

1. 不可观察样本不污染任何回测收益和命中率统计。
2. 数据源兼容字段与完整错误详情保持一致。
3. VCP 稳定 ID 测试无条件覆盖相同和不同结构。
4. 离线测试与编译检查全部通过。

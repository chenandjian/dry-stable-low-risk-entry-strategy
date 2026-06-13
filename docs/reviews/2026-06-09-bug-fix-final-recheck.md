# 代码问题最终复查报告

> `FINAL-001` 已修复并通过复查。本报告已由 `2026-06-09-bug-fix-completion-recheck.md` 替代。

## 1. 总体结论

第五轮修复方案中的核心问题均已完成：

* 按判定汇总不再把不可观察收益当作 0。
* 返回 `observed_10d_count`，无可观察收益时 `avg_ret_10d=None`。
* 主源失败、备用源成功时，主源兼容字段已正确回填。
* 混合失败/忙碌场景中，最后实际失败备用源与错误能够对应。
* VCP 测试已直接比较生产 `patternId` 和 `_pattern_identity()`，核心断言不再空通过。
* 离线全量测试与编译检查通过。

当前只剩一个数据源兼容字段边界问题。修复后可完成本轮代码审查。

---

## 2. 最后剩余问题

### FINAL-001：仅主源失败、所有备用源忙碌时兼容字段自相矛盾

#### 严重程度

中。

#### 触发条件

数据源链：

```text
baidu -> sina -> tencent
```

实际结果：

* `baidu` 获取失败。
* `sina` 锁忙，未进行网络尝试。
* `tencent` 锁忙，未进行网络尝试。

#### 当前结果

直接复现实验输出：

```text
primary_source=baidu
primary_attempts=2
primary_error=timeout

fallback_source=baidu
fallback_attempts=0
fallback_error=None

source_errors={
  "baidu": "attempts=2 error=timeout",
  "sina": "busy",
  "tencent": "busy"
}
```

`fallback_source` 显示为 `baidu`，但对应尝试次数和错误为空。字段看起来像“百度作为备用源且成功”，与真实情况不符。

#### 根本原因

`scanner/engine.py::_apply_source_compatibility_fields()` 中：

```python
else:
    result.fallback_source = primary
    result.fallback_attempts = 0
    result.fallback_error = None
```

当全部失败 helper 选择的最后实际失败源就是主源时，会进入该分支。代码声称 fallback “mirrors primary”，但并未真正复制主源的尝试次数和错误。

#### 推荐修复方案

统一定义：如果没有实际进行网络请求的非主源，但存在忙碌备用源，则兼容 fallback 字段应表示最后一个忙碌备用源。

推荐输出：

```text
primary_source=baidu
primary_attempts=2
primary_error=timeout

fallback_source=tencent
fallback_attempts=0
fallback_error=data source busy
```

完整细节继续保存在 `source_errors`。

#### 推荐实现

在 `_build_all_failed_result()` 中确定 `selected_source` 后：

1. 如果 `selected_source != chain[0]`，沿用当前实际失败源逻辑。
2. 如果 `selected_source == chain[0]` 且存在忙碌备用源：
   * 先调用统一 helper 回填主源。
   * 将 fallback 字段设置为源链中最后一个忙碌的非主源。
3. 如果源链只有主源，则 fallback 可以镜像主源，但必须真正镜像：
   * `fallback_source = primary_source`
   * `fallback_attempts = primary_attempts`
   * `fallback_error = primary_error`

示意代码：

```python
result = _apply_source_compatibility_fields(...)

if selected_source == chain[0]:
    busy_fallbacks = [
        ds for ds in chain[1:]
        if source_errors.get(ds) == "busy"
    ]
    if busy_fallbacks:
        result.fallback_source = busy_fallbacks[-1]
        result.fallback_attempts = 0
        result.fallback_error = "data source busy"
    elif len(chain) == 1:
        result.fallback_source = result.primary_source
        result.fallback_attempts = result.primary_attempts
        result.fallback_error = result.primary_error
```

#### 必须增加的测试

在 `tests/test_engine_fresh_fetch.py` 增加：

```python
def test_primary_failed_all_fallbacks_busy_has_consistent_compatibility_fields():
    ...
```

必须断言：

```python
assert result.primary_source == "baidu"
assert result.primary_attempts == 2
assert result.primary_error == "timeout"

assert result.fallback_source == "tencent"
assert result.fallback_attempts == 0
assert result.fallback_error == "data source busy"

assert result.source_errors == {
    "baidu": "attempts=2 error=timeout",
    "sina": "busy",
    "tencent": "busy",
}
```

另增加单源链测试，确认 fallback 真正镜像 primary，不出现同源但错误为空。

---

## 3. 已确认完成

以下内容无需继续修改：

* BUG-008，已按用户确认排除。
* 量干 12 分制。
* 用户主动配置阈值。
* `baidu`、`sina`、`tencent` 三数据源范围。
* 真实阻力与无效止损目标处理。
* ATR 止损过近拦截。
* 统一策略引擎与历史回测真实止损。
* VCP 稳定结构 ID。
* 指数配置接入和历史回测市场数据注入。
* `source_errors` 数据库迁移与 JSON 持久化。
* 不可观察周期的总体统计、分层统计和按判定汇总。

---

## 4. 最终修复要求

1. 仅修改数据源兼容字段边界逻辑和对应测试。
2. 不要重构策略、评分、缓存或前端。
3. `fallback_source`、`fallback_attempts`、`fallback_error` 必须描述同一个源。
4. 保持现有 `source_errors` 完整详情。
5. 增加“主源失败、所有备用源忙碌”和“单源失败”两个测试。

---

## 5. 最终验收命令

```bash
python -m pytest tests/test_engine_fresh_fetch.py tests/test_scan_task_tracking.py -q
python -m pytest tests -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_yfinance_hist.py
python -m compileall analyzer scanner main.py server.py tests -q
```

全部通过且字段语义符合 FINAL-001 要求后，本轮审查可以结束。

---

## 6. 本次验证结果

```text
tests/test_dry_stable_backtester.py + tests/test_backtester.py: 16 passed
tests/test_engine_fresh_fetch.py + tests/test_scan_task_tracking.py: 47 passed
tests/test_single_stock_backtest.py: 13 passed
离线全量测试: 172 passed
compileall: passed
```

# 代码问题检查报告

## 1. 检查范围

* 策略3任务 `20260625-183554`
* 策略3支撑区 V2 风险收益计算
* 候选股票从 13 个下降到 1 个的问题
* `task_stocks.status_reason` 与 `error_detail.rejectReasons` 分布

---

## 2. 总体结论

存在一个中高等级实现语义 bug：支撑区 V2 将 `key_support` 直接用于战术止损和风险比计算，导致很多趋势仍有效、支撑状态为 `VALID` 的股票被远处关键支撑放大风险比，从而触发 `RISK_RATIO_TOO_HIGH`。

这不是“跌破支撑排除”导致的候选减少。任务中 `SUPPORT_TEST_FAILED` 只有 4 只，真正异常增长的是 `RISK_RATIO_TOO_HIGH`。

修复后，任务 `20260625-183554` 用本地 OHLC 重新评估，候选恢复为 15 个。

---

## 3. 问题清单

| 编号 | 问题 | 严重程度 | 影响范围 | 是否必须修复 |
| --- | --- | --- | --- | --- |
| BUG-S3-SUPPORT-001 | key_support 被错误当成战术止损支撑，导致风险比异常偏高 | 高 | 策略3候选数量 / 风险收益判断 | 是 |

---

## 4. 详细问题分析

### BUG-S3-SUPPORT-001：key_support 误用为战术止损支撑

#### 问题现象

策略3支撑区 V2 上线后，任务 `20260625-183554` 候选数从之前的 13 个下降到 1 个。

#### 涉及模块

* `strategy3/risk.py::compute_strategy3_risk()`
* `strategy3/indicators.py::_compute_support_levels()`
* `tests/test_strategy3_engine.py`

#### 证据链

排查任务 `20260625-183554`：

* 总股票：4992
* 流动性过滤：2549
* 候选：1
* `SUPPORT_TEST_FAILED`：4
* `RISK_RATIO_TOO_HIGH`：521

对比此前 13 只候选，12 只被 `RISK_RATIO_TOO_HIGH` 排除，但其 `supportStatus` 大多是 `VALID`，说明并非支撑失效。

示例：

```text
688099 晶晨股份
keySupport = 87.62
currentClose = 100.79
riskRatio = 15.48%
supportStatus = VALID
rejectReasons = ["RISK_RATIO_TOO_HIGH", "RR_TOO_LOW"]
```

原因是 `risk.py` 将远处 `key_support` 直接设为 `tactical_support`，止损线随之过低，风险比被放大。

#### 修复方式

修复后逻辑：

1. `key_support` 继续用于结构有效性和缩量企稳判断。
2. 战术风险选择最近的有效支撑区：
   * `short_support`
   * `key_support`
   * `strong_support`
   * MA20
   * MA60
3. 选择规则保持原策略3低风险语义：
   * 支撑价必须低于当前价；
   * 优先选择距离当前价最近且至少有 1% 安全距离的支撑；
   * 止损使用该支撑区下沿再扣 `support_stop_buffer_pct`。

#### 验证结果

新增测试：

```text
test_risk_model_uses_nearest_support_zone_for_tactical_risk_when_key_support_is_far
```

该测试先失败，证明旧代码会把远处 `key_support` 当作战术支撑；修复后通过。

任务 `20260625-183554` 本地重评估结果：

* 候选数：15
* `RISK_RATIO_TOO_HIGH`：521 降至 215
* `SUPPORT_TEST_FAILED`：仍为 4

---

## 5. 建议修复顺序

已完成：

1. 先定位排除分布。
2. 再对比原 13 只候选的逐股 reject reason。
3. 确认风险比异常来自战术支撑选择。
4. 写失败测试复现。
5. 修复 `risk.py`。
6. 重评估任务验证候选恢复。

---

## 6. 给修复 AI 的执行要求

后续如果继续优化策略3支撑区，请遵守：

1. 不要把 `key_support` 直接等同于战术止损支撑。
2. `key_support` 主要判断结构有效性；战术风险应使用最近有效支撑区。
3. 每次改变候选数量时，必须输出 `status_reason` 分布和核心候选对比。
4. 不能只看候选数量，必须检查排除原因是否符合业务语义。

---

## 7. 回归测试清单

* 原 13 只候选逐股复评
* 任务 `20260625-183554` 全量本地重评估
* 支撑区有效但 key_support 较远时，不应误触发 `RISK_RATIO_TOO_HIGH`
* 支撑真正跌破时，仍能触发 `SUPPORT_TEST_FAILED` / `KEY_SUPPORT_FAILED`
* 策略3专项测试
* 后端完整回归

---

## 8. 不建议修改的内容

* 不要放宽支撑跌破规则来掩盖风险比问题。
* 不要降低 `max_risk_ratio` 或候选分数阈值来恢复候选数量。
* 不要修改策略1和策略2。
* 不要重新引入 yfinance。

---

## 9. 最终交付标准

修复后应满足：

1. 候选数量恢复到合理范围。
2. 远处 `key_support` 不再误伤战术风险比。
3. 真正支撑跌破仍能被排除。
4. 自动化测试覆盖该回归。
5. 文档说明 `key_support` 与战术支撑的边界。

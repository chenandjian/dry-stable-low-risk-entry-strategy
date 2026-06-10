# 代码问题修复第四轮复查报告

> 本报告已被 `2026-06-09-bug-fix-recheck-round5.md` 取代，请以第五轮复查结论为准。

## 1. 检查范围

本次复查针对第三轮报告所列问题，重点验证：

* `source_errors` 旧数据库迁移和全状态持久化
* VCP 使用真实收缩结构日期生成稳定 ID
* 无有效止损和 VCP 假突破统计
* 历史回测市场数据注入
* 新增回归测试的有效性

继续遵循用户确认：BUG-008 不再作为问题。

---

## 2. 总体结论

第三轮主要问题已基本修复：

* 已有数据库能够自动新增 `source_errors`。
* VCP ID 已使用真实收缩结构日期，直接相邻日复现实验 ID 保持一致。
* 无有效止损和 VCP 假突破已使用 `None` 并从对应统计中排除。
* 历史回测已支持注入固定市场数据。
* 数据源忙碌信息和最终成功分支错误详情能够持久化为 JSON。

当前仍有两个会造成数据失真的问题：

1. 未达到观察周期的回测样本仍被当作失败或未假突破，污染命中率与假突破率。
2. 多源全部失败时，兼容字段中的尝试次数和错误仍为空，与结构化错误详情矛盾。

---

## 3. 问题清单

| 编号 | 问题 | 严重程度 | 影响范围 | 是否必须修复 |
| --- | --- | --- | --- | --- |
| ROUND4-001 | 未观察到完整周期的样本被计为失败或未假突破 | 高 | 回测命中率、假突破率、分层统计 | 是 |
| ROUND4-002 | 多源全部失败时兼容错误字段仍为空 | 中 | 任务详情、失败统计、接口兼容 | 是 |
| ROUND4-003 | VCP 稳定 ID 回归测试存在空通过风险 | 中 | 防回归能力 | 是 |

---

## 4. 详细问题分析

### ROUND4-001：未观察到完整周期的样本被计为失败或未假突破

#### 问题现象

`ret_*` 默认值已经是 `None`，但对应的 `hit_*` 和 `false_breakout_*` 默认值仍是 `False`。

当未来数据不足 10、20 或 60 天时，`_calc_forward()` 会直接跳过该周期，导致：

* `ret_10d = None`
* `hit_10d = False`
* `false_breakout_10d = False`

聚合逻辑会过滤 `ret_10d=None`，但会把两个 `False` 当作有效观察值。

#### 代码证据

* `scanner/backtester.py:43-58`：`hit_*` 和 `false_breakout_*` 默认是 `False`。
* `scanner/backtester.py:259-261`：未来数据不足时直接 `continue`。
* `scanner/backtester.py:290-305`：聚合时所有非 `None` 的布尔值进入分母。
* `scanner/backtester.py:320-326`：评分分层同样使用默认 `False`。
* `scanner/backtester.py:330-344`：按判定汇总将 `ret_10d=None` 转换为 `0.0`。

#### 已执行复现实验

对仅有 5 天未来数据的样本计算：

```text
ret10=None
hit10=False
false_breakout10=False
```

该样本会被错误解释为“10 日收益未命中”和“10 日未发生假突破”，而实际是根本没有 10 日观察数据。

#### 影响

* 命中率被系统性压低。
* 假突破率被系统性压低。
* 回测区间末端样本越多，统计偏差越大。
* 分数分层和按策略判定汇总同样受污染。

#### 修复建议

1. 将 `hit_*` 和 `false_breakout_*` 定义为 `bool | None`，默认值设为 `None`。
2. 仅当对应周期的未来数据充足时设置布尔值。
3. `_aggregate()`、`_score_stratify()` 和 `summarize_by_verdict()` 必须排除不可观察样本。
4. 报告建议增加每个周期的有效样本数。

#### 验证方式

混合一个具有完整 10 日未来数据的样本和一个仅有 5 日数据的样本。10 日指标分母必须是 1，不能是 2。

---

### ROUND4-002：多源全部失败时兼容错误字段仍为空

#### 问题现象

`source_errors` 已能完整记录每个源的失败详情，但 `_fetch_with_retry()` 在所有源失败时重新创建 `FetchResult`，没有将真实尝试次数和错误回填到现有兼容字段。

#### 代码证据

* `scanner/engine.py:592-598`：每个源的尝试次数和错误只写入 `source_errors`。
* `scanner/engine.py:621-624`：全部失败时新建的结果没有设置 `primary_attempts`、`fallback_attempts`、`primary_error`。
* 只有遇到忙碌源时才设置 `fallback_error = "data source busy"`。

#### 已执行复现实验

模拟三个数据源全部失败：

```text
primary_attempts=0
fallback_attempts=0
primary_error=None
fallback_error=None
source_errors={
  "baidu": "attempts=2 error=baidu failed",
  "sina": "attempts=3 error=sina failed",
  "tencent": "attempts=3 error=tencent failed"
}
```

#### 影响

* 现有任务详情字段显示“没有尝试、没有错误”，与真实情况冲突。
* 依赖旧字段的前端、接口或统计逻辑无法获得正确失败信息。
* `source_errors` 与兼容字段之间缺乏一致性。

#### 修复建议

1. 遍历过程中保存每个源的尝试次数和最终错误。
2. 返回时将配置链首源回填到 `primary_*`。
3. 将最后实际尝试的备用源回填到 `fallback_*`。
4. 锁忙不应计作网络尝试次数，但错误字段应明确为 `data source busy`。
5. 保留 `source_errors` 作为完整三源详情。

#### 验证方式

模拟主源失败、备用源失败、全部忙碌、主源失败后备用源成功四类场景，检查兼容字段与 `source_errors` 一致。

---

### ROUND4-003：VCP 稳定 ID 回归测试存在空通过风险

#### 问题现象

新增的 `test_vcp_identity_stable_across_adjacent_detection_days` 在最终去重结果上进行检查。最终结果每个 pattern ID 本来只会保留一条记录，因此：

```python
if len(dates_list) > 1:
```

通常不会进入断言主体。即使 VCP 每天生成不同 ID，该测试也可能通过。

另一个真实日期测试只遍历实际产生的 VCP；如果样本没有产生 VCP，也会空通过。

#### 影响

当前实现经直接复现实验确认在简单相邻日场景下 ID 稳定，但自动化测试无法可靠防止未来回归。

#### 修复建议

1. 直接对相邻两个窗口调用 `_build_pattern_entry()` 或稳定 identity helper。
2. 明确断言两个相邻窗口均识别出同一 VCP。
3. 明确断言两个 entry 的 `patternId` 和 `_pattern_identity()` 相同。
4. 另加结构不同的 VCP，断言 ID 不同。

---

## 5. 已确认修复完成

以下项目本轮确认完成：

* `source_errors` 已加入旧数据库增量迁移列。
* `source_errors` 使用稳定 JSON 持久化。
* 忙碌数据源会进入结构化错误详情。
* 候选、普通扫描、跳过和失败分支均会保存错误详情。
* VCP ID 使用真实收缩结构日期，不再使用整个窗口边界。
* 简单相邻检测日 VCP identity 直接复现实验通过。
* 无有效止损不再进入止损命中率分母。
* VCP 不再使用杯柄突破价计算假突破率。
* 历史回测支持注入固定市场数据。
* BUG-008 继续按用户确认排除。

---

## 6. 建议修复顺序

1. 修复未观察周期的命中率与假突破率统计污染。
2. 回填多源兼容错误字段。
3. 重写 VCP 稳定 ID 测试，确保不会空通过。
4. 执行重点测试、离线全量测试和编译检查。

---

## 7. 给修复 AI 的执行要求

1. 不要处理 BUG-008。
2. 不要重新启用 mootdx。
3. 不要修改量干 12 分制及用户主动配置阈值。
4. 不可观察的回测结果必须使用 `None`，禁止用 `False` 或 `0` 代替。
5. 保持 `source_errors` 与现有兼容字段信息一致。
6. 测试必须明确触发目标业务路径，禁止只有循环内条件断言的空通过测试。

---

## 8. 回归测试清单

* 未来不足 10 日的样本不进入 10 日命中率分母
* 未来不足 10 日的样本不进入 10 日假突破率分母
* 分数分层排除不可观察样本
* 按策略判定汇总排除不可观察收益
* 多源全部失败时兼容尝试次数和错误正确
* 主源失败、备用源成功时兼容字段正确
* 全部忙碌时兼容字段正确
* 相邻窗口同一 VCP ID 明确相同
* 不同 VCP ID 明确不同

---

## 9. 验证结果

新增修复相关测试：

```bash
python -m pytest tests/test_backtester.py tests/test_single_stock_backtest.py tests/test_engine_fresh_fetch.py tests/test_scan_task_tracking.py -q
```

结果：`58 passed`。

离线全量测试：

```bash
python -m pytest tests -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_yfinance_hist.py
```

结果：`155 passed`。

完整测试：

```bash
python -m pytest tests -q
```

结果：`156 passed, 2 failed`。失败项为东财代理连接失败和 yfinance 限流，均属于外部网络测试。

编译检查：

```bash
python -m compileall analyzer scanner main.py server.py tests -q
```

结果：通过。

---

## 10. 最终交付标准

1. 所有回测指标只统计具有完整观察周期的有效样本。
2. 多源完整错误详情与兼容字段保持一致。
3. VCP 稳定身份测试明确覆盖相同与不同结构。
4. 离线测试全部通过，外部接口测试单独执行。

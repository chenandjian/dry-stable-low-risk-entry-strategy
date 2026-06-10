# 代码问题修复第二轮复查报告

> 本报告已被 `2026-06-09-bug-fix-recheck-round3.md` 取代，请以第三轮复查结论为准。

## 1. 检查范围

本次复查针对以下最新修复提交：

* `3714b9c`：历史回测真实止损与 `min_score`
* `e5d4d79`：VCP 模式类型与唯一身份
* `c2aee49`：最近阻力与配置接入
* 当前未提交的 `scanner/engine.py` 数据源错误记录修改

经用户确认，**BUG-008 多数据源前复权一致性不再作为问题，本报告已排除该项，不要求修复 AI 继续处理。**

---

## 2. 总体结论

上一轮的大部分修复方向已经落实：

* 历史回测已保存策略真实止损并恢复 `min_score` 过滤。
* `pattern_kind` 已加入结果模型和序列化结果。
* 最近阻力已改为从 pivot 与 swing high 候选中选择最低有效阻力。
* `near_pivot_below_pct` 已写入配置文件。
* 扫描与重新评估入口已读取 `market_environment.index_symbol`。

但目前仍不能交付。历史回测存在一个必现的未定义变量错误；VCP 唯一 ID 仍会发生碰撞；无效止损仍会生成合成目标和合成回测止损；指数配置只接入部分入口；新增数据源错误详情尚未持久化。

---

## 3. 问题清单

| 编号 | 问题 | 严重程度 | 影响范围 | 是否必须修复 |
| --- | --- | --- | --- | --- |
| ROUND2-001 | 历史回测筛出候选后会触发 `NameError` | 高 | 历史回测核心功能 | 是 |
| ROUND2-002 | VCP 唯一 ID 仍会发生碰撞和错误去重 | 高 | 单股回测、VCP 结果追踪 | 是 |
| ROUND2-003 | 无效止损仍生成合成目标与合成回测止损 | 高 | RR1、回测止损统计 | 是 |
| ROUND2-004 | 指数配置接入不完整，历史回测仍依赖实时网络 | 中 | 配置一致性、回测可复现性 | 是 |
| ROUND2-005 | 多源错误详情只存在内存，且忙碌源未记录 | 中 | 故障定位、任务失败记录 | 是 |
| ROUND2-006 | 关键修复仍缺少有效回归测试 | 中 | 回归风险 | 是 |

---

## 4. 详细问题分析

### ROUND2-001：历史回测筛出候选后会触发 `NameError`

#### 问题现象

`run_backtest()` 将策略结果赋值给变量 `r`，但调用 `_calc_forward()` 时使用了未定义变量 `result`。

#### 代码证据

* `scanner/backtester.py:190`：`r = evaluation.result`
* `scanner/backtester.py:222`：`_calc_forward(br, detect_close, result.breakout_price, future_data)`

函数作用域内不存在 `result` 赋值。只要 `evaluation.passed` 为真且分数达到 `min_score`，就会在该行触发 `NameError`。

#### 影响

历史回测在真正发现首个候选时直接中断，无法生成报告。

#### 修复建议

将调用中的 `result.breakout_price` 改为当前策略结果变量对应的值，并新增一个能让 `run_backtest()` 实际筛出候选的端到端单元测试。

#### 验证方式

构造固定通过的策略评估结果，执行 `run_backtest()`，确认：

1. 不触发 `NameError`。
2. 生成至少一个 `BacktestResult`。
3. 前向收益和止损命中字段被正常计算。

---

### ROUND2-002：VCP 唯一 ID 仍会发生碰撞

#### 问题现象

VCP ID 设计仍依赖杯柄字段，并且尝试使用的 `detectedDate` 在生成 ID 时尚未写入 `pattern`。

#### 代码证据

* `scanner/single_stock_backtest.py:243-245`：VCP identity 使用 `handleStartDate`、`handleLowDate`、`vcpContractions`。
* `scanner/single_stock_backtest.py:258-263`：VCP ID 使用相同字段。
* `scanner/single_stock_backtest.py:286-294`：先调用 `_pattern_id(code, pattern)`，之后才把 `detectedDate` 写入返回字典。
* VCP-only 的 `right_high_idx` 默认是 `-1`，`_handle_start_date()` 会得到数据窗口第一个日期；`handleLowDate` 通常为空。

因此，同一回测区间中收缩次数相同的多个 VCP 很可能生成相同 ID，并被错误合并。

#### 影响

* 不同 VCP 被误认为同一形态。
* 单股回测低估 VCP 数量。
* `firstDetectedDate`、得分及规则信息可能被错误合并。

#### 修复建议

1. 不要使用杯柄字段构造 VCP identity。
2. 从 VCP 检测结果中输出稳定的收缩区间日期，例如首个收缩开始日期与最后收缩结束日期。
3. 在生成 ID 前明确传入 `detected_date`，不要从尚未包含该字段的 `pattern` 字典回退读取。
4. 为“两个不同 VCP、收缩次数相同”的场景增加测试，确认 ID 不同。

---

### ROUND2-003：无效止损仍生成合成目标与合成回测止损

#### 问题现象

实时策略在 `risk <= 0` 时仍生成当前价 110% 和 120% 的合成目标。历史回测在真实止损无效或为 0 时，又回退使用 `breakout_price * 0.95`。

#### 代码证据

* `analyzer/key_prices.py:90-92`：`risk <= 0` 时生成百分比目标价。
* `scanner/backtester.py:270`：真实止损无效时回退到 `breakout_price * 0.95`。

#### 影响

* 无效止损场景仍可能展示看似正常的目标价。
* 回测会用一个线上策略并未采用的合成止损计算命中率。
* 策略异常被掩盖，回测统计失真。

#### 修复建议

1. `risk <= 0` 时，将 `target_1`、`target_2` 置为 0，并让风险收益与决策层明确拒绝该场景。
2. 历史回测遇到无效真实止损时，不得回退到突破价 95%；应标记该结果止损无效，或不纳入止损命中率统计。
3. 增加无效止损的实时策略与历史回测测试。

---

### ROUND2-004：指数配置接入不完整，历史回测仍依赖实时网络

#### 问题现象

扫描、重新评估和 CLI 已读取 `market_environment.index_symbol`，但服务详情页与历史回测仍直接调用无参数的 `fetch_market_index_daily()`。

#### 代码证据

* 已接入：`main.py:114`、`scanner/engine.py:104,449`
* 未接入：`server.py:623`、`scanner/backtester.py:156`

历史回测也没有市场数据注入参数，因此单元测试和历史结果仍依赖执行时的外部网络与最新指数数据。

#### 修复建议

1. 服务详情页读取同一份配置并传入指数代码。
2. 历史回测读取配置中的指数代码。
3. 为历史回测提供可选 `market_data` 或 `market_fetch_fn` 注入点，保证测试和历史结果可复现。

---

### ROUND2-005：多源错误详情未形成可用闭环

#### 问题现象

当前未提交修改在 `FetchResult` 中增加了 `source_errors`，但：

* 锁忙时只设置 `saw_busy`，没有把忙碌源写入 `source_errors`。
* `source_errors` 没有传给 `db.update_task_stock()`。
* 数据库任务记录仍只保存 `primary_error` 和 `fallback_error`。
* 全部失败时 `primary_attempts`、`fallback_attempts` 仍保持 0。

#### 影响

新增字段只在当前函数返回对象中短暂存在，扫描任务完成后无法查询完整失败详情。

#### 修复建议

在不进行破坏性数据库变更的前提下，至少应：

1. 将主源与最后备用源的真实尝试次数、错误回填到现有字段。
2. 锁忙源也必须进入结构化错误记录。
3. 若保留 `source_errors`，应将其写入现有日志或新增兼容字段，并提供读取方式。
4. 增加“忙碌 + 超时 + 空响应”组合测试，验证最终任务记录。

---

### ROUND2-006：关键修复仍缺少有效回归测试

#### 问题现象

最新修复没有为以下核心行为增加有效测试：

* `run_backtest()` 真正筛出候选后的执行路径
* 真实止损与 `min_score` 在 `run_backtest()` 中生效
* 两个收缩次数相同但区间不同的 VCP 生成不同 ID
* 最近 swing high 被选为 `target_1`
* `risk <= 0` 时禁止生成目标价
* 指数配置在所有入口生效
* 多源错误详情最终被任务记录保留

现有策略重点测试全部通过，但未覆盖 ROUND2-001 的必现 `NameError`，说明测试通过不能证明修复闭环。

---

## 5. 已确认修复完成

以下项目本轮确认已完成，不需要重复修改：

* ATR 止损过近状态参与买入决策拦截。
* `min_score` 已重新参与历史回测候选过滤。
* `BacktestResult` 已保存真实止损、入场区间和 `pattern_kind`。
* `pattern_kind` 已正式加入 `CupHandleResult` 并进入序列化结果。
* 最近阻力已不再直接使用最近 60 日最高价或任意日线 high。
* `near_pivot_below_pct` 已写入 `config.yaml`。
* 扫描和重新评估已按配置读取指数代码。
* BUG-008 已按用户确认排除。

---

## 6. 建议修复顺序

1. 修复历史回测 `NameError`，增加候选通过路径测试。
2. 重新设计 VCP 稳定身份并增加碰撞测试。
3. 禁止无效止损生成合成目标或合成回测止损。
4. 补齐指数配置入口和历史回测市场数据注入。
5. 完成多源错误详情的持久化闭环。
6. 执行策略重点测试与全量测试。

---

## 7. 给修复 AI 的执行要求

1. 不要处理 BUG-008，多数据源前复权一致性已由用户确认无问题。
2. 不要修改量干 12 分制。
3. 不要修改用户设置的 `min_price_stable_score: 5`。
4. 日线数据源仅使用 `baidu`、`sina`、`tencent`，不要重新启用 mootdx。
5. 不要重构无关模块。
6. 每个问题必须增加能复现问题的测试后再修改实现。
7. 历史回测不得使用线上策略之外的合成止损。
8. VCP ID 必须由稳定的 VCP 结构日期生成，不得依赖空杯柄字段。

---

## 8. 回归测试清单

* 历史回测发现候选时不触发 `NameError`
* 历史回测使用真实止损
* 无效真实止损不回退为突破价 95%
* `min_score` 能过滤候选
* 两个同收缩次数、不同区间的 VCP ID 不同
* 同一 VCP 在相邻检测日按既定规则稳定去重
* 最近确认 swing high 成为 `target_1`
* `risk <= 0` 时目标价为 0 且决策拒绝
* 服务详情页使用配置的指数代码
* 历史回测可注入固定市场数据
* 多源忙碌、超时和空响应均可从任务记录追踪

---

## 9. 验证结果

策略重点测试：

```bash
python -m pytest tests/test_key_prices.py tests/test_decision.py tests/test_cuphandle_strategy_engine.py tests/test_backtester.py tests/test_single_stock_backtest.py tests/test_engine_fresh_fetch.py tests/test_index_source.py -q
```

结果：`58 passed`。

全量测试：

```bash
python -m pytest tests -q
```

结果：`147 passed, 1 failed`。唯一失败为东财外部接口断开连接，与本轮修复无关。

---

## 10. 最终交付标准

1. 历史回测发现候选时可完整执行并生成报告。
2. VCP 在序列化、回测和去重链路中拥有稳定唯一身份。
3. 无效止损不会产生虚假的目标价或止损命中统计。
4. 指数配置在所有入口一致生效，历史回测可以离线复现。
5. 多源失败原因在扫描任务结束后仍可查询。
6. 新增回归测试覆盖上述问题，离线测试全部通过。

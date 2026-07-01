# 策略3任务 20260625-183554 策略逻辑复盘与优化建议

## 1. 检查范围

- 任务：`20260625-183554`
- 策略：`STRATEGY_3_STRONG_PULLBACK_SECOND_BREAKOUT`
- 数据库：`data/cuphandle.db`
- 代码模块：
  - `strategy3/engine.py`
  - `strategy3/indicators.py`
  - `strategy3/trend.py`
  - `strategy3/pullback.py`
  - `strategy3/volume_stability.py`
  - `strategy3/second_breakout.py`
  - `strategy3/risk.py`
  - `strategy3/scorer.py`
  - `strategy3/scanner.py`
  - `scanner/yfinance_source.py`
  - `scanner/daily_data_service.py`

## 2. 总体结论

本次任务扫描链路整体完成，没有数据源全量失败，也没有任务级异常：

- 股票池：`4992`
- 完成扫描：`4992`
- 流动性过滤：`2547`
- 策略评估成功/拒绝：`2444`
- 候选：`1`
- 失败：`0`
- 最新 K 线日期：`2026-06-25`

策略3只选出 1 只，不能简单归因于候选分数太高或风险比阈值太严。敏感性测试显示：

- `candidate_min_score` 从 75 降到 70，仍只有 1 只候选。
- `max_risk_ratio` 从 8% 放宽到 10% / 12%，仍只有 1 只候选。
- 同时放宽分数和风险比，仍只有 1 只候选。

真正影响策略结果的核心问题有三个：

1. **高优先级数据质量问题**：297 只股票因 yfinance fallback 写入了 OHLC 不一致数据，被策略3判为 `INVALID_MARKET_DATA`。
2. **中优先级策略实现偏差**：策略3设计中的 `relative_strength_60 = stock_return_60 - index_return_60`，扫描时没有传入指数数据，实际退化成 `return_60`。
3. **中优先级策略优化点**：风险收益模块用最保守的最低支撑计算止损，导致大量强势回踩股被 `RISK_RATIO_TOO_HIGH` 排除；应改成“结构支撑 + 战术止损”双层模型，而不是简单放宽风险阈值。

## 3. 问题清单

| 编号 | 问题 | 严重程度 | 影响范围 | 是否建议修复 |
| --- | --- | --- | --- | --- |
| S3-REVIEW-001 | yfinance fallback 写入 OHLC 不一致数据 | 高 | 数据可信度 / 策略1-3复用本地 K 线 | 是 |
| S3-REVIEW-002 | 策略3扫描未传入市场指数，`relative_strength_60` 退化 | 中 | 强势趋势过滤准确性 | 是 |
| S3-REVIEW-003 | 风险支撑位取最低支撑，止损过宽 | 中 | 候选数量 / 风险收益判断 | 是 |
| S3-REVIEW-004 | 只有正式候选，没有 near-miss 观察层 | 中 | 策略解释 / 参数优化效率 | 建议 |
| S3-REVIEW-005 | 单纯放宽分数或风险阈值无明显收益 | 低 | 参数调优方向 | 不建议单独修改 |

## 4. 详细问题分析

### S3-REVIEW-001：yfinance fallback 写入 OHLC 不一致数据

#### 现象

任务中有 297 只股票被策略3拒绝为：

```text
INVALID_MARKET_DATA
```

这些股票全部来自同一类数据源路径：

```text
primary_source = baidu
fallback_source = yfinance
source_errors = {"baidu":"busy","sina":"busy","tencent":"busy"}
```

抽样数据：

```text
000006 深振业Ａ
2026-06-25 open=7.75 high=7.52 low=7.23 close=7.36
```

这里 `high < open`，OHLC 结构不合法。

另一个例子：

```text
000066 中国长城
2026-06-25 open=17.46 high=20.80 low=18.31 close=20.47
```

这里 `low > open`，同样不合法。

#### 原因

`scanner/yfinance_source.py::_is_valid_ohlc()` 只检查了价格为有限正数，没有检查 OHLC 相互关系：

```python
high >= max(open, close, low)
low <= min(open, close, high)
```

因此 yfinance 返回的异常行可以进入 `daily_ohlc`，随后策略3在 `validate_ohlc_values()` 中才拒绝。

#### 影响

- 本次策略3有 297 只股票无法评估。
- 这些无效 K 线已经写入共享 `daily_ohlc`，后续策略1/策略2也可能复用。
- 前端看起来是“策略没选中”，实际是数据源污染。

#### 修复建议

1. 在 `scanner/yfinance_source.py::_is_valid_ohlc()` 中增加 OHLC 关系校验。
2. 在 `scanner/daily_data_service.py` 保存前增加统一 OHLC 校验，防止任何数据源写入非法日线。
3. 当某个源返回非法 OHLC 时，应把该源视为失败，继续尝试下一个源；如果所有源都失败，股票进入失败列表。
4. 对已污染的 `daily_ohlc`，建议提供一次修复脚本：
   - 找出 `high < max(open, close, low)` 或 `low > min(open, close, high)` 的行。
   - 删除这些非法行，或标记后重新拉取。

#### 验证方式

1. 构造一条 yfinance 返回的非法 K 线，断言 `_normalize_history()` 会过滤掉。
2. 构造所有源都返回非法数据，断言股票进入 `task_stocks.status='failed'`。
3. 重新扫描任务，`INVALID_MARKET_DATA` 数量应显著下降。

---

### S3-REVIEW-002：策略3扫描未传入市场指数，`relative_strength_60` 退化

#### 现象

设计文档要求：

```text
relative_strength_60 = stock_return_60 - index_return_60
```

但当前 `strategy3/scanner.py` 调用为：

```python
evaluation = engine.evaluate_at(data, code=code, name=name)
```

没有传入 `market_data`。

`strategy3/indicators.py` 在 `market_data` 为空时：

```python
index_return_60 = 0.0
relative_strength_60 = return_60 - index_return_60
```

实际等价于：

```text
relative_strength_60 = stock_return_60
```

#### 影响

策略3的“相对强度”目前不是相对于指数，而是股票自身 60 日收益。

这会产生两类偏差：

- 如果指数 60 日上涨很多，股票只是跟涨，也可能被误认为相对强。
- 如果指数 60 日下跌，股票小幅下跌但明显跑赢指数，也可能被错误排除。

#### 修复建议

1. 策略3扫描路径加载市场指数数据。
2. 调用 `engine.evaluate_at(..., market_data=market_window)`。
3. 市场数据必须按评估日截断，避免未来数据泄漏。
4. 如果市场指数获取失败，应明确记录 `NO_MARKET_DATA_RELATIVE_STRENGTH_FALLBACK`，而不是静默退化。

#### 验证方式

1. 构造股票 60 日收益 3%、指数 60 日收益 -5%，应得到 `relative_strength_60=8%`。
2. 构造股票 60 日收益 8%、指数 60 日收益 10%，应得到 `relative_strength_60=-2%`，触发弱相对强度。
3. 策略3扫描测试断言 `evaluate_at()` 被传入截断后的市场数据。

---

### S3-REVIEW-003：风险支撑位取最低支撑，止损过宽

#### 现象

本次非流动性过滤后的主要拒绝原因中：

```text
RISK_RATIO_TOO_HIGH: 541 只第一拒绝原因
RISK_RATIO_TOO_HIGH: 1173 次全量 reject reason
```

高分但被拒的样本主要集中在风险比：

```text
688206 概伦电子 score=76 risk=10.69% rr1=2.01
000921 海信家电 score=76 risk=15.09% rr1=1.06
301282 金禄电子 score=75 risk=19.14% rr1=1.05
688220 翱捷科技 score=74 risk=14.22% rr1=1.92
```

当前风险模块：

```python
support_price = min(pullback_low, ind.ma20, support_low)
stop_loss = support_price * 0.98
```

这会选择所有候选支撑中最低的一个，导致止损非常远。

#### 敏感性分析

单纯放宽风险阈值到 10% / 12%，候选仍只有 1 只，因为大量股票还同时触发 `RR_TOO_LOW` 或波动拒绝。

但如果试算“最近有效支撑”模型：

```text
support_price = max(低于当前价的 pullback_low / support_low / ma20 / ma60)
```

则基线阈值下会多出一个明显候选：

```text
000921 海信家电
原 risk=15.09%, rr1=1.06
新 risk≈3.73%, rr1≈4.30
score=76
```

这说明真正的问题不是风险阈值，而是止损支撑口径。

#### 修复建议

不要简单把 `max_risk_ratio` 放宽到 12% 或 15%。建议改成双层风险模型：

1. `structural_support`
   - 回踩以来最低点，代表趋势失效支撑。
   - 用于显示“结构破坏价”。
2. `tactical_support`
   - 当前价下方最近有效支撑。
   - 可取 `pullback_low / support_low / ma20 / ma60` 中低于当前价且最近的支撑。
   - 用于正式入选的止损和风险比。
3. `support_quality`
   - 若战术支撑距离当前价过近但没有成交量收缩、没有低点企稳，则不允许使用战术止损。
   - 避免把止损设得过近导致假低风险。

推荐入选口径：

```text
正式风险比 = (close - tactical_stop) / close
结构风险比 = (close - structural_stop) / close

入选要求：
- tactical_risk_ratio <= 8%
- rr1_tactical >= 1.5
- structural_risk_ratio <= 18% 或作为风险提示
```

#### 验证方式

1. 用 `000921` 作为回归样本，验证新模型能识别较近战术支撑。
2. 用深跌弱势股样本，验证不会因为某个短期低点靠近当前价而误入选。
3. 对比候选数量，应小幅增加，而不是从 1 只暴增到几十只。

---

### S3-REVIEW-004：缺少 near-miss 观察层

#### 现象

本次有 321 只股票没有硬否决，但总分低于 `candidate_min_score=75`。

此外有 22 只股票总分达到 70 以上但被硬过滤拦截，其中：

```text
RISK_RATIO_TOO_HIGH: 18
RECENT_OVERHEATED: 4
```

这些股票不应直接进入正式候选，但对策略优化很有价值。

#### 建议

新增策略3 near-miss 观察层，只用于诊断和页面展示，不进入正式候选：

```text
near_miss 条件：
- total_score >= 70
- 未触发深跌、趋势破坏、放量大跌等高危拒绝
- 只因风险比、RR、短期波动、回踩过浅等可观察原因未入选
```

展示字段：

- 差多少分入选。
- 被哪个硬过滤挡住。
- 当前风险比、RR1。
- 如果使用战术支撑模型，风险比会变成多少。

#### 价值

- 不降低正式候选质量。
- 能解释“为什么今天只有 1 只”。
- 后续参数优化有样本池，不用盲目调参。

---

### S3-REVIEW-005：不建议单纯放宽阈值

本次实测：

| 调整方案 | 候选数 |
| --- | --- |
| 当前默认 | 1 |
| `candidate_min_score=70` | 1 |
| `max_risk_ratio=10%` | 1 |
| `max_risk_ratio=12%` | 1 |
| `candidate_min_score=70 + max_risk_ratio=10%` | 1 |
| `candidate_min_score=70 + max_risk_ratio=12%` | 1 |

结论：

不建议先调低分数或放宽风险比。优先修数据质量、相对强度、风险支撑模型。

## 5. 建议修复顺序

1. 先修复 yfinance OHLC 合法性校验，阻止非法 K 线进入共享数据库。
2. 清理或重拉已污染的 `daily_ohlc`。
3. 修复策略3相对强度，扫描时传入截断后的市场指数数据。
4. 优化策略3风险模型，引入结构支撑和战术支撑。
5. 增加 near-miss 诊断层，辅助观察但不进入正式候选。
6. 最后再考虑是否微调 `candidate_min_score` 或 `max_risk_ratio`。

## 6. 给修复 AI 的执行要求

请按照以下要求修复：

1. 不要修改策略1和策略2核心规则。
2. 不要为了增加候选数直接放宽策略3分数或风险阈值。
3. yfinance 返回非法 OHLC 时，应视为该数据源失败，而不是写入 DB。
4. 任一数据源写入 `daily_ohlc` 前都必须通过统一 OHLC 合法性校验。
5. 策略3相对强度必须使用股票收益减指数收益；无法获取指数时必须有明确 fallback 标记。
6. 风险模型优化必须同时输出战术支撑、结构支撑、战术风险比、结构风险比。
7. near-miss 只能用于诊断展示，不得混入正式候选表，除非新建独立字段明确区分。
8. 修复后必须用任务 `20260625-183554` 或等价本地数据重跑验证。

## 7. 回归测试清单

- yfinance 非法 OHLC 行会被过滤。
- 全部在线源返回非法 OHLC 时，股票进入失败列表。
- 合法 yfinance 数据仍可正常保存。
- 策略3扫描会传入按评估日截断的市场指数数据。
- `relative_strength_60` 等于股票 60 日收益减指数 60 日收益。
- 策略3重新评估后，候选表和 `task_stocks.status` 仍一致。
- 战术支撑模型不会让深跌弱势股误入选。
- `000921` 这类强势回踩但结构止损过宽的股票能进入 near-miss 或正式候选。
- 正式候选数量小幅增加，不应暴增。

## 8. 不建议修改的内容

- 不要取消 `DEEP_DRAWDOWN_FROM_HIGH`。
- 不要取消 `RECENT_OVERHEATED`。
- 不要取消 `RECENT_RANGE_TOO_WIDE` 和 `CLOSE_RANGE_TOO_WIDE`，最多调整为 near-miss 分层。
- 不要把策略3结果混入策略1/策略2候选表。
- 不要让旧缓存绕过全源失败规则。

## 9. 最终交付标准

修复完成后应满足：

1. 非法 OHLC 不再进入 `daily_ohlc`。
2. 策略3相对强度口径符合设计文档。
3. 风险模型能区分结构止损和战术止损。
4. 候选数量增加来自逻辑修正，而不是盲目放宽阈值。
5. 结果页能解释正式候选和 near-miss 的差异。
6. 策略1/策略2回归测试不受影响。

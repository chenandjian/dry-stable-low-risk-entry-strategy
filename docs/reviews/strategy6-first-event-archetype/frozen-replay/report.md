# 策略6首次候选事件与分入场类型成交冻结重放报告

- 来源任务：`s6bt-772c046cb6c982f61fc5`
- 参数集：`s6ps-f03199f3e7189f9b`
- 冻结信号：1121；实际重放：1120；setup：887；股票：519
- 缺失个股日线：002759；排除信号：1
- 入场原型逐日重建失败：0
- 入场原型分布：SUPPORT_PULLBACK=721, NONE=384, WAIT_BREAKOUT=15
- 价格口径：`FORWARD_ADJUSTED_LOCAL_OHLC`；真实指数：`READY`；2026+：`LOCKED_2026_PLUS`
- 四组实验使用完全相同的冻结候选信号，只比较事件去重和成交触发，未修改生产配置。

| 实验 | 信号选择 | 成交方式 | 订单 | 成交 | 闭合 | 训练交易 | 训练期望R | 训练PF | 验证交易 | 验证期望R | 验证PF | 验证盈亏比 | 门禁 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `S6_EXEC_E0_LEGACY` | `LEGACY_SETUP_ID` | `FROZEN_TRADE_PLAN` | 615 | 257 | 252 | 53 | -0.528 | 0.276 | 199 | -0.006 | 0.724 | 2.805 | 淘汰 |
| `S6_EXEC_E1_FIRST_EVENT` | `FIRST_EVENT_PER_START` | `FROZEN_TRADE_PLAN` | 483 | 202 | 198 | 42 | -0.397 | 0.384 | 156 | 0.024 | 0.880 | 2.800 | 淘汰 |
| `S6_EXEC_E2_ARCHETYPE` | `LEGACY_SETUP_ID` | `ARCHETYPE_TRIGGERED` | 615 | 447 | 440 | 80 | -0.499 | 0.267 | 360 | -0.135 | 0.548 | 2.562 | 淘汰 |
| `S6_EXEC_E3_COMBINED` | `FIRST_EVENT_PER_START` | `ARCHETYPE_TRIGGERED` | 483 | 351 | 345 | 65 | -0.378 | 0.353 | 280 | -0.081 | 0.637 | 2.537 | 淘汰 |

## 门禁明细

- `S6_EXEC_E0_LEGACY`：TRAIN_EXPECTANCY_NOT_POSITIVE, TRAIN_PF_LT_1_20, VALIDATION_EXPECTANCY_NOT_POSITIVE, VALIDATION_PF_LT_1_20
- `S6_EXEC_E1_FIRST_EVENT`：TRAIN_EXPECTANCY_NOT_POSITIVE, TRAIN_PF_LT_1_20, VALIDATION_PF_LT_1_20
- `S6_EXEC_E2_ARCHETYPE`：TRAIN_EXPECTANCY_NOT_POSITIVE, TRAIN_PF_LT_1_20, VALIDATION_EXPECTANCY_NOT_POSITIVE, VALIDATION_PF_LT_1_20
- `S6_EXEC_E3_COMBINED`：TRAIN_EXPECTANCY_NOT_POSITIVE, TRAIN_PF_LT_1_20, VALIDATION_EXPECTANCY_NOT_POSITIVE, VALIDATION_PF_LT_1_20

## 最终结论

- 决策：`KEEP_CURRENT_RULES`
- 原因：`NO_TRIAL_PASSED_INITIAL_GATE`
- 初筛入围：无
- 正式配置已修改：`false`

## 结论边界

- 这是同一批真实历史日线和真实指数日历上的冻结信号重放，可以判断事件去重和成交模型是否值得继续。
- 它不能发现来源任务没有生成的新候选；只有初筛通过后才应执行当前代码逐日完整确认和压力测试。
- 训练期与验证期必须同时为正期望、PF>=1.20，验证闭合交易>=30，平均盈利R/平均亏损R>=2.5。
- 本样本没有 PIVOT_BREAKOUT 或 FAILED_BREAKOUT_RECLAIM，分原型结果只验证 SUPPORT_PULLBACK，不能外推到未出现原型。

## 交付文件

- `daily-candidates.csv`：逐日冻结候选及首次事件字段。
- `orders.csv`：四组实验全部订单和未成交原因。
- `trades.csv`：四组实验交易明细。
- `summary.json`：机器可读完整汇总。

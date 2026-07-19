# 策略6全面参数调优报告

## 总体结论

- 结论：`REJECT`
- Campaign：`s6opt-comprehensive-fe84532`
- 原始七阶段实验 Git：`fe84532086ee6ec0252d89614433dc53de99edc2`
- 最终审计重跑 Git：`e26b69fcfdf70430d34e9790074991166e8a7faf`
- 数据版本：`07298d5b8a3f86b05864f774ec87c49152b3ef1e90dd48df88014c5f9f59d26a`
- 最终完整回测：`s6bt-6be85f4fb5a935680beb`
- 生产配置未自动修改。
- 2026-01-01 起 OOS 保持锁定，未用于搜索、筛选或排序。

## 七阶段状态

| 顺序 | 阶段 | 状态 | 决策 | 选中参数集 |
| --- | --- | --- | --- | --- |
| 1 | liquidity_rs | FROZEN | KEEP_PREVIOUS_STAGE | s6ps-71bdb4dbb9c5c096 |
| 2 | strong_start | FROZEN | KEEP_PREVIOUS_STAGE | s6ps-71bdb4dbb9c5c096 |
| 3 | pattern | FROZEN | KEEP_PREVIOUS_STAGE | s6ps-71bdb4dbb9c5c096 |
| 4 | support_risk | FROZEN | KEEP_PREVIOUS_STAGE | s6ps-71bdb4dbb9c5c096 |
| 5 | dry_tail | FROZEN | KEEP_PREVIOUS_STAGE | s6ps-71bdb4dbb9c5c096 |
| 6 | box_compact | FROZEN | KEEP_PREVIOUS_STAGE | s6ps-71bdb4dbb9c5c096 |
| 7 | score_trade_plan | FROZEN | KEEP_PREVIOUS_STAGE | s6ps-71bdb4dbb9c5c096 |

## 修正后粗筛门槛复核

- 步长：`5` 个交易日。
- OAT试验：`164` 组。
- 通过修正后粗筛门槛：`0` 组。
- 粗筛阶段按步长折算最低交易样本；集中度门槛延后到逐日完整验证。

## 参数差异

- 无建议变更。

## 训练与验证指标

- `TRAIN`：交易 19，期望R -0.5117551052631579，PF 0.5835969708040649，最大回撤 0.08632112919885902。
- `VALIDATION`：交易 158，期望R -0.25931919620253163，PF 0.5116910758325357，最大回撤 0.25496703970832907。

## 执行参数与压力测试

- 执行参数试验：`16` 组。
- 保留默认买入有效期：`3` 个交易日。
- 保留默认最大持有期：`20` 个交易日。
- 2025验证确认：`未通过`。
- 高成本压力：`未通过`。
- 70%成交率压力：`未通过`。
- 延迟一个交易日压力：`未通过`。

| 场景 | 订单 | 未成交率 | 闭合交易 | 期望R | PF |
| --- | ---: | ---: | ---: | ---: | ---: |
| BASE | 644 | 74.84% | 158 | -0.2593 | 0.5117 |
| HIGH_COST | 644 | 74.84% | 158 | -0.3173 | 0.4730 |
| LOW_FILL | 644 | 82.30% | 111 | -0.2850 | 0.3058 |
| ONE_DAY_DELAY | 644 | 79.81% | 128 | -0.2665 | 0.4668 |

## 风险披露

- 股票池为当前股票池，存在幸存者偏差。
- 历史证券状态信息不完整。
- 七阶段、验证和压力测试均已执行，但验证与三类压力未通过，因此拒绝正式参数升级。

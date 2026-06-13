# 策略2优化后正式策略文档：极致量干价稳短线候选

## 1. 策略版本

- 策略版本号：`strategy2-v3`
- 生效日期：2026-06-13
- 启用状态：已作为策略2正式版本启用
- 定位：短线观察、低风险候选、非自动交易
- 适用市场：A股本地日线数据库与正式策略2全市场扫描
- 适用周期：日线，短线观察窗口优先参考 5 个交易日

## 2. 决策依据

可信基线任务：

- `s2bt-20260613-174358-baseline`
- `status=completed`
- `credibility_status=TRUSTED_BASELINE`
- 处理股票：5527
- 机会数：669
- 平均实际收益：`-0.004071`
- 目标达成率：`40.29%`

采用的主要实验任务：

- `s2bt-20260613-174929-vol40`
  - `minimumVolumeDryScore=40`
  - 机会数：377
  - 实际入场：347
  - 平均实际收益：`0.001903`
  - 相对基线平均收益：`+0.005974`
  - 相对基线成功率：`+0.066875`
- `s2bt-20260613-175657-vol40-exit5`
  - `minimumVolumeDryScore=40`
  - `timeExitDays=5`
  - 机会数：377
  - 实际入场：347
  - 平均实际收益：`0.006787`
  - 时间退出次数：169
  - 相对基线平均收益：`+0.010858`

参考但未作为正式硬过滤的实验任务：

- `s2bt-20260613-175258-vol50`
  - 平均实际收益：`0.003014`
  - 相对基线平均收益：`+0.007085`
  - 机会数下降到 160，收缩过强。
- `s2bt-20260613-180134-vol40-exit10`
  - 平均实际收益：`0.005287`
  - 优于基线，但弱于 5 日退出。
- `s2bt-20260613-180601-vol40-break5`
  - 启动确认失败 206 次，仅 29 个实际入场。
  - 平均实际收益：`-0.023904`
  - 不适合作为正式规则。

## 3. 正式参数表

| 参数名 | 旧值 | 新值 | 生效位置 | 调整原因 |
|---|---:|---:|---|---|
| `candidate_min_score` | 70 | 70 | 正式扫描 | 总分门槛保持不变，避免同时收紧多个维度造成不可解释变化。 |
| `minimum_volume_dry_score` | 0 | 40 | 正式扫描硬过滤 | `vol40` 实验在保留 377 个机会的同时，平均收益和成功率均优于可信基线。 |
| `short_term_time_exit_days` | 0 | 5 | 候选展示 / 策略说明 | `vol40-exit5` 表现最好，但退出属于交易执行建议，不作为扫描入选硬过滤。 |
| `max_risk_ratio` | 0.05 | 0.05 | 正式扫描 | 风险上限保持不变，避免改变风险模型。 |
| `entry_confirmation.type` | `NONE` | `NONE` | 不启用正式硬过滤 | `BREAK_RECENT_5D_HIGH` 实验入场过少且收益恶化。 |

## 4. 正式过滤规则

策略2正式候选必须同时满足：

1. 行情结构和值校验通过。
2. 策略窗口内有效数据不少于 `minimum_required_days=250`。
3. 趋势不为 `DOWNTREND`。
4. 一票否决规则为空。
5. `total_score >= candidate_min_score`，当前为 `70`。
6. `volume_dry_score >= minimum_volume_dry_score`，当前为 `40`。
7. `risk_ratio <= max_risk_ratio`，当前为 `0.05`。

新增未通过原因：

- `VOLUME_DRY_BELOW_THRESHOLD`

## 5. 评分和趋势规则

评分规则保持策略2原有 100 分制：

- 量干评分：0-50。
- 价稳评分：0-50。
- 总分：量干 + 价稳。

趋势规则保持 V2 价格路径和 120 日长期确认：

- `UPTREND_OR_SIDEWAYS` 可继续评估。
- `DOWNTREND` 直接过滤。
- `INVALID_MARKET_DATA` / `INSUFFICIENT_TREND_DATA` 不进入候选。

## 6. 风险规则

风险规则保持不变：

- 关键支撑：不含评估日的前 `support_lookback_days=10` 个交易日最低收盘价。
- 买入区间上限：`key_support * (1 + buy_zone_max_premium)`，当前溢价 `0.03`。
- 止损价：`key_support * (1 - stop_loss_buffer)`，当前缓冲 `0.03`。
- 最大风险比：`0.05`。

## 7. 未采用参数

- `minimum_volume_dry_score=50`
  - 收益更好，但机会数从 669 降到 160，收缩过强。
  - 暂不作为正式硬过滤，后续可作为“高质量子集”标签。
- `time_exit_days=10`
  - 优于基线，但弱于 5 日退出。
- `BREAK_RECENT_5D_HIGH`
  - 入场确认失败过多，平均收益为负。
  - 不升级为正式启动确认。
- `CLOSE_ABOVE_MA20` / `BREAK_HIGH_WITH_MODERATE_VOLUME`
  - 本轮没有形成足够正式启用证据。

## 8. 已知风险

- 本次正式升级基于一轮本地全市场可信基线和五个可比较实验任务。
- `minimum_volume_dry_score=40` 会减少候选数量，可能漏掉部分价稳但量干不足的机会。
- `short_term_time_exit_days=5` 是观察建议，不等于自动卖出规则。
- 后续如果市场环境显著变化，量干门槛可能需要重新实验。

## 9. 回滚方案

回滚触发条件：

1. 连续 3 次全市场正式扫描候选数量低于基线期均值的 30%，且没有明显市场停牌或数据缺失原因。
2. 新可信基线回测显示 `strategy2-v3` 平均实际收益低于 `strategy2-v2`，且成功率未改善。
3. 用户观察到正式候选过度稀疏，无法满足跟踪需求。

回滚参数：

```yaml
strategy2:
  candidate_min_score: 70
  minimum_volume_dry_score: 0
  short_term_time_exit_days: 0
```

回滚验证：

1. 运行策略2引擎和扫描相关测试。
2. 运行一次小范围策略2扫描，确认低量干候选可按旧规则恢复。
3. 若涉及回测可信度，重新运行同区间基线任务并确认版本标识。

## 10. 后续观察指标

- 正式扫描候选数。
- 候选的量干分分布。
- 候选 5 日和 10 日后续表现。
- 止损率和目标达成率。
- 按月份、机会类型、量干分段、价稳分段的表现差异。

## 11. 实施位置

- `config.yaml`
  - 新增正式参数 `minimum_volume_dry_score=40`。
  - 新增展示建议参数 `short_term_time_exit_days=5`。
- `strategy2/validation.py`
  - 解析并校验新增参数。
- `strategy2/engine.py`
  - 将 `minimum_volume_dry_score` 接入正式入选条件。
- `strategy2/version.py`
  - 策略版本提升为 `strategy2-v3`。
- `scanner/db.py`
  - 候选表兼容新增 `short_term_time_exit_days`。
- `web/src/pages/StrategyConfig.vue`
  - 展示和保存新增正式参数。
- `web/src/pages/Strategy2Results.vue`
  - 展示短线退出建议。

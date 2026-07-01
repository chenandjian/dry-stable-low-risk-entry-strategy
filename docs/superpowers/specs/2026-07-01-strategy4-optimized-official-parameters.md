# 策略4优化后正式参数文档

## 1. 结论

本次 Phase 2 已实现策略4历史快照回测和参数实验框架，但当前本地真实数据不足以支撑正式调参。

最终正式建议：

- 暂不修改策略4生产默认参数。
- 暂不把任何实验参数组升级为“正式推荐参数”。
- 保持当前 Phase 1 默认值作为观察基线。
- 后续至少积累 20 个以上真实策略4热点/龙头快照交易日，并覆盖不同市场环境后，再重新执行参数优化。

这个结论不是“没有优化空间”，而是“当前证据不足，强行调参会过拟合”。

## 2. 当前保留的正式参数

```yaml
strategy4:
  enabled: true
  hot_topic_top_n: 8
  watch_hot_topic_top_n: 15
  min_hot_topic_score: 85
  min_hot_topic_signal_count: 2
  core_leaders_per_topic: 1
  backup_leaders_per_topic: 2
  max_total_leaders_per_topic: 3
  min_leader_strength_score: 88
  core_leader_strength_score: 93
  first_wave_lookback_short: 10
  first_wave_lookback_long: 20
  min_first_wave_return_10d: 0.25
  min_first_wave_return_20d: 0.35
  min_strong_day_count_10d: 2
  pullback_min_pct: 0.08
  pullback_max_pct: 0.25
  pullback_min_days: 2
  pullback_max_days: 8
  max_risk_ratio: 0.15
  aggressive_max_risk_ratio: 0.20
  min_reward_risk_ratio: 2.0
  core_leader_min_reward_risk_ratio: 1.8
```

## 3. 本次回测证据

回测报告：

- `docs/reviews/2026-07-01-strategy4-phase2-backtest-optimization-report.md`

真实数据覆盖：

- `daily_ohlc`：约 245 万行，4998 只股票，覆盖 2024-03-25 至 2026-07-01。
- `market_index_ohlc`：3600 行，覆盖上证、深成指、创业板指、科创50，至 2026-06-30。
- `topic_index_ohlc`：0 行；当前没有行业/题材指数历史缓存，按 `UNOBSERVED_TOPIC_INDEX` 处理。
- `strategy4_hot_topics`：135 行，但全部来自 2026-07-01 当天。
- `strategy4_leaders`：116 行，但全部来自 2026-07-01 当天。
- `strategy4_candidates`：0 行。

回测区间 2026-06-01 至 2026-07-01：

| 指标 | 结果 |
|---|---:|
| 评估日 | 22 |
| 有策略4真实快照的日期 | 1 |
| 不可观察日期 | 21 |
| 基线机会数 | 0 |
| 参数实验最大机会数 | 0 |
| 可验证入场交易 | 0 |

## 4. 已实验参数组

本次实验只使用真实策略4快照，不使用当前热点倒推历史。

| 实验 | 主要变化 | 结果 |
|---|---|---|
| baseline | 当前默认参数 | 0 机会 |
| top15 | 热点正式 Top N 8→15 | 0 机会 |
| hot80_leader80 | 热点分 85→80，龙头分 88→80 | 0 机会 |
| hot75_leader75 | 热点分 85→75，龙头分 88→75 | 0 机会 |
| first_wave_20_30 | 第一波 10日涨幅 25%→20%，20日涨幅 35%→30% | 0 机会 |
| locked_attention12 | 锁仓关注度实验阈值 18→12 | 0 机会 |
| rr18_risk20 | RR 2.0→1.8，风险上限 15%→20% | 0 机会 |
| pullback_05_30 | 回踩区间 8%-25% → 5%-30% | 0 机会 |

本次最佳参数组合判定：

- 没有可证明更优的实验参数组。
- `baseline` 是当前唯一可保留的正式观察基线。
- 不建议把放宽后的实验参数写入 `config.yaml` 或默认配置。

## 5. 为什么不升级参数

当前唯一可观察日的策略4快照中：

- 热点题材多为 `WATCH_HOT`，没有形成足够的 `CONFIRMED_HOT` 样本。
- 龙头快照没有形成可交易二波候选。
- 放宽热点分、龙头分、回踩区间、RR、风险比后仍没有机会。
- 没有任何已入场交易，无法计算真实胜率、盈亏比、Profit Factor、最大连续亏损。

因此不存在可证明更优的参数组。

## 6. 后续重新优化条件

满足以下条件后，再重新生成正式参数：

1. 至少 20 个交易日有策略4热点/龙头快照。
2. 至少覆盖 3 类市场环境：
   - 指数上行阶段。
   - 指数震荡阶段。
   - 指数回撤阶段。
3. 至少产生 20 个可回测二波机会，且其中大部分能观察到 T+1 入场和后续 5-20 日走势。
4. 参数实验需要同时报告：
   - 机会数。
   - 入场数。
   - 未入场原因。
   - 目标命中数。
   - 止损数。
   - 平均收益。
   - Profit Factor。
   - 最大连续亏损。
   - 月度/行业集中度。

## 7. 回测框架约束

本次新增回测框架必须继续保持：

- 不使用未来热点快照。
- 不用当前热点倒推历史。
- 缺少历史题材快照时标记 `UNOBSERVED_TOPIC_SNAPSHOT`。
- 缺少行业/题材指数历史缓存时标记 `UNOBSERVED_TOPIC_INDEX`，不伪造板块指数走势。
- 指数数据只截断到评估日及之前。
- 执行模型使用 `NEXT_OPEN`。
- 次日一字涨停不可成交时标记 `NO_ENTRY_LIMIT_UP_UNBUYABLE`。
- 次日 T 字涨停或开盘涨停回封时标记 `NO_ENTRY_OPEN_LIMIT_UNOBSERVED`，不假设能按开盘价成交。
- 不把不可观察数据当作 0 收益。
- 不修改策略1、策略2、策略3核心规则。

## 8. 给后续 AI 的要求

后续不要为了“完成调参”直接放宽策略4参数。

如果没有新的真实快照样本，禁止：

- 把单日结果当成正式参数依据。
- 用当前行业榜重建历史热点。
- 把 `UNOBSERVED` 日期计为失败或 0 收益。
- 只看候选数量，不看可执行入场和盈亏比。

正确做法是继续积累策略4每日快照，然后重新运行：

```bash
python -m strategy4.backtester --db data/cuphandle.db --start <start-date> --end <end-date> --report docs/reviews/<new-report>.md
```

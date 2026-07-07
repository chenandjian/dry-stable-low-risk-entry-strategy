# 策略5历史收益与最大回撤验证报告

## 1. 检查范围

- 策略5历史回测收益计算。
- 策略5持有期最大回撤计算。
- 本地 `daily_ohlc` 数据可观察性。
- 正式参数与探索参数的结果区分。

## 2. 回测口径

本次新增历史性能回测能力，使用本地数据库，不请求任何外部行情源。

| 项目 | 口径 |
|---|---|
| 数据源 | `data/cuphandle.db` 的 `stock_pool` + `daily_ohlc` |
| 信号生成 | `ShortSprintSupportEngine.evaluate_at()` |
| 入场模型 | `NEXT_OPEN`，信号日次一交易日开盘价 |
| 收益窗口 | 5 / 10 / 20 个交易日 |
| 最大回撤 | 从入场日起到最大观察窗口内，最低价相对入场价的最大跌幅 |
| 同股去重 | 默认 10 个交易日冷却 |
| 未来数据泄漏 | 禁止；每个信号只使用评估日及之前 K 线 |

新增命令：

```bash
python -m strategy5.backtester --db data/cuphandle.db --historical-performance --forward-days 5 10 20 --evaluation-step 5 --cooldown-days 10
```

## 3. 正式参数验证结果

正式参数：

```text
minimum_trading_days = 500
forward_windows = 5 / 10 / 20
```

验证命令：

```bash
python -m strategy5.backtester --db data/cuphandle.db --historical-performance --forward-days 5 10 20 --evaluation-step 5 --cooldown-days 10
```

结果：

| 指标 | 数值 |
|---|---:|
| 股票池总数 | 5528 |
| 数据缺失股票数 | 523 |
| 无可观察历史+未来窗口股票数 | 5005 |
| 历史评估点 | 0 |
| 历史信号事件 | 0 |
| KEY 事件 | 0 |
| WATCH 事件 | 0 |
| 5日平均收益 | 不可计算 |
| 10日平均收益 | 不可计算 |
| 20日平均收益 | 不可计算 |
| 平均最大回撤 | 不可计算 |
| 最差最大回撤 | 不可计算 |
| 限制原因 | `INSUFFICIENT_HISTORY_PLUS_FORWARD_WINDOW` |

结论：

当前本地 DB 每只股票最多约 500 根 K 线。正式策略5要求 `minimum_trading_days=500`，若要计算 20 日未来收益，至少需要：

```text
500 根历史 K 线 + 20 个未来交易日 = 520 根以上 K 线
```

当前数据长度不足以形成任何正式历史收益样本。因此正式历史收益和最大回撤不能负责任地给出数值，系统现在会返回 `null` 和明确限制原因，而不是错误地把收益当作 0。

## 4. 非正式探索样本

为了验证历史收益和最大回撤计算链路确实可用，额外做了一次非正式探索样本：

```text
minimum_trading_days = 260
forward_windows = 5 / 10 / 20
evaluation_step = 10
cooldown_days = 10
```

注意：该结果只用于验证计算能力，不代表策略5正式参数收益。

运行命令：

```bash
python -c "from strategy5.backtester import run_strategy5_historical_performance_backtest; import json; summary=run_strategy5_historical_performance_backtest({'data': {'database_path':'data/cuphandle.db'}, 'strategy5': {'minimum_trading_days': 260}}, forward_windows=(5,10,20), evaluation_step=10, cooldown_days=10); print(json.dumps(summary, ensure_ascii=False, indent=2))"
```

结果摘要：

| 指标 | 数值 |
|---|---:|
| 股票池总数 | 5528 |
| 历史评估点 | 111994 |
| 历史信号事件 | 612 |
| KEY 事件 | 367 |
| WATCH 事件 | 245 |
| 5日平均收益 | +2.2812% |
| 5日胜率 | 55.0654% |
| 10日平均收益 | +3.0480% |
| 10日胜率 | 51.1438% |
| 20日平均收益 | +4.8195% |
| 20日胜率 | 48.8562% |
| 20日利润因子 | 1.9442 |
| 20日平均盈利 | +20.3117% |
| 20日平均亏损 | -10.0118% |
| 平均最大回撤 | -10.0574% |
| 最差最大回撤 | -55.0292% |
| 重复信号跳过 | 142 |

探索样本说明：

1. 计算链路可以正常输出历史收益、胜率、利润因子和最大回撤。
2. 收益呈现“小亏大赢”特征：20日平均盈利约为平均亏损的 2 倍。
3. 最差最大回撤达到 -55.03%，说明策略5即使有正期望，也必须继续强化风险控制和仓位管理。
4. 该探索样本使用 260 天历史门槛，不是正式参数，不能直接作为策略5最终收益结论。

## 5. 修复与验证结论

本次补齐内容：

1. 新增策略5历史收益回测入口。
2. 新增 `NEXT_OPEN` 入场后的 5/10/20 日收益计算。
3. 新增持有期最大回撤计算。
4. 新增无可观察窗口的显式限制原因。
5. 新增自动化测试覆盖：
   - 有历史+未来窗口时能计算收益和最大回撤；
   - 只有 500 根数据、没有未来窗口时不伪造收益。

正式结论：

当前本地数据无法验证 `minimum_trading_days=500` 正式参数下的历史收益和最大回撤，需要补充至少 520 根以上日线，最好 600 根以上，才能形成可用的正式样本。

## 6. 后续建议

1. 下一次拉取历史数据时，将策略5 `kline_days` 实际数据覆盖提高到至少 650 根。
2. 有足够历史后，重新运行正式参数历史性能回测。
3. 若正式样本仍出现过深回撤，应优先增加：
   - 单日大跌后禁止入选；
   - 高波动 WATCH 降权；
   - 最大持有期回撤止损模拟；
   - KEY 与 WATCH 分层收益单独统计。

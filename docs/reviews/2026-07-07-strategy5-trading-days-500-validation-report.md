# 策略5 TRADING_DAYS=500 本地验证报告

## 1. 检查范围

- 策略5 F1 交易天数过滤。
- 策略5默认配置与 `config.yaml`。
- 前端策略5配置页默认值展示。
- 本地 DB 全市场验证：`data/cuphandle.db`。

## 2. 本次变更

原策略5要求 `trading_days > 1000`，但当前本地 `daily_ohlc` 最大可用日线数正好为 500。若仅把配置值从 1000 改成 500，并继续使用 `<= minimum_trading_days` 拦截，则所有 500 根日线股票仍会被排除，无法完成真实本地验证。

因此本次将策略5 F1语义调整为：

```text
trading_days >= 500 通过
trading_days < 500 拦截
```

稳定拒绝码同步调整为：

```text
TRADING_DAYS_LT_500
```

## 3. 本地数据概况

只读统计命令：

```bash
python -c "import sqlite3, json; con=sqlite3.connect('data/cuphandle.db'); rows=con.execute('select code, count(*) c, min(date), max(date) from daily_ohlc group by code order by c desc limit 10').fetchall(); agg=con.execute('select min(c), max(c), avg(c), sum(case when c>=500 then 1 else 0 end), sum(case when c>500 then 1 else 0 end), count(*) from (select code,count(*) c from daily_ohlc group by code)').fetchone(); print(json.dumps({'top':rows,'agg':agg}, ensure_ascii=False, default=str, indent=2))"
```

结果：

| 指标 | 数值 |
|---|---:|
| 有日线股票数 | 5008 |
| 最少日线数 | 2 |
| 最多日线数 | 500 |
| 平均日线数 | 491.35 |
| 日线数 >= 500 的股票数 | 4830 |
| 日线数 > 500 的股票数 | 0 |

结论：当前本地数据正好是约 500 根 K 线，策略5若要基于本地数据验证，必须采用 `>=500` 口径。

## 4. 全市场验证结果

验证命令：

```bash
python -m strategy5.backtester --db data/cuphandle.db
```

结果摘要：

| 指标 | 数值 |
|---|---:|
| 股票池总数 | 5528 |
| 实际评估股票数 | 5005 |
| 数据不足股票数 | 523 |
| 候选总数 | 24 |
| KEY_CANDIDATE | 8 |
| WATCH_CANDIDATE | 16 |

主要拦截原因：

| 拒绝原因 | 数量 |
|---|---:|
| CLOSE_LE_MA250 | 3249 |
| AVG60D_LE_20YI | 1117 |
| NO_DAILY_OHLC | 523 |
| SHORT_TERM_STRENGTH_FAILED | 163 |
| MA120_LE_MA250 | 143 |
| TRADING_DAYS_LT_500 | 92 |
| INSUFFICIENT_KLINE_DAYS | 86 |
| AMP5D_GT_22PCT | 63 |
| NEW_HIGH_FAILED | 44 |
| MAX_DECLINE_LT_NEG8PCT | 10 |
| REJECTED | 7 |
| AVG30D_LE_15YI | 4 |
| AMP10D_GT_45PCT | 2 |
| CONSOLIDATION_VOLUME_UP_DECLINE | 1 |

## 5. 候选股票列表

| 代码 | 名称 | 类型 | 总分 | 支撑状态 | 主支撑 | 支撑距离 | 强度触发 | 新高触发 | 警告 | 风险 |
|---|---|---|---:|---|---|---:|---|---|---|---|
| 600176 | 中国巨石 | KEY_CANDIDATE | 88.56 | SPRINT_MA5_SUPPORT | MA5 | 0.004654 | ret_20d | new_120d_high | EXTREME_5D_VOLATILITY_OBSERVE, EXTREME_10D_VOLATILITY_OBSERVE |  |
| 300433 | 蓝思科技 | KEY_CANDIDATE | 85.30 | SPRINT_MA5_SUPPORT | MA5 | 0.000305 | ret_20d | new_120d_high | HIGH_5D_VOLATILITY |  |
| 300570 | 太辰光 | KEY_CANDIDATE | 82.65 | SPRINT_MA5_SUPPORT | MA5 | 0.001754 | ret_20d | new_120d_high | HIGH_5D_VOLATILITY, HIGH_10D_VOLATILITY, DEEP_PULLBACK |  |
| 600172 | 黄河旋风 | KEY_CANDIDATE | 81.92 | SPRINT_MA5_SUPPORT | MA5 | 0.000712 | ret_10d | new_120d_high | HIGH_5D_VOLATILITY, HIGH_10D_VOLATILITY |  |
| 688598 | 金博股份 | WATCH_CANDIDATE | 79.04 | SPRINT_MA20_SUPPORT | MA20 | 0.056123 | ret_20d | new_120d_high | HIGH_5D_VOLATILITY, HIGH_10D_VOLATILITY, DEEP_PULLBACK |  |
| 688686 | 奥普特 | KEY_CANDIDATE | 78.69 | SPRINT_MA5_SUPPORT | MA5 | 0.012247 | ret_20d | new_120d_high | EXTREME_5D_VOLATILITY_OBSERVE |  |
| 300398 | 飞凯材料 | WATCH_CANDIDATE | 78.60 | SPRINT_MA20_SUPPORT | MA20 | 0.045892 | ret_20d | new_120d_high | EXTREME_5D_VOLATILITY_OBSERVE, EXTREME_10D_VOLATILITY_OBSERVE, DEEP_PULLBACK | BIG_DROP_TODAY |
| 300661 | 圣邦股份 | KEY_CANDIDATE | 77.60 | SPRINT_MA5_SUPPORT | MA5 | 0.003023 | ret_20d | new_120d_high | EXTREME_5D_VOLATILITY_OBSERVE |  |
| 600110 | 诺德股份 | KEY_CANDIDATE | 76.85 | SPRINT_MA10_SUPPORT | MA10 | 0.020635 | ret_20d | new_120d_high | HIGH_5D_VOLATILITY |  |
| 000657 | 中钨高新 | WATCH_CANDIDATE | 76.71 | SPRINT_MA20_SUPPORT | MA20 | 0.001936 | ret_20d | new_120d_high | HIGH_5D_VOLATILITY, HIGH_10D_VOLATILITY, DEEP_PULLBACK | BIG_DROP_TODAY |
| 301217 | 铜冠铜箔 | WATCH_CANDIDATE | 75.99 | SPRINT_MA20_SUPPORT | MA20 | 0.028723 | ret_20d | new_120d_high | HIGH_5D_VOLATILITY, HIGH_10D_VOLATILITY, EXTREME_PULLBACK_OBSERVE |  |
| 688536 | 思瑞浦 | WATCH_CANDIDATE | 74.99 | SPRINT_MA20_SUPPORT | MA20 | 0.014724 | single_day_surge | new_120d_high | HIGH_5D_VOLATILITY |  |
| 688010 | 福光股份 | WATCH_CANDIDATE | 74.70 | SPRINT_MA20_SUPPORT | MA20 | 0.006392 | single_day_surge | new_120d_high | EXTREME_5D_VOLATILITY_OBSERVE |  |
| 688498 | 源杰科技 | WATCH_CANDIDATE | 73.87 | SPRINT_MA20_SUPPORT | MA20 | 0.014648 | ret_20d | new_120d_high | EXTREME_5D_VOLATILITY_OBSERVE |  |
| 688248 | 南网科技 | KEY_CANDIDATE | 70.32 | SPRINT_MA10_SUPPORT | MA10 | 0.019707 | ret_20d | near_120d_high |  |  |
| 688156 | 路德科技 | WATCH_CANDIDATE | 68.81 | SPRINT_MA10_SUPPORT | MA10 | 0.033300 | ret_20d | new_120d_high | EXTREME_5D_VOLATILITY_OBSERVE, HIGH_10D_VOLATILITY |  |
| 688182 | 灿勤科技 | WATCH_CANDIDATE | 68.78 | SPRINT_MA20_SUPPORT | MA20 | 0.008777 | single_day_surge | near_120d_high | HIGH_5D_VOLATILITY |  |
| 688388 | 嘉元科技 | WATCH_CANDIDATE | 68.17 | SPRINT_MA50_TESTING | MA50 | 0.078987 | ret_20d | new_120d_high | HIGH_5D_VOLATILITY, DEEP_PULLBACK |  |
| 600392 | 盛和资源 | WATCH_CANDIDATE | 67.80 | SPRINT_MA20_SUPPORT | MA20 | 0.022401 | ret_20d | new_120d_high | DEEP_PULLBACK |  |
| 300903 | 科翔股份 | WATCH_CANDIDATE | 65.63 | SPRINT_MA20_SUPPORT | MA20 | 0.053655 | ret_20d | new_120d_high | HIGH_5D_VOLATILITY, HIGH_10D_VOLATILITY |  |
| 688653 | 康希通信 | WATCH_CANDIDATE | 65.30 | SPRINT_MA20_SUPPORT | MA20 | 0.038481 | single_day_surge | new_120d_high | HIGH_5D_VOLATILITY |  |
| 002297 | 博云新材 | WATCH_CANDIDATE | 63.90 | SPRINT_MA20_SUPPORT | MA20 | 0.039521 | ret_20d | new_120d_high | HIGH_5D_VOLATILITY, HIGH_10D_VOLATILITY, DEEP_PULLBACK |  |
| 600186 | 莲花控股 | WATCH_CANDIDATE | 59.25 | SPRINT_MA50_TESTING | MA50 | 0.029425 | ret_20d | new_120d_high | EXTREME_5D_VOLATILITY_OBSERVE, HIGH_10D_VOLATILITY, EXTREME_PULLBACK_OBSERVE |  |
| 688325 | 赛微微电 | WATCH_CANDIDATE | 52.07 | SPRINT_MA50_TESTING | MA50 | 0.030001 | single_day_surge | new_120d_high | HIGH_5D_VOLATILITY, DEEP_PULLBACK |  |

## 6. 结论

1. `TRADING_DAYS=500` 后，策略5可以基于当前本地 DB 跑出真实候选。
2. 全市场 5528 只股票中得到 24 只候选，候选数量仍然偏少，说明策略5核心质量门槛仍然较严。
3. 主要拦截不再是交易日不足，而是 `CLOSE_LE_MA250` 和 `AVG60D_LE_20YI`，即长期趋势和成交额质量过滤仍是主漏斗。
4. 24 只候选里有 8 只 KEY，16 只 WATCH；KEY 候选主要集中在 MA5/MA10 支撑，WATCH 候选多为 MA20/MA50 观察。
5. 部分 WATCH 候选带 `BIG_DROP_TODAY`、`DEEP_PULLBACK` 或高波动警告，前端展示时应明确提示，不应与 KEY 候选混为同等质量。

## 7. 风险提示

1. 将交易日门槛从 1000 降到 500，会降低长期历史过滤强度；但当前本地数据最大只有 500 根，这是本阶段可验证的合理折中。
2. `>=500` 是本轮为了适配本地真实数据作出的明确语义选择；如果未来 DB 扩展到 1000 根以上，可以重新评估是否恢复更长历史过滤。
3. 本次只验证静态候选，不代表回测收益已优化；后续若用于正式交易，应补策略5历史回测收益和最大回撤验证。

# 策略4 Phase 2 回测与参数优化报告

- 回测区间：2026-03-01 至 2026-07-02
- 数据库：`data/cuphandle.db`
- daily_ohlc：2459507 行，5006 只，2024-03-26 至 2026-07-02
- market_index_ohlc：4000 行，2022-05-19 至 2026-07-02
- strategy4_topic_index_ohlc：13369 行（observable）
- strategy4_hot_topics：225 行，2026-07-01 14:42:41 至 2026-07-03 12:17:54
- strategy4_leaders：239 行

## 参数实验结果

| 实验 | 可观察日 | 不可观察日 | 不可观察率 | 池题材 | 池龙头 | 信号 | 即时机会 | 跟踪池机会 | 总机会 | 入场 | 未入场 | 目标 | 止损 | 平均收益 | PF | 平均盈利 | 平均亏损 | 平均盈亏比 | 跟踪年龄分布 | 月度分布 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| baseline | 66 | 0 | 0.0% | 4 | 33 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% | -- | -- | -- | -- | 1-20:0, 21-60:0, 61-120:0 | -- |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 81 | 0 | 0.0% | 31 | 235 | 123 | 6 | 123 | 123 | 123 | 0 | 37 | 82 | 1.10% | 1.20 | 20.00% | -8.01% | 2.50 | 1-20:15, 21-60:75, 61-120:27 | 2026-03:9, 2026-04:66, 2026-05:28, 2026-06:18, 2026-07:2 |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 81 | 0 | 0.0% | 31 | 235 | 98 | 5 | 98 | 98 | 98 | 0 | 29 | 66 | 1.22% | 1.24 | 19.99% | -7.47% | 2.68 | 1-20:10, 21-60:62, 61-120:21 | 2026-03:9, 2026-04:49, 2026-05:24, 2026-06:14, 2026-07:2 |
| early_only_risk10_pb35 | 81 | 0 | 0.0% | 31 | 235 | 25 | 4 | 25 | 25 | 25 | 0 | 8 | 17 | 1.43% | 1.25 | 22.23% | -8.36% | 2.66 | 1-20:1, 21-60:17, 61-120:3 | 2026-04:16, 2026-05:7, 2026-06:2 |
| main_only_pb35_risk12 | 81 | 0 | 0.0% | 31 | 235 | 80 | 2 | 80 | 80 | 80 | 0 | 23 | 54 | 0.84% | 1.15 | 19.31% | -8.06% | 2.40 | 1-20:11, 21-60:51, 61-120:16 | 2026-03:9, 2026-04:43, 2026-05:17, 2026-06:9, 2026-07:2 |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 81 | 0 | 0.0% | 30 | 192 | 56 | 3 | 56 | 56 | 56 | 0 | 9 | 43 | -3.23% | 0.51 | 15.65% | -8.38% | 1.87 | 1-20:15, 21-60:28, 61-120:10 | 2026-03:8, 2026-04:22, 2026-05:12, 2026-06:12, 2026-07:2 |

## 机会明细

| 实验 | 股票 | 题材 | 来源 | 发现日 | 入场日 | 退出原因 | 收益 | RR | 风险 | 回踩 | 回踩天数 | 跟踪天数 | 板块源 | 板块K线日期 | 板块阶段 |
|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---|
| confirm60_leader40_fw10_pb35_risk12_rr10 | 000822 山东海化 | 化学原料 | merged_current_and_tracking | 2026-03-11 | 2026-03-12 | STOP | -8.72% | 1.30 | 8.05% | 11.88% | 6 | 0 | akshare_ths | 2026-03-11 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 600740 山西焦化 | 煤炭开采加工 | tracking_pool | 2026-03-11 | 2026-03-12 | STOP | -7.85% | 1.99 | 6.70% | 11.26% | 6 | 8 | akshare_ths | 2026-03-11 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 000822 山东海化 | 化学原料 | tracking_pool | 2026-03-17 | 2026-03-18 | STOP | -6.54% | 1.58 | 7.23% | 11.88% | 6 | 14 | akshare_ths | 2026-03-17 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 600740 山西焦化 | 煤炭开采加工 | tracking_pool | 2026-03-23 | 2026-03-24 | STOP | -5.23% | 2.07 | 7.86% | 14.56% | 13 | 20 | akshare_ths | 2026-03-23 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 600740 山西焦化 | 煤炭开采加工 | tracking_pool | 2026-03-24 | 2026-03-25 | STOP | -5.02% | 2.15 | 7.67% | 14.56% | 13 | 21 | akshare_ths | 2026-03-24 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 600740 山西焦化 | 煤炭开采加工 | tracking_pool | 2026-03-25 | 2026-03-26 | STOP | -7.47% | 2.07 | 7.86% | 14.56% | 13 | 22 | akshare_ths | 2026-03-25 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 002128 电投能源 | 煤炭开采加工 | tracking_pool | 2026-03-25 | 2026-03-26 | STOP | -6.60% | 2.32 | 7.24% | 17.53% | 8 | 22 | akshare_ths | 2026-03-25 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 600740 山西焦化 | 煤炭开采加工 | tracking_pool | 2026-03-27 | 2026-03-30 | STOP | -9.98% | 1.83 | 8.45% | 14.56% | 13 | 24 | akshare_ths | 2026-03-27 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 002128 电投能源 | 煤炭开采加工 | tracking_pool | 2026-03-27 | 2026-03-30 | STOP | -9.81% | 2.81 | 6.37% | 17.53% | 8 | 24 | akshare_ths | 2026-03-27 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 301092 争光股份 | 塑料制品 | tracking_pool | 2026-04-01 | 2026-04-02 | TARGET | 30.82% | 4.31 | 7.17% | 24.14% | 18 | 22 | akshare_ths | 2026-04-01 | PULLBACK_REPAIR |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 301588 美新科技 | 塑料制品 | tracking_pool | 2026-04-08 | 2026-04-09 | TARGET | 31.01% | 3.97 | 7.70% | 26.76% | 18 | 29 | akshare_ths | 2026-04-08 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 300980 祥源新材 | 塑料制品 | tracking_pool | 2026-04-08 | 2026-04-09 | STOP | -6.71% | 1.41 | 7.53% | 11.67% | 8 | 29 | akshare_ths | 2026-04-08 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 301092 争光股份 | 塑料制品 | tracking_pool | 2026-04-08 | 2026-04-09 | TARGET | 29.17% | 3.37 | 8.45% | 24.14% | 18 | 29 | akshare_ths | 2026-04-08 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 001378 德冠新材 | 塑料制品 | tracking_pool | 2026-04-08 | 2026-04-09 | TARGET | 12.74% | 1.42 | 8.68% | 17.53% | 9 | 29 | akshare_ths | 2026-04-08 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 300221 银禧科技 | 塑料制品 | tracking_pool | 2026-04-08 | 2026-04-09 | TARGET | 31.82% | 3.57 | 8.55% | 28.13% | 35 | 29 | akshare_ths | 2026-04-08 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 002395 双象股份 | 塑料制品 | tracking_pool | 2026-04-08 | 2026-04-09 | TARGET | 13.44% | 1.59 | 8.01% | 18.27% | 28 | 29 | akshare_ths | 2026-04-08 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 002395 双象股份 | 塑料制品 | tracking_pool | 2026-04-09 | 2026-04-10 | TARGET | 11.43% | 1.28 | 9.00% | 18.27% | 28 | 30 | akshare_ths | 2026-04-09 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 000908 石药景峰 | 化学制药 | tracking_pool | 2026-04-09 | 2026-04-10 | STOP | -8.93% | 1.69 | 10.18% | 15.56% | 5 | 2 | akshare_ths | 2026-04-09 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 301092 争光股份 | 塑料制品 | tracking_pool | 2026-04-10 | 2026-04-13 | TARGET | 27.71% | 3.00 | 9.16% | 24.14% | 18 | 31 | akshare_ths | 2026-04-10 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 001378 德冠新材 | 塑料制品 | tracking_pool | 2026-04-10 | 2026-04-13 | TARGET | 12.74% | 1.51 | 8.37% | 17.53% | 9 | 31 | akshare_ths | 2026-04-10 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 001378 德冠新材 | 塑料制品 | tracking_pool | 2026-04-13 | 2026-04-14 | TARGET | 12.05% | 1.43 | 8.63% | 17.53% | 9 | 34 | akshare_ths | 2026-04-13 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 300221 银禧科技 | 塑料制品 | tracking_pool | 2026-04-13 | 2026-04-14 | TARGET | 29.09% | 3.68 | 8.36% | 28.13% | 35 | 34 | akshare_ths | 2026-04-13 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 605168 三人行 | 文化传媒 | merged_current_and_tracking | 2026-04-14 | 2026-04-15 | TARGET | 28.16% | 2.53 | 11.13% | 33.12% | 39 | 0 | akshare_ths | 2026-04-14 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 301588 美新科技 | 塑料制品 | tracking_pool | 2026-04-14 | 2026-04-15 | TARGET | 27.85% | 4.94 | 6.53% | 26.76% | 18 | 35 | akshare_ths | 2026-04-14 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 301092 争光股份 | 塑料制品 | tracking_pool | 2026-04-14 | 2026-04-15 | TARGET | 27.03% | 2.90 | 9.38% | 24.14% | 18 | 35 | akshare_ths | 2026-04-14 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 301588 美新科技 | 塑料制品 | tracking_pool | 2026-04-15 | 2026-04-16 | TARGET | 25.17% | 2.70 | 10.09% | 26.76% | 18 | 36 | akshare_ths | 2026-04-15 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 301092 争光股份 | 塑料制品 | tracking_pool | 2026-04-16 | 2026-04-17 | TARGET | 26.32% | 2.63 | 9.99% | 24.14% | 18 | 37 | akshare_ths | 2026-04-16 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 605168 三人行 | 文化传媒 | tracking_pool | 2026-04-16 | 2026-04-17 | TARGET | 26.97% | 2.25 | 11.96% | 33.12% | 39 | 2 | akshare_ths | 2026-04-16 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 300834 星辉环材 | 塑料制品 | merged_current_and_tracking | 2026-04-17 | 2026-04-20 | STOP | -10.67% | 1.78 | 12.45% | 18.28% | 4 | 0 | akshare_ths | 2026-04-17 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 301588 美新科技 | 塑料制品 | tracking_pool | 2026-04-17 | 2026-04-20 | TARGET | 30.28% | 3.85 | 7.87% | 26.76% | 18 | 38 | akshare_ths | 2026-04-17 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 301092 争光股份 | 塑料制品 | tracking_pool | 2026-04-17 | 2026-04-20 | TARGET | 26.13% | 2.52 | 10.28% | 24.14% | 18 | 38 | akshare_ths | 2026-04-17 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 002395 双象股份 | 塑料制品 | tracking_pool | 2026-04-17 | 2026-04-20 | TARGET | 15.97% | 2.97 | 5.16% | 18.27% | 28 | 38 | akshare_ths | 2026-04-17 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 688386 泛亚微透 | 塑料制品 | tracking_pool | 2026-04-17 | 2026-04-20 | STOP | -7.39% | 4.72 | 6.33% | 28.29% | 36 | 38 | akshare_ths | 2026-04-17 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 000908 石药景峰 | 化学制药 | tracking_pool | 2026-04-17 | 2026-04-20 | STOP | -7.38% | 2.38 | 7.38% | 15.56% | 5 | 10 | akshare_ths | 2026-04-17 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 688513 苑东生物 | 化学制药 | tracking_pool | 2026-04-17 | 2026-04-20 | STOP | -4.00% | 3.89 | 5.28% | 18.91% | 7 | 10 | akshare_ths | 2026-04-17 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 301588 美新科技 | 塑料制品 | tracking_pool | 2026-04-20 | 2026-04-21 | TARGET | 25.06% | 2.15 | 11.44% | 26.76% | 18 | 41 | akshare_ths | 2026-04-20 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 002395 双象股份 | 塑料制品 | tracking_pool | 2026-04-20 | 2026-04-21 | TARGET | 14.37% | 2.50 | 5.72% | 18.27% | 28 | 41 | akshare_ths | 2026-04-20 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 301518 长华化学 | 化学制品 | merged_current_and_tracking | 2026-04-21 | 2026-04-22 | STOP | -14.39% | 1.34 | 14.33% | 26.02% | 18 | 0 | akshare_ths | 2026-04-21 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 603790 雅运股份 | 化学制品 | merged_current_and_tracking | 2026-04-21 | 2026-04-22 | TARGET | 14.66% | 1.63 | 9.56% | 26.05% | 13 | 0 | akshare_ths | 2026-04-21 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 688017 绿的谐波 | 自动化设备 | tracking_pool | 2026-04-21 | 2026-04-22 | TARGET | 17.79% | 1.45 | 11.34% | 27.35% | 21 | 6 | akshare_ths | 2026-04-21 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 301092 争光股份 | 塑料制品 | tracking_pool | 2026-04-22 | 2026-04-23 | TARGET | 20.84% | 2.07 | 9.87% | 24.14% | 18 | 43 | akshare_ths | 2026-04-22 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 688386 泛亚微透 | 塑料制品 | tracking_pool | 2026-04-22 | 2026-04-23 | STOP | -7.33% | 4.42 | 6.55% | 28.29% | 36 | 43 | akshare_ths | 2026-04-22 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 002838 道恩股份 | 塑料制品 | tracking_pool | 2026-04-23 | 2026-04-24 | TARGET | 7.76% | 1.07 | 8.07% | 24.35% | 31 | 44 | akshare_ths | 2026-04-23 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 301149 隆华新材 | 化学制品 | tracking_pool | 2026-04-23 | 2026-04-24 | TARGET | 9.18% | 1.39 | 5.69% | 19.06% | 35 | 3 | akshare_ths | 2026-04-23 | PULLBACK_REPAIR |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 603790 雅运股份 | 化学制品 | tracking_pool | 2026-04-23 | 2026-04-24 | TARGET | 16.56% | 1.55 | 9.83% | 26.05% | 13 | 3 | akshare_ths | 2026-04-23 | PULLBACK_REPAIR |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 000822 山东海化 | 化学原料 | tracking_pool | 2026-04-24 | 2026-04-27 | STOP | -6.65% | 2.27 | 10.01% | 26.10% | 15 | 52 | akshare_ths | 2026-04-24 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 000830 鲁西化工 | 化学原料 | tracking_pool | 2026-04-24 | 2026-04-27 | STOP | -9.57% | 2.46 | 11.56% | 27.68% | 36 | 52 | akshare_ths | 2026-04-24 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 000683 博源化工 | 化学原料 | tracking_pool | 2026-04-24 | 2026-04-27 | STOP | -9.79% | 1.15 | 10.09% | 21.59% | 9 | 52 | akshare_ths | 2026-04-24 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 600955 维远股份 | 化学原料 | tracking_pool | 2026-04-24 | 2026-04-27 | STOP | -9.41% | 1.61 | 8.51% | 30.19% | 20 | 52 | akshare_ths | 2026-04-24 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 600426 华鲁恒升 | 农化制品 | tracking_pool | 2026-04-24 | 2026-04-27 | STOP | -10.92% | 1.53 | 11.27% | 17.99% | 8 | 49 | akshare_ths | 2026-04-24 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 301092 争光股份 | 塑料制品 | tracking_pool | 2026-04-24 | 2026-04-27 | TARGET | 26.02% | 4.08 | 6.01% | 24.14% | 18 | 45 | akshare_ths | 2026-04-24 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 688386 泛亚微透 | 塑料制品 | tracking_pool | 2026-04-24 | 2026-04-27 | STOP | -6.89% | 4.14 | 6.89% | 28.29% | 36 | 45 | akshare_ths | 2026-04-24 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 603790 雅运股份 | 化学制品 | tracking_pool | 2026-04-24 | 2026-04-27 | TARGET | 12.29% | 1.47 | 10.10% | 26.05% | 13 | 4 | akshare_ths | 2026-04-24 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 600740 山西焦化 | 煤炭开采加工 | tracking_pool | 2026-04-27 | 2026-04-28 | STOP | -5.29% | 5.20 | 5.74% | 21.75% | 34 | 55 | akshare_ths | 2026-04-27 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 000830 鲁西化工 | 化学原料 | tracking_pool | 2026-04-27 | 2026-04-28 | STOP | -9.51% | 3.22 | 9.68% | 27.68% | 36 | 55 | akshare_ths | 2026-04-27 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 600623 华谊集团 | 化学原料 | tracking_pool | 2026-04-27 | 2026-04-28 | STOP | -6.95% | 5.63 | 4.39% | 26.08% | 16 | 55 | akshare_ths | 2026-04-27 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 000683 博源化工 | 化学原料 | tracking_pool | 2026-04-27 | 2026-04-28 | STOP | -9.99% | 1.10 | 10.29% | 21.59% | 9 | 55 | akshare_ths | 2026-04-27 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 002250 联化科技 | 农化制品 | tracking_pool | 2026-04-27 | 2026-04-28 | STOP | -11.17% | 1.02 | 10.77% | 23.83% | 17 | 52 | akshare_ths | 2026-04-27 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 002395 双象股份 | 塑料制品 | tracking_pool | 2026-04-27 | 2026-04-28 | TARGET | 13.44% | 1.13 | 8.91% | 18.27% | 28 | 48 | akshare_ths | 2026-04-27 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 688386 泛亚微透 | 塑料制品 | tracking_pool | 2026-04-27 | 2026-04-28 | STOP | -8.41% | 2.90 | 8.88% | 28.29% | 36 | 48 | akshare_ths | 2026-04-27 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 688017 绿的谐波 | 自动化设备 | tracking_pool | 2026-04-27 | 2026-04-28 | TARGET | 17.18% | 2.01 | 8.05% | 27.35% | 21 | 12 | akshare_ths | 2026-04-27 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 000830 鲁西化工 | 化学原料 | tracking_pool | 2026-04-28 | 2026-04-29 | STOP | -9.51% | 2.44 | 11.61% | 27.68% | 36 | 56 | akshare_ths | 2026-04-28 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 000683 博源化工 | 化学原料 | tracking_pool | 2026-04-28 | 2026-04-29 | STOP | -9.99% | 1.04 | 10.59% | 21.59% | 9 | 56 | akshare_ths | 2026-04-28 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 600955 维远股份 | 化学原料 | tracking_pool | 2026-04-28 | 2026-04-29 | STOP | -7.47% | 1.10 | 9.31% | 30.19% | 20 | 56 | akshare_ths | 2026-04-28 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 688386 泛亚微透 | 塑料制品 | tracking_pool | 2026-04-28 | 2026-04-29 | STOP | -9.29% | 2.59 | 9.03% | 28.29% | 36 | 49 | akshare_ths | 2026-04-28 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 300834 星辉环材 | 塑料制品 | merged_current_and_tracking | 2026-04-29 | 2026-04-30 | TARGET | 40.03% | 6.20 | 6.32% | 23.25% | 15 | 0 | akshare_ths | 2026-04-29 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 600740 山西焦化 | 煤炭开采加工 | tracking_pool | 2026-04-29 | 2026-04-30 | STOP | -9.83% | 2.54 | 9.62% | 21.75% | 34 | 57 | akshare_ths | 2026-04-29 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 002128 电投能源 | 煤炭开采加工 | tracking_pool | 2026-04-29 | 2026-04-30 | STOP | -6.52% | 1.15 | 6.28% | 17.53% | 8 | 57 | akshare_ths | 2026-04-29 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 000822 山东海化 | 化学原料 | tracking_pool | 2026-04-29 | 2026-04-30 | STOP | -9.23% | 2.50 | 9.23% | 26.10% | 15 | 57 | akshare_ths | 2026-04-29 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 000830 鲁西化工 | 化学原料 | tracking_pool | 2026-04-29 | 2026-04-30 | STOP | -12.75% | 2.51 | 11.40% | 27.68% | 36 | 57 | akshare_ths | 2026-04-29 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 300980 祥源新材 | 塑料制品 | tracking_pool | 2026-04-29 | 2026-04-30 | STOP | -6.49% | 2.71 | 7.09% | 17.67% | 22 | 50 | akshare_ths | 2026-04-29 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 688017 绿的谐波 | 自动化设备 | tracking_pool | 2026-04-29 | 2026-04-30 | TARGET | 16.03% | 1.81 | 8.57% | 27.35% | 21 | 14 | akshare_ths | 2026-04-29 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 605033 美邦股份 | 农化制品 | tracking_pool | 2026-04-30 | 2026-05-06 | STOP | -9.60% | 5.61 | 8.82% | 33.37% | 19 | 55 | akshare_ths | 2026-04-30 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 300221 银禧科技 | 塑料制品 | tracking_pool | 2026-04-30 | 2026-05-06 | TARGET | 6.60% | 1.40 | 5.67% | 28.13% | 35 | 51 | akshare_ths | 2026-04-30 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 600125 铁龙物流 | 公路铁路运输 | tracking_pool | 2026-04-30 | 2026-05-06 | STOP | -5.22% | 3.38 | 5.07% | 14.53% | 20 | 48 | akshare_ths | 2026-04-30 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 600740 山西焦化 | 煤炭开采加工 | tracking_pool | 2026-05-06 | 2026-05-07 | STOP | -7.07% | 3.51 | 7.72% | 21.75% | 34 | 64 | akshare_ths | 2026-05-06 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 300834 星辉环材 | 塑料制品 | tracking_pool | 2026-05-06 | 2026-05-07 | TARGET | 33.91% | 4.12 | 8.66% | 23.25% | 15 | 57 | akshare_ths | 2026-05-06 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 002126 银轮股份 | 汽车零部件 | tracking_pool | 2026-05-06 | 2026-05-07 | TARGET | 15.15% | 1.37 | 11.26% | 26.30% | 21 | 19 | akshare_ths | 2026-05-06 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 300980 祥源新材 | 塑料制品 | tracking_pool | 2026-05-07 | 2026-05-08 | STOP | -8.82% | 1.72 | 9.45% | 17.67% | 22 | 58 | akshare_ths | 2026-05-07 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 603565 中谷物流 | 港口航运 | tracking_pool | 2026-05-07 | 2026-05-08 | STOP | -8.68% | 1.24 | 8.60% | 14.65% | 4 | 29 | akshare_ths | 2026-05-07 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 000719 中原传媒 | 文化传媒 | tracking_pool | 2026-05-07 | 2026-05-08 | STOP | -5.44% | 1.18 | 5.44% | 8.74% | 7 | 23 | akshare_ths | 2026-05-07 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 301518 长华化学 | 化学制品 | tracking_pool | 2026-05-07 | 2026-05-08 | STOP | -8.05% | 4.65 | 8.05% | 28.69% | 34 | 17 | akshare_ths | 2026-05-07 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 601107 四川成渝 | 公路铁路运输 | tracking_pool | 2026-05-08 | 2026-05-11 | STOP | -5.51% | 1.44 | 5.67% | 17.83% | 35 | 56 | akshare_ths | 2026-05-08 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 601083 锦江航运 | 港口航运 | tracking_pool | 2026-05-08 | 2026-05-11 | STOP | -6.38% | 1.64 | 6.70% | 24.18% | 24 | 30 | akshare_ths | 2026-05-08 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 600395 盘江股份 | 煤炭开采加工 | tracking_pool | 2026-05-11 | 2026-05-12 | STOP | -4.70% | 3.55 | 5.05% | 16.43% | 8 | 69 | akshare_ths | 2026-05-11 | PULLBACK_REPAIR |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 600955 维远股份 | 化学原料 | tracking_pool | 2026-05-11 | 2026-05-12 | STOP | -4.97% | 2.44 | 5.48% | 30.19% | 20 | 69 | akshare_ths | 2026-05-11 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 601107 四川成渝 | 公路铁路运输 | tracking_pool | 2026-05-11 | 2026-05-12 | STOP | -6.63% | 1.18 | 6.31% | 17.83% | 35 | 59 | akshare_ths | 2026-05-11 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 688336 三生国健 | 生物制品 | tracking_pool | 2026-05-11 | 2026-05-12 | STOP | -6.24% | 4.78 | 6.52% | 23.86% | 22 | 40 | akshare_ths | 2026-05-11 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 688513 苑东生物 | 化学制药 | tracking_pool | 2026-05-11 | 2026-05-12 | STOP | -4.78% | 3.90 | 6.30% | 22.42% | 22 | 34 | akshare_ths | 2026-05-11 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 001367 海森药业 | 化学制药 | tracking_pool | 2026-05-11 | 2026-05-12 | STOP | -6.39% | 2.28 | 6.70% | 15.62% | 11 | 34 | akshare_ths | 2026-05-11 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 000908 石药景峰 | 化学制药 | tracking_pool | 2026-05-12 | 2026-05-13 | STOP | -9.79% | 1.63 | 8.94% | 15.56% | 5 | 35 | akshare_ths | 2026-05-12 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 001367 海森药业 | 化学制药 | tracking_pool | 2026-05-12 | 2026-05-13 | STOP | -8.07% | 1.84 | 7.66% | 15.62% | 11 | 35 | akshare_ths | 2026-05-12 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 600395 盘江股份 | 煤炭开采加工 | tracking_pool | 2026-05-13 | 2026-05-14 | STOP | -5.74% | 2.98 | 5.74% | 16.43% | 8 | 71 | akshare_ths | 2026-05-13 | PULLBACK_REPAIR |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 002128 电投能源 | 煤炭开采加工 | tracking_pool | 2026-05-13 | 2026-05-14 | STOP | -5.10% | 2.29 | 4.91% | 17.53% | 8 | 71 | akshare_ths | 2026-05-13 | PULLBACK_REPAIR |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 300980 祥源新材 | 塑料制品 | tracking_pool | 2026-05-13 | 2026-05-14 | STOP | -8.45% | 2.31 | 7.88% | 17.67% | 22 | 64 | akshare_ths | 2026-05-13 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 000534 万泽股份 | 生物制品 | tracking_pool | 2026-05-13 | 2026-05-14 | STOP | -10.45% | 1.89 | 11.06% | 26.48% | 15 | 42 | akshare_ths | 2026-05-13 | PULLBACK_REPAIR |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 600428 中远海特 | 港口航运 | tracking_pool | 2026-05-14 | 2026-05-15 | STOP | -4.35% | 4.93 | 4.24% | 15.21% | 24 | 36 | akshare_ths | 2026-05-14 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 688386 泛亚微透 | 塑料制品 | tracking_pool | 2026-05-18 | 2026-05-19 | STOP | -7.88% | 2.58 | 8.62% | 28.29% | 36 | 69 | akshare_ths | 2026-05-18 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 301237 和顺科技 | 塑料制品 | tracking_pool | 2026-05-19 | 2026-05-20 | STOP | -9.64% | 1.21 | 9.63% | 8.20% | 4 | 70 | akshare_ths | 2026-05-19 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 001268 联合精密 | 白色家电 | tracking_pool | 2026-05-22 | 2026-05-25 | STOP | -8.88% | 1.13 | 8.88% | 7.17% | 2 | 32 | akshare_ths | 2026-05-22 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 603580 艾艾精工 | 塑料制品 | tracking_pool | 2026-05-28 | 2026-05-29 | STOP | -13.18% | 1.10 | 11.17% | 16.22% | 10 | 79 | akshare_ths | 2026-05-28 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 600395 盘江股份 | 煤炭开采加工 | tracking_pool | 2026-05-29 | 2026-06-01 | STOP | -11.54% | 1.36 | 10.91% | 19.43% | 38 | 87 | akshare_ths | 2026-05-29 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 600348 华阳股份 | 煤炭开采加工 | tracking_pool | 2026-05-29 | 2026-06-01 | STOP | -7.84% | 2.04 | 6.85% | 16.54% | 12 | 87 | akshare_ths | 2026-05-29 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 600125 铁龙物流 | 公路铁路运输 | tracking_pool | 2026-06-01 | 2026-06-02 | STOP | -6.76% | 3.55 | 6.59% | 20.20% | 39 | 80 | akshare_ths | 2026-06-01 | PULLBACK_REPAIR |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 002979 雷赛智能 | 自动化设备 | tracking_pool | 2026-06-09 | 2026-06-10 | STOP | -8.14% | 2.35 | 9.38% | 23.59% | 11 | 55 | akshare_ths | 2026-06-09 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 600508 上海能源 | 煤炭开采加工 | tracking_pool | 2026-06-12 | 2026-06-15 | STOP | -6.29% | 2.40 | 7.30% | 16.68% | 7 | 101 | akshare_ths | 2026-06-12 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 600784 鲁银投资 | 化学原料 | tracking_pool | 2026-06-15 | 2026-06-16 | STOP | -5.59% | 3.61 | 6.39% | 21.49% | 12 | 104 | akshare_ths | 2026-06-15 | PULLBACK_REPAIR |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 300834 星辉环材 | 塑料制品 | tracking_pool | 2026-06-15 | 2026-06-16 | STOP | -9.53% | 1.21 | 10.38% | 13.46% | 9 | 97 | akshare_ths | 2026-06-15 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 688571 杭华股份 | 化学制品 | tracking_pool | 2026-06-15 | 2026-06-16 | STOP | -8.71% | 1.80 | 9.78% | 20.46% | 17 | 56 | akshare_ths | 2026-06-15 | PULLBACK_REPAIR |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 001218 丽臣实业 | 化学制品 | tracking_pool | 2026-06-15 | 2026-06-16 | STOP | -8.17% | 1.61 | 8.92% | 18.84% | 16 | 56 | akshare_ths | 2026-06-15 | PULLBACK_REPAIR |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 300834 星辉环材 | 塑料制品 | tracking_pool | 2026-06-16 | 2026-06-17 | STOP | -9.31% | 1.35 | 9.81% | 13.46% | 9 | 98 | akshare_ths | 2026-06-16 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 601083 锦江航运 | 港口航运 | tracking_pool | 2026-06-17 | 2026-06-18 | STOP | -8.75% | 2.12 | 9.00% | 24.18% | 24 | 70 | akshare_ths | 2026-06-17 | PULLBACK_REPAIR |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 603790 雅运股份 | 化学制品 | tracking_pool | 2026-06-17 | 2026-06-18 | STOP | -9.61% | 3.12 | 9.61% | 26.72% | 10 | 58 | akshare_ths | 2026-06-17 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 603790 雅运股份 | 化学制品 | tracking_pool | 2026-06-22 | 2026-06-23 | STOP | -7.20% | 3.46 | 8.26% | 26.72% | 10 | 63 | akshare_ths | 2026-06-22 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 600784 鲁银投资 | 化学原料 | tracking_pool | 2026-06-23 | 2026-06-24 | STOP | -10.96% | 2.35 | 10.96% | 26.90% | 18 | 112 | akshare_ths | 2026-06-23 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 001378 德冠新材 | 塑料制品 | tracking_pool | 2026-06-23 | 2026-06-24 | STOP | -8.40% | 1.13 | 9.04% | 14.09% | 17 | 105 | akshare_ths | 2026-06-23 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 001367 海森药业 | 化学制药 | tracking_pool | 2026-06-23 | 2026-06-24 | STOP | -9.65% | 3.71 | 10.00% | 31.82% | 34 | 77 | akshare_ths | 2026-06-23 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 601083 锦江航运 | 港口航运 | tracking_pool | 2026-06-23 | 2026-06-24 | STOP | -9.50% | 2.16 | 8.92% | 24.18% | 24 | 76 | akshare_ths | 2026-06-23 | PULLBACK_REPAIR |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 001872 招商港口 | 港口航运 | tracking_pool | 2026-06-23 | 2026-06-24 | UNRESOLVED | -1.49% | 2.81 | 6.85% | 18.47% | 26 | 76 | akshare_ths | 2026-06-23 | PULLBACK_REPAIR |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 001218 丽臣实业 | 化学制品 | tracking_pool | 2026-06-23 | 2026-06-24 | STOP | -7.70% | 1.69 | 8.93% | 18.84% | 16 | 64 | akshare_ths | 2026-06-23 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 300006 莱美药业 | 化学制药 | tracking_pool | 2026-06-29 | 2026-06-30 | UNRESOLVED | 3.54% | 4.13 | 10.91% | 34.65% | 29 | 83 | akshare_ths | 2026-06-29 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 301149 隆华新材 | 化学制品 | tracking_pool | 2026-07-01 | 2026-07-02 | UNRESOLVED | 8.34% | 3.74 | 9.98% | 31.38% | 31 | 72 | akshare_ths | 2026-07-01 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk12_rr10 | 001218 丽臣实业 | 化学制品 | tracking_pool | 2026-07-01 | 2026-07-02 | UNRESOLVED | 5.35% | 2.96 | 8.54% | 23.01% | 39 | 72 | akshare_ths | 2026-07-01 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 000822 山东海化 | 化学原料 | merged_current_and_tracking | 2026-03-11 | 2026-03-12 | STOP | -8.72% | 1.30 | 8.05% | 11.88% | 6 | 0 | akshare_ths | 2026-03-11 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 600740 山西焦化 | 煤炭开采加工 | tracking_pool | 2026-03-11 | 2026-03-12 | STOP | -7.85% | 1.99 | 6.70% | 11.26% | 6 | 8 | akshare_ths | 2026-03-11 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 000822 山东海化 | 化学原料 | tracking_pool | 2026-03-17 | 2026-03-18 | STOP | -6.54% | 1.58 | 7.23% | 11.88% | 6 | 14 | akshare_ths | 2026-03-17 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 600740 山西焦化 | 煤炭开采加工 | tracking_pool | 2026-03-23 | 2026-03-24 | STOP | -5.23% | 2.07 | 7.86% | 14.56% | 13 | 20 | akshare_ths | 2026-03-23 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 600740 山西焦化 | 煤炭开采加工 | tracking_pool | 2026-03-24 | 2026-03-25 | STOP | -5.02% | 2.15 | 7.67% | 14.56% | 13 | 21 | akshare_ths | 2026-03-24 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 600740 山西焦化 | 煤炭开采加工 | tracking_pool | 2026-03-25 | 2026-03-26 | STOP | -7.47% | 2.07 | 7.86% | 14.56% | 13 | 22 | akshare_ths | 2026-03-25 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 002128 电投能源 | 煤炭开采加工 | tracking_pool | 2026-03-25 | 2026-03-26 | STOP | -6.60% | 2.32 | 7.24% | 17.53% | 8 | 22 | akshare_ths | 2026-03-25 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 600740 山西焦化 | 煤炭开采加工 | tracking_pool | 2026-03-27 | 2026-03-30 | STOP | -9.98% | 1.83 | 8.45% | 14.56% | 13 | 24 | akshare_ths | 2026-03-27 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 002128 电投能源 | 煤炭开采加工 | tracking_pool | 2026-03-27 | 2026-03-30 | STOP | -9.81% | 2.81 | 6.37% | 17.53% | 8 | 24 | akshare_ths | 2026-03-27 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 301092 争光股份 | 塑料制品 | tracking_pool | 2026-04-01 | 2026-04-02 | TARGET | 30.82% | 4.31 | 7.17% | 24.14% | 18 | 22 | akshare_ths | 2026-04-01 | PULLBACK_REPAIR |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 301588 美新科技 | 塑料制品 | tracking_pool | 2026-04-08 | 2026-04-09 | TARGET | 31.01% | 3.97 | 7.70% | 26.76% | 18 | 29 | akshare_ths | 2026-04-08 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 300980 祥源新材 | 塑料制品 | tracking_pool | 2026-04-08 | 2026-04-09 | STOP | -6.71% | 1.41 | 7.53% | 11.67% | 8 | 29 | akshare_ths | 2026-04-08 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 301092 争光股份 | 塑料制品 | tracking_pool | 2026-04-08 | 2026-04-09 | TARGET | 29.17% | 3.37 | 8.45% | 24.14% | 18 | 29 | akshare_ths | 2026-04-08 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 001378 德冠新材 | 塑料制品 | tracking_pool | 2026-04-08 | 2026-04-09 | TARGET | 12.74% | 1.42 | 8.68% | 17.53% | 9 | 29 | akshare_ths | 2026-04-08 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 300221 银禧科技 | 塑料制品 | tracking_pool | 2026-04-08 | 2026-04-09 | TARGET | 31.82% | 3.57 | 8.55% | 28.13% | 35 | 29 | akshare_ths | 2026-04-08 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 002395 双象股份 | 塑料制品 | tracking_pool | 2026-04-08 | 2026-04-09 | TARGET | 13.44% | 1.59 | 8.01% | 18.27% | 28 | 29 | akshare_ths | 2026-04-08 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 002395 双象股份 | 塑料制品 | tracking_pool | 2026-04-09 | 2026-04-10 | TARGET | 11.43% | 1.28 | 9.00% | 18.27% | 28 | 30 | akshare_ths | 2026-04-09 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 301092 争光股份 | 塑料制品 | tracking_pool | 2026-04-10 | 2026-04-13 | TARGET | 27.71% | 3.00 | 9.16% | 24.14% | 18 | 31 | akshare_ths | 2026-04-10 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 001378 德冠新材 | 塑料制品 | tracking_pool | 2026-04-10 | 2026-04-13 | TARGET | 12.74% | 1.51 | 8.37% | 17.53% | 9 | 31 | akshare_ths | 2026-04-10 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 001378 德冠新材 | 塑料制品 | tracking_pool | 2026-04-13 | 2026-04-14 | TARGET | 12.05% | 1.43 | 8.63% | 17.53% | 9 | 34 | akshare_ths | 2026-04-13 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 300221 银禧科技 | 塑料制品 | tracking_pool | 2026-04-13 | 2026-04-14 | TARGET | 29.09% | 3.68 | 8.36% | 28.13% | 35 | 34 | akshare_ths | 2026-04-13 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 301588 美新科技 | 塑料制品 | tracking_pool | 2026-04-14 | 2026-04-15 | TARGET | 27.85% | 4.94 | 6.53% | 26.76% | 18 | 35 | akshare_ths | 2026-04-14 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 301092 争光股份 | 塑料制品 | tracking_pool | 2026-04-14 | 2026-04-15 | TARGET | 27.03% | 2.90 | 9.38% | 24.14% | 18 | 35 | akshare_ths | 2026-04-14 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 301092 争光股份 | 塑料制品 | tracking_pool | 2026-04-16 | 2026-04-17 | TARGET | 26.32% | 2.63 | 9.99% | 24.14% | 18 | 37 | akshare_ths | 2026-04-16 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 300834 星辉环材 | 塑料制品 | merged_current_and_tracking | 2026-04-17 | 2026-04-20 | STOP | -10.67% | 1.78 | 12.45% | 18.28% | 4 | 0 | akshare_ths | 2026-04-17 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 301588 美新科技 | 塑料制品 | tracking_pool | 2026-04-17 | 2026-04-20 | TARGET | 30.28% | 3.85 | 7.87% | 26.76% | 18 | 38 | akshare_ths | 2026-04-17 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 002395 双象股份 | 塑料制品 | tracking_pool | 2026-04-17 | 2026-04-20 | TARGET | 15.97% | 2.97 | 5.16% | 18.27% | 28 | 38 | akshare_ths | 2026-04-17 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 688386 泛亚微透 | 塑料制品 | tracking_pool | 2026-04-17 | 2026-04-20 | STOP | -7.39% | 4.72 | 6.33% | 28.29% | 36 | 38 | akshare_ths | 2026-04-17 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 000908 石药景峰 | 化学制药 | tracking_pool | 2026-04-17 | 2026-04-20 | STOP | -7.38% | 2.38 | 7.38% | 15.56% | 5 | 10 | akshare_ths | 2026-04-17 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 688513 苑东生物 | 化学制药 | tracking_pool | 2026-04-17 | 2026-04-20 | STOP | -4.00% | 3.89 | 5.28% | 18.91% | 7 | 10 | akshare_ths | 2026-04-17 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 002395 双象股份 | 塑料制品 | tracking_pool | 2026-04-20 | 2026-04-21 | TARGET | 14.37% | 2.50 | 5.72% | 18.27% | 28 | 41 | akshare_ths | 2026-04-20 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 301518 长华化学 | 化学制品 | merged_current_and_tracking | 2026-04-21 | 2026-04-22 | STOP | -14.39% | 1.34 | 14.33% | 26.02% | 18 | 0 | akshare_ths | 2026-04-21 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 603790 雅运股份 | 化学制品 | merged_current_and_tracking | 2026-04-21 | 2026-04-22 | TARGET | 14.66% | 1.63 | 9.56% | 26.05% | 13 | 0 | akshare_ths | 2026-04-21 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 301092 争光股份 | 塑料制品 | tracking_pool | 2026-04-22 | 2026-04-23 | TARGET | 20.84% | 2.07 | 9.87% | 24.14% | 18 | 43 | akshare_ths | 2026-04-22 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 688386 泛亚微透 | 塑料制品 | tracking_pool | 2026-04-22 | 2026-04-23 | STOP | -7.33% | 4.42 | 6.55% | 28.29% | 36 | 43 | akshare_ths | 2026-04-22 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 002838 道恩股份 | 塑料制品 | tracking_pool | 2026-04-23 | 2026-04-24 | TARGET | 7.76% | 1.07 | 8.07% | 24.35% | 31 | 44 | akshare_ths | 2026-04-23 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 301149 隆华新材 | 化学制品 | tracking_pool | 2026-04-23 | 2026-04-24 | TARGET | 9.18% | 1.39 | 5.69% | 19.06% | 35 | 3 | akshare_ths | 2026-04-23 | PULLBACK_REPAIR |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 603790 雅运股份 | 化学制品 | tracking_pool | 2026-04-23 | 2026-04-24 | TARGET | 16.56% | 1.55 | 9.83% | 26.05% | 13 | 3 | akshare_ths | 2026-04-23 | PULLBACK_REPAIR |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 600955 维远股份 | 化学原料 | tracking_pool | 2026-04-24 | 2026-04-27 | STOP | -9.41% | 1.61 | 8.51% | 30.19% | 20 | 52 | akshare_ths | 2026-04-24 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 301092 争光股份 | 塑料制品 | tracking_pool | 2026-04-24 | 2026-04-27 | TARGET | 26.02% | 4.08 | 6.01% | 24.14% | 18 | 45 | akshare_ths | 2026-04-24 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 688386 泛亚微透 | 塑料制品 | tracking_pool | 2026-04-24 | 2026-04-27 | STOP | -6.89% | 4.14 | 6.89% | 28.29% | 36 | 45 | akshare_ths | 2026-04-24 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 600740 山西焦化 | 煤炭开采加工 | tracking_pool | 2026-04-27 | 2026-04-28 | STOP | -5.29% | 5.20 | 5.74% | 21.75% | 34 | 55 | akshare_ths | 2026-04-27 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 000830 鲁西化工 | 化学原料 | tracking_pool | 2026-04-27 | 2026-04-28 | STOP | -9.51% | 3.22 | 9.68% | 27.68% | 36 | 55 | akshare_ths | 2026-04-27 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 600623 华谊集团 | 化学原料 | tracking_pool | 2026-04-27 | 2026-04-28 | STOP | -6.95% | 5.63 | 4.39% | 26.08% | 16 | 55 | akshare_ths | 2026-04-27 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 002395 双象股份 | 塑料制品 | tracking_pool | 2026-04-27 | 2026-04-28 | TARGET | 13.44% | 1.13 | 8.91% | 18.27% | 28 | 48 | akshare_ths | 2026-04-27 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 688386 泛亚微透 | 塑料制品 | tracking_pool | 2026-04-27 | 2026-04-28 | STOP | -8.41% | 2.90 | 8.88% | 28.29% | 36 | 48 | akshare_ths | 2026-04-27 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 688017 绿的谐波 | 自动化设备 | tracking_pool | 2026-04-27 | 2026-04-28 | TARGET | 17.18% | 2.01 | 8.05% | 27.35% | 21 | 12 | akshare_ths | 2026-04-27 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 600955 维远股份 | 化学原料 | tracking_pool | 2026-04-28 | 2026-04-29 | STOP | -7.47% | 1.10 | 9.31% | 30.19% | 20 | 56 | akshare_ths | 2026-04-28 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 688386 泛亚微透 | 塑料制品 | tracking_pool | 2026-04-28 | 2026-04-29 | STOP | -9.29% | 2.59 | 9.03% | 28.29% | 36 | 49 | akshare_ths | 2026-04-28 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 300834 星辉环材 | 塑料制品 | merged_current_and_tracking | 2026-04-29 | 2026-04-30 | TARGET | 40.03% | 6.20 | 6.32% | 23.25% | 15 | 0 | akshare_ths | 2026-04-29 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 600740 山西焦化 | 煤炭开采加工 | tracking_pool | 2026-04-29 | 2026-04-30 | STOP | -9.83% | 2.54 | 9.62% | 21.75% | 34 | 57 | akshare_ths | 2026-04-29 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 002128 电投能源 | 煤炭开采加工 | tracking_pool | 2026-04-29 | 2026-04-30 | STOP | -6.52% | 1.15 | 6.28% | 17.53% | 8 | 57 | akshare_ths | 2026-04-29 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 000822 山东海化 | 化学原料 | tracking_pool | 2026-04-29 | 2026-04-30 | STOP | -9.23% | 2.50 | 9.23% | 26.10% | 15 | 57 | akshare_ths | 2026-04-29 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 300980 祥源新材 | 塑料制品 | tracking_pool | 2026-04-29 | 2026-04-30 | STOP | -6.49% | 2.71 | 7.09% | 17.67% | 22 | 50 | akshare_ths | 2026-04-29 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 688017 绿的谐波 | 自动化设备 | tracking_pool | 2026-04-29 | 2026-04-30 | TARGET | 16.03% | 1.81 | 8.57% | 27.35% | 21 | 14 | akshare_ths | 2026-04-29 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 605033 美邦股份 | 农化制品 | tracking_pool | 2026-04-30 | 2026-05-06 | STOP | -9.60% | 5.61 | 8.82% | 33.37% | 19 | 55 | akshare_ths | 2026-04-30 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 300221 银禧科技 | 塑料制品 | tracking_pool | 2026-04-30 | 2026-05-06 | TARGET | 6.60% | 1.40 | 5.67% | 28.13% | 35 | 51 | akshare_ths | 2026-04-30 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 600125 铁龙物流 | 公路铁路运输 | tracking_pool | 2026-04-30 | 2026-05-06 | STOP | -5.22% | 3.38 | 5.07% | 14.53% | 20 | 48 | akshare_ths | 2026-04-30 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 600740 山西焦化 | 煤炭开采加工 | tracking_pool | 2026-05-06 | 2026-05-07 | STOP | -7.07% | 3.51 | 7.72% | 21.75% | 34 | 64 | akshare_ths | 2026-05-06 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 300834 星辉环材 | 塑料制品 | tracking_pool | 2026-05-06 | 2026-05-07 | TARGET | 33.91% | 4.12 | 8.66% | 23.25% | 15 | 57 | akshare_ths | 2026-05-06 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 300980 祥源新材 | 塑料制品 | tracking_pool | 2026-05-07 | 2026-05-08 | STOP | -8.82% | 1.72 | 9.45% | 17.67% | 22 | 58 | akshare_ths | 2026-05-07 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 603565 中谷物流 | 港口航运 | tracking_pool | 2026-05-07 | 2026-05-08 | STOP | -8.68% | 1.24 | 8.60% | 14.65% | 4 | 29 | akshare_ths | 2026-05-07 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 000719 中原传媒 | 文化传媒 | tracking_pool | 2026-05-07 | 2026-05-08 | STOP | -5.44% | 1.18 | 5.44% | 8.74% | 7 | 23 | akshare_ths | 2026-05-07 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 301518 长华化学 | 化学制品 | tracking_pool | 2026-05-07 | 2026-05-08 | STOP | -8.05% | 4.65 | 8.05% | 28.69% | 34 | 17 | akshare_ths | 2026-05-07 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 601107 四川成渝 | 公路铁路运输 | tracking_pool | 2026-05-08 | 2026-05-11 | STOP | -5.51% | 1.44 | 5.67% | 17.83% | 35 | 56 | akshare_ths | 2026-05-08 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 601083 锦江航运 | 港口航运 | tracking_pool | 2026-05-08 | 2026-05-11 | STOP | -6.38% | 1.64 | 6.70% | 24.18% | 24 | 30 | akshare_ths | 2026-05-08 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 600395 盘江股份 | 煤炭开采加工 | tracking_pool | 2026-05-11 | 2026-05-12 | STOP | -4.70% | 3.55 | 5.05% | 16.43% | 8 | 69 | akshare_ths | 2026-05-11 | PULLBACK_REPAIR |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 600955 维远股份 | 化学原料 | tracking_pool | 2026-05-11 | 2026-05-12 | STOP | -4.97% | 2.44 | 5.48% | 30.19% | 20 | 69 | akshare_ths | 2026-05-11 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 601107 四川成渝 | 公路铁路运输 | tracking_pool | 2026-05-11 | 2026-05-12 | STOP | -6.63% | 1.18 | 6.31% | 17.83% | 35 | 59 | akshare_ths | 2026-05-11 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 688336 三生国健 | 生物制品 | tracking_pool | 2026-05-11 | 2026-05-12 | STOP | -6.24% | 4.78 | 6.52% | 23.86% | 22 | 40 | akshare_ths | 2026-05-11 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 688513 苑东生物 | 化学制药 | tracking_pool | 2026-05-11 | 2026-05-12 | STOP | -4.78% | 3.90 | 6.30% | 22.42% | 22 | 34 | akshare_ths | 2026-05-11 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 001367 海森药业 | 化学制药 | tracking_pool | 2026-05-11 | 2026-05-12 | STOP | -6.39% | 2.28 | 6.70% | 15.62% | 11 | 34 | akshare_ths | 2026-05-11 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 000908 石药景峰 | 化学制药 | tracking_pool | 2026-05-12 | 2026-05-13 | STOP | -9.79% | 1.63 | 8.94% | 15.56% | 5 | 35 | akshare_ths | 2026-05-12 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 001367 海森药业 | 化学制药 | tracking_pool | 2026-05-12 | 2026-05-13 | STOP | -8.07% | 1.84 | 7.66% | 15.62% | 11 | 35 | akshare_ths | 2026-05-12 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 600395 盘江股份 | 煤炭开采加工 | tracking_pool | 2026-05-13 | 2026-05-14 | STOP | -5.74% | 2.98 | 5.74% | 16.43% | 8 | 71 | akshare_ths | 2026-05-13 | PULLBACK_REPAIR |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 002128 电投能源 | 煤炭开采加工 | tracking_pool | 2026-05-13 | 2026-05-14 | STOP | -5.10% | 2.29 | 4.91% | 17.53% | 8 | 71 | akshare_ths | 2026-05-13 | PULLBACK_REPAIR |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 300980 祥源新材 | 塑料制品 | tracking_pool | 2026-05-13 | 2026-05-14 | STOP | -8.45% | 2.31 | 7.88% | 17.67% | 22 | 64 | akshare_ths | 2026-05-13 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 600428 中远海特 | 港口航运 | tracking_pool | 2026-05-14 | 2026-05-15 | STOP | -4.35% | 4.93 | 4.24% | 15.21% | 24 | 36 | akshare_ths | 2026-05-14 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 688386 泛亚微透 | 塑料制品 | tracking_pool | 2026-05-18 | 2026-05-19 | STOP | -7.88% | 2.58 | 8.62% | 28.29% | 36 | 69 | akshare_ths | 2026-05-18 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 301237 和顺科技 | 塑料制品 | tracking_pool | 2026-05-19 | 2026-05-20 | STOP | -9.64% | 1.21 | 9.63% | 8.20% | 4 | 70 | akshare_ths | 2026-05-19 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 001268 联合精密 | 白色家电 | tracking_pool | 2026-05-22 | 2026-05-25 | STOP | -8.88% | 1.13 | 8.88% | 7.17% | 2 | 32 | akshare_ths | 2026-05-22 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 600348 华阳股份 | 煤炭开采加工 | tracking_pool | 2026-05-29 | 2026-06-01 | STOP | -7.84% | 2.04 | 6.85% | 16.54% | 12 | 87 | akshare_ths | 2026-05-29 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 600125 铁龙物流 | 公路铁路运输 | tracking_pool | 2026-06-01 | 2026-06-02 | STOP | -6.76% | 3.55 | 6.59% | 20.20% | 39 | 80 | akshare_ths | 2026-06-01 | PULLBACK_REPAIR |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 002979 雷赛智能 | 自动化设备 | tracking_pool | 2026-06-09 | 2026-06-10 | STOP | -8.14% | 2.35 | 9.38% | 23.59% | 11 | 55 | akshare_ths | 2026-06-09 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 600508 上海能源 | 煤炭开采加工 | tracking_pool | 2026-06-12 | 2026-06-15 | STOP | -6.29% | 2.40 | 7.30% | 16.68% | 7 | 101 | akshare_ths | 2026-06-12 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 600784 鲁银投资 | 化学原料 | tracking_pool | 2026-06-15 | 2026-06-16 | STOP | -5.59% | 3.61 | 6.39% | 21.49% | 12 | 104 | akshare_ths | 2026-06-15 | PULLBACK_REPAIR |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 688571 杭华股份 | 化学制品 | tracking_pool | 2026-06-15 | 2026-06-16 | STOP | -8.71% | 1.80 | 9.78% | 20.46% | 17 | 56 | akshare_ths | 2026-06-15 | PULLBACK_REPAIR |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 001218 丽臣实业 | 化学制品 | tracking_pool | 2026-06-15 | 2026-06-16 | STOP | -8.17% | 1.61 | 8.92% | 18.84% | 16 | 56 | akshare_ths | 2026-06-15 | PULLBACK_REPAIR |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 300834 星辉环材 | 塑料制品 | tracking_pool | 2026-06-16 | 2026-06-17 | STOP | -9.31% | 1.35 | 9.81% | 13.46% | 9 | 98 | akshare_ths | 2026-06-16 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 601083 锦江航运 | 港口航运 | tracking_pool | 2026-06-17 | 2026-06-18 | STOP | -8.75% | 2.12 | 9.00% | 24.18% | 24 | 70 | akshare_ths | 2026-06-17 | PULLBACK_REPAIR |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 603790 雅运股份 | 化学制品 | tracking_pool | 2026-06-17 | 2026-06-18 | STOP | -9.61% | 3.12 | 9.61% | 26.72% | 10 | 58 | akshare_ths | 2026-06-17 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 603790 雅运股份 | 化学制品 | tracking_pool | 2026-06-22 | 2026-06-23 | STOP | -7.20% | 3.46 | 8.26% | 26.72% | 10 | 63 | akshare_ths | 2026-06-22 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 001378 德冠新材 | 塑料制品 | tracking_pool | 2026-06-23 | 2026-06-24 | STOP | -8.40% | 1.13 | 9.04% | 14.09% | 17 | 105 | akshare_ths | 2026-06-23 | EARLY_ACCELERATION |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 601083 锦江航运 | 港口航运 | tracking_pool | 2026-06-23 | 2026-06-24 | STOP | -9.50% | 2.16 | 8.92% | 24.18% | 24 | 76 | akshare_ths | 2026-06-23 | PULLBACK_REPAIR |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 001872 招商港口 | 港口航运 | tracking_pool | 2026-06-23 | 2026-06-24 | UNRESOLVED | -1.49% | 2.81 | 6.85% | 18.47% | 26 | 76 | akshare_ths | 2026-06-23 | PULLBACK_REPAIR |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 001218 丽臣实业 | 化学制品 | tracking_pool | 2026-06-23 | 2026-06-24 | STOP | -7.70% | 1.69 | 8.93% | 18.84% | 16 | 64 | akshare_ths | 2026-06-23 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 301149 隆华新材 | 化学制品 | tracking_pool | 2026-07-01 | 2026-07-02 | UNRESOLVED | 8.34% | 3.74 | 9.98% | 31.38% | 31 | 72 | akshare_ths | 2026-07-01 | MAIN_TREND |
| confirm60_leader40_fw10_pb35_risk10_rr10 | 001218 丽臣实业 | 化学制品 | tracking_pool | 2026-07-01 | 2026-07-02 | UNRESOLVED | 5.35% | 2.96 | 8.54% | 23.01% | 39 | 72 | akshare_ths | 2026-07-01 | MAIN_TREND |
| early_only_risk10_pb35 | 300834 星辉环材 | 塑料制品 | merged_current_and_tracking | 2026-04-17 | 2026-04-20 | STOP | -10.67% | 1.78 | 12.45% | 18.28% | 4 | 0 | akshare_ths | 2026-04-17 | EARLY_ACCELERATION |
| early_only_risk10_pb35 | 301588 美新科技 | 塑料制品 | tracking_pool | 2026-04-17 | 2026-04-20 | TARGET | 30.28% | 3.85 | 7.87% | 26.76% | 18 | 38 | akshare_ths | 2026-04-17 | EARLY_ACCELERATION |
| early_only_risk10_pb35 | 002395 双象股份 | 塑料制品 | tracking_pool | 2026-04-17 | 2026-04-20 | TARGET | 15.97% | 2.97 | 5.16% | 18.27% | 28 | 38 | akshare_ths | 2026-04-17 | EARLY_ACCELERATION |
| early_only_risk10_pb35 | 688386 泛亚微透 | 塑料制品 | tracking_pool | 2026-04-17 | 2026-04-20 | STOP | -7.39% | 4.72 | 6.33% | 28.29% | 36 | 38 | akshare_ths | 2026-04-17 | EARLY_ACCELERATION |
| early_only_risk10_pb35 | 002395 双象股份 | 塑料制品 | tracking_pool | 2026-04-20 | 2026-04-21 | TARGET | 14.37% | 2.50 | 5.72% | 18.27% | 28 | 41 | akshare_ths | 2026-04-20 | EARLY_ACCELERATION |
| early_only_risk10_pb35 | 301518 长华化学 | 化学制品 | merged_current_and_tracking | 2026-04-21 | 2026-04-22 | STOP | -14.39% | 1.34 | 14.33% | 26.02% | 18 | 0 | akshare_ths | 2026-04-21 | EARLY_ACCELERATION |
| early_only_risk10_pb35 | 603790 雅运股份 | 化学制品 | merged_current_and_tracking | 2026-04-21 | 2026-04-22 | TARGET | 14.66% | 1.63 | 9.56% | 26.05% | 13 | 0 | akshare_ths | 2026-04-21 | EARLY_ACCELERATION |
| early_only_risk10_pb35 | 301092 争光股份 | 塑料制品 | tracking_pool | 2026-04-22 | 2026-04-23 | TARGET | 20.84% | 2.07 | 9.87% | 24.14% | 18 | 43 | akshare_ths | 2026-04-22 | EARLY_ACCELERATION |
| early_only_risk10_pb35 | 688386 泛亚微透 | 塑料制品 | tracking_pool | 2026-04-22 | 2026-04-23 | STOP | -7.33% | 4.42 | 6.55% | 28.29% | 36 | 43 | akshare_ths | 2026-04-22 | EARLY_ACCELERATION |
| early_only_risk10_pb35 | 002838 道恩股份 | 塑料制品 | tracking_pool | 2026-04-23 | 2026-04-24 | TARGET | 7.76% | 1.07 | 8.07% | 24.35% | 31 | 44 | akshare_ths | 2026-04-23 | EARLY_ACCELERATION |
| early_only_risk10_pb35 | 300834 星辉环材 | 塑料制品 | merged_current_and_tracking | 2026-04-29 | 2026-04-30 | TARGET | 40.03% | 6.20 | 6.32% | 23.25% | 15 | 0 | akshare_ths | 2026-04-29 | EARLY_ACCELERATION |
| early_only_risk10_pb35 | 600740 山西焦化 | 煤炭开采加工 | tracking_pool | 2026-04-29 | 2026-04-30 | STOP | -9.83% | 2.54 | 9.62% | 21.75% | 34 | 57 | akshare_ths | 2026-04-29 | EARLY_ACCELERATION |
| early_only_risk10_pb35 | 002128 电投能源 | 煤炭开采加工 | tracking_pool | 2026-04-29 | 2026-04-30 | STOP | -6.52% | 1.15 | 6.28% | 17.53% | 8 | 57 | akshare_ths | 2026-04-29 | EARLY_ACCELERATION |
| early_only_risk10_pb35 | 000822 山东海化 | 化学原料 | tracking_pool | 2026-04-29 | 2026-04-30 | STOP | -9.23% | 2.50 | 9.23% | 26.10% | 15 | 57 | akshare_ths | 2026-04-29 | EARLY_ACCELERATION |
| early_only_risk10_pb35 | 300980 祥源新材 | 塑料制品 | tracking_pool | 2026-04-29 | 2026-04-30 | STOP | -6.49% | 2.71 | 7.09% | 17.67% | 22 | 50 | akshare_ths | 2026-04-29 | EARLY_ACCELERATION |
| early_only_risk10_pb35 | 605033 美邦股份 | 农化制品 | tracking_pool | 2026-04-30 | 2026-05-06 | STOP | -9.60% | 5.61 | 8.82% | 33.37% | 19 | 55 | akshare_ths | 2026-04-30 | EARLY_ACCELERATION |
| early_only_risk10_pb35 | 300834 星辉环材 | 塑料制品 | tracking_pool | 2026-05-06 | 2026-05-07 | TARGET | 33.91% | 4.12 | 8.66% | 23.25% | 15 | 57 | akshare_ths | 2026-05-06 | EARLY_ACCELERATION |
| early_only_risk10_pb35 | 300980 祥源新材 | 塑料制品 | tracking_pool | 2026-05-07 | 2026-05-08 | STOP | -8.82% | 1.72 | 9.45% | 17.67% | 22 | 58 | akshare_ths | 2026-05-07 | EARLY_ACCELERATION |
| early_only_risk10_pb35 | 000719 中原传媒 | 文化传媒 | tracking_pool | 2026-05-07 | 2026-05-08 | STOP | -5.44% | 1.18 | 5.44% | 8.74% | 7 | 23 | akshare_ths | 2026-05-07 | EARLY_ACCELERATION |
| early_only_risk10_pb35 | 301518 长华化学 | 化学制品 | tracking_pool | 2026-05-07 | 2026-05-08 | STOP | -8.05% | 4.65 | 8.05% | 28.69% | 34 | 17 | akshare_ths | 2026-05-07 | EARLY_ACCELERATION |
| early_only_risk10_pb35 | 601107 四川成渝 | 公路铁路运输 | tracking_pool | 2026-05-08 | 2026-05-11 | STOP | -5.51% | 1.44 | 5.67% | 17.83% | 35 | 56 | akshare_ths | 2026-05-08 | EARLY_ACCELERATION |
| early_only_risk10_pb35 | 601107 四川成渝 | 公路铁路运输 | tracking_pool | 2026-05-11 | 2026-05-12 | STOP | -6.63% | 1.18 | 6.31% | 17.83% | 35 | 59 | akshare_ths | 2026-05-11 | EARLY_ACCELERATION |
| early_only_risk10_pb35 | 300980 祥源新材 | 塑料制品 | tracking_pool | 2026-05-13 | 2026-05-14 | STOP | -8.45% | 2.31 | 7.88% | 17.67% | 22 | 64 | akshare_ths | 2026-05-13 | EARLY_ACCELERATION |
| early_only_risk10_pb35 | 300834 星辉环材 | 塑料制品 | tracking_pool | 2026-06-16 | 2026-06-17 | STOP | -9.31% | 1.35 | 9.81% | 13.46% | 9 | 98 | akshare_ths | 2026-06-16 | EARLY_ACCELERATION |
| early_only_risk10_pb35 | 001378 德冠新材 | 塑料制品 | tracking_pool | 2026-06-23 | 2026-06-24 | STOP | -8.40% | 1.13 | 9.04% | 14.09% | 17 | 105 | akshare_ths | 2026-06-23 | EARLY_ACCELERATION |
| main_only_pb35_risk12 | 000822 山东海化 | 化学原料 | merged_current_and_tracking | 2026-03-11 | 2026-03-12 | STOP | -8.72% | 1.30 | 8.05% | 11.88% | 6 | 0 | akshare_ths | 2026-03-11 | MAIN_TREND |
| main_only_pb35_risk12 | 600740 山西焦化 | 煤炭开采加工 | tracking_pool | 2026-03-11 | 2026-03-12 | STOP | -7.85% | 1.99 | 6.70% | 11.26% | 6 | 8 | akshare_ths | 2026-03-11 | MAIN_TREND |
| main_only_pb35_risk12 | 000822 山东海化 | 化学原料 | tracking_pool | 2026-03-17 | 2026-03-18 | STOP | -6.54% | 1.58 | 7.23% | 11.88% | 6 | 14 | akshare_ths | 2026-03-17 | MAIN_TREND |
| main_only_pb35_risk12 | 600740 山西焦化 | 煤炭开采加工 | tracking_pool | 2026-03-23 | 2026-03-24 | STOP | -5.23% | 2.07 | 7.86% | 14.56% | 13 | 20 | akshare_ths | 2026-03-23 | MAIN_TREND |
| main_only_pb35_risk12 | 600740 山西焦化 | 煤炭开采加工 | tracking_pool | 2026-03-24 | 2026-03-25 | STOP | -5.02% | 2.15 | 7.67% | 14.56% | 13 | 21 | akshare_ths | 2026-03-24 | MAIN_TREND |
| main_only_pb35_risk12 | 600740 山西焦化 | 煤炭开采加工 | tracking_pool | 2026-03-25 | 2026-03-26 | STOP | -7.47% | 2.07 | 7.86% | 14.56% | 13 | 22 | akshare_ths | 2026-03-25 | MAIN_TREND |
| main_only_pb35_risk12 | 002128 电投能源 | 煤炭开采加工 | tracking_pool | 2026-03-25 | 2026-03-26 | STOP | -6.60% | 2.32 | 7.24% | 17.53% | 8 | 22 | akshare_ths | 2026-03-25 | MAIN_TREND |
| main_only_pb35_risk12 | 600740 山西焦化 | 煤炭开采加工 | tracking_pool | 2026-03-27 | 2026-03-30 | STOP | -9.98% | 1.83 | 8.45% | 14.56% | 13 | 24 | akshare_ths | 2026-03-27 | MAIN_TREND |
| main_only_pb35_risk12 | 002128 电投能源 | 煤炭开采加工 | tracking_pool | 2026-03-27 | 2026-03-30 | STOP | -9.81% | 2.81 | 6.37% | 17.53% | 8 | 24 | akshare_ths | 2026-03-27 | MAIN_TREND |
| main_only_pb35_risk12 | 301588 美新科技 | 塑料制品 | tracking_pool | 2026-04-08 | 2026-04-09 | TARGET | 31.01% | 3.97 | 7.70% | 26.76% | 18 | 29 | akshare_ths | 2026-04-08 | MAIN_TREND |
| main_only_pb35_risk12 | 300980 祥源新材 | 塑料制品 | tracking_pool | 2026-04-08 | 2026-04-09 | STOP | -6.71% | 1.41 | 7.53% | 11.67% | 8 | 29 | akshare_ths | 2026-04-08 | MAIN_TREND |
| main_only_pb35_risk12 | 301092 争光股份 | 塑料制品 | tracking_pool | 2026-04-08 | 2026-04-09 | TARGET | 29.17% | 3.37 | 8.45% | 24.14% | 18 | 29 | akshare_ths | 2026-04-08 | MAIN_TREND |
| main_only_pb35_risk12 | 001378 德冠新材 | 塑料制品 | tracking_pool | 2026-04-08 | 2026-04-09 | TARGET | 12.74% | 1.42 | 8.68% | 17.53% | 9 | 29 | akshare_ths | 2026-04-08 | MAIN_TREND |
| main_only_pb35_risk12 | 300221 银禧科技 | 塑料制品 | tracking_pool | 2026-04-08 | 2026-04-09 | TARGET | 31.82% | 3.57 | 8.55% | 28.13% | 35 | 29 | akshare_ths | 2026-04-08 | MAIN_TREND |
| main_only_pb35_risk12 | 002395 双象股份 | 塑料制品 | tracking_pool | 2026-04-08 | 2026-04-09 | TARGET | 13.44% | 1.59 | 8.01% | 18.27% | 28 | 29 | akshare_ths | 2026-04-08 | MAIN_TREND |
| main_only_pb35_risk12 | 002395 双象股份 | 塑料制品 | tracking_pool | 2026-04-09 | 2026-04-10 | TARGET | 11.43% | 1.28 | 9.00% | 18.27% | 28 | 30 | akshare_ths | 2026-04-09 | MAIN_TREND |
| main_only_pb35_risk12 | 000908 石药景峰 | 化学制药 | tracking_pool | 2026-04-09 | 2026-04-10 | STOP | -8.93% | 1.69 | 10.18% | 15.56% | 5 | 2 | akshare_ths | 2026-04-09 | MAIN_TREND |
| main_only_pb35_risk12 | 301092 争光股份 | 塑料制品 | tracking_pool | 2026-04-10 | 2026-04-13 | TARGET | 27.71% | 3.00 | 9.16% | 24.14% | 18 | 31 | akshare_ths | 2026-04-10 | MAIN_TREND |
| main_only_pb35_risk12 | 001378 德冠新材 | 塑料制品 | tracking_pool | 2026-04-10 | 2026-04-13 | TARGET | 12.74% | 1.51 | 8.37% | 17.53% | 9 | 31 | akshare_ths | 2026-04-10 | MAIN_TREND |
| main_only_pb35_risk12 | 001378 德冠新材 | 塑料制品 | tracking_pool | 2026-04-13 | 2026-04-14 | TARGET | 12.05% | 1.43 | 8.63% | 17.53% | 9 | 34 | akshare_ths | 2026-04-13 | MAIN_TREND |
| main_only_pb35_risk12 | 300221 银禧科技 | 塑料制品 | tracking_pool | 2026-04-13 | 2026-04-14 | TARGET | 29.09% | 3.68 | 8.36% | 28.13% | 35 | 34 | akshare_ths | 2026-04-13 | MAIN_TREND |
| main_only_pb35_risk12 | 605168 三人行 | 文化传媒 | merged_current_and_tracking | 2026-04-14 | 2026-04-15 | TARGET | 28.16% | 2.53 | 11.13% | 33.12% | 39 | 0 | akshare_ths | 2026-04-14 | MAIN_TREND |
| main_only_pb35_risk12 | 301588 美新科技 | 塑料制品 | tracking_pool | 2026-04-14 | 2026-04-15 | TARGET | 27.85% | 4.94 | 6.53% | 26.76% | 18 | 35 | akshare_ths | 2026-04-14 | MAIN_TREND |
| main_only_pb35_risk12 | 301092 争光股份 | 塑料制品 | tracking_pool | 2026-04-14 | 2026-04-15 | TARGET | 27.03% | 2.90 | 9.38% | 24.14% | 18 | 35 | akshare_ths | 2026-04-14 | MAIN_TREND |
| main_only_pb35_risk12 | 301588 美新科技 | 塑料制品 | tracking_pool | 2026-04-15 | 2026-04-16 | TARGET | 25.17% | 2.70 | 10.09% | 26.76% | 18 | 36 | akshare_ths | 2026-04-15 | MAIN_TREND |
| main_only_pb35_risk12 | 301092 争光股份 | 塑料制品 | tracking_pool | 2026-04-16 | 2026-04-17 | TARGET | 26.32% | 2.63 | 9.99% | 24.14% | 18 | 37 | akshare_ths | 2026-04-16 | MAIN_TREND |
| main_only_pb35_risk12 | 605168 三人行 | 文化传媒 | tracking_pool | 2026-04-16 | 2026-04-17 | TARGET | 26.97% | 2.25 | 11.96% | 33.12% | 39 | 2 | akshare_ths | 2026-04-16 | MAIN_TREND |
| main_only_pb35_risk12 | 000908 石药景峰 | 化学制药 | tracking_pool | 2026-04-17 | 2026-04-20 | STOP | -7.38% | 2.38 | 7.38% | 15.56% | 5 | 10 | akshare_ths | 2026-04-17 | MAIN_TREND |
| main_only_pb35_risk12 | 688513 苑东生物 | 化学制药 | tracking_pool | 2026-04-17 | 2026-04-20 | STOP | -4.00% | 3.89 | 5.28% | 18.91% | 7 | 10 | akshare_ths | 2026-04-17 | MAIN_TREND |
| main_only_pb35_risk12 | 688017 绿的谐波 | 自动化设备 | tracking_pool | 2026-04-21 | 2026-04-22 | TARGET | 17.79% | 1.45 | 11.34% | 27.35% | 21 | 6 | akshare_ths | 2026-04-21 | MAIN_TREND |
| main_only_pb35_risk12 | 000822 山东海化 | 化学原料 | tracking_pool | 2026-04-24 | 2026-04-27 | STOP | -6.65% | 2.27 | 10.01% | 26.10% | 15 | 52 | akshare_ths | 2026-04-24 | MAIN_TREND |
| main_only_pb35_risk12 | 000830 鲁西化工 | 化学原料 | tracking_pool | 2026-04-24 | 2026-04-27 | STOP | -9.57% | 2.46 | 11.56% | 27.68% | 36 | 52 | akshare_ths | 2026-04-24 | MAIN_TREND |
| main_only_pb35_risk12 | 000683 博源化工 | 化学原料 | tracking_pool | 2026-04-24 | 2026-04-27 | STOP | -9.79% | 1.15 | 10.09% | 21.59% | 9 | 52 | akshare_ths | 2026-04-24 | MAIN_TREND |
| main_only_pb35_risk12 | 600955 维远股份 | 化学原料 | tracking_pool | 2026-04-24 | 2026-04-27 | STOP | -9.41% | 1.61 | 8.51% | 30.19% | 20 | 52 | akshare_ths | 2026-04-24 | MAIN_TREND |
| main_only_pb35_risk12 | 600426 华鲁恒升 | 农化制品 | tracking_pool | 2026-04-24 | 2026-04-27 | STOP | -10.92% | 1.53 | 11.27% | 17.99% | 8 | 49 | akshare_ths | 2026-04-24 | MAIN_TREND |
| main_only_pb35_risk12 | 301092 争光股份 | 塑料制品 | tracking_pool | 2026-04-24 | 2026-04-27 | TARGET | 26.02% | 4.08 | 6.01% | 24.14% | 18 | 45 | akshare_ths | 2026-04-24 | MAIN_TREND |
| main_only_pb35_risk12 | 688386 泛亚微透 | 塑料制品 | tracking_pool | 2026-04-24 | 2026-04-27 | STOP | -6.89% | 4.14 | 6.89% | 28.29% | 36 | 45 | akshare_ths | 2026-04-24 | MAIN_TREND |
| main_only_pb35_risk12 | 600740 山西焦化 | 煤炭开采加工 | tracking_pool | 2026-04-27 | 2026-04-28 | STOP | -5.29% | 5.20 | 5.74% | 21.75% | 34 | 55 | akshare_ths | 2026-04-27 | MAIN_TREND |
| main_only_pb35_risk12 | 000830 鲁西化工 | 化学原料 | tracking_pool | 2026-04-27 | 2026-04-28 | STOP | -9.51% | 3.22 | 9.68% | 27.68% | 36 | 55 | akshare_ths | 2026-04-27 | MAIN_TREND |
| main_only_pb35_risk12 | 600623 华谊集团 | 化学原料 | tracking_pool | 2026-04-27 | 2026-04-28 | STOP | -6.95% | 5.63 | 4.39% | 26.08% | 16 | 55 | akshare_ths | 2026-04-27 | MAIN_TREND |
| main_only_pb35_risk12 | 000683 博源化工 | 化学原料 | tracking_pool | 2026-04-27 | 2026-04-28 | STOP | -9.99% | 1.10 | 10.29% | 21.59% | 9 | 55 | akshare_ths | 2026-04-27 | MAIN_TREND |
| main_only_pb35_risk12 | 002250 联化科技 | 农化制品 | tracking_pool | 2026-04-27 | 2026-04-28 | STOP | -11.17% | 1.02 | 10.77% | 23.83% | 17 | 52 | akshare_ths | 2026-04-27 | MAIN_TREND |
| main_only_pb35_risk12 | 002395 双象股份 | 塑料制品 | tracking_pool | 2026-04-27 | 2026-04-28 | TARGET | 13.44% | 1.13 | 8.91% | 18.27% | 28 | 48 | akshare_ths | 2026-04-27 | MAIN_TREND |
| main_only_pb35_risk12 | 688386 泛亚微透 | 塑料制品 | tracking_pool | 2026-04-27 | 2026-04-28 | STOP | -8.41% | 2.90 | 8.88% | 28.29% | 36 | 48 | akshare_ths | 2026-04-27 | MAIN_TREND |
| main_only_pb35_risk12 | 688017 绿的谐波 | 自动化设备 | tracking_pool | 2026-04-27 | 2026-04-28 | TARGET | 17.18% | 2.01 | 8.05% | 27.35% | 21 | 12 | akshare_ths | 2026-04-27 | MAIN_TREND |
| main_only_pb35_risk12 | 000830 鲁西化工 | 化学原料 | tracking_pool | 2026-04-28 | 2026-04-29 | STOP | -9.51% | 2.44 | 11.61% | 27.68% | 36 | 56 | akshare_ths | 2026-04-28 | MAIN_TREND |
| main_only_pb35_risk12 | 000683 博源化工 | 化学原料 | tracking_pool | 2026-04-28 | 2026-04-29 | STOP | -9.99% | 1.04 | 10.59% | 21.59% | 9 | 56 | akshare_ths | 2026-04-28 | MAIN_TREND |
| main_only_pb35_risk12 | 600955 维远股份 | 化学原料 | tracking_pool | 2026-04-28 | 2026-04-29 | STOP | -7.47% | 1.10 | 9.31% | 30.19% | 20 | 56 | akshare_ths | 2026-04-28 | MAIN_TREND |
| main_only_pb35_risk12 | 688386 泛亚微透 | 塑料制品 | tracking_pool | 2026-04-28 | 2026-04-29 | STOP | -9.29% | 2.59 | 9.03% | 28.29% | 36 | 49 | akshare_ths | 2026-04-28 | MAIN_TREND |
| main_only_pb35_risk12 | 688017 绿的谐波 | 自动化设备 | tracking_pool | 2026-04-29 | 2026-04-30 | TARGET | 16.03% | 1.81 | 8.57% | 27.35% | 21 | 14 | akshare_ths | 2026-04-29 | MAIN_TREND |
| main_only_pb35_risk12 | 300221 银禧科技 | 塑料制品 | tracking_pool | 2026-04-30 | 2026-05-06 | TARGET | 6.60% | 1.40 | 5.67% | 28.13% | 35 | 51 | akshare_ths | 2026-04-30 | MAIN_TREND |
| main_only_pb35_risk12 | 600125 铁龙物流 | 公路铁路运输 | tracking_pool | 2026-04-30 | 2026-05-06 | STOP | -5.22% | 3.38 | 5.07% | 14.53% | 20 | 48 | akshare_ths | 2026-04-30 | MAIN_TREND |
| main_only_pb35_risk12 | 600740 山西焦化 | 煤炭开采加工 | tracking_pool | 2026-05-06 | 2026-05-07 | STOP | -7.07% | 3.51 | 7.72% | 21.75% | 34 | 64 | akshare_ths | 2026-05-06 | MAIN_TREND |
| main_only_pb35_risk12 | 002126 银轮股份 | 汽车零部件 | tracking_pool | 2026-05-06 | 2026-05-07 | TARGET | 15.15% | 1.37 | 11.26% | 26.30% | 21 | 19 | akshare_ths | 2026-05-06 | MAIN_TREND |
| main_only_pb35_risk12 | 603565 中谷物流 | 港口航运 | tracking_pool | 2026-05-07 | 2026-05-08 | STOP | -8.68% | 1.24 | 8.60% | 14.65% | 4 | 29 | akshare_ths | 2026-05-07 | MAIN_TREND |
| main_only_pb35_risk12 | 601083 锦江航运 | 港口航运 | tracking_pool | 2026-05-08 | 2026-05-11 | STOP | -6.38% | 1.64 | 6.70% | 24.18% | 24 | 30 | akshare_ths | 2026-05-08 | MAIN_TREND |
| main_only_pb35_risk12 | 600955 维远股份 | 化学原料 | tracking_pool | 2026-05-11 | 2026-05-12 | STOP | -4.97% | 2.44 | 5.48% | 30.19% | 20 | 69 | akshare_ths | 2026-05-11 | MAIN_TREND |
| main_only_pb35_risk12 | 688336 三生国健 | 生物制品 | tracking_pool | 2026-05-11 | 2026-05-12 | STOP | -6.24% | 4.78 | 6.52% | 23.86% | 22 | 40 | akshare_ths | 2026-05-11 | MAIN_TREND |
| main_only_pb35_risk12 | 688513 苑东生物 | 化学制药 | tracking_pool | 2026-05-11 | 2026-05-12 | STOP | -4.78% | 3.90 | 6.30% | 22.42% | 22 | 34 | akshare_ths | 2026-05-11 | MAIN_TREND |
| main_only_pb35_risk12 | 001367 海森药业 | 化学制药 | tracking_pool | 2026-05-11 | 2026-05-12 | STOP | -6.39% | 2.28 | 6.70% | 15.62% | 11 | 34 | akshare_ths | 2026-05-11 | MAIN_TREND |
| main_only_pb35_risk12 | 000908 石药景峰 | 化学制药 | tracking_pool | 2026-05-12 | 2026-05-13 | STOP | -9.79% | 1.63 | 8.94% | 15.56% | 5 | 35 | akshare_ths | 2026-05-12 | MAIN_TREND |
| main_only_pb35_risk12 | 001367 海森药业 | 化学制药 | tracking_pool | 2026-05-12 | 2026-05-13 | STOP | -8.07% | 1.84 | 7.66% | 15.62% | 11 | 35 | akshare_ths | 2026-05-12 | MAIN_TREND |
| main_only_pb35_risk12 | 600428 中远海特 | 港口航运 | tracking_pool | 2026-05-14 | 2026-05-15 | STOP | -4.35% | 4.93 | 4.24% | 15.21% | 24 | 36 | akshare_ths | 2026-05-14 | MAIN_TREND |
| main_only_pb35_risk12 | 688386 泛亚微透 | 塑料制品 | tracking_pool | 2026-05-18 | 2026-05-19 | STOP | -7.88% | 2.58 | 8.62% | 28.29% | 36 | 69 | akshare_ths | 2026-05-18 | MAIN_TREND |
| main_only_pb35_risk12 | 301237 和顺科技 | 塑料制品 | tracking_pool | 2026-05-19 | 2026-05-20 | STOP | -9.64% | 1.21 | 9.63% | 8.20% | 4 | 70 | akshare_ths | 2026-05-19 | MAIN_TREND |
| main_only_pb35_risk12 | 001268 联合精密 | 白色家电 | tracking_pool | 2026-05-22 | 2026-05-25 | STOP | -8.88% | 1.13 | 8.88% | 7.17% | 2 | 32 | akshare_ths | 2026-05-22 | MAIN_TREND |
| main_only_pb35_risk12 | 603580 艾艾精工 | 塑料制品 | tracking_pool | 2026-05-28 | 2026-05-29 | STOP | -13.18% | 1.10 | 11.17% | 16.22% | 10 | 79 | akshare_ths | 2026-05-28 | MAIN_TREND |
| main_only_pb35_risk12 | 600395 盘江股份 | 煤炭开采加工 | tracking_pool | 2026-05-29 | 2026-06-01 | STOP | -11.54% | 1.36 | 10.91% | 19.43% | 38 | 87 | akshare_ths | 2026-05-29 | MAIN_TREND |
| main_only_pb35_risk12 | 600348 华阳股份 | 煤炭开采加工 | tracking_pool | 2026-05-29 | 2026-06-01 | STOP | -7.84% | 2.04 | 6.85% | 16.54% | 12 | 87 | akshare_ths | 2026-05-29 | MAIN_TREND |
| main_only_pb35_risk12 | 002979 雷赛智能 | 自动化设备 | tracking_pool | 2026-06-09 | 2026-06-10 | STOP | -8.14% | 2.35 | 9.38% | 23.59% | 11 | 55 | akshare_ths | 2026-06-09 | MAIN_TREND |
| main_only_pb35_risk12 | 600508 上海能源 | 煤炭开采加工 | tracking_pool | 2026-06-12 | 2026-06-15 | STOP | -6.29% | 2.40 | 7.30% | 16.68% | 7 | 101 | akshare_ths | 2026-06-12 | MAIN_TREND |
| main_only_pb35_risk12 | 300834 星辉环材 | 塑料制品 | tracking_pool | 2026-06-15 | 2026-06-16 | STOP | -9.53% | 1.21 | 10.38% | 13.46% | 9 | 97 | akshare_ths | 2026-06-15 | MAIN_TREND |
| main_only_pb35_risk12 | 603790 雅运股份 | 化学制品 | tracking_pool | 2026-06-17 | 2026-06-18 | STOP | -9.61% | 3.12 | 9.61% | 26.72% | 10 | 58 | akshare_ths | 2026-06-17 | MAIN_TREND |
| main_only_pb35_risk12 | 603790 雅运股份 | 化学制品 | tracking_pool | 2026-06-22 | 2026-06-23 | STOP | -7.20% | 3.46 | 8.26% | 26.72% | 10 | 63 | akshare_ths | 2026-06-22 | MAIN_TREND |
| main_only_pb35_risk12 | 600784 鲁银投资 | 化学原料 | tracking_pool | 2026-06-23 | 2026-06-24 | STOP | -10.96% | 2.35 | 10.96% | 26.90% | 18 | 112 | akshare_ths | 2026-06-23 | MAIN_TREND |
| main_only_pb35_risk12 | 001367 海森药业 | 化学制药 | tracking_pool | 2026-06-23 | 2026-06-24 | STOP | -9.65% | 3.71 | 10.00% | 31.82% | 34 | 77 | akshare_ths | 2026-06-23 | MAIN_TREND |
| main_only_pb35_risk12 | 001218 丽臣实业 | 化学制品 | tracking_pool | 2026-06-23 | 2026-06-24 | STOP | -7.70% | 1.69 | 8.93% | 18.84% | 16 | 64 | akshare_ths | 2026-06-23 | MAIN_TREND |
| main_only_pb35_risk12 | 300006 莱美药业 | 化学制药 | tracking_pool | 2026-06-29 | 2026-06-30 | UNRESOLVED | 3.54% | 4.13 | 10.91% | 34.65% | 29 | 83 | akshare_ths | 2026-06-29 | MAIN_TREND |
| main_only_pb35_risk12 | 301149 隆华新材 | 化学制品 | tracking_pool | 2026-07-01 | 2026-07-02 | UNRESOLVED | 8.34% | 3.74 | 9.98% | 31.38% | 31 | 72 | akshare_ths | 2026-07-01 | MAIN_TREND |
| main_only_pb35_risk12 | 001218 丽臣实业 | 化学制品 | tracking_pool | 2026-07-01 | 2026-07-02 | UNRESOLVED | 5.35% | 2.96 | 8.54% | 23.01% | 39 | 72 | akshare_ths | 2026-07-01 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 000822 山东海化 | 化学原料 | merged_current_and_tracking | 2026-03-11 | 2026-03-12 | STOP | -8.72% | 1.30 | 8.05% | 11.88% | 6 | 0 | akshare_ths | 2026-03-11 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 600740 山西焦化 | 煤炭开采加工 | tracking_pool | 2026-03-11 | 2026-03-12 | STOP | -7.85% | 1.99 | 6.70% | 11.26% | 6 | 8 | akshare_ths | 2026-03-11 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 000822 山东海化 | 化学原料 | tracking_pool | 2026-03-17 | 2026-03-18 | STOP | -6.54% | 1.58 | 7.23% | 11.88% | 6 | 14 | akshare_ths | 2026-03-17 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 600740 山西焦化 | 煤炭开采加工 | tracking_pool | 2026-03-23 | 2026-03-24 | STOP | -5.23% | 2.07 | 7.86% | 14.56% | 13 | 20 | akshare_ths | 2026-03-23 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 600740 山西焦化 | 煤炭开采加工 | tracking_pool | 2026-03-24 | 2026-03-25 | STOP | -5.02% | 2.15 | 7.67% | 14.56% | 13 | 21 | akshare_ths | 2026-03-24 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 600740 山西焦化 | 煤炭开采加工 | tracking_pool | 2026-03-25 | 2026-03-26 | STOP | -7.47% | 2.07 | 7.86% | 14.56% | 13 | 22 | akshare_ths | 2026-03-25 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 002128 电投能源 | 煤炭开采加工 | tracking_pool | 2026-03-25 | 2026-03-26 | STOP | -6.60% | 2.32 | 7.24% | 17.53% | 8 | 22 | akshare_ths | 2026-03-25 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 002128 电投能源 | 煤炭开采加工 | tracking_pool | 2026-03-27 | 2026-03-30 | STOP | -9.81% | 2.81 | 6.37% | 17.53% | 8 | 24 | akshare_ths | 2026-03-27 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 000908 石药景峰 | 化学制药 | tracking_pool | 2026-04-09 | 2026-04-10 | STOP | -8.93% | 1.69 | 10.18% | 15.56% | 5 | 1 | akshare_ths | 2026-04-09 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 300834 星辉环材 | 塑料制品 | merged_current_and_tracking | 2026-04-17 | 2026-04-20 | STOP | -10.67% | 1.78 | 12.45% | 18.28% | 4 | 0 | akshare_ths | 2026-04-17 | EARLY_ACCELERATION |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 000908 石药景峰 | 化学制药 | tracking_pool | 2026-04-17 | 2026-04-20 | STOP | -7.38% | 2.38 | 7.38% | 15.56% | 5 | 9 | akshare_ths | 2026-04-17 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 688513 苑东生物 | 化学制药 | tracking_pool | 2026-04-17 | 2026-04-20 | STOP | -4.00% | 3.89 | 5.28% | 18.91% | 7 | 9 | akshare_ths | 2026-04-17 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 688017 绿的谐波 | 自动化设备 | tracking_pool | 2026-04-21 | 2026-04-22 | TARGET | 17.79% | 1.45 | 11.34% | 27.35% | 21 | 6 | akshare_ths | 2026-04-21 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 603790 雅运股份 | 化学制品 | tracking_pool | 2026-04-21 | 2026-04-22 | TARGET | 14.66% | 1.63 | 9.56% | 26.05% | 13 | 1 | akshare_ths | 2026-04-21 | EARLY_ACCELERATION |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 301149 隆华新材 | 化学制品 | tracking_pool | 2026-04-23 | 2026-04-24 | TARGET | 9.18% | 1.39 | 5.69% | 19.06% | 35 | 3 | akshare_ths | 2026-04-23 | PULLBACK_REPAIR |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 000830 鲁西化工 | 化学原料 | tracking_pool | 2026-04-24 | 2026-04-27 | STOP | -9.57% | 2.46 | 11.56% | 27.68% | 36 | 52 | akshare_ths | 2026-04-24 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 000683 博源化工 | 化学原料 | tracking_pool | 2026-04-24 | 2026-04-27 | STOP | -9.79% | 1.15 | 10.09% | 21.59% | 9 | 52 | akshare_ths | 2026-04-24 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 600955 维远股份 | 化学原料 | tracking_pool | 2026-04-24 | 2026-04-27 | STOP | -9.41% | 1.61 | 8.51% | 30.19% | 20 | 52 | akshare_ths | 2026-04-24 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 600426 华鲁恒升 | 农化制品 | tracking_pool | 2026-04-24 | 2026-04-27 | STOP | -10.92% | 1.53 | 11.27% | 17.99% | 8 | 49 | akshare_ths | 2026-04-24 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 600623 华谊集团 | 化学原料 | tracking_pool | 2026-04-27 | 2026-04-28 | STOP | -6.95% | 5.63 | 4.39% | 26.08% | 16 | 55 | akshare_ths | 2026-04-27 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 000830 鲁西化工 | 化学原料 | tracking_pool | 2026-04-27 | 2026-04-28 | STOP | -9.51% | 3.22 | 9.68% | 27.68% | 36 | 55 | akshare_ths | 2026-04-27 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 000683 博源化工 | 化学原料 | tracking_pool | 2026-04-27 | 2026-04-28 | STOP | -9.99% | 1.10 | 10.29% | 21.59% | 9 | 55 | akshare_ths | 2026-04-27 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 688017 绿的谐波 | 自动化设备 | tracking_pool | 2026-04-27 | 2026-04-28 | TARGET | 17.18% | 2.01 | 8.05% | 27.35% | 21 | 12 | akshare_ths | 2026-04-27 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 000830 鲁西化工 | 化学原料 | tracking_pool | 2026-04-28 | 2026-04-29 | STOP | -9.51% | 2.44 | 11.61% | 27.68% | 36 | 56 | akshare_ths | 2026-04-28 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 000683 博源化工 | 化学原料 | tracking_pool | 2026-04-28 | 2026-04-29 | STOP | -9.99% | 1.04 | 10.59% | 21.59% | 9 | 56 | akshare_ths | 2026-04-28 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 600955 维远股份 | 化学原料 | tracking_pool | 2026-04-28 | 2026-04-29 | STOP | -7.47% | 1.10 | 9.31% | 30.19% | 20 | 56 | akshare_ths | 2026-04-28 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 300834 星辉环材 | 塑料制品 | merged_current_and_tracking | 2026-04-29 | 2026-04-30 | TARGET | 40.03% | 6.20 | 6.32% | 23.25% | 15 | 0 | akshare_ths | 2026-04-29 | EARLY_ACCELERATION |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 000830 鲁西化工 | 化学原料 | tracking_pool | 2026-04-29 | 2026-04-30 | STOP | -12.75% | 2.51 | 11.40% | 27.68% | 36 | 57 | akshare_ths | 2026-04-29 | EARLY_ACCELERATION |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 688017 绿的谐波 | 自动化设备 | tracking_pool | 2026-04-29 | 2026-04-30 | TARGET | 16.03% | 1.81 | 8.57% | 27.35% | 21 | 14 | akshare_ths | 2026-04-29 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 300221 银禧科技 | 塑料制品 | tracking_pool | 2026-04-30 | 2026-05-06 | TARGET | 6.60% | 1.40 | 5.67% | 28.13% | 35 | 13 | akshare_ths | 2026-04-30 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 300834 星辉环材 | 塑料制品 | tracking_pool | 2026-05-06 | 2026-05-07 | TARGET | 33.91% | 4.12 | 8.66% | 23.25% | 15 | 19 | akshare_ths | 2026-05-06 | EARLY_ACCELERATION |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 002126 银轮股份 | 汽车零部件 | tracking_pool | 2026-05-06 | 2026-05-07 | TARGET | 15.15% | 1.37 | 11.26% | 26.30% | 21 | 19 | akshare_ths | 2026-05-06 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 301518 长华化学 | 化学制品 | tracking_pool | 2026-05-07 | 2026-05-08 | STOP | -8.05% | 4.65 | 8.05% | 28.69% | 34 | 17 | akshare_ths | 2026-05-07 | EARLY_ACCELERATION |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 688336 三生国健 | 生物制品 | tracking_pool | 2026-05-11 | 2026-05-12 | STOP | -6.24% | 4.78 | 6.52% | 23.86% | 22 | 40 | akshare_ths | 2026-05-11 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 001367 海森药业 | 化学制药 | tracking_pool | 2026-05-11 | 2026-05-12 | STOP | -6.39% | 2.28 | 6.70% | 15.62% | 11 | 33 | akshare_ths | 2026-05-11 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 001367 海森药业 | 化学制药 | tracking_pool | 2026-05-12 | 2026-05-13 | STOP | -8.07% | 1.84 | 7.66% | 15.62% | 11 | 34 | akshare_ths | 2026-05-12 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 000534 万泽股份 | 生物制品 | tracking_pool | 2026-05-13 | 2026-05-14 | STOP | -10.45% | 1.89 | 11.06% | 26.48% | 15 | 42 | akshare_ths | 2026-05-13 | PULLBACK_REPAIR |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 301237 和顺科技 | 塑料制品 | tracking_pool | 2026-05-19 | 2026-05-20 | STOP | -9.64% | 1.21 | 9.63% | 8.20% | 4 | 32 | akshare_ths | 2026-05-19 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 001268 联合精密 | 白色家电 | tracking_pool | 2026-05-22 | 2026-05-25 | STOP | -8.88% | 1.13 | 8.88% | 7.17% | 2 | 32 | akshare_ths | 2026-05-22 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 603580 艾艾精工 | 塑料制品 | tracking_pool | 2026-05-28 | 2026-05-29 | STOP | -13.18% | 1.10 | 11.17% | 16.22% | 10 | 41 | akshare_ths | 2026-05-28 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 600395 盘江股份 | 煤炭开采加工 | tracking_pool | 2026-05-29 | 2026-06-01 | STOP | -11.54% | 1.36 | 10.91% | 19.43% | 38 | 87 | akshare_ths | 2026-05-29 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 600348 华阳股份 | 煤炭开采加工 | tracking_pool | 2026-05-29 | 2026-06-01 | STOP | -7.84% | 2.04 | 6.85% | 16.54% | 12 | 87 | akshare_ths | 2026-05-29 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 002979 雷赛智能 | 自动化设备 | tracking_pool | 2026-06-09 | 2026-06-10 | STOP | -8.14% | 2.35 | 9.38% | 23.59% | 11 | 55 | akshare_ths | 2026-06-09 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 600508 上海能源 | 煤炭开采加工 | tracking_pool | 2026-06-12 | 2026-06-15 | STOP | -6.29% | 2.40 | 7.30% | 16.68% | 7 | 101 | akshare_ths | 2026-06-12 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 600784 鲁银投资 | 化学原料 | tracking_pool | 2026-06-15 | 2026-06-16 | STOP | -5.59% | 3.61 | 6.39% | 21.49% | 12 | 104 | akshare_ths | 2026-06-15 | PULLBACK_REPAIR |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 300834 星辉环材 | 塑料制品 | tracking_pool | 2026-06-15 | 2026-06-16 | STOP | -9.53% | 1.21 | 10.38% | 13.46% | 9 | 59 | akshare_ths | 2026-06-15 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 688571 杭华股份 | 化学制品 | tracking_pool | 2026-06-15 | 2026-06-16 | STOP | -8.71% | 1.80 | 9.78% | 20.46% | 17 | 56 | akshare_ths | 2026-06-15 | PULLBACK_REPAIR |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 300834 星辉环材 | 塑料制品 | tracking_pool | 2026-06-16 | 2026-06-17 | STOP | -9.31% | 1.35 | 9.81% | 13.46% | 9 | 60 | akshare_ths | 2026-06-16 | EARLY_ACCELERATION |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 603790 雅运股份 | 化学制品 | tracking_pool | 2026-06-17 | 2026-06-18 | STOP | -9.61% | 3.12 | 9.61% | 26.72% | 10 | 58 | akshare_ths | 2026-06-17 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 603790 雅运股份 | 化学制品 | tracking_pool | 2026-06-22 | 2026-06-23 | STOP | -7.20% | 3.46 | 8.26% | 26.72% | 10 | 63 | akshare_ths | 2026-06-22 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 600784 鲁银投资 | 化学原料 | tracking_pool | 2026-06-23 | 2026-06-24 | STOP | -10.96% | 2.35 | 10.96% | 26.90% | 18 | 112 | akshare_ths | 2026-06-23 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 001218 丽臣实业 | 化学制品 | tracking_pool | 2026-06-23 | 2026-06-24 | STOP | -7.70% | 1.69 | 8.93% | 18.84% | 16 | 64 | akshare_ths | 2026-06-23 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 001872 招商港口 | 港口航运 | tracking_pool | 2026-06-23 | 2026-06-24 | UNRESOLVED | -1.49% | 2.81 | 6.85% | 18.47% | 26 | 46 | akshare_ths | 2026-06-23 | PULLBACK_REPAIR |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 300006 莱美药业 | 化学制药 | tracking_pool | 2026-06-29 | 2026-06-30 | UNRESOLVED | 3.54% | 4.13 | 10.91% | 34.65% | 29 | 82 | akshare_ths | 2026-06-29 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 301149 隆华新材 | 化学制品 | tracking_pool | 2026-07-01 | 2026-07-02 | UNRESOLVED | 8.34% | 3.74 | 9.98% | 31.38% | 31 | 72 | akshare_ths | 2026-07-01 | MAIN_TREND |
| confirm65_leader50_fw15_pb35_risk12_rr10 | 001218 丽臣实业 | 化学制品 | tracking_pool | 2026-07-01 | 2026-07-02 | UNRESOLVED | 5.35% | 2.96 | 8.54% | 23.01% | 39 | 72 | akshare_ths | 2026-07-01 | MAIN_TREND |

## 最佳参数组合

当前表现最好的可执行实验是 `early_only_risk10_pb35`：入场 25，平均收益 1.43%，PF 1.25。
是否升级正式参数仍需结合样本量、月度集中度和最大连续亏损审查；样本不足时不建议自动升级。

## 结论

当前策略4真实快照覆盖 3 个交易日，历史样本仍偏少。
行业/题材指数缓存覆盖 40 个题材、13369 行，日期范围 2025-02-17 至 2026-07-02。
本次回测仅使用历史快照、跟踪池历史状态，以及 evaluation_date 当日及之前的真实板块K线和个股K线，不使用未来数据。
跟踪池最大入池题材数 31，最大入池龙头数 235。
参数实验最多产生 123 个机会、123 个可观察入场；正式升级仍需检查样本量和集中度。

## 失效场景

- 缺少历史热点题材快照时，回测日标记为 `UNOBSERVED_TOPIC_SNAPSHOT`。
- 缺少行业/题材指数历史缓存时，报告标记为 `UNOBSERVED_TOPIC_INDEX`，不伪造板块指数走势。
- 次日一字涨停不可成交时，机会标记为 `NO_ENTRY_LIMIT_UP_UNBUYABLE`。
- 次日 T 字涨停或开盘涨停回封时，机会标记为 `NO_ENTRY_OPEN_LIMIT_UNOBSERVED`，不假设能按开盘价成交。
- 历史快照未覆盖完整热点周期时，参数实验可能只反映单日市场状态。

## 过拟合风险

目前可观察策略4样本过少。若直接根据单日热点榜调参，会把参数拟合到一个截面，而不是二波交易规律。

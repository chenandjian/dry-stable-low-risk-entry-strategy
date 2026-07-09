# 策略6强势 VCP 尾部候选池设计

## 1. 目标

策略6基于用户提供的 `strong-vcp-stock-selection-strategy.md` 独立开发，不增强或复用策略5的候选判断语义。

策略6筛选的是：

```text
强势启动 -> 有支撑横盘 -> 尾部价稳量干 -> 盈亏比合格 -> 候选池
```

候选池不是直接买入清单。每只候选必须输出支撑位、买入区、止损、三档目标、盈亏比、评分、候选类型、风险标签和操作建议。

## 2. 策略边界

- 新增独立包 `strategy6/`。
- 新增独立扫描类型 `STRATEGY_6_STRONG_VCP_TAIL`。
- 新增独立候选表 `strategy6_candidates`。
- 新增独立 API、前端结果页和配置区。
- 不修改策略1、策略2、策略3、策略4、策略5的入选规则。
- 可复用共享数据层：`scanner/daily_data_service.py`、`scanner/db.py`、`scan_tasks/task_stocks`、股票池和日线缓存。
- 策略6不得写入策略1 `candidates`、策略2 `strategy2_candidates`、策略3/4/5候选表。

## 3. 一期实现范围

一期完整实现策略核心、扫描闭环、候选持久化和前端展示：

1. 基础指标：MA5/10/20/50/120/250、return_5/10/20、V3/5/10/20、成交额均值、振幅、收盘价波动。
2. A股涨停判断：主板10%，创业板/科创板20%。
3. 强势启动识别：普通强势大阳线、放量涨停、缩量涨停、一字涨停、触及涨停未封住。
4. 强势启动等级：S/A/B/NONE。
5. 新高确认：最近20日最高收盘接近或创120日高点。
6. 上方压力标签：近120日高点压力、放量长上影压力。
7. 支撑横盘：MA5/MA10/MA20/MA50支撑，支撑失败排除。
8. 支撑位价格：从均线、10/20日低点、平台下沿、强启动低点中评分选择。
9. 支撑区间和支撑测试次数。
10. 尾部价稳量干：V5/V20、V3<V5<V10<V20、5日收盘波动、跌不动、无放量下跌。
11. 一票否决：放量下跌、支撑失败、无强启动、无新高确认、盈亏比不足。
12. 交易计划：建议买入价、买入区、止损、目标1/2/3、RR1/2/3。
13. 评分：强启动25 + 支撑25 + 尾部价稳量干25 + 盈亏比15 + 风控10。
14. 分层：`READY_CANDIDATE`、`KEY_CANDIDATE`、`WATCH_CANDIDATE`、`REJECTED`。
15. 生命周期状态：一期按当前日计算 `SETUP_FORMING`、`READY`、`BUY_ZONE`、`BREAKOUT_CONFIRMED`、`EXTENDED`、`FAILED`；跨日持久状态机留到二期。
16. 前端：扫描入口、任务列表识别、策略6结果页、配置页。

## 4. 一期明确不做

以下能力保留字段和配置，不阻塞一期上线：

- 真实市场环境过滤：一期输出 `market_status=UNKNOWN`，过滤开关关闭时不得影响候选。
- 真实板块强度过滤：一期输出 `sector_strength_status=UNKNOWN`，过滤开关关闭时不得影响候选。
- Excel日报：一期通过 API 和候选表输出完整字段。
- 跨日候选池持久生命周期：一期输出当前日生命周期状态，二期再做候选首次入池日期、10交易日过期、连续跟踪。

## 5. 数据输入

日线输入按升序排列：

```text
data[0] = 最早交易日
data[-1] = 评估日
```

策略6接受项目现有日线字段并归一化：

- `date` 或 `trade_date`
- `open`
- `high`
- `low`
- `close`
- `prev_close` 缺失时用前一日 close 推导
- `volume`
- `turnover` 或 `amount`
- `code/name/sector_name` 从扫描股票池或候选字段补充

最少历史交易日默认 `minimum_trading_days=500`，建议拉取 `kline_days=1100`。

## 6. 核心模块

```text
strategy6/
  __init__.py
  models.py          数据模型和候选输出结构
  validation.py      默认配置和参数校验
  indicators.py      基础指标、涨幅、均线、成交量、振幅
  limit_up.py        A股涨停/一字板/触板未封判断
  strong_start.py    强势启动类型和等级
  support.py         支撑状态、支撑候选评分、支撑区间
  dry_tail.py        尾部价稳量干和卖压衰竭
  pressure.py        上方压力和长上影风险标签
  trade_plan.py      买入区、止损、目标、盈亏比
  scorer.py          100分评分
  filters.py         硬过滤和候选分层
  engine.py          单股唯一判断入口
  scanner.py         全市场扫描编排
```

唯一策略判断入口为：

```python
StrongVcpTailEngine.evaluate_at(data, code, name="", sector_name="", ...)
```

所有扫描、回测和详情重算后续都必须通过该入口。

## 7. 候选输出字段

一期候选表和 API 至少输出：

- 股票：`code`、`name`、`sector_name`
- 任务：`task_id`、`evaluation_date`、`data_source`、`kline_latest_date`、`kline_fetched_at`
- 配置开关：`enable_market_filter`、`enable_sector_filter`、`market_filter_mode`、`sector_filter_mode`
- 行情指标：`current_price`、`daily_return`、MA、return、成交额均值、V3/5/10/20、`volume_ratio_5_20`
- 强启动：`start_date`、`start_type`、`start_grade`、`start_day_return`、`start_day_volume_ratio`、`start_day_amount`、`start_day_close_position`、`is_limit_up`、`is_one_word_limit_up`、`limit_up_pct`
- 支撑：`key_support_price`、`support_zone_low`、`support_zone_high`、`defense_support_price`、`main_support_ma`、`support_status`、`support_test_count`
- 交易计划：`suggested_buy_price`、`buy_zone_low`、`buy_zone_high`、`stop_loss_price`、`target_price_1/2/3`、`risk_amount`、`reward_amount_1/2/3`、`risk_reward_ratio_1/2/3`
- 评分：`strong_start_score`、`support_score`、`dry_stable_score`、`risk_reward_score`、`risk_control_score`、`total_score`
- 结论：`candidate_type`、`classification`、`lifecycle_status`、`risk_tags`、`warn_tags`、`reject_reasons`、`suggestion`

字段只新增，不删除旧策略字段。

## 8. 分层规则

`READY_CANDIDATE`：

- `total_score >= 85`
- `risk_reward_ratio_2 >= 2.5`
- 当前价在支撑区间内
- `volume_ratio_5_20 <= 0.60`
- 支撑状态为 MA5/MA10/MA20
- 无重大风险标签

`KEY_CANDIDATE`：

- `total_score >= 75`
- `risk_reward_ratio_2 >= 2.0`
- 支撑状态为 MA5/MA10/MA20
- 尾部价稳量干分 `>= 15`
- 无重大风险标签

`WATCH_CANDIDATE`：

- `total_score >= 60`
- 或 `risk_reward_ratio_2 >= 1.5`
- 或 MA50测试、一字板未确认、B级启动、上方压力偏大、尾部量未完全干透

`REJECTED`：

- 放量下跌
- 支撑失败
- 无强启动
- 无新高确认
- `risk_reward_ratio_2 < 1.5`
- 数据不足

## 9. API 和前端

后端新增：

```text
POST /api/strategy6/scans
GET  /api/strategy6/scans/status
GET  /api/strategy6/tasks
GET  /api/strategy6/tasks/{task_id}/candidates
GET  /api/strategy6/tasks/{task_id}/candidates/{code}
```

前端新增：

- `Strategy6Results.vue`
- 顶部导航策略6入口
- 扫描控制台策略6启动按钮
- 任务中心策略6标签与查看结果跳转
- 策略配置页 `strategy6` 配置分区

## 10. 测试要求

后端测试：

- 主板10%、创业板/科创板20%涨停判断。
- 一字涨停不能因成交量低被误杀。
- 触及涨停未封住不能作为强启动通过。
- return_5/10/20、MA、V3/5/10/20 不应大面积为0。
- close < MA5 不能标记 MA5_SUPPORT。
- 候选必须输出 `key_support_price`、支撑区间和交易计划。
- `risk_reward_ratio_2 < 1.5` 不进入候选。
- 放量下跌必须排除。
- 策略6候选只写入 `strategy6_candidates`。
- 策略6 task_id 访问其他策略候选接口返回 `TASK_STRATEGY_MISMATCH`。

前端测试：

- 策略6结果页能展示候选。
- 扫描按钮调用策略6 API。
- 配置页能展示和保存 `strategy6` 段。

验证命令：

```bash
python -m pytest tests/test_strategy6_*.py -q
python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py --ignore=tests/test_yfinance_hist.py
python -m compileall strategy6 scanner server.py -q
npm --prefix web test -- --run
npm --prefix web run build
```

## 11. 风险和约束

- 策略6字段较多，数据库迁移必须兼容旧库，使用 `_ensure_column()`。
- `PRAGMA table_info` 列名必须用 `d[1]`。
- 扫描任务状态仍以 `scan_tasks/task_stocks` 为事实来源。
- 不得复用策略5候选表或修改策略5规则。
- 不得为了候选数量放宽：放量下跌、支撑失败、无新高确认、RR2<1.5。
- 市场/板块过滤在一期为可解释字段，不得假装已经接入真实板块K线。


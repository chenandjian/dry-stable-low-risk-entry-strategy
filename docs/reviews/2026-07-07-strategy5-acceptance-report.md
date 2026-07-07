# 策略5验收报告

## 检查范围

- 策略5核心规则：配置、指标、F1-F11、支撑状态、三级分类、四维评分。
- 策略5扫描链路：`stock_pool + fetch_with_retry + daily_ohlc + task_stocks`。
- 数据库与 API：`strategy5_candidates` 独立表，策略5扫描/任务/候选接口。
- 前端：扫描入口、任务中心、配置页、策略5结果页。
- 本地 DB 最小验证：只读 `data/cuphandle.db`，不拉取外部行情。

## 总体结论

策略5已作为独立策略接入，不修改策略1、策略2、策略3、策略4的判断逻辑。当前实现保留原有行情链路，不引入 westock、westock-mcp、外部 JSON 流水线或 yfinance。

## 已验证结果

| 验证项 | 命令 | 结果 |
|---|---|---|
| 策略5专项后端 | `python -m pytest tests/test_strategy5_validation.py tests/test_strategy5_core_rules.py tests/test_strategy5_db_api.py tests/test_strategy5_scanner.py tests/test_strategy5_backtester.py -q` | 14 passed |
| Python 编译 | `python -m compileall scanner strategy2 strategy3 strategy4 strategy5 server.py -q` | 通过 |
| 后端回归 | `python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py` | 831 passed |
| 前端策略5页 | `npm.cmd --prefix web test -- Strategy5Results --run` | 1 passed |
| 前端全量 | `npm.cmd --prefix web test -- --run` | 14 files / 62 tests passed |
| 前端构建 | `npm.cmd --prefix web run build` | 通过 |

## 本地 DB 验证

命令：

```bash
python -m strategy5.backtester --db data/cuphandle.db --limit 300
```

结果摘要：

- 数据源：`daily_ohlc`
- 股票数：300
- 已评估：283
- 数据缺失：17
- 候选：0
- 拒绝原因：
  - `TRADING_DAYS_LE_1000`: 283
  - `NO_DAILY_OHLC`: 17

解释：当前本地缓存日线覆盖约 2024-03-27 到 2026-07-03，不满足策略5文档要求的 `trading_days > 1000` 硬过滤，因此零候选是符合规则的结果，不是扫描异常。

## 验收重点

- 策略5核心入口为 `strategy5.engine.ShortSprintSupportEngine.evaluate_at()`。
- 策略5候选独立写入 `strategy5_candidates`。
- 策略5任务类型为 `STRATEGY_5_SHORT_SPRINT_SUPPORT`。
- 策略5扫描器复用 `fetch_with_retry()`，三源失败写入 `task_stocks.status='failed'`。
- 策略5本地验证只读 `daily_ohlc`，不发起外部行情请求。
- 前端可以从扫描页启动策略5，可以在任务中心识别 S5，可以在策略5结果页查看 KEY/WATCH 分层。

## 残余风险

1. 当前真实本地数据长度不足 1000 个交易日，无法产生真实策略5候选样本；需要更长历史日线后再做候选质量评估。
2. 策略5暂未实现失败股票重试专用接口，失败股票已进入统一失败列表；后续如需一键重试，可按策略3模式补 `retry-failed`。
3. 策略5没有改变定时串行扫描流程；如后续希望定时扫描也包含策略5，需要单独设计调度顺序。

## 中高等级问题结论

本轮验收未发现中/高等级问题。低风险残余项均不影响策略5作为独立策略上线和人工验证。

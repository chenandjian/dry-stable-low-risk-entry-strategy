# 策略3本地 DB 回测闭环实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:test-driven-development 开发，使用 superpowers:verification-before-completion 验证。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 为策略3「强势回踩二次启动」建立可信的本地 DB 回测闭环，并以回测统计支持后续策略3参数调优。

**实施状态（2026-06-30）：** 已按本计划完成策略3本地 DB 回测闭环、数据驱动参数收紧和长区间回测验证。最终调优结论与可信回测任务见 `docs/superpowers/reports/2026-06-30-strategy3-local-backtest-and-tuning-report.md`。下方复选框保留为原始执行计划，不作为当前完成状态来源。

**架构：** 新增策略3专用回测模型、纯计算模块、任务执行服务和 SQLite 表；回测只读 `stock_pool` / `daily_ohlc`，通过 `StrongPullbackSecondBreakoutEngine.evaluate_at()` 逐日回放信号，使用 `NEXT_OPEN` 执行模型，保存原始信号、机会、执行结果、未入场原因和分组统计。不复用策略2回测表，不修改策略1/2核心逻辑。

**技术栈：** Python dataclass + pytest + SQLite 兼容迁移 + 本地 OHLC 数据。

---

## 文件结构

- 创建：`strategy3/backtest_models.py`
  - 定义 `Strategy3BacktestSignal`、`Strategy3BacktestOpportunity`、`Strategy3BacktestSummary`、`Strategy3HorizonPerformance`。
- 创建：`strategy3/backtester.py`
  - 纯计算函数：`calculate_strategy3_execution_outcome()`、`calculate_strategy3_horizon_performance()`、`merge_strategy3_signals()`、`run_strategy3_stock_backtest()`、`aggregate_strategy3_backtest_summary()`。
- 创建：`strategy3/backtest_service.py`
  - 任务级本地 DB 执行服务：读取股票池与日线，保存逐股结果，最终生成可信汇总。
- 创建：`strategy3/version.py`
  - 保存策略3回测引擎版本和策略引擎版本，防止旧任务混用新实现。
- 修改：`scanner/db.py`
  - 新增策略3回测表：`strategy3_backtest_tasks`、`strategy3_backtest_task_stocks`、`strategy3_backtest_signals`、`strategy3_backtest_opportunities`、`strategy3_backtest_insufficient_stocks`。
  - 新增原子替换、汇总、完整性校验和查询函数。
- 创建：`tests/test_strategy3_backtester.py`
  - TDD 覆盖执行模型、机会合并、未来函数、分组统计和策略隔离。
- 创建：`tests/test_strategy3_backtest_db.py`
  - TDD 覆盖 DB 表、原子替换、幂等、完整性校验、只写策略3回测表。
- 后续可选：`server.py`
  - 首阶段不新增前端页面；如需要只增加轻量内部 API，不作为本计划第一批验收必需。

---

## 任务 1：纯执行模型和机会合并

**文件：**

- 创建：`tests/test_strategy3_backtester.py`
- 创建：`strategy3/backtest_models.py`
- 创建：`strategy3/backtester.py`

- [ ] **步骤 1：编写失败测试，验证 NEXT_OPEN 入场**

```python
def test_strategy3_next_open_entry_uses_next_trading_day_open():
    opp = Strategy3BacktestOpportunity(
        code="000001",
        first_detected_date="2026-01-02",
        stop_loss=9.5,
        target_price=11.0,
    )
    rows = [
        {"date": "2026-01-02", "open": 10, "high": 10.2, "low": 9.9, "close": 10, "volume": 1000},
        {"date": "2026-01-05", "open": 10.1, "high": 10.5, "low": 10.0, "close": 10.3, "volume": 1000},
    ]
    calculate_strategy3_execution_outcome(opp, rows, {"2026-01-02": 0, "2026-01-05": 1})
    assert opp.execution_model == "NEXT_OPEN"
    assert opp.entry_date == "2026-01-05"
    assert opp.entry_price == 10.1
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/test_strategy3_backtester.py::test_strategy3_next_open_entry_uses_next_trading_day_open -q`

预期：导入失败或函数不存在。

- [ ] **步骤 3：实现最小模型和 NEXT_OPEN 函数**

实现 `Strategy3BacktestOpportunity` 和 `calculate_strategy3_execution_outcome()`，只使用传入 OHLC，不访问 DB/网络。

- [ ] **步骤 4：验证止损优先**

新增测试：同一交易日 high 到目标且 low 到止损时，`exit_reason == "STOP"`。

- [ ] **步骤 5：验证未入场原因**

新增测试：

- 次日开盘低于止损：`NO_ENTRY_GAP_BELOW_STOP`
- 次日开盘过高超过目标附近：`NO_ENTRY_GAP_TOO_HIGH`
- 没有次日数据：`UNOBSERVED_ENTRY`

- [ ] **步骤 6：验证机会合并**

新增测试：同一股票两个信号之间少于 10 个有效未命中交易日合并，达到 10 个有效未命中交易日拆分。

---

## 任务 2：逐股历史回放和未来函数防护

**文件：**

- 修改：`tests/test_strategy3_backtester.py`
- 修改：`strategy3/backtester.py`

- [ ] **步骤 1：编写失败测试，验证评估日不会看到未来数据**

使用 fake engine 记录传入 `history[-1]["date"]`，确保每个评估点只传入 `<= evaluation_date` 的数据。

- [ ] **步骤 2：实现 `run_strategy3_stock_backtest()`**

函数签名：

```python
def run_strategy3_stock_backtest(
    code: str,
    name: str,
    ohlc_data: list[dict],
    config_snapshot: dict,
    start_date: str,
    end_date: str,
    *,
    engine_factory=None,
) -> dict:
    ...
```

核心规则：

- `minimum_required_days` 来自 `strategy3.minimum_required_days`。
- `strategy_window_days` 来自 `strategy3.strategy_window_days`。
- 每个评估日构造 `history = ohlc_data[:i]`，再截取最近 `strategy_window_days`。
- 使用 `StrongPullbackSecondBreakoutEngine.evaluate_at(history, code, name)`。
- `evaluation.passed` 生成 `Strategy3BacktestSignal`。
- 未通过时记录稳定结果类型：`INSUFFICIENT_DATA`、`LIQUIDITY_FILTERED`、`TREND_REJECTED`、`SETUP_REJECTED`、`VOLUME_REJECTED`、`SECOND_BREAKOUT_REJECTED`、`RISK_REJECTED`、`SCORE_BELOW_THRESHOLD`、`TRADE_QUALITY_REJECTED`、`EVALUATION_ERROR`。

- [ ] **步骤 3：验证 raw signal 可追溯**

断言每个 signal 保存：

- `evaluation_date`
- `evaluation_index`
- `total_score`
- 五个模块分
- `trade_state`
- `trade_quality_score`
- `support_price`
- `stop_loss`
- `target_price`
- `risk_ratio`
- `rr1`
- `evaluation_snapshot`

---

## 任务 3：策略3回测 DB 持久化

**文件：**

- 创建：`tests/test_strategy3_backtest_db.py`
- 修改：`scanner/db.py`

- [ ] **步骤 1：编写失败测试，验证策略3回测表存在且独立**

运行 `db.init_db(tmp_db)` 后查询表：

- `strategy3_backtest_tasks`
- `strategy3_backtest_task_stocks`
- `strategy3_backtest_signals`
- `strategy3_backtest_opportunities`
- `strategy3_backtest_insufficient_stocks`

并断言不写入 `strategy2_backtest_*`。

- [ ] **步骤 2：实现兼容迁移**

在 `_init_db()` 中调用 `_ensure_strategy3_backtest_tables(conn)`，用 `_ensure_column()` 增量添加字段。

- [ ] **步骤 3：编写失败测试，验证单股结果原子替换且幂等**

调用 `replace_strategy3_stock_backtest_result()` 两次，断言 signals/opportunities 数量不重复。

- [ ] **步骤 4：实现保存函数**

新增函数：

- `create_strategy3_backtest_task()`
- `save_strategy3_backtest_task_stock()`
- `replace_strategy3_stock_backtest_result()`
- `build_strategy3_backtest_summary()`
- `validate_strategy3_backtest_integrity()`
- `get_strategy3_backtest_opportunities()`

---

## 任务 4：任务级服务和本地数据只读

**文件：**

- 创建：`strategy3/backtest_service.py`
- 修改：`tests/test_strategy3_backtest_db.py`

- [ ] **步骤 1：编写失败测试，禁止外部数据源**

monkeypatch `scanner.daily_data_service.fetch_with_retry`、`scanner.sina_source.fetch_sina_daily` 等为抛错，运行策略3回测服务，预期不触发这些函数。

- [ ] **步骤 2：实现 `run_strategy3_backtest_task()`**

输入：

- `task_id`
- `target_stocks`
- `config_snapshot`
- `payload_snapshot`
- `data_snapshot_date`
- `cancel_event`
- `running_state`

行为：

- 只通过 `db.get_ohlc(code)` 读取本地 OHLC。
- 根据 `data_snapshot_date` 截断数据。
- 每只股票先写 `RUNNING`，完成后写 `COMPLETED` / `INSUFFICIENT` / `FAILED`。
- 单股结果用 `replace_strategy3_stock_backtest_result()` 原子替换。
- 任务汇总从 DB 明细生成，不依赖内存计数。

---

## 任务 5：分组统计和数据驱动调优报告

**文件：**

- 修改：`strategy3/backtester.py`
- 修改：`scanner/db.py`
- 创建：`docs/reviews/YYYY-MM-DD-strategy3-backtest-tuning-report.md`

- [ ] **步骤 1：实现 `aggregate_strategy3_backtest_summary()`**

汇总维度：

- 总分区间：`75-79`、`80-84`、`85-89`、`90+`
- 趋势分区间
- 回踩幅度区间：`<10%`、`10-15%`、`15-22%`、`22-30%`
- 缩量企稳分区间
- 二次转强分区间
- 风险比区间：`<=4%`、`4-6%`、`6-8%`、`>8%`
- RR1 区间：`<1.5`、`1.5-2`、`2-3`、`>=3`
- 交易状态：`LOW_ABSORB`、`WATCH`、`WAIT_BREAKOUT`
- 月份：`YYYY-MM`
- 失败原因/未入场原因

- [ ] **步骤 2：运行本地 DB 策略3回测**

默认范围先用本地数据的可用区间，建议第一轮：

- `startDate = 2026-03-01`
- `endDate = 2026-06-29`
- `maxStocks = 全部`

只读 `data/cuphandle.db`。

- [ ] **步骤 3：形成调优结论**

规则：

- 样本数过低的分组只标为观察，不直接调参。
- 只根据显著更优/更差分组提出策略3参数变更。
- 不为了增加候选数放宽风控。
- 任何调参必须说明对候选数量、止损率、目标率、收益均值/中位数的影响。

---

## 任务 6：必要规则修改和回归验证

**文件：**

- 仅在回测数据支持时修改：`strategy3/validation.py`、`strategy3/trend.py`、`strategy3/pullback.py`、`strategy3/volume_stability.py`、`strategy3/second_breakout.py`、`strategy3/risk.py`、`strategy3/trade_quality.py`
- 修改对应测试

- [ ] **步骤 1：基于回测报告选择调参点**

仅允许改策略3自身阈值、评分权重、否决规则和解释字段。

- [ ] **步骤 2：先写失败测试**

每个调参点必须有测试展示预期行为变化。

- [ ] **步骤 3：最小实现并回归**

运行：

```bash
python -m pytest tests/test_strategy3_backtester.py tests/test_strategy3_backtest_db.py tests/test_strategy3_engine.py tests/test_strategy3_independence.py -q
python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py --ignore=tests/test_yfinance_hist.py
python -m compileall scanner strategy2 strategy3 server.py -q
```

---

## 自检清单

- [ ] 策略3回测只读本地 DB，不访问外部行情源。
- [ ] 回测通过 `StrongPullbackSecondBreakoutEngine.evaluate_at()`，不重复实现策略判断。
- [ ] 每个信号保存评估快照，能追溯入选原因。
- [ ] 每个机会保存 first/last signal、入场、止损、目标、退出原因、未入场原因。
- [ ] `NEXT_OPEN` 使用信号日下一交易日 open。
- [ ] 同日目标和止损同时触发时止损优先。
- [ ] 机会合并使用 10 个有效未命中交易日。
- [ ] 汇总从 DB 明细生成。
- [ ] 策略1、策略2核心逻辑不修改。
- [ ] 调参结论来自回测分组统计，不根据单个样本拍脑袋。

# 策略4 Phase 2 回测与参数优化实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:executing-plans 或在当前会话中按 TDD 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 为策略4「热点龙头二波」新增严格无未来泄漏的历史回测、参数实验和优化报告能力。

**架构：** 新增 `strategy4/backtester.py` 与 `strategy4/backtest_models.py`，只读任务快照、真实指数缓存和本地日线数据。历史热点/龙头缺失时标记 `UNOBSERVED`，不使用当前热点倒推历史；参数实验基于可观测快照评估，证据不足时不强行升级正式参数。

**技术栈：** Python dataclass、SQLite 只读查询、现有 `HotLeaderSecondWaveEngine`、`PriceLimitResolver`、pytest、Markdown 报告。

---

## 文件结构

- 创建：`strategy4/backtest_models.py`
  - 定义回测信号、机会、执行结果、实验结果和汇总模型。
- 创建：`strategy4/backtester.py`
  - 读取历史策略4快照、截断日线、评估策略4信号、执行 NEXT_OPEN 模型、运行参数实验、生成 Markdown 报告。
- 创建：`tests/test_strategy4_backtester.py`
  - 覆盖不可观察快照、涨停不可成交、参数实验过滤和无未来泄漏。
- 创建：`docs/reviews/2026-07-01-strategy4-phase2-backtest-optimization-report.md`
  - 真实数据回测与参数实验报告。
- 创建：`docs/superpowers/specs/2026-07-01-strategy4-optimized-official-parameters.md`
  - 策略4优化后正式参数文档；若证据不足，写明暂不升级正式参数和后续数据积累条件。
- 修改：`strategy4/__init__.py`
  - 如有必要，导出回测公共入口。
- 谨慎：`strategy4/config.py`
  - 只有在测试与报告证明需要接入正式扫描参数时，才新增 `min_locked_attention_score` 等配置；否则保持扫描默认参数不变。

## 任务 1：不可观察历史快照

- [ ] **步骤 1：编写失败测试**

在 `tests/test_strategy4_backtester.py` 中新增：

```python
def test_strategy4_backtest_marks_missing_snapshot_unobserved(tmp_path):
    db.init_db(str(tmp_path / "test.db"))
    db.save_ohlc("300750", make_daily_rows("2026-06-01", [10, 11, 12, 13, 14, 15]))

    result = run_strategy4_snapshot_backtest(
        db_path=str(tmp_path / "test.db"),
        start_date="2026-06-10",
        end_date="2026-06-10",
        config_snapshot={"strategy4": {}},
    )

    assert result.summary.unobserved_snapshot_days == 1
    assert result.signals == []
    assert result.unobserved[0].reason_code == "UNOBSERVED_TOPIC_SNAPSHOT"
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/test_strategy4_backtester.py::test_strategy4_backtest_marks_missing_snapshot_unobserved -q`

预期：FAIL，原因是 `strategy4.backtester` 尚不存在。

- [ ] **步骤 3：实现最小模型和快照查询**

实现 `Strategy4UnobservedDay`、`Strategy4BacktestSummary`、`Strategy4BacktestResult` 和 `run_strategy4_snapshot_backtest()`，当评估日没有 `strategy4_hot_topics.snapshot_time <= 当日收盘` 的任务快照时记录 `UNOBSERVED_TOPIC_SNAPSHOT`。

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest tests/test_strategy4_backtester.py::test_strategy4_backtest_marks_missing_snapshot_unobserved -q`

预期：PASS。

## 任务 2：NEXT_OPEN 和涨停不可成交

- [ ] **步骤 1：编写失败测试**

```python
def test_strategy4_execution_rejects_one_word_limit_up_entry(tmp_path):
    db.init_db(str(tmp_path / "test.db"))
    rows = make_buyable_rows_with_next_day_limit_up()
    db.save_ohlc("300750", rows)
    seed_strategy4_snapshot(tmp_path, task_id="s4-snap", date="2026-06-20", code="300750")

    result = run_strategy4_snapshot_backtest(
        db_path=str(tmp_path / "test.db"),
        start_date="2026-06-20",
        end_date="2026-06-20",
        config_snapshot={"strategy4": {"min_leader_strength_score": 60}},
    )

    opp = result.opportunities[0]
    assert opp.execution_model == "NEXT_OPEN"
    assert opp.exit_reason == "NO_ENTRY_LIMIT_UP_UNBUYABLE"
    assert opp.entry_price == 0
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/test_strategy4_backtester.py::test_strategy4_execution_rejects_one_word_limit_up_entry -q`

预期：FAIL，执行模型尚未实现。

- [ ] **步骤 3：实现执行模型**

在 `calculate_strategy4_execution_outcome()` 中：

- 信号日为评估日 T。
- 入场日为 T+1 的开盘价。
- 如果 T+1 无数据，标记 `UNOBSERVED_ENTRY`。
- 如果 T+1 为一字涨停或开盘接近涨停且无法合理成交，标记 `NO_ENTRY_LIMIT_UP_UNBUYABLE`。
- 如果开盘低于止损，标记 `NO_ENTRY_GAP_BELOW_STOP`。
- 后续观察目标/止损，无法完整观察时使用 `UNOBSERVED` 或 `UNRESOLVED`。

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest tests/test_strategy4_backtester.py::test_strategy4_execution_rejects_one_word_limit_up_entry -q`

预期：PASS。

## 任务 3：参数实验只使用可观测快照

- [ ] **步骤 1：编写失败测试**

```python
def test_strategy4_parameter_experiments_filter_observed_snapshots_only(tmp_path):
    db.init_db(str(tmp_path / "test.db"))
    db.save_ohlc("300750", make_buyable_rows())
    seed_strategy4_snapshot(tmp_path, task_id="s4-snap", date="2026-06-20", code="300750", hot_score=92, leader_score=91)

    experiments = run_strategy4_parameter_experiments(
        db_path=str(tmp_path / "test.db"),
        start_date="2026-06-20",
        end_date="2026-06-21",
        base_config={"strategy4": {}},
        experiment_grid=[
            {"name": "strict", "min_hot_topic_score": 95, "min_leader_strength_score": 95},
            {"name": "baseline", "min_hot_topic_score": 85, "min_leader_strength_score": 88},
        ],
    )

    assert experiments["strict"].summary.total_opportunities == 0
    assert experiments["baseline"].summary.unobserved_snapshot_days == 1
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/test_strategy4_backtester.py::test_strategy4_parameter_experiments_filter_observed_snapshots_only -q`

预期：FAIL，参数实验尚未实现。

- [ ] **步骤 3：实现参数实验**

实现 `run_strategy4_parameter_experiments()`：

- 每组参数深拷贝基础配置后覆盖 `strategy4`。
- 只比较已存在且时间不晚于评估日的热点/龙头快照。
- `hot_topic_top_n` 对排序后的可观测热点生效。
- `min_hot_topic_score`、`min_leader_strength_score`、`min_first_wave_return_*`、`pullback_min/max`、`min_reward_risk_ratio`、`max_risk_ratio` 对策略评估生效。
- `locked_attention_score` 在实验报告中作为锁仓题材/龙头的过滤阈值，不反向修改历史快照。

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest tests/test_strategy4_backtester.py::test_strategy4_parameter_experiments_filter_observed_snapshots_only -q`

预期：PASS。

## 任务 4：真实数据报告

- [ ] **步骤 1：运行真实数据实验**

运行一个只读脚本或模块入口，对 `data/cuphandle.db` 执行：

```bash
python -m strategy4.backtester --db data/cuphandle.db --start 2026-07-01 --end 2026-07-01 --report docs/reviews/2026-07-01-strategy4-phase2-backtest-optimization-report.md
```

- [ ] **步骤 2：生成报告**

报告必须包含：

- 数据覆盖：`daily_ohlc`、`market_index_ohlc`、`strategy4_hot_topics`、`strategy4_leaders`。
- 可观察天数与 `UNOBSERVED` 天数。
- 基线参数表现。
- 参数实验表。
- 最佳参数组合。
- 优化前后对比。
- 失效场景。
- 过拟合风险。
- 是否足以作为正式参数。

- [ ] **步骤 3：生成正式参数文档**

创建 `docs/superpowers/specs/2026-07-01-strategy4-optimized-official-parameters.md`，写明：

- 推荐参数。
- 推荐依据。
- 未采用参数。
- 何时重新优化。
- 如果证据不足，明确“暂不修改生产默认参数”。

## 任务 5：验收和提交

- [ ] **步骤 1：运行专项测试**

```bash
python -m pytest tests/test_strategy4_* -q
python -m compileall strategy4 scanner server.py -q
```

- [ ] **步骤 2：审核中高风险**

检查：

- 无未来泄漏。
- 无伪造历史热点。
- 不修改策略1/2/3判断入口。
- `UNOBSERVED` 不按 0 收益统计。
- 涨停不可成交不算已入场。
- 报告结论不夸大证据。

- [ ] **步骤 3：提交**

```bash
git add strategy4/backtester.py strategy4/backtest_models.py tests/test_strategy4_backtester.py docs/reviews/2026-07-01-strategy4-phase2-backtest-optimization-report.md docs/superpowers/specs/2026-07-01-strategy4-optimized-official-parameters.md docs/superpowers/plans/2026-07-01-strategy4-phase2-backtest-optimization.md
git commit -m "feat: add strategy4 phase2 backtest optimization"
```

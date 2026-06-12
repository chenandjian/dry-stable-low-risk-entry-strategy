# 策略2 Phase 1 复查与任务 `s2bt-20260612-220015-qmr54h` 分析

## 1. 检查范围

- 当前提交：`cd78cc2`
- 上轮审核基线：`b23d254`
- 新回测任务：`s2bt-20260612-220015-qmr54h`
- 对照任务：`s2bt-20260612-155934-n35sdk`
- 重点文件：
  - `server.py`
  - `scanner/db.py`
  - `strategy2/backtester.py`
  - `web/src/pages/Strategy2Backtest.vue`
  - `tests/test_strategy2_backtester.py`
- 本报告只记录中、高等级问题。

---

## 2. 总体结论

本轮修复已确认通过：

- 单股信号、机会、终态使用事务原子替换。
- 重跑同一股票不会产生重复信号和机会。
- 669 个机会的 `first_signal_id`、`last_signal_id` 全部成功关联。
- 完整 3/5/10/20 日汇总已经生成，不再是空对象。
- 任务详情接口返回解析后的 `summary`。
- 前端 ScannerConsole 测试由 2 项失败修复为 25 项全部通过。
- 任务开始、结束时间已统一为 UTC，墙钟耗时约 210 秒，与
  `elapsed_seconds=206.8` 基本一致。

但 Phase 1 仍不能最终验收，剩余问题集中在：

1. 完整性校验执行顺序错误，且任务观察截止日期未聚合，导致完整任务也必然被降级。
2. 3/5/10/20 日汇总的收益口径错误，前后端字段也不匹配。
3. 回测恢复、失败重试和取消仍是占位或无效实现。
4. 数据快照没有真正冻结或强制执行，相同快照标签的任务结果不可复现。
5. 逐股审计元数据和实时处理进度仍不完整。

---

## 3. 问题清单

| 编号 | 问题 | 严重程度 | 影响范围 | 必须修复 |
|---|---|---:|---|---|
| RECHECK-001 | 完整性校验时机错误，观察截止日期未聚合 | 高 | 可信状态、任务验收 | 是 |
| RECHECK-002 | 周期汇总收益口径错误且前后端字段不匹配 | 高 | 回测统计、策略判断、前端展示 | 是 |
| RECHECK-003 | `resume/retry-failed/cancel` 仍未实现真实行为 | 高 | 任务可靠性、恢复与取消 | 是 |
| RECHECK-004 | `data_snapshot_date` 未真正冻结和约束输入数据 | 高 | 可重复性、任务对比、可信基线 | 是 |
| RECHECK-005 | 逐股审计字段和实时进度仍不完整 | 中 | 问题定位、运行进度、审计 | 是 |

---

## 4. 已确认通过

### 4.1 原子持久化和关联

新任务数据：

| 项目 | 数量 |
|---|---:|
| `task_stocks` | 5527 |
| 原始信号 | 1373 |
| 机会 | 669 |
| 缺少 `first_signal_id` | 0 |
| 缺少 `last_signal_id` | 0 |
| 重复信号 | 0 |
| 重复机会 | 0 |
| 信号数量差值 | 0 |
| 机会数量差值 | 0 |

### 4.2 退出字段

- `TARGET`：253 条。
- `STOP`：373 条。
- 目标和止损记录均有真实 `exit_date`、`exit_price`。

### 4.3 测试和构建

| 验证项 | 结果 |
|---|---|
| 策略2专项测试 | 26 passed |
| 前端 Vitest | 25 passed |
| 前端构建 | 通过 |
| Python 编译检查 | 通过 |
| 后端测试 | 508 passed，1 个外部 yfinance 429 失败 |

外部 yfinance 429 属于网络诊断测试失败，不是本轮策略2代码回归。

---

## 5. 详细问题分析

### RECHECK-001：完整性校验时机错误，观察截止日期未聚合

#### 问题现象

新任务最终状态：

```text
status = completed
credibility_status = PHASE1_INCOMPLETE
observation_data_end_date = NULL
```

任务汇总记录的完整性错误：

```json
{
  "errors": [
    "processed 0 != total 5527",
    "missing observation_data_end_date",
    "missing summary_json"
  ]
}
```

但任务最终数据库值实际为：

```text
processed_stocks = 5527
summary_json != NULL
```

#### 根因

`server.py` 在写入最终任务字段前调用完整性校验：

```python
summary = db.build_strategy2_backtest_summary(task_id)
integrity_ok, integrity_errors = db.validate_strategy2_backtest_integrity(task_id)
...
db.update_strategy2_backtest_task(
    processed_stocks=total,
    summary_json=summary_json,
)
```

因此校验读取到的仍是运行中的旧状态：

- `processed_stocks=0`
- `summary_json=NULL`

同时，虽然逐股表已经保存了 `observation_data_end_date`，任务结束聚合 SQL
没有查询和写入该字段。

新任务逐股数据中：

```text
MAX(task_stocks.observation_data_end_date) = 2026-06-12
```

任务表中却仍是 `NULL`。

#### 影响

- 当前所有完整全市场任务都无法成为 `TRUSTED_BASELINE`。
- 完整性错误包含已经不存在的旧错误，误导用户和修复人员。
- 前端无法展示未来观察数据截止日期。

#### 一次性修复方案

将完成流程改为明确的两阶段最终化：

```python
def finalize_strategy2_backtest_task(task_id: str, runtime_stats: dict) -> None:
    # 1. 从 task_stocks 和明细表聚合全部最终字段
    aggregates = db.aggregate_strategy2_backtest_task(task_id)

    # 2. 生成完整 summary，但此时先不写 integrity
    summary = db.build_strategy2_backtest_summary(task_id)

    # 3. 先写任务最终数据和 summary_json
    db.update_strategy2_backtest_task(
        task_id,
        processed_stocks=aggregates["terminal_stocks"],
        actual_evaluation_start_date=aggregates["actual_eval_start"],
        actual_evaluation_end_date=aggregates["actual_eval_end"],
        observation_data_end_date=aggregates["observation_data_end"],
        completed_evaluations=aggregates["evaluation_days"],
        raw_signals_count=aggregates["raw_signals_count"],
        evaluation_error_days=aggregates["evaluation_error_days"],
        summary_json=json.dumps(summary, ensure_ascii=False),
        ...
    )

    # 4. 再对数据库最终状态执行完整性校验
    integrity_ok, integrity_errors = db.validate_strategy2_backtest_integrity(task_id)

    # 5. 将校验结果写回 summary 和 credibility_status
    summary["integrity"] = {
        "passed": integrity_ok,
        "errors": integrity_errors,
    }
    db.update_strategy2_backtest_task(
        task_id,
        credibility_status="TRUSTED_BASELINE" if integrity_ok else "PHASE1_INCOMPLETE",
        summary_json=json.dumps(summary, ensure_ascii=False),
    )
```

聚合 SQL 至少包含：

```sql
SELECT
  COUNT(*) AS total,
  SUM(status IN ('COMPLETED','INSUFFICIENT','FAILED')) AS terminal_stocks,
  MIN(actual_eval_start_date),
  MAX(actual_eval_end_date),
  MAX(observation_data_end_date),
  SUM(evaluation_days),
  SUM(evaluation_error_days),
  SUM(raw_signals_count),
  SUM(opportunities_count)
FROM strategy2_backtest_task_stocks
WHERE task_id=?;
```

#### 必须新增的测试

1. 构造完整任务并运行最终化函数，最终必须成为 `TRUSTED_BASELINE`。
2. 校验结果不得包含最终化前的旧状态错误。
3. 任务 `observation_data_end_date` 等于逐股表最大观察日期。
4. 删除一个周期汇总后，任务必须成为 `PHASE1_INCOMPLETE`。

---

### RECHECK-002：周期汇总收益口径错误且前后端字段不匹配

#### 问题现象

后端每个周期生成：

```text
avg_realized_return
median_realized_return
avg_holding_days
```

前端实际读取：

```text
avg_end_return
avg_max_upside
avg_max_drawdown
```

因此前端短线表现表中的平均收益、最大上涨、最大回撤仍显示 `--`。

更重要的是，后端周期汇总把整笔交易最终的 `opportunity.realized_return`
当作 3/5/10/20 日周期收益：

```python
results["realized_returns"].append(o.get("realized_return") or 0)
```

这不是对应周期 `horizon_N.end_return`。

#### 直接证据

股票 `600566`：

```text
3日 end_return = -0.1911%
3日 result = UNRESOLVED
最终 exit_reason = TARGET
最终 realized_return = +5.00%
```

这笔机会在 3 日周期内没有成功，但最终整笔交易止盈。周期统计不能使用最终
`+5%` 替代 3 日表现。

数据库按真实 `horizon_N.end_return` 重新计算：

| 周期 | 观察样本 | 成功 | 失败 | 未决 | 正确平均期末收益 |
|---|---:|---:|---:|---:|---:|
| 3日 | 628 | 88 | 115 | 425 | +0.1675% |
| 5日 | 628 | 142 | 162 | 324 | +0.0721% |
| 10日 | 628 | 220 | 280 | 128 | -0.5809% |
| 20日 | 628 | 248 | 353 | 27 | -3.4466% |

#### 其他统计错误

执行汇总使用：

```python
realized_returns = [
    o["realized_return"] for o in opps
    if o.get("realized_return") != 0
]
```

这会排除已经入场但收益为 0 的未决样本。新任务：

- 后端汇总平均收益：`-0.4084%`
- 628 个实际入场样本真实平均收益：`-0.4071%`

#### 影响

- 前端周期收益字段为空。
- 后端周期统计含义错误，不能用于判断策略持有 3/5/10/20 日的效果。
- 策略优化可能基于错误收益口径。

#### 一次性修复方案

`build_strategy2_backtest_summary()` 必须拆分两套统计：

#### 周期观察统计

每个周期只能使用对应 `horizon_N` JSON：

```python
horizon_end_returns.append(horizon["end_return"])
horizon_max_upsides.append(horizon["max_upside"])
horizon_max_drawdowns.append(horizon["max_drawdown"])
```

输出字段必须与前端一致：

```json
{
  "observed": 628,
  "unobserved": 41,
  "success": 88,
  "failed": 115,
  "unresolved": 425,
  "target_hit_rate": 14.01,
  "stop_hit_rate": 18.31,
  "unresolved_rate": 67.68,
  "decisive_win_rate": 43.35,
  "avg_end_return": 0.001675,
  "median_end_return": 0.001212,
  "avg_max_upside": 0.0,
  "median_max_upside": 0.0,
  "avg_max_drawdown": 0.0,
  "median_max_drawdown": 0.0,
  "avg_days_to_target": null,
  "avg_days_to_stop": null
}
```

#### 整笔交易执行统计

只能使用机会执行字段：

```text
entry_price
exit_reason
realized_return
holding_days
```

实际入场样本全部纳入平均收益，包括 `realized_return=0`：

```python
entered_opps = [o for o in opps if o["entry_price"] > 0]
realized_returns = [o["realized_return"] or 0 for o in entered_opps]
```

同时补齐设计文档要求的：

- 平均和中位收益。
- 正收益比例。
- 盈亏比。
- 期望值。
- 平均持有天数。

删除 `build_strategy2_backtest_summary()` 中重复执行的第一段周期循环。

#### 必须新增的测试

1. 构造“3日未决、20日后止盈”的机会，3日统计不得使用最终 `+5%`。
2. 前后端字段契约测试必须验证 `avg_end_return`、
   `avg_max_upside`、`avg_max_drawdown` 存在。
3. 实际入场但收益为 0 的机会必须计入执行平均收益分母。
4. 使用新任务数据库样本验证 3 日平均期末收益约为 `0.001675`。

---

### RECHECK-003：`resume/retry-failed/cancel` 仍未实现真实行为

#### 问题现象

当前接口仍然返回：

```text
resume_not_implemented
retry_not_implemented
```

取消接口只修改内存标记和任务状态，工作线程不检查取消信号，仍会继续执行并在结束时
覆盖取消状态。

#### 影响

- 服务重启后的中断任务无法恢复。
- 失败股票无法重试。
- 用户无法真正取消长任务。
- 原子持久化能力没有被任务恢复流程使用。

#### 一次性修复方案

按上轮文档方案提取统一任务执行器，禁止为恢复和重试复制新循环：

```python
run_strategy2_backtest_task(
    task_id,
    target_codes,
    config_snapshot,
    payload_snapshot,
    cancel_event,
    mode,
)
```

实现要求：

- `cancel` 设置 `threading.Event`，工作线程每只股票开始前检查。
- 工作线程确认取消后写 `canceled`，不得继续最终化为 `completed`。
- `resume` 仅执行 `PENDING` 股票，使用原任务配置和数据快照。
- `retry-failed` 仅执行 `FAILED` 股票。
- 恢复或重试完成后重新生成汇总并运行完整性校验。
- 重复调用恢复或重试必须返回 409。

必须新增行为级测试，不能只断言接口返回字符串。

---

### RECHECK-004：`data_snapshot_date` 未真正冻结和约束输入数据

#### 问题现象

两个任务配置快照哈希完全一致：

```text
79079394745f03ea0150b3c95d59ba9ffbf4ecb0109e3d685611f16c7adca860
```

两者 `data_snapshot_date` 都是 `2026-06-12`，但结果发生明显变化：

| 指标 | 15:59任务 | 22:00任务 |
|---|---:|---:|
| 原始信号 | 1389 | 1373 |
| 机会 | 679 | 669 |
| 有机会股票 | 605 | 599 |
| 实际评估开始 | 2025-11-28 | 2025-12-11 |

进一步对比：

- 旧任务独有信号：69 条。
- 新任务独有信号：53 条。
- 4850 只股票的真实评估区间或评估日数发生变化。

当前回测直接读取当时的 `daily_ohlc` 全量内容，未按任务
`data_snapshot_date` 过滤，也没有记录数据版本。

#### 影响

- 同配置、同快照标签任务无法复现。
- 无法判断策略变化还是数据变化导致结果变化。
- 恢复任务时可能读取任务创建后新增的数据。
- `TRUSTED_BASELINE` 无法用于可靠对照实验。

#### 一次性修复方案

最低要求：

1. 创建任务时保存精确快照时间，而不是只有日期。
2. 调用单股回测前过滤：

```python
ohlc = [row for row in db.get_ohlc(code) if row["date"] <= data_snapshot_date]
```

3. 恢复和重试必须继续使用原任务 `data_snapshot_date`。
4. 每只股票记录：
   - `available_days`
   - 实际读取最早日期
   - 实际读取最晚日期
   - 数据内容摘要或版本号
5. 任务开始和结束时检查数据版本；版本变化时任务不得标记可信。

推荐增加轻量数据版本表：

```sql
CREATE TABLE data_revisions (
  revision_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  row_count INTEGER NOT NULL,
  max_trade_date TEXT,
  content_fingerprint TEXT NOT NULL
);
```

任务保存 `data_revision_id`。至少用各股票
`code + count + min(date) + max(date) + max(updated_at)` 形成稳定摘要。

报告中必须明确披露：若日线历史行会被重新前复权覆盖，仅冻结日期仍不足以保证完全
可复现，需要版本化数据或任务级数据快照。

#### 必须新增的测试

1. 创建任务后插入快照日期之后的数据，任务结果不得变化。
2. 恢复任务时不得读取原快照日期之后的数据。
3. 相同配置与相同数据版本运行两次，信号和机会集合必须完全一致。
4. 数据版本变化时不得标记 `TRUSTED_BASELINE`。

---

### RECHECK-005：逐股审计字段和实时进度仍不完整

#### 问题现象

新任务：

```text
5527 / 5527 task_stocks.started_at 为空
5527 / 5527 task_stocks.finished_at 为空
4293 条 COMPLETED 股票 available_days = 0
```

成功股票没有返回真实 `available_days`，原子写入函数错误地回退为信号数量：

```python
available_days = len(result["signals"])
```

因此无信号的成功股票被记录为 0 天数据。

此外，运行时 `processed_stocks=i+1` 只在 `COMPLETED` 路径执行；
`INSUFFICIENT` 和 `FAILED` 路径提前 `continue`，实时进度会少算。
新任务有 635 只数据不足股票，运行末期进度可能停留在低于总数的位置。

#### 影响

- 无法审计每只股票实际使用的数据量和执行耗时。
- 实时进度与真实处理数量不一致。
- 数据快照一致性无法验证。

#### 修复方案

1. `run_strategy2_stock_backtest()` 的成功结果必须返回：

```python
"available_days": len(ohlc_data),
"required_days": min_required,
"earliest_date": ohlc_data[0]["date"],
"latest_date": ohlc_data[-1]["date"],
```

2. 删除以信号数量代替可用数据天数的回退逻辑。
3. 股票进入 `RUNNING` 时写 `started_at`。
4. 股票进入任何终态时写 `finished_at`。
5. 将进度更新放入每只股票循环的 `finally`，确保所有终态都增加处理数。
6. 最终任务 `processed_stocks` 应从终态股票数量聚合，而不是直接强制写 `total`。

---

## 6. 新回测任务分析

### 6.1 数据概览

| 指标 | 数值 |
|---|---:|
| 总股票 | 5527 |
| 完成股票 | 4892 |
| 数据不足 | 635 |
| 失败股票 | 0 |
| 原始信号 | 1373 |
| 有机会股票 | 599 |
| 总机会 | 669 |
| 实际入场 | 628 |
| 未入场 | 41 |
| 止盈 | 253 |
| 止损 | 373 |
| 未决 | 2 |

### 6.2 执行收益

按全部 628 个实际入场样本计算：

```text
止盈率：40.29%
平均已实现收益：-0.4071%
```

与上一轮任务相比：

- 上一轮平均收益：`-0.3191%`
- 新任务平均收益：`-0.4071%`

结果进一步变差。当前尚未计入手续费、印花税和滑点。

### 6.3 月度表现

| 入场月份 | 入场数 | 止盈 | 止损 | 未决 | 平均收益 |
|---|---:|---:|---:|---:|---:|
| 2026-01 | 65 | 17 | 48 | 0 | -1.6713% |
| 2026-02 | 376 | 186 | 190 | 0 | +0.3081% |
| 2026-03 | 80 | 11 | 69 | 0 | -2.3250% |
| 2026-04 | 104 | 37 | 65 | 2 | -0.8021% |
| 2026-05 | 3 | 2 | 1 | 0 | +2.1871% |

结论：

- 仅 2026 年 2 月的大样本月份为正。
- 2026 年 1、3、4 月均为负。
- 3 月止盈率仅 13.75%，明显失效。
- 当前策略仍没有表现出跨月份稳定盈利能力。

### 6.4 周期观察表现

按 `horizon_N.end_return` 正确计算：

| 周期 | 平均期末收益 | 中位期末收益 |
|---|---:|---:|
| 3日 | +0.1675% | +0.1212% |
| 5日 | +0.0721% | -0.0328% |
| 10日 | -0.5809% | -1.1518% |
| 20日 | -3.4466% | -4.3482% |

该结果显示信号在 3 日内有轻微正向表现，但随着持有期延长迅速恶化。
在汇总口径修复后，可以优先研究更短持有期和更严格退出方案，但在 Phase 1
可信度闭环完成前，不建议直接修改正式策略规则。

---

## 7. 建议修复顺序

1. 修复 RECHECK-002，确保汇总统计口径正确。
2. 修复 RECHECK-001，建立正确的任务最终化和可信度校验顺序。
3. 修复 RECHECK-005，补齐逐股数据和真实进度。
4. 修复 RECHECK-004，强制执行数据快照约束和版本检查。
5. 实现 RECHECK-003 的恢复、重试和取消。
6. 跑两次相同数据版本的全市场回测，验证结果完全一致。

---

## 8. 给修复 AI 的提示语

```text
请严格按照：
docs/reviews/2026-06-12-strategy2-phase1-recheck-and-task-220015-analysis.md
完成修复。

本轮目标是完成策略2 Phase 1 最终可信闭环。不得保留 TODO、占位接口或只修改测试
绕过生产问题。

必须完成：

1. 修复周期汇总口径：horizon 统计只能读取对应 horizon_N JSON，前后端字段必须一致。
2. 建立两阶段任务最终化：先写最终聚合和 summary，再执行完整性校验，最后写可信状态。
3. 聚合并保存 observation_data_end_date。
4. 成功股票保存真实 available_days、required_days、最早和最晚数据日期。
5. 所有逐股终态保存 started_at、finished_at，所有终态都更新实时进度。
6. data_snapshot_date 必须限制回测和恢复可读取的数据，增加数据版本或一致性检查。
7. 实现真实 resume、retry-failed、cancel 行为，不接受占位返回。
8. 保持已有单股原子替换和信号ID关联，不得回退。
9. 不要修改策略评分阈值、趋势规则、信号规则和 NEXT_OPEN 执行模型。
10. 修复后新增行为级测试，并跑两次相同数据版本的全市场回测验证结果一致。

交付时提供：

- 每个 RECHECK 问题对应的修改说明。
- 修改文件清单。
- 新增测试清单和真实测试结果。
- 两个相同快照、相同配置任务的 ID。
- 两个任务信号集合、机会集合的差值，必须均为 0。
- 新任务完整性校验结果和可信状态。
```

---

## 9. 回归测试清单

```bash
python -m pytest tests/test_strategy2_backtester.py tests/test_strategy2_independence.py -v
python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py --ignore=tests/test_yfinance_hist.py
python -m compileall scanner strategy2 server.py -q
cd web
npm.cmd test -- --run
npm.cmd run build
```

必须新增测试：

- 完整任务最终化后成为可信基线。
- 完整性校验不读取旧任务状态。
- 周期收益使用 `horizon_N.end_return`。
- 前后端汇总字段契约一致。
- 0 收益实际入场样本计入执行平均收益。
- 数据快照后新增数据不影响任务。
- 相同数据版本任务结果完全一致。
- 取消真实停止线程。
- 恢复只执行待处理股票。
- 重试只执行失败股票。
- 所有逐股终态均有审计时间和真实数据天数。

---

## 10. 最终验收 SQL

```sql
SELECT
  id, status, credibility_status,
  total_stocks, processed_stocks,
  observation_data_end_date,
  summary_json
FROM strategy2_backtest_tasks
WHERE id='<TASK_ID>';
```

```sql
SELECT
  COUNT(*) total,
  SUM(started_at IS NULL) missing_start,
  SUM(finished_at IS NULL) missing_finish,
  SUM(status='COMPLETED' AND available_days<=0) invalid_available_days,
  SUM(status='COMPLETED' AND required_days<=0) invalid_required_days
FROM strategy2_backtest_task_stocks
WHERE task_id='<TASK_ID>';
```

```sql
SELECT
  COUNT(*) total,
  SUM(first_signal_id IS NULL) missing_first_signal,
  SUM(last_signal_id IS NULL) missing_last_signal
FROM strategy2_backtest_opportunities
WHERE task_id='<TASK_ID>';
```

两个同配置、同数据版本任务必须满足：

```sql
-- 旧任务独有信号和新任务独有信号都必须为 0
SELECT COUNT(*)
FROM strategy2_backtest_signals a
WHERE a.task_id='<TASK_A>'
AND NOT EXISTS (
  SELECT 1 FROM strategy2_backtest_signals b
  WHERE b.task_id='<TASK_B>'
    AND b.code=a.code
    AND b.evaluation_date=a.evaluation_date
);
```

---

## 11. 不建议修改

- 不要为了让任务成为可信基线而删除完整性检查。
- 不要把最终交易收益继续当作周期期末收益。
- 不要修改策略2评分和过滤阈值。
- 不要通过修改前端字段名掩盖后端统计缺失。
- 不要在恢复时使用最新配置或最新数据快照。
- 不要通过强制写 `processed_stocks=total` 掩盖未完成股票。

---

## 12. 最终交付标准

1. 周期统计含义和前端展示正确。
2. 完整任务可以通过完整性校验并成为可信基线。
3. 不完整任务不能成为可信基线。
4. 相同配置、相同数据版本任务结果完全可复现。
5. 取消、恢复、失败重试真实可用。
6. 逐股审计和实时进度完整。
7. 后端、前端测试全部通过。


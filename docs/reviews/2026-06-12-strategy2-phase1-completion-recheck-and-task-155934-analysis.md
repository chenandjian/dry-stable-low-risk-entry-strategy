# 策略2 Phase 1 完成度复查与新回测分析

## 1. 检查范围

- 工作树：`strategy2-extreme-dry-stable`
- 当前提交：`b23d254`
- 对比起点：`c9493d3`
- 设计文档：`docs/superpowers/specs/2026-06-12-strategy2-backtest-correctness-and-strategy-optimization-design.md`
- 本轮重点修改：
  - `server.py`
  - `scanner/db.py`
  - `strategy2/backtester.py`
  - `web/src/pages/Strategy2Backtest.vue`
  - `tests/test_strategy2_backtester.py`
- 实际回测任务：`s2bt-20260612-155934-n35sdk`
- 本报告仅记录中、高等级问题，不记录低等级问题。

---

## 2. 总体结论

本轮已经完成以下关键修复：

- 新任务创建了完整的 `strategy2_backtest_task_stocks`，数量与股票池一致。
- 原始信号、机会数和逐股汇总数量能够互相对账。
- 止盈和止损机会已经保存真实 `exit_date`、`exit_price`。
- 信号拆分结果稳定，新任务与上一轮任务均产生 1389 个信号、679 个机会。
- 后端专项测试和后端全量离线测试通过。

但当前仍不能将 Phase 1 判定为最终完成，主要原因是：

1. 任务在完整性条件不满足时仍被标记为 `TRUSTED_BASELINE`。
2. 汇总统计实际为空，前端也无法读取 `summary_json`。
3. `resume`、`retry-failed` 是占位接口，`cancel` 不会停止工作线程。
4. 单只股票结果不是事务写入，恢复或重试时仍可能形成部分数据或重复数据。
5. 逐股审计字段、信号关联和任务时间字段仍不完整。

建议本轮按本文第 6 节顺序一次完成，不要继续用“先返回接口占位状态、后续再实现”的方式拆分。

---

## 3. 问题清单

| 编号 | 问题 | 严重程度 | 影响范围 | 是否必须修复 |
|---|---|---:|---|---|
| FINAL-001 | 空汇总和缺失观察区间仍被标记为可信基线 | 高 | 回测可信度、前端汇总、策略判断 | 是 |
| FINAL-002 | 恢复、重试、取消接口没有形成真实任务控制闭环 | 高 | 中断恢复、人工取消、失败重试 | 是 |
| FINAL-003 | 单股持久化非事务化且机会未关联原始信号 | 高 | 数据一致性、幂等恢复、审计追踪 | 是 |
| FINAL-004 | 任务和逐股审计元数据不完整，时间口径混用 | 中 | 任务审计、问题定位、耗时展示 | 是 |
| FINAL-005 | 前端全量测试仍有 2 项失败 | 中 | 仓库验收、扫描终态展示 | 是 |

---

## 4. 已确认通过的内容

### 4.1 数据数量闭环

任务 `s2bt-20260612-155934-n35sdk`：

| 指标 | 数量 |
|---|---:|
| 总股票 | 5527 |
| `task_stocks` | 5527 |
| 完成股票 | 4889 |
| 数据不足股票 | 638 |
| 失败股票 | 0 |
| 原始信号 | 1389 |
| 机会 | 679 |
| 有机会股票 | 605 |

逐股汇总与明细表对账结果：

- `SUM(task_stocks.raw_signals_count) = signals COUNT(*) = 1389`
- `SUM(task_stocks.opportunities_count) = opportunities COUNT(*) = 679`
- 未发现任务内重复信号。
- 未发现任务内重复机会。

### 4.2 执行退出字段

- `TARGET`：265 条。
- `STOP`：374 条。
- 上述 639 条记录的 `exit_date` 和 `exit_price` 均已填写。
- 未发现真实止盈或止损记录缺少退出字段。

### 4.3 回测结果稳定性

上一轮任务 `s2bt-20260612-145513-dc0yw2` 与新任务的关键结果一致：

| 指标 | 上一轮 | 新任务 |
|---|---:|---:|
| 原始信号 | 1389 | 1389 |
| 机会 | 679 | 679 |
| 有机会股票 | 605 | 605 |
| 数据不足股票 | 638 | 638 |

这说明本轮任务状态和退出字段修复没有改变信号识别结果。

---

## 5. 详细问题分析

### FINAL-001：空汇总和缺失观察区间仍被标记为可信基线

#### 问题现象

新任务状态为：

```text
status = completed
credibility_status = TRUSTED_BASELINE
observation_data_end_date = NULL
summary_json.horizon_stats = {}
```

前端无法展示 3、5、10、20 日表现，因为任务详情接口返回原始
`summary_json` 字符串，而前端只读取 `task.summary.horizon_stats` 或
`task.horizon_stats`。

#### 涉及模块

- `server.py:1378`
- `server.py:1507`
- `server.py:1510`
- `server.py:1517`
- `server.py:1571`
- `web/src/pages/Strategy2Backtest.vue:157-159`

#### 代码证据

当前汇总使用空机会列表生成，然后主动清空统计：

```python
summary = aggregate_backtest_summary([], total, total_eval_days, 0, 0)
if all_db_opps:
    summary.total_opportunities = len(all_db_opps)
    summary.horizon_stats = {}  # simplified for now
```

可信状态只检查：

```python
failed_count == 0 and actual_eval_start and summary_json
```

`summary_json` 即使只有空对象也是真值，所以空汇总仍会成为可信基线。
任务启动时还会提前写入 `TRUSTED_BASELINE`。

#### 影响

- 用户看不到设计文档要求的 3、5、10、20 日成功率和收益统计。
- 不完整任务被错误标记为可信，后续策略优化可能基于错误前提。
- `observation_data_end_date` 为空，无法证明未来观察数据使用到哪里。
- 当前任务不能作为正式策略优化的可信基线。

#### 一次性修复方案

1. 任务创建时将可信状态设为 `RUNNING_UNVERIFIED`，禁止提前写
   `TRUSTED_BASELINE`。
2. 新增统一的数据库汇总函数，例如：

```python
def build_strategy2_backtest_summary(task_id: str) -> dict:
    """从数据库完整明细生成汇总，不接受分页结果。"""
```

3. 该函数必须查询任务全部机会并解析：

```text
horizon_3
horizon_5
horizon_10
horizon_20
realized_return
mark_to_market_end_return
exit_reason
holding_days
```

4. 汇总至少包含：

```json
{
  "horizon_stats": {
    "3": {},
    "5": {},
    "10": {},
    "20": {}
  },
  "execution_stats": {
    "opportunities": 679,
    "entered": 641,
    "target": 265,
    "stop": 374,
    "unresolved": 2,
    "not_entered": 38,
    "target_hit_rate": 0.4134165,
    "avg_realized_return": -0.0031909
  },
  "funnel": {},
  "integrity": {}
}
```

5. 在单股回测结果中返回 `observation_data_end_date`，并保存到
   `task_stocks`；任务结束时取所有股票的最大值写入任务表。
6. 任务详情接口必须解析 `summary_json` 并返回：

```python
task["summary"] = json.loads(task["summary_json"]) if task["summary_json"] else None
```

7. 新增唯一可信度校验函数：

```python
def validate_strategy2_backtest_integrity(task_id: str) -> tuple[bool, list[str]]:
    ...
```

校验必须覆盖：

- `task_stocks COUNT(*) == total_stocks`
- 不存在 `PENDING` 或 `RUNNING`
- `processed_stocks == total_stocks`
- 任务信号数与逐股信号数一致
- 任务机会数与逐股机会数一致
- `summary.horizon_stats` 包含 `3/5/10/20`
- `observation_data_end_date` 不为空
- `evaluation_error_days == 0`
- `failed_stocks_count == 0`

只有全部通过后才能写 `TRUSTED_BASELINE`；否则写
`PHASE1_INCOMPLETE`，并将失败原因保存到汇总的 `integrity.errors`。

#### 验证方式

1. 新建完整全市场任务。
2. 验证 `summary_json.horizon_stats` 包含 4 个周期且不是空对象。
3. 验证详情接口返回解析后的 `summary`。
4. 验证前端显示 3、5、10、20 日统计。
5. 人工将一条 `task_stock` 改为 `PENDING`，完整性校验必须拒绝
   `TRUSTED_BASELINE`。
6. 人工清空 `observation_data_end_date`，完整性校验必须拒绝可信状态。

---

### FINAL-002：恢复、重试、取消接口没有形成真实任务控制闭环

#### 问题现象

- `resume` 返回 `resume_not_implemented`。
- `retry-failed` 返回 `retry_not_implemented`。
- `cancel` 只修改全局状态和数据库状态。
- 实际工作线程的股票循环不检查取消信号，会继续处理剩余股票，并可能在最后把
  `CANCELED` 覆盖成 `completed`。

#### 涉及模块

- `server.py:1416`
- `server.py:1647`
- `server.py:1651`
- `server.py:1669`

#### 影响

- 服务重启后的 `INTERRUPTED` 任务无法继续。
- 用户点击取消后任务仍在后台运行和写数据库。
- 失败股票无法按原配置快照重试。
- 当前实现不满足设计文档中任务可靠性要求。

#### 一次性修复方案

不要分别复制三套循环。先把当前线程内部函数提取为统一执行器：

```python
def run_strategy2_backtest_task(
    task_id: str,
    stock_codes: list[str],
    config: dict,
    payload: dict,
    cancel_event: threading.Event,
    mode: str,
) -> None:
    ...
```

任务控制状态使用带锁的结构，至少保存：

```python
{
    "task_id": str | None,
    "thread": threading.Thread | None,
    "cancel_event": threading.Event | None,
}
```

每只股票开始前检查：

```python
if cancel_event.is_set():
    mark_remaining_pending_or_canceled(...)
    finish_task_as_canceled(...)
    return
```

各接口行为：

#### `cancel`

- 只允许取消当前运行任务。
- 设置 `cancel_event`。
- 不要立即清空当前任务控制信息。
- 工作线程确认取消并完成数据库状态收尾后，再清空控制信息。
- 最终状态必须保持 `canceled`，不能被完成逻辑覆盖。

#### `resume`

- 只允许恢复 `interrupted` 状态任务。
- 使用原任务的 `config_snapshot`、请求日期、范围和执行模型。
- 仅调度 `PENDING` 股票。
- 将遗留 `RUNNING` 股票先恢复为 `PENDING`。
- 已完成股票不得重复执行。

#### `retry-failed`

- 只调度 `FAILED` 股票。
- 重试前使用事务删除该股票的旧部分结果，再重新写入。
- 成功后重新生成任务汇总和可信度。
- 任务状态应根据最终失败数量变为 `completed` 或
  `completed_with_errors`。

#### 验证方式

必须新增真实行为测试，不允许只断言 HTTP 返回 200：

1. 启动 3 股票任务，在第一只后取消。
2. 等待工作线程退出。
3. 验证任务状态为 `canceled`，且剩余股票没有继续完成。
4. 构造 `interrupted` 任务，验证恢复只执行 `PENDING` 股票。
5. 构造 1 条 `FAILED` 股票，验证重试只执行该股票。
6. 连续调用两次恢复，第二次必须返回 409，且不会产生重复结果。

---

### FINAL-003：单股持久化非事务化且机会未关联原始信号

#### 问题现象

当前每条信号、每条机会和逐股终态分别提交：

- `scanner/db.py:1338`
- `scanner/db.py:1383`
- `scanner/db.py:1413`

如果进程在写入中途退出，可能出现：

- 已写部分信号但未写机会。
- 已写机会但逐股状态仍为 `RUNNING`。
- 重试时机会唯一约束冲突。
- 逐股统计与明细表不一致。

新任务 679 条机会的 `first_signal_id` 和 `last_signal_id` 全部为空，
因此机会无法追踪到组成它的原始信号。

#### 影响

- 恢复和重试不具备可靠幂等性。
- 服务崩溃时可能留下部分结果。
- 无法解释一个机会由哪些信号组成。
- 即使 FINAL-002 实现恢复接口，仍可能破坏任务数据。

#### 一次性修复方案

新增单股原子替换函数，并让任务执行器只调用该函数：

```python
def replace_strategy2_stock_backtest_result(
    task_id: str,
    code: str,
    result: dict,
) -> None:
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "DELETE FROM strategy2_backtest_opportunities WHERE task_id=? AND code=?",
            (task_id, code),
        )
        conn.execute(
            "DELETE FROM strategy2_backtest_signals WHERE task_id=? AND code=?",
            (task_id, code),
        )

        signal_id_by_date = insert_signals_without_commit(conn, task_id, result["signals"])
        insert_opportunities_without_commit(
            conn,
            task_id,
            result["opportunities"],
            signal_id_by_date,
        )
        update_task_stock_without_commit(conn, task_id, code, result)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
```

写机会时，根据机会的首末信号日期设置：

```python
first_signal_id = signal_id_by_date[opp.first_detected_date]
last_signal_id = signal_id_by_date[opp.last_detected_date]
```

要求：

- 底层 `insert_*_without_commit` 不得自行 `commit()`。
- 单股信号、机会和终态必须同一事务提交。
- 数据不足股票也应在单一事务内写 `INSUFFICIENT` 和不足详情。
- 失败股票在单一事务内写 `FAILED` 和错误详情。
- 汇总生成前再次运行数量一致性检查。

#### 验证方式

1. 单股执行完成后，机会首末信号 ID 均非空且属于同一任务、同一股票。
2. 在机会插入过程中注入异常，事务回滚后该股票不得留下部分信号或机会。
3. 对同一股票连续执行两次原子替换，最终明细数量不变。
4. 恢复任务后验证信号和机会不存在重复。

---

### FINAL-004：任务和逐股审计元数据不完整，时间口径混用

#### 问题现象

新任务中：

- 5527 条 `task_stocks.started_at` 全部为空。
- 5527 条 `task_stocks.finished_at` 全部为空。
- 4889 条已完成股票的 `available_days=0`。
- 4889 条已完成股票的 `required_days=0`。
- 任务 `actual_start_date`、`actual_end_date` 为空。
- 任务 `started_at=2026-06-12 07:59:34`，`finished_at=2026-06-12 16:03:09`，
  但 `elapsed_seconds=211.3`。

原因是任务开始时间使用 SQLite `datetime('now')`，该函数返回 UTC；
结束时间使用 Python 本地时间，二者相差 8 小时。

#### 影响

- 用户看到的任务耗时和开始结束时间互相矛盾。
- 无法定位单只股票的执行耗时和卡点。
- 无法审计已完成股票实际拥有多少数据、需要多少数据。

#### 一次性修复方案

1. 全部时间统一为带时区 ISO 8601，推荐 UTC：

```python
datetime.datetime.now(datetime.timezone.utc).isoformat()
```

2. 禁止同一任务混用 SQLite `datetime('now')` 与本地无时区时间。
3. 股票进入 `RUNNING` 时写 `started_at`。
4. 股票进入任意终态时写 `finished_at`。
5. 所有股票均填写 `available_days` 和 `required_days`，不能只在
   `INSUFFICIENT` 时填写。
6. 明确 `actual_start_date`、`actual_end_date` 的兼容含义；若保留字段，
   应写入真实评估区间，或从 API 中移除其展示，避免与
   `actual_evaluation_*` 冲突。
7. 对历史任务不要伪造时间；迁移时保留空值并标记为 legacy。

#### 验证方式

- `finished_at - started_at` 与 `elapsed_seconds` 误差小于 5 秒。
- 所有终态股票的 `started_at`、`finished_at` 非空。
- 所有已完成股票的 `available_days > 0`、`required_days > 0`。

---

### FINAL-005：前端全量测试仍有 2 项失败

#### 问题现象

执行：

```bash
cd web
npm.cmd test -- --run
```

结果：

```text
2 failed, 23 passed
```

失败项：

- `[18] live completion shows final failures and candidates`
- `[23] live failure stock terminal refresh fails — candidates still loaded`

第一项终态仍显示 `processed=80`，没有应用最终 `processed=100` 汇总。
第二项候选 `600001` 没有显示。

#### 涉及模块

- `web/src/pages/ScannerConsole.vue:413`
- `web/src/pages/__tests__/ScannerConsole.history-task.test.js:223`
- `web/src/pages/__tests__/ScannerConsole.history-task.test.js:302`

#### 修复建议

该问题与策略2回测主逻辑独立，但会阻塞仓库全量验收。修复时应先确认测试模拟的
“运行中到终态”转换真实发生：

1. 测试中先返回一次 `running=true`，再由下一次轮询返回
   `running=false`，不要始终返回 `running=true`。
2. 终态刷新时，实时任务也必须从任务详情应用最终 summary；不能只在历史任务路径
   使用 `applySummary=true`。
3. `loadResults()` 和 `loadFailures()` 必须各自执行，单个接口失败不能阻止另一个。
4. 不要为了通过测试删除 stale context 和 poll session 防护。

#### 验证方式

- 25 个 `ScannerConsole.history-task` 测试全部通过。
- 手工验证实时扫描完成后显示最终处理数、候选和失败股票。

---

## 6. 新回测任务分析

### 6.1 任务可信度判断

任务数据数量稳定，真实退出字段完整，适合用于核对执行模型结果。

但由于 `horizon_stats` 为空、观察结束日期为空、信号关联为空，并且可信度校验存在
误判，本任务目前应视为：

```text
PHASE1_INCOMPLETE
```

不应视为最终可信基线。

### 6.2 执行结果

| 指标 | 结果 |
|---|---:|
| 总机会 | 679 |
| 实际入场 | 641 |
| 未入场 | 38 |
| 止盈 | 265 |
| 止损 | 374 |
| 未决 | 2 |
| 止盈率 | 41.34% |
| 平均已实现收益 | -0.3191% |

止盈样本平均收益为 `+5.00%`，止损样本平均收益约为 `-4.09%`。
当前 41.34% 的止盈率不足以覆盖该盈亏结构，因此平均收益为负。

该结果尚未计入交易费用和滑点，真实可执行结果通常会更差。

### 6.3 月度稳定性

| 入场月份 | 入场数 | 平均已实现收益 | 止盈率 |
|---|---:|---:|---:|
| 2026-01 | 73 | -1.3119% | 30.14% |
| 2026-02 | 381 | +0.2851% | 49.34% |
| 2026-03 | 78 | -2.4221% | 12.82% |
| 2026-04 | 106 | -0.3305% | 40.57% |
| 2026-05 | 3 | +2.1863% | 66.67% |

结论：

- 结果高度依赖月份。
- 2026 年 2 月贡献了主要正向表现。
- 2026 年 3 月明显失效。
- 当前策略尚未表现出跨月份稳定盈利能力。

在修完 Phase 1 数据闭环前，不建议直接调整策略阈值。先确保完整汇总、交易统计和
可信度校验正确，再进入 Phase 2 优化实验。

---

## 7. 建议修复顺序

1. 先实现 FINAL-003 的单股原子替换和信号关联。
2. 在原子持久化基础上实现 FINAL-002 的取消、恢复和失败重试。
3. 实现 FINAL-001 的完整数据库汇总和可信度校验。
4. 补齐 FINAL-004 的任务审计字段和统一时间口径。
5. 修复 FINAL-005 的前端测试失败。
6. 新跑一次全市场回测并执行本文验收 SQL。

这个顺序不能颠倒。恢复和重试依赖幂等、事务化的单股持久化；可信度校验又依赖
完整可靠的任务结果。

---

## 8. 给修复 AI 的执行提示语

```text
请严格按照
docs/reviews/2026-06-12-strategy2-phase1-completion-recheck-and-task-155934-analysis.md
完成修复。

目标是一次完成 Phase 1 回测可信度闭环，不允许保留 TODO、占位返回或
“simplified for now”逻辑。

执行要求：

1. 先阅读设计文档和本审核文档，再修改代码。
2. 按 FINAL-003、FINAL-002、FINAL-001、FINAL-004、FINAL-005 的顺序修复。
3. 单只股票的信号、机会、逐股终态必须在同一个数据库事务中原子替换。
4. resume、retry-failed、cancel 必须实现真实行为，不接受只返回状态字符串。
5. 汇总必须从数据库完整明细生成，不允许使用空列表、API分页结果或手工清空
   horizon_stats。
6. 只有完整性校验全部通过后才能写 TRUSTED_BASELINE。
7. 任务详情接口必须返回解析后的 summary，前端必须能展示 3/5/10/20 日汇总。
8. 补齐 observation_data_end_date、信号首末ID、逐股开始结束时间和数据天数。
9. 统一任务时间口径，禁止 UTC 和本地无时区时间混用。
10. 不要修改策略2评分阈值、信号规则、趋势规则或执行模型。
11. 不要重构无关模块，不要修改历史任务结果。
12. 修复后新增行为级测试，不能只测试接口返回码。

完成后请提供：

- 修改文件清单。
- 每个 FINAL 问题对应的修复说明。
- 新增测试说明。
- 全部测试和构建结果。
- 新回测任务 ID。
- 本文第 10 节验收 SQL 的真实输出。
```

---

## 9. 回归测试清单

### 后端

```bash
python -m pytest tests/test_strategy2_backtester.py tests/test_strategy2_independence.py -v
python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py
python -m compileall scanner strategy2 server.py -q
```

新增测试必须覆盖：

- 单股事务中途异常完整回滚。
- 同一股票重复执行结果幂等。
- 机会首末信号 ID 正确。
- 完整 summary 含 4 个周期。
- 不完整任务不能成为可信基线。
- 取消后工作线程停止。
- 中断任务仅恢复未完成股票。
- 失败重试仅执行失败股票。
- 任务详情返回解析后的 summary。

### 前端

```bash
cd web
npm.cmd test -- --run
npm.cmd run build
```

---

## 10. 新任务验收 SQL

将 `<TASK_ID>` 替换为新任务 ID。

```sql
SELECT
  id, status, credibility_status,
  total_stocks, processed_stocks,
  actual_evaluation_start_date,
  actual_evaluation_end_date,
  observation_data_end_date,
  summary_json
FROM strategy2_backtest_tasks
WHERE id='<TASK_ID>';
```

```sql
SELECT status, COUNT(*)
FROM strategy2_backtest_task_stocks
WHERE task_id='<TASK_ID>'
GROUP BY status;
```

```sql
SELECT
  COUNT(*) AS total,
  SUM(first_signal_id IS NULL) AS missing_first_signal,
  SUM(last_signal_id IS NULL) AS missing_last_signal
FROM strategy2_backtest_opportunities
WHERE task_id='<TASK_ID>';
```

```sql
SELECT
  COUNT(*) AS total,
  SUM(started_at IS NULL) AS missing_started_at,
  SUM(finished_at IS NULL) AS missing_finished_at,
  SUM(available_days <= 0) AS invalid_available_days,
  SUM(required_days <= 0) AS invalid_required_days
FROM strategy2_backtest_task_stocks
WHERE task_id='<TASK_ID>';
```

```sql
SELECT
  (SELECT COUNT(*) FROM strategy2_backtest_signals WHERE task_id='<TASK_ID>')
  - COALESCE((SELECT SUM(raw_signals_count) FROM strategy2_backtest_task_stocks
              WHERE task_id='<TASK_ID>'), 0) AS signal_delta,
  (SELECT COUNT(*) FROM strategy2_backtest_opportunities WHERE task_id='<TASK_ID>')
  - COALESCE((SELECT SUM(opportunities_count) FROM strategy2_backtest_task_stocks
              WHERE task_id='<TASK_ID>'), 0) AS opportunity_delta;
```

验收标准：

- `credibility_status=TRUSTED_BASELINE` 时，观察区间和完整汇总必须存在。
- 不存在 `PENDING`、`RUNNING`。
- 信号和机会首末关联完整。
- 逐股审计字段完整。
- `signal_delta=0`。
- `opportunity_delta=0`。

---

## 11. 本轮验证结果

| 验证项 | 结果 |
|---|---|
| 策略2专项测试 | 23 passed |
| 后端离线全量测试 | 506 passed，2 warnings |
| Python 编译检查 | 通过 |
| `git diff --check` | 通过 |
| 前端构建 | 通过 |
| 前端测试 | 23 passed，2 failed |

---

## 12. 不建议修改的内容

- 不要修改策略2评分阈值。
- 不要修改量干、价稳和趋势判断规则。
- 不要修改 `NEXT_OPEN` 执行模型口径。
- 不要为了提高回测收益删除止损样本或未入场样本。
- 不要把恢复、重试实现为新建一个无关联任务。
- 不要删除原始信号表或逐股状态表。
- 不要通过放宽 `TRUSTED_BASELINE` 条件解决可信度问题。

---

## 13. 最终交付标准

修复完成后应同时满足：

1. 新任务完整汇总可在后端和前端查看。
2. 可信状态由统一完整性校验决定。
3. 取消会真实停止任务。
4. 中断任务可恢复，失败股票可重试。
5. 单股结果原子写入且可幂等替换。
6. 每个机会可追踪到首末原始信号。
7. 任务和逐股审计字段完整。
8. 后端、前端全部测试通过。
9. 新全市场回测通过第 10 节全部验收 SQL。


# 策略2 Phase 1 中高级问题复查报告

## 1. 检查范围

- 当前提交：`997d8f8`
- 同时检查当前未提交修改：
  - `scanner/db.py`
  - `server.py`
  - `web/src/pages/Strategy2Backtest.vue`
- 对照上一轮报告：
  `docs/reviews/2026-06-12-strategy2-phase1-recheck-and-task-220015-analysis.md`
- 本报告仅记录中、高等级问题。

---

## 2. 总体结论

上一轮的核心统计错误和任务最终化顺序已经修复：

- 周期汇总改为读取对应 `horizon_N` 数据。
- 前后端周期统计字段已经对齐。
- 两阶段任务最终化已经实现。
- 任务观察截止日期已经参与聚合。
- 数据读取增加了快照日期过滤。
- 取消接口已经使用 `cancel_event` 通知工作线程停止。
- 成功股票能够保存真实 `available_days`。

当前仍有 **3 个高等级问题、2 个中等级问题**。最主要的阻塞项是：

1. 回测恢复和失败重试仍是占位接口。
2. 数据快照只按日期过滤，仍不能保证同日任务可复现。
3. 可信度校验没有校验任务状态，并错误拒绝“完整但零机会”的任务。

因此当前 Phase 1 仍不建议宣布最终完成。

---

## 3. 问题清单

| 编号 | 问题 | 严重程度 | 影响范围 | 必须修复 |
|---|---|---:|---|---|
| MH-001 | `resume` 和 `retry-failed` 仍为占位接口 | 高 | 中断恢复、失败重试、长任务可靠性 | 是 |
| MH-002 | 数据快照仍无法保证同日任务可复现 | 高 | 可信基线、实验对比、恢复任务 | 是 |
| MH-003 | 可信度校验错误处理取消任务和零机会任务 | 高 | 可信状态准确性 | 是 |
| MH-004 | 逐股审计时间和实时进度仍不完整 | 中 | 运行进度、问题定位、审计 | 是 |
| MH-005 | 汇总漏斗和目标/止损耗时统计仍为空 | 中 | 策略问题分析、优化决策 | 是 |

---

## 4. 已确认修复

### 4.1 周期汇总口径

`build_strategy2_backtest_summary()` 已经使用：

```text
horizon_N.end_return
horizon_N.max_upside
horizon_N.max_drawdown
```

不再使用整笔交易最终收益代替周期收益。

### 4.2 两阶段最终化

任务现在先保存最终聚合和汇总，再执行完整性校验，上一轮
`processed_stocks=0`、`summary_json=NULL` 的旧状态误判已经消除。

### 4.3 真实取消信号

取消接口不再直接清空内存状态，而是设置 `cancel_event`，工作线程会在下一只股票开始前
停止。

### 4.4 测试结果

| 验证项 | 结果 |
|---|---|
| 策略2专项测试 | 26 passed |
| 策略2验收相关测试 | 65 passed |
| 后端离线全量测试 | 508 passed，1 warning |
| 前端 Vitest | 25 passed |
| 前端构建 | 通过 |
| Python 编译检查 | 通过 |

---

## 5. 详细问题分析

### MH-001：`resume` 和 `retry-failed` 仍为占位接口

#### 代码证据

`server.py` 当前仍返回：

```python
return {"task_id": task_id, "status": "resume_not_implemented"}
```

```python
return {"task_id": task_id, "status": "retry_not_implemented"}
```

仓库中也没有针对策略2回测恢复、失败重试的行为级测试。

#### 影响

- 服务重启后，中断的全市场回测无法继续。
- 单只股票失败后不能按原任务配置重试。
- 用户只能重新创建完整任务，浪费时间并可能读取不同数据。
- 当前实现不满足 Phase 1 长任务可靠性要求。

#### 一次性修复方案

将当前 `run_backtest()` 提取为统一执行器：

```python
def run_strategy2_backtest_task(
    task_id: str,
    target_stocks: list[dict],
    config_snapshot: dict,
    payload_snapshot: dict,
    data_snapshot_date: str,
    cancel_event: threading.Event,
    mode: str,
) -> None:
    ...
```

三个入口统一调用该执行器：

```text
start        -> 全部 PENDING 股票
resume       -> PENDING + 遗留 RUNNING 股票
retry-failed -> FAILED 股票
```

执行要求：

1. `resume` 只允许 `INTERRUPTED` 或 `CANCELED` 且仍有未完成股票的任务。
2. `retry-failed` 只执行 `FAILED` 股票。
3. 必须使用原任务的 `config_snapshot`、日期范围、执行模型和数据快照。
4. 重试前使用已有单股原子替换逻辑清理旧部分结果。
5. 完成后重新生成任务汇总并运行完整性校验。
6. 同一任务正在运行时，重复恢复或重试返回 HTTP 409。
7. 不要新建另一个无关联任务代替恢复。

#### 验证方式

- 构造 3 只股票的中断任务，恢复后只执行未完成股票。
- 构造 1 只失败股票，重试后只更新该股票。
- 已完成股票的信号和机会数量不得变化。
- 连续调用两次恢复，第二次必须返回 409。

---

### MH-002：数据快照仍无法保证同日任务可复现

#### 代码证据

任务保存精确时间：

```python
data_snapshot_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
```

但实际执行时截断为日期：

```python
snap_date = data_snapshot_date[:10]
ohlc = [d for d in ohlc if d["date"] <= snap_date]
```

`daily_ohlc` 没有任务级版本号或历史版本快照。

#### 触发条件

1. 上午创建回测任务。
2. 当天稍后行情抓取更新、重新前复权或覆盖历史日线。
3. 当天再次执行任务，或恢复上午创建的任务。

两个任务虽然快照日期相同，但会读取不同内容。

#### 影响

- 同配置、同快照日期的结果仍可能不同。
- 无法判断结果变化来自策略还是数据变化。
- 恢复任务可能读取创建任务后被更新的数据。
- 无法将任务稳定用作实验基线。

#### 一次性修复方案

仅过滤日期不足以解决可复现性，至少增加数据版本指纹：

```sql
ALTER TABLE strategy2_backtest_tasks ADD COLUMN data_revision_id TEXT;
```

任务开始时生成并保存：

```text
股票数量
日线总行数
MAX(date)
按股票聚合后的稳定内容指纹
```

最低可接受实现：

```python
def calculate_daily_ohlc_revision(snapshot_date: str) -> str:
    # 对 code、date、open、high、low、close、volume 的稳定排序结果计算 SHA-256
```

任务完成、恢复和重试前重新计算指纹：

- 指纹一致：允许继续。
- 指纹变化：拒绝恢复或将任务标记为 `DATA_REVISION_CHANGED`，禁止成为可信基线。

如果计算全表指纹性能过高，可维护数据导入批次版本号，但必须保证历史数据覆盖时版本号变化。

#### 验证方式

1. 创建任务后修改同一天的一条 OHLC 历史数据。
2. 恢复任务必须拒绝执行或明确标记数据版本变化。
3. 相同配置和相同数据版本连续运行两次，信号和机会集合差值必须均为 0。

---

### MH-003：可信度校验错误处理取消任务和零机会任务

#### 问题 A：取消任务可能成为可信基线

`validate_strategy2_backtest_integrity()` 没有校验任务 `status`。

直接复现：

```text
status = CANCELED
全部股票已经进入终态
其他完整性字段完整
```

校验结果：

```text
(True, [])
```

因此在最后一只股票处理完成与最终化之间触发取消时，任务可能同时出现：

```text
status = CANCELED
credibility_status = TRUSTED_BASELINE
```

#### 问题 B：完整但零机会任务被错误拒绝

`build_strategy2_backtest_summary()` 遇到零机会直接返回空周期：

```python
if not opps:
    return {"horizon_stats": {}, ...}
```

完整性校验随后报告：

```text
missing horizon_stats 3
missing horizon_stats 5
missing horizon_stats 10
missing horizon_stats 20
```

“策略完整执行但没有发现机会”是合法回测结果，不应自动成为不可信任务。

#### 一次性修复方案

可信度校验必须先校验任务状态：

```python
if task["status"] != "completed":
    errors.append(f"task status is {task['status']}, expected completed")
```

`completed_with_errors`、`CANCELED`、`INTERRUPTED`、`FAILED` 均不能成为
`TRUSTED_BASELINE`。

零机会时仍返回结构完整的零值汇总：

```json
{
  "horizon_stats": {
    "3": {"observed": 0, "unobserved": 0, "success": 0, "failed": 0},
    "5": {},
    "10": {},
    "20": {}
  },
  "execution_stats": {
    "opportunities": 0,
    "entered": 0
  }
}
```

零机会不是完整性错误；只有任务流程、数据或异常统计不完整时才是不可信。

#### 验证方式

- 完整零机会任务必须通过完整性校验。
- `CANCELED` 任务即使全部股票已终态，也必须拒绝可信状态。
- `completed_with_errors` 必须拒绝可信状态。

---

### MH-004：逐股审计时间和实时进度仍不完整

#### 问题现象

1. 股票进入 `RUNNING` 时没有写真实 `started_at`。
2. `COMPLETED` 原子替换路径没有写 `finished_at`。
3. 异常和数据不足路径在结束时同时写 `started_at`、`finished_at`，不能反映真实耗时。
4. `NO_LOCAL_DATA` 路径提前 `continue`，没有增加实时
   `processed_stocks`。
5. `NO_LOCAL_DATA` 路径也没有写逐股开始和结束时间。
6. `invalid_data_days` 已由回测器返回，但原子持久化未保存该字段。

#### 影响

- 无法定位慢股票和卡点。
- 实时进度在存在无本地数据股票时会少算。
- 逐股漏斗统计不完整。

#### 修复方案

在每只股票循环使用统一结构：

```python
started_at = now_local()
db.update_task_stock(..., status="RUNNING", started_at=started_at)
try:
    ...
finally:
    _backtest_running["stats"]["processed_stocks"] += 1
```

所有终态统一写 `finished_at`。原子完成写入中补充：

```text
started_at
finished_at
invalid_data_days
earliest_date
latest_date
```

不要在异常结束时伪造 `started_at=finished_at`。

---

### MH-005：汇总漏斗和目标/止损耗时统计仍为空

#### 代码证据

当前汇总仍固定返回：

```python
"funnel": {}
```

周期统计仍固定返回：

```python
"avg_days_to_target": None
"avg_days_to_stop": None
```

但逐股表已有流动性、趋势、分数、风险、异常等统计，`horizon_N` 也已有
`days_to_target`、`days_to_stop`。

#### 影响

- 无法判断策略主要在哪个过滤环节丢失样本。
- 无法分析目标与止损通常需要多少交易日触发。
- Phase 2 参数优化缺少必要依据。

#### 修复方案

从 `task_stocks` 聚合漏斗：

```text
evaluation_days
liquidity_filtered_days
trend_filtered_days
rejection_failed_days
score_failed_days
risk_failed_days
invalid_data_days
evaluation_error_days
raw_signals_count
opportunities_count
```

从每个 `horizon_N` 聚合：

```text
avg_days_to_target
avg_days_to_stop
```

前端至少展示总漏斗；周期触发天数可加入短线表现表或详情说明。

---

## 6. 建议修复顺序

1. 先修复 MH-003，确保可信度状态不会误判。
2. 实现 MH-001 的统一执行器、恢复和失败重试。
3. 修复 MH-002 的数据版本校验，使恢复任务可复现。
4. 补齐 MH-004 的逐股审计和实时进度。
5. 完成 MH-005 的汇总漏斗。
6. 运行两次同配置、同数据版本全市场回测进行最终验收。

---

## 7. 给修复 AI 的提示语

```text
请严格按照：
docs/reviews/2026-06-13-strategy2-phase1-medium-high-recheck.md
完成修复。

本轮仅处理报告中的中、高等级问题，不要修改策略评分、趋势判断、信号规则和
NEXT_OPEN 执行模型。

必须完成：

1. 实现策略2回测 resume 和 retry-failed 的真实行为，禁止保留占位返回。
2. 为任务建立可校验的数据版本；恢复、重试时数据版本变化必须拒绝执行。
3. 完整性校验必须拒绝 CANCELED、INTERRUPTED、FAILED、
   completed_with_errors；完整零机会任务必须可以成为可信基线。
4. 所有逐股终态必须保存真实 started_at、finished_at、数据区间和漏斗字段。
5. 所有终态路径必须正确增加实时 processed_stocks。
6. 汇总必须生成完整 funnel、avg_days_to_target、avg_days_to_stop。
7. 保持现有原子持久化、周期收益统计和两阶段最终化实现。
8. 新增行为级测试，不能只断言接口返回字符串。

交付时提供：

- 每个 MH 问题的修改说明。
- 新增测试及真实测试结果。
- resume、retry-failed、cancel 的行为测试结果。
- 零机会任务和取消任务的可信度测试结果。
- 两个相同数据版本任务的信号与机会集合差值，必须均为 0。
```

---

## 8. 回归测试清单

```bash
python -m pytest tests/test_strategy2_backtester.py tests/test_strategy2_independence.py -v
python -m pytest tests/test_strategy2_acceptance_fixes.py tests/test_strategy2_recheck_fixes.py -v
python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py --ignore=tests/test_yfinance_hist.py
python -m compileall scanner strategy2 server.py -q
cd web
npm.cmd test -- --run
npm.cmd run build
```

必须新增：

- 回测恢复行为测试。
- 失败股票重试行为测试。
- 取消任务不会成为可信基线测试。
- 完整零机会任务通过完整性校验测试。
- 同日数据修改导致数据版本变化测试。
- `NO_LOCAL_DATA` 路径进度和审计测试。
- 汇总漏斗和触发天数统计测试。

---

## 9. 不建议修改

- 不要删除或放宽完整性校验来获得 `TRUSTED_BASELINE`。
- 不要将取消任务改写成普通完成任务。
- 不要在恢复时使用最新配置或未校验的新数据。
- 不要修改策略阈值来提高回测收益。
- 不要删除已有原子持久化和信号关联。

---

## 10. 最终交付标准

1. 恢复、失败重试、取消均真实可用。
2. 数据版本变化可以被检测并阻止不一致恢复。
3. 可信状态准确区分完整、取消、失败和零机会任务。
4. 逐股审计字段和实时进度完整。
5. 汇总漏斗和周期触发耗时完整。
6. 相同配置、相同数据版本任务结果可复现。
7. 后端和前端测试全部通过。


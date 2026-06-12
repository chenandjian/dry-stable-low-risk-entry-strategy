# 策略2 Phase 1 最终修复执行指南

## 1. 文档用途

本文档用于指导修复 AI 完成策略2回测 Phase 1 的剩余修复。

目标不是继续扩展功能，而是把已经实现的信号合并与 NEXT_OPEN 计算完整接入任务、数据库、API 和前端，最终生成可审计、可恢复、可复现的可信基线任务。

本轮只处理 Phase 1，不实施 Phase 2 策略优化，不修改策略2正式选股规则。

---

## 2. 当前状态

### 2.1 已确认正确，禁止回退

以下功能已经通过代码和真实任务验证，修复时不要重写或改变其语义：

| 功能 | 当前状态 |
| --- | --- |
| 使用 `evaluation_index + eval_results` 计算冷却期 | 正确 |
| 中间 9 个计数未命中日不拆分 | 正确 |
| 中间 10 个计数未命中日拆分 | 正确 |
| 原始信号保存 | 正确 |
| NEXT_OPEN 入场日晚于信号日 | 正确 |
| 跳空高开、跳空低开不入场 | 正确 |
| 无实际入场不生成虚假 horizon 收益 | 正确 |
| 显式 `maxStocks=null` 表示全市场 | 正确 |
| 回测股票池只读取本地数据库 | 正确 |
| 旧任务标记 `LEGACY_UNTRUSTED` | 正确 |
| 机会 API 返回真实 total 的基础结构 | 已实现 |

### 2.2 新任务已验证结果

任务：

```text
s2bt-20260612-145513-dc0yw2
```

可信的局部结果：

| 指标 | 数值 |
| --- | ---: |
| 股票池 | 5527 |
| 原始信号 | 1389 |
| 有机会股票 | 605 |
| 合并后机会 | 679 |
| 实际入场 | 641 |
| 未入场 | 38 |
| 重复信号 | 0 |
| 重复机会 | 0 |

`601607` 已正确拆为三次独立机会：

```text
2026-01-08
2026-03-12
2026-04-21
```

### 2.3 当前不可作为可信基线的原因

当前任务虽然被标记为 `TRUSTED_BASELINE`，但仍缺少：

- 每只股票的持久化终态。
- 完整 summary。
- 实际评估区间。
- 观察数据截止日。
- 判断异常统计。
- TARGET/STOP 的退出日期和退出价格。
- 中断恢复和幂等重试。
- 可复现的干净提交。

因此当前任务只能作为“信号合并与 NEXT_OPEN 局部验证任务”，不能作为正式可信基线。

---

## 3. 修复依赖关系

必须按以下顺序修复：

```text
批次 A：形成可复现提交
  ↓
批次 B：完善单股回放结果
  ↓
批次 C：实现单股事务与任务股票状态
  ↓
批次 D：生成任务汇总和可信度判定
  ↓
批次 E：实现恢复、重试、取消
  ↓
批次 F：完善 API 与前端
  ↓
批次 G：完整测试和可信基线回测
```

不要跳过批次 B/C 直接实现前端汇总；没有可靠持久化数据时，前端展示无法可信。

---

## 4. 批次 A：形成可复现提交

### 目标

确保从干净 checkout 的提交可以启动并运行回测，不依赖本地未提交修改。

### 当前问题

当前 HEAD：

```text
c9493d3
```

仍有未提交生产修改：

- `scanner/db.py`
- `web/src/pages/Strategy2Backtest.vue`

其中 `scanner/db.py` 的未提交修改包含运行必需修复：

- 增加 `import json`。
- 修正机会 INSERT placeholder 数量。

### 修改要求

1. 将必要的 `scanner/db.py` 修复纳入提交。
2. 将已完成的前端分页修改纳入提交。
3. 增加覆盖这两个问题的测试：
   - 新数据库保存原始信号。
   - 保存并读取包含全部执行字段的机会。
4. 从干净 worktree 运行测试。

### 完成判据

```text
git status --short
```

除审核文档外无未提交生产代码。

从新提交 checkout 后：

- 可以保存信号。
- 可以保存机会。
- 执行字段 round-trip 一致。

---

## 5. 批次 B：完善单股回放结果

### 目标

让 `run_strategy2_stock_backtest()` 返回任务汇总与交易审计所需的完整单股结果。

### 涉及文件

- `strategy2/backtest_models.py`
- `strategy2/backtester.py`
- `tests/test_strategy2_backtester.py`

### B1：保存真实退出日期和退出价格

#### 当前问题

639 个 TARGET/STOP 机会全部缺少：

```text
exit_date
exit_price
```

#### 修改方式

在 `calculate_execution_outcome()` 遍历未来数据时，不只保存首次触发日序号，还保存触发日记录：

```python
target_hit = {
    "holding_days": i + 1,
    "date": d["date"],
    "price": target_price,
}

stop_hit = {
    "holding_days": i + 1,
    "date": d["date"],
    "price": stop_loss,
}
```

确定退出结果后统一赋值：

```python
opp.exit_reason = selected_reason
opp.exit_date = selected_hit["date"]
opp.exit_price = selected_hit["price"]
opp.holding_days = selected_hit["holding_days"]
opp.realized_return = opp.exit_price / opp.entry_price - 1.0
```

规则：

- TARGET：退出价为目标价。
- STOP：退出价为策略止损价。
- 同日 TARGET 与 STOP：保守选择 STOP。
- UNRESOLVED：不伪造退出日期和退出价格。
- 未入场：不设置退出日期和退出价格。

### B2：返回单股真实评估范围和漏斗

`run_strategy2_stock_backtest()` 返回值新增：

```python
{
    "actual_eval_start_date": str | None,
    "actual_eval_end_date": str | None,
    "observation_data_end_date": str | None,
    "evaluation_days": int,
    "liquidity_filtered_days": int,
    "trend_filtered_days": int,
    "rejection_failed_days": int,
    "score_failed_days": int,
    "risk_failed_days": int,
    "invalid_data_days": int,
    "evaluation_error_days": int,
    "raw_signals_count": int,
    "opportunities_count": int,
    "evaluation_errors": list[dict],
}
```

要求：

- `actual_eval_start_date`：真实调用评估入口的最早日期。
- `actual_eval_end_date`：真实调用评估入口的最晚日期。
- `observation_data_end_date`：未来观察实际使用的最晚日线日期。
- 每类过滤结果分别计数。
- 引擎异常记录代码、日期、异常类型和简化详情。
- 不允许只设置 `EVALUATION_ERROR` 后静默跳过。

### B3：返回机会与原始信号的直接关联

当前机会仅保存 `signal_count`，`first_signal_id` 和 `last_signal_id` 为空。

单股计算阶段可以先保存信号的稳定业务键：

```python
first_signal_date
last_signal_date
```

持久化阶段保存信号后，再解析成真实数据库 ID。

### B 批次测试

必须新增：

- TARGET 保存退出日期和退出价格。
- STOP 保存退出日期和退出价格。
- 同日双触发选择 STOP 并保存正确日期。
- UNRESOLVED 不设置退出字段。
- 实际评估区间正确。
- endDate 后数据仅用于观察，不产生新信号。
- 判断异常被记录和计数。

---

## 6. 批次 C：实现单股事务与任务股票状态

### 目标

确保 5527 只股票中的每一只都有持久化终态，并支持幂等恢复。

### 涉及文件

- `scanner/db.py`
- 建议新增 `strategy2/backtest_service.py`
- `server.py`
- 数据库与集成测试

### C1：任务创建时初始化股票状态

创建任务并解析 `resolved_stocks` 后，批量插入：

```text
PENDING
```

每只股票至少保存：

```text
task_id
code
name
status
```

### C2：统一单股状态机

每只股票只能经历：

```text
PENDING → RUNNING → COMPLETED
                  → INSUFFICIENT
                  → FAILED
```

禁止在循环分支中直接 `continue` 而不写终态。

建议统一执行结构：

```python
mark_running(task_id, stock)
try:
    result = run_stock(...)
    persist_stock_result_transaction(task_id, stock, result)
except Exception as exc:
    mark_failed(task_id, stock, exc)
finally:
    refresh_task_progress(task_id)
```

### C3：单股结果事务

新增 DB 事务函数：

```python
replace_strategy2_backtest_stock_result(
    task_id,
    stock,
    signals,
    opportunities,
    insufficient,
    stock_stats,
)
```

在同一事务中：

1. 删除该任务、该股票旧的 signals。
2. 删除该任务、该股票旧的 opportunities。
3. 删除该任务、该股票旧的 insufficient 记录。
4. 插入新 signals，并取得 ID。
5. 写入 opportunities 与 first/last signal ID。
6. 更新 task_stock 终态与统计。
7. 任一步失败则整体回滚。

### C4：任务进度从数据库聚合

不要以循环下标作为最终真相。

任务进度应从 `strategy2_backtest_task_stocks` 聚合：

```text
total
pending
running
completed
insufficient
failed
processed
completed_evaluations
raw_signals_count
opportunities_count
evaluation_error_days
```

### C 批次测试

- 任务创建后 task_stocks 数量等于股票池数量。
- 所有代码路径最终都有终态。
- 单股事务失败完整回滚。
- 同一股票重跑不会产生重复信号或机会。
- 进度统计与 task_stocks 聚合一致。

---

## 7. 批次 D：生成任务汇总和可信度判定

### 目标

任务完成后生成完整、可审计的任务报告，并根据完整性决定可信度。

### D1：生成任务级范围

从 task_stocks 聚合：

```text
actual_evaluation_start_date = MIN(actual_eval_start_date)
actual_evaluation_end_date = MAX(actual_eval_end_date)
completed_evaluations = SUM(evaluation_days)
evaluation_error_days = SUM(evaluation_error_days)
raw_signals_count = SUM(raw_signals_count)
```

从机会或单股结果聚合：

```text
observation_data_end_date
```

不要继续把请求区间复制为实际区间。

### D2：生成完整 summary

完成前从数据库读取任务全部机会，调用统一汇总服务生成：

```json
{
  "stockStats": {},
  "evaluationFunnel": {},
  "entryStats": {},
  "executionStats": {},
  "horizonStats": {},
  "dateRange": {},
  "integrityChecks": {}
}
```

至少包括：

- 原始信号数。
- 合并机会数。
- 实际入场数。
- 各未入场原因。
- TARGET / STOP / UNRESOLVED。
- 平均与中位 realized return。
- 各 horizon 成功、失败、未决、未观察。
- 每类评估过滤和异常数。
- 实际评估和观察区间。

### D3：完成状态

根据股票状态：

```text
全部完成且无失败 → COMPLETED
存在失败但流程结束 → COMPLETED_WITH_ERRORS
任务级异常 → FAILED
中断 → INTERRUPTED
用户取消 → CANCELED
```

### D4：可信度状态

创建任务时只能使用：

```text
RUNNING_UNVERIFIED
```

任务结束后执行完整性检查：

```python
integrity_checks = {
    "all_stocks_terminal": ...,
    "summary_generated": ...,
    "date_ranges_present": ...,
    "signals_opportunities_consistent": ...,
    "execution_fields_complete": ...,
    "errors_accounted_for": ...,
}
```

只有全部通过，且任务状态为完整完成时，才设置：

```text
TRUSTED_BASELINE
```

否则设置：

```text
PHASE1_INCOMPLETE
```

当前任务 `s2bt-20260612-145513-dc0yw2` 应标记为 `PHASE1_INCOMPLETE`。

### D 批次测试

- 完整任务生成 summary。
- 存在失败股票时为 COMPLETED_WITH_ERRORS。
- 缺少 summary 或 task_stocks 时不能标记 TRUSTED_BASELINE。
- summary 由数据库全量机会生成，不受分页限制。

---

## 8. 批次 E：实现恢复、失败重试和取消

### 目标

使耗时较长的全市场回测可以安全中断和恢复。

### E1：中断恢复

服务启动时：

1. 找到遗留 RUNNING 回测任务。
2. 将 RUNNING 股票恢复为 PENDING。
3. 将任务设置为 INTERRUPTED。
4. 用户可选择恢复，或按产品决定自动恢复。

恢复必须使用：

- 原任务 config snapshot。
- 原任务执行模型。
- 原任务数据 snapshot 日期。
- 原股票范围。

### E2：失败股票重试

```http
POST /api/strategy2/backtests/{taskId}/retry-failed
```

只重算 FAILED 股票，并通过单股事务替换结果。

### E3：取消

```http
POST /api/strategy2/backtests/{taskId}/cancel
```

在股票边界停止；已完成股票保持不变，未开始股票保持 PENDING，任务标记 CANCELED。

### E4：恢复

```http
POST /api/strategy2/backtests/{taskId}/resume
```

只处理 PENDING / FAILED（按参数）股票，不重复处理已完成股票。

### E 批次测试

- 模拟中断并恢复。
- 恢复后无重复结果。
- 重试失败股票不影响其他股票。
- 取消后状态一致。

---

## 9. 批次 F：完善 API 与前端

### F1：任务详情 API

返回解析后的：

```json
{
  "summary": {},
  "requestedRange": {},
  "actualEvaluationRange": {},
  "observationDataEndDate": "",
  "credibilityStatus": "",
  "integrityChecks": {}
}
```

### F2：机会与信号 API

机会 API：

```json
{
  "items": [],
  "total": 679,
  "limit": 100,
  "offset": 0,
  "hasMore": true
}
```

信号 API 支持：

```text
taskId
code
limit
offset
```

单股历史接口返回机会及其信号。

### F3：失败股票 API

支持按状态查询 task_stocks：

```http
GET /api/strategy2/backtests/{taskId}/stocks?status=FAILED
GET /api/strategy2/backtests/{taskId}/stocks?status=INSUFFICIENT
```

### F4：前端展示

必须展示：

- 可信度状态与完整性检查。
- 请求区间、实际评估区间、观察截止日。
- 汇总与漏斗。
- 机会总数和分页。
- 原始信号展开。
- 失败与数据不足股票。
- 恢复、失败重试和取消入口。

修复现有两个失败的 ScannerConsole 前端测试，不得带红灯交付。

---

## 10. 批次 G：最终测试与可信基线

### G1：必须新增的小型集成测试

使用临时 SQLite 数据库：

1. 创建小型股票池与日线。
2. 创建回测任务。
3. 初始化 task_stocks。
4. 生成多次机会和原始信号。
5. 保存完整执行结果。
6. 模拟单股失败。
7. 模拟中断并恢复。
8. 验证无重复。
9. 生成 summary。
10. 通过 API 查询任务、机会、信号和失败股票。

### G2：必须运行的门禁

```bash
python -m pytest tests/test_strategy2_backtester.py -v
python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py

cd web
npm test -- --run
npm run build

cd ..
python -m compileall scanner strategy2 server.py -q
git diff --check
git status --short
```

### G3：重新运行可信基线

使用与旧任务一致的配置：

```text
请求区间：2025-08-01 至 2026-05-01
执行模型：NEXT_OPEN
实验：关闭
股票范围：全市场本地股票池
```

任务完成后必须自动通过完整性检查。

---

## 11. 修复完成后的数据库验收 SQL

将 `<TASK_ID>` 替换为新任务 ID。

### 任务股票完整性

```sql
SELECT status, COUNT(*)
FROM strategy2_backtest_task_stocks
WHERE task_id = '<TASK_ID>'
GROUP BY status;
```

所有股票必须有终态，不能存在 RUNNING。

### 信号与机会一致性

```sql
SELECT COUNT(*)
FROM strategy2_backtest_opportunities o
WHERE o.task_id = '<TASK_ID>'
  AND NOT EXISTS (
    SELECT 1
    FROM strategy2_backtest_signals s
    WHERE s.id IN (o.first_signal_id, o.last_signal_id)
  );
```

结果必须为 0。

### 退出字段完整性

```sql
SELECT COUNT(*)
FROM strategy2_backtest_opportunities
WHERE task_id = '<TASK_ID>'
  AND exit_reason IN ('TARGET', 'STOP')
  AND (
    exit_date IS NULL OR exit_date = ''
    OR exit_price IS NULL OR exit_price <= 0
  );
```

结果必须为 0。

### 无入场机会收益

```sql
SELECT COUNT(*)
FROM strategy2_backtest_opportunities
WHERE task_id = '<TASK_ID>'
  AND exit_reason IN (
    'UNOBSERVED_ENTRY',
    'NO_ENTRY_GAP_BELOW_STOP',
    'NO_ENTRY_ABOVE_BUY_ZONE'
  )
  AND ABS(COALESCE(realized_return, 0)) > 0.0000001;
```

结果必须为 0。

### 任务报告完整性

```sql
SELECT
  credibility_status,
  actual_evaluation_start_date,
  actual_evaluation_end_date,
  observation_data_end_date,
  completed_evaluations,
  raw_signals_count,
  evaluation_error_days,
  summary_json
FROM strategy2_backtest_tasks
WHERE id = '<TASK_ID>';
```

除允许为 0 的异常数外，不得为空。

---

## 12. 给修复 AI 的最终提示语

```text
请严格按照
docs/reviews/2026-06-12-strategy2-phase1-final-fix-execution-guide.md
完成策略2回测 Phase 1 的最终修复。

不要实施 Phase 2，不要修改策略2正式评分、趋势、风险或否决规则。

必须按批次 A → G 顺序执行，每完成一个批次先运行对应测试，再继续下一批。

重点：
1. 保留已经验证正确的信号合并和 NEXT_OPEN 语义。
2. 先形成可从干净 checkout 运行的提交。
3. 补齐 TARGET/STOP 的退出日期与退出价格。
4. 将 task_stocks 真正接入回测循环，单股结果使用事务并支持幂等替换。
5. 任务完成前生成 summary、实际评估区间、观察区间和异常统计。
6. 只有完整性检查全部通过后才能标记 TRUSTED_BASELINE。
7. 实现 interrupted/resume/retry-failed/cancel。
8. 完成 API 和前端展示，并修复所有失败测试。
9. 使用临时 SQLite 数据库增加真实端到端集成测试。
10. 最终重新运行全市场可信基线，并执行文档第11节全部 SQL。

每个批次完成后报告：
- 修改文件。
- 实现内容。
- 对应测试。
- 测试实际结果。
- 尚未完成项。

最终交付时必须提供：
- 干净提交 Hash。
- 新可信基线任务 ID。
- 完整 summary。
- task_stocks 状态汇总。
- 实际评估与观察区间。
- 异常统计。
- 第11节 SQL 的实际结果。
- 601607 抽样结果。
- 全部测试和构建结果。
```

---

## 13. 最终验收标准

只有同时满足以下条件，Phase 1 才能验收：

1. 干净提交可独立运行。
2. 所有股票均有持久化终态。
3. 单股结果写入事务化、可恢复、可幂等重试。
4. summary、实际评估区间、观察区间和异常统计完整。
5. TARGET/STOP 均有退出日期和退出价格。
6. 所有机会可直接追溯到原始信号。
7. 可信度状态由完整性检查决定。
8. API 与前端完整展示可信报告。
9. 前后端所有测试通过。
10. 新全市场任务通过数据库完整性 SQL。

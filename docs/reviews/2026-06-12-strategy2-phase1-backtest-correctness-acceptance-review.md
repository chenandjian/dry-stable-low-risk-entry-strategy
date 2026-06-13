# 代码问题检查报告

## 1. 检查范围

- 开发文档：`docs/superpowers/specs/2026-06-12-strategy2-backtest-correctness-and-strategy-optimization-design.md`
- 本轮范围：仅 Phase 1「策略2回测可信度修复」
- 审核提交：`77ea835 fix(strategy2): Phase 1 backtest correctness — signal merge, NEXT_OPEN execution, external source ban`
- 对比基线：`77ea835^`，即 `66f8f96`
- 重点模块：
  - `strategy2/backtest_models.py`
  - `strategy2/backtester.py`
  - `scanner/db.py`
  - `server.py`
  - `web/src/pages/Strategy2Backtest.vue`
  - `tests/test_strategy2_backtester.py`
- 按要求过滤低等级问题，仅记录中、高等级问题。

---

## 2. 总体结论

本轮验收不通过。

已确认正确的部分：

- 信号合并已改用 `evaluation_index + eval_results`。
- 9 个计数未命中日不拆分、10 个计数未命中日拆分的纯函数测试通过。
- 回测股票池主路径使用本地 `db.get_stock_pool()`。
- 已增加 NEXT_OPEN 纯计算函数的基本框架。

但提交只完成了部分纯计算代码，Phase 1 的真实任务链路尚未完成。当前存在多个会直接破坏回测可信度或让真实任务失败的问题：

- 新数据库没有创建原始信号表，出现命中信号后真实任务会失败。
- NEXT_OPEN、实际收益和信号追溯字段没有保存到数据库。
- 无实际入场的机会仍会按信号日收盘价生成虚假收益。
- 完整汇总、真实评估区间、观察区间、异常漏斗均未生成。
- 空 `stock_pool` 的本地日线回退会跨线程使用 SQLite 连接并直接失败。
- 显式全市场参数 `maxStocks=null` 被错误改成 200，无法执行全市场可信基线。
- 任务股票状态、恢复、幂等重试、失败明细和完整状态机未实现。
- 机会分页总数、信号查询和前端汇总仍未实现。
- 前端测试当前有 2 个失败。

因此 `77ea835` 不能用于重新执行正式可信基线回测。

---

## 3. 问题清单

| 编号 | 问题 | 严重程度 | 影响范围 | 是否必须修复 |
| --- | --- | --- | --- | --- |
| PHASE1-001 | 原始信号表未创建，真实命中任务会在保存信号时失败 | 高 | 所有产生信号的回测任务、原始信号追溯 | 是 |
| PHASE1-002 | NEXT_OPEN 执行结果与信号关联字段未持久化 | 高 | 执行模型、实际收益、退出信息、机会追溯 | 是 |
| PHASE1-003 | 无实际入场机会仍生成基于信号收盘价的虚假 horizon 收益 | 高 | 成功率、失败率、收益统计、可信基线 | 是 |
| PHASE1-004 | 汇总、真实评估区间、观察区间和判断异常统计未接入任务流程 | 高 | 回测报告、统计结论、异常可见性 | 是 |
| PHASE1-005 | 空股票池回退跨线程使用 SQLite 连接，且显式全市场参数被改成 200 | 高 | 全市场回测、本地股票池回退、可信基线范围 | 是 |
| PHASE1-006 | 任务股票状态、恢复、幂等重试和失败明细未实现 | 高 | 8 小时级任务可靠性、重复数据、任务状态准确性 | 是 |
| PHASE1-007 | 参数校验、任务状态和进度统计仍会产生错误或误导结果 | 中 | API 调用、任务列表、进度展示 | 是 |
| PHASE1-008 | 分页总数、原始信号查询、汇总展示和可信度标识未实现 | 中 | API、前端、人工审计 | 是 |
| PHASE1-009 | 测试未覆盖真实数据库/API/任务链路，且前端测试当前失败 | 中 | 回归可信度、交付门禁 | 是 |

---

## 4. 详细问题分析

### PHASE1-001：原始信号表未创建

#### 问题现象

`save_strategy2_backtest_signal()` 会写入：

```sql
strategy2_backtest_signals
```

但 `_ensure_strategy2_backtest_tables()` 只创建：

- `strategy2_backtest_tasks`
- `strategy2_backtest_opportunities`
- `strategy2_backtest_insufficient_stocks`

没有创建 `strategy2_backtest_signals`。

#### 已复现证据

在全新临时数据库执行：

```python
db.init_db(path)
db.save_strategy2_backtest_signal(task_id, signal)
```

实际结果：

```text
OperationalError: no such table: strategy2_backtest_signals
```

#### 触发条件

任意股票产生至少一个 `evaluation.passed=True` 信号。

#### 影响

`run_backtest()` 在保存原始信号时抛出异常，外层任务会被标记为 `failed`。也就是说，没有命中的冒烟任务可能完成，但真正有机会的任务反而会失败。

#### 修复建议

1. 在 `_ensure_strategy2_backtest_tables()` 中创建完整 `strategy2_backtest_signals` 表。
2. 创建唯一索引：

```sql
UNIQUE(task_id, code, evaluation_date)
```

3. 增加 signals 分页查询 DB 函数和 API。
4. 增加新数据库与旧数据库迁移测试。
5. 不允许仅在测试数据库手工建表。

#### 验证方式

- 全新数据库初始化后能查询到 signals 表。
- 保存同一个信号两次不会重复。
- 更新同一个信号时所有快照字段正确更新。
- `/api/strategy2/backtests/{taskId}/signals` 能返回原始信号和真实总数。

---

### PHASE1-002：NEXT_OPEN 与信号追溯结果未持久化

#### 问题现象

`opps_to_dicts()` 已生成：

- `signal_count`
- `execution_model`
- `entry_date`
- `entry_price`
- `exit_date`
- `exit_price`
- `exit_reason`
- `realized_return`
- `mark_to_market_end_return`
- `holding_days`
- `available_forward_days`

但机会表没有这些列，`save_strategy2_backtest_opportunity()` 也完全没有写入这些字段。

机会表同样缺少：

- `first_signal_id`
- `last_signal_id`
- `signal_count`
- 任务内唯一约束

#### 已复现证据

保存包含 NEXT_OPEN 和实际收益字段的机会后重新查询，以下字段全部缺失：

```text
execution_model
entry_date
entry_price
exit_reason
realized_return
mark_to_market_end_return
signal_count
available_forward_days
```

#### 影响

- 数据库与 API 仍只能看到旧的信号日收盘模型字段。
- 无法证明机会使用 NEXT_OPEN。
- 无法区分实际交易收益与观察期末收益。
- 无法查询一个机会由哪些原始信号组成。
- 页面和汇总无法使用可信执行结果。

#### 修复建议

1. 使用兼容迁移为机会表增加 Phase 1 全部字段。
2. 保存原始信号后取得信号 ID，并为每个机会保存 `first_signal_id`、`last_signal_id`、`signal_count`。
3. `save_strategy2_backtest_opportunity()` 必须写入全部执行字段。
4. 创建唯一索引：

```sql
UNIQUE(task_id, code, first_detected_date, execution_model)
```

5. 使用 upsert 或单股事务替换，保证重试不会重复。
6. 旧任务新增列允许为空，并标记 `LEGACY_UNTRUSTED`。

#### 验证方式

- opportunity round-trip 测试逐字段比较。
- 同一任务、股票、首次日期、执行模型重复保存后仍只有一条。
- 单股历史接口返回机会及其包含的信号。

---

### PHASE1-003：无入场机会仍生成虚假收益

#### 问题现象

`calculate_execution_outcome()` 对以下情况正确设置了无入场原因：

- `UNOBSERVED_ENTRY`
- `NO_ENTRY_GAP_BELOW_STOP`
- `NO_ENTRY_ABOVE_BUY_ZONE`

但后续仍无条件计算 horizon：

```python
entry_price = opp.entry_price if opp.entry_price > 0 else opp.entry_close
opp.horizons[str(h)] = calculate_horizon_performance(...)
```

当没有实际入场时，`opp.entry_price == 0`，代码回退使用信号日收盘价，生成一笔实际上不存在的交易表现。

#### 已复现证据

构造次日开盘低于止损的机会，执行结果为：

```text
exit_reason = NO_ENTRY_GAP_BELOW_STOP
entry_price = 0
```

随后仍得到：

```text
fabricated_horizon.result = FAILED
fabricated_horizon.end_return = 0.08
```

#### 影响

- 未成交机会被混入成功率、失败率和收益统计。
- NEXT_OPEN 可信基线被信号日收盘价结果污染。
- 跳空低开、跳空高开和无下一交易日样本会产生错误统计。

#### 修复建议

1. 只有 `entry_price > 0` 时才允许计算入场后的 horizon。
2. 无入场机会的各 horizon 应明确标记 `UNOBSERVED`，或从交易表现汇总中排除。
3. 保存 `exit_reason` 和 `available_forward_days`。
4. 汇总分别统计：
   - 原始机会数
   - 实际入场数
   - 各类未入场原因
5. 为 TARGET/STOP 设置真实 `exit_date` 和 `exit_price`；当前这两个字段始终为空。

#### 验证方式

- `NO_ENTRY_GAP_BELOW_STOP` 不得生成 SUCCESS/FAILED/UNRESOLVED horizon。
- `NO_ENTRY_ABOVE_BUY_ZONE` 不得生成交易收益。
- `UNOBSERVED_ENTRY` 不得使用信号收盘价。
- TARGET/STOP 的退出日期、价格和 realized return 正确。

---

### PHASE1-004：汇总、真实区间与判断异常未接入流程

#### 问题现象

虽然实现了 `aggregate_backtest_summary()`，但任务服务没有调用它。

当前任务表没有：

- `summary_json`
- `actual_evaluation_start_date`
- `actual_evaluation_end_date`
- `observation_data_end_date`
- `implementation_version`
- `credibility_status`
- 完整漏斗与异常统计

任务完成时直接写入：

```python
actual_start_date=payload.get("startDate", "")
actual_end_date=payload.get("endDate", "")
```

这只是请求区间，不是真实发生判断的区间。

前端仍然：

```js
horizonStats() { return null }
```

判断日异常仍然：

```python
except Exception as exc:
    eval_results[evaluation_index] = "EVALUATION_ERROR"
    continue
```

没有日志、异常明细、统计或失败阈值。

#### 影响

- 页面永远不展示真实 horizon 汇总。
- 无法判断请求开始日是否实际能够执行。
- 评估异常会静默造成样本缺失。
- 无法区分策略过滤、数据问题和引擎错误。
- 无法标记旧任务不可用于正式基线。

#### 修复建议

1. 单股回放返回真实评估最早/最晚日期、观察数据截止日期和完整漏斗。
2. 判断异常记录日期、代码、异常类型和简化堆栈。
3. 增加 `evaluation_error_days`，超过阈值时标记股票失败。
4. 任务完成前从数据库完整机会生成 summary，不得使用 API 当前页。
5. 保存并解析 `summary_json`。
6. 保存实现版本和可信度状态。
7. 前端读取 `task.summary.horizonStats`，展示请求区间、实际区间、观察截止日和错误统计。

#### 验证方式

- 请求区间早于可评估区间时，实际开始日期正确后移。
- endDate 后未来观察数据可使用，但不产生 endDate 后信号。
- 引擎异常有日志、计数和股票失败阈值。
- 汇总与数据库全量机会一致。

---

### PHASE1-005：全市场范围与本地股票池回退错误

#### 问题一：空股票池回退跨线程使用连接

请求线程创建：

```python
conn = db.get_conn()
```

后台线程在空 `stock_pool` 时使用同一个 `conn`：

```python
conn.execute("SELECT DISTINCT code FROM daily_ohlc ...")
```

SQLite 默认禁止跨线程使用连接。

已复现：

```text
ProgrammingError: SQLite objects created in a thread can only be used in that same thread
```

#### 问题二：显式全市场被改成 200

规范定义：

- 缺省未传 `maxStocks`：200
- 显式 `maxStocks=null`：全市场
- `maxStocks<=0`：HTTP 422

当前后台线程：

```python
max_stocks = payload.get("maxStocks")
if max_stocks is None:
    max_stocks = 200
```

无法区分“未传”和“显式 null”。

前端把 0 或空值转换为 null，并告诉用户这是全市场；后端却只运行 200 只。

#### 影响

- 本地 `stock_pool` 为空时，规范要求的 `daily_ohlc DISTINCT code` 回退会直接失败。
- 用户选择全市场时实际只测 200 只，范围严重错误。
- 无法执行规范要求的正式全市场可信基线。

#### 修复建议

1. 请求模型在启动线程前完成参数解析与验证。
2. 使用字段是否存在区分：

```python
if "maxStocks" not in payload:
    max_stocks = 200
else:
    max_stocks = payload["maxStocks"]  # None 表示全市场
```

3. 全市场查询不要拼接 `LIMIT None`；分成有限和无限两个查询。
4. 后台线程内只使用 `db.get_conn()` 或新增 DB helper，禁止使用请求线程连接。
5. 前端全市场增加二次确认，并移除“需数分钟”的错误提示。

#### 验证方式

- 未传 `maxStocks` 实际处理 200。
- 显式 null 实际处理全部本地股票。
- 0 和负数同步返回 HTTP 422，不创建任务。
- `stock_pool` 为空但 daily_ohlc 有数据时能完成回测。

---

### PHASE1-006：恢复、幂等与失败明细未实现

#### 问题现象

规范要求新增 `strategy2_backtest_task_stocks`，但当前不存在该表，也没有：

- 股票级 `pending/running/completed/insufficient/failed`
- 服务重启后的 interrupted 状态
- resume
- retry-failed
- cancel
- 单股事务
- 机会唯一约束
- 数据不足唯一约束

`save_strategy2_backtest_opportunity()` 每次直接 INSERT；重跑或重试会重复。

任务存在股票失败时仍统一写：

```python
status="completed"
```

#### 影响

- 长时间全市场任务中断后无法恢复。
- 重试或重复执行可能写入重复机会与数据不足记录。
- 用户无法查看失败股票原因或重试失败股票。
- 存在失败股票的任务仍显示完整完成。

#### 修复建议

1. 新增任务股票表及状态 CRUD。
2. 每只股票通过统一终态函数更新状态和统计。
3. 单股信号、机会、任务股票结果在一个事务内提交。
4. 重试前原子替换该股票结果，不能影响其他股票。
5. 启动时将遗留 running 股票恢复为 pending，并将任务标为 interrupted 或恢复。
6. 增加 resume/retry-failed/cancel API。
7. 有股票失败时使用 `completed_with_errors`。

#### 验证方式

- 中途模拟服务重启后可以恢复。
- 同一任务重试不会增加重复信号或机会。
- 单股保存失败会完整回滚。
- 失败股票有错误码和详情。

---

### PHASE1-007：参数、状态与进度语义错误

#### 问题现象

- 请求使用裸 `dict`，日期、代码、重复代码和范围均未验证。
- `maxStocks<=0` 在任务创建和线程启动后才标记失败，而不是 HTTP 422。
- 任务 ID 只精确到秒，同一秒创建可能冲突。
- `elapsed_seconds` 从未计算或保存。
- 没有日线数据的股票在循环中直接 `continue`，运行中 `processed_stocks` 不增加。
- 股票异常同样 `continue`，运行中进度不增加。
- 最后无条件将 `processed_stocks=total`，掩盖运行过程中的遗漏。

#### 影响

- 非法任务会先返回“已启动”，随后异步失败。
- 同秒任务可能主键冲突。
- 页面进度可能长时间停滞，最终又突然显示全部处理。
- 无法可靠判断任务耗时和失败状态。

#### 修复建议

1. 使用 Pydantic 请求模型同步校验。
2. 日期、代码、maxStocks 在创建任务前验证。
3. 任务 ID 增加随机后缀。
4. 使用单调时钟计算耗时并持久化。
5. 所有股票路径通过统一 finally/终态函数增加 processed。
6. 进度优先从任务股票表聚合。

---

### PHASE1-008：API 与前端无法展示完整可信结果

#### 问题现象

机会接口返回：

```python
{"opportunities": opps, "total": len(opps)}
```

`total` 是当前页长度，不是数据库总数。

前端：

- 默认只加载 500 条。
- 标题使用 `opportunities.length`。
- 没有分页。
- `horizonStats()` 固定返回 null。
- 没有 signals 查询与展开。
- 没有失败股票列表。
- 没有恢复、重试、取消。
- 没有可信度标识与旧任务警告。
- 没有请求区间、实际评估区间和观察区间。

#### 影响

用户无法确认结果完整性，也无法审核原始信号或正式可信基线。

#### 修复建议

1. 增加独立 COUNT 查询，返回 `items/total/limit/offset/hasMore`。
2. 新增 signals 和 task-stocks API。
3. 前端实现分页、汇总、范围、错误、可信度和恢复入口。
4. 旧任务显示 `LEGACY_UNTRUSTED`。

---

### PHASE1-009：测试没有覆盖真实任务链路

#### 问题现象

新增测试主要覆盖信号合并纯函数，只包含少量汇总断言。没有覆盖：

- 新数据库建表与旧数据库迁移。
- 信号保存。
- NEXT_OPEN 执行边界。
- opportunity 执行字段 round-trip。
- 小型本地数据库任务集成。
- 外部数据源禁用。
- 全市场 null 与默认 200。
- 空股票池 fallback。
- 汇总保存。
- 分页总数。
- 恢复与幂等。
- API 参数校验。

此外，当前前端测试实际结果：

```text
2 failed, 23 passed
```

失败项：

- `[18] live completion shows final failures and candidates`
- `[23] live failure stock terminal refresh fails — candidates still loaded`

#### 影响

现有 `504 passed` 无法证明 Phase 1 可信任务链路可用，且项目当前回归门禁并非全绿。

#### 修复建议

以小型临时 SQLite 数据库增加端到端集成测试，真实创建任务、运行股票、保存信号/机会、生成汇总并通过 API 查询。

---

## 5. 建议修复顺序

1. 先补齐数据库迁移：signals、task_stocks、机会执行字段、任务 summary/version 字段和唯一约束。
2. 修复 NEXT_OPEN 无入场收益污染、退出日期和退出价格。
3. 将任务执行从 `server.py` 拆到独立服务，修复参数解析和本地股票池线程问题。
4. 实现单股事务、股票状态、恢复、重试、取消与幂等。
5. 接入异常漏斗、真实评估区间、观察区间、耗时和完整汇总。
6. 修复 API 分页、signals、失败股票和任务详情。
7. 完成前端可信度、汇总、分页、范围和恢复展示。
8. 补齐 DB/API/集成/前端测试。
9. 全部门禁通过后，再运行正式全市场可信基线并人工抽样。

---

## 6. 给修复 AI 的执行要求

```text
请根据
docs/reviews/2026-06-12-strategy2-phase1-backtest-correctness-acceptance-review.md
完整修复 PHASE1-001 至 PHASE1-009。

本轮仍只实施 Phase 1，不实施任何 Phase 2 策略优化实验，不修改策略2正式评分、趋势、风险或否决规则。

必须遵守：
1. 不要只修纯函数；必须打通“请求 → 后台任务 → 本地数据库 → 汇总/API → 前端”的真实链路。
2. 先完成兼容数据库迁移，确保全新数据库和旧数据库都可升级。
3. 原始信号、机会执行结果、信号关联、任务股票状态必须真实持久化。
4. 无实际入场机会不得生成基于信号收盘价的交易收益。
5. 显式 maxStocks=null 必须表示全市场；未传才默认200；<=0同步返回422。
6. 后台线程禁止使用请求线程创建的 SQLite connection。
7. 单股结果必须事务化、可幂等重试；任务必须支持 interrupted/resume/retry-failed/cancel。
8. 判断异常必须记录和统计，不能静默 continue。
9. 汇总必须基于数据库完整结果生成并保存，不能基于当前页或内存局部数据。
10. 修复机会分页总数、signals 查询、失败股票查询和前端完整展示。
11. 增加真实临时 SQLite 集成测试；测试必须能发现 signals 表缺失、执行字段丢失、空股票池线程错误和无入场收益污染。
12. 修复当前两个失败的前端测试。

完成后必须报告：
- 数据库迁移字段、索引和兼容方案。
- 每个问题对应的代码与测试。
- 全部验证命令及实际结果。
- 新可信基线任务 ID。
- 与旧任务同区间的机会数、汇总和日期范围差异。
- 601607 等跨月信号抽样核对结果。
```

---

## 7. 回归测试清单

- 新数据库初始化包含所有 Phase 1 表和字段。
- 旧数据库兼容升级，不删除旧任务。
- 原始信号可保存、查询、追溯。
- 机会可追溯到 first/last signal。
- 中间 9 个计数未命中日仍合并。
- 中间 10 个计数未命中日正确拆分。
- 数据异常日不计入冷却，但有异常统计。
- NEXT_OPEN 正确保存入场、退出和收益。
- 无入场机会不产生虚假交易收益。
- 同日目标和止损按保守失败。
- 回测不调用任何外部股票池或行情源。
- stock_pool 为空时从 daily_ohlc 本地回退。
- 未传 maxStocks 默认 200。
- 显式 null 执行全市场。
- 0 和负数同步返回 422。
- 请求区间、实际评估区间和观察区间正确。
- 汇总由数据库完整结果生成。
- 单股写入失败事务回滚。
- 中断后恢复不产生重复数据。
- 机会 API 返回真实 total 和 hasMore。
- 前端展示汇总、范围、可信度、分页和失败股票。
- 旧任务显示不可作为正式基线。
- 所有后端和前端测试通过。

---

## 8. 不建议修改的内容

- 不要实施 Phase 2 实验参数。
- 不要修改策略2正式评分、趋势、风险或否决规则。
- 不要修改策略1回测逻辑。
- 不要请求 AKShare、百度、新浪、腾讯、yfinance 或其他网络数据。
- 不要删除旧任务或旧数据。
- 不要用 API 当前页生成汇总。
- 不要将旧回测任务作为正式优化基线。

---

## 9. 本轮验证结果

| 验证项 | 结果 |
| --- | --- |
| `python -m pytest tests/test_strategy2_backtester.py -v` | 16 passed |
| 后端离线全量测试 | 504 passed，2 warnings |
| 前端生产构建 | 通过 |
| 前端测试 | 2 failed，23 passed |
| Python 编译检查 | 通过 |
| `git diff --check 77ea835^..77ea835` | 通过 |
| 新数据库保存原始信号 | 失败：`no such table: strategy2_backtest_signals` |
| NEXT_OPEN 字段持久化 round-trip | 失败：执行字段全部缺失 |
| 空股票池本地回退连接 | 失败：跨线程 SQLite `ProgrammingError` |
| 无入场机会收益检查 | 失败：仍生成虚假 FAILED horizon 与收益 |

---

## 10. 最终交付标准

只有同时满足以下条件，才能验收 Phase 1：

1. 所有 Phase 1 P0 与 P1 必须项已完成，不只是纯计算函数。
2. 真实小型数据库任务可完整运行并查询全部结果。
3. 任务中断可恢复，重试无重复。
4. NEXT_OPEN 和无入场语义正确且真实持久化。
5. 汇总、范围、异常和分页结果准确。
6. 前后端测试与构建全部通过。
7. 完成同区间全市场可信基线回测。
8. 提供可信基线任务 ID、结果对比和 601607 等人工抽样证据。

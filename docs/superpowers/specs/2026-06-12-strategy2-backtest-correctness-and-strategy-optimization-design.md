# 开发方案文档：策略2回测可信度修复与策略优化实验

## 1. 需求背景

### 1.1 当前问题

策略2本地数据库回测已经能够完成全市场历史回放，但对任务
`s2bt-20260611-234328` 的复核表明，当前实现存在会直接影响回测结论可信度的问题。

该任务的基本结果：

| 指标 | 结果 |
|---|---:|
| 回测股票数 | 4973 |
| 数据不足股票数 | 84 |
| 失败股票数 | 0 |
| 有机会股票数 | 605 |
| 记录机会数 | 605 |
| 请求区间 | 2025-08-01 至 2026-05-01 |
| 实际机会首次命中区间 | 2026-01-08 至 2026-04-30 |
| 2026年2月机会数 | 414，占全部机会的68.43% |
| 实际运行时间 | 约8小时4分钟 |

复核发现，当前605个机会恰好对应605只股票，并不是因为每只股票只产生了一次真实机会，
而是因为信号合并代码无法识别两个命中日之间实际存在的未命中交易日。
同一股票相隔数月的信号仍会被错误合并为一次机会。

因此：

- 当前机会数量被低估。
- 首次命中日被过度代表，后续独立机会被丢失。
- 各周期收益、成功率和失败率只基于错误合并后的首次机会。
- 当前任务不能作为正式策略调参基线。

除信号合并外，当前实现还存在汇总统计未保存、回测可能访问外部股票池、
实际评估区间错误、异常静默跳过、任务不能恢复、分页总数错误、执行价格过于理想化等问题。

### 1.2 用户痛点

- 用户无法判断策略2是否真的具备稳定选股能力。
- 页面显示的机会数、日期范围和统计结果可能与实际历史信号不一致。
- 用户无法区分策略问题、市场阶段问题和回测实现问题。
- 回测耗时长，但任务中断后无法恢复，重新执行成本高。
- 当前总分、量干分、价稳分和后续收益之间缺少可信对比。
- 策略修改后无法与基准策略进行公平实验对比。

### 1.3 业务目标

本次优化分为两个阶段：

1. **Phase 1：修复策略2回测可信度。**
   先确保历史信号、机会划分、执行价格、收益计算、任务状态和统计展示准确。
2. **Phase 2：增加策略优化实验能力。**
   在不直接修改正式策略扫描结果的前提下，对量干门槛、时间止损、启动确认、
   机会类型和市场环境等优化方案进行可重复对比。

### 1.4 预期效果

- 修复后的回测结果能够追溯到每个判断日和每个原始命中信号。
- 同一股票相隔10个未命中交易日后重新命中时，正确生成新机会。
- 页面展示真实评估区间、完整汇总、分页总数和错误统计。
- 回测严格只读取本地数据库，不访问任何外部数据源。
- 回测任务中断后可以安全恢复或明确失败，不产生重复数据。
- 策略优化通过实验配置完成，能够与原始策略做同区间对照。

---

## 2. 需求目标

### 2.1 必须实现

#### Phase 1：回测可信度修复

- 修复原始信号合并逻辑。
- 保存每个原始命中信号，保证机会可追溯。
- 定义并正确实现10个未命中交易日冷却规则。
- 正确计算请求区间、实际评估区间和未来观察区间。
- 严格使用本地 `stock_pool` 和 `daily_ohlc`，禁止访问AKShare和其他外部数据源。
- 正确生成并保存完整回测汇总。
- 正确记录每类判断结果、过滤原因和异常原因。
- 修复任务默认参数、进度、耗时、分页和总数。
- 增加任务级和股票级持久化状态，支持中断恢复与幂等重试。
- 增加现实执行价格模型，避免默认使用不可保证成交的信号日收盘价。
- 对历史旧任务标记回测实现版本，防止新旧结果混用。
- 修复前端汇总、分页、任务状态和数据覆盖展示。

#### Phase 2：策略优化实验

- 增加独立的回测实验配置，不直接修改正式策略2配置。
- 支持量干分最低门槛实验。
- 支持5日检查和10日时间止损实验。
- 支持启动确认实验。
- 支持机会类型标签：趋势延续与反转修复。
- 支持基准策略与实验策略同区间对照。
- 支持按月份、分数、量干分、价稳分、趋势证据和机会类型分组统计。
- 支持同期本地全市场基准对比。

### 2.2 可选增强

- 导出回测任务、机会和原始信号CSV。
- 多任务对比页面。
- 参数网格实验。
- 行业和市场板块分组统计。
- 手续费、印花税和滑点的可配置模拟。
- 组合资金曲线与最大回撤。

### 2.3 不做范围

- Phase 1不修改策略2正式评分、趋势、风险和否决规则。
- Phase 2实验参数默认不影响正式扫描。
- 不复制或重写策略2判断逻辑。
- 不请求百度、新浪、腾讯、yfinance、AKShare或其他网络数据。
- 不修改策略1回测逻辑。
- 不删除已有回测任务。
- 不覆盖或回退worktree中的已有未提交修改。
- 不在未完成可信基线回测前，将实验参数升级为正式策略参数。

---

## 3. 默认假设

1. 策略2唯一判断入口仍为 `ExtremeDryStableStrategyEngine.evaluate_at()`。
2. 当前策略2至少250日数据即可执行，最多使用最近350日。
3. 回测判断日只能使用判断日及之前数据。
4. 回测结束日期限制的是“信号判断日”，未来观察允许使用结束日期之后的本地日线。
5. 同一股票的“交易日”以该股票本地有效日线序列为准，停牌且没有日线的日期不计入未命中天数。
6. 流动性过滤未通过、趋势过滤未通过、评分未通过和风险未通过均属于“已评估但未命中”，应计入未命中交易日。
7. 无法完成判断的数据异常日不计入冷却期，但必须记录异常原因。
8. 当前数据库主要覆盖存续股票，可能存在幸存者偏差；本期必须在报告中披露，但不建设历史退市股票池。
9. 当前本地日线没有数据源字段，无法完全识别不同来源或复权差异；本期增加数据质量检查与报告，不重构全部行情库。
10. `s2bt-20260611-234328` 以及修复前创建的任务只作为问题证据，不作为优化基线。

---

## 4. 已确认问题清单

### 4.1 P0：直接导致结果错误的问题

#### BT-P0-001：同一股票全部历史命中被错误合并

当前代码：

```python
missed = i - prev_idx - 1
```

`i` 和 `prev_idx` 是命中列表中的下标，不是完整交易日序列中的下标。
相邻两条命中记录即使相隔数月，下标仍然连续，`missed` 仍为0。

影响：

- 每只命中过的股票通常只产生一个机会。
- 后续独立信号被丢失。
- 首次命中日、入场价、止损价和收益统计失真。

修复：

- `merge_consecutive_signals()` 必须接收完整的“可评估交易日序列”或每个命中的 `evaluation_index`。
- 对两个命中之间的实际可评估交易日计算连续未命中数量。
- 当下一次命中前已经连续出现 `>= 10` 个有效未命中交易日时，创建新机会。
- 不能使用自然日差，也不能使用命中列表下标差。

精确定义：

```text
T0 命中
T1-T9 均为可评估但未命中
T10 再次命中
=> 中间只有9个未命中交易日，仍属于原机会

T0 命中
T1-T10 均为可评估但未命中
T11 再次命中
=> 中间已有10个未命中交易日，创建新机会
```

#### BT-P0-002：没有保存原始命中信号

当前只保存合并后的机会，无法核对：

- 每个机会由哪些命中日组成。
- 中间哪些日期未命中。
- 分数如何变化。
- 后续为何被合并或拆分。

修复：

- 新增原始信号表 `strategy2_backtest_signals`。
- 每个 `evaluation.passed=True` 的判断日保存一条信号。
- 机会表保存 `first_signal_id`、`last_signal_id` 和 `signal_count`。
- 单股历史接口可以返回机会以及其包含的信号。

#### BT-P0-003：回测汇总函数未被调用，汇总没有保存

当前虽然存在 `aggregate_backtest_summary()`，但任务执行流程没有调用它，
任务表也没有保存 `horizon_stats`。前端 `horizonStats()` 固定返回 `null`。

影响：

- 页面无法展示真实成功率、失败率、收益和回撤。
- 用户只能查看机会明细，无法从系统获得可信汇总。

修复：

- 任务完成前调用统一汇总服务。
- 将汇总JSON保存到任务表 `summary_json`。
- API返回解析后的 `summary`。
- 前端从 `task.summary.horizonStats` 展示汇总。
- 汇总必须基于数据库中该任务的完整机会，而不是API分页结果。

#### BT-P0-004：全市场回测可能访问外部AKShare股票池

当前全市场回测调用：

```python
get_a_stock_pool(config)
```

该函数优先调用AKShare网络接口，再回退本地缓存，违反“回测只使用本地数据库”的要求。

修复：

- 回测只能调用 `db.get_stock_pool()`。
- 如果本地 `stock_pool` 为空，则从 `daily_ohlc` 的不同股票代码构造本地股票范围。
- 禁止导入或调用 `scanner.stock_pool.get_a_stock_pool()`。
- 增加测试，通过monkeypatch保证任何外部股票池调用都会让测试失败。

#### BT-P0-005：执行价格存在信号日收盘成交偏差

当前使用判断日收盘价作为入场价，同时策略指标也使用了该日完整收盘数据。
如果策略在收盘后运行，无法保证以当天收盘价成交。

影响：

- 存在现实交易不可执行偏差。
- 收盘后出现的信号被假设在收盘价成交。

修复：

- Phase 1增加执行模型配置。
- 正式可信基线默认使用 `NEXT_OPEN`：信号日后的下一交易日开盘价入场。
- 保留 `SIGNAL_CLOSE` 仅作为诊断对照，不作为默认结果。
- 如果下一交易日不存在，机会标记 `UNOBSERVED_ENTRY`。
- 止损、目标和持有期从实际入场日开始计算。
- `NEXT_OPEN` 的目标价必须按实际入场价计算，不能继续按信号日收盘价计算。
- 下一交易日开盘价低于或等于信号止损价时，不应先买入再立即止损，标记 `NO_ENTRY_GAP_BELOW_STOP`。
- 下一交易日开盘价高于信号快照 `buy_zone_high` 时，可信基线默认标记
  `NO_ENTRY_ABOVE_BUY_ZONE`，避免将跳空高开追涨当成低风险入场。
- 成功入场后，入场日高低价参与目标和止损判断。
- 入场后同一交易日同时触发目标和止损时，继续按保守失败处理并记录原因。

#### BT-P0-006：任务实际评估区间记录错误

当前完成任务时直接将用户请求日期写入 `actual_start_date` 和 `actual_end_date`。
由于最低250日数据限制，请求开始日可能根本不能执行策略判断。

修复：

- `requested_start_date/requested_end_date` 保存用户请求。
- `actual_evaluation_start_date/actual_evaluation_end_date` 保存真实发生过判断的最早和最晚日期。
- `observation_data_end_date` 保存未来观察实际使用到的最晚数据日期。
- 前端同时展示请求区间和实际区间。

#### BT-P0-007：判断日异常被静默忽略

当前：

```python
except Exception:
    continue
```

影响：

- 某些判断日可能被静默丢失。
- 用户看到 `failed_stocks_count=0`，但无法确认是否存在判断日级异常。

修复：

- 禁止空异常捕获。
- 判断日异常必须记录股票、日期、异常类型和简化堆栈。
- 增加 `evaluation_error_days` 统计。
- 单日异常不中断股票；同一股票异常超过可配置阈值后标记股票失败。
- 任务汇总展示异常判断日数和失败股票数。

### 4.2 P1：任务可靠性和统计完整性问题

#### BT-P1-001：任务没有股票级持久化状态，无法恢复

当前任务执行进度只存在内存 `_backtest_running` 中。
服务重启后：

- 运行任务不会恢复。
- 数据库任务可能永久保持 `running`。
- 已完成股票和未完成股票无法区分。
- 重新执行可能产生重复结果。

修复：

- 新增 `strategy2_backtest_task_stocks`。
- 每只股票保存 `pending/running/completed/insufficient/failed`。
- 保存评估日数、命中数、机会数、过滤数、异常数和错误详情。
- 服务启动时将遗留 `running` 股票恢复为 `pending`。
- 对遗留任务支持自动恢复或明确标记 `interrupted`。
- 任务恢复必须使用原任务 `config_snapshot` 和 `experiment_snapshot`。

#### BT-P1-002：任务写入不具备幂等性

当前机会表没有任务内唯一约束，恢复或重试时可能重复写入。

修复：

- 原始信号唯一键：`(task_id, code, evaluation_date)`。
- 机会唯一键：`(task_id, code, first_detected_date, execution_model)`。
- 使用 `INSERT ... ON CONFLICT DO UPDATE` 或先删除该股票任务结果再原子重算。
- 单股重试只能替换该股票结果，不能影响其他股票。

#### BT-P1-003：默认 `maxStocks` 行为不一致

数据库创建任务时缺省值为200，但服务执行时：

```python
max_stocks = payload.get("maxStocks")
```

请求未传 `maxStocks` 时会执行全市场，而返回信息可能仍显示200。

修复：

- 后端统一解析参数，缺省值明确为200。
- `null` 仅表示用户明确选择全市场。
- `0` 和负数不再静默转换为全市场，应返回参数错误。
- 前端全市场必须二次确认。

#### BT-P1-004：请求参数缺少严格校验

当前没有完整校验：

- 开始日期和结束日期格式。
- 开始日期是否晚于结束日期。
- 股票代码格式和重复代码。
- `maxStocks` 范围。
- 回测区间是否完全无本地数据。
- 实验参数范围和组合合法性。

修复：

- 使用明确请求模型，不继续直接接收裸 `dict`。
- 非法参数返回HTTP 422和稳定错误码。
- 股票代码去重并保留稳定顺序。

#### BT-P1-005：任务ID可能在同一秒冲突

当前任务ID精确到秒：

```text
s2bt-YYYYMMDD-HHMMSS
```

修复：

- 增加毫秒或随机后缀。
- 推荐 `s2bt-YYYYMMDD-HHMMSS-<6位随机串>`。

#### BT-P1-006：任务耗时没有保存

当前 `elapsed_seconds` 永远为空。

修复：

- 使用单调时钟计算运行耗时。
- 运行中接口返回当前耗时。
- 完成、失败、中断均保存耗时。

#### BT-P1-007：进度统计在无数据和异常路径不准确

当前无日线数据时直接 `continue`，不会及时增加 `processed_stocks`。
当前股票、已完成判断次数和失败数也不会可靠持久化。

修复：

- 每只股票必须通过统一终态函数结束。
- 无论完成、数据不足或失败，都增加已处理数。
- 进度以数据库任务股票状态为准，内存仅作为缓存。
- 增加 `estimated_evaluations` 和 `completed_evaluations`。

#### BT-P1-008：股票失败只计数，不保存明细

当前股票级异常只写日志并增加 `failed_count`。

修复：

- 股票任务表保存 `error_code/error_detail`。
- 前端增加失败股票列表。
- 支持按失败股票重试。

#### BT-P1-009：任务完成状态无法区分完整与部分完成

如果存在股票失败，任务仍然直接标记 `completed`。

修复：

- 状态支持：
  - `created`
  - `running`
  - `completed`
  - `completed_with_errors`
  - `interrupted`
  - `failed`
  - `canceled`
- 存在失败股票但整体流程结束时使用 `completed_with_errors`。

### 4.3 P1：收益和统计口径问题

#### BT-P1-010：`end_return` 与实际交易收益混淆

当前即使第3日达到目标并退出，20日 `end_return` 仍使用第20日收盘价。
用户可能错误理解为实际持仓收益。

修复：

- 明确拆分：
  - `mark_to_market_end_return`：观察期末收盘收益。
  - `realized_return`：按目标、止损或时间退出后的实际模拟收益。
  - `exit_reason`：`TARGET/STOP/TIME_EXIT/UNOBSERVED_ENTRY`。
  - `exit_date/exit_price/holding_days`。
- 汇总同时展示期末表现和模拟交易表现。

#### BT-P1-011：缺少关键成功率口径

当前只计算 `success / observed`，但未决样本占比较高时难以理解。

修复：

每个周期至少展示：

- `target_hit_rate = success / observed`
- `stop_hit_rate = failed / observed`
- `unresolved_rate = unresolved / observed`
- `decisive_win_rate = success / (success + failed)`
- 平均和中位 `realized_return`
- 盈亏比、期望值和正收益比例
- 平均持有天数

#### BT-P1-012：缺少原始评估漏斗

当前无法回答策略为什么过滤股票。

修复：

任务和股票级统计至少包括：

- 总可评估判断日。
- 流动性过滤日。
- 趋势过滤日。
- 分数不足日。
- 风险比超限日。
- 一票否决日，按原因分组。
- 数据不足日。
- 数据异常日。
- 引擎异常日。
- 最终命中日。
- 合并后机会数。

#### BT-P1-013：缺少同期市场基准

当前无法区分策略收益与市场整体涨跌。

修复：

- 只使用本地数据库构造同期等权全市场基准。
- 每个信号日计算3/5/10/20日基准收益。
- 机会保存 `benchmark_return` 和 `excess_return`。
- 汇总展示平均超额收益、跑赢基准比例。
- 明确标注等权本地股票池存在幸存者偏差。

#### BT-P1-014：快速模式取股票池前N只，样本可能有偏

当前 `stocks[:max_stocks]` 不能代表全市场。

修复：

- 快速模式明确定位为“功能冒烟测试”，不能用于策略有效性结论。
- 若用于策略抽样实验，采用固定随机种子或按市场板块分层抽样。
- 保存 `sampling_method` 和 `sampling_seed`。

#### BT-P1-015：未来观察不足信息不完整

当前 `UNOBSERVED` 没有保存实际可观察天数。

修复：

- 保存 `available_forward_days`。
- `UNOBSERVED` 不计入完整周期成功率。
- 可选展示部分观察收益，但不得混入完整周期统计。

#### BT-P1-016：需要明确回测结束日期语义

修复：

- `endDate` 仅限制最后信号判断日。
- 未来观察可以读取 `endDate` 之后的本地日线。
- 未来观察不能超过任务冻结的 `data_snapshot_date`。
- 页面明确展示“信号区间”和“未来观察数据截止日”。

### 4.4 P1：数据库、API和前端问题

#### BT-P1-017：机会接口总数错误

当前接口返回：

```python
{"opportunities": opps, "total": len(opps)}
```

`total` 只是当前页数量，不是数据库总数。

修复：

- 数据库增加独立 `COUNT(*)`。
- 返回 `items/total/limit/offset/hasMore`。
- 支持按代码、月份、结果、分数和机会类型过滤。

#### BT-P1-018：前端只加载默认500条机会

当前任务有605条机会，前端会遗漏105条，并显示错误明细数量。

修复：

- 前端增加分页。
- 标题展示数据库总数，不使用当前页长度。
- 单页默认100条。

#### BT-P1-019：前端汇总表永远不展示

当前：

```javascript
horizonStats() { return null }
```

修复：

- 从任务详情中的 `summary` 读取。
- 任务完成后自动加载任务详情。
- 历史任务点击后展示完整汇总。

#### BT-P1-020：前端运行时间提示严重低估

当前提示全市场约需数分钟，但实际任务运行约8小时。

修复：

- 不写死“数分钟”。
- 启动前由后端估算股票数和判断次数。
- 根据历史同版本任务计算粗略耗时区间。
- 无历史样本时只提示“可能耗时较长”。

#### BT-P1-021：缺少配置快照和实现版本展示

修复：

- 任务保存并展示：
  - `config_snapshot`
  - `experiment_snapshot`
  - `backtest_engine_version`
  - `strategy_engine_version`
  - `execution_model`
  - `data_snapshot_date`
- 新旧版本结果不得默认直接比较。

#### BT-P1-022：历史任务列表无分页且返回完整配置快照

当前历史任务列表读取全部任务完整字段，随着任务数量增长会返回大量配置快照和汇总JSON。

修复：

- 历史任务列表增加分页。
- 列表接口只返回任务摘要，不返回完整 `config_snapshot`、`experiment_snapshot` 和 `summary_json`。
- 任务详情接口按任务ID返回完整快照和汇总。
- 前端任务历史列表支持分页和状态过滤。

#### BT-P1-023：长任务缺少明确的数据快照一致性

全市场任务可能运行数小时。如果任务运行期间日线数据被其他进程修改，
不同股票可能读取到不同时间点的数据版本。

修复：

- 创建任务时冻结 `data_snapshot_date`，判断日和未来观察都不得读取该日期之后的数据。
- 应用内继续保持扫描和回测互斥，避免行情写入与回测并行。
- 每只股票记录本次读取的最早日期、最晚日期和数据行数。
- 如果检测到任务运行期间数据库数据版本发生变化，任务标记警告或中断。
- 报告中披露当前未建设完整历史数据版本库，外部进程修改历史行仍可能影响可重复性。

#### BT-P1-024：指定股票回测可能丢失股票名称

当前指定股票代码时直接构造：

```python
{"code": code, "name": ""}
```

修复：

- 从本地 `stock_pool` 查询名称。
- 本地股票池不存在时允许名称为空，但前端显示明确占位。
- 不得为补充名称请求外部接口。

### 4.5 P2：性能和可维护性问题

#### BT-P2-001：逐条机会提交数据库事务

当前每保存一个机会立即提交事务，会增加SQLite写入开销。

修复：

- 单只股票结果使用一个事务批量写入。
- 原始信号和机会统一批量保存。
- 股票结果与股票终态原子提交。

#### BT-P2-002：任务将全部机会保存在内存

当前 `all_opps` 会持续增长，但最终并未正确用于汇总。

修复：

- 任务过程只维护计数。
- 汇总从数据库流式读取或分批聚合。
- 不在内存保存全市场全部机会。

#### BT-P2-003：机会未来数据定位为重复线性查找

当前每个机会都遍历整只股票日线寻找入选日。

修复：

- 在单股回放开始时创建 `date_to_index`。
- 原始命中直接保存 `evaluation_index`。
- 未来观察使用索引切片，避免重复遍历。

#### BT-P2-004：状态更新频率和持久化策略未定义

修复：

- 每完成一只股票保存股票终态。
- 每完成固定数量股票或固定秒数刷新任务汇总。
- 不为每个判断日写任务进度。
- 原始命中信号按单股批量写入。

---

## 5. 产品设计方案

### 5.1 用户使用流程

#### Phase 1可信基线回测

1. 用户进入策略2回测页面。
2. 页面默认选择“可信基线”模式。
3. 用户选择信号判断日期范围和股票范围。
4. 页面展示本地股票数、实际可评估日期预估和预计判断次数。
5. 用户选择执行模型，默认 `NEXT_OPEN`。
6. 用户启动任务。
7. 系统冻结配置、实验配置、实现版本和数据截止日期。
8. 系统从本地股票池和日线执行回放。
9. 前端展示任务漏斗和进度。
10. 任务完成后展示可信度状态、汇总、机会、原始信号、数据不足和失败股票。

#### Phase 2优化实验

1. 用户选择一个已完成的可信基线任务或创建同区间新实验。
2. 用户选择实验配置。
3. 系统确保股票范围、日期范围、执行模型和数据截止日期可比较。
4. 系统执行实验并生成与基线的对比报告。
5. 用户根据机会数量、实际收益、超额收益和稳定性判断是否保留优化方案。

### 5.2 页面展示要求

#### 任务可信度标识

- `LEGACY_UNTRUSTED`：修复前旧任务。
- `TRUSTED_BASELINE`：通过Phase 1规则运行的基线任务。
- `EXPERIMENTAL`：带实验参数的任务。
- `PARTIAL`：任务中断或存在未处理股票。

#### 回测漏斗

```text
本地股票
→ 可回测股票
→ 总判断日
→ 流动性通过
→ 趋势通过
→ 否决规则通过
→ 分数通过
→ 风险通过
→ 原始命中信号
→ 合并后机会
→ 可完成未来观察机会
```

#### 汇总报告

- 请求信号区间。
- 实际判断区间。
- 未来观察数据截止日。
- 股票范围和抽样方式。
- 配置快照和实验参数。
- 机会数量、原始信号数量和机会股票数量。
- 各周期目标命中率、止损率、未决率和决定性胜率。
- 各周期平均实际交易收益、期末收益和超额收益。
- 平均持有天数、平均达到目标天数、平均止损天数。
- 按月份和关键指标分组结果。

### 5.3 交互规则

- 旧任务必须显示“结果存在已知回测问题，不可作为正式调参依据”。
- 全市场任务需要用户明确确认。
- 快速前N只模式只能标记为冒烟测试。
- 用户修改正式配置后，不影响历史任务解释。
- 实验任务必须显示与正式扫描不一致的实验参数。
- 任务中断后允许恢复或终止，不能静默停留在运行中。
- 用户可以重试失败股票，但不能重复插入机会。

---

## 6. 技术架构方案

### 6.1 总体架构

```text
Strategy2Backtest 页面
  → 回测请求校验与快照冻结
  → 本地股票范围解析
  → 回测任务与股票任务持久化
  → 单股历史回放
      → 历史时点流动性过滤
      → ExtremeDryStableStrategyEngine.evaluate_at()
      → 保存原始信号与判断漏斗
      → 使用完整评估日序列合并机会
      → 执行模型与未来表现计算
  → 批量持久化
  → 数据库汇总服务
  → 基准和实验对比
  → API分页与前端展示
```

### 6.2 模块职责

#### `strategy2/backtester.py`

- 单股历史回放纯计算。
- 判断日结果分类。
- 原始信号生成。
- 基于完整评估日序列的机会合并。
- 执行模型和未来表现计算。

不得负责：

- 网络访问。
- 全局任务线程管理。
- 直接修改正式策略判断。

#### 建议新增 `strategy2/backtest_service.py`

- 创建和恢复任务。
- 解析本地股票范围。
- 调度单股回放。
- 批量持久化。
- 更新任务和股票状态。
- 调用汇总服务。

#### 建议新增 `strategy2/backtest_summary.py`

- 从数据库生成完整任务汇总。
- 生成指标分组、月份分组和基准对比。
- 不依赖API分页结果。

#### `scanner/db.py`

- 回测任务、股票任务、原始信号、机会和汇总CRUD。
- 单股结果事务。
- 幂等写入与分页总数。

#### `server.py`

- 参数校验。
- 冲突检查。
- 启动、恢复、取消和查询接口。
- 不包含单股回测核心算法。

### 6.3 状态设计

#### 任务状态

| 状态 | 说明 |
|---|---|
| CREATED | 已创建，尚未开始 |
| RUNNING | 正在执行 |
| COMPLETED | 全部股票成功完成 |
| COMPLETED_WITH_ERRORS | 已结束，但存在失败股票 |
| INTERRUPTED | 服务停止或任务意外中断，可恢复 |
| FAILED | 任务级错误，无法继续 |
| CANCELED | 用户取消 |

#### 股票状态

| 状态 | 说明 |
|---|---|
| PENDING | 等待处理 |
| RUNNING | 正在处理 |
| COMPLETED | 已完成回放 |
| INSUFFICIENT | 无法产生任何有效判断日 |
| FAILED | 股票级异常超过限制 |

#### 判断日结果分类

| 分类 | 是否计入冷却期未命中 |
|---|---|
| PASSED | 命中 |
| LIQUIDITY_FILTERED | 是 |
| DOWNTREND_FILTERED | 是 |
| REJECTION_FAILED | 是 |
| SCORE_BELOW_THRESHOLD | 是 |
| RISK_RATIO_TOO_HIGH | 是 |
| INSUFFICIENT_DATA | 否 |
| INVALID_DATA | 否 |
| EVALUATION_ERROR | 否 |

---

## 7. 数据库设计方案

### 7.1 修改任务表

兼容式新增字段，不删除旧字段：

```sql
ALTER TABLE strategy2_backtest_tasks ADD COLUMN backtest_engine_version TEXT;
ALTER TABLE strategy2_backtest_tasks ADD COLUMN strategy_engine_version TEXT;
ALTER TABLE strategy2_backtest_tasks ADD COLUMN credibility_status TEXT;
ALTER TABLE strategy2_backtest_tasks ADD COLUMN experiment_snapshot TEXT;
ALTER TABLE strategy2_backtest_tasks ADD COLUMN execution_model TEXT;
ALTER TABLE strategy2_backtest_tasks ADD COLUMN sampling_method TEXT;
ALTER TABLE strategy2_backtest_tasks ADD COLUMN sampling_seed INTEGER;
ALTER TABLE strategy2_backtest_tasks ADD COLUMN data_snapshot_date TEXT;
ALTER TABLE strategy2_backtest_tasks ADD COLUMN actual_evaluation_start_date TEXT;
ALTER TABLE strategy2_backtest_tasks ADD COLUMN actual_evaluation_end_date TEXT;
ALTER TABLE strategy2_backtest_tasks ADD COLUMN observation_data_end_date TEXT;
ALTER TABLE strategy2_backtest_tasks ADD COLUMN estimated_evaluations INTEGER DEFAULT 0;
ALTER TABLE strategy2_backtest_tasks ADD COLUMN completed_evaluations INTEGER DEFAULT 0;
ALTER TABLE strategy2_backtest_tasks ADD COLUMN raw_signals_count INTEGER DEFAULT 0;
ALTER TABLE strategy2_backtest_tasks ADD COLUMN evaluation_error_days INTEGER DEFAULT 0;
ALTER TABLE strategy2_backtest_tasks ADD COLUMN summary_json TEXT;
```

旧任务迁移：

- `credibility_status = LEGACY_UNTRUSTED`
- `backtest_engine_version = legacy-v1`

### 7.2 新增股票任务表

```sql
CREATE TABLE IF NOT EXISTS strategy2_backtest_task_stocks (
    task_id                  TEXT NOT NULL,
    code                     TEXT NOT NULL,
    name                     TEXT,
    status                   TEXT NOT NULL DEFAULT 'PENDING',
    available_days           INTEGER DEFAULT 0,
    actual_eval_start_date   TEXT,
    actual_eval_end_date     TEXT,
    evaluation_days          INTEGER DEFAULT 0,
    liquidity_filtered_days  INTEGER DEFAULT 0,
    trend_filtered_days      INTEGER DEFAULT 0,
    rejection_failed_days    INTEGER DEFAULT 0,
    score_failed_days        INTEGER DEFAULT 0,
    risk_failed_days         INTEGER DEFAULT 0,
    invalid_data_days        INTEGER DEFAULT 0,
    evaluation_error_days    INTEGER DEFAULT 0,
    raw_signals_count        INTEGER DEFAULT 0,
    opportunities_count      INTEGER DEFAULT 0,
    error_code               TEXT,
    error_detail             TEXT,
    started_at               TEXT,
    finished_at              TEXT,
    PRIMARY KEY (task_id, code)
);
```

### 7.3 新增原始信号表

```sql
CREATE TABLE IF NOT EXISTS strategy2_backtest_signals (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id                  TEXT NOT NULL,
    code                     TEXT NOT NULL,
    name                     TEXT,
    evaluation_date          TEXT NOT NULL,
    evaluation_index         INTEGER NOT NULL,
    score                    INTEGER NOT NULL,
    level                    TEXT,
    current_close            REAL NOT NULL,
    stop_loss                REAL,
    risk_ratio               REAL,
    volume_dry_score         INTEGER,
    price_stable_score       INTEGER,
    trend_type               TEXT,
    trend_evidence_score     INTEGER,
    opportunity_type         TEXT,
    evaluation_snapshot      TEXT NOT NULL,
    UNIQUE (task_id, code, evaluation_date)
);
```

### 7.4 修改机会表

建议兼容式新增：

```sql
ALTER TABLE strategy2_backtest_opportunities ADD COLUMN first_signal_id INTEGER;
ALTER TABLE strategy2_backtest_opportunities ADD COLUMN last_signal_id INTEGER;
ALTER TABLE strategy2_backtest_opportunities ADD COLUMN signal_count INTEGER DEFAULT 0;
ALTER TABLE strategy2_backtest_opportunities ADD COLUMN opportunity_type TEXT;
ALTER TABLE strategy2_backtest_opportunities ADD COLUMN execution_model TEXT;
ALTER TABLE strategy2_backtest_opportunities ADD COLUMN entry_date TEXT;
ALTER TABLE strategy2_backtest_opportunities ADD COLUMN entry_price REAL;
ALTER TABLE strategy2_backtest_opportunities ADD COLUMN available_forward_days INTEGER DEFAULT 0;
ALTER TABLE strategy2_backtest_opportunities ADD COLUMN benchmark_json TEXT;
```

唯一索引：

```sql
CREATE UNIQUE INDEX IF NOT EXISTS uq_s2_bt_signal
ON strategy2_backtest_signals(task_id, code, evaluation_date);

CREATE UNIQUE INDEX IF NOT EXISTS uq_s2_bt_opportunity
ON strategy2_backtest_opportunities(task_id, code, first_detected_date, execution_model);
```

### 7.5 数据兼容方案

- 不修改旧任务原始数据。
- 旧任务统一标记为 `LEGACY_UNTRUSTED`。
- 新字段允许为空，旧页面查询不应报错。
- 新汇总只对新版本任务生成。
- 旧任务页面展示已知问题说明。

---

## 8. 接口设计方案

### 8.1 创建回测任务

```http
POST /api/strategy2/backtests
```

请求示例：

```json
{
  "startDate": "2025-08-01",
  "endDate": "2026-05-01",
  "codes": [],
  "maxStocks": 200,
  "samplingMethod": "SMOKE_FIRST_N",
  "samplingSeed": 20260612,
  "executionModel": "NEXT_OPEN",
  "experiment": {
    "enabled": false
  }
}
```

约束：

- 缺省 `maxStocks=200`。
- 只有明确传入 `maxStocks=null` 才表示全市场。
- `maxStocks<=0` 返回参数错误。
- `startDate <= endDate`。
- `executionModel` 只允许 `NEXT_OPEN` 或 `SIGNAL_CLOSE_DIAGNOSTIC`。

返回：

```json
{
  "taskId": "s2bt-20260612-120000-a1b2c3",
  "status": "CREATED",
  "estimatedStocks": 200,
  "estimatedEvaluations": 20000,
  "credibilityStatus": "TRUSTED_BASELINE"
}
```

### 8.2 查询任务详情

```http
GET /api/strategy2/backtests/{taskId}
```

必须返回：

- 任务状态。
- 请求区间和实际区间。
- 进度和耗时。
- 配置与实验快照。
- 实现版本。
- 汇总 `summary`。
- 可信度状态。

### 8.3 查询机会

```http
GET /api/strategy2/backtests/{taskId}/opportunities?limit=100&offset=0&result10=SUCCESS
```

返回：

```json
{
  "items": [],
  "total": 1234,
  "limit": 100,
  "offset": 0,
  "hasMore": true
}
```

### 8.4 查询原始信号

```http
GET /api/strategy2/backtests/{taskId}/signals?code=601607&limit=100&offset=0
```

### 8.5 查询失败和数据不足股票

```http
GET /api/strategy2/backtests/{taskId}/stocks?status=FAILED
GET /api/strategy2/backtests/{taskId}/stocks?status=INSUFFICIENT
```

### 8.6 恢复和重试

```http
POST /api/strategy2/backtests/{taskId}/resume
POST /api/strategy2/backtests/{taskId}/retry-failed
POST /api/strategy2/backtests/{taskId}/cancel
```

---

## 9. Phase 2策略优化实验方案

### 9.1 原则

- 所有优化先作为回测实验参数。
- 实验不得复制策略2核心判断代码。
- 正式策略仍调用唯一引擎。
- 实验过滤作用于引擎评估结果或交易执行层。
- 只有通过多区间对照后，才单独讨论升级正式策略配置。

### 9.2 实验一：最低量干分

任务复核结果显示：

| 条件 | 机会数 | 10日成功率 | 10日失败率 | 10日模拟平均收益 |
|---|---:|---:|---:|---:|
| 全部机会 | 605 | 41.32% | 41.32% | +0.47% |
| 量干分>=40 | 335 | 49.55% | 37.91% | +1.01% |
| 量干分=50 | 119 | 49.58% | 36.13% | +1.18% |

实验参数：

```yaml
experiment:
  minimum_volume_dry_score: null
```

候选值：

- `null`：保持基线。
- `40`
- `50`

注意：

- 当前数据来自存在合并问题的旧任务，只能作为提出实验的证据，不能直接升级正式规则。
- 修复后必须重新验证。

### 9.3 实验二：量干与价稳分层门槛

当前总分允许高价稳分补偿弱量干分。
建议实验：

```yaml
experiment:
  minimum_total_score: 70
  minimum_volume_dry_score: 40
  minimum_price_stable_score: null
```

目的：

- 验证“真正量干”是否比单纯高总分更有预测能力。
- 避免将无上涨动力的窄幅横盘误判为高质量机会。

### 9.4 实验三：时间退出

旧任务初步结果：

- 5日模拟平均收益约 `+0.53%`。
- 10日模拟平均收益约 `+0.47%`。
- 20日模拟平均收益约 `+0.17%`。

实验参数：

```yaml
experiment:
  time_exit_days: null
```

候选值：

- `null`：只按目标和止损。
- `5`
- `10`

规则：

- 目标或止损先触发时按先触发规则退出。
- 到达时间退出日仍未触发目标或止损时，按当日收盘价退出。
- 保存 `exit_reason=TIME_EXIT`。

### 9.5 实验四：启动确认

策略2当前发现的是“量干价稳观察机会”，不一定代表当日立即适合买入。

实验参数：

```yaml
experiment:
  entry_confirmation:
    type: NONE
    max_wait_days: 5
```

候选类型：

- `NONE`：下一交易日开盘买入。
- `BREAK_RECENT_5D_HIGH`：等待收盘突破信号日前5日最高价。
- `CLOSE_ABOVE_MA20`：等待收盘重新站上MA20。
- `BREAK_HIGH_WITH_MODERATE_VOLUME`：突破且成交量不超过V20的指定倍数。

规则：

- 确认只使用确认日及之前数据。
- 超过 `max_wait_days` 未确认，标记 `NO_ENTRY_CONFIRMATION`。
- 确认条件属于交易执行实验，不修改原始策略命中。
- 必须分别统计“原始机会数”和“实际入场数”。

### 9.6 实验五：机会类型标签

策略2当前可能同时捕捉：

- 上涨或横盘后的趋势延续。
- 下跌后的超跌反弹。

新增标签，不直接否决：

#### `CONTINUATION`

建议初始定义：

```text
center_shift_20 >= 0
AND ma20 >= ma60
```

#### `REVERSAL`

建议初始定义：

```text
return_20 < -5%
OR drawdown_from_high_60 <= -12%
```

#### `NEUTRAL`

不满足以上条件。

要求：

- 标签规则集中在单一分类函数中。
- 标签只用于实验分组，不改变策略引擎 `passed`。
- 分别统计三类机会的收益、止损率和时间退出表现。

### 9.7 实验六：市场环境

旧任务机会高度集中在单一月份，因此必须增加市场阶段对比。

本期先只增加统计，不直接过滤：

- 信号日前5日、10日、20日本地等权市场收益。
- 市场等权指数是否高于MA20。
- 按月份和市场状态分组。

只有当多个时间区间都显示稳定差异时，才讨论市场过滤规则。

### 9.8 暂不建议直接实施的策略修改

- 不建议仅提高总分门槛。旧任务中总分>=80没有明显改善。
- 不建议仅根据下降趋势证据分做硬过滤。旧任务分组关系不稳定。
- 不建议根据单个2026年2月结果确定正式参数。
- 不建议直接删除反转类机会；应先分类比较。
- 不建议将20日持有结果作为策略主要成功标准，策略定位为短线。

---

## 10. 可以实施的代码方案

### 10.1 任务一：修复信号与机会模型

修改模块：

- `strategy2/backtest_models.py`
- `strategy2/backtester.py`
- `tests/test_strategy2_backtester.py`

实现：

1. 新增原始信号模型。
2. 单股回放返回完整评估日序列和原始命中。
3. 每个命中保存 `evaluation_index`。
4. 使用完整评估日状态计算未命中交易日。
5. 正确拆分机会。
6. 使用 `date_to_index` 计算未来数据。

不允许：

- 使用自然日差代替交易日。
- 使用命中列表下标计算未命中天数。
- 修改策略2引擎判断。

验证：

- 相隔数月信号必须拆分。
- 中间9个未命中日不拆分。
- 中间10个未命中日拆分。
- 数据异常日不计入冷却期。
- 流动性过滤日计入未命中。

### 10.2 任务二：实现现实执行与收益模型

修改模块：

- `strategy2/backtest_models.py`
- `strategy2/backtester.py`

实现：

- 默认下一交易日开盘入场。
- 保存入场日、入场价、退出日、退出价、退出原因和实际收益。
- 保留观察期末收益。
- 支持目标、止损和时间退出。

边界条件：

- 无下一交易日。
- 入场日高低价同时触发目标与止损。
- 跳空低开越过止损。
- 停牌导致未来交易日不足。

### 10.3 任务三：完善数据库持久化

修改模块：

- `scanner/db.py`
- 数据库迁移测试

实现：

- 新表和兼容字段。
- 单股结果事务。
- 幂等保存。
- 分页总数。
- 汇总JSON。
- 旧任务可信度迁移。

### 10.4 任务四：拆分任务服务

修改或新增：

- `strategy2/backtest_service.py`
- `strategy2/backtest_summary.py`
- `server.py`

实现：

- 使用本地股票池。
- 请求模型和参数校验。
- 创建、运行、恢复、取消和重试。
- 任务状态与股票状态持久化。
- 汇总生成。
- 任务版本快照。

不允许：

- 在 `server.py` 继续扩展大量回测算法。
- 调用外部股票池。
- 使用当前配置恢复历史任务。

### 10.5 任务五：完善API和前端

修改：

- `server.py`
- `web/src/composables/useApi.js`
- `web/src/pages/Strategy2Backtest.vue`

实现：

- 完整任务详情。
- 机会和信号分页。
- 失败股票与数据不足股票。
- 可信度标识。
- 汇总和漏斗。
- 请求区间与实际区间。
- 任务恢复和重试入口。
- 实验配置和基线对比。

### 10.6 任务六：增加实验过滤与对比

建议新增：

- `strategy2/backtest_experiments.py`

职责：

- 解析和校验实验配置。
- 对原始策略评估结果应用实验过滤。
- 机会类型分类。
- 启动确认和时间退出。

约束：

- 不复制策略2评分、趋势和否决规则。
- 默认实验关闭时结果等同可信基线。
- 实验配置必须完整保存到任务快照。

---

## 11. 日志与异常处理方案

### 11.1 必须记录的日志

- 任务创建、配置快照、实验快照和实现版本。
- 本地股票池来源和股票数。
- 请求区间、实际判断区间和数据截止日期。
- 每100只股票进度。
- 单股失败和判断日异常摘要。
- 任务恢复、取消和重试。
- 汇总生成开始和完成。
- 任务完成状态和耗时。

### 11.2 异常处理

- 单个判断日异常不终止单股，但必须计数和记录。
- 单股异常超过阈值时标记股票失败，不终止整体任务。
- 单股结果写入失败时整只股票事务回滚。
- 汇总生成失败时任务不能标记完整完成。
- 服务重启时运行任务标记 `INTERRUPTED` 并允许恢复。
- 数据库无本地股票池和日线时拒绝创建任务。

---

## 12. 测试方案

### 12.1 单元测试

#### 信号合并

- 连续命中合并。
- 中间9个未命中交易日仍合并。
- 中间10个未命中交易日拆分。
- 相隔数月命中拆分。
- 流动性过滤日计入未命中。
- 数据异常日不计入未命中。
- 不同股票独立处理。

#### 执行和收益

- 下一日开盘入场。
- 无下一日时 `UNOBSERVED_ENTRY`。
- 目标先触发。
- 止损先触发。
- 同日目标和止损按保守失败。
- 跳空低开穿过止损。
- 5日和10日时间退出。
- `realized_return` 与 `mark_to_market_end_return` 分离。

#### 实验配置

- 实验关闭时等同基线。
- 最低量干分过滤。
- 启动确认。
- 机会类型分类。
- 非法参数拒绝。

### 12.2 数据库测试

- 新表和新增字段自动创建。
- 旧数据库兼容升级。
- 旧任务标记 `LEGACY_UNTRUSTED`。
- 原始信号唯一约束。
- 机会唯一约束。
- 单股事务回滚。
- 重试不会重复插入。
- 分页总数正确。

### 12.3 接口测试

- 缺省 `maxStocks=200`。
- 明确 `null` 才运行全市场。
- `0` 和负数返回错误。
- 日期格式和区间校验。
- 回测不调用外部股票池。
- 查询任务返回汇总和版本。
- 机会分页总数正确。
- 原始信号查询。
- 失败股票查询和重试。
- 中断任务恢复。
- 扫描和回测互斥。

### 12.4 集成测试

1. 使用小型本地数据库创建股票池和日线。
2. 创建可信基线任务。
3. 生成多个相隔10个未命中交易日的机会。
4. 验证原始信号、机会和未来表现。
5. 中途模拟服务重启。
6. 恢复任务。
7. 验证无重复数据。
8. 生成汇总。
9. 创建实验任务并与基线对比。

### 12.5 前端测试

- 默认快速模式参数。
- 全市场二次确认。
- 请求区间和实际区间展示。
- 可信度状态。
- 任务进度与恢复。
- 汇总表展示。
- 漏斗展示。
- 机会分页。
- 原始信号展开。
- 失败和数据不足列表。
- 实验配置和基线对比。

### 12.6 回归测试

- 策略2扫描结果不受Phase 1影响。
- 实验关闭时不改变正式策略判断。
- 策略1扫描和回测不受影响。
- 配置页不混淆正式策略配置与实验配置。
- 回测仍不请求任何外部数据源。
- 全量后端测试和前端构建通过。

### 12.7 基准验收回测

修复后必须重新运行与旧任务相同的全市场区间：

```text
信号请求区间：2025-08-01 至 2026-05-01
策略窗口：至少250日，最多350日
执行模型：NEXT_OPEN
实验：关闭
```

必须验证：

- 机会数不再等于有机会股票数，除非数据真实如此。
- 上海医药 `601607` 相隔数月的信号不再错误合并。
- 页面显示实际评估区间，而不是直接复制请求区间。
- 汇总、分页总数和任务耗时可见。
- 任务报告包含可信度版本。

---

## 13. 验收标准

### Phase 1验收

1. 修复所有P0问题。
2. 同一股票机会按真实未命中交易日正确拆分。
3. 原始信号可以查询和追溯。
4. 回测严格不访问网络数据源。
5. 默认使用下一交易日开盘执行模型。
6. 任务汇总真实生成并展示。
7. 请求区间、实际判断区间和观察区间准确。
8. 判断日异常不再静默丢失。
9. 任务中断后可恢复，重试不产生重复数据。
10. API分页总数和前端展示准确。
11. 旧任务明确标记不可作为正式优化基线。
12. 新可信基线任务完成并通过人工抽样核对。

### Phase 2验收

1. 实验配置不影响正式扫描。
2. 基线和实验任务可以公平比较。
3. 量干分、时间退出、启动确认和机会类型实验可独立启用。
4. 实验关闭时结果等同可信基线。
5. 报告包含按月份和关键指标分组结果。
6. 不基于单一区间自动修改正式策略参数。

---

## 14. 给 Claude Code / Codex 的执行指令

请严格分阶段实施。

### Phase 1执行顺序

1. 阅读当前策略2引擎、回测器、数据库、服务接口和前端页面。
2. 保留并适配worktree中的已有未提交回测代码，不覆盖或回退。
3. 先为信号合并错误编写失败测试。
4. 修复机会划分，并新增原始信号持久化。
5. 增加现实执行与收益模型。
6. 完善任务股票状态、幂等写入和恢复。
7. 修复本地股票池、参数校验、实际日期和耗时。
8. 实现完整汇总、分页总数和前端展示。
9. 完成Phase 1测试后重新运行可信基线。
10. 未完成可信基线验证前，不实施Phase 2正式代码。

### Phase 2执行顺序

1. 新增独立实验配置和实验模块。
2. 默认关闭所有实验。
3. 先实现最低量干分和时间退出。
4. 再实现启动确认和机会类型。
5. 使用相同数据范围与基线比较。
6. 输出实验结论，不自动修改正式策略配置。

### 禁止事项

- 禁止复制策略2核心判断逻辑。
- 禁止在回测中调用网络数据源或外部股票池。
- 禁止静默捕获异常。
- 禁止使用命中列表下标计算未命中交易日。
- 禁止使用API分页结果生成任务汇总。
- 禁止将旧任务结果作为策略升级依据。
- 禁止修改无关模块。

---

## 15. AI开始开发提示语

```text
请阅读并严格执行：
docs/superpowers/specs/2026-06-12-strategy2-backtest-correctness-and-strategy-optimization-design.md

本次先只实施Phase 1：策略2回测可信度修复，不实施Phase 2策略优化实验。

核心要求：
1. 先阅读当前worktree中的strategy2/backtester.py、backtest_models.py、scanner/db.py、server.py、
   tests/test_strategy2_backtester.py和web/src/pages/Strategy2Backtest.vue。
2. 当前worktree存在未提交修改，必须保留并在其基础上开发，禁止回退。
3. 使用测试驱动开发，首先复现并修复“同一股票相隔数月信号仍被合并”的错误。
4. 连续机会必须根据完整可评估交易日序列计算；连续10个未命中交易日后再次命中才创建新机会。
5. 保存每个原始命中信号，机会必须可追溯。
6. 回测严格只读取本地stock_pool和daily_ohlc，禁止调用AKShare、百度、新浪、腾讯、yfinance。
7. 默认使用NEXT_OPEN执行模型，分离实际交易收益和观察期末收益。
8. 完善任务股票状态、幂等写入、中断恢复、失败明细、实际评估日期、耗时和完整汇总。
9. 修复机会分页总数、前端汇总和旧任务可信度提示。
10. 不修改策略2正式评分、趋势、风险和否决规则，不修改策略1。
11. 每完成一个模块运行对应测试；最终运行策略2测试、全量后端测试和前端构建。
12. 修复后使用相同区间重新执行可信基线回测，并核对601607等跨月命中股票。
13. 将修改文件、数据库变更、接口变更、测试结果、基线回测结果和遗留问题写入operations-log.md。
```

---

## 16. 最终交付物

开发完成后必须交付：

1. 修改文件清单。
2. 已修复问题与对应测试清单。
3. 数据库兼容变更说明。
4. 新增和修改接口说明。
5. 前端变更说明。
6. 旧任务兼容和可信度标识说明。
7. 全量测试和前端构建结果。
8. 修复后可信基线任务ID。
9. 新旧任务机会数、汇总和日期范围差异。
10. 上海医药 `601607` 等抽样核对结果。
11. 尚未实施的Phase 2实验清单。
12. 遗留风险和后续优化建议。

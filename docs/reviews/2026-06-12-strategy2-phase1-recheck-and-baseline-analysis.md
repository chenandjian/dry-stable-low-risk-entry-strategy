# 策略2 Phase 1 修复复查与新回测分析报告

## 1. 检查范围

- 开发规范：`docs/superpowers/specs/2026-06-12-strategy2-backtest-correctness-and-strategy-optimization-design.md`
- 本轮代码提交：`c9493d3 fix(strategy2): Phase 1 acceptance review — DB migration, execution persistence, parameter validation`
- 对比基线：`77ea835`
- 当前 worktree 额外未提交修改：
  - `scanner/db.py`
  - `web/src/pages/Strategy2Backtest.vue`
- 分析任务：`s2bt-20260612-145513-dc0yw2`
- 按要求过滤低等级问题，仅记录中、高等级问题。

---

## 2. 总体结论

本轮修复取得了实质进展：

- 原始信号表和任务股票表已经创建。
- NEXT_OPEN 执行字段已经加入机会表并可保存。
- 无实际入场机会不再产生虚假 horizon 收益。
- 显式 `maxStocks=null` 已按全市场解析。
- 空股票池回退不再跨线程使用 SQLite connection。
- 旧任务已标记为 `LEGACY_UNTRUSTED`。
- 机会接口增加了真实总数和分页结构。

新任务也证明信号合并修复有效：

- 原始信号 `1389` 条。
- 合并后机会 `679` 次。
- 有机会股票 `605` 只。
- 旧任务为 `605` 次机会 / `605` 只股票；新任务识别出额外 `74` 次独立机会。
- `601607` 已正确拆分为三次跨月机会。

但 Phase 1 仍不能验收，新任务也不能标记为正式可信基线：

- 任务股票表完全为空，恢复、失败明细、进度和幂等能力没有接入运行流程。
- `summary_json`、实际评估区间、观察区间、评估次数和异常统计均为空或 0。
- 所有 TARGET/STOP 机会都缺少退出日期和退出价格。
- 当前 HEAD `c9493d3` 本身不包含两个运行必需修复；仅当前脏 worktree 可以保存机会。
- 前端测试仍有 2 个失败。

---

## 3. 问题清单

| 编号 | 问题 | 严重程度 | 影响范围 | 是否必须修复 |
| --- | --- | --- | --- | --- |
| RECHECK-P1-001 | 任务股票状态表已建但运行流程未写入，恢复、幂等、失败明细仍不可用 | 高 | 长任务恢复、进度、失败重试、任务状态可信度 | 是 |
| RECHECK-P1-002 | 任务汇总、实际评估区间、观察区间和异常统计仍未生成 | 高 | 任务报告、统计结论、可信基线资格 | 是 |
| RECHECK-P1-003 | TARGET/STOP 机会未保存退出日期和退出价格 | 高 | 交易审计、实际收益验证、持有期核对 | 是 |
| RECHECK-P1-004 | `c9493d3` 不是可独立运行的提交，必要修复仍未提交 | 高 | 部署、复现、交付版本可靠性 | 是 |
| RECHECK-P1-005 | 新任务被过早标记为 `TRUSTED_BASELINE` | 高 | 用户决策、后续策略优化、结果可信度 | 是 |
| RECHECK-P1-006 | 恢复、重试失败股票、取消接口与单股事务仍未实现 | 高 | Phase 1 可靠性、重复结果、任务中断 | 是 |
| RECHECK-P1-007 | 原始信号与机会只按日期间接关联，first/last signal ID 仍为空 | 中 | 机会追溯、信号审计 | 是 |
| RECHECK-P1-008 | 时间字段口径不一致，前端测试仍有 2 项失败 | 中 | 耗时审计、回归门禁 | 是 |

---

## 4. 已修复项验收结果

### 4.1 信号合并修复：通过

任务对比：

| 指标 | 旧任务 `s2bt-20260611-234328` | 新任务 `s2bt-20260612-145513-dc0yw2` |
| --- | ---: | ---: |
| 有机会股票 | 605 | 605 |
| 机会数 | 605 | 679 |
| 原始信号数 | 无法追溯 | 1389 |
| 机会数与股票数是否恒等 | 是 | 否 |

新任务比旧任务增加 `74` 次独立机会，增幅约 `12.23%`。

月份对比：

| 月份 | 旧任务机会 | 新任务机会 | 增加 |
| --- | ---: | ---: | ---: |
| 2026-01 | 76 | 76 | 0 |
| 2026-02 | 414 | 427 | 13 |
| 2026-03 | 53 | 69 | 16 |
| 2026-04 | 62 | 107 | 45 |

这与“后续独立机会曾被错误合并”的问题特征一致。

### 4.2 `601607` 人工抽样：通过

原始信号共 10 条，已合并为三次机会：

| 首次命中 | 最后命中 | 信号数 | 入场日 | 执行结果 |
| --- | --- | ---: | --- | --- |
| 2026-01-08 | 2026-01-08 | 1 | 2026-01-09 | STOP |
| 2026-03-12 | 2026-03-17 | 4 | 2026-03-13 | STOP |
| 2026-04-21 | 2026-04-29 | 5 | 2026-04-22 | STOP |

跨月信号已不再错误合并为一次机会。

### 4.3 NEXT_OPEN 和无入场语义：部分通过

新任务：

- 所有 679 次机会的 `execution_model` 均为 `NEXT_OPEN`。
- 641 次实际入场的入场日均晚于信号日。
- 38 次未入场机会：
  - `NO_ENTRY_ABOVE_BUY_ZONE`：37
  - `NO_ENTRY_GAP_BELOW_STOP`：1
- 未入场机会的 realized return 均为 0。
- 未入场机会的各 horizon 均为 `UNOBSERVED`。

但退出日期和退出价格仍未生成，见 `RECHECK-P1-003`。

---

## 5. 详细问题分析与修复方案

### RECHECK-P1-001：任务股票状态未接入运行流程

#### 证据

任务：

```text
total_stocks = 5527
processed_stocks = 5527
```

但：

```text
strategy2_backtest_task_stocks = 0 条
```

代码已经新增：

```python
save_strategy2_backtest_task_stock(...)
get_strategy2_backtest_task_stocks(...)
```

但 `server.py` 的回测循环没有调用它们。

#### 影响

- 无法知道每只股票是 completed、insufficient 还是 failed。
- 无法恢复中断任务。
- 无法只重试失败股票。
- 无法根据股票状态可靠计算进度。
- `failed_stocks_count=0` 无法证明没有股票级错误。
- 任务结果无法幂等重算。

#### 一次性修复

1. 创建任务后，为 `resolved_stocks` 批量插入 `PENDING` 状态。
2. 每只股票开始前更新为 `RUNNING`。
3. 每只股票必须通过统一终态函数结束：

```python
COMPLETED
INSUFFICIENT
FAILED
```

4. 保存单股：
   - 实际评估区间
   - 评估日数
   - 各过滤日数
   - 异常日数
   - 原始信号数
   - 机会数
   - 错误码与错误详情
5. 任务进度和最终统计从任务股票表聚合。
6. 单股信号、机会、数据不足与任务股票状态必须放在一个事务中。

---

### RECHECK-P1-002：任务汇总和可信范围仍为空

#### 新任务证据

以下字段为空或 0：

```text
summary_json = NULL
actual_evaluation_start_date = NULL
actual_evaluation_end_date = NULL
observation_data_end_date = NULL
estimated_evaluations = 0
completed_evaluations = 0
raw_signals_count = 0
evaluation_error_days = 0
```

实际数据库已有：

```text
原始信号数 = 1389
最早信号日 = 2026-01-08
最晚信号日 = 2026-04-30
```

但任务表仍未保存。

#### 影响

- 前端无法展示真实汇总。
- 无法确认请求区间 `2023-01-01 ~ 2026-05-01` 中哪些日期真实发生判断。
- 无法确认未来观察使用到哪一天。
- 无法判断是否存在评估异常。
- 任务被标记为可信，但没有任务级可信报告。

#### 一次性修复

1. 单股回放返回：
   - `actual_eval_start_date`
   - `actual_eval_end_date`
   - `observation_data_end_date`
   - 完整漏斗
   - `evaluation_error_days`
2. 汇总所有任务股票状态，保存任务级范围与统计。
3. 任务完成前调用 `aggregate_backtest_summary()`。
4. 汇总必须从数据库完整机会读取，不使用内存局部列表或 API 当前页。
5. 保存 `summary_json` 并在任务详情 API 中解析为 `summary`。
6. 前端展示：
   - 请求区间
   - 实际评估区间
   - 观察数据截止日
   - 评估漏斗
   - horizon 汇总

---

### RECHECK-P1-003：退出日期和退出价格缺失

#### 证据

新任务中：

```text
TARGET = 265
STOP = 374
TARGET/STOP 合计 = 639
缺少 exit_date / exit_price = 639
```

`calculate_execution_outcome()` 只保存了：

```python
exit_reason
holding_days
realized_return
```

没有根据触发日设置 `exit_date` 和 `exit_price`。

#### 影响

- 无法核对目标或止损在哪一天触发。
- 无法审计 realized return。
- 无法验证 holding days。
- 后续时间退出、手续费和滑点模型没有可靠基础。

#### 一次性修复

遍历未来日线时保存目标和止损首次触发的完整记录：

```python
target_hit = (day_index, date, target_price)
stop_hit = (day_index, date, stop_loss)
```

确定保守触发顺序后设置：

```python
opp.exit_date
opp.exit_price
opp.exit_reason
opp.holding_days
opp.realized_return
```

规则：

- TARGET：`exit_price = target_price`
- STOP：可信基线至少保存策略止损价；若未来采用跳空止损模型，应单独定义
- 同日同时触发：STOP
- UNRESOLVED：退出字段保持空，不能伪造退出

---

### RECHECK-P1-004：提交版本不是可独立运行交付物

#### 证据

当前 HEAD 为 `c9493d3`，但 worktree 仍有未提交生产修改：

- `scanner/db.py`
- `web/src/pages/Strategy2Backtest.vue`

其中 `scanner/db.py` 的未提交修改修复了两个运行阻断问题：

1. 增加缺失的 `import json`。
2. 修正机会 INSERT placeholder 数量。

若只 checkout `c9493d3`：

- 保存原始信号会触发 `NameError: json is not defined`。
- 保存机会会因 placeholder 数量不匹配失败。

#### 影响

版本号无法复现新回测任务，部署该提交会回退到不可运行状态。

#### 修复建议

1. 将必要生产修复和测试纳入新的明确提交。
2. 提交前从干净 worktree 重新运行小型数据库集成任务。
3. 验收时只使用可 checkout 的提交，不依赖本地脏修改。

---

### RECHECK-P1-005：可信度标识过早

#### 问题现象

任务创建时立即写入：

```python
credibility_status="TRUSTED_BASELINE"
```

但当前任务缺少 summary、实际评估区间、任务股票状态、异常统计和退出审计字段。

#### 影响

用户可能将不完整结果用于 Phase 2 参数优化或正式策略决策。

#### 修复建议

可信度状态应由完成后的完整性校验决定：

```text
RUNNING_UNVERIFIED
PHASE1_INCOMPLETE
TRUSTED_BASELINE
LEGACY_UNTRUSTED
```

只有满足以下条件才允许标记 `TRUSTED_BASELINE`：

- 所有任务股票存在终态。
- summary 已生成。
- 实际评估与观察区间已保存。
- 信号、机会和执行字段完整。
- 无未记录异常。
- 完整性校验通过。

当前任务应改为 `PHASE1_INCOMPLETE`，不应继续标记为正式可信基线。

---

### RECHECK-P1-006：恢复、重试与取消仍未实现

#### 证据

没有以下回测接口：

```text
POST /api/strategy2/backtests/{taskId}/resume
POST /api/strategy2/backtests/{taskId}/retry-failed
POST /api/strategy2/backtests/{taskId}/cancel
```

也没有服务启动时处理遗留 running 回测任务的流程。

#### 修复建议

1. 服务启动时将遗留 `RUNNING` 股票恢复为 `PENDING`。
2. 任务状态改为 `INTERRUPTED`，或按原配置快照自动恢复。
3. resume 必须使用任务的配置快照与数据快照。
4. retry-failed 只原子替换失败股票结果。
5. cancel 在股票边界安全停止并保存进度。

---

### RECHECK-P1-007：信号 ID 关联仍未建立

#### 问题现象

机会表已有：

```text
first_signal_id
last_signal_id
```

但保存机会时未写入，当前任务中均为空。当前只能通过 code + 日期范围间接推断关联。

#### 修复建议

保存信号后返回 ID 映射，将 cluster 的首尾信号 ID 写入机会。单股历史接口应直接返回机会包含的信号。

---

### RECHECK-P1-008：时间口径与回归门禁

#### 时间口径

任务记录：

```text
started_at = 2026-06-12 06:55:13
finished_at = 2026-06-12 14:58:43
elapsed_seconds = 209.9
```

`started_at` 来自 SQLite `datetime('now')`，使用 UTC；`finished_at` 使用本地时间。两个时间看起来相差约 8 小时，但 elapsed 为约 3.5 分钟。

应统一使用 UTC ISO8601 或统一本地时区，避免误读。

#### 前端测试

当前：

```text
2 failed, 23 passed
```

失败测试：

- `[18] live completion shows final failures and candidates`
- `[23] live failure stock terminal refresh fails — candidates still loaded`

Phase 1 修改不能以已有前端回归测试失败的状态交付。

---

## 6. 新回测任务结果分析

### 6.1 数据完整性概览

| 指标 | 数值 |
| --- | ---: |
| 股票池 | 5527 |
| 数据不足 | 638 |
| 有机会股票 | 605 |
| 原始信号 | 1389 |
| 合并机会 | 679 |
| 实际入场 | 641 |
| 未入场 | 38 |
| 重复信号 | 0 |
| 重复机会 | 0 |
| 机会无对应信号 | 0 |
| signal_count 不一致 | 0 |

数据不足原因：

| 原因 | 数量 |
| --- | ---: |
| `NO_LOCAL_DATA` | 554 |
| `INSUFFICIENT_HISTORY_DATA` | 84 |

### 6.2 实际执行结果

| 结果 | 数量 | 占实际入场 |
| --- | ---: | ---: |
| TARGET | 265 | 41.34% |
| STOP | 374 | 58.35% |
| UNRESOLVED | 2 | 0.31% |

实际入场样本平均 `realized_return`：

```text
-0.3191%
```

按当前 NEXT_OPEN、目标 +5%、策略止损规则，这个区间的策略实际执行期望为负。

### 6.3 月份表现

| 月份 | 机会 | 实际入场 | TARGET | STOP | 平均实际收益 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2026-01 | 76 | 74 | 23 | 51 | -1.2266% |
| 2026-02 | 427 | 398 | 187 | 211 | +0.1469% |
| 2026-03 | 69 | 63 | 10 | 52 | -2.4513% |
| 2026-04 | 107 | 106 | 45 | 60 | -0.1680% |

机会仍高度集中在 2026 年 2 月：

```text
427 / 679 = 62.89%
```

2 月表现略为正，但 1 月、3 月和 4 月均为负，尤其 3 月明显较差。当前结果支持“市场阶段影响显著”的判断，不支持直接升级正式策略参数。

### 6.4 10 日表现

| 10 日结果 | 数量 | 占实际入场 |
| --- | ---: | ---: |
| SUCCESS | 227 | 35.41% |
| FAILED | 278 | 43.37% |
| UNRESOLVED | 136 | 21.22% |

10 日内成功样本少于失败样本，且仍有较高未决比例。

### 6.5 结果使用建议

当前任务可以用于：

- 证明信号合并修复生效。
- 初步观察 NEXT_OPEN 下的结果分布。
- 发现月份表现差异。

当前任务不能用于：

- 作为正式 `TRUSTED_BASELINE`。
- 直接决定 Phase 2 正式优化参数。
- 证明完整回测任务无异常。
- 审计退出日期、任务恢复和完整汇总。

---

## 7. 建议修复顺序

1. 先提交当前未提交的运行必需修复，并从干净提交验证。
2. 将任务股票状态接入真实回测循环，完成单股事务与状态聚合。
3. 生成完整 summary、实际评估区间、观察区间和异常统计。
4. 补齐 exit_date / exit_price 与 first/last signal ID。
5. 实现 interrupted/resume/retry-failed/cancel。
6. 增加任务完成完整性校验，再决定可信度状态。
7. 修复时间口径和前端测试。
8. 重新执行全市场基线任务。

---

## 8. 给修复 AI 的执行要求

```text
请根据
docs/reviews/2026-06-12-strategy2-phase1-recheck-and-baseline-analysis.md
修复 RECHECK-P1-001 至 RECHECK-P1-008。

本轮仍只实施 Phase 1，不实施 Phase 2 策略优化，也不修改正式策略2判断规则。

关键要求：
1. 当前 HEAD c9493d3 缺少运行必需修复；先将 scanner/db.py 和 Strategy2Backtest.vue 的必要修改纳入可复现提交。
2. 将 strategy2_backtest_task_stocks 真正接入回测循环，所有股票必须有终态。
3. 单股信号、机会、数据不足、错误和任务股票状态必须事务化且可幂等替换。
4. 任务完成前从数据库完整结果生成 summary_json、实际评估区间、观察区间、评估次数、原始信号数和异常统计。
5. 为 TARGET/STOP 保存 exit_date 和 exit_price。
6. 保存 first_signal_id 和 last_signal_id，单股接口直接返回机会对应信号。
7. 实现 interrupted/resume/retry-failed/cancel。
8. 不要在任务创建时直接标记 TRUSTED_BASELINE；完成完整性检查后再标记。
9. 统一 started_at、finished_at 的时区口径。
10. 修复当前两个失败的前端测试。
11. 增加临时 SQLite 集成测试，验证任务股票、summary、退出字段、恢复和幂等。

完成后重新执行全市场任务，并提供：
- 新任务 ID。
- 完整 summary。
- 实际评估和观察区间。
- task_stocks 状态汇总。
- 异常统计。
- 退出字段完整性检查。
- 601607 抽样结果。
- 所有测试实际结果。
```

---

## 9. 本轮验证结果

| 验证项 | 结果 |
| --- | --- |
| Strategy2 回测与独立性测试 | 21 passed |
| 后端离线全量测试 | 504 passed，2 warnings |
| 前端测试 | 2 failed，23 passed |
| 前端生产构建 | 通过 |
| Python 编译检查 | 通过 |
| 当前 `git diff --check` | 通过 |
| 原始信号与机会重复检查 | 通过 |
| 信号与机会数量关联检查 | 通过 |
| NEXT_OPEN 入场顺序检查 | 通过 |
| 未入场虚假收益检查 | 通过 |
| 任务股票状态完整性 | 失败：0 / 5527 |
| 任务 summary 与真实区间 | 失败：均未生成 |
| TARGET/STOP 退出字段 | 失败：639 / 639 缺失 |
| 提交可复现性 | 失败：必要修复仍在未提交 worktree |

---

## 10. 最终交付标准

1. 可从干净提交运行完整回测。
2. 每只股票有持久化终态，任务可恢复和幂等重试。
3. summary、真实评估区间、观察区间和异常统计完整。
4. 所有实际退出机会有退出日期和价格。
5. 所有机会可直接追溯原始信号。
6. 可信度状态由完成完整性校验决定。
7. 前后端全部测试通过。
8. 新全市场任务满足完整性检查后，才可标记 `TRUSTED_BASELINE`。

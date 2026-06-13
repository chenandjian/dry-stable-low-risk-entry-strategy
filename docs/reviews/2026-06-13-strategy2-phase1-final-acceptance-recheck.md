# 策略2 Phase 1 最终验收复查与一次性修复方案

## 1. 检查范围

- 当前提交：`d981fed fix(strategy2): close final phase1 acceptance gaps`
- 上一修复提交：`7a3430e fix(strategy2): complete phase1 backtest reliability`
- Phase 1 基线：`77ea835 fix(strategy2): Phase 1 backtest correctness`
- 设计文档：
  `docs/superpowers/specs/2026-06-12-strategy2-backtest-correctness-and-strategy-optimization-design.md`
- 重点检查：
  - `server.py`
  - `scanner/db.py`
  - `strategy2/backtest_service.py`
  - `strategy2/backtester.py`
  - `web/src/pages/Strategy2Backtest.vue`
  - `web/src/composables/useApi.js`
  - `tests/test_strategy2_medium_high_fixes.py`
- 本报告仅记录中、高等级问题，不记录低等级问题。

---

## 2. 总体结论

上一轮 `ACCEPT-001`～`ACCEPT-003` 已正确修复：

- 数据版本指纹已经包含 `turnover`。
- 历史不满足新规则的 `TRUSTED_BASELINE` 会降级。
- 任务数据版本查询已经在 SQL 层按任务股票范围过滤。
- 专项测试、后端全量测试、前端测试和构建均通过。

但是 Phase 1 当前仍有 **3 个高等级问题、1 个中等级问题**：

1. 服务重启时，遗留回测任务不会被标记为 `INTERRUPTED`，实际无法恢复。
2. 可信基线没有保存和校验策略引擎版本，代码变化后的结果仍可能被错误视为同版本。
3. 前端没有恢复、取消、失败重试、失败股票和可信度展示，后端闭环无法由用户操作。
4. 历史任务列表仍无分页和状态过滤。

因此当前不建议宣布 Phase 1 最终验收通过。

---

## 3. 问题清单

| 编号 | 问题 | 严重程度 | 影响范围 | 必须修复 |
|---|---|---:|---|---|
| FINAL-001 | 服务重启后的回测任务恢复失效 | 高 | 长任务可靠性、中断恢复 | 是 |
| FINAL-002 | 可信基线未冻结和校验策略实现版本 | 高 | 结果可复现性、跨版本对比、恢复与重试 | 是 |
| FINAL-003 | 前端缺少回测任务控制、失败明细和可信度展示 | 高 | 用户操作闭环、失败处理、可信结果识别 | 是 |
| FINAL-004 | 历史回测任务列表无分页和状态过滤 | 中 | 长期使用性能、任务定位 | 是 |

---

## 4. 已确认通过

### 4.1 数据版本

- 指纹字段为：
  `code/date/open/high/low/close/volume/turnover`。
- 修改 `turnover` 会改变指纹。
- 恢复和失败重试会拒绝数据版本变化的任务。
- 生产指纹查询通过 `strategy2_backtest_task_stocks` 关联，仅读取任务范围内股票。

### 4.2 回测执行与汇总

- `resume` 只选择 `PENDING/RUNNING` 股票。
- `retry-failed` 只选择 `FAILED` 股票。
- 单股结果原子替换，不重复写入机会和信号。
- 取消任务不能成为可信基线。
- 零机会完整任务可以生成完整汇总。
- 逐股审计、漏斗、周期收益和目标/止损耗时统计已实现。

### 4.3 本轮验证结果

| 验证项 | 结果 |
|---|---|
| 中高问题专项测试 | `15 passed` |
| 策略2专项与验收测试 | `70 passed` |
| 后端离线全量测试 | `523 passed, 1 warning` |
| 前端 Vitest | `25 passed` |
| 前端生产构建 | 通过 |
| Python 编译检查 | 通过 |
| 当前提交 `git show --check` | 通过 |

---

## 5. 详细问题分析与一次性修复方案

### FINAL-001：服务重启后的回测任务恢复失效

#### 问题现象

服务启动后，数据库中遗留的策略2回测任务仍保持：

```text
task.status = running
task_stock.status = RUNNING
```

不会转换为：

```text
task.status = INTERRUPTED
task_stock.status = PENDING
```

用户调用恢复接口时，接口只允许 `interrupted` 或 `canceled`，因此会返回
`TASK_NOT_RESUMABLE`。

#### 代码证据

`server.py` 的 `lifespan()` 中直接使用未定义变量：

```python
running = conn.execute(
    "SELECT id FROM strategy2_backtest_tasks WHERE status='running'"
).fetchall()
```

此作用域没有执行：

```python
conn = db.get_conn()
```

并且异常被完全吞掉：

```python
except Exception:
    pass
```

因此启动流程表面正常，但回测任务状态没有更新。

#### 已完成的直接复现

构造一个 `running` 任务和一个 `RUNNING` 股票后进入 `lifespan()`，结果仍为：

```text
running
RUNNING
```

#### 影响

- 全市场长回测在服务重启后无法恢复。
- 历史任务永久停留在 `running`。
- 前端和用户会误以为任务仍在运行。
- 已实现的 `resume` 执行器无法发挥作用。

#### 精确修复步骤

1. 在 `lifespan()` 的策略2回测恢复块中显式获取连接：

   ```python
   conn = db.get_conn()
   ```

2. 使用一个事务完成状态转换：

   ```sql
   UPDATE strategy2_backtest_tasks
   SET status='INTERRUPTED',
       credibility_status='PHASE1_INCOMPLETE',
       error='Interrupted by server restart'
   WHERE status='running';

   UPDATE strategy2_backtest_task_stocks
   SET status='PENDING'
   WHERE task_id=? AND status='RUNNING';
   ```

3. 不要再使用 `except Exception: pass`。

4. 只允许忽略明确可接受的数据库兼容异常；其他异常必须记录完整日志：

   ```python
   except sqlite3.OperationalError as exc:
       logger.warning("Unable to recover Strategy2 backtests on startup: %s", exc)
   ```

5. 启动恢复只负责将任务标记为可恢复，不要自动使用当前配置继续运行。

#### 必须新增测试

新增真实 `lifespan` 行为测试：

1. 创建 `running` 回测任务。
2. 创建一个 `RUNNING` 股票、一个 `COMPLETED` 股票。
3. 启动应用 lifespan。
4. 断言任务变为 `INTERRUPTED`。
5. 断言原 `RUNNING` 股票变为 `PENDING`。
6. 断言 `COMPLETED` 股票及其信号、机会保持不变。
7. 调用 `/api/strategy2/backtests/{task_id}/resume`，断言只恢复未完成股票。

---

### FINAL-002：可信基线未冻结和校验策略实现版本

#### 问题现象

任务表已经有：

```text
backtest_engine_version
strategy_engine_version
```

但当前新任务只写入固定值：

```python
backtest_engine_version="phase1-v1"
```

`strategy_engine_version` 从未写入，完整性校验也不检查两个引擎版本。

#### 代码证据

仓库搜索结果：

```text
strategy_engine_version=  无生产写入
backtest_engine_version="phase1-v1"  仅 server.py 一处固定写入
```

从 `77ea835` 到当前提交，回测器、汇总、执行器和策略相关行为已经多次修改，但
`backtest_engine_version` 仍然是同一个 `phase1-v1`。

当前实际数据库中的策略2回测任务：

```text
backtest_engine_version = phase1-v1
strategy_engine_version = NULL
```

#### 触发条件

1. 使用当前代码创建一个可信任务。
2. 修改策略评分、趋势、风险、信号合并、执行模型或回测器实现。
3. 使用相同配置和相同数据版本再次运行。

两个任务会拥有相同或缺失的实现版本标识，但结果可能不同。

#### 影响

- 无法判断结果变化来自数据、配置还是代码实现。
- 不同策略代码版本的任务可能被错误直接比较。
- 服务升级后恢复旧任务，会把旧结果和新代码生成的结果混在同一任务中。
- `TRUSTED_BASELINE` 不能真正代表可追溯的可信基线。

#### 精确修复步骤

1. 建立单一版本定义模块，例如：

   ```python
   # strategy2/version.py
   STRATEGY2_BACKTEST_ENGINE_VERSION = "phase1-v3"
   STRATEGY2_STRATEGY_ENGINE_VERSION = "strategy2-v2"
   ```

2. 新建任务时同时保存：

   ```text
   backtest_engine_version
   strategy_engine_version
   data_revision_version
   data_revision_id
   config_snapshot
   ```

3. `validate_strategy2_backtest_integrity()` 必须拒绝缺少任一实现版本的新任务。

4. `resume` 和 `retry-failed` 在启动前必须校验：

   ```python
   task.backtest_engine_version == 当前回测引擎版本
   task.strategy_engine_version == 当前策略引擎版本
   ```

5. 版本不一致时：

   - 返回 HTTP `409`。
   - 错误码使用 `ENGINE_REVISION_CHANGED`。
   - 不得在新代码下继续写入旧任务。
   - 保留旧任务已有结果，不要清理或重写。

6. 历史任务迁移规则：

   - 缺少 `strategy_engine_version` 的旧任务不得保留为当前可信基线。
   - 不要为历史任务伪造版本。
   - 已完整完成且版本明确的历史任务可以保留其原版本结果，但前端必须展示版本。

7. 每次修改以下任一行为时必须升级对应版本：

   ```text
   策略评分、趋势、风险、否决规则
   信号合并规则
   NEXT_OPEN 入场和退出语义
   周期表现计算
   影响结果的回测窗口和数据校验
   ```

#### 必须新增测试

- 新任务同时保存两个实现版本。
- 缺少策略引擎版本的任务不能成为 `TRUSTED_BASELINE`。
- 旧策略引擎版本任务恢复时返回 `ENGINE_REVISION_CHANGED`。
- 旧回测引擎版本任务失败重试时返回 `ENGINE_REVISION_CHANGED`。
- 版本不匹配时旧任务信号、机会和逐股结果不发生变化。
- 相同数据、配置和两个实现版本的任务结果集合完全一致。

---

### FINAL-003：前端缺少任务控制、失败明细和可信度展示

#### 问题现象

后端已经提供：

```text
POST /api/strategy2/backtests/{task_id}/resume
POST /api/strategy2/backtests/{task_id}/cancel
POST /api/strategy2/backtests/{task_id}/retry-failed
GET  /api/strategy2/backtests/{task_id}/stocks?status=FAILED
```

但 `web/src/composables/useApi.js` 和 `Strategy2Backtest.vue` 没有接入这些接口。

当前前端还存在以下行为：

- 不展示 `credibility_status`。
- 不展示 `backtest_engine_version`、`strategy_engine_version` 和
  `data_revision_version`。
- 不展示失败股票及失败原因。
- 没有恢复、取消、重试失败按钮。
- 汇总区域只在 `task.status === 'completed'` 时展示。
- `completed_with_errors`、`INTERRUPTED`、`CANCELED`、
  `DATA_REVISION_CHANGED` 没有明确操作入口和解释。
- 新任务结束轮询后只刷新任务列表，不自动加载本次任务详情。

#### 影响

- 用户无法从页面恢复中断任务。
- 用户无法取消长任务或重试失败股票。
- 用户无法判断任务是否为可信基线。
- 失败任务看不到失败股票和原因。
- 后端已完成的可靠性能力无法形成真实用户闭环。

#### 精确修复步骤

##### A. 扩展 `useApi.js`

新增并导出：

```javascript
resumeStrategy2Backtest(taskId)
cancelStrategy2Backtest(taskId)
retryFailedStrategy2Backtest(taskId)
getStrategy2BacktestStocks(taskId, status)
```

所有写接口必须返回：

```text
ok
statusCode
error/message
```

##### B. 扩展 `Strategy2Backtest.vue` 状态

增加：

```text
activeTaskId
failedStocks
actionPending
actionError
```

##### C. 展示可信度和版本

任务详情必须显示：

```text
credibility_status
backtest_engine_version
strategy_engine_version
data_revision_version
data_revision_id 前12位
execution_model
data_snapshot_date
```

颜色和文字必须明确区分：

```text
TRUSTED_BASELINE
PHASE1_INCOMPLETE
LEGACY_UNTRUSTED
RUNNING_UNVERIFIED
```

##### D. 根据状态显示操作按钮

| 任务状态 | 操作 |
|---|---|
| `running` | 取消 |
| `INTERRUPTED` / `CANCELED` 且有未完成股票 | 恢复 |
| `completed_with_errors` / 存在失败股票 | 重试失败股票 |
| `DATA_REVISION_CHANGED` / `ENGINE_REVISION_CHANGED` | 禁止恢复，明确解释 |
| `completed` | 只读查看 |

##### E. 展示失败股票

加载任务详情时同时请求：

```http
GET /api/strategy2/backtests/{task_id}/stocks?status=FAILED
```

表格至少展示：

```text
code
name
error_code
error_detail
started_at
finished_at
```

##### F. 修复完成后的自动刷新

启动任务时保存 `activeTaskId`。轮询发现任务结束后：

1. 停止轮询。
2. 加载 `activeTaskId` 的任务详情。
3. 加载机会、数据不足股票和失败股票。
4. 刷新任务列表。
5. 不要要求用户手动点击历史任务后才能看到结果。

##### G. 汇总展示条件

完整汇总不应只绑定 `status === 'completed'`。对于
`completed_with_errors`、`CANCELED`、`INTERRUPTED`，如果后端存在
`summary`，应展示汇总并明确标记“不可信/未完成”，不能伪装成可信结果。

#### 必须新增前端测试

- `running` 任务显示取消按钮，点击后调用正确接口。
- `INTERRUPTED` 任务显示恢复按钮。
- `completed_with_errors` 显示失败股票和重试按钮。
- `DATA_REVISION_CHANGED` 和 `ENGINE_REVISION_CHANGED` 不显示恢复按钮。
- `TRUSTED_BASELINE` 与 `LEGACY_UNTRUSTED` 标签正确。
- 轮询完成后自动加载刚完成任务详情。
- 操作接口失败时显示后端错误，不清空当前任务数据。

---

### FINAL-004：历史回测任务列表无分页和状态过滤

#### 问题现象

当前后端：

```python
SELECT * FROM strategy2_backtest_tasks ORDER BY started_at DESC
```

返回所有任务。前端也一次展示全部任务，没有状态过滤。

虽然列表接口已经移除 `config_snapshot` 和 `summary_json`，但任务数量持续增加后，
请求、渲染和任务定位仍会逐渐变慢。

#### 修复步骤

1. 修改列表接口：

   ```http
   GET /api/strategy2/backtests?page=1&page_size=20&status=completed
   ```

2. 后端使用：

   ```sql
   SELECT COUNT(*) ...
   SELECT 摘要字段 ...
   ORDER BY started_at DESC
   LIMIT ? OFFSET ?
   ```

3. 返回：

   ```json
   {
     "tasks": [],
     "total": 0,
     "page": 1,
     "page_size": 20
   }
   ```

4. 前端增加上一页、下一页和状态过滤。

5. 列表只返回摘要字段，继续禁止返回完整配置和汇总 JSON。

#### 必须新增测试

- 默认只返回第一页。
- `page_size` 有合理上限。
- 状态过滤返回正确总数。
- 第二页与第一页无重复任务。
- 列表响应不包含 `config_snapshot` 和 `summary_json`。

---

## 6. 建议修复顺序

1. 修复 `FINAL-001`，恢复服务重启后的任务状态闭环。
2. 修复 `FINAL-002`，冻结并校验策略与回测实现版本。
3. 修复 `FINAL-003`，完成前端任务操作和可信度展示。
4. 修复 `FINAL-004`，完成历史任务分页。
5. 运行一次小样本恢复/重试/取消集成测试。
6. 运行一次新的全市场可信基线任务并人工抽样核对。

---

## 7. 给修复 AI 的执行提示语

```text
请严格按照：
docs/reviews/2026-06-13-strategy2-phase1-final-acceptance-recheck.md
一次性修复 FINAL-001～FINAL-004。

本轮仅处理报告中的中、高等级问题。不要修改策略评分、趋势判断、风险规则、
否决规则、信号合并规则和 NEXT_OPEN 交易语义。

必须完成：

1. 修复 server.py lifespan 中未定义 conn 和静默吞异常的问题，确保服务重启后
   running 回测任务变为 INTERRUPTED，RUNNING 股票变为 PENDING，并可真实恢复。
2. 为新任务保存 backtest_engine_version 和 strategy_engine_version；完整性校验、
   resume、retry-failed 必须校验实现版本，版本变化返回 ENGINE_REVISION_CHANGED，
   禁止新旧代码结果混写。
3. 前端接入回测 resume、cancel、retry-failed 和失败股票接口；展示可信度、版本、
   失败原因，并在任务完成后自动加载本次任务详情。
4. 为历史回测任务列表增加后端分页、状态过滤和前端分页。
5. 不要为历史任务伪造策略版本或数据版本。
6. 不要删除或放宽现有数据版本、完整性和可信度校验。
7. 新增行为级后端测试和前端 Vitest，不能只断言函数存在或接口字符串。

交付时必须提供：

- FINAL-001～004 的逐项修改说明。
- 服务重启后任务和股票状态转换的测试结果。
- 引擎版本不一致时 resume/retry 拒绝且旧结果不变的测试结果。
- 前端恢复、取消、失败重试、可信度和失败股票展示的测试结果。
- 新任务保存的三个版本字段示例。
- 全部测试、构建和 git diff --check 结果。
```

---

## 8. 回归测试清单

```bash
python -m pytest tests/test_strategy2_medium_high_fixes.py -v
python -m pytest tests/test_strategy2_backtester.py tests/test_strategy2_independence.py -v
python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py --ignore=tests/test_yfinance_hist.py
python -m compileall scanner strategy2 server.py -q
npm --prefix web test -- --run
npm --prefix web run build
git diff --check
```

必须额外验证：

1. 服务重启前创建运行中任务，重启后任务可恢复。
2. 恢复只处理未完成股票，已完成股票结果不变。
3. 修改当前策略引擎版本后，旧任务恢复和失败重试均被拒绝。
4. 前端能看到失败股票原因并执行失败重试。
5. 前端能区分可信、未完成和旧版不可信任务。
6. 新任务完成后页面自动展示本次结果。
7. 历史任务分页和状态过滤正确。

---

## 9. 不建议修改

- 不要修改策略2正式评分阈值。
- 不要修改趋势、风险和一票否决规则。
- 不要修改信号合并和冷却期规则。
- 不要修改 `NEXT_OPEN` 入场和退出语义。
- 不要删除数据版本指纹或降低完整性校验条件。
- 不要自动把旧任务升级成当前可信版本。
- 不要为了前端展示把失败或中断任务改写为 `completed`。

---

## 10. 最终交付标准

修复完成后必须满足：

1. 服务重启后的运行中任务可以被准确标记并恢复。
2. 同一任务不会混用不同策略或回测实现版本。
3. 用户可在前端完成启动、取消、恢复、失败重试和结果查看闭环。
4. 用户能明确识别可信基线、未完成任务和旧版不可信任务。
5. 失败股票和失败原因可见。
6. 历史任务列表支持分页和状态过滤。
7. 后端、前端测试和构建全部通过。
8. 使用修复后的当前版本运行一个新的全市场任务，并生成
   `TRUSTED_BASELINE`，再宣布 Phase 1 最终完成。

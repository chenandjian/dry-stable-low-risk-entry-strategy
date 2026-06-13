# 策略2 Phase 1 最终验收报告

## 1. 检查范围

- 验收提交：`7a3430e fix(strategy2): complete phase1 backtest reliability`
- 基线提交：`997d8f8`
- 重点模块：
  - `strategy2/backtest_service.py`
  - `strategy2/backtester.py`
  - `scanner/db.py`
  - `server.py`
  - `web/src/pages/Strategy2Backtest.vue`
  - `tests/test_strategy2_medium_high_fixes.py`
- 本报告只记录中、高等级问题。

---

## 2. 验收结论

上一轮 MH-001～MH-005 的主体功能已经完成：

- `resume` 已真实恢复未完成股票。
- `retry-failed` 已真实重试失败股票。
- `cancel` 已真实通知执行线程停止。
- 取消任务不会成为可信基线。
- 完整零机会任务可生成完整零值汇总。
- 汇总漏斗和目标、止损平均触发天数已经生成。
- 逐股开始时间、结束时间、数据区间和无数据路径进度已经补齐。
- 相同数据版本的任务已有可重复性测试。

但当前仍存在 **2 个高等级问题、1 个中等级问题**，因此暂不建议将 Phase 1
标记为最终验收通过。

---

## 3. 问题清单

| 编号 | 问题 | 严重程度 | 影响范围 | 必须修复 |
|---|---|---:|---|---|
| ACCEPT-001 | 数据版本指纹遗漏 `turnover`，无法检测影响策略结果的数据变化 | 高 | 可重复性、可信基线、恢复与重试 | 是 |
| ACCEPT-002 | 历史不可信任务仍保留 `TRUSTED_BASELINE` 状态 | 高 | 历史结果可信度、用户判断 | 是 |
| ACCEPT-003 | 数据版本计算无论任务范围大小都会扫描全市场日线 | 中 | 启动延迟、恢复与重试性能 | 是 |

---

## 4. 已确认通过

### 4.1 任务控制闭环

- 恢复接口只选择 `PENDING` 和遗留 `RUNNING` 股票。
- 失败重试接口只选择 `FAILED` 股票。
- 恢复和重试使用原任务配置、日期范围和数据快照。
- 数据版本变化时恢复接口返回 `DATA_REVISION_CHANGED`。
- 取消任务保留未处理股票，并被标记为不可信。

### 4.2 可信度边界

- `CANCELED` 任务会被完整性校验拒绝。
- 完整执行但零机会的任务会生成 3/5/10/20 日完整零值汇总。
- 完整性校验要求任务状态必须为 `completed`。

### 4.3 汇总和逐股审计

- 汇总生成漏斗统计。
- 汇总生成 `avg_days_to_target` 和 `avg_days_to_stop`。
- 逐股记录真实 `started_at`、`finished_at`。
- 保存 `invalid_data_days`、`earliest_date`、`latest_date`。
- `NO_LOCAL_DATA` 路径会更新实时处理进度。

### 4.4 验证结果

| 验证项 | 结果 |
|---|---|
| 策略2专项与验收测试 | 70 passed |
| 后端离线全量测试 | 518 passed，1 warning |
| 前端 Vitest | 25 passed |
| 前端构建 | 通过 |
| Python 编译检查 | 通过 |
| `git diff --check` / `git show --check` | 通过 |

---

## 5. 详细问题分析

### ACCEPT-001：数据版本指纹遗漏 `turnover`

#### 问题现象

数据版本函数当前查询：

```python
SELECT code,date,open,high,low,close,volume
FROM daily_ohlc
```

没有包含 `turnover`。

但策略2回测在流动性过滤中明确使用：

```python
turnovers = [d.get("turnover") or (d["volume"] * d["close"]) for d in recent]
latest_turnover = latest.get("turnover") or (latest["volume"] * latest["close"])
```

#### 直接复现

同一股票的成交额从 `1,000` 修改为 `200,000,000`：

```text
数据版本指纹：完全相同
修改前流动性过滤：False
修改后流动性过滤：True
```

也就是说，策略输入和结果已经发生变化，但数据版本检查认为数据没有变化。

#### 影响

- 恢复任务可能读取与原任务不同的流动性数据。
- 相同 `data_revision_id` 可能产生不同信号和机会。
- 数据版本校验无法保证可信基线可复现。
- 当前新增的可重复性测试没有覆盖 `turnover` 变化。

#### 修复方案

版本指纹必须包含所有能够影响回测结果的本地行情字段：

```sql
SELECT code, date, open, high, low, close, volume, turnover
FROM daily_ohlc
...
```

测试必须新增：

```python
def test_daily_ohlc_revision_changes_when_turnover_changes(...):
    ...
```

验收条件：

1. 仅修改 `turnover` 后，`data_revision_id` 必须变化。
2. 恢复和失败重试必须拒绝成交额已经变化的任务。
3. 两个具有相同 `data_revision_id` 的任务，其流动性过滤、信号和机会集合必须一致。

---

### ACCEPT-002：历史不可信任务仍保留 `TRUSTED_BASELINE`

#### 问题现象

当前兼容迁移只处理：

```sql
WHERE credibility_status IS NULL
```

不会重新检查已经标记为 `TRUSTED_BASELINE` 的旧任务。

实际数据库中存在 **11 个** 不满足当前可信规则但仍标记为可信的任务，包括：

- `status=failed` 但 `credibility_status=TRUSTED_BASELINE`
- `status=running` 但 `credibility_status=TRUSTED_BASELINE`
- `data_revision_id=NULL` 但 `credibility_status=TRUSTED_BASELINE`

示例：

```text
s2bt-20260612-155148-0mlpq9
status = failed
credibility_status = TRUSTED_BASELINE
data_revision_id = NULL
processed_stocks = 0
```

重新执行 `db.init_db()` 后，该错误状态仍不会被修正。

#### 影响

- 前端历史列表会继续把旧失败任务或不可复现任务展示为可信基线。
- 用户可能使用旧的不可信结果进行策略优化和任务对比。
- 新的可信度规则只约束新任务，没有修复历史数据。

#### 修复方案

兼容迁移必须降级所有不满足当前可信基础条件的历史任务：

```sql
UPDATE strategy2_backtest_tasks
SET credibility_status='LEGACY_UNTRUSTED',
    backtest_engine_version=COALESCE(backtest_engine_version, 'legacy-v1')
WHERE credibility_status='TRUSTED_BASELINE'
  AND (
    LOWER(COALESCE(status, '')) <> 'completed'
    OR data_revision_id IS NULL
    OR data_revision_id = ''
    OR summary_json IS NULL
  );
```

建议再执行完整性条件的保守检查：

- `processed_stocks != total_stocks`
- 存在 `PENDING/RUNNING`
- `failed_stocks_count > 0`
- `evaluation_error_days > 0`

不要为旧任务补造 `data_revision_id`，因为无法证明当时使用的数据内容。旧任务只能降级，
不能升级为可信。

测试必须新增：

1. `failed + TRUSTED_BASELINE` 旧任务在重新初始化后被降级。
2. `completed + data_revision_id NULL + TRUSTED_BASELINE` 被降级。
3. 满足新规则的新任务不会被错误降级。

---

### ACCEPT-003：数据版本计算无论任务范围大小都会扫描全市场日线

#### 问题现象

当前实现先查询快照日期前的全市场数据：

```python
rows = conn.execute(
    "SELECT ... FROM daily_ohlc WHERE date<=? ORDER BY code,date",
    ...
).fetchall()
```

然后在 Python 中按 `codes` 过滤。

在当前数据库约 172 万条日线数据下，实测：

| 任务范围 | 指纹耗时 |
|---|---:|
| 单只股票 | 约 2.9 秒 |
| 全市场 | 约 15.0 秒 |

单只股票任务仍会读取全市场行。任务启动时同步计算一次，执行前后还会再次校验，因此快速
任务和恢复操作会产生明显额外延迟。

#### 影响

- 单股和小样本回测启动明显变慢。
- 启动 API 在计算指纹期间同步阻塞。
- 全市场任务执行前后增加额外数据库读压。

#### 修复方案

按任务股票范围在 SQL 层过滤，不要先读取全表再由 Python 丢弃。

推荐使用任务股票表关联，避免大量 `IN` 参数：

```sql
SELECT o.code,o.date,o.open,o.high,o.low,o.close,o.volume,o.turnover
FROM daily_ohlc o
JOIN strategy2_backtest_task_stocks s ON s.code=o.code
WHERE s.task_id=? AND o.date<=?
ORDER BY o.code,o.date;
```

将版本函数改为基于 `task_id` 计算：

```python
calculate_task_daily_ohlc_revision(task_id, snapshot_date)
```

验收条件：

- 单股任务只读取该股票日线。
- 指纹结果与原稳定排序规则一致。
- 单股版本计算不应随全市场数据量线性增长。

---

## 6. 建议修复顺序

1. 修复 ACCEPT-001，将 `turnover` 纳入数据版本。
2. 修复 ACCEPT-002，降级历史不可信任务。
3. 修复 ACCEPT-003，将版本计算过滤下推到 SQL。
4. 新建两次相同数据版本任务，验证信号与机会集合完全一致。
5. 再执行最终验收测试。

---

## 7. 给修复 AI 的提示语

```text
请严格按照：
docs/reviews/2026-06-13-strategy2-phase1-final-acceptance.md
修复剩余验收问题。

本轮只处理 ACCEPT-001～003，不修改策略评分、趋势、风险、信号合并和 NEXT_OPEN
执行语义。

必须完成：

1. 数据版本指纹纳入 turnover，确保所有影响策略结果的 daily_ohlc 字段均被覆盖。
2. 新增 turnover 变化导致版本变化、恢复拒绝的行为测试。
3. 兼容迁移降级所有不满足当前可信规则的历史 TRUSTED_BASELINE 任务。
4. 禁止为历史任务伪造 data_revision_id。
5. 数据版本计算在 SQL 层按任务股票范围过滤，避免单股任务扫描全市场日线。
6. 保持当前 resume、retry-failed、cancel、零机会汇总、漏斗和逐股审计实现。

交付时提供：

- ACCEPT-001～003 对应修改说明。
- 历史任务降级数量和 SQL 验证结果。
- turnover 修改前后的 data_revision_id。
- 单股和全市场版本计算耗时。
- 全部测试和构建结果。
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
```

---

## 9. 最终交付标准

1. 修改任何影响回测的日线字段都会改变数据版本。
2. 数据版本相同的任务结果可以复现。
3. 历史失败、运行中、无数据版本任务不再显示为可信基线。
4. 单股任务的数据版本计算不扫描全市场日线。
5. 恢复、重试、取消、汇总和审计功能保持通过。
6. 后端和前端测试全部通过。

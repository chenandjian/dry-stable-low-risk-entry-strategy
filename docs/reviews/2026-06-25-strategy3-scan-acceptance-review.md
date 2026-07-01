# 策略3正式扫描验收审核报告

## 1. 检查范围

本次验收覆盖策略3「强势回踩二次启动」正式扫描闭环：

- 策略3配置、模型、数据校验和唯一评估入口。
- 策略3指标、趋势、回踩、缩量企稳、二次转强、风险收益和评分模块。
- `strategy3_candidates` 独立候选表及 CRUD。
- 策略3全市场扫描、失败重试、基于本地缓存的重新评估。
- FastAPI 策略3扫描、任务、候选、失败重试、重新评估接口。
- 前端扫描控制台三策略入口、策略3配置区、任务中心、策略3结果页。
- 策略1/策略2隔离与关键回归。

## 2. 总体结论

策略3正式扫描主链路已实现并通过验收。当前未发现未修复的中/高等级问题。

本轮审核发现 1 个中等级数据一致性问题：策略3重新评估只更新 `strategy3_candidates`，未同步 `task_stocks.status`，会导致任务中心候选数、DB 汇总和结果页候选表不一致。该问题已修复，并补充回归测试。

## 3. 问题清单

| 编号 | 问题 | 严重程度 | 影响范围 | 状态 |
| --- | --- | --- | --- | --- |
| ACCEPT-001 | 策略3重新评估未同步 `task_stocks` 终态 | 中 | 任务中心 / 扫描汇总 / 候选数一致性 | 已修复 |

## 4. 中高等级问题分析

### ACCEPT-001：策略3重新评估未同步任务股票终态

#### 问题现象

策略3任务执行“重新扫描策略”后，候选表中已经有新候选，但 `task_stocks` 中对应股票仍可能保持 `pending` 或旧状态。

由于 `scanner.db.refresh_scan_task_counts()` 的候选数来自：

```text
task_stocks.status = 'candidate'
```

这会导致任务中心显示的候选数与 `/api/strategy3/candidates` 返回的候选列表不一致。

#### 涉及模块

- `strategy3/scanner.py::re_evaluate_strategy3_task()`
- `scanner/db.py::refresh_scan_task_counts()`
- `tests/test_strategy3_db_api.py`

#### 原因

`re_evaluate_strategy3_task()` 之前只在评估通过时调用：

```python
db.upsert_strategy3_candidate(task_id, discovery)
```

但没有同时调用 `db.update_task_stock(..., status="candidate")`。未通过、流动性过滤、本地 K 线缺失、评估异常等路径也没有统一写入终态。

#### 修复结果

已在 `re_evaluate_strategy3_task()` 中补齐逐股终态同步：

- 本地 K 线缺失：`failed / MISSING_LOCAL_OHLC`
- 流动性未通过：`skipped / LIQUIDITY_FILTER_REJECTED`
- 策略3通过：`candidate`
- 策略3未通过：`scanned / evaluation.status_reason`
- 评估异常：`failed / STRATEGY3_EVALUATION_ERROR`

并保留旧候选移除逻辑：重新评估后不再符合策略3的旧候选会从 `strategy3_candidates` 删除，并将原 `candidate` 状态改为 `scanned`。

#### 验证方式

新增测试：

- `test_re_evaluate_strategy3_task_uses_cached_ohlc`
  - 验证重新评估后候选表有记录。
  - 验证 `task_stocks.status == 'candidate'`。
  - 验证 `refresh_scan_task_counts()["candidates_count"] == 1`。

新增测试：

- `test_strategy3_running_status_includes_live_failed_counts`
  - 验证策略3运行态 status 能返回实时 failed 计数，防止前端进度显示和 DB 汇总脱节。

## 5. 已运行验证

后端专项：

```bash
python -m pytest tests/test_strategy3_validation.py tests/test_strategy3_engine.py tests/test_strategy3_independence.py tests/test_strategy3_db_api.py -q
```

结果：`22 passed`

策略1/策略2关键回归：

```bash
python -m pytest tests/test_strategy2_engine.py tests/test_strategy2_independence.py tests/test_strategy2_final_fixes.py tests/test_server_scan_api.py -q
```

结果：`49 passed`

Python 编译：

```bash
python -m compileall scanner strategy2 strategy3 server.py -q
```

结果：退出码 `0`

前端全量测试：

```bash
npm --prefix web test -- --run
```

结果：`7 passed / 43 passed`

前端生产构建：

```bash
npm --prefix web run build
```

结果：`built in 2.09s`

## 6. 残余风险

- 策略3目前只实现正式扫描，不包含回测；回测应按第二阶段独立设计实现，不能复用策略2回测表或机会合并逻辑。
- 策略3相对强度在没有市场指数数据时使用自身 `return_60` 作为保守替代，后续若引入指数相对强度，需要补充市场数据截断和未来数据泄漏测试。
- 前端结果页已覆盖候选字段展示和刷新失败保留旧数据，但尚未做真实浏览器人工验收；建议联调时用一个策略3任务检查 `/strategy3/results?task=<id>`。

## 7. 回测第二计划入口

策略3回测不在本次正式扫描计划内。后续如启动策略3回测，应单独编写计划并至少覆盖：

- 只读本地 `daily_ohlc`，不请求外部行情源。
- 信号日、入场日、止损、目标、失败原因可追溯。
- 原始信号、机会合并、逐股状态和汇总完整性独立建表。
- 不复用策略1杯柄/VCP回测逻辑，不复用策略2短线机会合并逻辑。

# Plan: 修复 daily_kline_days 250→500 后候选不显示

## Context

用户将 `config.data.daily_kline_days` 从 250 改为 500 后，前端「机会雷达」显示「跳过 2522 · 失败 0 · 候选 3」，但左侧候选面板为空。候选数量统计正确（3），但候选列表未渲染。

关键线索：250 时正常，500 时异常。问题出在扫描完成后候选持久化或前端加载环节。

## 根因假设

`scan_all()` 的 `candidate_by_code` 被正确填充（所以轮询显示的 `candidates_found=3`），但 `result["candidates"]` 返回后，`save_candidates()` 未执行或执行失败，导致 DB 中无候选记录。前端 `loadResults()` 查 DB 返回空。

最可能的触发条件：`kline_days=500` 时数据拉取耗时更长，某些边界条件（锁忙重试、超时）改变了 worker 的执行时序，导致 `candidate_by_code` 与 `result["candidates"]` 不一致。

## 诊断步骤

1. **在 server.py 扫描线程中加日志**，打印 `scan_all()` 返回值：

```python
# server.py 约 279 行之后
result = scan_all(config, ...)
logger.info("scan_all returned: candidates=%d, stats.candidates_found=%d, stats.scanned=%d",
            len(result["candidates"]), result["stats"].get("candidates_found", 0),
            result["stats"].get("scanned", 0))
```

2. **在 `save_candidates` 调用前后加日志**：
```python
if result["candidates"]:
    logger.info("save_candidates: saving %d candidates for task %s", len(result["candidates"]), task_id)
    db.save_candidates(task_id, result["candidates"], ...)
    logger.info("save_candidates: done")
else:
    logger.warning("result['candidates'] is EMPTY despite scan completion")
```

3. 修改 `daily_kline_days` 为 500，重启服务，执行扫描，查看日志。

## 预期修复

根据日志确认根因后，最可能的修复是：

### 场景 A：`result["candidates"]` 为空但 `task_stocks` 有 candidate 状态

安全网已存在但可能未生效。检查 `re_evaluate_task` 是否抛异常：
- `server.py` 安全网路径加 try/except 日志
- 确保 `re_evaluate_task` 内 `db.get_ohlc(code, max_rows=kline_days)` 在 kline_days=500 时正确返回数据

### 场景 B：`result["candidates"]` 非空但 `save_candidates` 失败

- `save_candidates` 全部用 `.get()` 取值，不会因缺 key 崩溃
- 但 DB 写入可能失败（列数不匹配、unique constraint 等）
- 加 try/except 日志

### 场景 C：`save_candidates` 成功但前端 `getCandidates` 查不到

- 前端 `loadResults` 调 `/api/candidates`，该端点查 `db.get_candidates()`（无 task_id 时取最新已完成任务的候选项）
- 检查 DB 中 candidates 表是否有该 task_id 的记录

## 修改文件

- `server.py` — 扫描线程加诊断日志（约 279-306 行）
- 不修改业务逻辑，仅加日志定位根因

## 验证

1. 改 `daily_kline_days=500`，启动 `python main.py serve`
2. 触发扫描，查看服务端日志中的 `scan_all returned:` 行
3. 检查 `data/cuphandle.db` 中 `SELECT COUNT(*) FROM candidates WHERE task_id='<最新task_id>'`
4. 根据日志输出确定根因后再编写修复代码

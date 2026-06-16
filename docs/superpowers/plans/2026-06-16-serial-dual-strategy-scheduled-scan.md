# 串行双策略定时扫描实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 新增一个周一至周五 15:15 执行的串行扫描任务：先执行策略1，等待策略1全部股票处理完成；策略1失败股票最多按失败列表重试 3 轮；策略1完整结束后再执行策略2，让策略2复用策略1刚拉取和记录过的股票历史日线数据，避免策略2再次重复请求各个外部数据源；全流程具备日志、异常处理和防重复执行锁。

**架构：** 在 `scheduler/scheduler.py` 增加调度编排层，不改策略1/策略2判断规则。调度任务直接复用现有 `scanner.engine.scan_all()`、`strategy2.scanner.scan_strategy2_all()`、`scanner.db.scan_tasks/task_stocks`，通过 DB 任务状态和模块级锁保证串行与防重复执行。失败重试只针对策略1 `task_stocks.status='failed'` 列表，每轮重试后重新查询失败列表，最多 3 轮。策略2仍调用自己的扫描入口，但由于策略1任务已在当天写入 `daily_ohlc` 和 `task_stocks.kline_latest_date`，策略2的共享日线服务应命中同日新鲜缓存，不应对策略1已成功处理的股票重复请求外部数据源。

**技术栈：** Python 3.10+、APScheduler `BackgroundScheduler`、SQLite DB helper、pytest、现有扫描引擎。

---

## 1. 检查范围

- 调度入口：`scheduler/scheduler.py`
- CLI 调度启动：`main.py schedule` 通过 `start_scheduler(config)` 间接受影响
- 策略1扫描：`scanner/engine.py::scan_all()`
- 策略2扫描：`strategy2/scanner.py::scan_strategy2_all()`
- 任务与失败列表：`scanner/db.py::create_scan_task()`、`save_task_stocks()`、`get_task_stocks()`、`refresh_scan_task_counts()`、`finish_scan_task()`、`get_running_task()`
- 配置：`config.yaml` 的 `scheduler` 段
- 测试：新增 `tests/test_scheduler_serial_dual_scan.py`

不修改内容：

- 不修改策略1 `CupHandleStrategyEngine.evaluate_at()` 入选规则。
- 不修改策略2 `ExtremeDryStableStrategyEngine.evaluate_at()` 入选规则。
- 不修改前端页面。
- 不新增数据库表，不做破坏性 schema 变更。

---

## 2. 关键业务规则

1. 定时触发时间：周一至周五 15:15。
2. 串行顺序：策略1全量扫描结束后，才允许执行策略2。这个顺序的核心目的，是让策略2复用策略1刚拉取的股票历史日线数据，减少重复拉取时间和外部数据源压力。
3. 策略1失败重试：策略1全量扫描完成后，如果 `task_stocks` 中存在 `status='failed'` 股票，只对失败列表重试；最多 3 轮。
4. 重试收敛：每轮重试都重新查询失败列表；若失败数为 0，立即停止重试并进入策略2。
5. 策略2执行条件：策略1全量扫描和最多 3 轮失败重试流程已结束。即使策略1仍有失败股票，也视为策略1流程完整结束，然后继续策略2，并在日志中记录剩余失败数。
6. 策略2数据复用要求：策略1成功处理过的股票，策略2应通过现有 `db.get_today_task_stock_latest_date()` / `daily_ohlc` 新鲜缓存机制复用本地数据；策略1仍失败的股票可以由策略2按自身扫描逻辑尝试拉取，但必须保留现有“外部数据源全部失败则进入失败列表，不使用旧缓存产出结果”的规则。
7. 防重复执行：同一进程内使用模块级 `threading.Lock`；如果上一次串行任务仍在执行，本次触发直接跳过并写 warning 日志。
8. 跨进程/跨入口防重复：启动前检查 `db.get_running_task()`；如果 DB 中已有 `status='running'` 的策略1或策略2扫描任务，跳过本次串行任务并写 info 日志。
9. 异常处理：任一阶段异常必须写 error 日志；当前阶段已创建的 `scan_tasks` 要标记为 `failed` 并写入 `error`、`finished_at`；锁必须释放。
10. 日志要求：每个阶段开始、结束、失败数、候选数、耗时、跳过原因都要有日志。

---

## 3. 配置设计

在 `config.yaml` 的 `scheduler` 段新增串行任务配置：

```yaml
scheduler:
  enabled: false
  cron: 30 15 * * 1-5
  skip_if_running: true
  on_complete: log
  webhook_url: null
  serial_dual_scan:
    enabled: true
    cron: 15 15 * * 1-5
    strategy1_failed_retry_rounds: 3
```

解释：

- `scheduler.enabled` 仍然是总开关，保持现有行为兼容。
- `scheduler.serial_dual_scan.enabled` 控制新串行双策略任务是否注册，默认按缺失视为 `true`。
- `scheduler.serial_dual_scan.cron` 默认 `15 15 * * 1-5`。
- `scheduler.serial_dual_scan.strategy1_failed_retry_rounds` 默认 `3`，小于 0 时按 `0` 处理，大于 10 时建议限制为 `10` 防止配置错误导致长时间重试。
- 旧的 `scheduler.cron` 保留兼容，但实现时建议：如果启用 `serial_dual_scan`，不再注册旧的单策略 `daily_scan`，避免 15:15 串行任务和 15:30 旧策略1任务重复拉取。

---

## 4. 文件职责

- 修改 `scheduler/scheduler.py`
  - 新增串行任务编排函数 `run_serial_dual_strategy_scan(config)`。
  - 新增内部 helper：任务 ID 生成、任务失败标记、失败股票查询、单阶段完成持久化。
  - `start_scheduler(config)` 注册新 job：`serial_dual_strategy_scan`。
  - 保留 `stop_scheduler()` 行为。

- 修改 `config.yaml`
  - 增加 `scheduler.serial_dual_scan` 默认配置。

- 新增 `tests/test_scheduler_serial_dual_scan.py`
  - 覆盖调度注册、串行顺序、失败重试、防重复锁、异常中断。

- 可选修改 `README.md`
  - 如果实现后需要对用户说明新调度任务，可补充一句；本计划不强制。

---

## 5. 详细实现任务

### 任务 1：为串行调度写失败测试

**文件：**

- 创建：`tests/test_scheduler_serial_dual_scan.py`
- 修改：无

- [ ] **步骤 1：编写失败测试：注册 15:15 串行任务**

```python
def test_start_scheduler_registers_serial_dual_scan_job(monkeypatch):
    from scheduler import scheduler as sched_mod

    added = []

    class FakeScheduler:
        running = False

        def add_job(self, func, trigger, **kwargs):
            added.append({"func": func, "trigger": trigger, **kwargs})

        def start(self):
            self.running = True

    monkeypatch.setattr(sched_mod, "BackgroundScheduler", FakeScheduler)

    sched_mod.start_scheduler({
        "scheduler": {
            "enabled": True,
            "serial_dual_scan": {
                "enabled": True,
                "cron": "15 15 * * 1-5",
            },
        },
        "data": {"database_path": "data/test.db"},
    })

    assert len(added) == 1
    job = added[0]
    assert job["id"] == "serial_dual_strategy_scan"
    assert job["minute"] == "15"
    assert job["hour"] == "15"
    assert job["day_of_week"] == "1-5"
```

- [ ] **步骤 2：运行测试验证失败**

运行：

```bash
python -m pytest tests/test_scheduler_serial_dual_scan.py::test_start_scheduler_registers_serial_dual_scan_job -q
```

预期：失败，原因是当前 `start_scheduler()` 只注册旧 `daily_scan`，没有 `serial_dual_strategy_scan`。

- [ ] **步骤 3：编写失败测试：策略1先于策略2，策略1失败最多重试 3 轮**

```python
def test_serial_scan_runs_strategy1_retries_failed_then_strategy2(monkeypatch, tmp_path):
    from scheduler import scheduler as sched_mod
    from scanner import db

    db_path = tmp_path / "cuphandle.db"
    config = {"data": {"database_path": str(db_path)}, "scheduler": {"serial_dual_scan": {"strategy1_failed_retry_rounds": 3}}}
    db.init_db(str(db_path))

    calls = []

    def fake_stock_pool(config):
        return [
            {"code": "000001", "name": "A", "market": "SZ"},
            {"code": "000002", "name": "B", "market": "SZ"},
        ]

    def fake_scan_all(config, task_id=None, stocks=None, retry_policy="normal", **kwargs):
        calls.append(("s1", retry_policy, [s["code"] for s in (stocks or [])]))
        if retry_policy == "normal":
            db.update_task_stock(task_id, "000001", status="scanned", finished_at="2026-06-16 15:16:00")
            db.update_task_stock(task_id, "000002", status="failed", status_reason="fetch failed", finished_at="2026-06-16 15:16:00")
        elif len([c for c in calls if c[0] == "s1" and c[1] == "failed_only"]) < 3:
            db.update_task_stock(task_id, "000002", status="failed", status_reason="fetch failed again", finished_at="2026-06-16 15:17:00")
        else:
            db.update_task_stock(task_id, "000002", status="scanned", finished_at="2026-06-16 15:18:00")
        summary = db.refresh_scan_task_counts(task_id)
        return {"task_id": task_id, "candidates": [], "stats": {"candidates_found": 0, "elapsed_seconds": 1, **summary}}

    def fake_scan_strategy2_all(config, task_id=None, stocks=None, **kwargs):
        calls.append(("s2", "normal", [s["code"] for s in (stocks or [])]))
        for stock in stocks:
            db.update_task_stock(task_id, stock["code"], status="scanned", finished_at="2026-06-16 15:19:00")
        summary = db.refresh_scan_task_counts(task_id)
        return {"task_id": task_id, "candidates": [], "stats": {"candidates_found": 0, "elapsed_seconds": 1, **summary}}

    monkeypatch.setattr(sched_mod.stock_pool, "get_a_stock_pool", fake_stock_pool)
    monkeypatch.setattr(sched_mod, "scan_all", fake_scan_all)
    monkeypatch.setattr(sched_mod, "scan_strategy2_all", fake_scan_strategy2_all)
    monkeypatch.setattr(sched_mod.time, "strftime", lambda fmt: "20260616-151500" if "%Y%m%d" in fmt else "2026-06-16 15:15:00")

    result = sched_mod.run_serial_dual_strategy_scan(config)

    assert result["status"] == "completed"
    assert [c[0] for c in calls] == ["s1", "s1", "s1", "s1", "s2"]
    assert calls[1][1] == "failed_only"
    assert calls[1][2] == ["000002"]
    assert calls[-1][0] == "s2"
```

- [ ] **步骤 4：运行测试验证失败**

运行：

```bash
python -m pytest tests/test_scheduler_serial_dual_scan.py::test_serial_scan_runs_strategy1_retries_failed_then_strategy2 -q
```

预期：失败，原因是 `run_serial_dual_strategy_scan` 尚不存在。

- [ ] **步骤 5：编写失败测试：锁占用时跳过**

```python
def test_serial_scan_skips_when_lock_already_held(monkeypatch, tmp_path):
    from scheduler import scheduler as sched_mod

    calls = []
    monkeypatch.setattr(sched_mod, "scan_all", lambda *args, **kwargs: calls.append("s1"))

    assert sched_mod._serial_scan_lock.acquire(blocking=False) is True
    try:
        result = sched_mod.run_serial_dual_strategy_scan({
            "data": {"database_path": str(tmp_path / "cuphandle.db")},
            "scheduler": {},
        })
    finally:
        sched_mod._serial_scan_lock.release()

    assert result["status"] == "skipped"
    assert result["reason"] == "already_running_in_process"
    assert calls == []
```

- [ ] **步骤 6：运行测试验证失败**

运行：

```bash
python -m pytest tests/test_scheduler_serial_dual_scan.py::test_serial_scan_skips_when_lock_already_held -q
```

预期：失败，原因是 `_serial_scan_lock` 或 `run_serial_dual_strategy_scan` 尚不存在。

- [ ] **步骤 7：编写失败测试：策略1异常时不启动策略2并标记失败**

```python
def test_serial_scan_marks_strategy1_failed_and_does_not_start_strategy2(monkeypatch, tmp_path):
    from scheduler import scheduler as sched_mod
    from scanner import db

    db_path = tmp_path / "cuphandle.db"
    config = {"data": {"database_path": str(db_path)}, "scheduler": {}}
    db.init_db(str(db_path))

    monkeypatch.setattr(sched_mod.stock_pool, "get_a_stock_pool", lambda config: [{"code": "000001", "name": "A"}])

    def boom(*args, **kwargs):
        raise RuntimeError("strategy1 boom")

    s2_calls = []
    monkeypatch.setattr(sched_mod, "scan_all", boom)
    monkeypatch.setattr(sched_mod, "scan_strategy2_all", lambda *args, **kwargs: s2_calls.append("s2"))
    monkeypatch.setattr(sched_mod.time, "strftime", lambda fmt: "20260616-151500" if "%Y%m%d" in fmt else "2026-06-16 15:15:00")

    result = sched_mod.run_serial_dual_strategy_scan(config)

    assert result["status"] == "failed"
    assert "strategy1 boom" in result["error"]
    assert s2_calls == []

    tasks = db.get_scan_tasks(strategy_type="STRATEGY_1_CUP_HANDLE")
    assert tasks[0]["status"] == "failed"
    assert "strategy1 boom" in tasks[0]["error"]
```

- [ ] **步骤 8：运行测试验证失败**

运行：

```bash
python -m pytest tests/test_scheduler_serial_dual_scan.py::test_serial_scan_marks_strategy1_failed_and_does_not_start_strategy2 -q
```

预期：失败，原因是串行任务实现不存在。

---

### 任务 2：实现串行扫描编排

**文件：**

- 修改：`scheduler/scheduler.py`
- 测试：`tests/test_scheduler_serial_dual_scan.py`

- [ ] **步骤 1：调整导入和模块级锁**

在 `scheduler/scheduler.py` 顶部导入：

```python
import threading
import time

import scanner.db as db
from scanner import stock_pool
from strategy2.scanner import scan_strategy2_all
```

新增模块级锁：

```python
_serial_scan_lock = threading.Lock()
```

- [ ] **步骤 2：新增 helper：Cron 解析**

在 `scheduler/scheduler.py` 新增：

```python
def _parse_cron_parts(cron: str) -> dict:
    parts = str(cron or "").split()
    if len(parts) != 5:
        raise ValueError(f"Invalid scheduler cron: {cron}")
    return {
        "minute": parts[0],
        "hour": parts[1],
        "day": parts[2],
        "month": parts[3],
        "day_of_week": parts[4],
    }
```

用途：避免旧代码多处直接 `cron.split()[i]`，也让错误配置有明确异常。

- [ ] **步骤 3：新增 helper：生成唯一任务 ID**

```python
def _make_scan_task_id(prefix: str) -> str:
    return f"{prefix}-{time.strftime('%Y%m%d-%H%M%S')}"
```

建议前缀：

- 策略1：`sched-s1`
- 策略2：`sched-s2`

如果同一秒重复触发导致主键冲突，锁会阻止同进程重复；跨进程会被 DB running task 检查拦截。

- [ ] **步骤 4：新增 helper：标记任务失败**

```python
def _mark_scan_task_failed(task_id: str, error: str):
    conn = db.get_conn()
    conn.execute(
        "UPDATE scan_tasks SET status='failed', error=?, finished_at=? WHERE id=?",
        (error, time.strftime("%Y-%m-%d %H:%M:%S"), task_id),
    )
    conn.commit()
```

要求：只更新当前串行流程创建的任务，不批量改其他 running task。

- [ ] **步骤 5：新增 helper：完成任务持久化**

```python
def _finish_scan_task_from_summary(task_id: str, stats: dict):
    summary = db.refresh_scan_task_counts(task_id)
    db.finish_scan_task(
        task_id,
        time.strftime("%Y-%m-%d %H:%M:%S"),
        candidates_count=int(stats.get("candidates_found") or summary.get("candidates_count") or 0),
        elapsed_seconds=float(stats.get("elapsed_seconds") or 0),
        scanned=int(summary.get("processed") or 0),
        skipped=int(summary.get("skipped") or 0),
    )
    return summary
```

说明：`scan_all()` 和 `scan_strategy2_all()` 本身只刷新计数，不负责把任务状态置为 completed。调度层必须显式调用 `db.finish_scan_task()`。

- [ ] **步骤 6：新增 helper：查询失败股票**

```python
def _get_failed_stocks(task_id: str) -> list[dict]:
    return db.get_task_stocks(task_id, status="failed", limit=100000, offset=0)
```

注意：返回的数据已经包含 `code/name/market`，可直接传入 `scan_all(..., stocks=failed_stocks, retry_policy='failed_only')`。

- [ ] **步骤 7：实现 `run_serial_dual_strategy_scan(config)`**

核心结构：

```python
def run_serial_dual_strategy_scan(config: dict) -> dict:
    if not _serial_scan_lock.acquire(blocking=False):
        logger.warning("Serial dual strategy scan skipped: previous run is still active")
        return {"status": "skipped", "reason": "already_running_in_process"}

    s1_task_id = None
    s2_task_id = None
    started = time.time()
    try:
        db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
        db.init_db(db_path)

        running = db.get_running_task()
        if running:
            logger.info(
                "Serial dual strategy scan skipped: DB task already running id=%s strategy=%s",
                running.get("id"), running.get("strategy_type"),
            )
            return {"status": "skipped", "reason": "already_running_in_db", "running_task_id": running.get("id")}

        serial_cfg = config.get("scheduler", {}).get("serial_dual_scan", {})
        retry_rounds = int(serial_cfg.get("strategy1_failed_retry_rounds", 3))
        retry_rounds = max(0, min(10, retry_rounds))

        stocks = stock_pool.get_a_stock_pool(config)
        if not stocks:
            logger.error("Serial dual strategy scan aborted: stock pool is empty")
            return {"status": "failed", "error": "No stock pool available"}

        # Strategy 1 full scan
        s1_task_id = _make_scan_task_id("sched-s1")
        logger.info("Serial scan stage=strategy1_full task=%s stocks=%d started", s1_task_id, len(stocks))
        db.create_scan_task(
            s1_task_id,
            time.strftime("%Y-%m-%d %H:%M:%S"),
            total_stocks=len(stocks),
            retry_mode="full",
            strategy_type="STRATEGY_1_CUP_HANDLE",
        )
        db.save_task_stocks(s1_task_id, stocks)
        s1_result = scan_all(config, task_id=s1_task_id, stocks=stocks)
        s1_summary = _finish_scan_task_from_summary(s1_task_id, s1_result.get("stats", {}))
        logger.info("Serial scan stage=strategy1_full task=%s completed summary=%s", s1_task_id, s1_summary)

        # Strategy 1 failed-only retries
        retry_history = []
        for round_no in range(1, retry_rounds + 1):
            failed_stocks = _get_failed_stocks(s1_task_id)
            if not failed_stocks:
                logger.info("Serial scan strategy1 retry stopped: no failed stocks")
                break
            logger.info(
                "Serial scan stage=strategy1_retry round=%d/%d task=%s failed=%d started",
                round_no, retry_rounds, s1_task_id, len(failed_stocks),
            )
            retry_result = scan_all(
                config,
                task_id=s1_task_id,
                stocks=failed_stocks,
                retry_policy="failed_only",
            )
            s1_summary = db.refresh_scan_task_counts(s1_task_id)
            retry_history.append({"round": round_no, "failed_before": len(failed_stocks), "failed_after": s1_summary.get("failed")})
            logger.info(
                "Serial scan stage=strategy1_retry round=%d/%d task=%s completed summary=%s",
                round_no, retry_rounds, s1_task_id, s1_summary,
            )

        remaining_failed = len(_get_failed_stocks(s1_task_id))
        if remaining_failed:
            logger.warning(
                "Serial scan strategy1 completed with remaining failed stocks task=%s failed=%d after_retries=%d",
                s1_task_id, remaining_failed, retry_rounds,
            )

        # Strategy 2 full scan
        s2_task_id = _make_scan_task_id("sched-s2")
        logger.info(
            "Serial scan stage=strategy2_full task=%s stocks=%d started after strategy1 task=%s; "
            "strategy2 should reuse same-day daily_ohlc/task_stocks freshness when available",
            s2_task_id, len(stocks), s1_task_id,
        )
        db.create_scan_task(
            s2_task_id,
            time.strftime("%Y-%m-%d %H:%M:%S"),
            total_stocks=len(stocks),
            retry_mode="full",
            strategy_type="STRATEGY_2_EXTREME_DRY_STABLE",
        )
        db.save_task_stocks(s2_task_id, stocks)
        s2_result = scan_strategy2_all(config, task_id=s2_task_id, stocks=stocks)
        s2_summary = _finish_scan_task_from_summary(s2_task_id, s2_result.get("stats", {}))
        logger.info("Serial scan stage=strategy2_full task=%s completed summary=%s", s2_task_id, s2_summary)

        return {
            "status": "completed",
            "strategy1_task_id": s1_task_id,
            "strategy2_task_id": s2_task_id,
            "strategy1_remaining_failed": remaining_failed,
            "strategy1_retry_history": retry_history,
            "elapsed_seconds": round(time.time() - started, 1),
        }
    except Exception as exc:
        logger.exception("Serial dual strategy scan failed")
        if s2_task_id:
            _mark_scan_task_failed(s2_task_id, str(exc))
        elif s1_task_id:
            _mark_scan_task_failed(s1_task_id, str(exc))
        return {"status": "failed", "error": str(exc), "strategy1_task_id": s1_task_id, "strategy2_task_id": s2_task_id}
    finally:
        _serial_scan_lock.release()
```

实现注意：

- `scan_all()` 的 failed-only 重试会把失败股票重新置为 `fetching/scanned/candidate/skipped/failed`，所以每轮必须重新查 DB。
- 失败重试使用同一个策略1 `task_id`，保持一个任务的失败列表可在前端查看。
- 策略2使用独立 `task_id` 和 `strategy_type='STRATEGY_2_EXTREME_DRY_STABLE'`。
- 策略2必须在策略1完整结束后启动，不能并发或提前启动；这是为了让策略2命中策略1当天写入的 `daily_ohlc` 和 `task_stocks.kline_latest_date`，避免重复请求外部行情源。
- 不要为了“强制复用”绕过策略2扫描入口；复用应通过现有共享日线服务和同日新鲜缓存机制自然发生。
- 策略1异常时不启动策略2；策略2异常时策略1保留 completed，策略2标记 failed。

- [ ] **步骤 8：运行任务 1 的专项测试**

运行：

```bash
python -m pytest tests/test_scheduler_serial_dual_scan.py -q
```

预期：全部通过。

---

### 任务 3：接入 `start_scheduler(config)` 注册新 job

**文件：**

- 修改：`scheduler/scheduler.py`
- 测试：`tests/test_scheduler_serial_dual_scan.py`

- [ ] **步骤 1：调整 `start_scheduler(config)` 逻辑**

行为要求：

```python
serial_cfg = sched_cfg.get("serial_dual_scan", {})
serial_enabled = serial_cfg.get("enabled", True)

if serial_enabled:
    cron = serial_cfg.get("cron", "15 15 * * 1-5")
    cron_parts = _parse_cron_parts(cron)
    _scheduler.add_job(
        lambda: run_serial_dual_strategy_scan(config),
        "cron",
        minute=cron_parts["minute"],
        hour=cron_parts["hour"],
        day_of_week=cron_parts["day_of_week"],
        id="serial_dual_strategy_scan",
    )
    logger.info("Serial dual strategy scheduler started: %s", cron)
else:
    # 保留旧 daily_scan 注册逻辑，供显式关闭新任务的用户继续使用旧策略1定时扫描。
```

兼容要求：

- `scheduler.enabled=false` 时仍然不启动任何定时任务。
- `serial_dual_scan.enabled=true` 时只注册新串行任务，不注册旧 `daily_scan`，避免重复执行。
- `serial_dual_scan.enabled=false` 时保留原有旧 `daily_scan` 行为。

- [ ] **步骤 2：补充测试：serial enabled 时不注册旧 daily_scan**

```python
def test_start_scheduler_serial_enabled_does_not_register_legacy_daily_scan(monkeypatch):
    from scheduler import scheduler as sched_mod

    added = []

    class FakeScheduler:
        running = False
        def add_job(self, func, trigger, **kwargs):
            added.append(kwargs["id"])
        def start(self):
            self.running = True

    monkeypatch.setattr(sched_mod, "BackgroundScheduler", FakeScheduler)

    sched_mod.start_scheduler({"scheduler": {"enabled": True, "serial_dual_scan": {"enabled": True}}})

    assert added == ["serial_dual_strategy_scan"]
```

- [ ] **步骤 3：补充测试：serial disabled 时保留 legacy daily_scan**

```python
def test_start_scheduler_serial_disabled_keeps_legacy_daily_scan(monkeypatch):
    from scheduler import scheduler as sched_mod

    added = []

    class FakeScheduler:
        running = False
        def add_job(self, func, trigger, **kwargs):
            added.append(kwargs["id"])
        def start(self):
            self.running = True

    monkeypatch.setattr(sched_mod, "BackgroundScheduler", FakeScheduler)

    sched_mod.start_scheduler({
        "scheduler": {
            "enabled": True,
            "cron": "30 15 * * 1-5",
            "serial_dual_scan": {"enabled": False},
        }
    })

    assert added == ["daily_scan"]
```

- [ ] **步骤 4：运行专项测试**

运行：

```bash
python -m pytest tests/test_scheduler_serial_dual_scan.py -q
```

预期：全部通过。

---

### 任务 4：更新配置文件

**文件：**

- 修改：`config.yaml`

- [ ] **步骤 1：更新 `config.yaml`**

在 `scheduler` 段加入：

```yaml
  serial_dual_scan:
    enabled: true
    cron: 15 15 * * 1-5
    strategy1_failed_retry_rounds: 3
```

保持已有：

```yaml
scheduler:
  enabled: false
  cron: 30 15 * * 1-5
  skip_if_running: true
  on_complete: log
  webhook_url: null
```

说明：`scheduler.enabled` 仍然默认 `false`，所以仅启动服务不会自动跑；用户显式开启调度后，新串行任务成为默认调度行为。

- [ ] **步骤 2：运行配置相关测试**

运行：

```bash
python -m pytest tests/test_scheduler_serial_dual_scan.py -q
```

预期：通过。

---

### 任务 5：审核验收与回归

**文件：**

- 不新增生产代码，必要时修正测试或调度实现。

- [ ] **步骤 1：运行专项测试**

```bash
python -m pytest tests/test_scheduler_serial_dual_scan.py -q
```

预期：通过。

- [ ] **步骤 2：运行调度相关和扫描任务相关测试**

```bash
python -m pytest tests/test_scan_task_tracking.py tests/test_server_scan_api.py tests/test_strategy2_final_fixes.py -q
```

预期：通过。

- [ ] **步骤 3：运行后端常规验证**

```bash
python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py --ignore=tests/test_yfinance_hist.py
python -m compileall scanner strategy2 scheduler server.py main.py -q
```

预期：全部通过。

- [ ] **步骤 4：人工代码审核重点**

审核以下中高风险点：

- 防重复锁是否在异常路径释放。
- DB 已有 running task 时是否跳过，不创建新任务。
- 策略1失败重试是否只传入失败列表，而不是全量股票。
- 策略1重试是否最多 3 轮，不会无限循环。
- 策略1异常时是否不会启动策略2。
- 策略2是否确实在策略1完整结束后才启动，以便复用策略1当天写入的日线数据。
- 实现是否没有绕过策略2扫描入口、没有破坏现有 `daily_ohlc` / `kline_latest_date` 同日复用机制。
- 策略2异常时是否标记策略2任务 failed，且不回退策略1任务状态。
- 新串行任务启用时是否不会同时注册旧 `daily_scan`，避免重复扫描。
- `finish_scan_task()` 是否在策略1和策略2正常结束后都被调用。
- 日志是否足够定位阶段、task_id、失败数和跳过原因。

---

## 6. 给修复 AI 的执行要求

1. 严格按 TDD：先写 `tests/test_scheduler_serial_dual_scan.py` 并确认失败，再实现。
2. 不修改策略1/策略2的评分、入选、否决、风险规则。
3. 不修改前端。
4. 不新增数据库表；只复用现有 `scan_tasks/task_stocks`。
5. 调度层必须显式创建任务、保存股票列表、完成后调用 `finish_scan_task()`。
6. 失败重试必须复用策略1同一个 `task_id`，只重跑 `status='failed'` 股票。
7. 策略2必须使用独立任务，`strategy_type='STRATEGY_2_EXTREME_DRY_STABLE'`。
8. 策略2必须在策略1完整结束后再启动，让策略2通过现有同日新鲜缓存机制复用策略1已成功拉取的历史日线数据，避免重复请求外部数据源。
9. 任一异常路径必须写日志，并把当前阶段任务标记为 failed。
10. 不允许引入新的大型依赖。
11. 提交前必须运行专项测试、相关回归和 compileall。

---

## 7. 不建议修改的内容

- 不要修改 `scanner/strategy_engine.py`。
- 不要修改 `strategy2/engine.py`。
- 不要改变 `daily_ohlc` 缓存复用规则。
- 不要为了策略2复用数据新增绕路逻辑；优先复用现有 `daily_ohlc`、`task_stocks.kline_latest_date` 和共享日线服务。
- 不要把调度串行任务改成 HTTP 调用自身 API。
- 不要让策略2在策略1失败重试未结束前启动。
- 不要在 `scheduler.enabled=false` 时注册任何后台 job。
- 不要把旧 `daily_scan` 和新 `serial_dual_strategy_scan` 同时注册为默认行为。

---

## 8. 最终交付标准

完成后应满足：

1. `python main.py schedule` 在 `scheduler.enabled=true` 且 `serial_dual_scan.enabled=true` 时注册周一至周五 15:15 串行双策略任务。
2. 策略1全量扫描完整结束后，失败股票最多重试 3 轮。
3. 策略1流程结束后再启动策略2，策略2能够复用策略1当天成功写入的股票历史日线数据，避免对这些股票重复请求外部数据源。
4. 运行中重复触发会被进程锁跳过。
5. DB 中已有 running 扫描任务时会跳过，不创建新任务。
6. 异常路径有日志，当前任务状态正确变为 failed。
7. 策略1和策略2任务都能在 `scan_tasks/task_stocks` 中被追踪。
8. 所有新增测试和相关回归通过。

---

## 9. 文档自检

- 规格覆盖度：已覆盖触发时间、串行顺序、策略2复用策略1日线数据的业务目的、失败列表重试、最多 3 轮、防重复锁、异常处理、日志、DB 任务追踪。
- 占位符扫描：本文没有使用待实现占位符；每个任务都有明确文件、代码片段、命令和预期结果。
- 类型一致性：统一使用 `run_serial_dual_strategy_scan(config)`、`_serial_scan_lock`、`_get_failed_stocks(task_id)`、`_finish_scan_task_from_summary(task_id, stats)`。
- 范围控制：仅调度层编排，不修改策略规则、不改前端、不改 DB schema。

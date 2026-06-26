def test_start_scheduler_registers_serial_dual_scan_job(monkeypatch):
    from scheduler import scheduler as sched_mod

    added = []

    class FakeScheduler:
        running = False

        def add_job(self, func, trigger, **kwargs):
            added.append({"func": func, "trigger": trigger, **kwargs})

        def start(self):
            self.running = True

        def shutdown(self, wait=True):
            self.running = False

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
    assert job["day_of_week"] == "mon-fri"


def test_reload_scheduler_replaces_existing_job(monkeypatch):
    from scheduler import scheduler as sched_mod

    started_jobs = []
    shutdowns = []

    class FakeScheduler:
        running = False

        def __init__(self):
            self.jobs = []

        def add_job(self, func, trigger, **kwargs):
            self.jobs.append({"func": func, "trigger": trigger, **kwargs})

        def get_jobs(self):
            return [type("Job", (), {"id": j["id"], "next_run_time": None, "trigger": j["trigger"]})() for j in self.jobs]

        def start(self):
            self.running = True
            started_jobs.append(self.jobs[0]["hour"])

        def shutdown(self, wait=True):
            shutdowns.append(wait)
            self.running = False

    monkeypatch.setattr(sched_mod, "BackgroundScheduler", FakeScheduler)

    sched_mod.reload_scheduler({
        "scheduler": {
            "enabled": True,
            "serial_dual_scan": {"enabled": True, "cron": "15 15 * * 1-5"},
        }
    })
    sched_mod.reload_scheduler({
        "scheduler": {
            "enabled": True,
            "serial_dual_scan": {"enabled": True, "cron": "50 16 * * 1-5"},
        }
    })

    assert started_jobs == ["15", "16"]
    assert shutdowns == [False]


def test_get_scheduler_status_reports_registered_jobs(monkeypatch):
    from scheduler import scheduler as sched_mod

    class FakeScheduler:
        running = False

        def __init__(self):
            self.jobs = []

        def add_job(self, func, trigger, **kwargs):
            self.jobs.append({"func": func, "trigger": trigger, **kwargs})

        def get_jobs(self):
            return [
                type("Job", (), {
                    "id": j["id"],
                    "next_run_time": "2026-06-17 15:50:00",
                    "trigger": j["trigger"],
                })()
                for j in self.jobs
            ]

        def start(self):
            self.running = True

        def shutdown(self, wait=True):
            self.running = False

    monkeypatch.setattr(sched_mod, "BackgroundScheduler", FakeScheduler)
    sched_mod.reload_scheduler({
        "scheduler": {
            "enabled": True,
            "serial_dual_scan": {"enabled": True, "cron": "50 15 * * 1-5"},
        }
    })

    status = sched_mod.get_scheduler_status()

    assert status["running"] is True
    assert status["jobs"][0]["id"] == "serial_dual_strategy_scan"
    assert status["jobs"][0]["next_run_time"] == "2026-06-17 15:50:00"


def test_serial_scan_runs_strategy1_retries_failed_then_strategy2_then_strategy3(monkeypatch, tmp_path):
    from scheduler import scheduler as sched_mod
    from scanner import db

    db_path = tmp_path / "cuphandle.db"
    config = {
        "data": {"database_path": str(db_path)},
        "scheduler": {"serial_dual_scan": {"strategy1_failed_retry_rounds": 3}},
    }
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
            db.update_task_stock(
                task_id,
                "000001",
                status="scanned",
                finished_at="2026-06-16 15:16:00",
            )
            db.update_task_stock(
                task_id,
                "000002",
                status="failed",
                status_reason="fetch failed",
                finished_at="2026-06-16 15:16:00",
            )
        elif len([c for c in calls if c[0] == "s1" and c[1] == "failed_only"]) < 3:
            db.update_task_stock(
                task_id,
                "000002",
                status="failed",
                status_reason="fetch failed again",
                finished_at="2026-06-16 15:17:00",
            )
        else:
            db.update_task_stock(
                task_id,
                "000002",
                status="scanned",
                finished_at="2026-06-16 15:18:00",
            )
        summary = db.refresh_scan_task_counts(task_id)
        return {
            "task_id": task_id,
            "candidates": [],
            "stats": {"candidates_found": 0, "elapsed_seconds": 1, **summary},
        }

    def fake_scan_strategy2_all(config, task_id=None, stocks=None, **kwargs):
        calls.append(("s2", "normal", [s["code"] for s in (stocks or [])]))
        for stock in stocks:
            db.update_task_stock(
                task_id,
                stock["code"],
                status="scanned",
                finished_at="2026-06-16 15:19:00",
            )
        summary = db.refresh_scan_task_counts(task_id)
        return {
            "task_id": task_id,
            "candidates": [],
            "stats": {"candidates_found": 0, "elapsed_seconds": 1, **summary},
        }

    def fake_scan_strategy3_all(config, task_id=None, stocks=None, **kwargs):
        calls.append(("s3", "normal", [s["code"] for s in (stocks or [])]))
        for stock in stocks:
            db.update_task_stock(
                task_id,
                stock["code"],
                status="scanned",
                finished_at="2026-06-16 15:20:00",
            )
        summary = db.refresh_scan_task_counts(task_id)
        return {
            "task_id": task_id,
            "candidates": [],
            "stats": {"candidates_found": 0, "elapsed_seconds": 1, **summary},
        }

    monkeypatch.setattr(sched_mod.stock_pool, "get_a_stock_pool", fake_stock_pool)
    monkeypatch.setattr(sched_mod, "scan_all", fake_scan_all)
    monkeypatch.setattr(sched_mod, "scan_strategy2_all", fake_scan_strategy2_all)
    monkeypatch.setattr(sched_mod, "scan_strategy3_all", fake_scan_strategy3_all)
    monkeypatch.setattr(
        sched_mod.time,
        "strftime",
        lambda fmt, *args: "20260616-151500" if "%Y%m%d" in fmt else "2026-06-16 15:15:00",
    )

    result = sched_mod.run_serial_dual_strategy_scan(config)

    assert result["status"] == "completed"
    assert [c[0] for c in calls] == ["s1", "s1", "s1", "s1", "s2", "s3"]
    assert calls[1][1] == "failed_only"
    assert calls[1][2] == ["000002"]
    assert calls[-2][0] == "s2"
    assert calls[-1][0] == "s3"
    assert result["strategy3_task_id"].startswith("sched-s3-")
    tasks = db.get_scan_tasks(strategy_type="STRATEGY_3_STRONG_PULLBACK_SECOND_BREAKOUT")
    assert len(tasks) == 1
    assert tasks[0]["id"] == result["strategy3_task_id"]


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


def test_serial_scan_marks_strategy1_failed_and_does_not_start_strategy2(monkeypatch, tmp_path):
    from scheduler import scheduler as sched_mod
    from scanner import db

    db_path = tmp_path / "cuphandle.db"
    config = {"data": {"database_path": str(db_path)}, "scheduler": {}}
    db.init_db(str(db_path))

    monkeypatch.setattr(
        sched_mod.stock_pool,
        "get_a_stock_pool",
        lambda config: [{"code": "000001", "name": "A"}],
    )

    def boom(*args, **kwargs):
        raise RuntimeError("strategy1 boom")

    s2_calls = []
    s3_calls = []
    monkeypatch.setattr(sched_mod, "scan_all", boom)
    monkeypatch.setattr(sched_mod, "scan_strategy2_all", lambda *args, **kwargs: s2_calls.append("s2"))
    monkeypatch.setattr(sched_mod, "scan_strategy3_all", lambda *args, **kwargs: s3_calls.append("s3"))
    monkeypatch.setattr(
        sched_mod.time,
        "strftime",
        lambda fmt, *args: "20260616-151500" if "%Y%m%d" in fmt else "2026-06-16 15:15:00",
    )

    result = sched_mod.run_serial_dual_strategy_scan(config)

    assert result["status"] == "failed"
    assert "strategy1 boom" in result["error"]
    assert s2_calls == []
    assert s3_calls == []

    tasks = db.get_scan_tasks(strategy_type="STRATEGY_1_CUP_HANDLE")
    assert tasks[0]["status"] == "failed"
    row = db.get_conn().execute(
        "SELECT error FROM scan_tasks WHERE id=?",
        (tasks[0]["id"],),
    ).fetchone()
    assert "strategy1 boom" in row[0]


def test_serial_scan_persists_strategy1_discoveries(monkeypatch, tmp_path):
    from scheduler import scheduler as sched_mod
    from scanner import db

    db_path = tmp_path / "cuphandle.db"
    config = {
        "data": {"database_path": str(db_path)},
        "scheduler": {"serial_dual_scan": {"strategy1_failed_retry_rounds": 0}},
    }
    db.init_db(str(db_path))

    stock = {"code": "000001", "name": "A", "market": "SZ"}
    monkeypatch.setattr(sched_mod.stock_pool, "get_a_stock_pool", lambda config: [stock])

    def fake_scan_all(config, progress_callback=None, task_id=None, stocks=None, **kwargs):
        db.update_task_stock(task_id, "000001", status="candidate", finished_at="2026-06-16 15:16:00")
        progress_callback(
            "discovery",
            1,
            1,
            "000001 A",
            {
                "code": "000001",
                "name": "A",
                "score": 88,
                "latest_close": 10.5,
                "dry_stable_verdict": "可低吸",
                "dry_stable_summary": "ok",
                "volume_dry_score": 9,
                "price_stable_score": 8,
                "pattern_score_20": 18,
                "pattern_type": "VCP",
                "key_pattern_type": "vcp",
            },
        )
        summary = db.refresh_scan_task_counts(task_id)
        return {
            "task_id": task_id,
            "candidates": [],
            "stats": {"candidates_found": 1, "elapsed_seconds": 1, **summary},
        }

    def fake_scan_strategy2_all(config, task_id=None, stocks=None, **kwargs):
        db.update_task_stock(task_id, "000001", status="scanned", finished_at="2026-06-16 15:19:00")
        summary = db.refresh_scan_task_counts(task_id)
        return {
            "task_id": task_id,
            "candidates": [],
            "stats": {"candidates_found": 0, "elapsed_seconds": 1, **summary},
        }

    def fake_scan_strategy3_all(config, task_id=None, stocks=None, **kwargs):
        db.update_task_stock(task_id, "000001", status="scanned", finished_at="2026-06-16 15:20:00")
        summary = db.refresh_scan_task_counts(task_id)
        return {
            "task_id": task_id,
            "candidates": [],
            "stats": {"candidates_found": 0, "elapsed_seconds": 1, **summary},
        }

    monkeypatch.setattr(sched_mod, "scan_all", fake_scan_all)
    monkeypatch.setattr(sched_mod, "scan_strategy2_all", fake_scan_strategy2_all)
    monkeypatch.setattr(sched_mod, "scan_strategy3_all", fake_scan_strategy3_all)

    result = sched_mod.run_serial_dual_strategy_scan(config)

    assert result["status"] == "completed"
    candidates = db.get_candidates(result["strategy1_task_id"])
    assert len(candidates) == 1
    assert candidates[0]["code"] == "000001"
    assert candidates[0]["score"] == 88


def test_serial_scan_final_candidate_count_includes_retry_discoveries(monkeypatch, tmp_path):
    from scheduler import scheduler as sched_mod
    from scanner import db

    db_path = tmp_path / "cuphandle.db"
    config = {
        "data": {"database_path": str(db_path)},
        "scheduler": {"serial_dual_scan": {"strategy1_failed_retry_rounds": 1}},
    }
    db.init_db(str(db_path))

    stocks = [
        {"code": "000001", "name": "A", "market": "SZ"},
        {"code": "000002", "name": "B", "market": "SZ"},
    ]
    monkeypatch.setattr(sched_mod.stock_pool, "get_a_stock_pool", lambda config: stocks)

    def emit(progress_callback, code, name, score):
        progress_callback(
            "discovery",
            1,
            2,
            f"{code} {name}",
            {"code": code, "name": name, "score": score},
        )

    def fake_scan_all(config, progress_callback=None, task_id=None, stocks=None, retry_policy="normal", **kwargs):
        if retry_policy == "normal":
            db.update_task_stock(task_id, "000001", status="candidate", finished_at="2026-06-16 15:16:00")
            db.update_task_stock(task_id, "000002", status="failed", status_reason="fetch failed", finished_at="2026-06-16 15:16:00")
            emit(progress_callback, "000001", "A", 80)
            summary = db.refresh_scan_task_counts(task_id)
            return {
                "task_id": task_id,
                "candidates": [],
                "stats": {"candidates_found": 1, "elapsed_seconds": 1, **summary},
            }

        db.update_task_stock(task_id, "000002", status="candidate", finished_at="2026-06-16 15:17:00")
        emit(progress_callback, "000002", "B", 81)
        summary = db.refresh_scan_task_counts(task_id)
        return {
            "task_id": task_id,
            "candidates": [],
            "stats": {"candidates_found": 1, "elapsed_seconds": 1, **summary},
        }

    def fake_scan_strategy2_all(config, task_id=None, stocks=None, **kwargs):
        for stock in stocks:
            db.update_task_stock(task_id, stock["code"], status="scanned", finished_at="2026-06-16 15:19:00")
        summary = db.refresh_scan_task_counts(task_id)
        return {
            "task_id": task_id,
            "candidates": [],
            "stats": {"candidates_found": 0, "elapsed_seconds": 1, **summary},
        }

    def fake_scan_strategy3_all(config, task_id=None, stocks=None, **kwargs):
        for stock in stocks:
            db.update_task_stock(task_id, stock["code"], status="scanned", finished_at="2026-06-16 15:20:00")
        summary = db.refresh_scan_task_counts(task_id)
        return {
            "task_id": task_id,
            "candidates": [],
            "stats": {"candidates_found": 0, "elapsed_seconds": 1, **summary},
        }

    monkeypatch.setattr(sched_mod, "scan_all", fake_scan_all)
    monkeypatch.setattr(sched_mod, "scan_strategy2_all", fake_scan_strategy2_all)
    monkeypatch.setattr(sched_mod, "scan_strategy3_all", fake_scan_strategy3_all)

    result = sched_mod.run_serial_dual_strategy_scan(config)

    assert result["status"] == "completed"
    row = db.get_conn().execute(
        "SELECT candidates_count FROM scan_tasks WHERE id=?",
        (result["strategy1_task_id"],),
    ).fetchone()
    assert row[0] == 2


def test_scheduler_events_are_recorded_and_limited():
    from scheduler import scheduler as sched_mod

    sched_mod.clear_scheduler_events()

    for i in range(205):
        sched_mod.record_scheduler_event(
            "info",
            "stage-test",
            f"message-{i}",
            task_id=f"task-{i}",
            details={"idx": i},
        )

    events = sched_mod.get_scheduler_events()

    assert len(events) == 200
    assert events[0]["message"] == "message-5"
    assert events[-1]["message"] == "message-204"
    assert events[-1]["level"] == "info"
    assert events[-1]["stage"] == "stage-test"
    assert events[-1]["task_id"] == "task-204"
    assert events[-1]["details"] == {"idx": 204}
    assert "time" in events[-1]


def test_start_scheduler_serial_enabled_does_not_register_legacy_daily_scan(monkeypatch):
    from scheduler import scheduler as sched_mod

    added = []

    class FakeScheduler:
        running = False

        def add_job(self, func, trigger, **kwargs):
            added.append(kwargs["id"])

        def start(self):
            self.running = True

        def shutdown(self, wait=True):
            self.running = False

    monkeypatch.setattr(sched_mod, "BackgroundScheduler", FakeScheduler)

    sched_mod.start_scheduler({"scheduler": {"enabled": True, "serial_dual_scan": {"enabled": True}}})

    assert added == ["serial_dual_strategy_scan"]


def test_start_scheduler_serial_disabled_keeps_legacy_daily_scan(monkeypatch):
    from scheduler import scheduler as sched_mod

    added = []

    class FakeScheduler:
        running = False

        def add_job(self, func, trigger, **kwargs):
            added.append(kwargs["id"])

        def start(self):
            self.running = True

        def shutdown(self, wait=True):
            self.running = False

    monkeypatch.setattr(sched_mod, "BackgroundScheduler", FakeScheduler)

    sched_mod.start_scheduler({
        "scheduler": {
            "enabled": True,
            "cron": "30 15 * * 1-5",
            "serial_dual_scan": {"enabled": False},
        }
    })

    assert added == ["daily_scan"]

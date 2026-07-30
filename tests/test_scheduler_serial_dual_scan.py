from __future__ import annotations


def _fake_scheduler_factory(added, started=None, shutdowns=None):
    class FakeScheduler:
        running = False

        def __init__(self):
            self.jobs = []

        def add_job(self, func, trigger, **kwargs):
            job = {"func": func, "trigger": trigger, **kwargs}
            self.jobs.append(job)
            added.append(job)

        def get_jobs(self):
            return [
                type(
                    "Job",
                    (),
                    {
                        "id": job["id"],
                        "next_run_time": "2026-07-31 15:15:00",
                        "trigger": job["trigger"],
                    },
                )()
                for job in self.jobs
            ]

        def start(self):
            self.running = True
            if started is not None:
                started.append(self.jobs[0]["hour"])

        def shutdown(self, wait=True):
            self.running = False
            if shutdowns is not None:
                shutdowns.append(wait)

    return FakeScheduler


def test_start_scheduler_registers_only_strategy6_job(monkeypatch):
    from scheduler import scheduler as sched_mod

    added = []
    monkeypatch.setattr(sched_mod, "BackgroundScheduler", _fake_scheduler_factory(added))

    sched_mod.start_scheduler(
        {
            "scheduler": {
                "enabled": True,
                "serial_dual_scan": {
                    "enabled": True,
                    "cron": "15 15 * * 1-5",
                },
            }
        }
    )

    assert len(added) == 1
    assert added[0]["id"] == "strategy6_scan"
    assert added[0]["minute"] == "15"
    assert added[0]["hour"] == "15"
    assert added[0]["day_of_week"] == "mon-fri"


def test_legacy_serial_switch_cannot_restore_old_strategy_scan(monkeypatch):
    from scheduler import scheduler as sched_mod

    added = []
    monkeypatch.setattr(sched_mod, "BackgroundScheduler", _fake_scheduler_factory(added))

    sched_mod.start_scheduler(
        {
            "scheduler": {
                "enabled": True,
                "cron": "30 16 * * 1-5",
                "serial_dual_scan": {"enabled": False},
            }
        }
    )

    assert [job["id"] for job in added] == ["strategy6_scan"]
    assert added[0]["minute"] == "30"
    assert added[0]["hour"] == "16"


def test_reload_scheduler_replaces_strategy6_job(monkeypatch):
    from scheduler import scheduler as sched_mod

    added = []
    started = []
    shutdowns = []
    monkeypatch.setattr(
        sched_mod,
        "BackgroundScheduler",
        _fake_scheduler_factory(added, started, shutdowns),
    )

    sched_mod.reload_scheduler(
        {"scheduler": {"enabled": True, "serial_dual_scan": {"cron": "15 15 * * 1-5"}}}
    )
    sched_mod.reload_scheduler(
        {"scheduler": {"enabled": True, "serial_dual_scan": {"cron": "50 16 * * 1-5"}}}
    )

    assert started == ["15", "16"]
    assert shutdowns == [False]
    assert all(job["id"] == "strategy6_scan" for job in added)


def test_scheduled_scan_runs_only_strategy6(monkeypatch, tmp_path):
    from scanner import db
    from scheduler import scheduler as sched_mod
    from strategy6 import STRATEGY6_TYPE

    db_path = tmp_path / "cuphandle.db"
    config = {"data": {"database_path": str(db_path)}, "scheduler": {}}
    db.init_db(str(db_path))
    stocks = [
        {"code": "000001", "name": "A", "market": "SZ"},
        {"code": "000002", "name": "B", "market": "SZ"},
    ]
    calls = []
    monkeypatch.setattr(sched_mod.stock_pool, "get_a_stock_pool", lambda _config: stocks)

    def fake_scan_strategy6(config, task_id=None, stocks=None, progress_callback=None, **kwargs):
        calls.append((task_id, [stock["code"] for stock in stocks]))
        for index, stock in enumerate(stocks, start=1):
            db.update_task_stock(
                task_id,
                stock["code"],
                status="scanned",
                finished_at="2026-07-30 15:16:00",
            )
            progress_callback("scanning", index, len(stocks), f"{stock['code']} {stock['name']}")
        return {
            "task_id": task_id,
            "candidates": [],
            "stats": {"candidates_found": 0, "elapsed_seconds": 1.2},
        }

    monkeypatch.setattr(sched_mod, "scan_strategy6_all", fake_scan_strategy6)
    monkeypatch.setattr(
        sched_mod.time,
        "strftime",
        lambda fmt, *args: "20260730-151500" if "%Y%m%d" in fmt else "2026-07-30 15:15:00",
    )

    result = sched_mod.run_strategy6_scheduled_scan(config)

    assert result["status"] == "completed"
    assert result["strategy6_task_id"].startswith("sched-s6-")
    assert calls == [(result["strategy6_task_id"], ["000001", "000002"])]
    tasks = db.get_scan_tasks(strategy_type=STRATEGY6_TYPE)
    assert len(tasks) == 1
    assert tasks[0]["id"] == result["strategy6_task_id"]
    assert tasks[0]["status"] == "completed"
    assert db.get_scan_tasks(strategy_type="STRATEGY_1_CUP_HANDLE") == []


def test_scheduled_scan_skips_when_process_lock_is_held(monkeypatch, tmp_path):
    from scheduler import scheduler as sched_mod

    calls = []
    monkeypatch.setattr(sched_mod, "scan_strategy6_all", lambda *args, **kwargs: calls.append("s6"))

    assert sched_mod._serial_scan_lock.acquire(blocking=False) is True
    try:
        result = sched_mod.run_strategy6_scheduled_scan(
            {"data": {"database_path": str(tmp_path / "cuphandle.db")}}
        )
    finally:
        sched_mod._serial_scan_lock.release()

    assert result == {"status": "skipped", "reason": "already_running_in_process"}
    assert calls == []


def test_scheduled_scan_marks_strategy6_task_failed(monkeypatch, tmp_path):
    from scanner import db
    from scheduler import scheduler as sched_mod
    from strategy6 import STRATEGY6_TYPE

    db_path = tmp_path / "cuphandle.db"
    config = {"data": {"database_path": str(db_path)}, "scheduler": {}}
    db.init_db(str(db_path))
    monkeypatch.setattr(
        sched_mod.stock_pool,
        "get_a_stock_pool",
        lambda _config: [{"code": "000001", "name": "A"}],
    )
    monkeypatch.setattr(
        sched_mod,
        "scan_strategy6_all",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("strategy6 boom")),
    )

    result = sched_mod.run_strategy6_scheduled_scan(config)

    assert result["status"] == "failed"
    assert "strategy6 boom" in result["error"]
    task = db.get_scan_tasks(strategy_type=STRATEGY6_TYPE)[0]
    assert task["status"] == "failed"


def test_scheduler_events_are_recorded_and_limited():
    from scheduler import scheduler as sched_mod

    sched_mod.clear_scheduler_events()
    for index in range(205):
        sched_mod.record_scheduler_event("info", "test", f"message-{index}")

    events = sched_mod.get_scheduler_events()
    assert len(events) == 200
    assert events[0]["message"] == "message-5"
    assert events[-1]["message"] == "message-204"

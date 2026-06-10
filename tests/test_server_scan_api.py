from fastapi.testclient import TestClient

import server
from scanner import db


def test_start_scan_rejects_when_db_task_running(monkeypatch, tmp_path):
    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))
    db.create_scan_task("running-1", "2026-06-04 09:30:00", total_stocks=1)
    server._running["running"] = False
    server._running["task_id"] = None

    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": {"data": {"database_path": str(db_path)}})

    client = TestClient(server.app)
    res = client.get("/api/scan/start")

    assert res.status_code == 409
    assert res.json()["error"] == "Scan already running"
    assert res.json()["running_task_id"] == "running-1"


def test_startup_resume_failure_clears_in_memory_running_state(monkeypatch, tmp_path):
    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))
    db.create_scan_task("interrupted-1", "2026-06-04 09:30:00", total_stocks=2)
    db.save_task_stocks("interrupted-1", [
        {"code": "600000", "name": "浦发银行", "market": "上证主板"},
        {"code": "000001", "name": "平安银行", "market": "深证主板"},
    ])
    db.update_task_stock("interrupted-1", "600000", status="scanned")
    db.refresh_scan_task_counts("interrupted-1")
    server._running["running"] = False
    server._running["task_id"] = None
    server._running["stats"] = {}

    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": {"data": {"database_path": str(db_path)}, "scheduler": {"enabled": False}})

    def failing_scan_all(*args, **kwargs):
        raise RuntimeError("resume boom")

    monkeypatch.setattr(server, "scan_all", failing_scan_all)

    import time
    with TestClient(server.app) as client:
        deadline = time.time() + 2
        while time.time() < deadline and server._running.get("running"):
            time.sleep(0.01)
        res = client.get("/api/scan/status")

    assert server._running["running"] is False
    assert res.json()["running"] is False
    row = db.get_conn().execute("SELECT status, error FROM scan_tasks WHERE id=?", ("interrupted-1",)).fetchone()
    assert row[0] == "failed"
    assert "resume boom" in row[1]


def test_startup_resume_success_finishes_interrupted_task(monkeypatch, tmp_path):
    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))
    db.create_scan_task("interrupted-ok", "2026-06-04 09:30:00", total_stocks=2)
    db.save_task_stocks("interrupted-ok", [
        {"code": "600000", "name": "浦发银行", "market": "上证主板"},
        {"code": "000001", "name": "平安银行", "market": "深证主板"},
    ])
    db.update_task_stock("interrupted-ok", "600000", status="scanned")
    db.refresh_scan_task_counts("interrupted-ok")
    # Leave the task as running; app startup will mark it as a current-startup interruption.
    server._running["running"] = False
    server._running["task_id"] = None
    server._running["stats"] = {}

    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": {"data": {"database_path": str(db_path)}, "scheduler": {"enabled": False}})

    def successful_scan_all(*args, **kwargs):
        db.update_task_stock("interrupted-ok", "000001", status="scanned", finished_at="2026-06-04 09:31:00")
        db.refresh_scan_task_counts("interrupted-ok")
        return {
            "stats": {
                "candidates_found": 0,
                "elapsed_seconds": 1.2,
                "scanned": 2,
                "skipped": 0,
            },
            "candidates": [],
        }

    monkeypatch.setattr(server, "scan_all", successful_scan_all)

    import time
    with TestClient(server.app) as client:
        deadline = time.time() + 2
        while time.time() < deadline and server._running.get("running"):
            time.sleep(0.01)
        res = client.get("/api/scan/status")

    assert res.json()["running"] is False
    row = db.get_conn().execute("SELECT status, error, finished_at FROM scan_tasks WHERE id=?", ("interrupted-ok",)).fetchone()
    assert row[0] == "completed"
    assert row[1] is None
    assert row[2]


def test_task_stocks_endpoint_filters_failed_rows(monkeypatch, tmp_path):
    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))
    db.create_scan_task("task-1", "2026-06-04 09:30:00", total_stocks=2)
    db.save_task_stocks("task-1", [
        {"code": "600000", "name": "浦发银行", "market": "上证主板"},
        {"code": "000001", "name": "平安银行", "market": "深证主板"},
    ])
    db.update_task_stock("task-1", "600000", status="failed", status_reason="数据源全部失败")
    db.update_task_stock("task-1", "000001", status="scanned")

    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": {"data": {"database_path": str(db_path)}})

    client = TestClient(server.app)
    res = client.get("/api/scan/tasks/task-1/stocks?status=failed")

    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 1
    assert body["stocks"][0]["code"] == "600000"
    assert body["stocks"][0]["status_reason"] == "数据源全部失败"


def test_retry_failed_returns_zero_when_no_failures(monkeypatch, tmp_path):
    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))
    db.create_scan_task("task-1", "2026-06-04 09:30:00", total_stocks=1)
    db.save_task_stocks("task-1", [{"code": "600000", "name": "浦发银行", "market": "上证主板"}])
    db.update_task_stock("task-1", "600000", status="scanned")
    db.finish_scan_task("task-1", "2026-06-04 09:31:00", candidates_count=0, elapsed_seconds=1, scanned=1, skipped=0)
    server._running["running"] = False
    server._running["task_id"] = None

    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": {"data": {"database_path": str(db_path)}})

    client = TestClient(server.app)
    res = client.post("/api/scan/tasks/task-1/retry-failed")

    assert res.status_code == 200
    assert res.json()["retry_count"] == 0
    assert res.json()["status"] == "no_failed_stocks"


# ── COMPLETION-003: entry-level API regression tests ────────────────

def _safe_config():
    """Return a valid config dict that passes resolve_strategy_windows()."""
    return {
        "data": {"scan_window_days": 200, "backtest_window_days": 250},
        "liquidity": {"min_listing_days": 250},
        "market_environment": {"index_symbol": "000001"},
        "scheduler": {"enabled": False},
    }


def test_start_scan_valid_config_reaches_window_validation(monkeypatch, tmp_path):
    """COMPLETION-003: scan start with valid config → 200, no NameError."""
    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))

    server._running["running"] = False
    server._running["task_id"] = None

    cfg = _safe_config()
    cfg["data"]["database_path"] = str(db_path)
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": cfg)

    # Prevent actual scan execution — mock the background thread function
    monkeypatch.setattr(server, "scan_all", lambda *args, **kwargs: {
        "candidates": [], "task_id": "test-task",
        "stats": {"total": 0, "scanned": 0, "skipped": 0, "failed": 0, "candidates_found": 0},
    })
    # Mock stock_pool to avoid actual fetching
    from scanner import stock_pool
    monkeypatch.setattr(stock_pool, "get_a_stock_pool_result",
                        lambda config: {"stocks": [{"code": "600000", "name": "Test", "market": "SSE"}], "source": "test"})
    # Prevent actual thread execution that could interfere with test
    import threading
    monkeypatch.setattr(threading, "Thread",
                        lambda target=None, args=(), daemon=None: type("T", (), {
                            "start": lambda self: target(*args) if target else None,
                            "join": lambda self, timeout=None: None,
                        })())

    client = TestClient(server.app)
    res = client.get("/api/scan/start")

    # Must not be NameError (500), should be 200 with task_id
    assert res.status_code == 200
    body = res.json()
    assert "task_id" in body


def test_update_config_valid_window_returns_ok(monkeypatch, tmp_path):
    """COMPLETION-003: PUT /api/config with valid windows → 200."""
    import builtins

    config_path = tmp_path / "config.yaml"
    cfg = _safe_config()
    cfg["data"]["daily_sources"] = ["sina", "tencent"]
    import yaml
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f)

    # Redirect config.yaml reads/writes to tmp_path
    original_open = builtins.open

    def _fake_open(file, *args, **kwargs):
        if file == "config.yaml":
            return original_open(str(config_path), *args, **kwargs)
        return original_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", _fake_open)
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": {
        **cfg, "data": {**cfg["data"], "database_path": str(tmp_path / "cuphandle.db")},
    })

    client = TestClient(server.app)
    res = client.put("/api/config", json={"data": {"scan_window_days": 200}})

    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_update_config_invalid_window_returns_400(monkeypatch, tmp_path):
    """COMPLETION-003: PUT /api/config with invalid scan_window_days → 400."""
    import builtins

    config_path = tmp_path / "config.yaml"
    cfg = _safe_config()
    cfg["data"]["daily_sources"] = ["sina", "tencent"]
    import yaml
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f)

    original_open = builtins.open

    def _fake_open(file, *args, **kwargs):
        if file == "config.yaml":
            return original_open(str(config_path), *args, **kwargs)
        return original_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", _fake_open)
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": {
        **cfg, "data": {**cfg["data"], "database_path": str(tmp_path / "cuphandle.db")},
    })

    client = TestClient(server.app)
    # scan_window_days=0 should be rejected by resolve_strategy_windows
    res = client.put("/api/config", json={"data": {"scan_window_days": 0}})

    assert res.status_code == 400
    assert "Invalid window config" in res.json()["message"]


def test_candidate_detail_with_ohlc_returns_current_analysis(monkeypatch, tmp_path):
    """COMPLETION-003: GET /api/candidate/{code} with OHLC → 200 + current_analysis."""
    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))

    # Save a candidate and OHLC data
    db.create_scan_task("task-1", "2026-01-01 09:00:00", total_stocks=1)
    db.save_task_stocks("task-1", [{"code": "600000", "name": "Test", "market": "SSE"}])
    db.upsert_candidate("task-1", {
        "code": "600000", "name": "Test", "score": 75,
        "dry_stable_verdict": "观察", "dry_stable_summary": "ok",
        "volume_dry_score": 8, "price_stable_score": 7,
        "pattern_score_20": 16, "pattern_type": "杯柄", "key_pattern_type": "cup_handle",
        "risk_percent": 5, "rr1": 2.0, "position_advice": "20%",
        "entry_zone_low": 19, "entry_zone_high": 21, "pivot": 22,
        "stop_loss": 18, "target_1": 25, "target_2": 30,
        "market_status": "一般", "market_position_advice": "轻仓",
    })

    # Save enough OHLC data for scan_window_days
    rows = []
    for i in range(250):
        rows.append({
            "date": f"2025-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
            "open": 10.0, "high": 10.5, "low": 9.5, "close": 10.2 + i * 0.01,
            "volume": 1_000_000, "turnover": 10_200_000,
        })
    db.save_ohlc("600000", rows)

    cfg = _safe_config()
    cfg["data"]["database_path"] = str(db_path)
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": cfg)
    monkeypatch.setattr(server, "fetch_market_index_daily", lambda symbol=None: [])

    client = TestClient(server.app)
    res = client.get("/api/candidate/600000")

    assert res.status_code == 200
    body = res.json()
    assert body["code"] == "600000"
    assert "analysis_notice" in body
    assert body["current_analysis"] is not None
    assert "passed" in body["current_analysis"]


def test_candidate_detail_invalid_window_returns_400(monkeypatch, tmp_path):
    """COMPLETION-003: candidate detail with invalid window config → 400."""
    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))

    db.create_scan_task("task-1", "2026-01-01 09:00:00", total_stocks=1)
    db.save_task_stocks("task-1", [{"code": "600000", "name": "Test", "market": "SSE"}])
    db.upsert_candidate("task-1", {"code": "600000", "name": "Test", "score": 75})

    rows = []
    for i in range(250):
        rows.append({
            "date": f"2025-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
            "open": 10.0, "high": 10.5, "low": 9.5, "close": 10.2,
            "volume": 1_000_000, "turnover": 10_200_000,
        })
    db.save_ohlc("600000", rows)

    # scan_window_days=0 causes ValueError in resolve_strategy_windows
    cfg = _safe_config()
    cfg["data"]["database_path"] = str(db_path)
    cfg["data"]["scan_window_days"] = 0
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": cfg)

    client = TestClient(server.app)
    res = client.get("/api/candidate/600000")

    assert res.status_code == 400
    assert "Invalid window config" in res.json()["error"]

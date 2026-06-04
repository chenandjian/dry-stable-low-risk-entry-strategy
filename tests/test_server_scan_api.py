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

from fastapi.testclient import TestClient

import server
from scanner import db


def test_cup_handle_backtest_endpoint_returns_success(monkeypatch, tmp_path):
    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": {"data": {"database_path": str(db_path)}})

    def fake_run(code, start_date, end_date, config, handle_start_date=None, handle_end_date=None):
        assert code == "600000"
        assert start_date == "2025-01-01"
        assert end_date == "2025-01-20"
        assert handle_start_date is None
        assert handle_end_date is None
        return {
            "code": code,
            "strategyVersion": "cuphandle-v1",
            "configHash": "sha256:" + "1" * 64,
            "patterns": [],
            "specifiedDiagnosis": None,
            "dataCoverage": {},
            "ohlc": [],
        }

    monkeypatch.setattr(server, "run_single_stock_cuphandle_backtest", fake_run, raising=False)
    client = TestClient(server.app)

    res = client.post("/api/stock/600000/backtest/cup-handle", json={"startDate": "2025-01-01", "endDate": "2025-01-20"})

    assert res.status_code == 200
    body = res.json()
    assert body["code"] == "600000"
    assert body["strategyVersion"] == "cuphandle-v1"
    assert body["configHash"].startswith("sha256:")


def test_cup_handle_backtest_endpoint_passes_specified_handle(monkeypatch, tmp_path):
    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": {"data": {"database_path": str(db_path)}})
    seen = {}

    def fake_run(code, start_date, end_date, config, handle_start_date=None, handle_end_date=None):
        seen["handle_start_date"] = handle_start_date
        seen["handle_end_date"] = handle_end_date
        return {
            "code": code,
            "strategyVersion": "cuphandle-v1",
            "configHash": "sha256:" + "2" * 64,
            "patterns": [],
            "specifiedDiagnosis": {"passed": False, "passedRules": [], "failedRules": []},
            "dataCoverage": {},
            "ohlc": [],
        }

    monkeypatch.setattr(server, "run_single_stock_cuphandle_backtest", fake_run, raising=False)
    client = TestClient(server.app)

    res = client.post("/api/stock/600000/backtest/cup-handle", json={
        "startDate": "2025-01-01",
        "endDate": "2025-01-20",
        "specifiedHandle": {"startDate": "2025-01-10", "endDate": "2025-01-12"},
    })

    assert res.status_code == 200
    assert seen == {"handle_start_date": "2025-01-10", "handle_end_date": "2025-01-12"}


def test_cup_handle_backtest_endpoint_returns_validation_error(monkeypatch, tmp_path):
    db_path = tmp_path / "cuphandle.db"
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": {"data": {"database_path": str(db_path)}})
    client = TestClient(server.app)

    res = client.post("/api/stock/600000/backtest/cup-handle", json={"startDate": "2025-02-01", "endDate": "2025-01-01"})

    assert res.status_code == 400
    assert res.json()["error"] == "Invalid request"


def test_cup_handle_backtest_endpoint_returns_data_coverage_error(monkeypatch, tmp_path):
    from scanner.single_stock_backtest import DataCoverageError

    db_path = tmp_path / "cuphandle.db"
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": {"data": {"database_path": str(db_path)}})

    def fake_run(*args, **kwargs):
        raise DataCoverageError("600000", "2025-01-01", "2025-01-20", {"startDate": "2025-01-10", "endDate": "2025-01-11"})

    monkeypatch.setattr(server, "run_single_stock_cuphandle_backtest", fake_run, raising=False)
    client = TestClient(server.app)

    res = client.post("/api/stock/600000/backtest/cup-handle", json={"startDate": "2025-01-01", "endDate": "2025-01-20"})

    assert res.status_code == 422
    body = res.json()
    assert body["error"] == "Insufficient data coverage"
    assert body["missingRanges"]

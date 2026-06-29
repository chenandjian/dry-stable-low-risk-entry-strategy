from datetime import datetime
import json

from fastapi.testclient import TestClient

import server
from scanner import db


def _row(day: str, close: float = 10.0) -> dict:
    return {
        "date": day,
        "open": close,
        "high": close + 0.5,
        "low": close - 0.5,
        "close": close,
        "volume": 1000,
        "turnover": close * 1000,
    }


def _zero_volume_flat_row(day: str, close: float = 10.0) -> dict:
    return {
        "date": day,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 0,
        "turnover": 0,
    }


def test_kline_history_returns_paginated_rows_and_fresh_summary(monkeypatch, tmp_path):
    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))
    db.save_ohlc("000831", [_row("2026-06-12", 9), _row("2026-06-15", 10), _row("2026-06-16", 11)])
    db.create_scan_task("task-1", "2026-06-16 15:20:00", total_stocks=1)
    db.save_task_stocks("task-1", [{"code": "000831", "name": "五矿稀土", "market": "深证主板"}])
    db.update_task_stock(
        "task-1",
        "000831",
        status="scanned",
        kline_latest_date="2026-06-16",
        kline_fetched_at="2026-06-16 15:12:00",
        kline_target_trade_date="2026-06-16",
        quote_status="not_requested",
    )
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": {"data": {"database_path": str(db_path)}})
    monkeypatch.setattr(server, "_now", lambda: datetime(2026, 6, 16, 15, 20, 0), raising=False)

    res = TestClient(server.app).get(
        "/api/stock/000831/kline-history",
        params={"start_date": "2026-06-15", "end_date": "2026-06-16", "page": 1, "page_size": 1},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 2
    assert body["page"] == 1
    assert body["page_size"] == 1
    assert body["rows"][0]["date"] == "2026-06-16"
    assert body["summary"]["target_trade_date"] == "2026-06-16"
    assert body["summary"]["latest_kline_date"] == "2026-06-16"
    assert body["summary"]["latest_fetch_time"] == "2026-06-16 15:12:00"
    assert body["summary"]["is_fresh"] is True
    assert body["summary"]["needs_refetch"] is False


def test_kline_history_accepts_suspended_stock_with_recent_fetch(monkeypatch, tmp_path):
    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))
    db.save_ohlc("000831", [_row("2026-06-15", 10)])
    db.create_scan_task("task-suspended", "2026-06-16 15:20:00", total_stocks=1)
    db.save_task_stocks("task-suspended", [{"code": "000831", "name": "五矿稀土", "market": "深证主板"}])
    db.update_task_stock(
        "task-suspended",
        "000831",
        status="scanned",
        kline_latest_date="2026-06-15",
        kline_fetched_at="2026-06-16 15:12:00",
        kline_target_trade_date="2026-06-16",
        quote_status="suspended",
    )
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": {"data": {"database_path": str(db_path)}})
    monkeypatch.setattr(server, "_now", lambda: datetime(2026, 6, 16, 15, 20, 0), raising=False)

    res = TestClient(server.app).get("/api/stock/000831/kline-history")

    assert res.status_code == 200
    summary = res.json()["summary"]
    assert summary["latest_kline_date"] == "2026-06-15"
    assert summary["target_trade_date"] == "2026-06-16"
    assert summary["quote_status"] == "suspended"
    assert summary["is_fresh"] is True
    assert summary["needs_refetch"] is False


def test_kline_history_marks_stale_data_as_needing_refetch(monkeypatch, tmp_path):
    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))
    db.save_ohlc("000831", [_row("2026-06-15", 10)])
    db.create_scan_task("task-stale", "2026-06-16 14:50:00", total_stocks=1)
    db.save_task_stocks("task-stale", [{"code": "000831", "name": "五矿稀土", "market": "深证主板"}])
    db.update_task_stock(
        "task-stale",
        "000831",
        status="scanned",
        kline_latest_date="2026-06-15",
        kline_fetched_at="2026-06-16 14:50:00",
        kline_target_trade_date="2026-06-16",
        quote_status="not_requested",
    )
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": {"data": {"database_path": str(db_path)}})
    monkeypatch.setattr(server, "_now", lambda: datetime(2026, 6, 16, 15, 20, 0), raising=False)

    res = TestClient(server.app).get("/api/stock/000831/kline-history")

    assert res.status_code == 200
    summary = res.json()["summary"]
    assert summary["is_fresh"] is False
    assert summary["needs_refetch"] is True
    assert "重新拉取" in summary["reason"]


def test_kline_history_rejects_invalid_date_range(monkeypatch, tmp_path):
    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": {"data": {"database_path": str(db_path)}})

    res = TestClient(server.app).get(
        "/api/stock/000831/kline-history",
        params={"start_date": "2026-06-17", "end_date": "2026-06-16"},
    )

    assert res.status_code == 400
    assert res.json()["error"] == "Invalid date range"


def test_kline_history_summary_uses_full_latest_date_not_filtered_page(monkeypatch, tmp_path):
    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))
    db.save_ohlc("000831", [_row("2026-06-15", 10), _row("2026-06-16", 11)])
    db.create_scan_task("task-latest", "2026-06-16 15:20:00", total_stocks=1)
    db.save_task_stocks("task-latest", [{"code": "000831", "name": "五矿稀土", "market": "深证主板"}])
    db.update_task_stock(
        "task-latest",
        "000831",
        status="scanned",
        kline_latest_date="2026-06-16",
        kline_fetched_at="2026-06-16 15:12:00",
        kline_target_trade_date="2026-06-16",
    )
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": {"data": {"database_path": str(db_path)}})
    monkeypatch.setattr(server, "_now", lambda: datetime(2026, 6, 16, 15, 20, 0), raising=False)

    res = TestClient(server.app).get(
        "/api/stock/000831/kline-history",
        params={"start_date": "2026-06-15", "end_date": "2026-06-15"},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["rows"][0]["date"] == "2026-06-15"
    assert body["summary"]["latest_kline_date"] == "2026-06-16"


def test_kline_history_returns_empty_rows_and_refetch_summary_for_missing_data(monkeypatch, tmp_path):
    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": {"data": {"database_path": str(db_path)}})
    monkeypatch.setattr(server, "_now", lambda: datetime(2026, 6, 16, 15, 20, 0), raising=False)

    res = TestClient(server.app).get("/api/stock/000831/kline-history")

    assert res.status_code == 200
    body = res.json()
    assert body["rows"] == []
    assert body["total"] == 0
    assert body["summary"]["latest_kline_date"] is None
    assert body["summary"]["is_fresh"] is False
    assert body["summary"]["needs_refetch"] is True


def test_kline_health_returns_summary_and_problem_list(monkeypatch, tmp_path):
    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))
    target = "2026-06-16"
    min_fetch_time = "2026-06-16 15:00:00"

    db.save_stock_pool([
        {"code": "000001", "name": "正常股份", "market": "SZ"},
        {"code": "000002", "name": "停牌股份", "market": "SZ"},
        {"code": "000003", "name": "异常股份", "market": "SZ"},
        {"code": "000004", "name": "失败股份", "market": "SZ"},
        {"code": "000005", "name": "缺失股份", "market": "SZ"},
        {"code": "000006", "name": "ST噪音", "market": "SZ"},
    ])
    db.save_ohlc("000001", [_row("2026-06-15", 10), _row(target, 11)])
    db.save_ohlc("000002", [_row("2026-06-15", 20)])
    db.save_ohlc("000003", [_row("2026-06-15", 30), _zero_volume_flat_row(target, 30)])

    db.create_scan_task("health-task", "2026-06-16 15:20:00", total_stocks=4)
    db.save_task_stocks("health-task", [
        {"code": "000001", "name": "正常股份", "market": "SZ"},
        {"code": "000002", "name": "停牌股份", "market": "SZ"},
        {"code": "000003", "name": "异常股份", "market": "SZ"},
        {"code": "000004", "name": "失败股份", "market": "SZ"},
    ])
    db.update_task_stock(
        "health-task", "000001", status="scanned",
        kline_latest_date=target, kline_fetched_at="2026-06-16 15:12:00",
        kline_target_trade_date=target, quote_status="not_requested",
    )
    db.update_task_stock(
        "health-task", "000002", status="scanned",
        kline_latest_date="2026-06-15", kline_fetched_at="2026-06-16 15:12:00",
        kline_target_trade_date=target, quote_status="suspended",
        source_errors=json.dumps({
            "baidu": "attempts=1 error=missing target trade date 2026-06-16",
            "sina": "attempts=1 error=missing target trade date 2026-06-16",
            "tencent": "attempts=1 error=missing target trade date 2026-06-16",
        }, ensure_ascii=False),
    )
    db.update_task_stock(
        "health-task", "000003", status="scanned",
        kline_latest_date=target, kline_fetched_at="2026-06-16 15:12:00",
        kline_target_trade_date=target, quote_status="not_requested",
    )
    db.update_task_stock(
        "health-task", "000004", status="failed",
        status_reason="ALL_DATA_SOURCES_FAILED",
        kline_fetched_at="2026-06-16 15:12:00",
        kline_target_trade_date=target,
    )
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": {"data": {"database_path": str(db_path)}})
    monkeypatch.setattr(server, "_now", lambda: datetime(2026, 6, 16, 15, 20, 0), raising=False)

    client = TestClient(server.app)
    res = client.get("/api/kline-health", params={"status": "problem"})

    assert res.status_code == 200
    body = res.json()
    assert body["summary"]["target_trade_date"] == target
    assert body["summary"]["min_fetch_time"] == min_fetch_time
    assert body["summary"]["total"] == 5
    assert body["summary"]["fresh"] == 1
    assert body["summary"]["no_trade"] == 1
    assert body["summary"]["anomaly"] == 3
    assert body["summary"]["needs_refetch"] == 3
    assert body["total"] == 4
    by_code = {item["code"]: item for item in body["items"]}
    assert "000006" not in by_code
    assert by_code["000002"]["health_status"] == "no_trade"
    assert by_code["000002"]["severity"] == "warning"
    assert by_code["000003"]["health_status"] == "anomaly"
    assert "零成交量平盘K线" in by_code["000003"]["reason"]
    assert by_code["000004"]["health_status"] == "failed"
    assert by_code["000004"]["severity"] == "danger"
    assert by_code["000005"]["health_status"] == "missing"
    assert by_code["000005"]["needs_refetch"] is True

    failed = client.get("/api/kline-health", params={"status": "failed"})
    assert failed.status_code == 200
    assert failed.json()["total"] == 1
    assert failed.json()["items"][0]["code"] == "000004"


def test_kline_health_initializes_database_from_config_when_needed(monkeypatch, tmp_path):
    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))
    db.save_stock_pool([{"code": "000001", "name": "平安银行", "market": "SZ"}])
    db.save_ohlc("000001", [_row("2026-06-16", 11)])
    db.create_scan_task("health-init-task", "2026-06-16 15:20:00", total_stocks=1)
    db.save_task_stocks("health-init-task", [{"code": "000001", "name": "平安银行", "market": "SZ"}])
    db.update_task_stock(
        "health-init-task", "000001", status="scanned",
        kline_latest_date="2026-06-16", kline_fetched_at="2026-06-16 15:12:00",
        kline_target_trade_date="2026-06-16", quote_status="not_requested",
    )
    monkeypatch.setattr(db, "DB_PATH", None)
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": {"data": {"database_path": str(db_path)}})
    monkeypatch.setattr(server, "_now", lambda: datetime(2026, 6, 16, 15, 20, 0), raising=False)

    res = TestClient(server.app).get("/api/kline-health")

    assert res.status_code == 200
    body = res.json()
    assert body["summary"]["total"] == 1
    assert body["summary"]["fresh"] == 1

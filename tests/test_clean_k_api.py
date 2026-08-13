from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient

import server
from scanner import db


def _weekdays(count: int) -> list[str]:
    current = date(2026, 4, 1)
    result = []
    while len(result) < count:
        if current.weekday() < 5:
            result.append(current.isoformat())
        current += timedelta(days=1)
    return result


def _rows(count: int = 60) -> list[dict]:
    result = []
    previous = 100.0
    for index, day in enumerate(_weekdays(count)):
        close = 100 + index * 0.15
        result.append({
            "date": day,
            "open": previous,
            "high": max(previous, close) + 0.15,
            "low": min(previous, close) - 0.15,
            "close": close,
            "volume": 1_000_000,
            "turnover": close * 1_000_000,
        })
        previous = close
    return result


def _configure(monkeypatch, tmp_path, rows=None):
    db_path = tmp_path / "clean-k.db"
    db.init_db(str(db_path))
    if rows:
        db.replace_ohlc_with_metadata(
            "300888",
            rows,
            source="tickflow",
            fetched_at=f"{rows[-1]['date']} 15:30:00",
        )
    monkeypatch.setattr(
        server,
        "load_config",
        lambda path="config.yaml": {"data": {"database_path": str(db_path)}, "clean_k": {}},
    )
    return db_path


def test_clean_k_api_analyzes_local_completed_bars_without_fetching(monkeypatch, tmp_path):
    rows = _rows()
    _configure(monkeypatch, tmp_path, rows)
    last_date = datetime.fromisoformat(rows[-1]["date"]).replace(hour=16)
    monkeypatch.setattr(server, "_now", lambda: last_date)
    monkeypatch.setattr(
        server,
        "fetch_with_retry",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not fetch")),
    )

    response = TestClient(server.app).post(
        "/api/stock/clean-k/analyze",
        json={"stockCode": "300888", "period": 20},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["stockCode"] == "300888"
    assert body["period"] == 20
    assert body["endDate"] == rows[-1]["date"]
    assert body["targetTradeDate"] == rows[-1]["date"]
    assert body["dataIsFresh"] is True
    assert body["evaluatedBarCount"] == 20
    assert len(body["barMetrics"]) == 20
    assert body["modelVersion"] == "CLEAN_K_V2"
    assert body["cleanKScore"] == body["window"]["score"]
    assert body["isClean"] == body["window"]["isClean"]
    assert body["current"]["days"] >= 5


def test_clean_k_api_marks_stale_local_data_but_still_returns_analysis(monkeypatch, tmp_path):
    rows = _rows()
    _configure(monkeypatch, tmp_path, rows)
    next_day = datetime.fromisoformat(rows[-1]["date"]) + timedelta(days=1)
    while next_day.weekday() >= 5:
        next_day += timedelta(days=1)
    monkeypatch.setattr(server, "_now", lambda: next_day.replace(hour=16))

    response = TestClient(server.app).post(
        "/api/stock/clean-k/analyze",
        json={"stockCode": "300888", "period": 20},
    )

    assert response.status_code == 200
    assert response.json()["dataIsFresh"] is False
    assert "STALE_LOCAL_DATA" in response.json()["riskFlags"]


def test_clean_k_api_excludes_target_bar_fetched_before_market_close(monkeypatch, tmp_path):
    rows = _rows()
    _configure(monkeypatch, tmp_path, rows)
    db.replace_ohlc_with_metadata(
        "300888",
        rows,
        source="tickflow",
        fetched_at=f"{rows[-1]['date']} 14:30:00",
    )
    now = datetime.fromisoformat(rows[-1]["date"]).replace(hour=16)
    monkeypatch.setattr(server, "_now", lambda: now)

    response = TestClient(server.app).post(
        "/api/stock/clean-k/analyze",
        json={"stockCode": "300888", "period": 20},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["targetTradeDate"] == rows[-1]["date"]
    assert body["endDate"] == rows[-2]["date"]
    assert body["latestDataDate"] == rows[-2]["date"]
    assert body["dataIsFresh"] is False
    assert body["excludedIncompleteDate"] == rows[-1]["date"]
    assert "INCOMPLETE_TARGET_BAR_EXCLUDED" in body["riskFlags"]


def test_clean_k_api_rejects_invalid_code_and_period(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    client = TestClient(server.app)

    invalid_code = client.post(
        "/api/stock/clean-k/analyze", json={"stockCode": "30088", "period": 20}
    )
    invalid_period = client.post(
        "/api/stock/clean-k/analyze", json={"stockCode": "300888", "period": 9}
    )
    fractional_period = client.post(
        "/api/stock/clean-k/analyze", json={"stockCode": "300888", "period": 20.5}
    )

    assert invalid_code.status_code == 400
    assert invalid_code.json()["error"] == "INVALID_STOCK_CODE"
    assert invalid_period.status_code == 400
    assert invalid_period.json()["error"] == "INVALID_PERIOD"
    assert fractional_period.status_code == 400
    assert fractional_period.json()["error"] == "INVALID_PERIOD"


def test_clean_k_api_returns_not_found_and_insufficient_history(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    client = TestClient(server.app)
    missing = client.post(
        "/api/stock/clean-k/analyze", json={"stockCode": "300888", "period": 20}
    )

    db.save_ohlc("300888", _rows(25))
    insufficient = client.post(
        "/api/stock/clean-k/analyze", json={"stockCode": "300888", "period": 20}
    )

    assert missing.status_code == 404
    assert missing.json()["error"] == "KLINE_NOT_FOUND"
    assert insufficient.status_code == 422
    assert insufficient.json()["error"] == "INSUFFICIENT_KLINE_DATA"

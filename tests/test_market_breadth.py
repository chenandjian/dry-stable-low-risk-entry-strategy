from fastapi.testclient import TestClient
import pytest

import scanner.db as db
import scanner.market_breadth as market_breadth_mod
import server as server_mod
from scanner.market_breadth import MarketBreadthDataChanging, build_market_breadth_history
from strategy6 import STRATEGY6_TYPE


def _bar(code: str, date: str, close: float) -> tuple:
    return (code, date, close, close, close, close, 1000, 10000)


def _seed_market_data(db_path: str) -> None:
    db.init_db(db_path)
    conn = db.get_conn()
    conn.executemany(
        "INSERT INTO stock_pool(code,name,market) VALUES(?,?,?)",
        [
            ("000001", "上涨样本", "SZ"),
            ("000002", "下跌样本", "SZ"),
            ("000003", "停牌样本", "SZ"),
            ("000004", "跨日缺口样本", "SZ"),
            ("600001", "平盘样本", "SH"),
        ],
    )
    conn.executemany(
        "INSERT INTO daily_ohlc(code,date,open,high,low,close,volume,turnover) VALUES(?,?,?,?,?,?,?,?)",
        [
            _bar("000001", "2026-01-05", 10),
            _bar("000001", "2026-01-06", 11),
            _bar("000002", "2026-01-05", 10),
            _bar("000002", "2026-01-06", 9),
            _bar("000003", "2026-01-05", 10),
            _bar("000004", "2026-01-02", 8),
            _bar("000004", "2026-01-06", 12),
            _bar("600001", "2026-01-05", 10),
            _bar("600001", "2026-01-06", 10),
        ],
    )
    for symbol, base in (
        ("sh000001", 3000),
        ("sz399001", 10000),
        ("sz399006", 2000),
        ("hs300", 4000),
    ):
        db.upsert_market_index_ohlc(
            symbol,
            [
                {"date": "2026-01-05", "open": base, "high": base, "low": base, "close": base, "volume": 1, "turnover": 1},
                {"date": "2026-01-06", "open": base + 10, "high": base + 10, "low": base + 10, "close": base + 10, "volume": 1, "turnover": 1},
            ],
            source="tickflow",
        )
    conn.commit()


def _seed_strategy6_signal() -> None:
    db.create_scan_task("s6-breadth", "2026-01-06 15:30:00", strategy_type=STRATEGY6_TYPE)
    conn = db.get_conn()
    conn.execute(
        "UPDATE scan_tasks SET status='completed', latest_trade_date='2026-01-06' WHERE id='s6-breadth'"
    )
    conn.executemany(
        """INSERT INTO strategy6_candidates
           (task_id, code, name, evaluation_date, candidate_type, classification, total_score)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [
            ("s6-breadth", "000001", "上涨样本", "2026-01-06", "KEY_CANDIDATE", "highlight", 80),
            ("s6-breadth", "000002", "下跌样本", "2026-01-06", "WATCH_CANDIDATE", "watch", 70),
            ("s6-breadth", "000003", "仅VCP观察", "2026-01-06", "REJECTED", "observation", 60),
        ],
    )
    conn.commit()


def test_market_breadth_uses_exact_previous_market_date_and_audits_missing_rows(tmp_path):
    _seed_market_data(str(tmp_path / "breadth.db"))

    payload = build_market_breadth_history(start_date="2026-01-06", end_date="2026-01-06")

    assert payload["meta"]["data_mode"] == "CURRENT_UNIVERSE_RECONSTRUCTION"
    assert payload["meta"]["affects_strategy6"] is False
    row = payload["rows"][0]
    assert row["previous_trade_date"] == "2026-01-05"
    assert row["up_count"] == 1
    assert row["down_count"] == 1
    assert row["flat_count"] == 1
    assert row["valid_count"] == 3
    assert row["unavailable_count"] == 2
    assert row["data_quality"] == "LOW_COVERAGE"
    assert row["down_ratio"] == 1 / 3
    assert row["breadth"] == 0
    assert row["indexes"]["sh000001"]["source"] == "tickflow"
    assert row["indexes"]["sh000001"]["daily_return"] == pytest.approx(10 / 3000)


def test_market_breadth_overlays_only_latest_completed_strategy6_trading_task(tmp_path):
    _seed_market_data(str(tmp_path / "signals.db"))
    _seed_strategy6_signal()

    payload = build_market_breadth_history(start_date="2026-01-06", end_date="2026-01-06")

    signal = payload["rows"][0]["strategy6_signal"]
    assert signal["task_id"] == "s6-breadth"
    assert signal["total"] == 2
    assert signal["key_count"] == 1
    assert signal["watch_count"] == 1
    assert {item["code"] for item in signal["stocks"]} == {"000001", "000002"}


def test_market_breadth_refreshes_latest_cached_day_when_local_close_changes(tmp_path):
    _seed_market_data(str(tmp_path / "cache-refresh.db"))
    first = build_market_breadth_history(start_date="2026-01-06", end_date="2026-01-06")
    assert first["rows"][0]["up_count"] == 1

    conn = db.get_conn()
    conn.execute("UPDATE daily_ohlc SET close=9 WHERE code='000001' AND date='2026-01-06'")
    conn.commit()
    second = build_market_breadth_history(start_date="2026-01-06", end_date="2026-01-06")

    assert second["rows"][0]["up_count"] == 0
    assert second["rows"][0]["down_count"] == 2


def test_market_breadth_invalidates_historical_cache_when_ohlc_revision_changes(tmp_path):
    _seed_market_data(str(tmp_path / "revision.db"))
    conn = db.get_conn()
    conn.executemany(
        "INSERT INTO daily_ohlc(code,date,open,high,low,close,volume,turnover) VALUES(?,?,?,?,?,?,?,?)",
        [
            _bar("000001", "2026-01-07", 12),
            _bar("000002", "2026-01-07", 8),
            _bar("600001", "2026-01-07", 10),
        ],
    )
    for symbol, base in (("sh000001", 3010), ("sz399001", 10010), ("sz399006", 2010), ("hs300", 4010)):
        db.upsert_market_index_ohlc(
            symbol,
            [{"date": "2026-01-07", "open": base, "high": base, "low": base, "close": base, "volume": 1, "turnover": 1}],
            source="tickflow",
        )
    conn.executemany(
        """INSERT INTO daily_ohlc_metadata
           (code,source,price_basis,row_count,first_date,latest_date,fetched_at)
           VALUES(?, 'tickflow', 'FORWARD_ADJUSTED', ?, ?, ?, ?)""",
        [
            ("000001", 3, "2026-01-05", "2026-01-07", "2026-01-07 10:00:00"),
            ("000002", 3, "2026-01-05", "2026-01-07", "2026-01-07 10:00:00"),
            ("000003", 1, "2026-01-05", "2026-01-05", "2026-01-07 10:00:00"),
            ("000004", 2, "2026-01-02", "2026-01-06", "2026-01-07 10:00:00"),
            ("600001", 3, "2026-01-05", "2026-01-07", "2026-01-07 10:00:00"),
        ],
    )
    conn.commit()
    first = build_market_breadth_history(start_date="2026-01-06", end_date="2026-01-07")
    assert first["rows"][0]["up_count"] == 1

    conn.execute("UPDATE daily_ohlc SET close=9 WHERE code='000001' AND date='2026-01-06'")
    conn.execute("UPDATE daily_ohlc_metadata SET fetched_at='2026-01-07 11:00:00' WHERE code='000001'")
    conn.commit()
    second = build_market_breadth_history(start_date="2026-01-06", end_date="2026-01-07")

    assert second["rows"][0]["up_count"] == 0
    assert second["rows"][0]["down_count"] == 2


def test_market_breadth_refuses_mixed_snapshot_when_data_changes_during_build(tmp_path, monkeypatch):
    _seed_market_data(str(tmp_path / "concurrent.db"))
    revisions = iter(["before", "after"])
    monkeypatch.setattr(market_breadth_mod, "_source_revision", lambda conn: next(revisions))

    with pytest.raises(MarketBreadthDataChanging):
        build_market_breadth_history(start_date="2026-01-06", end_date="2026-01-06")

    assert db.get_conn().execute("SELECT COUNT(*) FROM market_breadth_daily").fetchone()[0] == 0


def test_market_breadth_api_returns_real_history_without_changing_strategy(tmp_path, monkeypatch):
    db_path = str(tmp_path / "api.db")
    _seed_market_data(db_path)
    _seed_strategy6_signal()
    monkeypatch.setattr(server_mod, "load_config", lambda: {"data": {"database_path": db_path}})

    response = TestClient(server_mod.app).get(
        "/api/market-breadth/history?start_date=2026-01-06&end_date=2026-01-06"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["affects_strategy6"] is False
    assert body["rows"][0]["date"] == "2026-01-06"
    assert body["summary"]["down_count"] == 1

    invalid = TestClient(server_mod.app).get("/api/market-breadth/history?start_date=not-a-date")
    assert invalid.status_code == 400
    assert invalid.json()["error"] == "INVALID_MARKET_BREADTH_QUERY"

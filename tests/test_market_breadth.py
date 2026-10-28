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


def _seed_replaceable_three_day_market_data(db_path: str) -> dict[str, list[dict]]:
    db.init_db(db_path)
    conn = db.get_conn()
    conn.executemany(
        "INSERT INTO stock_pool(code,name,market) VALUES(?,?,?)",
        [
            ("000001", "上涨样本", "SZ"),
            ("000002", "下跌样本", "SZ"),
            ("600001", "平盘样本", "SH"),
        ],
    )
    conn.commit()
    series = {
        "000001": [
            {"date": "2026-01-05", "open": 10, "high": 10, "low": 10, "close": 10, "volume": 1},
            {"date": "2026-01-06", "open": 11, "high": 11, "low": 11, "close": 11, "volume": 1},
            {"date": "2026-01-07", "open": 12, "high": 12, "low": 12, "close": 12, "volume": 1},
        ],
        "000002": [
            {"date": "2026-01-05", "open": 10, "high": 10, "low": 10, "close": 10, "volume": 1},
            {"date": "2026-01-06", "open": 9, "high": 9, "low": 9, "close": 9, "volume": 1},
            {"date": "2026-01-07", "open": 8, "high": 8, "low": 8, "close": 8, "volume": 1},
        ],
        "600001": [
            {"date": "2026-01-05", "open": 10, "high": 10, "low": 10, "close": 10, "volume": 1},
            {"date": "2026-01-06", "open": 10, "high": 10, "low": 10, "close": 10, "volume": 1},
            {"date": "2026-01-07", "open": 10, "high": 10, "low": 10, "close": 10, "volume": 1},
        ],
    }
    for code, rows in series.items():
        db.replace_ohlc_with_metadata(
            code,
            rows,
            source="tickflow",
            fetched_at="2026-01-07 10:00:00",
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
                {"date": "2026-01-05", "open": base, "high": base, "low": base, "close": base, "volume": 1},
                {"date": "2026-01-06", "open": base + 10, "high": base + 10, "low": base + 10, "close": base + 10, "volume": 1},
                {"date": "2026-01-07", "open": base + 20, "high": base + 20, "low": base + 20, "close": base + 20, "volume": 1},
            ],
            source="tickflow",
        )
    conn.commit()
    return series


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
    assert row["estimated_limit_up_count"] == 1
    assert row["estimated_limit_down_count"] == 1
    assert row["limit_estimate_sample_count"] == 3
    assert row["indexes"]["sh000001"]["source"] == "tickflow"
    assert row["indexes"]["sh000001"]["daily_return"] == pytest.approx(10 / 3000)


def test_limit_estimates_respect_board_bands_and_exclude_st_unknown_and_extreme_moves(tmp_path):
    _seed_market_data(str(tmp_path / 'limits.db'))
    conn = db.get_conn()
    stocks = [('300001', '创业样本', 12.), ('688001', '科创样本', 8.),
              ('920001', '北交样本', 13.), ('600002', 'ST样本', 11.),
              ('999999', '未知板块', 11.), ('600003', '异常大涨', 14.),
              ('600004', '接近上限', 10.98), ('600005', '普通大涨', 10.97),
              ('600006', ' N新股样本', 11), ('600007', ' C新股样本', 11)]
    conn.executemany('INSERT INTO stock_pool(code,name) VALUES(?,?)', [(x[0], x[1]) for x in stocks])
    for code, _, close in stocks:
        conn.executemany('INSERT INTO daily_ohlc VALUES(?,?,?,?,?,?,?,?)',
                         [_bar(code, '2026-01-05', 10), _bar(code, '2026-01-06', close)])
    conn.commit()
    payload = build_market_breadth_history()
    row = payload['rows'][-1]
    assert row['estimated_limit_up_count'] == 4
    assert row['estimated_limit_down_count'] == 2
    assert row['limit_estimate_sample_count'] == 9
    assert payload['meta']['limit_count_method'] == 'LOCAL_ADJUSTED_RETURN_ESTIMATE_V1'
    assert row['estimated_limit_net_count'] == 2


def test_limit_estimates_rebuild_old_cache_and_follow_name_changes(tmp_path):
    _seed_replaceable_three_day_market_data(str(tmp_path / 'limit-cache.db'))
    build_market_breadth_history()
    conn = db.get_conn()
    conn.execute("UPDATE market_breadth_daily SET estimated_limit_up_count=NULL,limit_estimate_revision=NULL")
    conn.commit()
    assert build_market_breadth_history()['rows'][0]['estimated_limit_up_count'] == 1
    conn.execute("UPDATE stock_pool SET name='ST样本' WHERE code='000001'")
    conn.commit()
    row = build_market_breadth_history()['rows'][0]
    assert row['estimated_limit_up_count'] == 0
    assert row['limit_estimate_sample_count'] == 2


def test_no_estimable_stocks_is_unknown_not_zero(tmp_path):
    _seed_market_data(str(tmp_path / 'no-limits.db'))
    conn = db.get_conn()
    conn.execute("UPDATE stock_pool SET name='ST样本'")
    conn.commit()
    row = build_market_breadth_history()['rows'][-1]
    assert row['limit_estimate_sample_count'] == 0
    assert row['estimated_limit_up_count'] is None
    assert row['estimated_limit_down_count'] is None
    assert row['estimated_limit_net_count'] is None


def test_limit_estimate_chinext_transition_uses_historical_date(tmp_path):
    _seed_market_data(str(tmp_path / 'historical-limit.db'))
    conn = db.get_conn()
    conn.execute("INSERT INTO stock_pool(code,name) VALUES('300001','创业样本')")
    conn.executemany('INSERT INTO daily_ohlc VALUES(?,?,?,?,?,?,?,?)',
                     [_bar('300001', day, close) for day, close in
                      [('2020-08-20', 10), ('2020-08-21', 11), ('2020-08-24', 13.2)]])
    conn.commit()
    for symbol in ('sh000001', 'sz399001', 'sz399006', 'hs300'):
        db.upsert_market_index_ohlc(symbol, [
            dict(date=day, open=100, high=100, low=100, close=100, volume=1)
            for day in ('2020-08-20', '2020-08-21', '2020-08-24')], source='test')
    payload = build_market_breadth_history(start_date='2020-08-21', end_date='2020-08-24')
    assert [r['estimated_limit_up_count'] for r in payload['rows']] == [1, 1]


def test_limit_cache_migration_preserves_legacy_rows(tmp_path):
    import sqlite3
    path = str(tmp_path / 'legacy-limit.db')
    with sqlite3.connect(path) as conn:
        conn.execute('''CREATE TABLE market_breadth_daily (
            trade_date TEXT PRIMARY KEY, previous_trade_date TEXT NOT NULL,
            up_count INTEGER NOT NULL, down_count INTEGER NOT NULL, flat_count INTEGER NOT NULL,
            source_mode TEXT DEFAULT 'CURRENT_UNIVERSE_RECONSTRUCTION', calculated_at TEXT)''')
        conn.execute("INSERT INTO market_breadth_daily VALUES('2026-01-06','2026-01-05',5,3,2,'CURRENT_UNIVERSE_RECONSTRUCTION','old')")
    db.init_db(path)
    row = db.get_conn().execute('SELECT up_count,estimated_limit_up_count,limit_estimate_revision FROM market_breadth_daily').fetchone()
    assert tuple(row) == (5, None, None)


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


def test_market_breadth_keeps_historical_cache_when_only_fetch_time_changes(tmp_path):
    series = _seed_replaceable_three_day_market_data(str(tmp_path / "stable-revision.db"))
    build_market_breadth_history(start_date="2026-01-06", end_date="2026-01-07")
    conn = db.get_conn()
    conn.execute(
        "UPDATE market_breadth_daily SET calculated_at='2000-01-01 00:00:00' WHERE trade_date='2026-01-06'"
    )
    conn.commit()

    for code, rows in series.items():
        db.replace_ohlc_with_metadata(
            code,
            rows,
            source="tickflow",
            fetched_at="2026-01-07 11:00:00",
        )
    build_market_breadth_history(start_date="2026-01-06", end_date="2026-01-07")

    calculated_at = conn.execute(
        "SELECT calculated_at FROM market_breadth_daily WHERE trade_date='2026-01-06'"
    ).fetchone()[0]
    assert calculated_at == "2000-01-01 00:00:00"


def test_market_breadth_keeps_history_when_formal_writer_only_appends_new_day(tmp_path):
    series = _seed_replaceable_three_day_market_data(str(tmp_path / "append-revision.db"))
    build_market_breadth_history(start_date="2026-01-06", end_date="2026-01-07")
    conn = db.get_conn()
    conn.execute(
        "UPDATE market_breadth_daily SET calculated_at='2000-01-01 00:00:00' WHERE trade_date='2026-01-06'"
    )
    conn.commit()

    for code, rows in series.items():
        appended = [*rows, {**rows[-1], "date": "2026-01-08"}]
        db.replace_ohlc_with_metadata(
            code,
            appended,
            source="tickflow",
            fetched_at="2026-01-08 15:30:00",
        )
    for symbol, base in (
        ("sh000001", 3020),
        ("sz399001", 10020),
        ("sz399006", 2020),
        ("hs300", 4020),
    ):
        db.upsert_market_index_ohlc(
            symbol,
            [{"date": "2026-01-08", "open": base, "high": base, "low": base, "close": base, "volume": 1}],
            source="tickflow",
        )
    build_market_breadth_history(start_date="2026-01-06", end_date="2026-01-08")

    calculated_at = conn.execute(
        "SELECT calculated_at FROM market_breadth_daily WHERE trade_date='2026-01-06'"
    ).fetchone()[0]
    assert calculated_at == "2000-01-01 00:00:00"


def test_market_breadth_rebuilds_history_when_formal_writer_changes_close(tmp_path):
    series = _seed_replaceable_three_day_market_data(str(tmp_path / "changed-revision.db"))
    first = build_market_breadth_history(start_date="2026-01-06", end_date="2026-01-07")
    assert first["rows"][0]["up_count"] == 1

    corrected = [dict(row) for row in series["000001"]]
    corrected[1].update({"open": 9, "high": 9, "low": 9, "close": 9})
    db.replace_ohlc_with_metadata(
        "000001",
        corrected,
        source="tickflow",
        fetched_at="2026-01-07 11:00:00",
    )
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


def test_market_breadth_initializes_database_off_event_loop(monkeypatch):
    import asyncio
    import threading
    event_thread = threading.get_ident()
    initialized = []
    monkeypatch.setattr(server_mod, 'load_config', lambda: {'data': {'database_path': 'unused.db'}})
    monkeypatch.setattr(db, 'init_db', lambda path: initialized.append(threading.get_ident()))
    monkeypatch.setattr(server_mod, 'build_market_breadth_history', lambda **kwargs: {'rows': []})
    asyncio.run(server_mod.market_breadth_history())
    assert initialized and initialized[0] != event_thread


def test_refresh_preserves_off_calendar_gap_semantics(tmp_path):
    _seed_market_data(str(tmp_path / 'off-calendar.db'))
    conn = db.get_conn()
    conn.executemany('INSERT INTO daily_ohlc VALUES(?,?,?,?,?,?,?,?)',
                     [_bar('000001', '2026-01-07', 10), _bar('000001', '2026-01-08', 11)])
    for symbol in ('sh000001', 'sz399001', 'sz399006', 'hs300'):
        conn.execute('INSERT INTO market_index_ohlc(symbol,date,close) VALUES(?,?,?)', (symbol,'2026-01-08',100))
    conn.commit()
    payload = build_market_breadth_history(start_date='2026-01-08', end_date='2026-01-08')
    assert payload['rows'] == []  # Jan 7 is not a market date; do not silently skip the bad bar.


def test_small_market_breadth_refresh_seeks_by_date(tmp_path):
    _seed_market_data(str(tmp_path / 'date-seek.db'))
    statements = []
    db.get_conn().set_trace_callback(statements.append)
    try:
        result = build_market_breadth_history()
    finally:
        db.get_conn().set_trace_callback(None)
    assert result['rows'][-1]['up_count'] == 1
    assert any('WITH moves AS' in sql and 'INDEXED BY idx_ohlc_date' in sql for sql in statements)

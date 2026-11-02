from scanner import db


def test_bounded_ohlc_reads_limit_in_sql_and_preserve_ascending_order(tmp_path):
    db.init_db(str(tmp_path / "bounded.db"))
    rows = [dict(date=f"2026-01-{day:02d}", open=10, high=11, low=9,
                 close=10, volume=100, turnover=1000) for day in range(1, 11)]
    db.save_ohlc("000001", rows)
    queries = []
    conn = db.get_conn()
    conn.set_trace_callback(queries.append)
    try:
        assert db.get_ohlc("000001", max_rows=3) == rows[-3:]
        assert any("ORDER BY date DESC LIMIT 3" in query for query in queries)
        assert db.get_ohlc("000001", max_rows=1) == rows[-1:]
        assert db.get_ohlc("000001", max_rows=100) == rows
        assert db.get_ohlc("000001") == rows
        assert db.get_ohlc("999999", max_rows=1) is None
    finally:
        conn.set_trace_callback(None)

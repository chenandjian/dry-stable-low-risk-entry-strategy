import sqlite3

from strategy6.backtest.data import (
    audit_ohlc_rows,
    build_data_fingerprint,
    build_database_fingerprint,
    slice_visible_rows,
)


ROWS = [
    {"date": "2025-01-02", "open": 10.0, "high": 10.5, "low": 9.8, "close": 10.2, "volume": 100},
    {"date": "2025-01-03", "open": 10.2, "high": 10.6, "low": 10.0, "close": 10.4, "volume": 120},
]


def test_data_audit_and_fingerprint_are_deterministic():
    audit = audit_ohlc_rows(ROWS)
    assert audit["valid"] is True
    assert audit["rows"] == 2
    assert audit["min_date"] == "2025-01-02"
    assert build_data_fingerprint({"000001": ROWS}) == build_data_fingerprint({"000001": list(ROWS)})


def test_data_audit_rejects_duplicate_date_and_illegal_ohlc():
    duplicate = ROWS + [dict(ROWS[-1])]
    assert "DUPLICATE_DATE" in audit_ohlc_rows(duplicate)["errors"]
    broken = [dict(ROWS[0], high=9.0)]
    assert "ILLEGAL_OHLC" in audit_ohlc_rows(broken)["errors"]


def test_visible_slice_never_returns_future_rows():
    assert [row["date"] for row in slice_visible_rows(ROWS, "2025-01-02")] == ["2025-01-02"]


def test_database_fingerprint_changes_when_price_changes_without_row_count_change():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE stock_pool(code TEXT, name TEXT, market TEXT);
        CREATE TABLE daily_ohlc(
            code TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL,
            volume REAL, turnover REAL
        );
        CREATE TABLE market_index_ohlc(
            symbol TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL,
            volume REAL, turnover REAL, source TEXT, fetched_at TEXT
        );
        INSERT INTO stock_pool VALUES ('000001', '样本', 'sz');
        INSERT INTO daily_ohlc VALUES ('000001','2025-01-02',10,11,9,10,100,1000);
        INSERT INTO market_index_ohlc VALUES ('sh000001','2025-01-02',3000,3100,2900,3050,100,1000,'sina','x');
    """)
    first = build_database_fingerprint(conn)
    conn.execute("UPDATE daily_ohlc SET close=10.5 WHERE code='000001'")
    second = build_database_fingerprint(conn)

    assert first != second
    conn.execute("UPDATE daily_ohlc SET close=10 WHERE code='000001'")
    assert first == build_database_fingerprint(conn)

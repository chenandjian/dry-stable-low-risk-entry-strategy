import sqlite3

from tools.data_repair.repair_invalid_ohlc import (
    find_yfinance_sourced_codes,
    refetch_yfinance_sourced_stocks,
    repair_invalid_rows,
)


def _init_db(path):
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE daily_ohlc (
            code TEXT,
            date TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            turnover REAL,
            PRIMARY KEY(code, date)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE task_stocks (
            task_id TEXT,
            code TEXT,
            fallback_source TEXT,
            kline_latest_date TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO daily_ohlc VALUES (?,?,?,?,?,?,?,?)",
        ("000006", "2026-06-25", 7.75, 7.52, 7.23, 7.36, 22670823, 166857260),
    )
    conn.execute(
        "INSERT INTO task_stocks VALUES (?,?,?,?)",
        ("task-1", "000006", "yfinance", "2026-06-25"),
    )
    conn.commit()
    conn.close()


def test_repair_invalid_rows_is_dry_run_by_default(tmp_path):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    def fake_sina(code, days):
        return [{
            "date": "2026-06-25",
            "open": 7.45,
            "high": 7.52,
            "low": 7.23,
            "close": 7.36,
            "volume": 22670823,
            "turnover": 166857257.28,
        }]

    result = repair_invalid_rows(
        str(db_path),
        task_id="task-1",
        fetchers=[("sina", fake_sina)],
        apply=False,
    )

    conn = sqlite3.connect(db_path)
    open_ = conn.execute(
        "SELECT open FROM daily_ohlc WHERE code='000006' AND date='2026-06-25'"
    ).fetchone()[0]
    conn.close()
    assert result.scanned == 1
    assert result.repaired == 1
    assert open_ == 7.75


def test_repair_invalid_rows_updates_with_trusted_source_when_applied(tmp_path):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    def fake_sina(code, days):
        return [{
            "date": "2026-06-25",
            "open": 7.45,
            "high": 7.52,
            "low": 7.23,
            "close": 7.36,
            "volume": 22670823,
            "turnover": 166857257.28,
        }]

    result = repair_invalid_rows(
        str(db_path),
        task_id="task-1",
        fetchers=[("sina", fake_sina)],
        apply=True,
    )

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT open, high, low, close FROM daily_ohlc WHERE code='000006' AND date='2026-06-25'"
    ).fetchone()
    remaining_bad = conn.execute(
        "SELECT COUNT(*) FROM daily_ohlc WHERE high < max(open, close, low) OR low > min(open, close, high)"
    ).fetchone()[0]
    conn.close()
    assert result.scanned == 1
    assert result.repaired == 1
    assert row == (7.45, 7.52, 7.23, 7.36)
    assert remaining_bad == 0


def test_repair_invalid_rows_tries_next_source_when_first_replacement_is_invalid(tmp_path):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    def invalid_first(code, days):
        return [{
            "date": "2026-06-25",
            "open": 7.75,
            "high": 7.52,
            "low": 7.23,
            "close": 7.36,
            "volume": 1,
            "turnover": 1,
        }]

    def valid_second(code, days):
        return [{
            "date": "2026-06-25",
            "open": 7.45,
            "high": 7.52,
            "low": 7.23,
            "close": 7.36,
            "volume": 1,
            "turnover": 1,
        }]

    result = repair_invalid_rows(
        str(db_path),
        task_id="task-1",
        fetchers=[("bad", invalid_first), ("good", valid_second)],
        apply=True,
    )

    conn = sqlite3.connect(db_path)
    open_ = conn.execute(
        "SELECT open FROM daily_ohlc WHERE code='000006' AND date='2026-06-25'"
    ).fetchone()[0]
    conn.close()
    assert result.repaired == 1
    assert result.invalid_replacement == 0
    assert open_ == 7.45


def test_find_yfinance_sourced_codes_deduplicates_fallback_rows(tmp_path):
    db_path = tmp_path / "test.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO task_stocks VALUES (?,?,?,?)",
        ("task-2", "000006", "yfinance", "2026-06-25"),
    )
    conn.execute(
        "INSERT INTO task_stocks VALUES (?,?,?,?)",
        ("task-3", "000007", "sina", "2026-06-25"),
    )
    conn.commit()

    codes = find_yfinance_sourced_codes(conn)

    conn.close()
    assert codes == ["000006"]


def test_refetch_yfinance_sourced_stocks_replaces_whole_ohlc_series_when_applied(tmp_path):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    def fake_sina(code, days):
        assert code == "000006"
        assert days == 500
        return [
            {
                "date": "2026-06-24",
                "open": 7.30,
                "high": 7.40,
                "low": 7.20,
                "close": 7.35,
                "volume": 100,
                "turnover": 735,
            },
            {
                "date": "2026-06-25",
                "open": 7.45,
                "high": 7.52,
                "low": 7.23,
                "close": 7.36,
                "volume": 200,
                "turnover": 1472,
            },
        ]

    result = refetch_yfinance_sourced_stocks(
        str(db_path),
        fetchers=[("sina", fake_sina)],
        days=500,
        apply=True,
    )

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT date, open, high, low, close FROM daily_ohlc WHERE code='000006' ORDER BY date"
    ).fetchall()
    conn.close()
    assert result.scanned == 1
    assert result.repaired == 1
    assert rows == [
        ("2026-06-24", 7.30, 7.40, 7.20, 7.35),
        ("2026-06-25", 7.45, 7.52, 7.23, 7.36),
    ]


def test_refetch_yfinance_sourced_stocks_tries_next_source_when_first_series_is_invalid(tmp_path):
    db_path = tmp_path / "test.db"
    _init_db(db_path)

    def invalid_first(code, days):
        return [{
            "date": "2026-06-25",
            "open": 7.75,
            "high": 7.52,
            "low": 7.23,
            "close": 7.36,
            "volume": 1,
            "turnover": 1,
        }]

    def valid_second(code, days):
        return [{
            "date": "2026-06-25",
            "open": 7.45,
            "high": 7.52,
            "low": 7.23,
            "close": 7.36,
            "volume": 1,
            "turnover": 1,
        }]

    result = refetch_yfinance_sourced_stocks(
        str(db_path),
        fetchers=[("bad", invalid_first), ("good", valid_second)],
        apply=True,
    )

    conn = sqlite3.connect(db_path)
    open_ = conn.execute(
        "SELECT open FROM daily_ohlc WHERE code='000006' AND date='2026-06-25'"
    ).fetchone()[0]
    conn.close()
    assert result.repaired == 1
    assert result.invalid_replacement == 0
    assert open_ == 7.45

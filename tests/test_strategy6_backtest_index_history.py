from scanner import db
from strategy6.backtest.index_history import (
    INDEX_SYMBOLS,
    ensure_index_history,
    load_index_history,
    validate_index_history_data,
)


def test_index_history_reports_blocked_until_all_symbols_cover_range(tmp_path):
    db.init_db(str(tmp_path / "index.db"))
    db.save_market_index_ohlc("sh000001", [{
        "date": "2025-01-02", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1,
    }], source="fixture")
    result = load_index_history("2025-01-02", "2025-01-03")
    assert result.status == "BLOCKED_INDEX_HISTORY"
    assert "sz399001" in result.missing_symbols


def test_index_fetch_only_requests_four_approved_symbols_and_persists(tmp_path):
    db.init_db(str(tmp_path / "index.db"))
    calls = []

    def fetcher(symbol, days):
        calls.append((symbol, days))
        return [
            {"date": "2025-01-02", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1},
            {"date": "2025-01-03", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 2},
        ]

    result = ensure_index_history("2025-01-02", "2025-01-03", days=900, fetcher=fetcher)
    assert [symbol for symbol, _ in calls] == list(INDEX_SYMBOLS.values())
    assert result.status == "READY"
    assert set(result.data_by_symbol) == set(INDEX_SYMBOLS)
    assert db.get_market_index_coverage("sh000300")["rows"] == 2


def test_index_history_blocks_when_one_index_has_internal_trading_date_gap(tmp_path):
    db.init_db(str(tmp_path / "gap.db"))
    dates = ["2025-01-02", "2025-01-03", "2025-01-06"]
    for symbol in INDEX_SYMBOLS.values():
        symbol_dates = dates if symbol != "sz399006" else [dates[0], dates[2]]
        db.save_market_index_ohlc(symbol, [
            {"date": date, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1}
            for date in symbol_dates
        ], source="fixture")

    result = load_index_history("2025-01-02", "2025-01-06")

    assert result.status == "BLOCKED_INDEX_HISTORY"
    assert "sz399006" in result.missing_symbols
    assert result.coverage["sz399006"]["missing_dates"] == ["2025-01-03"]


def test_index_history_blocks_when_all_indexes_miss_reference_calendar_date():
    data = {
        symbol: [
            {"date": date, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1}
            for date in ("2025-01-02", "2025-01-06")
        ]
        for symbol in INDEX_SYMBOLS
    }

    result = validate_index_history_data(
        data,
        start_date="2025-01-02",
        end_date="2025-01-06",
        reference_dates=["2025-01-02", "2025-01-03", "2025-01-06"],
    )

    assert result.status == "BLOCKED_INDEX_HISTORY"
    assert set(result.missing_symbols) == set(INDEX_SYMBOLS)
    assert result.coverage["sh000001"]["missing_dates"] == ["2025-01-03"]


def test_index_history_loads_tickflow_hs300_storage_key(tmp_path):
    db.init_db(str(tmp_path / "tickflow-index.db"))
    dates = ["2025-01-02", "2025-01-03"]
    for symbol in ("sh000001", "sz399001", "sz399006", "hs300"):
        db.save_market_index_ohlc(symbol, [
            {
                "date": date,
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10,
                "volume": 1,
            }
            for date in dates
        ], source="tickflow")

    result = load_index_history(dates[0], dates[-1])

    assert result.status == "READY"
    assert result.missing_symbols == []
    assert [row["date"] for row in result.data_by_symbol["hs300"]] == dates
    assert result.coverage["hs300"]["stored_symbol"] == "hs300"

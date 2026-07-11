from scanner import db
from strategy6.backtest.index_history import (
    INDEX_SYMBOLS,
    ensure_index_history,
    load_index_history,
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

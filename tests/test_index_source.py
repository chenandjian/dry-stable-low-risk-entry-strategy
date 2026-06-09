from scanner import index_source
from scanner.index_source import normalize_index_ohlc, fetch_market_index_daily


def test_normalize_index_ohlc_sorts_and_keeps_required_fields():
    raw = [
        {"date": "2026-06-02", "open": 101, "high": 103, "low": 100, "close": 102, "volume": 20},
        {"date": "2026-06-01", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 10},
    ]

    result = normalize_index_ohlc(raw)

    assert [d["date"] for d in result] == ["2026-06-01", "2026-06-02"]
    assert result[0]["close"] == 101
    assert result[1]["volume"] == 20


def test_normalize_index_ohlc_skips_incomplete_rows():
    raw = [
        {"date": "2026-06-01", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 10},
        {"date": "2026-06-02", "open": 101, "high": 103, "close": 102, "volume": 20},
    ]

    result = normalize_index_ohlc(raw)

    assert len(result) == 1
    assert result[0]["date"] == "2026-06-01"


# ---- BUG-002 regression: market index uses correct symbol ----


def test_default_index_is_sh000001():
    """BUG-002: Default market index is 上证指数, not 平安银行."""
    assert index_source.DEFAULT_MARKET_INDEX == "sh000001"


def test_fetch_index_requests_sh000001(monkeypatch):
    """BUG-002: Mock Sina to verify requests sh000001, not sz000001."""
    captured = []

    def fake_raw(symbol, days=250):
        captured.append(symbol)
        return [{"date": "2026-06-01", "open": "3100", "high": "3120",
                 "low": "3080", "close": "3115", "volume": "100000"}]

    monkeypatch.setattr(index_source, "_fetch_sina_index_raw", fake_raw)
    result = fetch_market_index_daily()
    assert captured[0] == "sh000001", f"Expected sh000001, got {captured[0]}"
    assert result is not None
    assert len(result) == 1


def test_index_failure_returns_none(monkeypatch):
    """BUG-002: Fetch failure → None → caller defaults to 一般."""

    def fake_raw(symbol, days=250):
        return None

    monkeypatch.setattr(index_source, "_fetch_sina_index_raw", fake_raw)
    result = fetch_market_index_daily()
    assert result is None

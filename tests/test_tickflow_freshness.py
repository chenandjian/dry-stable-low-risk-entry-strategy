import pandas as pd

from scanner import db
from tickflow_data.models import BatchFetchResult


def _frame(date):
    return pd.DataFrame([{
        "trade_date": date,
        "open": 10.0,
        "high": 10.5,
        "low": 9.8,
        "close": 10.2,
        "volume": 1000,
        "amount": 1_000_000,
    }])


class _ProbeClient:
    def __init__(self, *, stock_error=None, index_error=None):
        self.stock_error = stock_error
        self.index_error = index_error
        self.stock_calls = []
        self.index_calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def fetch(self, symbols, *, count):
        self.stock_calls.append((list(symbols), count))
        if self.stock_error:
            raise RuntimeError(self.stock_error)
        return BatchFetchResult(
            frames={symbols[0]: _frame("2026-07-23")},
            missing_symbols=[],
        )

    def fetch_indexes(self, symbols, *, count):
        self.index_calls.append((list(symbols), count))
        if self.index_error:
            raise RuntimeError(self.index_error)
        frames = {
            symbol: _frame("2026-07-23" if symbol != "399006.SZ" else "2026-07-22")
            for symbol in symbols
            if symbol != "000300.SH"
        }
        return BatchFetchResult(frames=frames, missing_symbols=["000300.SH"])


def test_freshness_probe_checks_stock_and_four_indexes_without_writing(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "market.db"))
    db.replace_ohlc_with_metadata(
        "000655",
        [{"date": "2026-07-22", "open": 10, "high": 11, "low": 9,
          "close": 10.5, "volume": 1000, "turnover": 10000}],
        source="tickflow",
        fetched_at="2026-07-22 16:00:00",
    )
    db.upsert_market_index_ohlc(
        "sh000001",
        [{"date": "2026-07-22", "open": 3000, "high": 3010, "low": 2990,
          "close": 3005, "volume": 1000, "turnover": 10000}],
        source="tickflow",
    )
    monkeypatch.setattr(
        db,
        "replace_ohlc_with_metadata",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("stock write")),
    )
    monkeypatch.setattr(
        db,
        "upsert_market_index_ohlc",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("index write")),
    )
    client = _ProbeClient()

    from tickflow_data.freshness import check_tickflow_freshness

    result = check_tickflow_freshness(
        "000655",
        target_trade_date="2026-07-23",
        client_factory=lambda: client,
        count=5,
    )

    assert client.stock_calls == [(["000655.SZ"], 5)]
    assert client.index_calls == [(
        ["000001.SH", "399001.SZ", "399006.SZ", "000300.SH"],
        5,
    )]
    assert result["stock"]["status"] == "FRESH"
    assert result["stock"]["remote_latest_date"] == "2026-07-23"
    assert result["stock"]["local_latest_date"] == "2026-07-22"
    assert len(result["indexes"]) == 4
    assert result["indexes"][0]["local_latest_date"] == "2026-07-22"
    assert result["indexes"][2]["status"] == "STALE"
    assert result["indexes"][3]["status"] == "FAILED"
    assert result["overall_status"] == "PARTIAL_FAILURE"


def test_freshness_probe_preserves_indexes_when_stock_request_fails(tmp_path):
    db.init_db(str(tmp_path / "market.db"))
    client = _ProbeClient(stock_error="stock request failed")

    from tickflow_data.freshness import check_tickflow_freshness

    result = check_tickflow_freshness(
        "000655",
        target_trade_date="2026-07-23",
        client_factory=lambda: client,
    )

    assert result["stock"]["status"] == "FAILED"
    assert "stock request failed" in result["stock"]["error"]
    assert len(result["indexes"]) == 4
    assert result["indexes"][0]["status"] == "FRESH"
    assert result["overall_status"] == "PARTIAL_FAILURE"


def test_freshness_probe_preserves_stock_when_index_request_fails(tmp_path):
    db.init_db(str(tmp_path / "market.db"))
    client = _ProbeClient(index_error="index request failed")

    from tickflow_data.freshness import check_tickflow_freshness

    result = check_tickflow_freshness(
        "000655",
        target_trade_date="2026-07-23",
        client_factory=lambda: client,
    )

    assert result["stock"]["status"] == "FRESH"
    assert len(result["indexes"]) == 4
    assert all(item["status"] == "FAILED" for item in result["indexes"])
    assert all("index request failed" in item["error"] for item in result["indexes"])
    assert result["overall_status"] == "PARTIAL_FAILURE"

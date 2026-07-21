import pandas as pd

from scanner import db
from tickflow_data.indexes import (
    MARKET_INDEX_SPECS,
    update_market_indexes,
)
from tickflow_data.models import BatchFetchResult


def _index_frame():
    return pd.DataFrame([
        {
            "trade_date": "2026-07-20",
            "open": 3000,
            "high": 3030,
            "low": 2990,
            "close": 3020,
            "volume": 1234,
            "amount": 5_000_000,
        }
    ])


class _Client:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def fetch_indexes(self, symbols, *, count):
        self.calls.append((list(symbols), count))
        return BatchFetchResult(frames={symbol: _index_frame() for symbol in symbols})


def test_market_index_specs_cover_four_required_real_indexes():
    assert [(item.local_symbol, item.tickflow_symbol) for item in MARKET_INDEX_SPECS] == [
        ("sh000001", "000001.SH"),
        ("sz399001", "399001.SZ"),
        ("sz399006", "399006.SZ"),
        ("hs300", "000300.SH"),
    ]


def test_update_market_indexes_normalizes_and_persists_tickflow_rows(tmp_path):
    db.init_db(str(tmp_path / "market.db"))
    client = _Client()

    results = update_market_indexes(client, history_days=1100)

    assert client.calls == [
        (["000001.SH", "399001.SZ", "399006.SZ", "000300.SH"], 1100)
    ]
    assert all(item["status"] == "success" for item in results)
    assert db.get_market_index_ohlc("sh000001")[-1]["close"] == 3020
    source = db.get_conn().execute(
        "SELECT source FROM market_index_ohlc WHERE symbol='sh000001'"
    ).fetchone()[0]
    assert source == "tickflow"

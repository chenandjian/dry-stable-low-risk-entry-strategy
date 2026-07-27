import sqlite3

import pandas as pd
import pytest

from scanner import db
from tickflow_data.models import BatchFetchResult
from tickflow_data.web_task import TickFlowFullRefreshManager, TickFlowTaskConflict


def _frame(code):
    base = int(code[-2:]) / 100
    return pd.DataFrame(
        [
            {
                "trade_date": f"2026-07-{day:02d}",
                "open": 10 + base + day / 10,
                "high": 10.3 + base + day / 10,
                "low": 9.9 + base + day / 10,
                "close": 10.2 + base + day / 10,
                "volume": 1000 + day,
                "amount": 1_000_000 + day,
            }
            for day in range(1, 4)
        ]
    )


class _ManualLauncher:
    def __init__(self):
        self.targets = []

    def __call__(self, target):
        self.targets.append(target)

    def run_next(self):
        self.targets.pop(0)()


class _Client:
    def __init__(self, responses, calls):
        self.responses = responses
        self.calls = calls

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def fetch(self, symbols, *, count):
        self.calls.append((list(symbols), count))
        return self.responses.pop(0)

    def fetch_indexes(self, symbols, *, count):
        self.calls.append((list(symbols), count, "indexes"))
        return BatchFetchResult(frames={symbol: _frame("600519") for symbol in symbols})


def _seed_database(path):
    db.init_db(str(path))
    stocks = [
        {"code": "600519", "name": "贵州茅台", "market": "SH"},
        {"code": "000001", "name": "平安银行", "market": "SZ"},
    ]
    db.save_stock_pool(stocks)
    return stocks


def test_web_full_refresh_uses_fixed_parameters_backup_and_terminal_report(tmp_path):
    database = tmp_path / "cuphandle.db"
    stocks = _seed_database(database)
    calls = []
    client_kwargs = []
    responses = [
        BatchFetchResult(
            frames={"600519.SH": _frame("600519"), "000001.SZ": _frame("000001")}
        )
    ]
    launcher = _ManualLauncher()

    def client_factory(**kwargs):
        client_kwargs.append(kwargs)
        return _Client(responses, calls)

    manager = TickFlowFullRefreshManager(
        client_factory=client_factory,
        thread_launcher=launcher,
    )

    started = manager.start(database, stocks, api_key="refresh-secret")
    assert started["status"] == "running"
    assert started["parameters"] == {
        "history_days": 1100,
        "chunk_size": 100,
        "batch_size": 100,
        "max_workers": 5,
        "adjustment": "forward_additive",
    }
    with pytest.raises(TickFlowTaskConflict):
        manager.start(database, stocks, api_key="other-secret")

    launcher.run_next()

    status = manager.status()
    assert status["status"] == "completed"
    assert status["running"] is False
    assert status["total_stocks"] == 2
    assert status["processed"] == 2
    assert status["succeeded"] == 2
    assert status["failed"] == 0
    assert status["report_path"]
    assert status["backup_path"]
    assert status["progress_path"]
    assert client_kwargs == [{
        "api_key": "refresh-secret",
        "batch_size": 100,
        "max_workers": 5,
    }]
    assert "api_key" not in str(status)
    assert "refresh-secret" not in str(status)
    assert calls[0] == (["600519.SH", "000001.SZ"], 1100)
    assert status["total_indexes"] == 4
    assert status["indexes_processed"] == 4
    assert status["indexes_failed"] == 0
    assert calls[-1] == (
        ["000001.SH", "399001.SZ", "399006.SZ", "000300.SH"],
        1100,
        "indexes",
    )
    assert db.get_market_index_ohlc("hs300")
    assert db.get_ohlc_metadata("600519")["source"] == "tickflow"
    backup = sqlite3.connect(status["backup_path"])
    try:
        assert backup.execute("SELECT COUNT(*) FROM daily_ohlc").fetchone()[0] == 0
    finally:
        backup.close()


def test_web_full_refresh_records_partial_failures_without_losing_success(tmp_path):
    database = tmp_path / "cuphandle.db"
    stocks = _seed_database(database)
    launcher = _ManualLauncher()
    manager = TickFlowFullRefreshManager(
        client_factory=lambda **kwargs: _Client(
            [
                BatchFetchResult(
                    frames={"600519.SH": _frame("600519")},
                    missing_symbols=["000001.SZ"],
                )
            ],
            [],
        ),
        thread_launcher=launcher,
    )

    manager.start(database, stocks)
    launcher.run_next()

    status = manager.status()
    assert status["status"] == "completed_with_errors"
    assert status["processed"] == 2
    assert status["succeeded"] == 1
    assert status["failed"] == 1
    assert status["failures"][0]["code"] == "000001"
    assert db.get_ohlc("600519")
    assert db.get_ohlc("000001") is None


def test_web_full_refresh_marks_top_level_exception_failed_and_releases_lock(tmp_path):
    database = tmp_path / "cuphandle.db"
    stocks = _seed_database(database)
    launcher = _ManualLauncher()

    def broken_factory(**kwargs):
        raise RuntimeError("sdk unavailable")

    manager = TickFlowFullRefreshManager(
        client_factory=broken_factory,
        thread_launcher=launcher,
    )

    manager.start(database, stocks)
    launcher.run_next()

    assert manager.status()["status"] == "failed"
    assert manager.status()["running"] is False
    assert "sdk unavailable" in manager.status()["error"]
    manager.start(database, stocks)

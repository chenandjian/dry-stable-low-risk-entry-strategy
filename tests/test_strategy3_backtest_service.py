"""策略3本地 DB 回测服务测试。"""
from __future__ import annotations

import json

from scanner import db
import strategy3.backtest_service as service


def _init_tmp_db(tmp_path):
    path = tmp_path / "strategy3_backtest_service.db"
    db.init_db(str(path))


def _row(date, close=10.0):
    return {
        "date": date,
        "open": close,
        "high": close * 1.02,
        "low": close * 0.98,
        "close": close,
        "volume": 1_000_000,
        "turnover": close * 1_000_000,
    }


def _create_task(task_id="s3bt-service"):
    db.create_strategy3_backtest_task(
        task_id,
        {"startDate": "2026-01-01", "endDate": "2026-01-02", "codes": ["000001"]},
        "{}",
    )
    db.save_strategy3_backtest_task_stock(task_id, "000001", name="样本", status="PENDING")


def test_strategy3_backtest_service_uses_real_cached_market_index_data(tmp_path, monkeypatch):
    _init_tmp_db(tmp_path)
    _create_task()
    db.save_ohlc("000001", [
        _row("2026-01-01", 10.0),
        _row("2026-01-02", 10.1),
        _row("2026-01-05", 10.8),
    ])
    db.save_market_index_ohlc("sz399001", [_row("2026-01-01", 100.0), _row("2026-01-02", 101.0)])
    db.save_market_index_ohlc("sh000001", [_row("2026-01-01", 200.0), _row("2026-01-02", 201.0)])
    db.save_market_index_ohlc("sz399006", [_row("2026-01-01", 300.0), _row("2026-01-02", 301.0)])
    seen = {}

    def fake_stock_backtest(
        code,
        name,
        ohlc,
        config_snapshot,
        start_date,
        end_date,
        market_data=None,
        market_data_by_symbol=None,
        market_data_mode="",
    ):
        seen["dates"] = [row["date"] for row in ohlc]
        seen["market_symbols"] = sorted((market_data_by_symbol or {}).keys())
        seen["market_dates"] = [
            row["date"] for row in (market_data_by_symbol or {}).get("sz399001", [])
        ]
        seen["market_data_mode"] = market_data_mode
        return {
            "signals": [],
            "opportunities": [],
            "eval_days": 2,
            "raw_signals_count": 0,
            "opportunities_count": 0,
            "actual_eval_start_date": start_date,
            "actual_eval_end_date": end_date,
            "observation_data_end_date": ohlc[-1]["date"],
            "available_days": len(ohlc),
            "required_days": 2,
            "earliest_date": ohlc[0]["date"],
            "latest_date": ohlc[-1]["date"],
            "insufficient": None,
        }

    monkeypatch.setattr(service, "run_strategy3_stock_backtest", fake_stock_backtest)
    monkeypatch.setattr(service, "refresh_strategy3_market_index_cache", lambda snapshot_date: {})

    service.run_strategy3_backtest_task(
        "s3bt-service",
        [{"code": "000001", "name": "样本"}],
        {"strategy3": {"minimum_required_days": 2, "strategy_window_days": 2}},
        {"startDate": "2026-01-01", "endDate": "2026-01-02"},
        "2026-01-02 16:00:00",
    )

    assert seen["dates"] == ["2026-01-01", "2026-01-02"]
    assert "sz399001" in seen["market_symbols"]
    assert seen["market_dates"] == ["2026-01-01", "2026-01-02"]
    assert seen["market_data_mode"] == "real_index_cache"
    stock = db.get_strategy3_backtest_task_stocks("s3bt-service")[0]
    assert stock["status"] == "COMPLETED"
    task = db.get_strategy3_backtest_task("s3bt-service")
    assert task["status"] == "completed"
    summary = json.loads(task["summary_json"])
    assert summary["funnel"]["evaluation_days"] == 2
    assert summary["marketDataMode"] == "real_index_cache"


def test_strategy3_backtest_service_fails_when_real_index_cache_missing(tmp_path, monkeypatch):
    _init_tmp_db(tmp_path)
    _create_task()
    db.save_ohlc("000001", [
        _row("2026-01-01", 10.0),
        _row("2026-01-02", 10.1),
    ])
    monkeypatch.setattr(service, "refresh_strategy3_market_index_cache", lambda snapshot_date: {})

    service.run_strategy3_backtest_task(
        "s3bt-service",
        [{"code": "000001", "name": "样本"}],
        {"strategy3": {"minimum_required_days": 2, "strategy_window_days": 2}},
        {"startDate": "2026-01-01", "endDate": "2026-01-02"},
        "2026-01-02 16:00:00",
    )

    task = db.get_strategy3_backtest_task("s3bt-service")
    stock = db.get_strategy3_backtest_task_stocks("s3bt-service")[0]
    assert task["status"] == "completed_with_errors"
    assert stock["status"] == "FAILED"
    assert stock["error_code"] == "RuntimeError"
    assert "MISSING_REAL_MARKET_INDEX_CACHE" in stock["error_detail"]


def test_strategy3_backtest_service_marks_missing_local_ohlc_insufficient(tmp_path):
    _init_tmp_db(tmp_path)
    _create_task()

    service.run_strategy3_backtest_task(
        "s3bt-service",
        [{"code": "000001", "name": "样本"}],
        {"strategy3": {"minimum_required_days": 180, "strategy_window_days": 250}},
        {"startDate": "2026-01-01", "endDate": "2026-01-02"},
        "2026-01-02 16:00:00",
    )

    stock = db.get_strategy3_backtest_task_stocks("s3bt-service")[0]
    assert stock["status"] == "INSUFFICIENT"
    assert stock["error_code"] == "NO_LOCAL_DATA"
    task = db.get_strategy3_backtest_task("s3bt-service")
    assert task["status"] == "completed"
    assert task["processed_stocks"] == 1

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


def test_strategy3_backtest_service_uses_local_ohlc_snapshot_only(tmp_path, monkeypatch):
    _init_tmp_db(tmp_path)
    _create_task()
    db.save_ohlc("000001", [
        _row("2026-01-01", 10.0),
        _row("2026-01-02", 10.1),
        _row("2026-01-05", 10.8),
    ])
    db.save_ohlc("000002", [
        _row("2026-01-01", 20.0),
        _row("2026-01-02", 20.4),
        _row("2026-01-05", 21.0),
    ])
    seen = {}

    def fake_stock_backtest(code, name, ohlc, config_snapshot, start_date, end_date, market_data=None):
        seen["dates"] = [row["date"] for row in ohlc]
        seen["market_dates"] = [row["date"] for row in market_data or []]
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

    service.run_strategy3_backtest_task(
        "s3bt-service",
        [{"code": "000001", "name": "样本"}],
        {"strategy3": {"minimum_required_days": 2, "strategy_window_days": 2}},
        {"startDate": "2026-01-01", "endDate": "2026-01-02"},
        "2026-01-02 16:00:00",
    )

    assert seen["dates"] == ["2026-01-01", "2026-01-02"]
    assert seen["market_dates"] == ["2026-01-02"]
    stock = db.get_strategy3_backtest_task_stocks("s3bt-service")[0]
    assert stock["status"] == "COMPLETED"
    task = db.get_strategy3_backtest_task("s3bt-service")
    assert task["status"] == "completed"
    assert json.loads(task["summary_json"])["funnel"]["evaluation_days"] == 2


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

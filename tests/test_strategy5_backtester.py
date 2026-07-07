import scanner.db as db
import pytest
from strategy5.backtester import run_strategy5_historical_performance_backtest, run_strategy5_local_backtest
from tests.test_strategy5_core_rules import _row, build_strong_data


def test_strategy5_local_backtest_reads_daily_ohlc_without_fetching(tmp_path):
    db_path = str(tmp_path / "s5bt.db")
    db.init_db(db_path)
    db.save_stock_pool([{"code": "000001", "name": "平安银行", "market": "SZ"}])
    db.save_ohlc("000001", build_strong_data())

    summary = run_strategy5_local_backtest({"data": {"database_path": db_path}}, limit=10)

    assert summary["evaluated"] == 1
    assert summary["candidates"] == 1
    assert summary["key_candidates"] + summary["watch_candidates"] == 1
    assert summary["data_source"] == "daily_ohlc"


def test_strategy5_historical_performance_calculates_returns_and_max_drawdown(tmp_path):
    db_path = str(tmp_path / "s5bt_perf.db")
    db.init_db(db_path)
    db.save_stock_pool([{"code": "000001", "name": "平安银行", "market": "SZ"}])
    data = build_strong_data(length=500)
    entry_price = data[-1]["close"]
    future_closes = [entry_price] * 20
    future_closes[4] = entry_price * 1.05
    future_closes[9] = entry_price * 0.98
    future_closes[19] = entry_price * 1.20
    for i, close in enumerate(future_closes, start=500):
        row = _row(i, close=close, high=close * 1.02, low=close * 0.99, volume=2_000_000, turnover=35)
        row["open"] = entry_price
        if i == 503:
            row["low"] = entry_price * 0.90
        data.append(row)
    db.save_ohlc("000001", data)

    summary = run_strategy5_historical_performance_backtest(
        {"data": {"database_path": db_path}},
        forward_windows=(5, 10, 20),
        evaluation_step=1,
    )

    assert summary["events"] == 1
    assert summary["historical_evaluation_points"] >= 1
    assert summary["avg_return_5d"] == pytest.approx(0.05, abs=0.0001)
    assert summary["avg_return_10d"] == pytest.approx(-0.02, abs=0.0001)
    assert summary["avg_return_20d"] == pytest.approx(0.20, abs=0.0001)
    assert summary["worst_max_drawdown"] == -0.10
    assert summary["events_detail"][0]["entry_model"] == "NEXT_OPEN"


def test_strategy5_historical_performance_reports_no_observable_forward_window(tmp_path):
    db_path = str(tmp_path / "s5bt_no_forward.db")
    db.init_db(db_path)
    db.save_stock_pool([{"code": "000001", "name": "平安银行", "market": "SZ"}])
    db.save_ohlc("000001", build_strong_data(length=500))

    summary = run_strategy5_historical_performance_backtest(
        {"data": {"database_path": db_path}},
        forward_windows=(5, 10, 20),
    )

    assert summary["events"] == 0
    assert summary["historical_evaluation_points"] == 0
    assert summary["no_observable_window_stocks"] == 1
    assert summary["limitation"] == "INSUFFICIENT_HISTORY_PLUS_FORWARD_WINDOW"

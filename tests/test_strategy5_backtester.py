import scanner.db as db
from strategy5.backtester import run_strategy5_local_backtest
from tests.test_strategy5_core_rules import build_strong_data


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

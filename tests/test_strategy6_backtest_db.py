import json

from scanner import db


EXPECTED_TABLES = {
    "strategy6_backtest_runs",
    "strategy6_backtest_parameter_sets",
    "strategy6_backtest_signals",
    "strategy6_backtest_orders",
    "strategy6_backtest_trades",
    "strategy6_backtest_metrics",
    "strategy6_backtest_walk_forward",
}


def _init(tmp_path):
    db.init_db(str(tmp_path / "strategy6-backtest.db"))
    return db.get_conn()


def test_strategy6_backtest_tables_are_created_on_old_database_init(tmp_path):
    conn = _init(tmp_path)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert EXPECTED_TABLES.issubset(tables)


def test_strategy6_backtest_run_parameter_and_signal_roundtrip_is_idempotent(tmp_path):
    conn = _init(tmp_path)
    db.save_strategy6_backtest_run({
        "run_id": "s6bt-test",
        "experiment_id": "E1_DUAL_DEFAULT",
        "strategy_version": "4.1.0",
        "strategy_git_commit": "4cff1ca",
        "strategy_config_hash": "strategy-hash",
        "backtest_config_hash": "backtest-hash",
        "data_version": "data-v1",
        "confidence_label": "RESEARCH_ONLY_CURRENT_UNIVERSE",
        "status": "RUNNING",
        "split_json": {"oos_start": "2026-01-01"},
    })
    db.save_strategy6_backtest_parameter_set("s6bt-test", {
        "parameter_set_id": "s6ps-test",
        "config_hash": "parameter-hash",
        "parameters": {"box_tail": {"enabled": True}},
        "status": "PENDING",
    })
    signals = [{
        "code": "000001",
        "name": "样本",
        "evaluation_date": "2025-06-03",
        "setup_id": "setup-1",
        "tail_path": "BOX",
        "candidate_type": "KEY_CANDIDATE",
        "snapshot": {"box_tail_pass": True, "tail_score": 18},
    }]
    db.replace_strategy6_backtest_signals("s6bt-test", "s6ps-test", "000001", signals)
    db.replace_strategy6_backtest_signals("s6bt-test", "s6ps-test", "000001", signals)

    run = db.get_strategy6_backtest_run("s6bt-test")
    loaded = db.get_strategy6_backtest_signals("s6bt-test", "s6ps-test")
    assert run["split_json"] == {"oos_start": "2026-01-01"}
    assert len(loaded) == 1
    assert loaded[0]["snapshot"]["box_tail_pass"] is True
    assert conn.execute("SELECT COUNT(*) FROM strategy6_backtest_signals").fetchone()[0] == 1


def test_strategy6_backtest_metric_query_blocks_oos_by_default(tmp_path):
    _init(tmp_path)
    db.save_strategy6_backtest_metric(
        "s6bt-test", "s6ps-test", "OOS", "portfolio", {"net_return": 0.5}
    )
    try:
        db.get_strategy6_backtest_metrics("s6bt-test", allow_oos=False)
    except PermissionError as exc:
        assert "OOS" in str(exc)
    else:
        raise AssertionError("OOS metrics must remain locked")


def test_same_business_order_and_trade_ids_can_be_saved_in_different_runs(tmp_path):
    conn = _init(tmp_path)
    order = {
        "order_id": "order-setup-1", "setup_id": "setup-1", "code": "000001",
        "signal_date": "2025-06-03", "status": "FILLED",
    }
    trade = {
        "trade_id": "trade-setup-1", "setup_id": "setup-1", "code": "000001",
        "signal_date": "2025-06-03", "entry_date": "2025-06-04",
        "exit_date": "2025-06-10", "net_return": 0.1, "r_multiple": 2.0,
    }

    for run_id in ("s6bt-a", "s6bt-b"):
        db.replace_strategy6_backtest_orders(run_id, "s6ps-same", "000001", [order])
        db.replace_strategy6_backtest_trades(run_id, "s6ps-same", "000001", [trade])

    assert conn.execute("SELECT COUNT(*) FROM strategy6_backtest_orders").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM strategy6_backtest_trades").fetchone()[0] == 2

import json

import scanner.db as db
from scanner.strategy1_backtest_models import (
    Strategy1BacktestOpportunity,
    Strategy1BacktestSignal,
)


def _init(tmp_path):
    path = str(tmp_path / "strategy1.db")
    db.init_db(path)
    return path


def _signal(code="600000", date="2025-01-02", idx=1):
    return Strategy1BacktestSignal(
        code=code,
        name="浦发银行",
        evaluation_date=date,
        evaluation_index=idx,
        pattern_kind="cup_handle",
        score=76,
        current_close=10.0,
        volume_dry_score=8,
        price_stable_score=7,
        pattern_score_20=14,
        verdict_key="BUY_LOW",
        risk_percent=5.0,
        rr1=2.0,
        stop_loss=9.2,
        evaluation_snapshot={"passed": True},
    )


def _opportunity(code="600000", first="2025-01-02"):
    return Strategy1BacktestOpportunity(
        code=code,
        name="浦发银行",
        first_detected_date=first,
        last_detected_date=first,
        pattern_kind="cup_handle",
        first_score=76,
        max_score=80,
        signal_count=1,
        entry_date="2025-01-03",
        entry_price=10.1,
        stop_loss=9.2,
        exit_date="2025-01-06",
        exit_price=10.6,
        exit_reason="TARGET",
        realized_return=0.049505,
        available_forward_days=20,
        evaluation_snapshot={"score": 76},
    )


def test_strategy1_backtest_tables_created_and_task_snapshot_roundtrip(tmp_path):
    _init(tmp_path)

    payload = {
        "startDate": "2025-01-01",
        "endDate": "2025-03-01",
        "codes": ["600000"],
        "maxStocks": 1,
        "experiment": {"enabled": True, "minimum_total_score": 75},
        "baselineTaskId": "s1bt-base",
    }
    db.create_strategy1_backtest_task("s1bt-exp", payload, '{"data":{}}')
    task = db.get_strategy1_backtest_task("s1bt-exp")

    assert task["id"] == "s1bt-exp"
    assert task["status"] == "running"
    assert task["credibility_status"] == "EXPERIMENTAL"
    assert task["requested_codes"] == "600000"
    assert json.loads(task["experiment_snapshot"])["minimum_total_score"] == 75
    assert task["baseline_task_id"] == "s1bt-base"


def test_strategy1_signal_save_is_idempotent(tmp_path):
    _init(tmp_path)
    sig = _signal()

    db.save_strategy1_backtest_signal("s1bt-1", sig)
    db.save_strategy1_backtest_signal("s1bt-1", sig)

    rows = db.get_conn().execute(
        "SELECT code, evaluation_date, score, evaluation_snapshot "
        "FROM strategy1_backtest_signals WHERE task_id='s1bt-1'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "600000"
    assert rows[0][2] == 76
    assert json.loads(rows[0][3])["passed"] is True


def test_strategy1_stock_result_replace_is_atomic_and_idempotent(tmp_path):
    _init(tmp_path)
    db.create_strategy1_backtest_task("s1bt-1", {"startDate": "", "endDate": ""}, "{}")

    result = {
        "signals": [_signal()],
        "opportunities": [_opportunity()],
        "eval_results": {1: "PASSED"},
        "raw_signals_count": 1,
        "opportunities_count": 1,
        "evaluation_days": 10,
        "actual_start_date": "2025-01-02",
        "actual_end_date": "2025-01-20",
        "available_days": 120,
        "required_days": 30,
    }

    db.replace_strategy1_stock_backtest_result("s1bt-1", "600000", "浦发银行", result)
    db.replace_strategy1_stock_backtest_result("s1bt-1", "600000", "浦发银行", result)

    conn = db.get_conn()
    assert conn.execute("SELECT COUNT(*) FROM strategy1_backtest_signals").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM strategy1_backtest_opportunities").fetchone()[0] == 1
    stock = conn.execute(
        "SELECT status, raw_signals_count, opportunities_count "
        "FROM strategy1_backtest_task_stocks WHERE task_id='s1bt-1' AND code='600000'"
    ).fetchone()
    assert stock == ("COMPLETED", 1, 1)


def test_strategy1_summary_is_built_from_database_details(tmp_path):
    _init(tmp_path)
    db.create_strategy1_backtest_task("s1bt-1", {"startDate": "", "endDate": ""}, "{}")
    db.replace_strategy1_stock_backtest_result(
        "s1bt-1",
        "600000",
        "浦发银行",
        {
            "signals": [_signal()],
            "opportunities": [_opportunity()],
            "raw_signals_count": 1,
            "opportunities_count": 1,
            "evaluation_days": 10,
        },
    )

    summary = db.build_strategy1_backtest_summary("s1bt-1")

    assert summary["total_opportunities"] == 1
    assert summary["entered_count"] == 1
    assert summary["target_count"] == 1
    assert summary["raw_signals_count"] == 1
    assert summary["by_pattern_kind"]["cup_handle"]["count"] == 1


def test_strategy1_comparison_rejects_incompatible_tasks(tmp_path):
    _init(tmp_path)
    db.create_strategy1_backtest_task(
        "base",
        {"startDate": "2025-01-01", "endDate": "2025-03-01", "maxStocks": 1},
        "{}",
    )
    db.create_strategy1_backtest_task(
        "exp",
        {"startDate": "2025-02-01", "endDate": "2025-03-01", "maxStocks": 1},
        "{}",
    )
    db.update_strategy1_backtest_task(
        "base",
        status="completed",
        credibility_status="TRUSTED_BASELINE",
        data_revision_id="rev-1",
        data_revision_version="daily-ohlc-v1",
        strategy_engine_version="cuphandle-v1",
        execution_model="NEXT_OPEN",
        summary_json=json.dumps({"total_opportunities": 1}),
    )
    db.update_strategy1_backtest_task(
        "exp",
        status="completed",
        credibility_status="EXPERIMENTAL",
        data_revision_id="rev-1",
        data_revision_version="daily-ohlc-v1",
        strategy_engine_version="cuphandle-v1",
        execution_model="NEXT_OPEN",
        summary_json=json.dumps({"total_opportunities": 2}),
    )

    comparison = db.compare_strategy1_backtest_tasks("exp", "base")

    assert comparison["comparable"] is False
    assert "DATE_RANGE_MISMATCH" in comparison["reasons"]

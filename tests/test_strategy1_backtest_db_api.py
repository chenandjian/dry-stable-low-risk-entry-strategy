import json

from fastapi.testclient import TestClient

import scanner.db as db
import server as server_mod
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


def test_strategy1_running_backtests_mark_interrupted_on_restart(tmp_path):
    _init(tmp_path)
    db.create_strategy1_backtest_task("s1bt-running", {"startDate": "", "endDate": ""}, "{}")
    db.replace_strategy1_stock_backtest_result(
        "s1bt-running",
        "600000",
        "浦发银行",
        {"status": "RUNNING", "raw_signals_count": 0, "opportunities_count": 0},
    )

    interrupted = db.mark_running_strategy1_backtests_interrupted()

    assert interrupted == ["s1bt-running"]
    task = db.get_strategy1_backtest_task("s1bt-running")
    stocks = db.get_strategy1_backtest_task_stocks("s1bt-running")
    assert task["status"] == "INTERRUPTED"
    assert task["credibility_status"] == "INCOMPLETE"
    assert stocks[0]["status"] == "PENDING"


def test_strategy1_integrity_rejects_pending_and_missing_summary(tmp_path):
    _init(tmp_path)
    db.create_strategy1_backtest_task("s1bt-bad", {"startDate": "", "endDate": ""}, "{}")
    db.replace_strategy1_stock_backtest_result("s1bt-bad", "600000", "浦发银行", {"status": "PENDING"})
    db.update_strategy1_backtest_task(
        "s1bt-bad",
        status="completed",
        total_stocks=1,
        processed_stocks=1,
        failed_stocks_count=0,
        data_revision_id="rev-1",
        data_revision_version=db.STRATEGY1_DATA_REVISION_VERSION,
        strategy_engine_version="cuphandle-v1",
        backtest_engine_version="strategy1-backtest-v1",
    )

    ok, errors = db.validate_strategy1_backtest_integrity("s1bt-bad")

    assert ok is False
    assert any("PENDING" in error for error in errors)
    assert "missing summary_json" in errors


def test_strategy1_integrity_accepts_completed_zero_opportunity_task(tmp_path):
    _init(tmp_path)
    db.create_strategy1_backtest_task("s1bt-zero", {"startDate": "", "endDate": ""}, "{}")
    db.replace_strategy1_stock_backtest_result(
        "s1bt-zero",
        "600000",
        "浦发银行",
        {"status": "INSUFFICIENT_DATA", "available_days": 10, "required_days": 250},
    )
    db.update_strategy1_backtest_task(
        "s1bt-zero",
        status="completed",
        total_stocks=1,
        processed_stocks=1,
        failed_stocks_count=0,
        data_revision_id="rev-1",
        data_revision_version=db.STRATEGY1_DATA_REVISION_VERSION,
        strategy_engine_version="cuphandle-v1",
        backtest_engine_version="strategy1-backtest-v1",
        observation_data_end_date="2026-06-12",
        summary_json=json.dumps(db.build_strategy1_backtest_summary("s1bt-zero")),
    )

    ok, errors = db.validate_strategy1_backtest_integrity("s1bt-zero")

    assert ok is True
    assert errors == []


def test_strategy1_experiment_preview_endpoint_normalizes_payload(monkeypatch, tmp_path):
    db_path = str(tmp_path / "preview.db")
    monkeypatch.setattr(server_mod, "load_config", lambda path="config.yaml": {"data": {"database_path": db_path}})

    response = TestClient(server_mod.app).post(
        "/api/strategy1/backtests/experiments/preview",
        json={"enabled": True, "minimumTotalScore": 75, "timeExitDays": 5},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["credibilityStatus"] == "EXPERIMENTAL"
    assert body["normalizedExperiment"]["minimum_total_score"] == 75


def test_strategy1_start_backtest_saves_snapshot_and_launches(monkeypatch, tmp_path):
    db_path = str(tmp_path / "start-api.db")
    db.init_db(db_path)
    db.save_stock_pool([{"code": "600000", "name": "浦发银行", "market": "SH"}])
    db.save_ohlc("600000", [{"date": "2025-01-01", "open": 10, "high": 10, "low": 10, "close": 10, "volume": 1, "turnover": 10}])
    config = {"data": {"database_path": db_path, "scan_window_days": 30, "backtest_window_days": 30}, "liquidity": {"min_listing_days": 30}}
    launched = {}
    monkeypatch.setattr(server_mod, "load_config", lambda path="config.yaml": config)
    monkeypatch.setattr(server_mod, "_launch_strategy1_backtest_task", lambda **kwargs: launched.update(kwargs))
    server_mod._backtest_running.update({"running": False, "task_id": None, "stats": {}, "cancel_event": None, "thread": None})
    server_mod._running.update({"running": False, "task_id": None, "strategy_type": None, "stats": {}})

    response = TestClient(server_mod.app).post(
        "/api/strategy1/backtests",
        json={
            "startDate": "2025-01-01",
            "endDate": "2025-03-31",
            "codes": ["600000"],
            "baselineTaskId": "baseline-1",
            "experiment": {"enabled": True, "minimumTotalScore": 75},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["credibilityStatus"] == "EXPERIMENTAL"
    assert body["status"] == "running"
    task = db.get_strategy1_backtest_task(body["task_id"])
    snapshot = json.loads(task["experiment_snapshot"])
    assert snapshot["minimum_total_score"] == 75
    assert task["baseline_task_id"] == "baseline-1"
    assert launched["target_stocks"] == [{"code": "600000", "name": "浦发银行"}]
    assert launched["payload_snapshot"]["experiment"]["minimum_total_score"] == 75


def test_strategy1_detail_opportunity_signal_and_comparison_endpoints(monkeypatch, tmp_path):
    db_path = str(tmp_path / "query-api.db")
    db.init_db(db_path)
    monkeypatch.setattr(server_mod, "load_config", lambda path="config.yaml": {"data": {"database_path": db_path}})
    for task_id, credibility in [("base", "TRUSTED_BASELINE"), ("exp", "EXPERIMENTAL")]:
        db.create_strategy1_backtest_task(
            task_id,
            {"startDate": "2025-01-01", "endDate": "2025-03-01", "codes": ["600000"], "maxStocks": 1},
            "{}",
        )
        db.update_strategy1_backtest_task(
            task_id,
            status="completed",
            credibility_status=credibility,
            data_revision_id="rev-1",
            data_revision_version=db.STRATEGY1_DATA_REVISION_VERSION,
            strategy_engine_version="cuphandle-v1",
            execution_model="NEXT_OPEN",
            summary_json=json.dumps({"total_opportunities": 1, "entered_count": 1}),
        )
        db.replace_strategy1_stock_backtest_result(
            task_id,
            "600000",
            "浦发银行",
            {"signals": [_signal()], "opportunities": [_opportunity()], "raw_signals_count": 1, "opportunities_count": 1},
        )

    client = TestClient(server_mod.app)
    detail = client.get("/api/strategy1/backtests/exp")
    opps = client.get("/api/strategy1/backtests/exp/opportunities")
    signals = client.get("/api/strategy1/backtests/exp/signals")
    comparison = client.get("/api/strategy1/backtests/exp/comparison?baselineTaskId=base")

    assert detail.status_code == 200
    assert detail.json()["task"]["id"] == "exp"
    assert opps.status_code == 200
    assert opps.json()["total"] == 1
    assert signals.status_code == 200
    assert signals.json()["signals"][0]["code"] == "600000"
    assert comparison.status_code == 200
    assert comparison.json()["comparable"] is True

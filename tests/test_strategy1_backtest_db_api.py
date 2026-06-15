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


def _signal(code="600000", date="2025-01-02", idx=1, score=76):
    return Strategy1BacktestSignal(
        code=code,
        name="浦发银行",
        evaluation_date=date,
        evaluation_index=idx,
        pattern_kind="cup_handle",
        score=score,
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


def test_strategy1_opportunity_quality_fields_roundtrip_and_summary(tmp_path):
    _init(tmp_path)
    db.create_strategy1_backtest_task("s1bt-quality", {"startDate": "", "endDate": ""}, "{}")
    opp = _opportunity()
    opp.price_stable_score = 7
    opp.volume_dry_score = 8
    opp.verdict_key = "WATCH_BREAKOUT"
    opp.quality_tags = ["PRICE_STABLE_STRONG", "BREAKOUT_OBSERVE"]
    opp.quality_layer = "strong"

    db.replace_strategy1_stock_backtest_result(
        "s1bt-quality",
        "600000",
        "浦发银行",
        {
            "signals": [_signal()],
            "opportunities": [opp],
            "raw_signals_count": 1,
            "opportunities_count": 1,
        },
    )

    stored = db.get_strategy1_backtest_opportunities("s1bt-quality")[0]
    summary = db.build_strategy1_backtest_summary("s1bt-quality")

    assert stored["price_stable_score"] == 7
    assert stored["volume_dry_score"] == 8
    assert stored["verdict_key"] == "WATCH_BREAKOUT"
    assert stored["quality_tags"] == ["PRICE_STABLE_STRONG", "BREAKOUT_OBSERVE"]
    assert stored["quality_layer"] == "strong"
    assert summary["by_quality_tag"]["PRICE_STABLE_STRONG"]["count"] == 1
    assert summary["by_quality_tag"]["BREAKOUT_OBSERVE"]["count"] == 1


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


def test_strategy1_service_uses_backtest_window_for_required_days(tmp_path):
    from scanner.strategy1_backtest_service import run_strategy1_backtest_task

    _init(tmp_path)
    rows = [
        {"date": f"2025-01-{i + 1:02d}", "open": 10, "high": 10, "low": 10, "close": 10, "volume": 1, "turnover": 10}
        for i in range(40)
    ]
    db.save_stock_pool([{"code": "600000", "name": "浦发银行", "market": "SH"}])
    db.save_ohlc("600000", rows)
    task_id = "s1bt-min-listing"
    config = {
        "data": {"scan_window_days": 30, "backtest_window_days": 30},
        "liquidity": {"min_listing_days": 50},
    }
    payload = {"startDate": "2025-01-01", "endDate": "2025-02-09", "experiment": {"enabled": False}}
    db.create_strategy1_backtest_task(task_id, payload, json.dumps(config))
    db.replace_strategy1_stock_backtest_result(task_id, "600000", "浦发银行", {"status": "PENDING"})
    db.update_strategy1_backtest_task(task_id, total_stocks=1, data_revision_id="rev-1", data_revision_version=db.STRATEGY1_DATA_REVISION_VERSION, strategy_engine_version="cuphandle-v1", backtest_engine_version="strategy1-backtest-v1")

    run_strategy1_backtest_task(task_id=task_id, target_stocks=[{"code": "600000", "name": "浦发银行"}], config_snapshot=config, payload_snapshot=payload)

    stock = db.get_strategy1_backtest_task_stocks(task_id)[0]
    assert stock["status"] == "COMPLETED"
    assert stock["required_days"] == 30
    assert stock["available_days"] == 40


def test_strategy1_service_marks_insufficient_when_below_backtest_window(tmp_path):
    from scanner.strategy1_backtest_service import run_strategy1_backtest_task

    _init(tmp_path)
    rows = [
        {"date": f"2025-01-{i + 1:02d}", "open": 10, "high": 10, "low": 10, "close": 10, "volume": 1, "turnover": 10}
        for i in range(25)
    ]
    db.save_stock_pool([{"code": "600000", "name": "浦发银行", "market": "SH"}])
    db.save_ohlc("600000", rows)
    task_id = "s1bt-backtest-window"
    config = {
        "data": {"scan_window_days": 30, "backtest_window_days": 30},
        "liquidity": {"min_listing_days": 50},
    }
    payload = {"startDate": "2025-01-01", "endDate": "2025-01-25", "experiment": {"enabled": False}}
    db.create_strategy1_backtest_task(task_id, payload, json.dumps(config))
    db.replace_strategy1_stock_backtest_result(task_id, "600000", "浦发银行", {"status": "PENDING"})
    db.update_strategy1_backtest_task(task_id, total_stocks=1, data_revision_id="rev-1", data_revision_version=db.STRATEGY1_DATA_REVISION_VERSION, strategy_engine_version="cuphandle-v1", backtest_engine_version="strategy1-backtest-v1")

    run_strategy1_backtest_task(task_id=task_id, target_stocks=[{"code": "600000", "name": "浦发银行"}], config_snapshot=config, payload_snapshot=payload)

    stock = db.get_strategy1_backtest_task_stocks(task_id)[0]
    assert stock["status"] == "INSUFFICIENT_DATA"
    assert stock["required_days"] == 30
    assert stock["available_days"] == 25


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
    assert task["baseline_task_id"] is None
    assert launched["target_stocks"] == [{"code": "600000", "name": "浦发银行"}]
    assert launched["payload_snapshot"]["experiment"]["minimum_total_score"] == 75


def test_strategy1_start_experiment_with_baseline_derives_without_launcher(monkeypatch, tmp_path):
    db_path = str(tmp_path / "derive-api.db")
    db.init_db(db_path)
    db.save_stock_pool([{"code": "600000", "name": "浦发银行", "market": "SH"}])
    db.save_ohlc("600000", [{"date": "2025-01-01", "open": 10, "high": 10, "low": 10, "close": 10, "volume": 1, "turnover": 10}])
    config = {"data": {"database_path": db_path, "scan_window_days": 30, "backtest_window_days": 30}, "liquidity": {"min_listing_days": 30}}
    db.create_strategy1_backtest_task("baseline-1", {"startDate": "2025-01-01", "endDate": "2025-03-31", "codes": ["600000"], "maxStocks": 1}, json.dumps(config))
    db.update_strategy1_backtest_task("baseline-1", status="completed", credibility_status="TRUSTED_BASELINE")
    derived = {}
    monkeypatch.setattr(server_mod, "load_config", lambda path="config.yaml": config)
    monkeypatch.setattr(server_mod, "_launch_strategy1_backtest_task", lambda **kwargs: (_ for _ in ()).throw(AssertionError("launcher should not run")))
    monkeypatch.setattr(server_mod, "run_strategy1_experiment_from_baseline", lambda **kwargs: derived.update(kwargs), raising=False)
    server_mod._backtest_running.update({"running": False, "task_id": None, "stats": {}, "cancel_event": None, "thread": None})
    server_mod._running.update({"running": False, "task_id": None, "strategy_type": None, "stats": {}})

    response = TestClient(server_mod.app).post(
        "/api/strategy1/backtests",
        json={
            "startDate": "2025-01-01",
            "endDate": "2025-03-31",
            "codes": ["600000"],
            "baselineTaskId": "baseline-1",
            "experiment": {"enabled": True, "minimumTotalScore": 80},
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert derived["baseline_task_id"] == "baseline-1"
    assert derived["experiment_snapshot"]["minimum_total_score"] == 80


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


def test_strategy1_experiment_can_be_derived_from_trusted_baseline(tmp_path):
    from scanner.strategy1_backtest_experiments import normalize_experiment_config
    from scanner.strategy1_backtest_service import (
        STRATEGY1_BACKTEST_ENGINE_VERSION,
        STRATEGY1_STRATEGY_ENGINE_VERSION,
        run_strategy1_experiment_from_baseline,
    )

    _init(tmp_path)
    rows = []
    for i in range(40):
        rows.append({
            "date": f"2025-01-{i + 1:02d}" if i < 31 else f"2025-02-{i - 30:02d}",
            "open": 10 + i * 0.1,
            "high": 10.5 + i * 0.1,
            "low": 9.5 + i * 0.1,
            "close": 10.1 + i * 0.1,
            "volume": 1_000_000,
            "turnover": 10_000_000,
        })
    db.save_stock_pool([{"code": "600000", "name": "浦发银行", "market": "SH"}])
    db.save_ohlc("600000", rows)
    baseline_id = "s1bt-baseline"
    experiment_id = "s1bt-experiment"
    config_snapshot = {"data": {"scan_window_days": 30, "backtest_window_days": 30}, "liquidity": {"min_listing_days": 30}}
    db.create_strategy1_backtest_task(
        baseline_id,
        {"startDate": "2025-01-01", "endDate": "2025-02-09", "codes": ["600000"], "maxStocks": 1},
        json.dumps(config_snapshot),
    )
    baseline_signal = _signal(date="2025-01-20", idx=19, score=76)
    baseline_opp = _opportunity(first="2025-01-20")
    baseline_opp.last_detected_date = "2025-01-20"
    db.replace_strategy1_stock_backtest_result(
        baseline_id,
        "600000",
        "浦发银行",
        {
            "signals": [baseline_signal],
            "opportunities": [baseline_opp],
            "raw_signals_count": 1,
            "opportunities_count": 1,
            "evaluation_days": 40,
            "available_days": 40,
            "required_days": 30,
            "latest_date": "2025-02-09",
        },
    )
    summary = db.build_strategy1_backtest_summary(baseline_id)
    db.update_strategy1_backtest_task(
        baseline_id,
        status="completed",
        credibility_status="TRUSTED_BASELINE",
        requested_start_date="2025-01-01",
        requested_end_date="2025-02-09",
        requested_codes="600000",
        max_stocks=1,
        total_stocks=1,
        processed_stocks=1,
        failed_stocks_count=0,
        raw_signals_count=1,
        opportunities_count=1,
        observation_data_end_date="2025-02-09",
        summary_json=json.dumps(summary),
        data_revision_id="rev-1",
        data_revision_version=db.STRATEGY1_DATA_REVISION_VERSION,
        strategy_engine_version=STRATEGY1_STRATEGY_ENGINE_VERSION,
        backtest_engine_version=STRATEGY1_BACKTEST_ENGINE_VERSION,
        execution_model="NEXT_OPEN",
    )
    experiment = normalize_experiment_config({"enabled": True, "minimumTotalScore": 80})

    run_strategy1_experiment_from_baseline(
        experiment_task_id=experiment_id,
        baseline_task_id=baseline_id,
        experiment_snapshot=experiment,
    )

    task = db.get_strategy1_backtest_task(experiment_id)
    signals = db.get_strategy1_backtest_signals(experiment_id)
    comparison = db.compare_strategy1_backtest_tasks(experiment_id, baseline_id)
    assert task["credibility_status"] == "EXPERIMENTAL"
    assert task["baseline_task_id"] == baseline_id
    assert task["raw_signals_count"] == 1
    assert task["opportunities_count"] == 0
    assert signals[0]["experiment_passed"] == 0
    assert signals[0]["experiment_filter_reason"] == "MIN_TOTAL_SCORE"
    assert comparison["comparable"] is True
    assert comparison["delta"]["opportunities"] == -1

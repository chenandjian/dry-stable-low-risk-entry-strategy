"""Strategy2 Phase 2 DB and API contract tests."""

import json

from fastapi.testclient import TestClient

import scanner.db as db
import server as server_mod
from strategy2.backtest_models import BacktestSignal
from strategy2.version import (
    STRATEGY2_BACKTEST_ENGINE_VERSION,
    STRATEGY2_STRATEGY_ENGINE_VERSION,
)


def _versions():
    return {
        "backtest_engine_version": STRATEGY2_BACKTEST_ENGINE_VERSION,
        "strategy_engine_version": STRATEGY2_STRATEGY_ENGINE_VERSION,
    }


def test_phase2_migration_adds_experiment_columns(tmp_path):
    db.init_db(str(tmp_path / "phase2-columns.db"))
    conn = db.get_conn()

    task_cols = {row[1] for row in conn.execute("PRAGMA table_info(strategy2_backtest_tasks)")}
    signal_cols = {row[1] for row in conn.execute("PRAGMA table_info(strategy2_backtest_signals)")}
    opp_cols = {row[1] for row in conn.execute("PRAGMA table_info(strategy2_backtest_opportunities)")}

    assert {"experiment_snapshot", "baseline_task_id", "comparison_summary_json"}.issubset(task_cols)
    assert {"baseline_passed", "experiment_passed", "experiment_filter_reason", "opportunity_type"}.issubset(signal_cols)
    assert {"opportunity_type", "entry_confirmation_type", "entry_confirmation_status", "time_exit_days", "market_context_json"}.issubset(opp_cols)


def test_replace_result_persists_filtered_signal_and_experiment_opportunity_fields(tmp_path):
    db.init_db(str(tmp_path / "phase2-persist.db"))
    experiment = {"enabled": True, "minimum_volume_dry_score": 40}
    db.create_strategy2_backtest_task(
        "exp-task",
        {"startDate": "2025-01-01", "endDate": "2025-03-31", "experiment": experiment},
        "{}",
    )
    db.save_strategy2_backtest_task_stock("exp-task", "000001", name="test", status="PENDING")
    sig = BacktestSignal(
        code="000001",
        name="test",
        evaluation_date="2025-03-01",
        evaluation_index=1,
        score=72,
        level="观察",
        current_close=10,
        stop_loss=9.5,
        risk_ratio=0.03,
        volume_dry_score=35,
        price_stable_score=35,
        trend_type="UPTREND_OR_SIDEWAYS",
        trend_evidence_score=4,
        evaluation_snapshot={},
        experiment_passed=False,
        experiment_filter_reason="MIN_VOLUME_DRY_SCORE",
        opportunity_type="CONTINUATION",
    )
    result = {
        "signals": [sig],
        "opportunities": [{
            "code": "000001",
            "name": "test",
            "first_detected_date": "2025-03-02",
            "last_detected_date": "2025-03-02",
            "consecutive_hit_days": 1,
            "first_score": 80,
            "max_score": 80,
            "entry_close": 10,
            "stop_loss": 9.5,
            "risk_ratio": 0.03,
            "signal_count": 1,
            "execution_model": "NEXT_OPEN",
            "entry_date": "2025-03-03",
            "entry_price": 10.1,
            "exit_date": "2025-03-07",
            "exit_price": 10.3,
            "exit_reason": "TIME_EXIT",
            "realized_return": 0.0198,
            "holding_days": 5,
            "available_forward_days": 10,
            "opportunity_type": "CONTINUATION",
            "entry_confirmation_type": "BREAK_RECENT_5D_HIGH",
            "entry_confirmation_date": "2025-03-02",
            "entry_confirmation_price": 10.2,
            "entry_confirmation_status": "ENTRY_CONFIRMED",
            "time_exit_days": 5,
            "market_context_json": json.dumps({"market_return_5d": 0.01}),
        }],
        "eval_days": 2,
        "raw_signals_count": 1,
        "opportunities_count": 1,
        "experiment_filtered_days": 1,
        "experiment_volume_filtered_days": 1,
        "experiment_score_filtered_days": 0,
        "entry_confirmation_failed_count": 0,
        "time_exit_count": 1,
    }

    db.replace_strategy2_stock_backtest_result("exp-task", "000001", "test", result)

    signal = db.get_conn().execute(
        "SELECT experiment_passed,experiment_filter_reason,opportunity_type FROM strategy2_backtest_signals WHERE task_id='exp-task'"
    ).fetchone()
    opportunity = db.get_strategy2_backtest_opportunities("exp-task")[0]
    stock = db.get_strategy2_backtest_task_stocks("exp-task")[0]

    assert signal == (0, "MIN_VOLUME_DRY_SCORE", "CONTINUATION")
    assert opportunity["entry_confirmation_type"] == "BREAK_RECENT_5D_HIGH"
    assert opportunity["exit_reason"] == "TIME_EXIT"
    assert opportunity["time_exit_days"] == 5
    assert stock["experiment_filtered_days"] == 1
    assert stock["time_exit_count"] == 1


def test_experimental_task_finalizes_as_experimental_not_trusted(tmp_path):
    from strategy2.backtest_service import _finalize_task

    db.init_db(str(tmp_path / "phase2-finalize.db"))
    db.create_strategy2_backtest_task(
        "exp-final",
        {"startDate": "2025-01-01", "endDate": "2025-03-31", "experiment": {"enabled": True}},
        "{}",
    )
    db.save_strategy2_backtest_task_stock(
        "exp-final",
        "000001",
        status="COMPLETED",
        observation_data_end_date="2025-03-31",
    )
    db.update_strategy2_backtest_task(
        "exp-final",
        total_stocks=1,
        processed_stocks=1,
        data_snapshot_date="2025-03-31 09:00:00",
        data_revision_id="revision",
        data_revision_version=db.STRATEGY2_DATA_REVISION_VERSION,
        observation_data_end_date="2025-03-31",
        failed_stocks_count=0,
        evaluation_error_days=0,
        **_versions(),
    )

    class Cancel:
        def is_set(self):
            return False

    _finalize_task("exp-final", Cancel(), 1.0)

    task = db.get_strategy2_backtest_task("exp-final")
    assert task["status"] == "completed"
    assert task["credibility_status"] == "EXPERIMENTAL"


def test_finalize_rolls_up_experiment_funnel_counts(tmp_path):
    from strategy2.backtest_service import _finalize_task

    db.init_db(str(tmp_path / "phase2-funnel.db"))
    db.create_strategy2_backtest_task(
        "exp-funnel",
        {"startDate": "2025-01-01", "endDate": "2025-03-31", "experiment": {"enabled": True}},
        "{}",
    )
    db.save_strategy2_backtest_task_stock(
        "exp-funnel",
        "000001",
        status="COMPLETED",
        observation_data_end_date="2025-03-31",
        experiment_filtered_days=3,
        experiment_volume_filtered_days=2,
        experiment_score_filtered_days=1,
        entry_confirmation_failed_count=4,
        time_exit_count=5,
    )
    db.update_strategy2_backtest_task(
        "exp-funnel",
        total_stocks=1,
        processed_stocks=1,
        data_snapshot_date="2025-03-31 09:00:00",
        data_revision_id="revision",
        data_revision_version=db.STRATEGY2_DATA_REVISION_VERSION,
        observation_data_end_date="2025-03-31",
        failed_stocks_count=0,
        evaluation_error_days=0,
        **_versions(),
    )

    class Cancel:
        def is_set(self):
            return False

    _finalize_task("exp-funnel", Cancel(), 1.0)

    task = db.get_strategy2_backtest_task("exp-funnel")
    summary = json.loads(task["summary_json"])
    assert task["experiment_filtered_days"] == 3
    assert task["entry_confirmation_failed_count"] == 4
    assert task["time_exit_count"] == 5
    assert summary["experiment_funnel"]["time_exit_count"] == 5


def test_summary_includes_experiment_group_statistics(tmp_path):
    db.init_db(str(tmp_path / "phase2-groups.db"))
    db.create_strategy2_backtest_task("group-task", {}, "{}")
    db.save_strategy2_backtest_opportunity("group-task", {
        "code": "000001",
        "first_detected_date": "2025-03-02",
        "last_detected_date": "2025-03-02",
        "consecutive_hit_days": 1,
        "first_score": 72,
        "max_score": 80,
        "entry_close": 10,
        "stop_loss": 9.5,
        "entry_price": 10,
        "exit_reason": "TARGET",
        "realized_return": 0.05,
        "volume_dry_score": 45,
        "price_stable_score": 35,
        "opportunity_type": "CONTINUATION",
        "entry_confirmation_status": "ENTRY_CONFIRMED",
    })
    db.save_strategy2_backtest_opportunity("group-task", {
        "code": "000002",
        "first_detected_date": "2025-04-02",
        "last_detected_date": "2025-04-02",
        "consecutive_hit_days": 1,
        "first_score": 58,
        "max_score": 58,
        "entry_close": 10,
        "stop_loss": 9.5,
        "entry_price": 10,
        "exit_reason": "STOP",
        "realized_return": -0.03,
        "volume_dry_score": 25,
        "price_stable_score": 20,
        "opportunity_type": "REVERSAL",
        "entry_confirmation_status": "NO_ENTRY_CONFIRMATION",
    })

    summary = db.build_strategy2_backtest_summary("group-task")

    groups = summary["groups"]
    assert groups["by_month"]["2025-03"]["opportunities"] == 1
    assert groups["by_month"]["2025-04"]["stop"] == 1
    assert groups["by_opportunity_type"]["CONTINUATION"]["target"] == 1
    assert groups["by_opportunity_type"]["REVERSAL"]["stop"] == 1
    assert groups["by_volume_dry_score_band"]["40-49"]["opportunities"] == 1
    assert groups["by_volume_dry_score_band"]["20-29"]["opportunities"] == 1
    assert groups["by_price_stable_score_band"]["30-39"]["opportunities"] == 1
    assert groups["by_total_score_band"]["70-79"]["average_realized_return"] == 0.05
    assert groups["by_entry_confirmation_status"]["NO_ENTRY_CONFIRMATION"]["stop"] == 1


def test_experiment_preview_endpoint_normalizes_payload(monkeypatch, tmp_path):
    db_path = str(tmp_path / "preview.db")
    config = {"data": {"database_path": db_path}}
    monkeypatch.setattr(server_mod, "load_config", lambda path="config.yaml": config)

    response = TestClient(server_mod.app).post(
        "/api/strategy2/backtests/experiments/preview",
        json={"enabled": True, "minimumVolumeDryScore": 40, "timeExitDays": 5},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["normalizedExperiment"]["minimum_volume_dry_score"] == 40
    assert body["credibilityStatus"] == "EXPERIMENTAL"


def test_start_backtest_saves_experiment_snapshot_and_baseline_id(monkeypatch, tmp_path):
    db_path = str(tmp_path / "start-api.db")
    db.init_db(db_path)
    db.save_ohlc("000001", [{"date": "2025-01-01", "open": 10, "high": 10, "low": 10, "close": 10, "volume": 1, "turnover": 10}])
    config = {"data": {"database_path": db_path}, "strategy2": {"minimum_required_days": 60}}
    launched = {}
    monkeypatch.setattr(server_mod, "load_config", lambda path="config.yaml": config)
    monkeypatch.setattr(server_mod, "_launch_strategy2_backtest_task", lambda **kwargs: launched.update(kwargs))
    server_mod._backtest_running.update({"running": False, "task_id": None, "stats": {}, "cancel_event": None, "thread": None})
    server_mod._running.update({"running": False, "task_id": None, "strategy_type": None, "stats": {}})

    response = TestClient(server_mod.app).post(
        "/api/strategy2/backtests",
        json={
            "startDate": "2025-01-01",
            "endDate": "2025-03-31",
            "codes": ["000001"],
            "baselineTaskId": "baseline-1",
            "experiment": {"enabled": True, "minimumVolumeDryScore": 40},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["credibilityStatus"] == "EXPERIMENTAL"
    task = db.get_strategy2_backtest_task(body["task_id"])
    snapshot = json.loads(task["experiment_snapshot"])
    assert snapshot["enabled"] is True
    assert snapshot["minimum_volume_dry_score"] == 40
    assert task["baseline_task_id"] == "baseline-1"
    assert launched["payload_snapshot"]["experiment"]["minimum_volume_dry_score"] == 40


def _create_comparison_task(task_id, *, credibility, start="2025-01-01", end="2025-03-31", codes="000001"):
    db.create_strategy2_backtest_task(
        task_id,
        {"startDate": start, "endDate": end, "codes": codes.split(","), "maxStocks": None},
        "{}",
    )
    db.update_strategy2_backtest_task(
        task_id,
        status="completed",
        credibility_status=credibility,
        requested_codes=codes,
        max_stocks=None,
        total_stocks=1,
        processed_stocks=1,
        failed_stocks_count=0,
        evaluation_error_days=0,
        observation_data_end_date=end,
        execution_model="NEXT_OPEN",
        data_revision_version=db.STRATEGY2_DATA_REVISION_VERSION,
        data_revision_id="same-revision",
        summary_json=json.dumps({"horizon_stats": {"3": {}, "5": {}, "10": {}, "20": {}}}),
        **_versions(),
    )
    db.save_strategy2_backtest_task_stock(
        task_id,
        codes.split(",")[0],
        status="COMPLETED",
        observation_data_end_date=end,
    )


def test_comparison_endpoint_reports_comparable_and_delta(monkeypatch, tmp_path):
    db_path = str(tmp_path / "comparison.db")
    db.init_db(db_path)
    config = {"data": {"database_path": db_path}}
    monkeypatch.setattr(server_mod, "load_config", lambda path="config.yaml": config)
    _create_comparison_task("baseline", credibility="TRUSTED_BASELINE")
    _create_comparison_task("experiment", credibility="EXPERIMENTAL")
    db.save_strategy2_backtest_opportunity("baseline", {
        "code": "000001", "first_detected_date": "2025-02-01", "last_detected_date": "2025-02-01",
        "consecutive_hit_days": 1, "first_score": 72, "max_score": 72,
        "entry_close": 10, "stop_loss": 9.5, "entry_price": 10,
        "exit_reason": "TARGET", "realized_return": 0.05,
    })
    db.save_strategy2_backtest_opportunity("experiment", {
        "code": "000001", "first_detected_date": "2025-02-01", "last_detected_date": "2025-02-01",
        "consecutive_hit_days": 1, "first_score": 80, "max_score": 80,
        "entry_close": 10, "stop_loss": 9.5, "entry_price": 10,
        "exit_reason": "TIME_EXIT", "realized_return": 0.03,
    })

    response = TestClient(server_mod.app).get(
        "/api/strategy2/backtests/experiment/comparison?baselineTaskId=baseline"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["comparable"] is True
    assert body["baseline"]["opportunities"] == 1
    assert body["experiment"]["opportunities"] == 1
    assert body["delta"]["averageRealizedReturn"] == -0.02


def test_comparison_endpoint_reports_incompatible_versions(monkeypatch, tmp_path):
    db_path = str(tmp_path / "comparison-bad.db")
    db.init_db(db_path)
    config = {"data": {"database_path": db_path}}
    monkeypatch.setattr(server_mod, "load_config", lambda path="config.yaml": config)
    _create_comparison_task("baseline", credibility="TRUSTED_BASELINE")
    _create_comparison_task("experiment", credibility="EXPERIMENTAL")
    db.update_strategy2_backtest_task("experiment", data_revision_id="different")

    response = TestClient(server_mod.app).get(
        "/api/strategy2/backtests/experiment/comparison?baselineTaskId=baseline"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["comparable"] is False
    assert "data_revision_id" in body["reasons"]

"""策略2 Phase 1 中高级问题修复的行为级测试。"""
import json
import threading

import scanner.db as db
import server as server_mod
from fastapi.testclient import TestClient
from strategy2.version import (
    STRATEGY2_BACKTEST_ENGINE_VERSION,
    STRATEGY2_STRATEGY_ENGINE_VERSION,
)


def _current_engine_versions():
    return {
        "backtest_engine_version": STRATEGY2_BACKTEST_ENGINE_VERSION,
        "strategy_engine_version": STRATEGY2_STRATEGY_ENGINE_VERSION,
    }


def _create_finished_task(tmp_path, task_id: str, status: str = "completed"):
    db.init_db(str(tmp_path / f"{task_id}.db"))
    db.create_strategy2_backtest_task(
        task_id,
        {"startDate": "2025-01-01", "endDate": "2025-06-01", "maxStocks": 1},
        "{}",
    )
    db.save_strategy2_backtest_task_stock(
        task_id,
        "000001",
        name="test",
        status="COMPLETED",
        raw_signals_count=0,
        opportunities_count=0,
    )
    db.update_strategy2_backtest_task(
        task_id,
        status=status,
        total_stocks=1,
        processed_stocks=1,
        observation_data_end_date="2025-06-01",
        failed_stocks_count=0,
        evaluation_error_days=0,
        data_revision_id="revision",
        data_revision_version=db.STRATEGY2_DATA_REVISION_VERSION,
        **_current_engine_versions(),
    )


def test_integrity_rejects_canceled_task_even_when_all_stocks_terminal(tmp_path):
    _create_finished_task(tmp_path, "canceled", status="CANCELED")
    summary = db.build_strategy2_backtest_summary("canceled")
    db.update_strategy2_backtest_task("canceled", summary_json=json.dumps(summary))

    ok, errors = db.validate_strategy2_backtest_integrity("canceled")

    assert ok is False
    assert any("task status" in error for error in errors)


def test_complete_zero_opportunity_task_has_full_summary_and_is_trusted(tmp_path):
    _create_finished_task(tmp_path, "zero-opps")
    summary = db.build_strategy2_backtest_summary("zero-opps")
    db.update_strategy2_backtest_task("zero-opps", summary_json=json.dumps(summary))

    ok, errors = db.validate_strategy2_backtest_integrity("zero-opps")

    assert set(summary["horizon_stats"]) == {"3", "5", "10", "20"}
    assert summary["execution_stats"]["opportunities"] == 0
    assert summary["funnel"]["opportunities_count"] == 0
    assert ok is True, errors


def test_summary_aggregates_funnel_and_horizon_trigger_days(tmp_path):
    _create_finished_task(tmp_path, "summary")
    db.save_strategy2_backtest_task_stock(
        "summary",
        "000001",
        status="COMPLETED",
        evaluation_days=20,
        liquidity_filtered_days=2,
        trend_filtered_days=3,
        rejection_failed_days=4,
        score_failed_days=5,
        risk_failed_days=1,
        invalid_data_days=2,
        evaluation_error_days=0,
        raw_signals_count=2,
        opportunities_count=1,
    )
    horizon = {
        "horizon_days": 3,
        "result": "SUCCESS",
        "end_return": 0.03,
        "max_upside": 0.06,
        "max_drawdown": -0.01,
        "days_to_target": 2,
        "days_to_stop": None,
    }
    db.save_strategy2_backtest_opportunity(
        "summary",
        {
            "code": "000001",
            "first_detected_date": "2025-01-10",
            "last_detected_date": "2025-01-11",
            "consecutive_hit_days": 2,
            "first_score": 80,
            "max_score": 85,
            "entry_close": 10.0,
            "stop_loss": 9.5,
            "entry_price": 10.1,
            "exit_reason": "TARGET",
            "realized_return": 0.05,
            "holding_days": 2,
            "horizon_3": json.dumps(horizon),
            "horizon_5": json.dumps({**horizon, "horizon_days": 5, "result": "FAILED", "days_to_target": None, "days_to_stop": 4}),
            "horizon_10": json.dumps({**horizon, "horizon_days": 10}),
            "horizon_20": json.dumps({**horizon, "horizon_days": 20}),
        },
    )

    summary = db.build_strategy2_backtest_summary("summary")

    assert summary["funnel"] == {
        "evaluation_days": 20,
        "liquidity_filtered_days": 2,
        "trend_filtered_days": 3,
        "rejection_failed_days": 4,
        "score_failed_days": 5,
        "risk_failed_days": 1,
        "invalid_data_days": 2,
        "evaluation_error_days": 0,
        "raw_signals_count": 2,
        "opportunities_count": 1,
    }
    assert summary["horizon_stats"]["3"]["avg_days_to_target"] == 2
    assert summary["horizon_stats"]["5"]["avg_days_to_stop"] == 4


def test_daily_ohlc_revision_changes_when_same_day_content_changes(tmp_path):
    from strategy2.backtest_service import calculate_daily_ohlc_revision

    db.init_db(str(tmp_path / "revision.db"))
    db.save_ohlc("000001", [
        {"date": "2025-01-02", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100, "turnover": 1000},
    ])
    first = calculate_daily_ohlc_revision("2025-01-02", ["000001"])

    db.save_ohlc("000001", [
        {"date": "2025-01-02", "open": 10, "high": 12, "low": 9, "close": 10, "volume": 100, "turnover": 1000},
    ])
    second = calculate_daily_ohlc_revision("2025-01-02", ["000001"])

    assert first != second


def test_task_daily_ohlc_revision_changes_when_turnover_changes(tmp_path):
    from strategy2.backtest_service import calculate_task_daily_ohlc_revision

    db.init_db(str(tmp_path / "turnover-revision.db"))
    db.create_strategy2_backtest_task("turnover-task", {}, "{}")
    db.save_strategy2_backtest_task_stock("turnover-task", "000001", status="PENDING")
    db.save_ohlc("000001", [
        {"date": "2025-01-02", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100, "turnover": 1000},
    ])
    first = calculate_task_daily_ohlc_revision("turnover-task", "2025-01-02")

    db.save_ohlc("000001", [
        {"date": "2025-01-02", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100, "turnover": 200_000_000},
    ])
    second = calculate_task_daily_ohlc_revision("turnover-task", "2025-01-02")

    assert first != second


def test_task_daily_ohlc_revision_filters_stock_scope_in_sql(tmp_path):
    from strategy2.backtest_service import calculate_task_daily_ohlc_revision

    db.init_db(str(tmp_path / "scoped-revision.db"))
    db.create_strategy2_backtest_task("single-stock", {}, "{}")
    db.save_strategy2_backtest_task_stock("single-stock", "000001", status="PENDING")
    db.save_ohlc("000001", [
        {"date": "2025-01-02", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100, "turnover": 1000},
    ])
    db.save_ohlc("999999", [
        {"date": "2025-01-02", "open": 20, "high": 21, "low": 19, "close": 20, "volume": 200, "turnover": 4000},
    ])
    statements = []
    db.get_conn().set_trace_callback(statements.append)

    calculate_task_daily_ohlc_revision("single-stock", "2025-01-02")

    revision_queries = [statement for statement in statements if "FROM daily_ohlc" in statement]
    assert len(revision_queries) == 1
    assert "JOIN strategy2_backtest_task_stocks" in revision_queries[0]
    assert "single-stock" in revision_queries[0]


def test_init_db_downgrades_historical_untrusted_baselines(tmp_path):
    db_path = str(tmp_path / "legacy-trusted.db")
    db.init_db(db_path)
    for task_id, status, revision, summary in [
        ("failed-trusted", "failed", "rev", "{}"),
        ("running-trusted", "running", "rev", "{}"),
        ("revisionless-trusted", "completed", None, "{}"),
        ("summaryless-trusted", "completed", "rev", None),
        ("legacy-revision-trusted", "completed", "old-algorithm-revision", "{}"),
    ]:
        db.create_strategy2_backtest_task(task_id, {}, "{}")
        db.update_strategy2_backtest_task(
            task_id,
            status=status,
            credibility_status="TRUSTED_BASELINE",
            data_revision_id=revision,
            summary_json=summary,
        )

    db.init_db(db_path)

    for task_id in (
        "failed-trusted", "running-trusted", "revisionless-trusted",
        "summaryless-trusted", "legacy-revision-trusted",
    ):
        assert db.get_strategy2_backtest_task(task_id)["credibility_status"] == "LEGACY_UNTRUSTED"


def test_init_db_preserves_current_valid_trusted_baseline(tmp_path):
    db_path = str(tmp_path / "valid-trusted.db")
    db.init_db(db_path)
    db.create_strategy2_backtest_task("valid-trusted", {}, "{}")
    db.save_strategy2_backtest_task_stock("valid-trusted", "000001", status="COMPLETED")
    db.update_strategy2_backtest_task(
        "valid-trusted",
        status="completed",
        credibility_status="TRUSTED_BASELINE",
        data_revision_id="revision",
        data_revision_version=db.STRATEGY2_DATA_REVISION_VERSION,
        **_current_engine_versions(),
        summary_json="{}",
        total_stocks=1,
        processed_stocks=1,
        failed_stocks_count=0,
        evaluation_error_days=0,
    )

    db.init_db(db_path)

    assert db.get_strategy2_backtest_task("valid-trusted")["credibility_status"] == "TRUSTED_BASELINE"


def test_no_local_data_path_records_audit_and_live_progress(tmp_path):
    from strategy2.backtest_service import (
        calculate_daily_ohlc_revision,
        run_strategy2_backtest_task,
    )

    db.init_db(str(tmp_path / "no-data.db"))
    task_id = "no-data"
    config = {"strategy2": {"minimum_required_days": 60}}
    payload = {"startDate": "2025-01-01", "endDate": "2025-06-01"}
    db.create_strategy2_backtest_task(task_id, payload, json.dumps(config))
    db.save_strategy2_backtest_task_stock(task_id, "000001", name="test", status="PENDING")
    revision = calculate_daily_ohlc_revision("2025-06-01", ["000001"])
    db.update_strategy2_backtest_task(
        task_id,
        data_snapshot_date="2025-06-01 09:00:00",
        data_revision_id=revision,
        data_revision_version=db.STRATEGY2_DATA_REVISION_VERSION,
        **_current_engine_versions(),
    )
    running_state = {
        "running": True,
        "task_id": task_id,
        "stats": {"processed_stocks": 0, "insufficient_stocks_count": 0, "opportunities_count": 0},
        "cancel_event": threading.Event(),
    }

    run_strategy2_backtest_task(
        task_id=task_id,
        target_stocks=[{"code": "000001", "name": "test"}],
        config_snapshot=config,
        payload_snapshot=payload,
        data_snapshot_date="2025-06-01 09:00:00",
        cancel_event=running_state["cancel_event"],
        running_state=running_state,
        mode="start",
    )

    stock = db.get_strategy2_backtest_task_stocks(task_id)[0]
    assert stock["status"] == "INSUFFICIENT"
    assert stock["started_at"]
    assert stock["finished_at"]
    assert running_state["stats"]["processed_stocks"] == 1


def _prepare_api_task(tmp_path, task_id: str, status: str, stock_statuses: dict[str, str]):
    from strategy2.backtest_service import calculate_daily_ohlc_revision

    db_path = str(tmp_path / f"{task_id}.db")
    db.init_db(db_path)
    config = {"data": {"database_path": db_path}, "strategy2": {"minimum_required_days": 60}}
    payload = {"startDate": "2025-01-01", "endDate": "2025-06-01", "maxStocks": None}
    db.create_strategy2_backtest_task(task_id, payload, json.dumps(config))
    for code, stock_status in stock_statuses.items():
        db.save_strategy2_backtest_task_stock(task_id, code, name=code, status=stock_status)
    revision = calculate_daily_ohlc_revision("2025-06-01", list(stock_statuses))
    db.update_strategy2_backtest_task(
        task_id,
        status=status,
        data_snapshot_date="2025-06-01 09:00:00",
        data_revision_id=revision,
        data_revision_version=db.STRATEGY2_DATA_REVISION_VERSION,
        **_current_engine_versions(),
    )
    server_mod._backtest_running.update({
        "running": False, "task_id": None, "stats": {}, "cancel_event": None, "thread": None,
    })
    return config


def test_resume_launches_only_unfinished_stocks(monkeypatch, tmp_path):
    config = _prepare_api_task(
        tmp_path,
        "resume-task",
        "INTERRUPTED",
        {"000001": "COMPLETED", "000002": "PENDING", "000003": "RUNNING"},
    )
    launched = {}
    monkeypatch.setattr(server_mod, "load_config", lambda path="config.yaml": config)
    monkeypatch.setattr(
        server_mod,
        "_launch_strategy2_backtest_task",
        lambda **kwargs: launched.update(kwargs),
    )

    response = TestClient(server_mod.app).post("/api/strategy2/backtests/resume-task/resume")

    assert response.status_code == 200
    assert {stock["code"] for stock in launched["target_stocks"]} == {"000002", "000003"}


def test_retry_failed_launches_only_failed_stocks(monkeypatch, tmp_path):
    config = _prepare_api_task(
        tmp_path,
        "retry-task",
        "completed_with_errors",
        {"000001": "COMPLETED", "000002": "FAILED", "000003": "INSUFFICIENT"},
    )
    launched = {}
    monkeypatch.setattr(server_mod, "load_config", lambda path="config.yaml": config)
    monkeypatch.setattr(
        server_mod,
        "_launch_strategy2_backtest_task",
        lambda **kwargs: launched.update(kwargs),
    )

    response = TestClient(server_mod.app).post("/api/strategy2/backtests/retry-task/retry-failed")

    assert response.status_code == 200
    assert [stock["code"] for stock in launched["target_stocks"]] == ["000002"]


def test_resume_rejects_changed_data_revision(monkeypatch, tmp_path):
    config = _prepare_api_task(
        tmp_path,
        "changed-revision",
        "INTERRUPTED",
        {"000001": "PENDING"},
    )
    db.save_ohlc("000001", [
        {"date": "2025-01-02", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100, "turnover": 1000},
    ])
    monkeypatch.setattr(server_mod, "load_config", lambda path="config.yaml": config)

    response = TestClient(server_mod.app).post("/api/strategy2/backtests/changed-revision/resume")

    assert response.status_code == 409
    assert response.json()["error"] == "DATA_REVISION_CHANGED"
    assert db.get_strategy2_backtest_task("changed-revision")["status"] == "DATA_REVISION_CHANGED"


def test_retry_failed_rejects_turnover_revision_change(monkeypatch, tmp_path):
    from strategy2.backtest_service import calculate_task_daily_ohlc_revision

    db_path = str(tmp_path / "retry-turnover.db")
    db.init_db(db_path)
    config = {"data": {"database_path": db_path}, "strategy2": {"minimum_required_days": 60}}
    db.save_ohlc("000001", [
        {"date": "2025-01-02", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100, "turnover": 1000},
    ])
    db.create_strategy2_backtest_task("retry-turnover", {}, json.dumps(config))
    db.save_strategy2_backtest_task_stock("retry-turnover", "000001", status="FAILED")
    revision = calculate_task_daily_ohlc_revision("retry-turnover", "2025-06-01")
    db.update_strategy2_backtest_task(
        "retry-turnover",
        status="completed_with_errors",
        data_snapshot_date="2025-06-01 09:00:00",
        data_revision_id=revision,
        data_revision_version=db.STRATEGY2_DATA_REVISION_VERSION,
        **_current_engine_versions(),
    )
    db.save_ohlc("000001", [
        {"date": "2025-01-02", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100, "turnover": 200_000_000},
    ])
    server_mod._backtest_running.update({
        "running": False, "task_id": None, "stats": {}, "cancel_event": None, "thread": None,
    })
    monkeypatch.setattr(server_mod, "load_config", lambda path="config.yaml": config)

    response = TestClient(server_mod.app).post("/api/strategy2/backtests/retry-turnover/retry-failed")

    assert response.status_code == 409
    assert response.json()["error"] == "DATA_REVISION_CHANGED"


def test_cancelled_executor_leaves_pending_stocks_and_is_not_trusted(tmp_path):
    from strategy2.backtest_service import calculate_daily_ohlc_revision, run_strategy2_backtest_task

    db.init_db(str(tmp_path / "cancel.db"))
    task_id = "cancel"
    config = {"strategy2": {"minimum_required_days": 60}}
    payload = {"startDate": "2025-01-01", "endDate": "2025-06-01"}
    db.create_strategy2_backtest_task(task_id, payload, json.dumps(config))
    db.save_strategy2_backtest_task_stock(task_id, "000001", name="test", status="PENDING")
    revision = calculate_daily_ohlc_revision("2025-06-01", ["000001"])
    db.update_strategy2_backtest_task(
        task_id,
        data_snapshot_date="2025-06-01 09:00:00",
        data_revision_id=revision,
        data_revision_version=db.STRATEGY2_DATA_REVISION_VERSION,
        **_current_engine_versions(),
    )
    cancel_event = threading.Event()
    cancel_event.set()
    running_state = {"running": True, "task_id": task_id, "stats": {}, "cancel_event": cancel_event}

    run_strategy2_backtest_task(
        task_id, [{"code": "000001", "name": "test"}], config, payload,
        "2025-06-01 09:00:00", cancel_event, running_state, "start",
    )

    task = db.get_strategy2_backtest_task(task_id)
    stock = db.get_strategy2_backtest_task_stocks(task_id)[0]
    assert task["status"] == "CANCELED"
    assert task["credibility_status"] == "PHASE1_INCOMPLETE"
    assert stock["status"] == "PENDING"


def test_same_data_revision_tasks_have_identical_signal_and_opportunity_sets(monkeypatch, tmp_path):
    from strategy2.backtest_models import BacktestSignal
    from strategy2 import backtest_service

    db.init_db(str(tmp_path / "reproducible.db"))
    db.save_ohlc("000001", [
        {"date": "2025-01-02", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100, "turnover": 1000},
    ])
    config = {"strategy2": {"minimum_required_days": 1}}
    payload = {"startDate": "2025-01-01", "endDate": "2025-06-01"}
    revision = backtest_service.calculate_daily_ohlc_revision("2025-06-01", ["000001"])

    signal = BacktestSignal(
        code="000001", name="test", evaluation_date="2025-01-02",
        evaluation_index=0, score=80, current_close=10.0, stop_loss=9.5,
        risk_ratio=0.05, evaluation_snapshot={},
    )
    result = {
        "signals": [signal],
        "opportunities": [{
            "code": "000001", "first_detected_date": "2025-01-02",
            "last_detected_date": "2025-01-02", "consecutive_hit_days": 1,
            "first_score": 80, "max_score": 80, "entry_close": 10.0,
            "stop_loss": 9.5, "signal_count": 1, "execution_model": "NEXT_OPEN",
        }],
        "eval_days": 1, "raw_signals_count": 1, "opportunities_count": 1,
        "invalid_data_days": 2,
        "actual_eval_start_date": "2025-01-02",
        "actual_eval_end_date": "2025-01-02",
        "observation_data_end_date": "2025-01-02",
        "available_days": 1, "required_days": 1,
        "earliest_date": "2025-01-02", "latest_date": "2025-01-02",
        "insufficient": None,
    }
    monkeypatch.setattr(backtest_service, "run_strategy2_stock_backtest", lambda *args, **kwargs: result)

    for task_id in ("same-a", "same-b"):
        db.create_strategy2_backtest_task(task_id, payload, json.dumps(config))
        db.save_strategy2_backtest_task_stock(task_id, "000001", name="test", status="PENDING")
        db.update_strategy2_backtest_task(
            task_id,
            data_snapshot_date="2025-06-01 09:00:00",
            data_revision_id=revision,
            data_revision_version=db.STRATEGY2_DATA_REVISION_VERSION,
            **_current_engine_versions(),
        )
        cancel_event = threading.Event()
        state = {"running": True, "task_id": task_id, "stats": {}, "cancel_event": cancel_event}
        backtest_service.run_strategy2_backtest_task(
            task_id, [{"code": "000001", "name": "test"}], config, payload,
            "2025-06-01 09:00:00", cancel_event, state, "start",
        )

    conn = db.get_conn()
    signal_sets = [
        set(conn.execute(
            "SELECT code,evaluation_date,score FROM strategy2_backtest_signals WHERE task_id=?",
            (task_id,),
        ).fetchall())
        for task_id in ("same-a", "same-b")
    ]
    opportunity_sets = [
        set(conn.execute(
            "SELECT code,first_detected_date,max_score FROM strategy2_backtest_opportunities WHERE task_id=?",
            (task_id,),
        ).fetchall())
        for task_id in ("same-a", "same-b")
    ]
    stock = db.get_strategy2_backtest_task_stocks("same-a")[0]

    assert signal_sets[0] ^ signal_sets[1] == set()
    assert opportunity_sets[0] ^ opportunity_sets[1] == set()
    assert stock["started_at"] and stock["finished_at"]
    assert stock["invalid_data_days"] == 2
    assert stock["earliest_date"] == "2025-01-02"
    assert stock["latest_date"] == "2025-01-02"


def test_startup_marks_running_backtest_interrupted_and_preserves_completed_results(monkeypatch, tmp_path):
    db_path = str(tmp_path / "startup-recovery.db")
    db.init_db(db_path)
    db.create_strategy2_backtest_task("restart-task", {}, "{}")
    db.save_strategy2_backtest_task_stock("restart-task", "000001", status="RUNNING")
    db.save_strategy2_backtest_task_stock("restart-task", "000002", status="COMPLETED")
    db.get_conn().execute(
        "INSERT INTO strategy2_backtest_signals "
        "(task_id,code,name,evaluation_date,evaluation_index,score,level,current_close,"
        "stop_loss,risk_ratio,volume_dry_score,price_stable_score,trend_type,"
        "trend_evidence_score,evaluation_snapshot) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("restart-task", "000002", "", "2025-01-02", 1, 80, "", 10, 9, 0.1, 4, 4, "", 0, "{}"),
    )
    db.get_conn().commit()
    monkeypatch.setattr(
        server_mod,
        "load_config",
        lambda path="config.yaml": {"data": {"database_path": db_path}, "scheduler": {"enabled": False}},
    )

    with TestClient(server_mod.app):
        task = db.get_strategy2_backtest_task("restart-task")
        stocks = {row["code"]: row for row in db.get_strategy2_backtest_task_stocks("restart-task")}

    assert task["status"] == "INTERRUPTED"
    assert task["credibility_status"] == "PHASE1_INCOMPLETE"
    assert stocks["000001"]["status"] == "PENDING"
    assert stocks["000002"]["status"] == "COMPLETED"
    assert db.get_conn().execute(
        "SELECT COUNT(*) FROM strategy2_backtest_signals WHERE task_id='restart-task'"
    ).fetchone()[0] == 1


def test_resume_rejects_old_engine_revision_without_changing_results(monkeypatch, tmp_path):
    config = _prepare_api_task(
        tmp_path, "old-engine", "INTERRUPTED", {"000001": "PENDING", "000002": "COMPLETED"},
    )
    db.update_strategy2_backtest_task("old-engine", strategy_engine_version="strategy2-old")
    db.get_conn().execute(
        "INSERT INTO strategy2_backtest_signals "
        "(task_id,code,name,evaluation_date,evaluation_index,score,level,current_close,"
        "stop_loss,risk_ratio,volume_dry_score,price_stable_score,trend_type,"
        "trend_evidence_score,evaluation_snapshot) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("old-engine", "000002", "", "2025-01-02", 1, 80, "", 10, 9, 0.1, 4, 4, "", 0, "{}"),
    )
    db.get_conn().commit()
    monkeypatch.setattr(server_mod, "load_config", lambda path="config.yaml": config)

    response = TestClient(server_mod.app).post("/api/strategy2/backtests/old-engine/resume")

    assert response.status_code == 409
    assert response.json()["error"] == "ENGINE_REVISION_CHANGED"
    assert db.get_strategy2_backtest_task("old-engine")["status"] == "ENGINE_REVISION_CHANGED"
    assert db.get_conn().execute(
        "SELECT COUNT(*) FROM strategy2_backtest_signals WHERE task_id='old-engine'"
    ).fetchone()[0] == 1


def test_retry_failed_rejects_old_backtest_engine_revision(monkeypatch, tmp_path):
    config = _prepare_api_task(
        tmp_path, "old-backtester", "completed_with_errors", {"000001": "FAILED"},
    )
    db.update_strategy2_backtest_task("old-backtester", backtest_engine_version="phase1-old")
    monkeypatch.setattr(server_mod, "load_config", lambda path="config.yaml": config)

    response = TestClient(server_mod.app).post(
        "/api/strategy2/backtests/old-backtester/retry-failed"
    )

    assert response.status_code == 409
    assert response.json()["error"] == "ENGINE_REVISION_CHANGED"
    assert db.get_strategy2_backtest_task("old-backtester")["status"] == "ENGINE_REVISION_CHANGED"


def test_integrity_rejects_missing_strategy_engine_version(tmp_path):
    _create_finished_task(tmp_path, "missing-engine")
    summary = db.build_strategy2_backtest_summary("missing-engine")
    db.update_strategy2_backtest_task(
        "missing-engine", strategy_engine_version=None, summary_json=json.dumps(summary),
    )

    ok, errors = db.validate_strategy2_backtest_integrity("missing-engine")

    assert ok is False
    assert any("strategy_engine_version" in error for error in errors)


def test_backtest_task_list_is_paginated_filtered_and_omits_large_fields(tmp_path):
    db.init_db(str(tmp_path / "task-pages.db"))
    for index, status in enumerate(("completed", "failed", "completed"), start=1):
        db.create_strategy2_backtest_task(f"task-{index}", {}, f'{{"index": {index}}}')
        db.update_strategy2_backtest_task(f"task-{index}", status=status, summary_json='{"large": true}')

    response = TestClient(server_mod.app).get(
        "/api/strategy2/backtests?page=1&page_size=1&status=completed"
    )

    body = response.json()
    assert response.status_code == 200
    assert body["total"] == 2
    assert len(body["tasks"]) == 1
    assert "config_snapshot" not in body["tasks"][0]
    assert "summary_json" not in body["tasks"][0]

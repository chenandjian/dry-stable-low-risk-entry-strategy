from fastapi.testclient import TestClient
import zipfile
from io import BytesIO
import pytest

import scanner.db as db
import server as server_mod
from strategy6 import STRATEGY6_TYPE


def _candidate():
    return {
        "code": "000001",
        "name": "平安银行",
        "sector_name": "银行",
        "evaluation_date": "2026-07-09",
        "candidate_type": "KEY_CANDIDATE",
        "classification": "highlight",
        "lifecycle_status": "BUY_ZONE",
        "first_pool_date": "2026-07-01",
        "pool_age_trading_days": 6,
        "current_price": 12.34,
        # Strategy6 currently uses forward-adjusted prices only. Even if a
        # caller supplies an alleged raw price, it must not be persisted.
        "current_price_raw": 999.99,
        "total_score": 82,
        "start_type": "NORMAL_STRONG_BREAKOUT",
        "start_grade": "A",
        "current_close_position": 0.72,
        "start_low": 11.5,
        "days_since_start": 5,
        "support_status": "MA20_SUPPORT",
        "key_support_price": 12.0,
        "prior_key_support_price": 11.8,
        "support_zone_low": 11.64,
        "support_zone_high": 12.48,
        "suggested_buy_price": 12.34,
        "stop_loss_price": 11.4,
        "target_price_1": 13.75,
        "target_price_2": 14.69,
        "target_price_3": 15.63,
        "risk_reward_ratio_2": 2.5,
        "risk_tags": [],
        "warn_tags": ["PRESSURE_NEAR_HIGH"],
        "reject_reasons": [],
        "score_reasons": ["strong=17"],
        "start_day_self_amount_percentile": 0.95,
        "strategy_version": "4.0.0",
        "config_hash": "abc123",
        "phase_status": "PHASE_VALID",
        "consolidation_start_date": "2026-06-20",
        "tail_start_date": "2026-07-03",
        "signal_date": "2026-07-09",
        "pattern_type": "VCP",
        "pattern_score": 18,
        "pivot_source": "VCP_LAST_CONTRACTION",
        "tactical_support_price": 12.1,
        "support_cluster_sources": ["MA10", "PATTERN_LOW"],
        "objective_target_1": 13.4,
        "objective_target_2": 14.8,
        "execution_target_1_5r": 13.75,
        "execution_target_2r": 14.22,
        "objective_rr_1": 1.7,
        "objective_rr_2": 2.6,
        "valid_from_date": "2026-07-10",
        "valid_until_date": "2026-07-14",
        "suggested_limit_price": 12.34,
        "execution_notes": ["NEXT_TRADING_DAY_ONLY", "T1_STOP_UNAVAILABLE_ON_BUY_DAY"],
        "pattern_score_component": 18,
        "tail_score": 19,
        "objective_rr_score": 8,
        "relative_strength_risk_score": 9,
        "tail_avg_volume": 500000,
        "pre_tail_avg_volume_20": 1000000,
        "tail_volume_ratio": 0.5,
    }


def test_strategy6_candidate_table_is_independent(tmp_path):
    db.init_db(str(tmp_path / "s6.db"))
    db.create_scan_task("s6-task", "2026-07-09 10:00:00", strategy_type=STRATEGY6_TYPE)

    db.upsert_strategy6_candidate("s6-task", _candidate())

    rows = db.get_strategy6_candidates("s6-task")
    detail = db.get_strategy6_candidate("000001", task_id="s6-task")
    assert rows[0]["code"] == "000001"
    assert rows[0]["candidate_type"] == "KEY_CANDIDATE"
    assert rows[0]["days_since_start"] == 5
    assert rows[0]["start_low"] == 11.5
    assert rows[0]["prior_key_support_price"] == 11.8
    assert rows[0]["first_pool_date"] == "2026-07-01"
    assert rows[0]["pool_age_trading_days"] == 6
    assert rows[0]["warn_tags"] == ["PRESSURE_NEAR_HIGH"]
    assert detail["risk_reward_ratio_2"] == 2.5
    assert detail["strategy_version"] == "4.0.0"
    assert detail["pattern_type"] == "VCP"
    assert detail["support_cluster_sources"] == ["MA10", "PATTERN_LOW"]
    assert detail["objective_rr_2"] == 2.6
    assert detail["execution_notes"] == ["NEXT_TRADING_DAY_ONLY", "T1_STOP_UNAVAILABLE_ON_BUY_DAY"]
    assert detail["price_basis"] == "FORWARD_ADJUSTED"
    assert detail["current_price_adj"] == 12.34
    assert detail["current_price_raw"] is None
    assert detail["start_day_self_amount_percentile"] == 0.95
    assert db.get_candidates(task_id="s6-task") == []
    assert db.get_strategy2_candidates(task_id="s6-task") == []
    assert db.get_strategy3_candidates(task_id="s6-task") == []
    assert db.get_strategy4_candidates("s6-task") == []
    assert db.get_strategy5_candidates("s6-task") == []


def test_strategy6_legacy_sector_columns_are_not_returned_by_new_api_rows(tmp_path):
    db.init_db(str(tmp_path / "s6-legacy.db"))
    conn = db.get_conn()
    for name, col_type in (
        ("enable_sector_filter", "INTEGER DEFAULT 0"),
        ("sector_filter_mode", "TEXT"),
        ("sector_strength_status", "TEXT"),
        ("relative_strength_10_sector", "REAL DEFAULT 0"),
        ("sector_member_new_high_count", "INTEGER DEFAULT 0"),
    ):
        conn.execute(f"ALTER TABLE strategy6_candidates ADD COLUMN {name} {col_type}")
    conn.commit()
    db.create_scan_task("s6-legacy", "2026-07-09 10:00:00", strategy_type=STRATEGY6_TYPE)
    db.upsert_strategy6_candidate("s6-legacy", _candidate())

    row = db.get_strategy6_candidates("s6-legacy")[0]

    assert "sector_name" in row
    assert "enable_sector_filter" not in row
    assert "sector_filter_mode" not in row
    assert "sector_strength_status" not in row
    assert "relative_strength_10_sector" not in row
    assert "sector_member_new_high_count" not in row


def test_strategy6_api_returns_candidates_and_rejects_cross_strategy(tmp_path, monkeypatch):
    db_path = str(tmp_path / "s6api.db")
    db.init_db(db_path)
    monkeypatch.setattr(server_mod, "load_config", lambda path="config.yaml": {"data": {"database_path": db_path}, "strategy6": {}})
    server_mod._running.update({"running": False, "task_id": None, "strategy_type": None, "stats": {}})

    db.create_scan_task("s1-task", "2026-07-09 10:00:00", strategy_type="STRATEGY_1_CUP_HANDLE")
    db.create_scan_task("s6-task", "2026-07-09 10:05:00", strategy_type=STRATEGY6_TYPE)
    db.upsert_strategy6_candidate("s6-task", _candidate())

    client = TestClient(server_mod.app)
    assert client.get("/api/strategy6/tasks").json()["tasks"][0]["id"] == "s6-task"
    assert client.get("/api/strategy6/tasks/s6-task/candidates").json()["candidates"][0]["code"] == "000001"
    assert client.get("/api/strategy6/tasks/s6-task/candidates/000001").json()["candidate"]["candidate_type"] == "KEY_CANDIDATE"

    mismatch = client.get("/api/strategy6/tasks/s1-task/candidates")
    assert mismatch.status_code == 400
    assert mismatch.json()["error"] == "TASK_STRATEGY_MISMATCH"


def test_strategy6_api_returns_market_snapshot_for_task(tmp_path, monkeypatch):
    db_path = str(tmp_path / "s6marketapi.db")
    db.init_db(db_path)
    monkeypatch.setattr(server_mod, "load_config", lambda path="config.yaml": {"data": {"database_path": db_path}, "strategy6": {}})
    server_mod._running.update({"running": False, "task_id": None, "strategy_type": None, "stats": {}})

    db.create_scan_task("s1-task", "2026-07-09 09:55:00", strategy_type="STRATEGY_1_CUP_HANDLE")
    db.create_scan_task("s6-task", "2026-07-09 10:00:00", strategy_type=STRATEGY6_TYPE)
    db.save_strategy6_market_snapshot(
        "s6-task",
        {
            "market_status": "MARKET_STRONG",
            "market_reasons": ["above_ma20=2", "ma20_above_ma50=1"],
            "market_return_20": 0.04,
            "indexes": [
                {
                    "symbol": "sh000001",
                    "name": "上证指数",
                    "latest_date": "2026-07-09",
                    "latest_close": 3200.5,
                    "ma20": 3150.2,
                    "ma50": 3100.1,
                    "return_20": 0.035,
                    "above_ma20": True,
                    "ma20_above_ma50": True,
                    "volume_down_risk": False,
                    "rows_count": 80,
                    "source": "sina",
                    "data_status": "FRESH",
                }
            ],
        },
    )

    client = TestClient(server_mod.app)
    response = client.get("/api/strategy6/tasks/s6-task/market-snapshot")
    assert response.status_code == 200
    body = response.json()
    assert body["taskId"] == "s6-task"
    assert body["snapshot"]["market_status"] == "MARKET_STRONG"
    assert body["snapshot"]["indexes"][0]["symbol"] == "sh000001"
    assert body["snapshot"]["indexes"][0]["latest_close"] == 3200.5
    assert body["snapshot"]["indexes"][0]["data_status"] == "FRESH"

    mismatch = client.get("/api/strategy6/tasks/s1-task/market-snapshot")
    assert mismatch.status_code == 400
    assert mismatch.json()["error"] == "TASK_STRATEGY_MISMATCH"


def test_strategy6_api_exports_excel_report(tmp_path, monkeypatch):
    db_path = str(tmp_path / "s6report.db")
    db.init_db(db_path)
    monkeypatch.setattr(server_mod, "load_config", lambda path="config.yaml": {"data": {"database_path": db_path}, "strategy6": {}})
    server_mod._running.update({"running": False, "task_id": None, "strategy_type": None, "stats": {}})

    candidate = _candidate()
    candidate.update({
        "enable_market_filter": True,
        "market_filter_mode": "downgrade",
        "market_status": "MARKET_STRONG",
        "relative_strength_20": 0.18,
    })
    db.create_scan_task("s6-report", "2026-07-09 10:05:00", strategy_type=STRATEGY6_TYPE)
    db.upsert_strategy6_candidate("s6-report", candidate)

    response = TestClient(server_mod.app).get("/api/strategy6/tasks/s6-report/report.xlsx")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "strategy6-report-s6-report.xlsx" in response.headers["content-disposition"]
    workbook = zipfile.ZipFile(BytesIO(response.content))
    sheet = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
    shared = workbook.read("xl/sharedStrings.xml").decode("utf-8")
    assert "stock_code" in shared
    assert "enable_market_filter" in shared
    assert "enable_sector_filter" not in shared
    assert "relative_strength_10_sector" not in shared
    assert "sector_member_new_high_count" not in shared
    assert "days_since_start" in shared
    assert "start_low" in shared
    assert "prior_key_support_price" in shared
    assert "000001" in shared
    assert "MARKET_STRONG" in shared
    assert "<v>0.18</v>" in sheet


def test_strategy6_candidate_persists_explicit_lifecycle_state(tmp_path):
    db.init_db(str(tmp_path / "s6lifecycle.db"))
    current = _candidate()
    current["evaluation_date"] = "2026-07-22"
    current.update({
        "lifecycle_status": "EXPIRED",
        "first_seen_date": "2026-07-01",
        "last_seen_date": "2026-07-22",
        "days_in_pool": 15,
        "exit_date": "2026-07-22",
        "exit_reason": "MAX_WATCH_DAYS_REACHED",
        "cooldown_until_date": "2026-07-29",
        "reentry_count": 0,
    })
    db.create_scan_task("s6-new", "2026-07-22 10:00:00", strategy_type=STRATEGY6_TYPE)
    db.upsert_strategy6_candidate("s6-new", current)

    saved = db.get_strategy6_candidate("000001", task_id="s6-new")
    assert saved["first_pool_date"] == "2026-07-01"
    assert saved["pool_age_trading_days"] == 15
    assert saved["days_in_pool"] == 15
    assert saved["lifecycle_status"] == "EXPIRED"
    assert saved["exit_reason"] == "MAX_WATCH_DAYS_REACHED"
    assert saved["cooldown_until_date"] == "2026-07-29"


def test_strategy6_lifecycle_audit_api_returns_exited_rows_without_candidates(tmp_path, monkeypatch):
    db_path = str(tmp_path / "s6-lifecycle-audit.db")
    db.init_db(db_path)
    monkeypatch.setattr(server_mod, "load_config", lambda path="config.yaml": {"data": {"database_path": db_path}, "strategy6": {}})
    db.create_scan_task("s6-audit", "2026-07-22 10:00:00", strategy_type=STRATEGY6_TYPE)
    db.create_scan_task("s1-audit", "2026-07-22 09:00:00", strategy_type="STRATEGY_1_CUP_HANDLE")
    db.save_strategy6_task_lifecycle(
        "s6-audit",
        code="000001",
        name="平安银行",
        evaluation_date="2026-07-22",
        candidate_type="REJECTED",
        lifecycle={
            "lifecycle_status": "FAILED",
            "first_seen_date": "2026-07-01",
            "last_seen_date": "2026-07-22",
            "days_in_pool": 10,
            "exit_date": "2026-07-22",
            "exit_reason": "SUPPORT_FAILED",
            "cooldown_until_date": "2026-08-05",
            "reentry_count": 0,
            "blocked": True,
        },
        reject_reasons=["SUPPORT_FAILED"],
    )

    response = TestClient(server_mod.app).get("/api/strategy6/tasks/s6-audit/lifecycle")

    assert response.status_code == 200
    rows = response.json()["lifecycle"]
    assert len(rows) == 1
    assert rows[0]["code"] == "000001"
    assert rows[0]["lifecycle_status"] == "FAILED"
    assert rows[0]["cooldown_until_date"] == "2026-08-05"
    assert rows[0]["reject_reasons"] == ["SUPPORT_FAILED"]
    assert db.get_strategy6_candidates("s6-audit") == []
    mismatch = TestClient(server_mod.app).get("/api/strategy6/tasks/s1-audit/lifecycle")
    assert mismatch.status_code == 400
    assert mismatch.json()["error"] == "TASK_STRATEGY_MISMATCH"


def test_strategy6_atomic_persist_rolls_back_lifecycle_when_candidate_write_fails(tmp_path, monkeypatch):
    db.init_db(str(tmp_path / "s6-atomic.db"))
    db.create_scan_task("s6-atomic", "2026-07-09 10:00:00", strategy_type=STRATEGY6_TYPE)

    def fail_candidate_write(*args, **kwargs):
        raise RuntimeError("candidate write failed")

    monkeypatch.setattr(db, "upsert_strategy6_candidate", fail_candidate_write)
    with pytest.raises(RuntimeError, match="candidate write failed"):
        db.persist_strategy6_evaluation(
            "s6-atomic",
            code="000001",
            name="平安银行",
            evaluation_date="2026-07-09",
            candidate_type="KEY_CANDIDATE",
            lifecycle_status="READY",
            event_key="stable-event",
            reject_reasons=[],
            max_watch_days=10,
            expired_cooldown_days=5,
            failed_cooldown_days=10,
            candidate=_candidate(),
        )

    assert db.get_strategy6_lifecycle("000001") is None
    assert db.get_strategy6_task_lifecycle("s6-atomic") == []
    assert db.get_strategy6_candidates("s6-atomic") == []


def test_strategy6_atomic_persist_rolls_back_when_task_audit_write_fails(tmp_path, monkeypatch):
    db.init_db(str(tmp_path / "s6-atomic-audit.db"))
    db.create_scan_task("s6-atomic-audit", "2026-07-09 10:00:00", strategy_type=STRATEGY6_TYPE)

    monkeypatch.setattr(
        db,
        "save_strategy6_task_lifecycle",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("audit write failed")),
    )
    with pytest.raises(RuntimeError, match="audit write failed"):
        db.persist_strategy6_evaluation(
            "s6-atomic-audit",
            code="000001", name="平安银行", evaluation_date="2026-07-09",
            candidate_type="KEY_CANDIDATE", lifecycle_status="READY",
            event_key="stable-event", reject_reasons=[], max_watch_days=10,
            expired_cooldown_days=5, failed_cooldown_days=10,
            candidate=_candidate(),
        )

    assert db.get_strategy6_lifecycle("000001") is None
    assert db.get_strategy6_task_lifecycle("s6-atomic-audit") == []
    assert db.get_strategy6_candidates("s6-atomic-audit") == []

from fastapi.testclient import TestClient

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
        "current_price": 12.34,
        "total_score": 82,
        "start_type": "NORMAL_STRONG_BREAKOUT",
        "start_grade": "A",
        "support_status": "MA20_SUPPORT",
        "key_support_price": 12.0,
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
    }


def test_strategy6_candidate_table_is_independent(tmp_path):
    db.init_db(str(tmp_path / "s6.db"))
    db.create_scan_task("s6-task", "2026-07-09 10:00:00", strategy_type=STRATEGY6_TYPE)

    db.upsert_strategy6_candidate("s6-task", _candidate())

    rows = db.get_strategy6_candidates("s6-task")
    detail = db.get_strategy6_candidate("000001", task_id="s6-task")
    assert rows[0]["code"] == "000001"
    assert rows[0]["candidate_type"] == "KEY_CANDIDATE"
    assert rows[0]["warn_tags"] == ["PRESSURE_NEAR_HIGH"]
    assert detail["risk_reward_ratio_2"] == 2.5
    assert db.get_candidates(task_id="s6-task") == []
    assert db.get_strategy2_candidates(task_id="s6-task") == []
    assert db.get_strategy3_candidates(task_id="s6-task") == []
    assert db.get_strategy4_candidates("s6-task") == []
    assert db.get_strategy5_candidates("s6-task") == []


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


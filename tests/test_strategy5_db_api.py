from fastapi.testclient import TestClient

import scanner.db as db
import server as server_mod


STRATEGY5_TYPE = "STRATEGY_5_SHORT_SPRINT_SUPPORT"


def test_strategy5_candidate_table_is_independent(tmp_path):
    db.init_db(str(tmp_path / "s5.db"))
    db.create_scan_task("s5-test", "2026-07-07 10:00:00", strategy_type=STRATEGY5_TYPE)

    db.upsert_strategy5_candidate("s5-test", {
        "code": "000001",
        "name": "平安银行",
        "evaluation_date": "2026-07-03",
        "candidate_type": "KEY_CANDIDATE",
        "classification": "highlight",
        "total_score": 88,
        "support_status": "SPRINT_MA5_SUPPORT",
        "main_support_ma": "MA5",
        "support_score": 9,
        "risk_tags": [],
        "warn_tags": ["LOW_5D_VOLATILITY"],
        "score_reasons": ["technical=30.0"],
        "reject_reasons": [],
    })

    rows = db.get_strategy5_candidates("s5-test")
    detail = db.get_strategy5_candidate("000001", task_id="s5-test")
    assert rows[0]["code"] == "000001"
    assert rows[0]["candidate_type"] == "KEY_CANDIDATE"
    assert rows[0]["warn_tags"] == ["LOW_5D_VOLATILITY"]
    assert detail["support_score"] == 9
    assert db.get_candidates(task_id="s5-test") == []
    assert db.get_strategy2_candidates(task_id="s5-test") == []
    assert db.get_strategy3_candidates(task_id="s5-test") == []
    assert db.get_strategy4_candidates("s5-test") == []


def test_strategy5_api_returns_candidates_and_rejects_cross_strategy(tmp_path, monkeypatch):
    db_path = str(tmp_path / "s5api.db")
    db.init_db(db_path)
    monkeypatch.setattr(server_mod, "load_config", lambda path="config.yaml": {"data": {"database_path": db_path}, "strategy5": {}})
    server_mod._running.update({"running": False, "task_id": None, "strategy_type": None, "stats": {}})

    db.create_scan_task("s1-task", "2026-07-07 10:00:00", strategy_type="STRATEGY_1_CUP_HANDLE")
    db.create_scan_task("s5-task", "2026-07-07 10:05:00", strategy_type=STRATEGY5_TYPE)
    db.upsert_strategy5_candidate("s5-task", {
        "code": "000001",
        "name": "平安银行",
        "evaluation_date": "2026-07-03",
        "candidate_type": "WATCH_CANDIDATE",
        "classification": "observe",
        "total_score": 72,
        "support_status": "SPRINT_MA50_TESTING",
        "support_score": 4,
    })

    client = TestClient(server_mod.app)
    assert client.get("/api/strategy5/tasks").json()["tasks"][0]["id"] == "s5-task"
    assert client.get("/api/strategy5/tasks/s5-task/candidates").json()["candidates"][0]["code"] == "000001"
    assert client.get("/api/strategy5/tasks/s5-task/candidates/000001").json()["candidate"]["candidate_type"] == "WATCH_CANDIDATE"

    mismatch = client.get("/api/strategy5/tasks/s1-task/candidates")
    assert mismatch.status_code == 400
    assert mismatch.json()["error"] == "TASK_STRATEGY_MISMATCH"

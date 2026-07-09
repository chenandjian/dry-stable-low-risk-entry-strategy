from fastapi.testclient import TestClient
import zipfile
from io import BytesIO

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


def test_strategy6_api_exports_excel_report(tmp_path, monkeypatch):
    db_path = str(tmp_path / "s6report.db")
    db.init_db(db_path)
    monkeypatch.setattr(server_mod, "load_config", lambda path="config.yaml": {"data": {"database_path": db_path}, "strategy6": {}})
    server_mod._running.update({"running": False, "task_id": None, "strategy_type": None, "stats": {}})

    candidate = _candidate()
    candidate.update({
        "enable_market_filter": True,
        "enable_sector_filter": True,
        "market_filter_mode": "downgrade",
        "sector_filter_mode": "downgrade",
        "market_status": "MARKET_STRONG",
        "sector_strength_status": "SECTOR_STRONG",
        "relative_strength_20": 0.18,
        "relative_strength_10_sector": 0.03,
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
    assert "relative_strength_10_sector" in shared
    assert "sector_member_new_high_count" in shared
    assert "days_since_start" in shared
    assert "start_low" in shared
    assert "prior_key_support_price" in shared
    assert "000001" in shared
    assert "MARKET_STRONG" in shared
    assert "SECTOR_STRONG" in shared
    assert "<v>0.18</v>" in sheet
    assert "<v>0.03</v>" in sheet


def test_strategy6_candidate_expires_after_ten_trading_days(tmp_path):
    db.init_db(str(tmp_path / "s6lifecycle.db"))
    previous = _candidate()
    previous["evaluation_date"] = "2026-07-01"
    previous["first_pool_date"] = "2026-07-01"
    previous["pool_age_trading_days"] = 0
    current = _candidate()
    current["evaluation_date"] = "2026-07-22"

    db.create_scan_task("s6-old", "2026-07-01 10:00:00", strategy_type=STRATEGY6_TYPE)
    db.upsert_strategy6_candidate("s6-old", previous)
    db.create_scan_task("s6-new", "2026-07-22 10:00:00", strategy_type=STRATEGY6_TYPE)
    db.upsert_strategy6_candidate("s6-new", current)

    saved = db.get_strategy6_candidate("000001", task_id="s6-new")
    assert saved["first_pool_date"] == "2026-07-01"
    assert saved["pool_age_trading_days"] >= 10
    assert saved["lifecycle_status"] == "EXPIRED"

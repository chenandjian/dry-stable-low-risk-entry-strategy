from scanner import db
from scanner.pattern_detector import CupHandleResult


def test_save_candidates_persists_dry_stable_and_market_fields(tmp_path):
    db_path = tmp_path / "cuphandle.db"
    db.init_db(str(db_path))
    db.create_scan_task("task-1", "2026-06-04 15:30:00", total_stocks=1)

    stock = {
        "code": "600000",
        "name": "测试银行",
        "latest_close": 10.5,
        "latest_turnover": 120_000_000,
        "dry_stable": {
            "decision": {"verdict": "可低吸", "summary": "测试摘要"},
            "volume_dry": {"score": 8},
            "price_stable": {"score": 7},
            "pattern_score": {"score": 15, "type": "较成熟VCP", "key_pattern_type": "vcp"},
            "risk_reward": {"risk_percent": 4.2, "rr1": 2.4, "position_advice": "30%-40%"},
            "key_prices": {
                "entry_zone_low": 10.1,
                "entry_zone_high": 10.4,
                "pivot": 11.0,
                "stop_loss": 9.8,
                "target_1": 12.0,
                "target_2": 13.0,
            },
            "market_environment": {"status": "一般", "position_advice": "轻仓"},
        },
    }
    result = CupHandleResult(found=True, code="600000", name="测试银行", score=76)

    db.save_candidates("task-1", [(stock, result)])
    saved = db.get_candidates("task-1")[0]

    assert saved["dry_stable_verdict"] == "可低吸"
    assert saved["volume_dry_score"] == 8
    assert saved["market_status"] == "一般"
    assert saved["pivot"] == 11.0
    assert saved["pattern_type"] == "较成熟VCP"
    assert saved["key_pattern_type"] == "vcp"

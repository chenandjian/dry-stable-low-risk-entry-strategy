import scanner.db as db


def test_strategy3_candidate_table_roundtrip(tmp_path):
    db.init_db(str(tmp_path / "test.db"))
    db.create_scan_task(
        "s3-task",
        "2026-06-25 15:30:00",
        strategy_type="STRATEGY_3_STRONG_PULLBACK_SECOND_BREAKOUT",
    )

    db.upsert_strategy3_candidate("s3-task", {
        "code": "000001",
        "name": "平安银行",
        "evaluation_date": "2026-06-25",
        "total_score": 86,
        "level": "核心候选",
        "trend_score": 25,
        "pullback_score": 20,
        "volume_stability_score": 16,
        "second_breakout_score": 12,
        "risk_reward_score": 13,
        "current_close": 10.0,
        "ma5": 10.1,
        "ma10": 10.0,
        "ma20": 9.8,
        "ma60": 9.2,
        "ma120": 8.5,
        "recent_high": 11.5,
        "pullback_pct": 0.13,
        "relative_strength_60": 0.10,
        "volume_ratio_5_20": 0.70,
        "range_5": 0.04,
        "close_range_5": 0.03,
        "support_price": 9.5,
        "stop_loss": 9.31,
        "target_1": 12.0,
        "risk_ratio": 0.04,
        "rr1": 2.2,
        "score_reasons": ["强趋势"],
        "reject_reasons": [],
    })

    rows = db.get_strategy3_candidates(task_id="s3-task")
    assert len(rows) == 1
    assert rows[0]["code"] == "000001"
    assert rows[0]["score_reasons"] == ["强趋势"]
    assert rows[0]["reject_reasons"] == []


def test_strategy3_candidates_do_not_leak_into_strategy1_or_strategy2_tables(tmp_path):
    db.init_db(str(tmp_path / "test.db"))
    db.create_scan_task(
        "s3-task",
        "2026-06-25 15:30:00",
        strategy_type="STRATEGY_3_STRONG_PULLBACK_SECOND_BREAKOUT",
    )
    db.upsert_strategy3_candidate("s3-task", {
        "code": "000001",
        "name": "平安银行",
        "evaluation_date": "2026-06-25",
        "total_score": 80,
        "level": "观察候选",
    })

    assert db.get_candidates(task_id="s3-task") == []
    assert db.get_strategy2_candidates(task_id="s3-task") == []


def test_get_strategy3_candidate_by_code(tmp_path):
    db.init_db(str(tmp_path / "test.db"))
    db.create_scan_task(
        "s3-task",
        "2026-06-25 15:30:00",
        strategy_type="STRATEGY_3_STRONG_PULLBACK_SECOND_BREAKOUT",
    )
    db.upsert_strategy3_candidate("s3-task", {
        "code": "000001",
        "name": "平安银行",
        "evaluation_date": "2026-06-25",
        "total_score": 80,
        "level": "观察候选",
    })

    row = db.get_strategy3_candidate("000001", task_id="s3-task")
    assert row["code"] == "000001"
    assert row["level"] == "观察候选"

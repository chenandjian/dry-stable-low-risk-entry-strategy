import scanner.db as db


def test_strategy4_tracking_tables_roundtrip_and_candidate_fields(tmp_path):
    db.init_db(str(tmp_path / "test.db"))
    db.create_scan_task("s4-track", "2026-07-01 15:30:00", strategy_type="STRATEGY_4_HOT_LEADER_SECOND_WAVE")

    db.upsert_strategy4_tracked_topic({
        "topic_id": "concept-ai",
        "topic_name": "AI算力",
        "topic_type": "concept",
        "first_detected_date": "2026-06-01",
        "last_confirmed_date": "2026-06-20",
        "last_evaluated_date": "2026-07-01",
        "age_calendar_days": 30,
        "tracking_status": "SECOND_WAVE_WATCH",
        "tracking_phase": "golden_second_wave",
        "peak_hot_score": 91,
        "latest_hot_score": 76,
        "topic_index_phase": "PULLBACK_REPAIR",
        "topic_index_latest_date": "2026-07-01",
        "source_modes": ["historical_kline_derived"],
        "membership_mode": "current_members_proxy",
        "risk_flags": ["current_members_proxy"],
        "raw_snapshot": {"reason": "unit-test"},
    })
    db.upsert_strategy4_tracked_leader({
        "topic_id": "concept-ai",
        "topic_name": "AI算力",
        "code": "300750",
        "name": "宁德时代",
        "first_detected_date": "2026-06-01",
        "last_confirmed_date": "2026-06-20",
        "last_evaluated_date": "2026-07-01",
        "tracking_status": "SECOND_WAVE_READY",
        "tracking_phase": "golden_second_wave",
        "peak_leader_score": 88,
        "latest_leader_score": 72,
        "support_price": 15.0,
        "stop_loss": 14.7,
        "target_price": 20.0,
        "risk_ratio": 0.08,
        "reward_risk_ratio": 2.4,
        "candidate_origin": "tracking_pool",
        "membership_mode": "current_members_proxy",
        "risk_flags": ["tracking_pool"],
        "raw_snapshot": {"reason": "unit-test"},
    })
    db.insert_strategy4_tracking_event({
        "evaluation_date": "2026-07-01",
        "task_id": "s4-track",
        "entity_type": "leader",
        "topic_id": "concept-ai",
        "code": "300750",
        "previous_status": "PULLBACK_TRACKING",
        "new_status": "SECOND_WAVE_READY",
        "event_type": "CANDIDATE",
        "reason": "second_wave_ready",
        "metrics_snapshot": {"rr": 2.4},
    })
    db.upsert_strategy4_candidate("s4-track", {
        "topic_id": "concept-ai",
        "topic_name": "AI算力",
        "code": "300750",
        "name": "宁德时代",
        "evaluation_date": "2026-07-01",
        "status": "BUYABLE_SECOND_WAVE",
        "strategy4_score": 88,
        "hot_topic_score": 76,
        "leader_strength_score": 72,
        "tradability_score": 80,
        "candidate_origin": "tracking_pool",
        "tracking_topic_status": "SECOND_WAVE_WATCH",
        "tracking_leader_status": "SECOND_WAVE_READY",
        "topic_first_detected_date": "2026-06-01",
        "topic_last_confirmed_date": "2026-06-20",
        "leader_first_detected_date": "2026-06-01",
        "leader_last_confirmed_date": "2026-06-20",
        "tracking_age_days": 30,
        "tracking_phase": "golden_second_wave",
        "tracking_reasons": ["second_wave_ready"],
        "tracking_risk_flags": ["current_members_proxy"],
        "invalid_conditions": [],
    })

    topics = db.get_strategy4_tracked_topics()
    leaders = db.get_strategy4_tracked_leaders()
    events = db.get_strategy4_tracking_events(topic_id="concept-ai")
    candidate = db.get_strategy4_candidates("s4-track")[0]

    assert topics[0]["tracking_status"] == "SECOND_WAVE_WATCH"
    assert topics[0]["source_modes"] == ["historical_kline_derived"]
    assert leaders[0]["tracking_status"] == "SECOND_WAVE_READY"
    assert leaders[0]["risk_flags"] == ["tracking_pool"]
    assert events[0]["event_type"] == "CANDIDATE"
    assert events[0]["metrics_snapshot"] == {"rr": 2.4}
    assert candidate["candidate_origin"] == "tracking_pool"
    assert candidate["tracking_reasons"] == ["second_wave_ready"]

import scanner.db as db

from strategy4.config import resolve_strategy4_config
from strategy4.tracking_service import Strategy4TrackingService


def test_tracking_service_updates_pool_and_builds_tracking_candidate(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    db.save_ohlc("300750", _bars_for_buyable_second_wave())
    db.save_strategy4_topic_index_ohlc(
        topic_id="concept-ai",
        topic_name="AI算力",
        topic_type="concept",
        source="fixture",
        rows=_topic_index_rows(),
    )
    cfg = resolve_strategy4_config({
        "strategy4": {
            "min_leader_strength_score": 40,
            "min_hot_topic_score": 70,
            "topic_index": {"min_required_rows": 20, "history_days": 60},
            "tracking": {"enabled": True},
        }
    })
    service = Strategy4TrackingService({"strategy4": cfg})
    topics = [{
        "topic_id": "concept-ai",
        "topic_name": "AI算力",
        "topic_type": "concept",
        "status": "CONFIRMED_HOT",
        "hot_topic_score": 80,
        "signal_count": 3,
        "topic_index_phase": "MAIN_TREND",
        "source_modes": ["historical_kline_derived"],
        "membership_mode": "current_members_proxy",
    }]
    leaders = [{
        "topic_id": "concept-ai",
        "topic_name": "AI算力",
        "code": "300750",
        "name": "宁德时代",
        "status": "LEADER_CONFIRMED",
        "leader_type": "SPACE_LEADER",
        "leader_strength_score": 72,
        "tradability_score": 80,
        "source_modes": ["historical_kline_derived"],
        "membership_mode": "current_members_proxy",
    }]

    service.update_from_snapshots("s4-track", "2026-06-20", topics, leaders)
    candidates = service.build_candidates_from_pool(
        task_id="s4-track",
        evaluation_date="2026-06-20",
        project_config={"data": {"database_path": db_path}, "strategy4": cfg},
    )

    assert db.get_strategy4_tracked_topics()[0]["tracking_status"] == "ACTIVE_HOT"
    assert db.get_strategy4_tracked_leaders()[0]["tracking_status"] == "SECOND_WAVE_READY"
    assert candidates[0]["candidate_origin"] == "tracking_pool"
    assert candidates[0]["tracking_topic_status"] == "ACTIVE_HOT"
    assert candidates[0]["tracking_leader_status"] == "SECOND_WAVE_READY"


def test_tracking_service_expires_stale_pool_without_refreshing_confirmation(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    cfg = resolve_strategy4_config({
        "strategy4": {
            "min_leader_strength_score": 40,
            "min_hot_topic_score": 70,
            "topic_index": {"min_required_rows": 20, "history_days": 60},
            "tracking": {"enabled": True},
        }
    })
    service = Strategy4TrackingService({"strategy4": cfg})
    service.update_from_snapshots(
        "s4-track",
        "2026-06-20",
        [{
            "topic_id": "concept-ai",
            "topic_name": "AI算力",
            "topic_type": "concept",
            "status": "CONFIRMED_HOT",
            "hot_topic_score": 80,
            "topic_index_phase": "MAIN_TREND",
            "source_modes": ["historical_kline_derived"],
        }],
        [{
            "topic_id": "concept-ai",
            "topic_name": "AI算力",
            "code": "300750",
            "name": "宁德时代",
            "status": "LEADER_CONFIRMED",
            "leader_strength_score": 72,
        }],
    )

    candidates = service.build_candidates_from_pool(
        task_id="s4-track-late",
        evaluation_date="2026-10-20",
        project_config={"data": {"database_path": db_path}, "strategy4": cfg},
    )

    topic = db.get_strategy4_tracked_topics(include_expired=True)[0]
    leader = db.get_strategy4_tracked_leaders(include_expired=True)[0]
    assert candidates == []
    assert topic["tracking_status"] == "EXPIRED"
    assert topic["last_confirmed_date"] == "2026-06-20"
    assert leader["tracking_status"] == "EXPIRED"
    assert leader["last_confirmed_date"] == "2026-06-20"


def _bars_for_buyable_second_wave():
    closes = [
        10.0, 10.2, 10.4, 10.6, 10.8,
        11.2, 12.4, 13.8, 15.2, 17.0,
        16.5, 15.8, 15.3, 15.2, 15.6,
        15.9, 16.1, 16.0, 16.2, 16.4,
    ]
    rows = []
    for idx, close in enumerate(closes):
        previous = closes[idx - 1] if idx else close
        open_ = previous * 0.995
        rows.append({
            "date": f"2026-06-{idx + 1:02d}",
            "open": round(open_, 2),
            "high": round(max(open_, close) * 1.02, 2),
            "low": round(min(open_, close) * 0.98, 2),
            "close": round(close, 2),
            "volume": 6_000_000 if idx < 10 else 3_000_000,
            "turnover": close * (6_000_000 if idx < 10 else 3_000_000),
        })
    rows[-1]["volume"] = 4_000_000
    rows[-1]["open"] = 15.9
    rows[-1]["low"] = 15.6
    rows[-1]["high"] = 16.6
    rows[9]["high"] = 24.0
    for row in rows[10:]:
        row["low"] = max(row["low"], 15.1)
    return rows


def _topic_index_rows():
    return [
        {
            "date": f"2026-06-{idx + 1:02d}",
            "open": 100 + idx,
            "high": 101 + idx,
            "low": 99 + idx,
            "close": 100 + idx,
            "amount": 1_000_000_000 + idx * 30_000_000,
        }
        for idx in range(20)
    ]

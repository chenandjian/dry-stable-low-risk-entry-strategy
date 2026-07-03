import pytest

from strategy4.config import resolve_strategy4_config
from strategy4.tracking_rules import (
    LEADER_EXPIRED,
    LEADER_SECOND_WAVE_READY,
    TOPIC_ACTIVE_HOT,
    TOPIC_EXPIRED,
    TOPIC_INVALIDATED,
    build_leader_tracking_state,
    build_topic_tracking_state,
    tracking_phase_for_age,
)


def test_strategy4_tracking_config_defaults_to_120_calendar_days():
    cfg = resolve_strategy4_config({})

    assert cfg["tracking"]["enabled"] is True
    assert cfg["tracking"]["max_calendar_days"] == 120
    assert cfg["tracking"]["strong_attention_days"] == 20
    assert cfg["tracking"]["golden_second_wave_days"] == 60


def test_confirmed_topic_enters_pool_and_expires_after_120_days():
    cfg = resolve_strategy4_config({})
    topic = {
        "topic_id": "concept-ai",
        "topic_name": "AI算力",
        "topic_type": "concept",
        "status": "CONFIRMED_HOT",
        "hot_topic_score": 82,
        "topic_index_phase": "MAIN_TREND",
        "source_modes": ["historical_kline_derived"],
    }

    active = build_topic_tracking_state(topic, evaluation_date="2026-06-01", config=cfg)
    expired = build_topic_tracking_state(
        topic,
        evaluation_date="2026-10-01",
        config=cfg,
        existing=active,
    )

    assert active["tracking_status"] == TOPIC_ACTIVE_HOT
    assert active["first_detected_date"] == "2026-06-01"
    assert active["tracking_phase"] == "strong_attention"
    assert expired["tracking_status"] == TOPIC_EXPIRED
    assert expired["age_calendar_days"] > 120


def test_weak_noise_topic_is_invalidated_in_tracking_pool():
    cfg = resolve_strategy4_config({})
    state = build_topic_tracking_state(
        {
            "topic_id": "concept-ai",
            "topic_name": "AI算力",
            "topic_type": "concept",
            "status": "CONFIRMED_HOT",
            "hot_topic_score": 80,
            "topic_index_phase": "WEAK_NOISE",
            "source_modes": ["historical_kline_derived"],
        },
        evaluation_date="2026-06-10",
        config=cfg,
    )

    assert state["tracking_status"] == TOPIC_INVALIDATED
    assert "WEAK_NOISE" in state["invalid_reason"]


@pytest.mark.parametrize(
    ("age", "expected"),
    [(3, "strong_attention"), (30, "golden_second_wave"), (90, "extension")],
)
def test_tracking_phase_for_age(age, expected):
    cfg = resolve_strategy4_config({})

    assert tracking_phase_for_age(age, cfg) == expected


def test_leader_ready_state_preserves_tracking_metadata():
    cfg = resolve_strategy4_config({})
    topic_state = {
        "topic_id": "concept-ai",
        "topic_name": "AI算力",
        "tracking_status": TOPIC_ACTIVE_HOT,
        "tracking_phase": "golden_second_wave",
        "first_detected_date": "2026-06-01",
        "last_confirmed_date": "2026-06-01",
        "age_calendar_days": 30,
    }
    leader = {
        "topic_id": "concept-ai",
        "topic_name": "AI算力",
        "code": "300750",
        "name": "宁德时代",
        "status": "LEADER_CONFIRMED",
        "leader_strength_score": 72,
        "membership_mode": "current_members_proxy",
    }
    evaluation = {
        "passed": True,
        "risk_reward": type("RR", (), {
            "support_price": 15.0,
            "stop_loss": 14.7,
            "target_price": 20.0,
            "risk_ratio": 0.08,
            "reward_risk_ratio": 2.4,
        })(),
        "pullback": type("PB", (), {"pullback_pct": 0.18, "pullback_days": 12})(),
    }

    state = build_leader_tracking_state(
        leader,
        evaluation_date="2026-07-01",
        config=cfg,
        topic_state=topic_state,
        evaluation=evaluation,
    )

    assert state["tracking_status"] == LEADER_SECOND_WAVE_READY
    assert state["topic_first_detected_date"] == "2026-06-01"
    assert state["tracking_phase"] == "golden_second_wave"
    assert state["reward_risk_ratio"] == 2.4


def test_leader_expires_when_topic_expires():
    cfg = resolve_strategy4_config({})
    state = build_leader_tracking_state(
        {"topic_id": "concept-ai", "code": "300750", "name": "宁德时代", "status": "LEADER_CONFIRMED"},
        evaluation_date="2026-10-01",
        config=cfg,
        topic_state={
            "topic_id": "concept-ai",
            "topic_name": "AI算力",
            "tracking_status": TOPIC_EXPIRED,
            "tracking_phase": "expired",
            "first_detected_date": "2026-06-01",
            "last_confirmed_date": "2026-06-01",
            "age_calendar_days": 122,
        },
        existing={"first_detected_date": "2026-06-01"},
    )

    assert state["tracking_status"] == LEADER_EXPIRED

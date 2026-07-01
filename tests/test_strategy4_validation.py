import pytest

from strategy4.config import resolve_strategy4_config


def test_resolve_strategy4_config_defaults():
    cfg = resolve_strategy4_config({})

    assert cfg["enabled"] is True
    assert cfg["hot_topic_top_n"] == 8
    assert cfg["watch_hot_topic_top_n"] == 15
    assert cfg["min_hot_topic_score"] == 85
    assert cfg["min_hot_topic_signal_count"] == 2
    assert cfg["core_leaders_per_topic"] == 1
    assert cfg["backup_leaders_per_topic"] == 2
    assert cfg["max_total_leaders_per_topic"] == 3
    assert cfg["min_leader_strength_score"] == 88
    assert cfg["core_leader_strength_score"] == 93
    assert cfg["first_wave_lookback_short"] == 10
    assert cfg["first_wave_lookback_long"] == 20
    assert cfg["min_first_wave_return_10d"] == 0.25
    assert cfg["min_first_wave_return_20d"] == 0.35
    assert cfg["pullback_min_pct"] == 0.08
    assert cfg["pullback_max_pct"] == 0.25
    assert cfg["pullback_min_days"] == 2
    assert cfg["pullback_max_days"] == 8
    assert cfg["max_risk_ratio"] == 0.15
    assert cfg["aggressive_max_risk_ratio"] == 0.20
    assert cfg["min_reward_risk_ratio"] == 2.0
    assert cfg["core_leader_min_reward_risk_ratio"] == 1.8


def test_resolve_strategy4_config_accepts_nested_overrides():
    cfg = resolve_strategy4_config({
        "strategy4": {
            "hot_topic_top_n": 10,
            "min_hot_topic_score": 80,
            "max_risk_ratio": 0.12,
            "core_leader_min_reward_risk_ratio": 1.6,
        },
    })

    assert cfg["hot_topic_top_n"] == 10
    assert cfg["min_hot_topic_score"] == 80
    assert cfg["max_risk_ratio"] == 0.12
    assert cfg["core_leader_min_reward_risk_ratio"] == 1.6


def test_strategy4_config_rejects_invalid_orders():
    with pytest.raises(ValueError, match="watch_hot_topic_top_n"):
        resolve_strategy4_config({"strategy4": {"hot_topic_top_n": 20, "watch_hot_topic_top_n": 10}})

    with pytest.raises(ValueError, match="max_total_leaders_per_topic"):
        resolve_strategy4_config({
            "strategy4": {
                "core_leaders_per_topic": 2,
                "backup_leaders_per_topic": 2,
                "max_total_leaders_per_topic": 3,
            },
        })

    with pytest.raises(ValueError, match="core_leader_strength_score"):
        resolve_strategy4_config({
            "strategy4": {
                "min_leader_strength_score": 95,
                "core_leader_strength_score": 90,
            },
        })

    with pytest.raises(ValueError, match="pullback_max_pct"):
        resolve_strategy4_config({"strategy4": {"pullback_min_pct": 0.20, "pullback_max_pct": 0.10}})

    with pytest.raises(ValueError, match="aggressive_max_risk_ratio"):
        resolve_strategy4_config({"strategy4": {"max_risk_ratio": 0.20, "aggressive_max_risk_ratio": 0.15}})

    with pytest.raises(ValueError, match="core_leader_min_reward_risk_ratio"):
        resolve_strategy4_config({
            "strategy4": {
                "min_reward_risk_ratio": 2.0,
                "core_leader_min_reward_risk_ratio": 2.5,
            },
        })

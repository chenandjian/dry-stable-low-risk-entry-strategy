import pytest

from strategy4.config import resolve_strategy4_config


def test_resolve_strategy4_config_defaults():
    cfg = resolve_strategy4_config({})

    assert cfg["enabled"] is True
    assert cfg["hot_topic_top_n"] == 16
    assert cfg["watch_hot_topic_top_n"] == 16
    assert cfg["min_hot_topic_score"] == 65
    assert cfg["min_hot_topic_signal_count"] == 1
    assert cfg["core_leaders_per_topic"] == 1
    assert cfg["backup_leaders_per_topic"] == 2
    assert cfg["max_total_leaders_per_topic"] == 3
    assert cfg["min_leader_strength_score"] == 50
    assert cfg["core_leader_strength_score"] == 50
    assert cfg["first_wave_lookback_short"] == 10
    assert cfg["first_wave_lookback_long"] == 20
    assert cfg["min_first_wave_return_10d"] == 0.10
    assert cfg["min_first_wave_return_20d"] == 0.15
    assert cfg["min_strong_day_count_10d"] == 1
    assert cfg["pullback_min_pct"] == 0.05
    assert cfg["pullback_max_pct"] == 0.30
    assert cfg["pullback_min_days"] == 1
    assert cfg["pullback_max_days"] == 40
    assert cfg["max_risk_ratio"] == 0.10
    assert cfg["aggressive_max_risk_ratio"] == 0.10
    assert cfg["min_reward_risk_ratio"] == 1.5
    assert cfg["core_leader_min_reward_risk_ratio"] == 1.5
    assert cfg["topic_index"]["enabled"] is True
    assert cfg["topic_index"]["preferred_sources"] == ["akshare_ths", "akshare_eastmoney"]
    assert cfg["topic_index"]["history_days"] == 250
    assert cfg["topic_index"]["min_required_rows"] == 60
    assert cfg["topic_index"]["require_for_buyable_candidate"] is True
    assert cfg["source_modes"]["live_external_enabled"] is True
    assert cfg["source_modes"]["historical_kline_derived_enabled"] is True
    assert cfg["source_modes"]["merge_mode"] == "union_with_confidence"
    assert cfg["derived_source"]["enabled"] is True
    assert cfg["derived_source"]["topic_top_n"] == 30
    assert cfg["derived_source"]["max_topics_per_day"] == 34
    assert cfg["derived_source"]["max_leaders_per_topic"] == 5
    assert cfg["derived_source"]["min_topic_hot_score"] == 50
    assert cfg["derived_source"]["min_confirmed_topic_hot_score"] == 60
    assert cfg["derived_source"]["min_member_count"] == 5
    assert cfg["derived_source"]["allow_current_members_proxy"] is True
    assert cfg["merge_policy"]["block_buyable_on_derived_weak_noise"] is True


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


def test_resolve_strategy4_config_accepts_nested_topic_index_overrides():
    cfg = resolve_strategy4_config({
        "strategy4": {
            "topic_index": {
                "preferred_sources": ["akshare_eastmoney"],
                "history_days": 120,
                "min_required_rows": 30,
            },
        },
    })

    assert cfg["topic_index"]["preferred_sources"] == ["akshare_eastmoney"]
    assert cfg["topic_index"]["history_days"] == 120
    assert cfg["topic_index"]["min_required_rows"] == 30
    assert cfg["topic_index"]["require_for_buyable_candidate"] is True


def test_resolve_strategy4_config_accepts_derived_source_overrides():
    cfg = resolve_strategy4_config({
        "strategy4": {
            "source_modes": {
                "historical_kline_derived_enabled": False,
            },
            "derived_source": {
                "topic_top_n": 12,
                "max_topics_per_day": 20,
                "max_leaders_per_topic": 4,
                "min_topic_index_rows": 30,
                "min_breadth_ratio": 0.4,
            },
            "merge_policy": {
                "allow_derived_only_buyable": False,
            },
        },
    })

    assert cfg["source_modes"]["historical_kline_derived_enabled"] is False
    assert cfg["source_modes"]["live_external_enabled"] is True
    assert cfg["derived_source"]["topic_top_n"] == 12
    assert cfg["derived_source"]["max_topics_per_day"] == 20
    assert cfg["derived_source"]["max_leaders_per_topic"] == 4
    assert cfg["derived_source"]["min_topic_index_rows"] == 30
    assert cfg["derived_source"]["min_breadth_ratio"] == 0.4
    assert cfg["merge_policy"]["allow_derived_only_buyable"] is False


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

    with pytest.raises(ValueError, match="topic_index.preferred_sources"):
        resolve_strategy4_config({"strategy4": {"topic_index": {"preferred_sources": ["fake"]}}})

    with pytest.raises(ValueError, match="topic_index.history_days"):
        resolve_strategy4_config({"strategy4": {"topic_index": {"history_days": 10}}})

    with pytest.raises(ValueError, match="topic_index.history_days must be >= topic_index.min_required_rows"):
        resolve_strategy4_config({"strategy4": {"topic_index": {"history_days": 80, "min_required_rows": 120}}})

    with pytest.raises(ValueError, match="source_modes.merge_mode"):
        resolve_strategy4_config({"strategy4": {"source_modes": {"merge_mode": "replace_live"}}})

    with pytest.raises(ValueError, match="derived_source.max_topics_per_day"):
        resolve_strategy4_config({"strategy4": {"derived_source": {"topic_top_n": 20, "max_topics_per_day": 10}}})

    with pytest.raises(ValueError, match="derived_source.min_breadth_ratio"):
        resolve_strategy4_config({"strategy4": {"derived_source": {"min_breadth_ratio": 1.5}}})

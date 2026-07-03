"""Strategy4 configuration validation."""
from __future__ import annotations

import copy
from numbers import Real


DEFAULT_STRATEGY4_CONFIG = {
    "enabled": True,
    "hot_topic_top_n": 8,
    "watch_hot_topic_top_n": 15,
    "min_hot_topic_score": 85,
    "min_hot_topic_signal_count": 2,
    "core_leaders_per_topic": 1,
    "backup_leaders_per_topic": 2,
    "max_total_leaders_per_topic": 3,
    "min_leader_strength_score": 88,
    "core_leader_strength_score": 93,
    "first_wave_lookback_short": 10,
    "first_wave_lookback_long": 20,
    "min_first_wave_return_10d": 0.25,
    "min_first_wave_return_20d": 0.35,
    "min_strong_day_count_10d": 2,
    "pullback_min_pct": 0.08,
    "pullback_max_pct": 0.25,
    "pullback_min_days": 2,
    "pullback_max_days": 8,
    "max_risk_ratio": 0.15,
    "aggressive_max_risk_ratio": 0.20,
    "min_reward_risk_ratio": 2.0,
    "core_leader_min_reward_risk_ratio": 1.8,
    "topic_index": {
        "enabled": True,
        "preferred_sources": ["akshare_ths", "akshare_eastmoney"],
        "history_days": 250,
        "min_required_rows": 60,
        "require_for_buyable_candidate": True,
        "allow_unobserved_for_watch": True,
        "max_fetch_topics_per_scan": 30,
        "source_retry_attempts": 2,
    },
    "topic_index_filters": {
        "min_trend_score": 8.0,
        "min_breakout_score": 0.0,
        "min_amount_ratio_5_20": 1.0,
        "max_drawdown_from_high_20": 0.12,
        "allowed_phases": ["EARLY_ACCELERATION", "MAIN_TREND", "PULLBACK_REPAIR"],
    },
    "leader_relative_strength": {
        "min_rs_10d": 0.05,
        "min_rs_20d": 0.08,
    },
    "source_modes": {
        "live_external_enabled": True,
        "historical_kline_derived_enabled": True,
        "merge_mode": "union_with_confidence",
    },
    "derived_source": {
        "enabled": True,
        "topic_top_n": 20,
        "max_topics_per_day": 30,
        "max_leaders_per_topic": 5,
        "min_topic_hot_score": 60,
        "min_confirmed_topic_hot_score": 75,
        "min_topic_index_rows": 60,
        "min_amount_ratio_5_20": 1.0,
        "min_breadth_ratio": 0.55,
        "min_member_count": 5,
        "allow_current_members_proxy": True,
        "current_members_proxy_trust_level": "experimental",
    },
    "merge_policy": {
        "buyable_requires_observed_source": True,
        "block_buyable_on_derived_weak_noise": True,
        "block_buyable_on_derived_high_risk_climax": True,
        "allow_derived_only_watch": True,
        "allow_derived_only_buyable": True,
    },
    "tracking": {
        "enabled": True,
        "max_calendar_days": 120,
        "strong_attention_days": 20,
        "golden_second_wave_days": 60,
        "allow_extension_days": 120,
        "expire_without_leader_days": 30,
        "extension_min_reward_risk_ratio": 2.0,
        "extension_max_risk_ratio": 0.12,
        "max_topic_drawdown_since_detected": 0.20,
        "max_leader_drawdown_from_first_wave_high": 0.45,
        "min_extension_leader_rs_20d": -0.05,
    },
}


def resolve_strategy4_config(config: dict | None) -> dict:
    """Resolve and validate Strategy4 config from full project or nested config."""
    config = config or {}
    raw = copy.deepcopy(DEFAULT_STRATEGY4_CONFIG)
    if "strategy4" in config:
        _deep_update(raw, config.get("strategy4") or {})
    else:
        _deep_update(raw, config)

    raw["enabled"] = bool(raw.get("enabled", True))
    _validate_int_range(raw, "hot_topic_top_n", 1, 50)
    _validate_int_range(raw, "watch_hot_topic_top_n", raw["hot_topic_top_n"], 100)
    _validate_number_range(raw, "min_hot_topic_score", 0, 100)
    _validate_int_range(raw, "min_hot_topic_signal_count", 1, 10)
    _validate_int_range(raw, "core_leaders_per_topic", 0, 10)
    _validate_int_range(raw, "backup_leaders_per_topic", 0, 20)
    _validate_int_range(
        raw,
        "max_total_leaders_per_topic",
        raw["core_leaders_per_topic"] + raw["backup_leaders_per_topic"],
        30,
    )
    _validate_number_range(raw, "min_leader_strength_score", 0, 100)
    _validate_number_range(raw, "core_leader_strength_score", raw["min_leader_strength_score"], 100)
    _validate_int_range(raw, "first_wave_lookback_short", 3, 60)
    _validate_int_range(raw, "first_wave_lookback_long", raw["first_wave_lookback_short"], 120)
    _validate_number_range(raw, "min_first_wave_return_10d", 0, 2)
    _validate_number_range(raw, "min_first_wave_return_20d", 0, 3)
    _validate_int_range(raw, "min_strong_day_count_10d", 1, 10)
    _validate_number_range(raw, "pullback_min_pct", 0, 0.8)
    _validate_number_range(raw, "pullback_max_pct", raw["pullback_min_pct"], 0.8)
    _validate_int_range(raw, "pullback_min_days", 1, 30)
    _validate_int_range(raw, "pullback_max_days", raw["pullback_min_days"], 60)
    _validate_number_range(raw, "max_risk_ratio", 0.01, 0.5)
    _validate_number_range(raw, "aggressive_max_risk_ratio", raw["max_risk_ratio"], 0.8)
    _validate_number_range(raw, "core_leader_min_reward_risk_ratio", 0.5, raw["min_reward_risk_ratio"])
    _validate_number_range(raw, "min_reward_risk_ratio", raw["core_leader_min_reward_risk_ratio"], 10)
    _validate_topic_index_config(raw)
    _validate_source_modes(raw)
    _validate_derived_source(raw)
    _validate_merge_policy(raw)
    _validate_tracking(raw)
    return raw


def _deep_update(base: dict, updates: dict) -> None:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            merged = dict(base[key])
            _deep_update(merged, value)
            base[key] = merged
        else:
            base[key] = value


def _validate_topic_index_config(config: dict) -> None:
    topic_index = config.get("topic_index") or {}
    topic_index["enabled"] = bool(topic_index.get("enabled", True))
    topic_index["require_for_buyable_candidate"] = bool(topic_index.get("require_for_buyable_candidate", True))
    topic_index["allow_unobserved_for_watch"] = bool(topic_index.get("allow_unobserved_for_watch", True))
    sources = topic_index.get("preferred_sources") or ["akshare_ths", "akshare_eastmoney"]
    if not isinstance(sources, list) or not sources:
        raise ValueError("topic_index.preferred_sources must be a non-empty list")
    allowed = {"akshare_ths", "akshare_eastmoney"}
    if any(src not in allowed for src in sources):
        raise ValueError("topic_index.preferred_sources contains unsupported source")
    topic_index["preferred_sources"] = sources
    for key, min_v, max_v in (
        ("history_days", 60, 1000),
        ("min_required_rows", 2, 500),
        ("max_fetch_topics_per_scan", 1, 100),
        ("source_retry_attempts", 1, 5),
    ):
        value = topic_index.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"topic_index.{key} must be an integer")
        if value < min_v or value > max_v:
            raise ValueError(f"topic_index.{key} must be between {min_v} and {max_v}")
    if topic_index["history_days"] < topic_index["min_required_rows"]:
        raise ValueError("topic_index.history_days must be >= topic_index.min_required_rows")
    config["topic_index"] = topic_index


def _validate_source_modes(config: dict) -> None:
    source_modes = config.get("source_modes") or {}
    source_modes["live_external_enabled"] = bool(source_modes.get("live_external_enabled", True))
    source_modes["historical_kline_derived_enabled"] = bool(source_modes.get("historical_kline_derived_enabled", True))
    merge_mode = str(source_modes.get("merge_mode") or "union_with_confidence")
    if merge_mode != "union_with_confidence":
        raise ValueError("source_modes.merge_mode must be union_with_confidence")
    source_modes["merge_mode"] = merge_mode
    config["source_modes"] = source_modes


def _validate_derived_source(config: dict) -> None:
    derived = config.get("derived_source") or {}
    derived["enabled"] = bool(derived.get("enabled", True))
    derived["allow_current_members_proxy"] = bool(derived.get("allow_current_members_proxy", True))
    for key, min_v, max_v in (
        ("topic_top_n", 1, 100),
        ("max_topics_per_day", 1, 200),
        ("max_leaders_per_topic", 1, 30),
        ("min_topic_index_rows", 20, 500),
        ("min_member_count", 1, 5000),
    ):
        value = derived.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"derived_source.{key} must be an integer")
        if value < min_v or value > max_v:
            raise ValueError(f"derived_source.{key} must be between {min_v} and {max_v}")
    if derived["max_topics_per_day"] < derived["topic_top_n"]:
        raise ValueError("derived_source.max_topics_per_day must be >= derived_source.topic_top_n")
    for key, min_v, max_v in (
        ("min_topic_hot_score", 0.0, 100.0),
        ("min_confirmed_topic_hot_score", 0.0, 100.0),
        ("min_amount_ratio_5_20", 0.0, 10.0),
        ("min_breadth_ratio", 0.0, 1.0),
    ):
        _validate_prefixed_number_range(derived, key, min_v, max_v, "derived_source")
    trust = str(derived.get("current_members_proxy_trust_level") or "experimental")
    if trust not in {"experimental", "trusted"}:
        raise ValueError("derived_source.current_members_proxy_trust_level must be experimental or trusted")
    derived["current_members_proxy_trust_level"] = trust
    config["derived_source"] = derived


def _validate_merge_policy(config: dict) -> None:
    policy = config.get("merge_policy") or {}
    for key, default in (
        ("buyable_requires_observed_source", True),
        ("block_buyable_on_derived_weak_noise", True),
        ("block_buyable_on_derived_high_risk_climax", True),
        ("allow_derived_only_watch", True),
        ("allow_derived_only_buyable", True),
    ):
        policy[key] = bool(policy.get(key, default))
    config["merge_policy"] = policy


def _validate_tracking(config: dict) -> None:
    tracking = config.get("tracking") or {}
    tracking["enabled"] = bool(tracking.get("enabled", True))
    for key, min_v, max_v in (
        ("strong_attention_days", 1, 120),
        ("golden_second_wave_days", 1, 180),
        ("allow_extension_days", 1, 240),
        ("max_calendar_days", 1, 365),
        ("expire_without_leader_days", 1, 180),
    ):
        value = tracking.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"tracking.{key} must be an integer")
        if value < min_v or value > max_v:
            raise ValueError(f"tracking.{key} must be between {min_v} and {max_v}")
    if tracking["golden_second_wave_days"] < tracking["strong_attention_days"]:
        raise ValueError("tracking.golden_second_wave_days must be >= tracking.strong_attention_days")
    if tracking["allow_extension_days"] < tracking["golden_second_wave_days"]:
        raise ValueError("tracking.allow_extension_days must be >= tracking.golden_second_wave_days")
    if tracking["max_calendar_days"] < tracking["allow_extension_days"]:
        raise ValueError("tracking.max_calendar_days must be >= tracking.allow_extension_days")
    for key, min_v, max_v in (
        ("extension_min_reward_risk_ratio", 0.5, 10.0),
        ("extension_max_risk_ratio", 0.01, 0.5),
        ("max_topic_drawdown_since_detected", 0.01, 0.8),
        ("max_leader_drawdown_from_first_wave_high", 0.01, 0.9),
        ("min_extension_leader_rs_20d", -1.0, 1.0),
    ):
        _validate_prefixed_number_range(tracking, key, min_v, max_v, "tracking")
    config["tracking"] = tracking


def _validate_int_range(config: dict, key: str, min_value: int, max_value: int) -> None:
    value = config.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    if value < min_value or value > max_value:
        raise ValueError(f"{key} must be between {min_value} and {max_value}")


def _validate_number_range(config: dict, key: str, min_value: float, max_value: float) -> None:
    value = config.get(key)
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{key} must be a number")
    value = float(value)
    if value < min_value or value > max_value:
        raise ValueError(f"{key} must be between {min_value} and {max_value}")
    config[key] = value


def _validate_prefixed_number_range(config: dict, key: str, min_value: float, max_value: float, prefix: str) -> None:
    value = config.get(key)
    full_key = f"{prefix}.{key}"
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{full_key} must be a number")
    value = float(value)
    if value < min_value or value > max_value:
        raise ValueError(f"{full_key} must be between {min_value} and {max_value}")
    config[key] = value

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

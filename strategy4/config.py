"""Strategy4 configuration validation."""
from __future__ import annotations

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
}


def resolve_strategy4_config(config: dict | None) -> dict:
    """Resolve and validate Strategy4 config from full project or nested config."""
    config = config or {}
    raw = dict(DEFAULT_STRATEGY4_CONFIG)
    if "strategy4" in config:
        raw.update(config.get("strategy4") or {})
    else:
        raw.update(config)

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
    return raw


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


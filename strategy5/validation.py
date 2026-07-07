"""Strategy5 configuration validation."""
from __future__ import annotations

import copy
from numbers import Real


DEFAULT_STRATEGY5_CONFIG = {
    "enabled": True,
    "kline_days": 1100,
    "minimum_kline_days": 260,
    "minimum_trading_days": 500,
    "min_avg_amount_60d_yi": 30,
    "min_avg_amount_30d_yi": 20,
    "min_avg_amount_10d_yi": 15,
    "strength_ret_20d": 0.25,
    "strength_ret_10d": 0.15,
    "strength_ret_5d": 0.10,
    "single_day_surge_return": 0.07,
    "single_day_surge_volume_ratio": 1.8,
    "near_120d_high_ratio": 1.00,
    "max_amp_5d": 0.22,
    "max_amp_10d": 0.45,
    "max_drawdown_20d": -0.30,
    "max_decline_5d": -0.08,
    "volume_down_return": -0.07,
    "volume_down_ratio": 1.5,
    "ma50_min_ratio": 0.92,
    "key_candidate_min_support_score": 8,
}


def resolve_strategy5_config(config: dict | None) -> dict:
    """Resolve Strategy5 config from a full project config or a nested config."""
    config = config or {}
    raw = copy.deepcopy(DEFAULT_STRATEGY5_CONFIG)
    overrides = config.get("strategy5") if "strategy5" in config else config
    if overrides:
        raw.update(overrides)

    raw["enabled"] = bool(raw.get("enabled", True))
    _validate_int_range(raw, "kline_days", 260, 3000)
    _validate_int_range(raw, "minimum_kline_days", 120, raw["kline_days"])
    _validate_int_range(raw, "minimum_trading_days", 120, raw["kline_days"])
    _validate_number_range(raw, "min_avg_amount_60d_yi", 0, 1000)
    _validate_number_range(raw, "min_avg_amount_30d_yi", 0, 1000)
    _validate_number_range(raw, "min_avg_amount_10d_yi", 0, 1000)
    _validate_number_range(raw, "strength_ret_20d", -1, 5)
    _validate_number_range(raw, "strength_ret_10d", -1, 5)
    _validate_number_range(raw, "strength_ret_5d", -1, 5)
    _validate_number_range(raw, "single_day_surge_return", 0, 1)
    _validate_number_range(raw, "single_day_surge_volume_ratio", 0, 20)
    _validate_number_range(raw, "near_120d_high_ratio", 0, 1)
    _validate_number_range(raw, "max_amp_5d", 0, 2)
    _validate_number_range(raw, "max_amp_10d", 0, 3)
    _validate_number_range(raw, "max_drawdown_20d", -1, 0)
    _validate_number_range(raw, "max_decline_5d", -1, 0)
    _validate_number_range(raw, "volume_down_return", -1, 0)
    _validate_number_range(raw, "volume_down_ratio", 0, 20)
    _validate_number_range(raw, "ma50_min_ratio", 0, 2)
    _validate_number_range(raw, "key_candidate_min_support_score", 0, 10)
    return raw


def _validate_int_range(config: dict, key: str, min_v: int, max_v: int) -> None:
    value = config.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    if value < min_v or value > max_v:
        raise ValueError(f"{key} must be between {min_v} and {max_v}")


def _validate_number_range(config: dict, key: str, min_v: float, max_v: float) -> None:
    value = config.get(key)
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{key} must be a number")
    if value < min_v or value > max_v:
        raise ValueError(f"{key} must be between {min_v} and {max_v}")

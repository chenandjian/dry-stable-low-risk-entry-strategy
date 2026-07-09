"""Strategy6 configuration validation."""
from __future__ import annotations

import copy
from numbers import Real


DEFAULT_STRATEGY6_CONFIG = {
    "enabled": True,
    "kline_days": 1100,
    "minimum_trading_days": 500,
    "min_avg_amount_60d_yi": 3,
    "min_avg_amount_30d_yi": 5,
    "min_avg_amount_10d_yi": 5,
    "amount10_vs_30_min_ratio": 0.8,
    "enable_market_filter": True,
    "enable_sector_filter": False,
    "market_filter_mode": "downgrade",
    "sector_filter_mode": "downgrade",
    "sector_min_member_new_high_count": 3,
    "min_relative_strength_20": 0.10,
    "normal_start_return": 0.07,
    "normal_start_volume_ratio": 2.0,
    "normal_start_close_position": 0.65,
    "normal_start_min_amount_yi": 8,
    "limit_up_volume_ratio": 1.5,
    "low_volume_limit_up_min_ratio": 0.6,
    "near_120d_high_ratio": 0.98,
    "max_amp_5d_s": 0.25,
    "max_amp_10d_s": 0.45,
    "max_pullback_20d_s": -0.30,
    "max_amp_5d_a": 0.22,
    "max_amp_10d_a": 0.40,
    "max_pullback_20d_a": -0.26,
    "max_amp_5d_b": 0.18,
    "max_amp_10d_b": 0.35,
    "max_pullback_20d_b": -0.22,
    "absolute_max_amp_10d": 0.50,
    "absolute_max_pullback_20d": -0.35,
    "ma50_min_ratio": 0.92,
    "tail_close_range_5": 0.08,
    "tail_volume_ratio_5_20": 0.75,
    "tail_strong_volume_ratio_5_20": 0.60,
    "tail_min_return_5": -0.06,
    "tail_min_return_3": -0.04,
    "big_down_return": -0.07,
    "big_down_volume_ratio": 1.5,
    "rr2_min_watch": 1.5,
    "rr2_min_key": 2.0,
    "rr2_min_ready": 2.5,
    "ready_min_score": 85,
    "key_min_score": 75,
    "watch_min_score": 60,
}


def resolve_strategy6_config(config: dict | None) -> dict:
    config = config or {}
    raw = copy.deepcopy(DEFAULT_STRATEGY6_CONFIG)
    overrides = config.get("strategy6") if "strategy6" in config else config
    if overrides:
        raw.update(overrides)

    raw["enabled"] = bool(raw.get("enabled", True))
    _validate_int_range(raw, "kline_days", 260, 3000)
    _validate_int_range(raw, "minimum_trading_days", 260, raw["kline_days"])
    _validate_int_range(raw, "sector_min_member_new_high_count", 0, 50)
    for key in (
        "min_avg_amount_60d_yi", "min_avg_amount_30d_yi", "min_avg_amount_10d_yi",
        "amount10_vs_30_min_ratio", "normal_start_return", "normal_start_volume_ratio",
        "normal_start_close_position", "normal_start_min_amount_yi", "limit_up_volume_ratio",
        "low_volume_limit_up_min_ratio", "near_120d_high_ratio", "min_relative_strength_20", "max_amp_5d_s",
        "max_amp_10d_s", "max_amp_5d_a", "max_amp_10d_a", "max_amp_5d_b",
        "max_amp_10d_b", "absolute_max_amp_10d", "ma50_min_ratio",
        "tail_close_range_5", "tail_volume_ratio_5_20", "tail_strong_volume_ratio_5_20",
        "big_down_volume_ratio", "rr2_min_watch", "rr2_min_key", "rr2_min_ready",
    ):
        _validate_number(raw, key)
    for key in (
        "max_pullback_20d_s", "max_pullback_20d_a", "max_pullback_20d_b",
        "absolute_max_pullback_20d", "tail_min_return_5", "tail_min_return_3", "big_down_return",
    ):
        _validate_number(raw, key)
    for key in ("ready_min_score", "key_min_score", "watch_min_score"):
        _validate_number_range(raw, key, 0, 100)
    raw["enable_market_filter"] = bool(raw.get("enable_market_filter", False))
    raw["enable_sector_filter"] = False
    raw["sector_filter_mode"] = "disabled"
    if raw.get("market_filter_mode") not in {"strict", "downgrade", "score_only"}:
        raise ValueError("market_filter_mode must be one of strict/downgrade/score_only")
    return raw


def _validate_int_range(config: dict, key: str, min_v: int, max_v: int) -> None:
    value = config.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    if value < min_v or value > max_v:
        raise ValueError(f"{key} must be between {min_v} and {max_v}")


def _validate_number(config: dict, key: str) -> None:
    value = config.get(key)
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{key} must be a number")


def _validate_number_range(config: dict, key: str, min_v: float, max_v: float) -> None:
    _validate_number(config, key)
    value = config[key]
    if value < min_v or value > max_v:
        raise ValueError(f"{key} must be between {min_v} and {max_v}")

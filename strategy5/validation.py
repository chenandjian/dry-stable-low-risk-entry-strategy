"""Strategy5 configuration validation."""
from __future__ import annotations

import copy
from numbers import Real


DEFAULT_STRATEGY5_CONFIG = {
    "enabled": True,
    "kline_days": 1100,
    "minimum_trading_days": 500,
    "min_avg_amount_60d_yi": 15,
    "min_avg_amount_30d_yi": 8,
    "min_avg_amount_10d_yi": 5,
    "kcb_min_avg_amount_60d_yi": 50,
    "kcb_min_avg_amount_30d_yi": 30,
    "kcb_min_avg_amount_10d_yi": 20,
    "strength_ret_20d": 0.25,
    "strength_ret_10d": 0.15,
    "strength_ret_5d": 0.10,
    "strength_ret_50d": 0.35,
    "strength_ret_50d_min_20d": 0.05,
    "strength_ret_50d_ma20_ratio": 0.98,
    "strength_ret_50d_max_amp_10d": 0.30,
    "strength_ret_50d_max_decline_5d": -0.06,
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
    "volume_dry_min_score_key": 14,
    "volume_dry_min_score_watch": 10,
    "trade_candidate_min_score": 70,
    "trade_volume_dry_min_score": 14,
    "trade_allow_ret50": False,
    "trade_allow_ma5_support": False,
    "volume_dry_ratio_5_20": 0.75,
    "volume_dry_strong_ratio_5_20": 0.65,
    "volume_dry_extreme_ratio_5_20": 0.50,
    "volume_dry_ratio_5_50": 0.70,
    "volume_dry_percentile_60": 0.25,
    "volume_dry_down_volume_ratio_5": 0.60,
    "volume_dry_down_day_avg_ratio_20": 0.90,
    "volume_dry_big_down_return": -0.05,
    "volume_dry_big_down_volume_ratio": 1.30,
    "volume_dry_consecutive_bear_days": 2,
    "volume_dry_close_range_5": 0.06,
    "volume_dry_atr_contract_ratio": 0.85,
    "volume_dry_direction_efficiency": 0.35,
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
    raw.pop("minimum_kline_days", None)
    _validate_int_range(raw, "minimum_trading_days", 260, raw["kline_days"])
    _validate_number_range(raw, "min_avg_amount_60d_yi", 0, 1000)
    _validate_number_range(raw, "min_avg_amount_30d_yi", 0, 1000)
    _validate_number_range(raw, "min_avg_amount_10d_yi", 0, 1000)
    _validate_number_range(raw, "kcb_min_avg_amount_60d_yi", 0, 1000)
    _validate_number_range(raw, "kcb_min_avg_amount_30d_yi", 0, 1000)
    _validate_number_range(raw, "kcb_min_avg_amount_10d_yi", 0, 1000)
    _validate_number_range(raw, "strength_ret_20d", -1, 5)
    _validate_number_range(raw, "strength_ret_10d", -1, 5)
    _validate_number_range(raw, "strength_ret_5d", -1, 5)
    _validate_number_range(raw, "strength_ret_50d", -1, 5)
    _validate_number_range(raw, "strength_ret_50d_min_20d", -1, 5)
    _validate_number_range(raw, "strength_ret_50d_ma20_ratio", 0, 2)
    _validate_number_range(raw, "strength_ret_50d_max_amp_10d", 0, 3)
    _validate_number_range(raw, "strength_ret_50d_max_decline_5d", -1, 0)
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
    _validate_int_range(raw, "volume_dry_min_score_key", 0, 20)
    _validate_int_range(raw, "volume_dry_min_score_watch", 0, raw["volume_dry_min_score_key"])
    _validate_number_range(raw, "trade_candidate_min_score", 0, 100)
    _validate_int_range(raw, "trade_volume_dry_min_score", 0, 20)
    raw["trade_allow_ret50"] = bool(raw.get("trade_allow_ret50", False))
    raw["trade_allow_ma5_support"] = bool(raw.get("trade_allow_ma5_support", False))
    _validate_number_range(raw, "volume_dry_ratio_5_20", 0.1, 2)
    _validate_number_range(raw, "volume_dry_strong_ratio_5_20", 0.1, raw["volume_dry_ratio_5_20"])
    _validate_number_range(raw, "volume_dry_extreme_ratio_5_20", 0.1, raw["volume_dry_strong_ratio_5_20"])
    _validate_number_range(raw, "volume_dry_ratio_5_50", 0.1, 2)
    _validate_number_range(raw, "volume_dry_percentile_60", 0, 1)
    _validate_number_range(raw, "volume_dry_down_volume_ratio_5", 0, 1)
    _validate_number_range(raw, "volume_dry_down_day_avg_ratio_20", 0, 2)
    _validate_number_range(raw, "volume_dry_big_down_return", -1, 0)
    _validate_number_range(raw, "volume_dry_big_down_volume_ratio", 0.5, 5)
    _validate_int_range(raw, "volume_dry_consecutive_bear_days", 1, 5)
    _validate_number_range(raw, "volume_dry_close_range_5", 0, 1)
    _validate_number_range(raw, "volume_dry_atr_contract_ratio", 0, 2)
    _validate_number_range(raw, "volume_dry_direction_efficiency", 0, 1)
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

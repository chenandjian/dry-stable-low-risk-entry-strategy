"""Strategy6 configuration validation."""
from __future__ import annotations

import copy
import hashlib
import json
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
    "market_filter_mode": "downgrade",
    "start_lookback_days": 60,
    "start_age_min_days": 5,
    "start_age_max_days": 60,
    "consolidation_min_days": 5,
    "consolidation_max_days": 40,
    "tail_window_days": 5,
    "pattern_filter_enabled": True,
    "pattern_filter_mode": "score_only",
    "pattern_pivot_proximity_pct": 0.05,
    "breakout_extended_max_pct": 0.08,
    "vcp_contraction_range_ratio": 0.90,
    "vcp_contraction_volume_ratio": 0.90,
    "vcp_min_first_range": 0.08,
    "cup_depth_min": 0.12,
    "cup_depth_max": 0.35,
    "platform_max_range": 0.12,
    "support_cluster_price_pct": 0.015,
    "support_cluster_atr_multiplier": 0.50,
    "support_zone_price_pct": 0.01,
    "support_zone_atr_multiplier": 0.30,
    "support_test_lookback": 10,
    "min_relative_strength_20": 0.10,
    "normal_start_return": 0.07,
    "normal_start_volume_ratio": 2.0,
    "normal_start_close_position": 0.65,
    "normal_start_min_amount_yi": 2,
    "normal_start_self_amount_percentile": 0.90,
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
    "target_2_cap_pct": 0.35,
    "stop_key_support_pct": 0.03,
    "stop_atr_multiplier": 0.8,
    "buy_zone_valid_days": 3,
    "max_watch_days": 10,
    "expired_cooldown_days": 5,
    "failed_cooldown_days": 10,
    "ready_min_score": 85,
    "key_min_score": 75,
    "watch_min_score": 60,
    "box_tail": {
        "enabled": True,
        "min_box_days": 5,
        "max_box_days": 30,
        "premium_box_width_max": 0.12,
        "normal_box_width_max": 0.18,
        "low_test_tolerance_up": 0.02,
        "low_test_close_tolerance_down": 0.02,
        "broken_close_tolerance": 0.03,
        "min_box_low_test_count": 2,
        "min_center_shift": -0.03,
        "premium_center_shift": 0.0,
        "max_volume_contraction_ratio": 0.85,
        "premium_volume_contraction_ratio": 0.70,
        "current_close_low_tolerance": 0.03,
        "current_close_high_tolerance": 0.03,
        "tail_volume_ratio_max": 0.75,
        "premium_tail_volume_ratio_max": 0.60,
        "support_ready_position_max": 0.40,
        "breakout_ready_position_min": 0.75,
        "compact_kline": {
            "enabled": True,
            "window_days": 5,
            "avg_body_ratio_max": 0.025,
            "premium_avg_body_ratio_max": 0.018,
            "max_body_ratio_max": 0.04,
            "close_range_max": 0.05,
            "premium_close_range_max": 0.03,
            "min_overlap_ratio": 0.50,
            "premium_overlap_ratio": 0.65,
            "min_overlap_pair_count": 3,
            "max_gap_ratio": 0.03,
            "atr_contraction_ratio_max": 0.80,
            "premium_atr_contraction_ratio_max": 0.65,
        },
    },
}


def resolve_strategy6_config(config: dict | None) -> dict:
    config = config or {}
    raw = copy.deepcopy(DEFAULT_STRATEGY6_CONFIG)
    overrides = config.get("strategy6") if "strategy6" in config else config
    if overrides:
        for key, value in overrides.items():
            if key not in raw:
                continue
            if key == "box_tail" and isinstance(value, dict):
                compact_override = value.get("compact_kline")
                raw["box_tail"].update({
                    nested_key: nested_value
                    for nested_key, nested_value in value.items()
                    if nested_key in raw["box_tail"] and nested_key != "compact_kline"
                })
                if isinstance(compact_override, dict):
                    raw["box_tail"]["compact_kline"].update({
                        nested_key: nested_value
                        for nested_key, nested_value in compact_override.items()
                        if nested_key in raw["box_tail"]["compact_kline"]
                    })
            else:
                raw[key] = value

    raw["enabled"] = bool(raw.get("enabled", True))
    _validate_int_range(raw, "kline_days", 260, 3000)
    _validate_int_range(raw, "minimum_trading_days", 260, raw["kline_days"])
    _validate_int_range(raw, "start_lookback_days", 20, 250)
    _validate_int_range(raw, "start_age_min_days", 1, 20)
    _validate_int_range(raw, "start_age_max_days", raw["start_age_min_days"], raw["start_lookback_days"])
    _validate_int_range(raw, "consolidation_min_days", 1, 40)
    _validate_int_range(raw, "consolidation_max_days", raw["consolidation_min_days"], 120)
    _validate_int_range(raw, "tail_window_days", 3, 10)
    _validate_int_range(raw, "support_test_lookback", 5, 40)
    _validate_int_range(raw, "buy_zone_valid_days", 1, 10)
    _validate_int_range(raw, "max_watch_days", 1, 60)
    _validate_int_range(raw, "expired_cooldown_days", 1, 30)
    _validate_int_range(raw, "failed_cooldown_days", 1, 60)
    for key in (
        "min_avg_amount_60d_yi", "min_avg_amount_30d_yi", "min_avg_amount_10d_yi",
        "amount10_vs_30_min_ratio", "normal_start_return", "normal_start_volume_ratio",
        "normal_start_close_position", "normal_start_min_amount_yi", "normal_start_self_amount_percentile", "limit_up_volume_ratio",
        "low_volume_limit_up_min_ratio", "near_120d_high_ratio", "min_relative_strength_20", "max_amp_5d_s",
        "max_amp_10d_s", "max_amp_5d_a", "max_amp_10d_a", "max_amp_5d_b",
        "max_amp_10d_b", "absolute_max_amp_10d", "ma50_min_ratio",
        "tail_close_range_5", "tail_volume_ratio_5_20", "tail_strong_volume_ratio_5_20",
        "big_down_volume_ratio", "rr2_min_watch", "rr2_min_key", "rr2_min_ready",
        "target_2_cap_pct", "stop_key_support_pct", "stop_atr_multiplier",
        "vcp_contraction_range_ratio", "vcp_contraction_volume_ratio",
        "vcp_min_first_range", "cup_depth_min", "cup_depth_max", "platform_max_range",
        "pattern_pivot_proximity_pct",
        "breakout_extended_max_pct",
        "support_cluster_price_pct", "support_cluster_atr_multiplier",
        "support_zone_price_pct", "support_zone_atr_multiplier",
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
    if raw.get("market_filter_mode") not in {"strict", "downgrade", "score_only"}:
        raise ValueError("market_filter_mode must be one of strict/downgrade/score_only")
    raw["pattern_filter_enabled"] = bool(raw.get("pattern_filter_enabled", True))
    if raw.get("pattern_filter_mode") not in {"strict", "downgrade", "score_only"}:
        raise ValueError("pattern_filter_mode must be one of strict/downgrade/score_only")
    _validate_between(raw, "normal_start_self_amount_percentile", 0, 1)
    _validate_between(raw, "vcp_contraction_range_ratio", 0, 1)
    _validate_between(raw, "vcp_contraction_volume_ratio", 0, 1)
    _validate_between(raw, "cup_depth_min", 0, 1)
    _validate_between(raw, "cup_depth_max", raw["cup_depth_min"], 1)
    _validate_between(raw, "platform_max_range", 0, 1)
    _validate_between(raw, "pattern_pivot_proximity_pct", 0, 0.20, lower_exclusive=True)
    _validate_between(raw, "breakout_extended_max_pct", 0, 0.30, lower_exclusive=True)
    _validate_between(raw, "tail_volume_ratio_5_20", 0, 2, lower_exclusive=True)
    _validate_between(raw, "tail_strong_volume_ratio_5_20", 0, raw["tail_volume_ratio_5_20"], lower_exclusive=True)
    if not raw["rr2_min_watch"] <= raw["rr2_min_key"] <= raw["rr2_min_ready"]:
        raise ValueError("rr2 thresholds must satisfy watch <= key <= ready")
    if not raw["watch_min_score"] <= raw["key_min_score"] <= raw["ready_min_score"]:
        raise ValueError("score thresholds must satisfy watch <= key <= ready")
    _validate_box_tail_config(raw["box_tail"])
    return raw


def strategy6_config_hash(config: dict) -> str:
    payload = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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


def _validate_between(
    config: dict,
    key: str,
    min_v: float,
    max_v: float,
    *,
    lower_exclusive: bool = False,
) -> None:
    _validate_number(config, key)
    value = config[key]
    lower_invalid = value <= min_v if lower_exclusive else value < min_v
    if lower_invalid or value > max_v:
        bracket = "(" if lower_exclusive else "["
        raise ValueError(f"{key} must be in {bracket}{min_v}, {max_v}]")


def _validate_box_tail_config(config: dict) -> None:
    config["enabled"] = bool(config.get("enabled", True))
    _validate_int_range(config, "min_box_days", 5, 30)
    _validate_int_range(config, "max_box_days", config["min_box_days"], 30)
    _validate_int_range(config, "min_box_low_test_count", 1, 10)
    for key in (
        "premium_box_width_max", "normal_box_width_max",
        "low_test_tolerance_up", "low_test_close_tolerance_down",
        "broken_close_tolerance", "min_center_shift", "premium_center_shift",
        "max_volume_contraction_ratio", "premium_volume_contraction_ratio",
        "current_close_low_tolerance", "current_close_high_tolerance",
        "tail_volume_ratio_max", "premium_tail_volume_ratio_max",
        "support_ready_position_max", "breakout_ready_position_min",
    ):
        _validate_number(config, key)
    for key in (
        "premium_box_width_max", "normal_box_width_max",
        "low_test_tolerance_up", "low_test_close_tolerance_down",
        "broken_close_tolerance", "current_close_low_tolerance",
        "current_close_high_tolerance", "support_ready_position_max",
        "breakout_ready_position_min",
    ):
        _validate_between(config, key, 0, 1)
    _validate_between(config, "min_center_shift", -1, 1)
    _validate_between(config, "premium_center_shift", -1, 1)
    for key in (
        "max_volume_contraction_ratio", "premium_volume_contraction_ratio",
        "tail_volume_ratio_max", "premium_tail_volume_ratio_max",
    ):
        _validate_between(config, key, 0, 2, lower_exclusive=True)
    if config["premium_box_width_max"] > config["normal_box_width_max"]:
        raise ValueError("premium_box_width_max must be <= normal_box_width_max")
    if config["premium_volume_contraction_ratio"] > config["max_volume_contraction_ratio"]:
        raise ValueError("premium_volume_contraction_ratio must be <= max_volume_contraction_ratio")
    if config["premium_tail_volume_ratio_max"] > config["tail_volume_ratio_max"]:
        raise ValueError("premium_tail_volume_ratio_max must be <= tail_volume_ratio_max")
    if config["support_ready_position_max"] >= config["breakout_ready_position_min"]:
        raise ValueError("support_ready_position_max must be < breakout_ready_position_min")

    compact = config["compact_kline"]
    compact["enabled"] = bool(compact.get("enabled", True))
    _validate_int_range(compact, "window_days", 3, 10)
    _validate_int_range(compact, "min_overlap_pair_count", 1, compact["window_days"] - 1)
    for key in (
        "avg_body_ratio_max", "premium_avg_body_ratio_max", "max_body_ratio_max",
        "close_range_max", "premium_close_range_max", "min_overlap_ratio",
        "premium_overlap_ratio", "max_gap_ratio", "atr_contraction_ratio_max",
        "premium_atr_contraction_ratio_max",
    ):
        _validate_between(compact, key, 0, 2)
    if compact["premium_avg_body_ratio_max"] > compact["avg_body_ratio_max"]:
        raise ValueError("premium_avg_body_ratio_max must be <= avg_body_ratio_max")
    if compact["premium_close_range_max"] > compact["close_range_max"]:
        raise ValueError("premium_close_range_max must be <= close_range_max")
    if compact["premium_overlap_ratio"] < compact["min_overlap_ratio"]:
        raise ValueError("premium_overlap_ratio must be >= min_overlap_ratio")
    if compact["premium_atr_contraction_ratio_max"] > compact["atr_contraction_ratio_max"]:
        raise ValueError("premium_atr_contraction_ratio_max must be <= atr_contraction_ratio_max")

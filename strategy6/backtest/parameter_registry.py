"""Typed, staged parameter registry for Strategy6 comprehensive research."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable

from strategy6.validation import resolve_strategy6_config


@dataclass(frozen=True)
class ParameterSpec:
    key: str
    default: Any
    candidates: tuple[Any, ...]
    value_type: str
    description: str = ""
    apply: Callable[[dict, Any], None] | None = None


@dataclass(frozen=True)
class StageSpec:
    stage_id: str
    order: int
    name: str
    parameters: tuple[ParameterSpec, ...]


_GRADE_KEYS = (
    "max_amp_5d_s", "max_amp_10d_s", "max_pullback_20d_s",
    "max_amp_5d_a", "max_amp_10d_a", "max_pullback_20d_a",
    "max_amp_5d_b", "max_amp_10d_b", "max_pullback_20d_b",
)


def _get_nested(config: dict, dotted_key: str) -> Any:
    value: Any = config
    for part in dotted_key.split("."):
        value = value[part]
    return value


def _set_nested(config: dict, dotted_key: str, value: Any) -> None:
    parts = dotted_key.split(".")
    current = config
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


def _value_type(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    return "string"


def _spec(config: dict, key: str, candidates: tuple[Any, ...], description: str = "") -> ParameterSpec:
    default = _get_nested(config, key)
    return ParameterSpec(key, default, candidates, _value_type(default), description)


def _apply_grade_profile(config: dict, profile: str) -> None:
    factor = {"default": 1.0, "strict_5": 0.95, "strict_10": 0.90}.get(profile)
    if factor is None:
        raise ValueError(f"unsupported grade risk profile: {profile}")
    if profile == "default":
        return
    for key in _GRADE_KEYS:
        config[key] = round(float(config[key]) * factor, 6)


def apply_parameter_value(config: dict, spec: ParameterSpec, value: Any) -> None:
    if value not in spec.candidates:
        raise ValueError(f"{value!r} is not a candidate for {spec.key}")
    if spec.apply is not None:
        spec.apply(config, value)
    else:
        _set_nested(config, spec.key, value)


def compact_overlap_candidates(window_days: int) -> tuple[int, ...]:
    if window_days < 3:
        raise ValueError("compact window must be at least 3 days")
    minimum = max(1, window_days // 2)
    return tuple(range(minimum, window_days))


def build_comprehensive_registry(production_config: dict) -> tuple[StageSpec, ...]:
    config = resolve_strategy6_config({"strategy6": copy.deepcopy(production_config)})
    grade = ParameterSpec(
        key="grade_risk_profile",
        default="default",
        candidates=("default", "strict_5", "strict_10"),
        value_type="group",
        description="S/A/B amplitude and pullback thresholds move together",
        apply=_apply_grade_profile,
    )
    stages = (
        StageSpec("liquidity_rs", 1, "流动性与相对强度", (
            _spec(config, "min_avg_amount_60d_yi", (2, 3, 4, 5)),
            _spec(config, "min_avg_amount_30d_yi", (3, 5, 7, 10)),
            _spec(config, "min_avg_amount_10d_yi", (3, 5, 7, 10)),
            _spec(config, "amount10_vs_30_min_ratio", (0.70, 0.80, 0.90, 1.00)),
            _spec(config, "min_relative_strength_20", (0.00, 0.05, 0.10, 0.15)),
            _spec(config, "ma50_min_ratio", (0.90, 0.92, 0.95, 0.98)),
        )),
        StageSpec("strong_start", 2, "强势启动与有效年龄", (
            _spec(config, "start_lookback_days", (40, 60, 80)),
            _spec(config, "start_age_min_days", (3, 5, 8)),
            _spec(config, "start_age_max_days", (40, 50, 60, 80)),
            _spec(config, "normal_start_return", (0.06, 0.07, 0.08, 0.09)),
            _spec(config, "normal_start_volume_ratio", (1.5, 2.0, 2.5, 3.0)),
            _spec(config, "normal_start_close_position", (0.60, 0.65, 0.70, 0.75)),
            _spec(config, "normal_start_min_amount_yi", (2, 3, 5)),
            _spec(config, "normal_start_self_amount_percentile", (0.80, 0.85, 0.90, 0.95)),
            _spec(config, "limit_up_volume_ratio", (1.2, 1.5, 2.0)),
            _spec(config, "low_volume_limit_up_min_ratio", (0.50, 0.60, 0.75)),
            _spec(config, "near_120d_high_ratio", (0.95, 0.98, 1.00)),
        )),
        StageSpec("pattern", 3, "形态", (
            _spec(config, "pattern_pivot_proximity_pct", (0.03, 0.05, 0.07)),
            _spec(config, "vcp_contraction_range_ratio", (0.75, 0.85, 0.90, 0.95)),
            _spec(config, "vcp_contraction_volume_ratio", (0.75, 0.85, 0.90, 0.95)),
            _spec(config, "vcp_min_first_range", (0.06, 0.08, 0.10, 0.12)),
            _spec(config, "cup_depth_min", (0.10, 0.12, 0.15)),
            _spec(config, "cup_depth_max", (0.30, 0.35, 0.40)),
            _spec(config, "platform_max_range", (0.08, 0.10, 0.12, 0.15)),
        )),
        StageSpec("support_risk", 4, "支撑、振幅和回撤", (
            _spec(config, "support_cluster_price_pct", (0.010, 0.015, 0.020)),
            _spec(config, "support_cluster_atr_multiplier", (0.3, 0.5, 0.8)),
            _spec(config, "support_zone_price_pct", (0.005, 0.010, 0.015)),
            _spec(config, "support_zone_atr_multiplier", (0.2, 0.3, 0.5)),
            _spec(config, "support_test_lookback", (5, 10, 15, 20)),
            grade,
            _spec(config, "absolute_max_amp_10d", (0.40, 0.45, 0.50)),
            _spec(config, "absolute_max_pullback_20d", (-0.25, -0.30, -0.35)),
        )),
        StageSpec("dry_tail", 5, "原尾部量干价稳", (
            _spec(config, "tail_window_days", (3, 5, 7, 10)),
            _spec(config, "tail_close_range_5", (0.04, 0.06, 0.08, 0.10)),
            _spec(config, "tail_volume_ratio_5_20", (0.55, 0.65, 0.75, 0.85)),
            _spec(config, "tail_strong_volume_ratio_5_20", (0.45, 0.55, 0.60, 0.70)),
            _spec(config, "tail_min_return_5", (-0.03, -0.05, -0.06, -0.08)),
            _spec(config, "tail_min_return_3", (-0.02, -0.03, -0.04, -0.05)),
            _spec(config, "big_down_return", (-0.05, -0.06, -0.07)),
            _spec(config, "big_down_volume_ratio", (1.2, 1.5, 2.0)),
        )),
        StageSpec("box_compact", 6, "箱体与紧密K线", (
            _spec(config, "box_tail.min_box_days", (5, 7, 10)),
            _spec(config, "box_tail.max_box_days", (20, 25, 30)),
            _spec(config, "box_tail.normal_box_width_max", (0.12, 0.15, 0.18, 0.20)),
            _spec(config, "box_tail.min_box_low_test_count", (2, 3)),
            _spec(config, "box_tail.min_center_shift", (-0.01, -0.02, -0.03)),
            _spec(config, "box_tail.max_volume_contraction_ratio", (0.70, 0.80, 0.85, 0.90)),
            _spec(config, "box_tail.tail_volume_ratio_max", (0.60, 0.70, 0.75, 0.80)),
            _spec(config, "box_tail.current_close_low_tolerance", (0.02, 0.03, 0.05)),
            _spec(config, "box_tail.current_close_high_tolerance", (0.02, 0.03, 0.05)),
            _spec(config, "box_tail.broken_close_tolerance", (0.02, 0.03, 0.05)),
            _spec(config, "box_tail.compact_kline.window_days", (3, 5, 7)),
            _spec(config, "box_tail.compact_kline.avg_body_ratio_max", (0.018, 0.025, 0.035)),
            _spec(config, "box_tail.compact_kline.max_body_ratio_max", (0.03, 0.04, 0.05)),
            _spec(config, "box_tail.compact_kline.close_range_max", (0.03, 0.05, 0.07)),
            _spec(config, "box_tail.compact_kline.min_overlap_ratio", (0.40, 0.50, 0.60)),
            _spec(config, "box_tail.compact_kline.min_overlap_pair_count", (1, 2, 3, 4, 5, 6)),
            _spec(config, "box_tail.compact_kline.max_gap_ratio", (0.02, 0.03, 0.05)),
            _spec(config, "box_tail.compact_kline.atr_contraction_ratio_max", (0.65, 0.80, 0.95)),
        )),
        StageSpec("score_trade_plan", 7, "评分、盈亏比和交易计划", (
            _spec(config, "watch_min_score", (60, 65, 70)),
            _spec(config, "key_min_score", (70, 75, 80)),
            _spec(config, "ready_min_score", (80, 85, 90)),
            _spec(config, "rr2_min_watch", (1.5, 2.0, 2.5)),
            _spec(config, "rr2_min_key", (2.0, 2.5, 3.0)),
            _spec(config, "rr2_min_ready", (2.5, 3.0, 3.5)),
            _spec(config, "stop_key_support_pct", (0.02, 0.03, 0.04)),
            _spec(config, "stop_atr_multiplier", (0.6, 0.8, 1.0, 1.2)),
            _spec(config, "target_2_cap_pct", (0.25, 0.35, 0.45)),
        )),
    )
    return stages


def validate_stage_combination(config: dict) -> dict:
    amount60 = float(config["min_avg_amount_60d_yi"])
    amount30 = float(config["min_avg_amount_30d_yi"])
    amount10 = float(config["min_avg_amount_10d_yi"])
    if not amount60 <= amount30 <= amount10:
        raise ValueError("amount thresholds must satisfy 60d <= 30d <= 10d")
    if int(config["start_age_min_days"]) >= int(config["start_age_max_days"]):
        raise ValueError("start age thresholds must satisfy min < max")
    if float(config["low_volume_limit_up_min_ratio"]) >= float(config["limit_up_volume_ratio"]):
        raise ValueError("limit-up volume thresholds must satisfy low-volume < normal")
    if float(config["cup_depth_min"]) >= float(config["cup_depth_max"]):
        raise ValueError("cup depth thresholds must satisfy min < max")
    if float(config["tail_strong_volume_ratio_5_20"]) > float(config["tail_volume_ratio_5_20"]):
        raise ValueError("tail volume strong threshold must not exceed normal threshold")
    if float(config["tail_min_return_3"]) < float(config["tail_min_return_5"]):
        raise ValueError("tail return thresholds must satisfy 3d floor >= 5d floor")
    if not float(config["watch_min_score"]) < float(config["key_min_score"]) < float(config["ready_min_score"]):
        raise ValueError("score thresholds must strictly increase")
    if not float(config["rr2_min_watch"]) < float(config["rr2_min_key"]) < float(config["rr2_min_ready"]):
        raise ValueError("risk-reward thresholds must strictly increase")
    compact = config["box_tail"]["compact_kline"]
    if int(compact["min_overlap_pair_count"]) not in compact_overlap_candidates(int(compact["window_days"])):
        raise ValueError("overlap pair count is invalid for compact window")
    return resolve_strategy6_config({"strategy6": config})

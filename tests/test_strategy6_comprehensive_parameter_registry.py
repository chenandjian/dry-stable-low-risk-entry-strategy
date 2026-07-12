import copy

import pytest

from strategy6.validation import DEFAULT_STRATEGY6_CONFIG


def _registry():
    from strategy6.backtest.parameter_registry import build_comprehensive_registry

    return build_comprehensive_registry(DEFAULT_STRATEGY6_CONFIG)


def test_comprehensive_registry_has_seven_ordered_stages_and_expected_parameters():
    registry = _registry()

    assert [stage.stage_id for stage in registry] == [
        "liquidity_rs",
        "strong_start",
        "pattern",
        "support_risk",
        "dry_tail",
        "box_compact",
        "score_trade_plan",
    ]
    assert [stage.order for stage in registry] == list(range(1, 8))

    keys = {spec.key for stage in registry for spec in stage.parameters}
    assert {
        "min_avg_amount_60d_yi",
        "min_relative_strength_20",
        "start_age_min_days",
        "normal_start_volume_ratio",
        "cup_depth_min",
        "support_cluster_price_pct",
        "grade_risk_profile",
        "tail_volume_ratio_5_20",
        "box_tail.normal_box_width_max",
        "box_tail.compact_kline.window_days",
        "ready_min_score",
        "rr2_min_ready",
        "target_2_cap_pct",
    } <= keys

    normal_start = next(spec for stage in registry for spec in stage.parameters if spec.key == "normal_start_return")
    assert normal_start.default == DEFAULT_STRATEGY6_CONFIG["normal_start_return"]
    assert normal_start.candidates == (0.06, 0.07, 0.08, 0.09)
    assert normal_start.value_type == "float"


def test_comprehensive_registry_excludes_fixed_system_and_semantic_parameters():
    keys = {spec.key for stage in _registry() for spec in stage.parameters}

    assert keys.isdisjoint({
        "enabled",
        "kline_days",
        "minimum_trading_days",
        "enable_market_filter",
        "market_filter_mode",
        "pattern_filter_enabled",
        "pattern_filter_mode",
        "max_watch_days",
        "expired_cooldown_days",
        "failed_cooldown_days",
    })


def test_grade_risk_profile_changes_all_grade_thresholds_as_one_unit():
    from strategy6.backtest.parameter_registry import apply_parameter_value

    registry = _registry()
    spec = next(spec for stage in registry for spec in stage.parameters if spec.key == "grade_risk_profile")
    config = copy.deepcopy(DEFAULT_STRATEGY6_CONFIG)

    apply_parameter_value(config, spec, "strict_10")

    assert config["max_amp_5d_s"] == pytest.approx(0.225)
    assert config["max_amp_10d_a"] == pytest.approx(0.36)
    assert config["max_pullback_20d_b"] == pytest.approx(-0.198)
    assert config["absolute_max_amp_10d"] == DEFAULT_STRATEGY6_CONFIG["absolute_max_amp_10d"]


def test_grade_risk_profile_perturbs_the_frozen_parent_config_not_global_defaults():
    from strategy6.backtest.parameter_registry import apply_parameter_value

    spec = next(spec for stage in _registry() for spec in stage.parameters if spec.key == "grade_risk_profile")
    config = copy.deepcopy(DEFAULT_STRATEGY6_CONFIG)
    config["max_amp_5d_s"] = 0.20
    config["max_pullback_20d_b"] = -0.18

    apply_parameter_value(config, spec, "strict_5")

    assert config["max_amp_5d_s"] == pytest.approx(0.19)
    assert config["max_pullback_20d_b"] == pytest.approx(-0.171)


def test_compact_overlap_candidates_are_legal_for_each_window():
    from strategy6.backtest.parameter_registry import compact_overlap_candidates

    assert compact_overlap_candidates(3) == (1, 2)
    assert compact_overlap_candidates(5) == (2, 3, 4)
    assert compact_overlap_candidates(7) == (3, 4, 5, 6)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"min_avg_amount_60d_yi": 6, "min_avg_amount_30d_yi": 5}, "amount thresholds"),
        ({"start_age_min_days": 8, "start_age_max_days": 5}, "start age"),
        ({"low_volume_limit_up_min_ratio": 1.5, "limit_up_volume_ratio": 1.5}, "limit-up volume"),
        ({"cup_depth_min": 0.35, "cup_depth_max": 0.30}, "cup depth"),
        ({"tail_strong_volume_ratio_5_20": 0.80, "tail_volume_ratio_5_20": 0.75}, "tail volume"),
        ({"tail_min_return_3": -0.08, "tail_min_return_5": -0.06}, "tail return"),
        ({"watch_min_score": 75, "key_min_score": 75, "ready_min_score": 85}, "score thresholds"),
        ({"rr2_min_watch": 2.0, "rr2_min_key": 2.0, "rr2_min_ready": 3.0}, "risk-reward thresholds"),
    ],
)
def test_stage_combination_rejects_invalid_linked_thresholds(updates, message):
    from strategy6.backtest.parameter_registry import validate_stage_combination

    config = copy.deepcopy(DEFAULT_STRATEGY6_CONFIG)
    config.update(updates)
    with pytest.raises(ValueError, match=message):
        validate_stage_combination(config)


def test_stage_combination_rejects_compact_overlap_outside_selected_window():
    from strategy6.backtest.parameter_registry import validate_stage_combination

    config = copy.deepcopy(DEFAULT_STRATEGY6_CONFIG)
    config["box_tail"]["compact_kline"].update({"window_days": 3, "min_overlap_pair_count": 3})

    with pytest.raises(ValueError, match="overlap pair count"):
        validate_stage_combination(config)

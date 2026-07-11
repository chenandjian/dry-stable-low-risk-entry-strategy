import importlib.util
from importlib import import_module

from strategy6.box_tail import (
    calculate_kline_overlap_ratio,
    count_independent_box_high_tests,
    count_independent_box_low_tests,
    evaluate_box_tail,
)
from strategy6.models import Strategy6DryTail, Strategy6Phase, Strategy6Support


def test_strategy6_box_tail_is_an_independent_module():
    assert importlib.util.find_spec("strategy6.box_tail") is not None


def test_box_tail_module_exposes_pure_calculation_entry_points():
    module = import_module("strategy6.box_tail")

    assert callable(getattr(module, "evaluate_box_tail", None))
    assert callable(getattr(module, "evaluate_compact_kline", None))
    assert callable(getattr(module, "count_independent_box_low_tests", None))
    assert callable(getattr(module, "count_independent_box_high_tests", None))
    assert callable(getattr(module, "calculate_kline_overlap_ratio", None))


BOX_CONFIG = {
    "low_test_tolerance_up": 0.02,
    "low_test_close_tolerance_down": 0.02,
}


def test_consecutive_box_low_tests_are_deduplicated_until_two_full_days_separate_them():
    rows = [
        {"low": 9.95, "high": 10.4, "close": 10.00},
        {"low": 9.98, "high": 10.4, "close": 10.03},
        {"low": 10.30, "high": 10.5, "close": 10.40},
        {"low": 9.97, "high": 10.4, "close": 10.02},
    ]

    assert count_independent_box_low_tests(rows, 10.0, BOX_CONFIG) == 2


def test_box_high_tests_use_symmetric_tolerance_and_same_deduplication():
    rows = [
        {"low": 10.0, "high": 10.95, "close": 10.90},
        {"low": 10.1, "high": 10.98, "close": 10.92},
        {"low": 10.0, "high": 10.4, "close": 10.2},
        {"low": 10.1, "high": 10.99, "close": 10.95},
    ]

    assert count_independent_box_high_tests(rows, 11.0, BOX_CONFIG) == 2


def test_kline_overlap_ratio_uses_the_smaller_daily_range():
    previous = {"low": 9.8, "high": 10.2}
    current = {"low": 9.9, "high": 10.1}

    assert calculate_kline_overlap_ratio(previous, current) == 1.0
    assert calculate_kline_overlap_ratio({"low": 10, "high": 10}, current) is None


def _daily_row(index, close, volume=1_000_000):
    return {
        "date": f"2026-01-{index + 1:02d}",
        "open": close * 0.998,
        "high": close * 1.008,
        "low": close * 0.992,
        "close": close,
        "volume": volume,
    }


def _box_rows():
    history = [_daily_row(index, 9.0 + index * 0.03, 1_200_000) for index in range(20)]
    closes = [10.0, 10.5, 10.2, 10.05, 10.45, 10.2, 10.1, 10.4, 10.25, 10.35, 10.30, 10.32]
    volumes = [1_000_000] * 5 + [650_000] * 7
    box = [_daily_row(20 + index, close, volumes[index]) for index, close in enumerate(closes)]
    return history + box


def _box_config(*, enabled=True, compact_enabled=True):
    return {
        "enabled": enabled,
        "min_box_days": 12,
        "max_box_days": 12,
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
            "enabled": compact_enabled,
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
    }


def _phase(rows):
    return Strategy6Phase(
        status="PHASE_VALID",
        valid=True,
        start_index=19,
        consolidation_start_index=20,
        tail_start_index=len(rows) - 5,
        signal_index=len(rows) - 1,
        start_date=rows[19]["date"],
        consolidation_start_date=rows[20]["date"],
        signal_date=rows[-1]["date"],
    )


def _support():
    return Strategy6Support(
        support_status="KEY_SUPPORT_VALID",
        key_support_price=9.8,
        support_zone_low=9.7,
        support_zone_high=10.6,
    )


def _original_tail():
    return Strategy6DryTail(
        dry_stable_score=10,
        dry_tail_pass=False,
        tail_volume_ratio=0.55,
        volume_slope_10=-0.08,
        rejects=["TAIL_CLOSE_RANGE_GT_8PCT"],
    )


def test_stable_box_passes_and_reports_confirmed_boundaries_metrics_and_quality():
    rows = _box_rows()

    result = evaluate_box_tail(
        rows, _phase(rows), _support(), _original_tail(),
        has_volume_selloff=False,
        config=_box_config(),
    )

    assert result.passed is True
    assert result.status in {"BOX_SUPPORT_READY", "BOX_STABLE", "BOX_BREAKOUT_READY"}
    assert result.days == 12
    assert result.start_date == rows[-12]["date"]
    assert result.end_date == rows[-1]["date"]
    assert result.box_low == 10.0
    assert result.box_high == 10.5
    assert result.low_test_count >= 2
    assert result.volume_contraction_ratio <= 0.70
    assert result.score >= 16
    assert result.quality_score == result.score + result.compact_kline.score


def test_box_tail_rejects_when_non_overlapping_volume_baseline_is_insufficient():
    rows = _box_rows()
    original_tail = Strategy6DryTail(
        dry_stable_score=0,
        dry_tail_pass=False,
        tail_volume_ratio=0.0,
        rejects=["TAIL_VOLUME_BASE_INSUFFICIENT"],
    )

    result = evaluate_box_tail(
        rows, _phase(rows), _support(), original_tail,
        has_volume_selloff=False,
        config=_box_config(),
    )

    assert result.passed is False
    assert result.score == 0
    assert result.status == "NO_BOX"
    assert "BOX_TAIL_VOLUME_BASE_INSUFFICIENT" in result.risk_tags


def test_box_boundaries_exclude_last_two_days_so_real_break_can_be_detected():
    rows = _box_rows()
    for index, close in ((-2, 9.9), (-1, 9.6)):
        rows[index].update({
            "open": close * 1.01,
            "high": close * 1.02,
            "low": close * 0.99,
            "close": close,
        })

    result = evaluate_box_tail(
        rows, _phase(rows), _support(), _original_tail(),
        has_volume_selloff=False,
        config=_box_config(),
    )

    assert result.box_low == 10.0
    assert result.passed is False
    assert result.status == "BOX_BROKEN"
    assert result.break_reason in {"CLOSE_BELOW_BOX_LOW_TOLERANCE", "TWO_CLOSES_BELOW_BOX_LOW"}


def test_compact_kline_failure_does_not_force_stable_box_to_fail():
    rows = _box_rows()
    rows[-1]["open"] = rows[-1]["close"] * 0.94
    rows[-1]["low"] = rows[-1]["open"] * 0.99

    result = evaluate_box_tail(
        rows, _phase(rows), _support(), _original_tail(),
        has_volume_selloff=False,
        config=_box_config(),
    )

    assert result.compact_kline.passed is False
    assert result.passed is True
    assert result.quality_tag == "NONE"


def test_disabled_box_tail_returns_no_box_without_scanning():
    rows = _box_rows()

    result = evaluate_box_tail(
        rows, _phase(rows), _support(), _original_tail(),
        has_volume_selloff=False,
        config=_box_config(enabled=False),
    )

    assert result.enabled is False
    assert result.passed is False
    assert result.status == "NO_BOX"
    assert result.score == 0


def test_box_width_above_normal_limit_is_forming_not_passed():
    rows = _box_rows()
    rows[-11]["close"] = 12.0
    rows[-11]["high"] = 12.1
    rows[-11]["low"] = 11.9

    result = evaluate_box_tail(
        rows, _phase(rows), _support(), _original_tail(),
        has_volume_selloff=False,
        config=_box_config(),
    )

    assert result.passed is False
    assert result.status == "BOX_FORMING"
    assert "BOX_WIDTH_TOO_WIDE" in result.risk_tags


def test_box_with_only_one_independent_low_test_is_forming():
    rows = _box_rows()
    for row in rows[-11:-2]:
        row["low"] = max(row["low"], 10.30)
    rows[-12]["low"] = 9.95

    result = evaluate_box_tail(
        rows, _phase(rows), _support(), _original_tail(),
        has_volume_selloff=False,
        config=_box_config(),
    )

    assert result.low_test_count == 1
    assert result.passed is False
    assert "BOX_LOW_TESTS_INSUFFICIENT" in result.risk_tags


def test_box_center_shift_below_floor_is_rejected():
    rows = _box_rows()
    for offset in range(-7, -2):
        rows[offset]["close"] *= 0.94
        rows[offset]["open"] = rows[offset]["close"] * 0.998
        rows[offset]["high"] = rows[offset]["close"] * 1.008
        rows[offset]["low"] = rows[offset]["close"] * 0.992

    result = evaluate_box_tail(
        rows, _phase(rows), _support(), _original_tail(),
        has_volume_selloff=False,
        config=_box_config(),
    )

    assert result.center_shift < -0.03
    assert result.passed is False
    assert "BOX_CENTER_SHIFT_TOO_WEAK" in result.risk_tags


def test_box_second_half_volume_expansion_is_rejected():
    rows = _box_rows()
    for row in rows[-7:-2]:
        row["volume"] = 1_200_000

    result = evaluate_box_tail(
        rows, _phase(rows), _support(), _original_tail(),
        has_volume_selloff=False,
        config=_box_config(),
    )

    assert result.volume_contraction_ratio > 1.0
    assert result.passed is False
    assert "BOX_VOLUME_NOT_CONTRACTED" in result.risk_tags


def test_compact_disabled_does_not_change_box_pass_or_score():
    rows = _box_rows()
    enabled = evaluate_box_tail(
        rows, _phase(rows), _support(), _original_tail(),
        has_volume_selloff=False,
        config=_box_config(compact_enabled=True),
    )
    disabled = evaluate_box_tail(
        rows, _phase(rows), _support(), _original_tail(),
        has_volume_selloff=False,
        config=_box_config(compact_enabled=False),
    )

    assert disabled.passed == enabled.passed
    assert disabled.score == enabled.score
    assert disabled.compact_kline.enabled is False
    assert disabled.compact_kline.score == 0

from datetime import date, timedelta

from strategy6.models import (
    Strategy6DryTail,
    Strategy6Indicators,
    Strategy6Phase,
    Strategy6Start,
    Strategy6Support,
    Strategy6TradePlan,
)
from strategy6.pattern import _best_vcp_chain, detect_pattern
from strategy6.scorer import score_strategy6
from strategy6.validation import resolve_strategy6_config


def _rows(closes, volumes):
    return [
        {
            "date": (date(2026, 1, 1) + timedelta(days=i)).isoformat(),
            "open": close * 0.995,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": volumes[i],
            "amount": 600_000_000,
        }
        for i, close in enumerate(closes)
    ]


def _phase(rows, start_index=0):
    return Strategy6Phase(
        status="PHASE_VALID",
        valid=True,
        start_index=start_index,
        consolidation_start_index=start_index + 1,
        tail_start_index=len(rows) - 5,
        signal_index=len(rows) - 1,
        start_date=rows[start_index]["date"],
        consolidation_start_date=rows[start_index + 1]["date"],
        tail_start_date=rows[-5]["date"],
        signal_date=rows[-1]["date"],
    )


def test_detects_vcp_from_two_contracting_price_and_volume_segments():
    closes = [100]
    closes += [108, 96, 106, 97, 105, 98, 104, 99, 103, 100]
    closes += [103, 99.5, 102.5, 100, 102, 100.5, 102, 101, 102, 101.5]
    volumes = [2_500_000] + [2_000_000 * (0.80 ** (i // 2)) for i in range(20)]
    rows = _rows(closes, volumes)

    pattern = detect_pattern(rows, _phase(rows), resolve_strategy6_config({}))

    assert pattern.pattern_type == "VCP"
    assert pattern.pattern_score > 0
    assert pattern.pivot_source == "VCP_LAST_CONTRACTION"
    assert pattern.pivot_price > pattern.pattern_low
    assert pattern.pattern_height > 0
    assert pattern.contraction_count >= 2
    assert pattern.pattern_start_date < pattern.pattern_end_date
    assert pattern.pattern_end_date < rows[-5]["date"]


def test_detects_cup_handle_with_recovered_right_side_and_shallow_handle():
    cup = [100, 98, 92, 84, 78, 76, 80, 85, 90, 95, 98, 97, 96, 97, 98, 98.5]
    closes = [90] + cup + [98.0, 98.1, 98.2, 98.3, 98.4]
    volumes = [2_500_000] + [2_000_000] * 11 + [900_000, 820_000, 760_000, 700_000, 650_000] + [600_000] * 5
    rows = _rows(closes, volumes)

    pattern = detect_pattern(rows, _phase(rows), resolve_strategy6_config({}))

    assert pattern.pattern_type == "CUP_HANDLE"
    assert pattern.pivot_source == "CUP_HANDLE_PIVOT"
    assert 0.12 <= pattern.depth_pct <= 0.35


def test_detects_platform_when_range_is_tight_and_lows_do_not_fall():
    closes = [100, 101, 100.5, 102, 101.5, 102.5, 102, 103, 102.7, 103.2, 103.0]
    volumes = [1_500_000, 1_400_000, 1_300_000, 1_200_000, 1_100_000, 1_000_000, 900_000, 800_000, 750_000, 700_000, 650_000]
    rows = _rows(closes, volumes)

    pattern = detect_pattern(rows, _phase(rows), resolve_strategy6_config({}))

    assert pattern.pattern_type == "PLATFORM"
    assert pattern.pivot_source == "PLATFORM_TOP"
    assert pattern.pattern_start_date < pattern.pattern_end_date


def test_disabled_pattern_filter_does_not_fabricate_pattern_quality():
    cfg = resolve_strategy6_config({"strategy6": {"pattern_filter_enabled": False}})
    unknown = detect_pattern([], Strategy6Phase(), cfg)

    score = score_strategy6(
        Strategy6Indicators(relative_strength_20=0.20, relative_strength_20_observed=True),
        Strategy6Start(start_grade="A", high_trigger="new_120d_high"),
        Strategy6Phase(),
        unknown,
        Strategy6Support(support_cluster_score=18, support_test_count=2),
        Strategy6DryTail(dry_stable_score=18),
        Strategy6TradePlan(objective_rr_2=3.0),
        cfg,
    )

    assert score.pattern_score_component == 0


def test_pattern_pivot_excludes_signal_day_breakout_close():
    closes = [100]
    closes += [108, 96, 106, 97, 105, 98, 104, 99, 103, 100]
    closes += [103, 99.5, 102.5, 100, 102, 100.5, 102, 101, 102, 106]
    volumes = [2_500_000] + [2_000_000 * (0.80 ** (i // 2)) for i in range(20)]
    rows = _rows(closes, volumes)

    pattern = detect_pattern(rows, _phase(rows), resolve_strategy6_config({}))

    assert pattern.pattern_type == "VCP"
    assert pattern.pivot_price < rows[-1]["close"]
    assert pattern.pattern_end_date < rows[-1]["date"]


def test_monotonic_two_half_range_shrink_is_not_false_vcp():
    closes = [100, 102, 104, 106, 108, 110, 108, 109, 110, 111, 112, 113, 114, 115]
    volumes = [2_000_000 - i * 80_000 for i in range(len(closes))]
    rows = _rows(closes, volumes)

    pattern = detect_pattern(rows, _phase(rows), resolve_strategy6_config({}))

    assert pattern.pattern_type != "VCP"


def test_cup_handle_rejects_bottom_that_occurs_before_left_peak():
    closes = [76, 80, 90, 100, 95, 90, 85, 88, 92, 96, 98, 99, 98, 97, 98, 98.5]
    volumes = [2_000_000] * 12 + [900_000, 820_000, 760_000, 700_000]
    rows = _rows(closes, volumes)

    pattern = detect_pattern(rows, _phase(rows), resolve_strategy6_config({}))

    assert pattern.pattern_type != "CUP_HANDLE"


def test_vcp_rejects_signal_price_far_below_last_contraction_pivot():
    closes = [100]
    closes += [108, 96, 106, 97, 105, 98, 104, 99, 103, 100]
    closes += [103, 99.5, 102.5, 100, 102, 100.5, 102, 101, 102, 80]
    volumes = [2_500_000] + [2_000_000 * (0.80 ** (i // 2)) for i in range(20)]
    rows = _rows(closes, volumes)

    pattern = detect_pattern(rows, _phase(rows), resolve_strategy6_config({}))

    assert pattern.pattern_type != "VCP"


def test_vcp_chain_cannot_skip_an_intermediate_failed_contraction():
    contractions = [
        {"peak_index": 1, "low_index": 2, "amplitude": 0.12, "avg_volume": 100, "low_close": 90},
        {"peak_index": 3, "low_index": 4, "amplitude": 0.14, "avg_volume": 120, "low_close": 100},
        {"peak_index": 5, "low_index": 6, "amplitude": 0.09, "avg_volume": 80, "low_close": 90},
    ]

    chain = _best_vcp_chain(contractions, resolve_strategy6_config({}))

    assert chain == []

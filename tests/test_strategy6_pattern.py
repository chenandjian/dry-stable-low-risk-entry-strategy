from datetime import date, timedelta

from strategy6.models import (
    Strategy6DryTail,
    Strategy6Indicators,
    Strategy6Pattern,
    Strategy6Phase,
    Strategy6Start,
    Strategy6Support,
    Strategy6TradePlan,
)
import strategy6.pattern as pattern_mod
from strategy6.pattern import detect_pattern
from strategy6.vcp_rounds import VcpRound, detect_vcp_rounds
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


def _vcp_round(low_close, *, peak_close=110.0):
    return VcpRound(
        peak_index=0,
        low_index=1,
        recovery_peak_index=2,
        peak_date="2026-01-01",
        low_date="2026-01-02",
        recovery_peak_date="2026-01-03",
        peak_close=peak_close,
        low_close=low_close,
        recovery_peak_close=108.0,
        amplitude=(peak_close - low_close) / peak_close,
        rebound=108.0 / low_close - 1.0,
        decline_avg_volume=1_000_000,
        rebound_avg_volume=800_000,
    )


def test_vcp_rising_lows_bonus_requires_every_round_not_to_make_a_new_low():
    rounds = [_vcp_round(100.0), _vcp_round(102.0), _vcp_round(101.9)]

    assert pattern_mod._has_vcp_rising_lows_bonus(rounds) is False


def test_vcp_rising_lows_bonus_accepts_average_rise_exactly_one_percent():
    rounds = [_vcp_round(100.0), _vcp_round(101.0), _vcp_round(102.01)]

    assert pattern_mod._has_vcp_rising_lows_bonus(rounds) is True


def test_vcp_rising_lows_bonus_rejects_flat_or_less_than_one_percent_average():
    assert pattern_mod._has_vcp_rising_lows_bonus(
        [_vcp_round(100.0), _vcp_round(100.0), _vcp_round(101.0)],
    ) is False
    assert pattern_mod._has_vcp_rising_lows_bonus(
        [_vcp_round(100.0), _vcp_round(100.5), _vcp_round(101.0)],
    ) is False


def test_vcp_rising_lows_bonus_requires_two_completed_rounds():
    assert pattern_mod._has_vcp_rising_lows_bonus([_vcp_round(100.0)]) is False


def test_vcp_contracting_highs_bonus_accepts_flat_or_lower_highs_with_rising_lows():
    rounds = [
        _vcp_round(90.0, peak_close=110.0),
        _vcp_round(91.0, peak_close=110.0),
        _vcp_round(92.0, peak_close=108.0),
    ]

    assert pattern_mod._has_vcp_contracting_highs_bonus(rounds) is True


def test_vcp_contracting_highs_bonus_rejects_any_higher_high():
    rounds = [
        _vcp_round(90.0, peak_close=110.0),
        _vcp_round(91.0, peak_close=111.0),
        _vcp_round(92.0, peak_close=108.0),
    ]

    assert pattern_mod._has_vcp_contracting_highs_bonus(rounds) is False


def test_vcp_contracting_highs_bonus_requires_every_low_to_rise_strictly():
    assert pattern_mod._has_vcp_contracting_highs_bonus([
        _vcp_round(90.0, peak_close=110.0),
        _vcp_round(90.0, peak_close=109.0),
    ]) is False
    assert pattern_mod._has_vcp_contracting_highs_bonus([
        _vcp_round(90.0, peak_close=110.0),
        _vcp_round(89.9, peak_close=109.0),
    ]) is False


def test_vcp_contracting_highs_bonus_requires_two_completed_rounds():
    assert pattern_mod._has_vcp_contracting_highs_bonus([
        _vcp_round(90.0, peak_close=110.0),
    ]) is False


def _score_pattern(pattern, *, phase_bonus=0):
    return score_strategy6(
        Strategy6Indicators(),
        Strategy6Start(),
        Strategy6Phase(valid=True, tail_segmentation_score=phase_bonus),
        pattern,
        Strategy6Support(),
        Strategy6DryTail(),
        Strategy6TradePlan(),
        resolve_strategy6_config({}),
    )


def test_main_chain_vcp_rising_lows_evidence_adds_two_pattern_points():
    baseline = _score_pattern(Strategy6Pattern(pattern_type="VCP", pattern_score=10))
    rewarded = _score_pattern(Strategy6Pattern(
        pattern_type="VCP",
        pattern_score=10,
        reasons=["VCP_LOW_RISING_BONUS"],
    ))

    assert rewarded.pattern_score_component == baseline.pattern_score_component + 2
    assert rewarded.total_score == baseline.total_score + 2
    assert "vcp_low_trend_bonus=2" in rewarded.score_reasons


def test_vcp_rising_lows_bonus_keeps_existing_pattern_component_cap():
    rewarded = _score_pattern(
        Strategy6Pattern(
            pattern_type="VCP",
            pattern_score=20,
            reasons=["VCP_LOW_RISING_BONUS"],
        ),
        phase_bonus=3,
    )

    assert rewarded.pattern_score_component == 20


def test_main_chain_vcp_contracting_highs_evidence_adds_two_pattern_points():
    baseline = _score_pattern(Strategy6Pattern(pattern_type="VCP", pattern_score=10))
    rewarded = _score_pattern(Strategy6Pattern(
        pattern_type="VCP",
        pattern_score=10,
        reasons=["VCP_HIGH_NOT_RISING_LOW_RISING_BONUS"],
    ))

    assert rewarded.pattern_score_component == baseline.pattern_score_component + 2
    assert rewarded.total_score == baseline.total_score + 2
    assert "vcp_contracting_highs_bonus=2" in rewarded.score_reasons


def test_vcp_quality_bonuses_accumulate_but_keep_pattern_component_cap():
    baseline = _score_pattern(Strategy6Pattern(pattern_type="VCP", pattern_score=10))
    combined = _score_pattern(Strategy6Pattern(
        pattern_type="VCP",
        pattern_score=10,
        reasons=[
            "VCP_LOW_RISING_BONUS",
            "VCP_HIGH_NOT_RISING_LOW_RISING_BONUS",
        ],
    ))
    capped = _score_pattern(
        Strategy6Pattern(
            pattern_type="VCP",
            pattern_score=20,
            reasons=[
                "VCP_LOW_RISING_BONUS",
                "VCP_HIGH_NOT_RISING_LOW_RISING_BONUS",
            ],
        ),
        phase_bonus=3,
    )

    assert combined.pattern_score_component == baseline.pattern_score_component + 4
    assert combined.total_score == baseline.total_score + 4
    assert capped.pattern_score_component == 20


def test_contracting_highs_tag_does_not_reward_non_vcp_pattern():
    baseline = _score_pattern(Strategy6Pattern(pattern_type="PLATFORM", pattern_score=10))
    tagged = _score_pattern(Strategy6Pattern(
        pattern_type="PLATFORM",
        pattern_score=10,
        reasons=["VCP_HIGH_NOT_RISING_LOW_RISING_BONUS"],
    ))

    assert tagged.pattern_score_component == baseline.pattern_score_component
    assert "vcp_contracting_highs_bonus=2" not in tagged.score_reasons


def test_detects_vcp_from_two_contracting_price_and_volume_segments():
    closes = [100]
    closes += [108, 96, 106, 97, 105, 98, 104, 99, 103, 100]
    closes += [103, 99.5, 102.5, 100, 102, 100.5, 102, 101, 102, 101.5]
    volumes = [2_500_000] + [2_000_000 * (0.80 ** (i // 2)) for i in range(20)]
    rows = _rows(closes, volumes)

    pattern = detect_pattern(rows, _phase(rows), resolve_strategy6_config({}))

    assert pattern.pattern_type == "VCP"
    assert pattern.pattern_score > 0
    assert pattern.pivot_source == "VCP_LAST_RECOVERY_PEAK"
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


def test_vcp_chain_restarts_instead_of_skipping_an_intermediate_failed_round():
    rows = _rows(
        [99, 100, 88, 100, 98, 86, 100, 98, 91, 100, 99],
        [150, 150, 100, 100, 120, 120, 100, 80, 80, 80, 70],
    )

    result = detect_vcp_rounds(rows, resolve_strategy6_config({}))

    assert result.confirmed is True
    assert result.completed_rounds[0].peak_index == 3
    assert all(
        previous.recovery_peak_index == current.peak_index
        for previous, current in zip(
            result.completed_rounds,
            result.completed_rounds[1:],
        )
    )

from datetime import date, timedelta

import pytest

from strategy6.brooks.models import BrooksTailResult, BrooksTradeTriggerResult
from strategy6.brooks.models import (
    BrooksCompactStructureResult,
    BrooksContextResult,
    BrooksSellingPressureResult,
    BrooksStructureResult,
)
from strategy6.brooks.tail import analyze_brooks_tail, score_brooks_tail
from strategy6.models import (
    Strategy6CompactKline,
    Strategy6DryTail,
    Strategy6Indicators,
    Strategy6Phase,
    Strategy6Start,
    Strategy6Support,
)
from strategy6.validation import resolve_strategy6_config


def test_brooks_config_defaults_and_nested_overrides_are_resolved():
    config = resolve_strategy6_config({
        "strategy6": {
            "brooks_tail": {
                "selling_pressure": {"window_days": 5},
                "scoring": {"pass_score_min": 15},
            },
        },
    })

    brooks = config["brooks_tail"]
    assert brooks["enabled"] is True
    assert brooks["selling_pressure"]["window_days"] == 5
    assert brooks["selling_pressure"]["max_strong_bear_bar_count"] == 1
    assert brooks["scoring"]["pass_score_min"] == 15
    assert brooks["scoring"]["premium_score_min"] == 17


@pytest.mark.parametrize(
    "override, message",
    [
        ({"mode": "invalid"}, "brooks_tail.mode"),
        ({"price_stability": {"premium_close_range_max": 0.09}}, "premium_close_range_max"),
        ({"second_entry": {"min_separation_days": 16}}, "min_separation_days"),
        ({"scoring": {"pass_score_min": 18}}, "pass_score_min"),
    ],
)
def test_brooks_config_rejects_invalid_values(override, message):
    with pytest.raises(ValueError, match=message):
        resolve_strategy6_config({"strategy6": {"brooks_tail": override}})


def test_disabled_brooks_result_has_explicit_compatible_defaults():
    result = BrooksTailResult.disabled()

    assert result.enabled is False
    assert result.passed is False
    assert result.score == 0
    assert result.status == "BROOKS_DISABLED"
    assert result.trade_trigger == BrooksTradeTriggerResult()
    assert result.reasons == []
    assert result.reject_reasons == []
    assert result.risk_tags == []
    assert result.to_dict()["brooks_tail_pass"] is False


def test_brooks_result_mutable_defaults_are_not_shared():
    first = BrooksTailResult.disabled()
    second = BrooksTailResult.disabled()

    first.reasons.append("FIRST")
    first.metrics["value"] = 1

    assert second.reasons == []
    assert second.metrics == {}


def test_brooks_tail_passes_on_complete_high_quality_evidence():
    config = resolve_strategy6_config({})["brooks_tail"]
    result = score_brooks_tail(
        context=BrooksContextResult(context_type="BULL_CONTEXT", passed=True),
        selling=BrooksSellingPressureResult(
            exhausted=True,
            strong_bear_bar_count=0,
            bear_follow_through_count=0,
            max_consecutive_bear_bars=0,
        ),
        compact=BrooksCompactStructureResult(structure_type="COMPACT_ORDERLY"),
        structure=BrooksStructureResult(
            micro_double_bottom=True,
            second_entry_long_ready=True,
            setup_types=["MICRO_DOUBLE_BOTTOM", "SECOND_ENTRY_LONG_READY"],
        ),
        price_stability_checks={
            "close_range": True,
            "atr": True,
            "body_avg": True,
            "body_max": True,
            "lower_lows": True,
        },
        volume_dry_pass=True,
        volume_dry_premium=True,
        support_not_broken=True,
        config=config,
    )

    assert result.passed is True
    assert result.score >= 17
    assert result.premium is True
    assert result.status == "SECOND_ENTRY_LONG_READY"


def test_bearish_compact_structure_is_a_hard_reject_even_with_high_score():
    config = resolve_strategy6_config({})["brooks_tail"]
    result = score_brooks_tail(
        context=BrooksContextResult(context_type="BEAR_CONTEXT", passed=False),
        selling=BrooksSellingPressureResult(exhausted=False),
        compact=BrooksCompactStructureResult(structure_type="COMPACT_BEARISH"),
        structure=BrooksStructureResult(setup_types=["ORDERLY_COMPRESSION_AT_SUPPORT"]),
        price_stability_checks={key: True for key in ("close_range", "atr", "body_avg", "body_max", "lower_lows")},
        volume_dry_pass=True,
        volume_dry_premium=True,
        support_not_broken=True,
        config=config,
    )

    assert result.hard_reject is True
    assert result.passed is False
    assert result.status == "COMPACT_BEARISH_REJECT"


def _phase_bar(index, *, open_price=10.0, high=10.1, low=10.0, close=10.0):
    return {
        "date": (date(2026, 2, 2) + timedelta(days=index)).isoformat(),
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": 100,
    }


def _analyze_phase_rows(rows, consolidation_start_index):
    return analyze_brooks_tail(
        rows,
        Strategy6Indicators(
            current_price=float(rows[-1]["close"]),
            ma20=10.0,
            ma50=9.8,
            atr14=0.5,
        ),
        Strategy6Start(start_grade="A", start_low=9.5),
        Strategy6Phase(
            status="PHASE_VALID",
            valid=True,
            start_index=consolidation_start_index - 1,
            consolidation_start_index=consolidation_start_index,
            tail_start_index=max(consolidation_start_index + 1, len(rows) - 5),
            signal_index=len(rows) - 1,
            start_date=rows[consolidation_start_index - 1]["date"],
            consolidation_start_date=rows[consolidation_start_index]["date"],
            signal_date=rows[-1]["date"],
        ),
        Strategy6Support(
            key_support_price=10.0,
            support_zone_low=9.8,
            support_zone_high=10.2,
        ),
        Strategy6DryTail(tail_volume_ratio=0.55, volume_slope_10=-0.1),
        Strategy6CompactKline(enabled=True, passed=False),
        config=resolve_strategy6_config({})["brooks_tail"],
    )


def _structure_event_dates(result):
    structure = result.structure
    return [
        value
        for value in (
            structure.first_recent_low_date,
            structure.second_recent_low_date,
            structure.second_entry_signal_date,
            structure.failed_bear_breakout_date,
            structure.reclaim_date,
            structure.bear_follow_through_failed_date,
        )
        if value
    ]


def test_brooks_tail_ignores_double_bottom_before_consolidation_start():
    rows = [_phase_bar(index) for index in range(13)]
    rows[1] = _phase_bar(1, low=9.80, close=10.02)
    rows[2] = _phase_bar(2, high=10.25, low=10.0, close=10.20)
    rows[4] = _phase_bar(4, low=9.82, close=10.08)
    rows[5] = _phase_bar(5, high=10.25, low=10.0, close=10.18)

    result = _analyze_phase_rows(rows, consolidation_start_index=7)

    assert result.structure.micro_double_bottom is False
    assert result.structure.second_entry_long_ready is False
    assert all(value >= rows[7]["date"] for value in _structure_event_dates(result))


def test_brooks_tail_ignores_failed_breakout_before_consolidation_start():
    rows = [_phase_bar(index) for index in range(13)]
    rows[2] = _phase_bar(2, open_price=10.05, high=10.1, low=9.85, close=9.90)
    rows[3] = _phase_bar(3, open_price=9.92, high=10.15, low=9.90, close=10.10)

    result = _analyze_phase_rows(rows, consolidation_start_index=7)

    assert result.structure.failed_bear_breakout is False
    assert all(value >= rows[7]["date"] for value in _structure_event_dates(result))


def test_brooks_tail_accepts_same_structure_inside_current_consolidation():
    rows = [_phase_bar(index) for index in range(14)]
    rows[5] = _phase_bar(5, low=9.80, close=10.02)
    rows[6] = _phase_bar(6, high=10.25, low=10.0, close=10.20)
    rows[9] = _phase_bar(9, low=9.82, close=10.08)
    rows[10] = _phase_bar(10, high=10.25, low=10.0, close=10.18)

    result = _analyze_phase_rows(rows, consolidation_start_index=4)

    assert result.structure.micro_double_bottom is True
    assert result.structure.second_entry_long_ready is True
    assert result.structure.second_entry_signal_date == rows[10]["date"]
    assert all(value >= rows[4]["date"] for value in _structure_event_dates(result))

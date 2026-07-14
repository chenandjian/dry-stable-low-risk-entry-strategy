import pytest

from strategy6.brooks.models import BrooksTailResult, BrooksTradeTriggerResult
from strategy6.brooks.models import (
    BrooksCompactStructureResult,
    BrooksContextResult,
    BrooksSellingPressureResult,
    BrooksStructureResult,
)
from strategy6.brooks.tail import score_brooks_tail
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

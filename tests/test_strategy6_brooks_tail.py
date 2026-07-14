import pytest

from strategy6.brooks.models import BrooksTailResult, BrooksTradeTriggerResult
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

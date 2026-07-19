from strategy6.brooks.models import BrooksTailResult, BrooksTradeTriggerResult
from strategy6.entry import identify_entry_archetype
from strategy6.models import Strategy6Indicators, Strategy6Support
from strategy6.validation import resolve_strategy6_config


def _ind(price=100.0, volume_ratio=0.7, close_position=0.7):
    return Strategy6Indicators(
        current_price=price,
        current_volume_ratio_20=volume_ratio,
        current_close_position=close_position,
        atr14=2.0,
    )


def _support():
    return Strategy6Support(
        support_status="PATTERN_SUPPORT",
        key_support_price=96.0,
        tactical_support_price=98.0,
        support_zone_low=98.0,
        support_zone_high=101.0,
        pivot_price=105.0,
    )


def test_identifies_support_pullback_near_valid_support_zone():
    result = identify_entry_archetype([], _ind(100.0), _support(), None, resolve_strategy6_config({}))
    assert result == "SUPPORT_PULLBACK"


def test_identifies_confirmed_pivot_breakout_before_support_fallback():
    result = identify_entry_archetype(
        [], _ind(106.0, volume_ratio=1.5, close_position=0.8), _support(), None,
        resolve_strategy6_config({}),
    )
    assert result == "PIVOT_BREAKOUT"


def test_identifies_failed_breakout_reclaim_from_authoritative_brooks_trigger():
    brooks = BrooksTailResult(
        enabled=True,
        passed=True,
        trade_trigger=BrooksTradeTriggerResult(
            ready=True,
            trigger_type="BROOKS_FAILED_BREAKOUT_READY",
            trigger_price=99.0,
        ),
    )
    result = identify_entry_archetype(
        [], _ind(100.0), _support(), brooks, resolve_strategy6_config({}),
    )
    assert result == "FAILED_BREAKOUT_RECLAIM"


def test_waits_for_breakout_when_structure_is_valid_but_price_is_not_near_support():
    result = identify_entry_archetype(
        [], _ind(103.5), _support(), None, resolve_strategy6_config({}),
    )
    assert result == "WAIT_BREAKOUT"


def test_identifies_support_pullback_near_tactical_support_when_key_support_is_remote():
    support = _support()
    support.key_support_price = 90.0
    support.support_zone_low = 89.0
    support.support_zone_high = 91.0
    support.tactical_support_price = 100.0

    result = identify_entry_archetype(
        [], _ind(100.0), support, None, resolve_strategy6_config({}),
    )

    assert result == "SUPPORT_PULLBACK"

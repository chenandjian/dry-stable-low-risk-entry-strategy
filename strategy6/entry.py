"""Entry archetype classification for Strategy6 trade planning."""
from __future__ import annotations

from strategy6.brooks.models import BrooksTailResult
from strategy6.models import Strategy6Indicators, Strategy6Support


ENTRY_ARCHETYPES = {
    "SUPPORT_PULLBACK",
    "PIVOT_BREAKOUT",
    "FAILED_BREAKOUT_RECLAIM",
    "WAIT_BREAKOUT",
    "NONE",
}


def identify_entry_archetype(
    rows: list[dict],
    ind: Strategy6Indicators,
    support: Strategy6Support,
    brooks_tail: BrooksTailResult | None,
    config: dict,
) -> str:
    del rows  # Reserved for future as-of price-action confirmations.
    trigger = brooks_tail.trade_trigger if brooks_tail is not None else None
    if (
        trigger is not None
        and trigger.ready
        and "FAILED_BREAKOUT" in str(trigger.trigger_type or "")
    ):
        return "FAILED_BREAKOUT_RECLAIM"
    pivot = float(support.pivot_price or 0.0)
    current = float(ind.current_price or 0.0)
    if (
        pivot > 0
        and pivot < current <= pivot * (1 + float(config["breakout_extended_max_pct"]))
        and ind.current_volume_ratio_20 >= 1.3
        and ind.current_close_position >= 0.65
    ):
        return "PIVOT_BREAKOUT"
    tactical_tolerance = max(
        current * float(config["support_zone_price_pct"]),
        float(ind.atr14 or 0.0) * float(config["support_zone_atr_multiplier"]),
    )
    near_key_support = (
        support.support_zone_low > 0
        and support.support_zone_low <= current <= support.support_zone_high * 1.02
    )
    near_tactical_support = (
        support.tactical_support_price > 0
        and support.tactical_support_price <= current
        and current - support.tactical_support_price <= tactical_tolerance
    )
    if near_key_support or near_tactical_support:
        return "SUPPORT_PULLBACK"
    if pivot > current > 0 and support.support_status != "SUPPORT_FAILED":
        return "WAIT_BREAKOUT"
    return "NONE"

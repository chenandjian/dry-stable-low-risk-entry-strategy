"""Strategy1 quality tag helpers."""

from __future__ import annotations


def build_strategy1_quality_tags(
    *,
    price_stable_score: int = 0,
    verdict_key: str = "",
    has_short_term_diagnostic: bool = False,
) -> list[str]:
    tags: list[str] = []
    if price_stable_score >= 8:
        tags.append("PRICE_STABLE_EXTREME")
    elif price_stable_score >= 7:
        tags.append("PRICE_STABLE_STRONG")
    if verdict_key == "WATCH_BREAKOUT":
        tags.append("BREAKOUT_OBSERVE")
    if has_short_term_diagnostic:
        tags.append("SHORT_TERM_RISK_CONTROL")
    return tags


def build_strategy1_quality_layer(tags: list[str]) -> str:
    if "PRICE_STABLE_EXTREME" in tags:
        return "premium"
    if "PRICE_STABLE_STRONG" in tags:
        return "strong"
    if "BREAKOUT_OBSERVE" in tags:
        return "watch"
    if "SHORT_TERM_RISK_CONTROL" in tags:
        return "risk_control"
    return "normal"

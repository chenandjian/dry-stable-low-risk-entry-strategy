"""Selling-pressure and bear follow-through analysis."""
from __future__ import annotations

from strategy6.brooks.context import support_effectively_broken
from strategy6.brooks.metrics import bar_metrics
from strategy6.brooks.models import BrooksSellingPressureResult
from strategy6.models import Strategy6Support


def analyze_selling_pressure(
    rows: list[dict],
    support: Strategy6Support,
    config: dict,
) -> BrooksSellingPressureResult:
    cfg = config["selling_pressure"]
    result = BrooksSellingPressureResult()
    window = rows[-int(cfg["window_days"]):]
    if len(window) < 2:
        result.risk_tags.append("BROOKS_SELLING_PRESSURE_DATA_INSUFFICIENT")
        return result

    strong_indexes: list[int] = []
    for index, row in enumerate(window):
        metric = bar_metrics(row)
        if not metric.valid:
            result.risk_tags.extend(metric.risk_tags)
            continue
        if (
            float(row.get("close") or 0) < float(row.get("open") or 0)
            and (metric.body_ratio or 0) >= float(cfg["strong_bear_body_ratio_min"])
            and (metric.close_position or 0) <= float(cfg["strong_bear_close_position_max"])
        ):
            strong_indexes.append(index)
            result.strong_bear_bar_dates.append(str(row.get("date") or ""))
    result.strong_bear_bar_count = len(strong_indexes)

    for index in strong_indexes:
        if index + 1 >= len(window):
            continue
        bear = window[index]
        following = window[index + 1]
        following_metric = bar_metrics(following)
        support_broken = (
            float(support.key_support_price or 0) > 0
            and float(following.get("close") or 0) < float(support.key_support_price)
        )
        followed = any((
            float(following.get("close") or 0) < float(bear.get("low") or 0),
            float(following.get("close") or 0) < float(bear.get("close") or 0)
            and (following_metric.close_position or 0) <= float(cfg["bear_follow_through_close_position_max"]),
            index + 1 in strong_indexes,
            support_broken,
        ))
        if followed:
            result.bear_follow_through_dates.append(str(following.get("date") or ""))
        else:
            reclaim_date = _reclaimed_body_midpoint(window, index)
            if not reclaim_date:
                continue
            result.bear_follow_through_failed = True
            if (
                not result.bear_follow_through_failed_date
                or reclaim_date < result.bear_follow_through_failed_date
            ):
                result.bear_follow_through_failed_date = reclaim_date
    result.bear_follow_through_count = len(result.bear_follow_through_dates)
    result.max_consecutive_bear_bars = _max_consecutive_bear_bars(window)
    result.bear_body_contraction_ratio = _bear_body_contraction_ratio(window)

    support_broken = support_effectively_broken(
        rows,
        support,
        float(config["support"]["effective_break_pct"]),
        int(config["support"]["consecutive_close_break_days"]),
    )
    if support_broken:
        result.risk_tags.append("BROOKS_SUPPORT_EFFECTIVELY_BROKEN")
    if result.max_consecutive_bear_bars > int(cfg["max_consecutive_bear_bars"]):
        result.risk_tags.append("BROOKS_CONSECUTIVE_BEAR_BARS")
    if result.strong_bear_bar_count > int(cfg["max_strong_bear_bar_count"]):
        result.risk_tags.append("BROOKS_STRONG_BEAR_BARS_EXCESSIVE")
    if result.bear_follow_through_count > int(cfg["max_bear_follow_through_count"]):
        result.risk_tags.append("BROOKS_BEAR_FOLLOW_THROUGH")

    body_contracting_pass = (
        not cfg["require_bear_body_contracting"]
        or result.bear_body_contraction_ratio is None
        or result.bear_body_contraction_ratio <= 1
    )
    result.exhausted = all((
        result.strong_bear_bar_count <= int(cfg["max_strong_bear_bar_count"]),
        result.bear_follow_through_count <= int(cfg["max_bear_follow_through_count"]),
        result.max_consecutive_bear_bars <= int(cfg["max_consecutive_bear_bars"]),
        body_contracting_pass,
        not support_broken,
    ))
    if result.exhausted:
        result.reasons.append("BROOKS_SELLING_PRESSURE_EXHAUSTED")
    return result


def _reclaimed_body_midpoint(rows: list[dict], bear_index: int) -> str:
    bear = rows[bear_index]
    midpoint = (
        float(bear.get("open") or 0) + float(bear.get("close") or 0)
    ) / 2
    for row in rows[bear_index + 1:bear_index + 3]:
        if float(row.get("close") or 0) >= midpoint:
            return str(row.get("date") or "")
    return ""


def _max_consecutive_bear_bars(rows: list[dict]) -> int:
    maximum = current = 0
    previous_low: float | None = None
    for row in rows:
        close = float(row.get("close") or 0)
        open_price = float(row.get("open") or 0)
        low = float(row.get("low") or 0)
        if close < open_price:
            current = current + 1 if previous_low is None or low < previous_low else 1
            previous_low = low
        else:
            current = 0
            previous_low = None
        maximum = max(maximum, current)
    return maximum


def _bear_body_contraction_ratio(rows: list[dict]) -> float | None:
    bodies = [
        abs(float(row.get("close") or 0) - float(row.get("open") or 0))
        for row in rows
        if float(row.get("close") or 0) < float(row.get("open") or 0)
    ]
    if len(bodies) < 2 or bodies[-2] <= 0:
        return None
    return round(bodies[-1] / bodies[-2], 6)

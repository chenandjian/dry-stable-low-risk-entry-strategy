"""Shared objective K-line metrics used by Strategy6 tail analyzers."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BarMetrics:
    valid: bool = False
    body_ratio: float | None = None
    close_position: float | None = None
    upper_shadow_ratio: float | None = None
    lower_shadow_ratio: float | None = None
    range_ratio: float | None = None
    risk_tags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SwingPoint:
    index: int
    date: str
    price: float


def bar_metrics(bar: dict) -> BarMetrics:
    close = _number(bar.get("close"))
    open_price = _number(bar.get("open"))
    high = _number(bar.get("high"))
    low = _number(bar.get("low"))
    if close <= 0:
        return BarMetrics(risk_tags=("INVALID_CLOSE",))
    if high < max(open_price, close) or low > min(open_price, close) or high < low:
        return BarMetrics(risk_tags=("INVALID_OHLC",))

    full_range = high - low
    tags: list[str] = []
    if full_range <= 0:
        close_position = 0.5
        upper_shadow = 0.0
        lower_shadow = 0.0
        tags.append("ZERO_RANGE_BAR")
    else:
        close_position = (close - low) / full_range
        upper_shadow = (high - max(open_price, close)) / full_range
        lower_shadow = (min(open_price, close) - low) / full_range
    return BarMetrics(
        valid=True,
        body_ratio=abs(close - open_price) / close,
        close_position=close_position,
        upper_shadow_ratio=upper_shadow,
        lower_shadow_ratio=lower_shadow,
        range_ratio=full_range / close,
        risk_tags=tuple(tags),
    )


def calculate_kline_overlap_ratio(previous: dict, current: dict) -> float | None:
    previous_range = _number(previous.get("high")) - _number(previous.get("low"))
    current_range = _number(current.get("high")) - _number(current.get("low"))
    minimum_range = min(previous_range, current_range)
    if minimum_range <= 0:
        return None
    overlap = max(
        0.0,
        min(_number(previous.get("high")), _number(current.get("high")))
        - max(_number(previous.get("low")), _number(current.get("low"))),
    )
    return round(overlap / minimum_range, 6)


def count_direction_changes(rows: list[dict]) -> int:
    directions: list[int] = []
    for previous, current in zip(rows[:-1], rows[1:]):
        delta = _number(current.get("close")) - _number(previous.get("close"))
        if delta > 0:
            directions.append(1)
        elif delta < 0:
            directions.append(-1)
    return sum(current != previous for previous, current in zip(directions[:-1], directions[1:]))


def find_swing_lows(rows: list[dict]) -> list[SwingPoint]:
    points: list[SwingPoint] = []
    for index in range(1, len(rows) - 1):
        previous = _number(rows[index - 1].get("low"))
        current = _number(rows[index].get("low"))
        following = _number(rows[index + 1].get("low"))
        if current > 0 and current <= previous and current <= following and (current < previous or current < following):
            points.append(SwingPoint(index, str(rows[index].get("date") or ""), current))
    return points


def find_swing_highs(rows: list[dict]) -> list[SwingPoint]:
    points: list[SwingPoint] = []
    for index in range(1, len(rows) - 1):
        previous = _number(rows[index - 1].get("high"))
        current = _number(rows[index].get("high"))
        following = _number(rows[index + 1].get("high"))
        if current > 0 and current >= previous and current >= following and (current > previous or current > following):
            points.append(SwingPoint(index, str(rows[index].get("date") or ""), current))
    return points


def _number(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0

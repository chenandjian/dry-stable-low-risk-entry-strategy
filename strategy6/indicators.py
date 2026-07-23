"""Strategy6 indicator calculation."""
from __future__ import annotations

from strategy6.models import Strategy6Indicators


def normalize_rows(data: list[dict]) -> list[dict]:
    rows = []
    previous_close = 0.0
    for row in data:
        close = _float(row.get("close", row.get("last", 0)))
        normalized = {
            "date": str(row.get("date") or row.get("trade_date") or ""),
            "open": _float(row.get("open", close)),
            "high": _float(row.get("high", close)),
            "low": _float(row.get("low", close)),
            "close": close,
            "prev_close": _float(row.get("prev_close", previous_close)),
            "volume": _float(row.get("volume", 0)),
            "amount": _amount_yuan(row),
        }
        previous_close = close
        rows.append(normalized)
    return rows


def calculate_indicators(
    data: list[dict],
    config: dict,
    *,
    trading_days_override: int | None = None,
    rows_normalized: bool = False,
) -> tuple[list[dict], Strategy6Indicators]:
    rows = data if rows_normalized else normalize_rows(data)
    ind = Strategy6Indicators(trading_days=trading_days_override or len(rows))
    if not rows:
        return rows, ind
    ind.evaluation_date = rows[-1]["date"]
    ind.current_price = rows[-1]["close"]
    ind.daily_return = _return_between(rows[-1]["prev_close"], rows[-1]["close"])
    ind.current_close_position = _close_position(rows[-1])
    ind.ma5 = _ma(rows, 5)
    ind.ma10 = _ma(rows, 10)
    ind.ma20 = _ma(rows, 20)
    ind.ma50 = _ma(rows, 50)
    ind.ma120 = _ma(rows, 120)
    ind.ma250 = _ma(rows, 250)
    ind.atr14 = _atr(rows, 14)
    ind.return_5 = _return_over(rows, 5)
    ind.return_10 = _return_over(rows, 10)
    ind.return_20 = _return_over(rows, 20)
    ind.amount_avg_10 = _avg_amount_yi(rows, 10)
    ind.amount_avg_30 = _avg_amount_yi(rows, 30)
    ind.amount_avg_60 = _avg_amount_yi(rows, 60)
    ind.v3 = _avg_volume(rows, 3)
    ind.v5 = _avg_volume(rows, 5)
    ind.v10 = _avg_volume(rows, 10)
    ind.v20 = _avg_volume(rows, 20)
    ind.volume_ratio_5_20 = round(ind.v5 / ind.v20, 6) if ind.v20 > 0 else 0.0
    prior_v20 = _mean(row["volume"] for row in rows[-21:-1]) if len(rows) >= 21 else 0.0
    ind.current_volume_ratio_20 = round(rows[-1]["volume"] / prior_v20, 6) if prior_v20 > 0 else 0.0
    ind.highest_close_20 = max((r["close"] for r in rows[-20:]), default=0.0)
    ind.highest_close_120 = max((r["close"] for r in rows[-120:]), default=0.0)
    ind.highest_close_250 = max((r["close"] for r in rows[-250:]), default=0.0)
    ind.pullback_from_20d_high = _return_between(ind.highest_close_20, ind.current_price)
    ind.range_5 = _range(rows, 5)
    ind.range_10 = _range(rows, 10)
    ind.close_range_5 = _close_range(rows, 5)
    (
        ind.consecutive_down_days,
        ind.consecutive_down_low,
        ind.consecutive_down_structure_pass,
        ind.consecutive_down_no_new_streak_low,
        ind.consecutive_down_min_low_margin_pct,
        ind.consecutive_down_max_high_break_pct,
    ) = _consecutive_decline_support(rows)
    ind.has_big_down_volume = _has_big_down_volume(rows, ind.v20, config)
    if ind.has_big_down_volume:
        ind.risk_tags.append("BIG_DOWN_VOLUME")
    return rows, ind


def _amount_yuan(row: dict) -> float:
    value = _float(row.get("amount", row.get("turnover", 0)))
    if 0 < value < 10_000:
        return value * 100_000_000
    return value


def _float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _ma(rows: list[dict], days: int, end: int | None = None) -> float:
    end = len(rows) if end is None else end
    start = end - days
    if start < 0 or end > len(rows):
        return 0.0
    return round(_mean(row["close"] for row in rows[start:end]), 4)


def _return_between(prev: float, current: float) -> float:
    return round((current - prev) / prev, 6) if prev > 0 else 0.0


def _return_over(rows: list[dict], days: int) -> float:
    if len(rows) <= days:
        return 0.0
    return _return_between(rows[-days - 1]["close"], rows[-1]["close"])


def _avg_amount_yi(rows: list[dict], days: int) -> float:
    selected = rows[-days:]
    return round(_mean(row["amount"] / 100_000_000 for row in selected), 4) if selected else 0.0


def _avg_volume(rows: list[dict], days: int) -> float:
    selected = rows[-days:]
    return round(_mean(row["volume"] for row in selected), 4) if selected else 0.0


def _atr(rows: list[dict], days: int) -> float:
    if len(rows) < days + 1:
        return 0.0
    values = []
    for prev, curr in zip(rows[-days - 1:-1], rows[-days:]):
        values.append(max(
            curr["high"] - curr["low"],
            abs(curr["high"] - prev["close"]),
            abs(curr["low"] - prev["close"]),
        ))
    return round(_mean(values), 4)


def _range(rows: list[dict], days: int) -> float:
    if len(rows) <= days:
        return 0.0
    selected = rows[-days:]
    base = rows[-days - 1]["close"]
    return round((max(r["high"] for r in selected) - min(r["low"] for r in selected)) / base, 6) if base > 0 else 0.0


def _close_range(rows: list[dict], days: int) -> float:
    selected = rows[-days:]
    close = rows[-1]["close"] if rows else 0.0
    return round((max(r["close"] for r in selected) - min(r["close"] for r in selected)) / close, 6) if close > 0 and selected else 0.0


def _consecutive_decline_support(
    rows: list[dict],
) -> tuple[int, float | None, bool, bool | None, float | None, float | None]:
    decline_indexes: list[int] = []
    for index in range(len(rows) - 1, 0, -1):
        if rows[index]["close"] >= rows[index - 1]["close"]:
            break
        decline_indexes.append(index)
    decline_indexes.reverse()

    days = len(decline_indexes)
    if not decline_indexes:
        return 0, None, False, None, None, None

    decline_low = round(min(rows[index]["low"] for index in decline_indexes), 4)
    first_decline_low = rows[decline_indexes[0]]["low"]
    no_new_streak_low = (
        all(rows[index]["low"] >= first_decline_low for index in decline_indexes[1:])
        if days >= 2
        else None
    )
    low_margins: list[float] = []
    high_breaks: list[float] = []
    for index in decline_indexes:
        if index < 5:
            return days, decline_low, False, None, None, None
        prior_five = rows[index - 5:index]
        prior_low = min(row["low"] for row in prior_five)
        prior_high = max(row["high"] for row in prior_five)
        if prior_low <= 0 or prior_high <= 0:
            return days, decline_low, False, None, None, None
        low_margins.append(rows[index]["low"] / prior_low - 1.0)
        high_breaks.append(rows[index]["high"] / prior_high - 1.0)

    min_low_margin = min(low_margins)
    max_high_break = max(high_breaks)
    passed = (
        days >= 3
        and no_new_streak_low is True
        and min_low_margin >= 0
        and max_high_break <= 0
    )
    return (
        days,
        decline_low,
        passed,
        no_new_streak_low,
        round(min_low_margin, 6),
        round(max_high_break, 6),
    )


def _has_big_down_volume(rows: list[dict], v20: float, config: dict) -> bool:
    if v20 <= 0 or len(rows) < 2:
        return False
    for prev, curr in zip(rows[-6:-1], rows[-5:]):
        ret = _return_between(prev["close"], curr["close"])
        if ret <= config["big_down_return"] and curr["volume"] >= v20 * config["big_down_volume_ratio"]:
            return True
    return False


def _close_position(row: dict) -> float:
    span = row["high"] - row["low"]
    return round((row["close"] - row["low"]) / span, 6) if span > 0 else 1.0


def _mean(values) -> float:
    total = 0.0
    count = 0
    for value in values:
        total += value
        count += 1
    return total / count if count else 0.0

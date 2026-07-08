"""Strategy5 indicator calculations."""
from __future__ import annotations

from strategy5.models import Strategy5Indicators

MA_PERIODS = (5, 10, 20, 50, 100, 120, 250)


def calculate_indicators(
    data: list[dict],
    config: dict,
    *,
    trading_days_override: int | None = None,
    rows_normalized: bool = False,
) -> Strategy5Indicators:
    rows = data if rows_normalized else normalize_rows(data)
    ind = Strategy5Indicators(trading_days=trading_days_override or len(rows))
    if not rows:
        return ind

    ind.evaluation_date = str(rows[-1].get("date") or "")
    ind.close = rows[-1]["close"]
    ind.daily_return = _return_between(rows[-2]["close"], rows[-1]["close"]) if len(rows) >= 2 else 0.0
    ind.change_pct = ind.daily_return * 100

    ma_values = {p: _ma(rows, p) for p in MA_PERIODS}
    ind.ma5 = ma_values[5]
    ind.ma10 = ma_values[10]
    ind.ma20 = ma_values[20]
    ind.ma50 = ma_values[50]
    ind.ma100 = ma_values[100]
    ind.ma120 = ma_values[120]
    ind.ma250 = ma_values[250]
    ind.distance_to_ma5 = _distance(ind.close, ind.ma5)
    ind.distance_to_ma10 = _distance(ind.close, ind.ma10)
    ind.distance_to_ma20 = _distance(ind.close, ind.ma20)

    ind.avg_turnover_60d = _avg_amount_yi(rows, 60)
    ind.avg_turnover_30d = _avg_amount_yi(rows, 30)
    ind.avg_turnover_10d = _avg_amount_yi(rows, 10)
    ind.recent_5d_return = _return_over(rows, 5)
    ind.recent_10d_return = _return_over(rows, 10)
    ind.recent_20d_return = _return_over(rows, 20)
    ind.recent_50d_return = _return_over(rows, 50)
    ind.v3 = _avg_volume(rows, 3)
    ind.v5 = _avg_volume(rows, 5)
    ind.v10 = _avg_volume(rows, 10)
    ind.v20 = _avg_volume(rows, 20)
    ind.v50 = _avg_volume(rows, 50)
    ind.volume_ratio_5_20 = round(ind.v5 / ind.v20, 6) if ind.v20 > 0 else 0.0
    ind.volume_ratio_5_50 = round(ind.v5 / ind.v50, 6) if ind.v50 > 0 else 0.0
    ind.volume_percentile_60 = _volume_percentile(rows, ind.v5, 60)
    ind.down_volume_ratio_5 = _down_volume_ratio(rows, 5)
    ind.down_day_avg_volume_ratio_20 = _down_day_avg_volume_ratio(rows, ind.v20, 5)
    ind.has_big_down_volume = _has_big_down_volume(rows, ind.v20, config)
    ind.consecutive_heavy_bear_days = _consecutive_heavy_bear_days(rows, ind.v20, config)
    ind.amplitude_5d = _amplitude(rows, 5)
    ind.amplitude_10d = _amplitude(rows, 10)
    ind.close_range_5 = _close_range(rows, 5)
    ind.atr_ratio_5_20 = _atr_ratio(rows, 5, 20)
    ind.direction_efficiency_5 = _direction_efficiency(rows, 5)
    ind.no_new_low_5 = _no_new_low(rows, 5)
    ind.bear_body_shrink = _bear_body_shrink(rows)
    ind.down_return_contracting = _down_return_contracting(rows)
    ind.close_20d_high = max((r["close"] for r in rows[-20:]), default=0.0)
    ind.close_120d_high = max((r["close"] for r in rows[-120:]), default=0.0)
    ind.near_120d_high_ratio = ind.close_20d_high / ind.close_120d_high if ind.close_120d_high > 0 else 0.0
    ind.drawdown_from_20d_high = _return_between(ind.close_20d_high, ind.close) if ind.close_20d_high > 0 else 0.0
    ind.max_decline_5d = min(_daily_returns(rows[-6:]), default=0.0)
    ind.ma20_slope_5d = _ma_slope(rows, 20, 5)
    ind.ma50_slope_10d = _ma_slope(rows, 50, 10)
    ind.dry_support_price = _dry_support_price(ind)
    ind.dry_support_distance = _distance(ind.close, ind.dry_support_price)
    ind.dry_support_valid = _dry_support_valid(rows, ind.dry_support_price)

    ind.strength_trigger = _strength_trigger(rows, ind, config)
    ind.short_strength_score = _short_strength_score(ind)
    ind.high_trigger = _high_trigger(ind, config)
    ind.has_volume_up_decline = _has_volume_up_decline(rows, config, ind.v20)
    _apply_tags(ind, config)
    return ind


def normalize_rows(data: list[dict]) -> list[dict]:
    return [_normalize_row(r) for r in data]


def _normalize_row(row: dict) -> dict:
    close = _float(row.get("close", row.get("last", 0)))
    return {
        "date": row.get("date", ""),
        "open": _float(row.get("open", close)),
        "high": _float(row.get("high", close)),
        "low": _float(row.get("low", close)),
        "close": close,
        "volume": _float(row.get("volume", 0)),
        "turnover": _float(row.get("turnover", row.get("amount", 0))),
    }


def _float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _ma(rows: list[dict], period: int, end: int | None = None) -> float:
    end = len(rows) if end is None else end
    start = end - period
    if start < 0 or end > len(rows):
        return 0.0
    return round(_mean(r["close"] for r in rows[start:end]), 4)


def _ma_slope(rows: list[dict], period: int, lookback: int) -> float:
    current = _ma(rows, period)
    previous = _ma(rows, period, len(rows) - lookback)
    return round((current - previous) / previous * 100, 4) if previous > 0 else 0.0


def _return_between(prev: float, current: float) -> float:
    return round((current - prev) / prev, 6) if prev > 0 else 0.0


def _return_over(rows: list[dict], days: int) -> float:
    if len(rows) <= days:
        return 0.0
    return _return_between(rows[-days - 1]["close"], rows[-1]["close"])


def _daily_returns(rows: list[dict]) -> list[float]:
    returns = []
    for i in range(1, len(rows)):
        returns.append(_return_between(rows[i - 1]["close"], rows[i]["close"]))
    return returns


def _avg_amount_yi(rows: list[dict], days: int) -> float:
    selected = rows[-days:]
    if not selected:
        return 0.0
    values = []
    for row in selected:
        amount = row["turnover"]
        values.append(amount / 100_000_000 if amount > 10_000 else amount)
    return round(_mean(values), 4)


def _avg_volume(rows: list[dict], days: int) -> float:
    selected = rows[-days:]
    return round(_mean(r["volume"] for r in selected), 4) if selected else 0.0


def _volume_percentile(rows: list[dict], value: float, days: int) -> float:
    if value <= 0:
        return 0.0
    selected = [r["volume"] for r in rows[-days:] if r["volume"] > 0]
    if not selected:
        return 0.0
    return round(sum(1 for volume in selected if volume <= value) / len(selected), 6)


def _down_volume_ratio(rows: list[dict], days: int) -> float:
    selected = rows[-days:]
    total = sum(r["volume"] for r in selected)
    if total <= 0:
        return 0.0
    down_volume = sum(r["volume"] for r in selected if _is_bear(r))
    return round(down_volume / total, 6)


def _down_day_avg_volume_ratio(rows: list[dict], v20: float, days: int) -> float:
    if v20 <= 0:
        return 0.0
    selected = [r["volume"] for r in rows[-days:] if _is_bear(r)]
    if not selected:
        return 0.0
    return round(_mean(selected) / v20, 6)


def _has_big_down_volume(rows: list[dict], v20: float, config: dict) -> bool:
    if v20 <= 0 or len(rows) < 2:
        return False
    return_threshold = config["volume_dry_big_down_return"]
    volume_ratio = config["volume_dry_big_down_volume_ratio"]
    for prev, curr in zip(rows[-6:-1], rows[-5:]):
        ret = _return_between(prev["close"], curr["close"])
        bear_body_return = _bear_body_return(curr)
        if curr["volume"] >= v20 * volume_ratio and (ret <= return_threshold or bear_body_return <= -0.04):
            return True
    return False


def _consecutive_heavy_bear_days(rows: list[dict], v20: float, config: dict) -> int:
    if v20 <= 0:
        return 0
    streak = 0
    max_streak = 0
    for row in rows[-10:]:
        if _bear_body_return(row) <= -0.03 and row["volume"] >= v20 * 1.2:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    return max_streak


def _amplitude(rows: list[dict], days: int) -> float:
    if len(rows) <= days:
        return 0.0
    selected = rows[-days:]
    base = rows[-days - 1]["close"]
    return round((max(r["high"] for r in selected) - min(r["low"] for r in selected)) / base, 6) if base > 0 else 0.0


def _close_range(rows: list[dict], days: int) -> float:
    selected = rows[-days:]
    close = rows[-1]["close"] if rows else 0.0
    if close <= 0 or not selected:
        return 0.0
    return round((max(r["close"] for r in selected) - min(r["close"] for r in selected)) / close, 6)


def _atr_ratio(rows: list[dict], short_days: int, long_days: int) -> float:
    short_atr = _atr(rows, short_days)
    long_atr = _atr(rows, long_days)
    return round(short_atr / long_atr, 6) if long_atr > 0 else 0.0


def _atr(rows: list[dict], days: int) -> float:
    if not rows:
        return 0.0
    selected = rows[-days:]
    values = []
    start = len(rows) - len(selected)
    for offset, row in enumerate(selected):
        idx = start + offset
        prev_close = rows[idx - 1]["close"] if idx > 0 else row["close"]
        values.append(max(row["high"] - row["low"], abs(row["high"] - prev_close), abs(row["low"] - prev_close)))
    return _mean(values)


def _direction_efficiency(rows: list[dict], days: int) -> float:
    if len(rows) <= days:
        return 0.0
    base = rows[-days - 1]["close"]
    if base <= 0:
        return 0.0
    net_change = abs(rows[-1]["close"] / base - 1)
    total_move = sum(abs(value) for value in _daily_returns(rows[-days - 1:]))
    return round(net_change / total_move, 6) if total_move > 0 else 0.0


def _no_new_low(rows: list[dict], days: int) -> bool:
    if len(rows) <= days * 2:
        return True
    previous = rows[-days * 2:-days]
    recent = rows[-days:]
    previous_low = min(r["low"] for r in previous)
    recent_low = min(r["low"] for r in recent)
    return recent_low >= previous_low * 0.995


def _bear_body_shrink(rows: list[dict]) -> bool:
    prior = [_bear_body_ratio(row) for row in rows[-10:-5] if _is_bear(row)]
    recent = [_bear_body_ratio(row) for row in rows[-5:] if _is_bear(row)]
    if not recent:
        return True
    if not prior:
        return False
    return _mean(recent) <= _mean(prior)


def _down_return_contracting(rows: list[dict]) -> bool:
    if len(rows) < 11:
        return True
    prior = [abs(v) for v in _daily_returns(rows[-11:-5]) if v < 0]
    recent = [abs(v) for v in _daily_returns(rows[-6:]) if v < 0]
    if not recent:
        return True
    if not prior:
        return False
    return _mean(recent) <= _mean(prior)


def _distance(close: float, value: float) -> float:
    return round(abs(close - value) / close, 6) if close > 0 and value > 0 else 0.0


def _dry_support_price(ind: Strategy5Indicators) -> float:
    for value in (ind.ma10, ind.ma20, ind.ma5):
        if value > 0 and ind.close >= value:
            return value
    return ind.ma20 if ind.ma20 > 0 else ind.close


def _dry_support_valid(rows: list[dict], support_price: float) -> bool:
    if support_price <= 0:
        return False
    floor = support_price * 0.98
    return all(row["close"] >= floor for row in rows[-5:])


def _is_bear(row: dict) -> bool:
    return row["close"] < row["open"]


def _bear_body_return(row: dict) -> float:
    return _return_between(row["open"], row["close"]) if row["open"] > 0 else 0.0


def _bear_body_ratio(row: dict) -> float:
    return abs(_bear_body_return(row)) if _is_bear(row) else 0.0


def _mean(values) -> float:
    total = 0.0
    count = 0
    for value in values:
        total += value
        count += 1
    return total / count if count else 0.0


def _strength_trigger(rows: list[dict], ind: Strategy5Indicators, config: dict) -> str:
    if ind.recent_20d_return >= config["strength_ret_20d"]:
        return "ret_20d"
    if ind.recent_10d_return >= config["strength_ret_10d"]:
        return "ret_10d"
    if ind.recent_5d_return >= config["strength_ret_5d"]:
        return "ret_5d"
    threshold = config["single_day_surge_return"]
    volume_ratio = config["single_day_surge_volume_ratio"]
    v20 = ind.v20
    for i in range(max(1, len(rows) - 20), len(rows)):
        ret = _return_between(rows[i - 1]["close"], rows[i]["close"])
        if ret >= threshold and v20 > 0 and rows[i]["volume"] >= v20 * volume_ratio:
            return "single_day_surge"
    return ""


def _short_strength_score(ind: Strategy5Indicators) -> int:
    base = {
        "ret_20d": 20,
        "ret_10d": 18,
        "ret_5d": 16,
        "single_day_surge": 13,
    }.get(ind.strength_trigger, 0)
    if base == 0:
        return 0
    if ind.drawdown_from_20d_high >= -0.12:
        base += 2
    if 0 < ind.amplitude_5d <= 0.16:
        base += 1
    if ind.close >= ind.ma10 > 0:
        base += 1
    return min(base, 24)


def _high_trigger(ind: Strategy5Indicators, config: dict) -> str:
    if ind.close_120d_high <= 0:
        return ""
    if ind.close_20d_high >= ind.close_120d_high:
        return "new_120d_high"
    if ind.close_20d_high >= ind.close_120d_high * config["near_120d_high_ratio"]:
        return "near_120d_high"
    return ""


def _has_volume_up_decline(rows: list[dict], config: dict, v20: float) -> bool:
    if v20 <= 0 or len(rows) < 6:
        return False
    for i in range(len(rows) - 5, len(rows)):
        ret = _return_between(rows[i - 1]["close"], rows[i]["close"])
        if ret <= config["volume_down_return"] and rows[i]["volume"] >= v20 * config["volume_down_ratio"]:
            return True
    return False


def _apply_tags(ind: Strategy5Indicators, config: dict) -> None:
    if ind.amplitude_5d <= 0.12:
        ind.range_5_tag = "LOW_5D_VOLATILITY"
    elif ind.amplitude_5d <= 0.18:
        ind.range_5_tag = "HIGH_5D_VOLATILITY"
        ind.warn_tags.append(ind.range_5_tag)
    elif ind.amplitude_5d <= config["max_amp_5d"]:
        ind.range_5_tag = "EXTREME_5D_VOLATILITY_OBSERVE"
        ind.warn_tags.append(ind.range_5_tag)

    if ind.amplitude_10d <= 0.25:
        ind.range_10_tag = "NORMAL_10D_CONSOLIDATION"
    elif ind.amplitude_10d <= 0.35:
        ind.range_10_tag = "HIGH_10D_VOLATILITY"
        ind.warn_tags.append(ind.range_10_tag)
    elif ind.amplitude_10d <= config["max_amp_10d"]:
        ind.range_10_tag = "EXTREME_10D_VOLATILITY_OBSERVE"
        ind.warn_tags.append(ind.range_10_tag)

    if ind.drawdown_from_20d_high >= -0.10:
        ind.pullback_tag = "STRONG_NEAR_HIGH"
    elif ind.drawdown_from_20d_high >= -0.15:
        ind.pullback_tag = "HEALTHY_PULLBACK"
    elif ind.drawdown_from_20d_high >= -0.22:
        ind.pullback_tag = "DEEP_PULLBACK"
        ind.warn_tags.append(ind.pullback_tag)
    elif ind.drawdown_from_20d_high >= config["max_drawdown_20d"]:
        ind.pullback_tag = "EXTREME_PULLBACK_OBSERVE"
        ind.warn_tags.append(ind.pullback_tag)

    if ind.daily_return <= -0.07:
        ind.risk_tags.append("BIG_DROP_TODAY")
    if ind.has_volume_up_decline:
        ind.risk_tags.append("VOLUME_UP_DECLINE")

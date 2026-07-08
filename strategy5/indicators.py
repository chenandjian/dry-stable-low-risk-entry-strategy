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
    ind.v20 = _avg_volume(rows, 20)
    ind.amplitude_5d = _amplitude(rows, 5)
    ind.amplitude_10d = _amplitude(rows, 10)
    ind.close_20d_high = max((r["close"] for r in rows[-20:]), default=0.0)
    ind.close_120d_high = max((r["close"] for r in rows[-120:]), default=0.0)
    ind.near_120d_high_ratio = ind.close_20d_high / ind.close_120d_high if ind.close_120d_high > 0 else 0.0
    ind.drawdown_from_20d_high = _return_between(ind.close_20d_high, ind.close) if ind.close_20d_high > 0 else 0.0
    ind.max_decline_5d = min(_daily_returns(rows[-6:]), default=0.0)
    ind.ma20_slope_5d = _ma_slope(rows, 20, 5)
    ind.ma50_slope_10d = _ma_slope(rows, 50, 10)

    ind.strength_trigger = _strength_trigger(rows, ind, config)
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


def _amplitude(rows: list[dict], days: int) -> float:
    if len(rows) <= days:
        return 0.0
    selected = rows[-days:]
    base = rows[-days - 1]["close"]
    return round((max(r["high"] for r in selected) - min(r["low"] for r in selected)) / base, 6) if base > 0 else 0.0


def _distance(close: float, value: float) -> float:
    return round(abs(close - value) / close, 6) if close > 0 and value > 0 else 0.0


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
    if _is_50d_quality_catchup(ind, config):
        return "ret_50d"
    return ""


def _is_50d_quality_catchup(ind: Strategy5Indicators, config: dict) -> bool:
    if ind.recent_50d_return < config["strength_ret_50d"]:
        return False
    if ind.recent_20d_return < config["strength_ret_50d_min_20d"]:
        return False
    if ind.ma20 <= 0 or ind.close < ind.ma20 * config["strength_ret_50d_ma20_ratio"]:
        return False
    if ind.amplitude_10d > config["strength_ret_50d_max_amp_10d"]:
        return False
    if ind.max_decline_5d < config["strength_ret_50d_max_decline_5d"]:
        return False
    return True


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

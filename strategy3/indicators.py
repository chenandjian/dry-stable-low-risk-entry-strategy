"""策略3指标计算。"""
from __future__ import annotations

from strategy3.models import Strategy3Indicators


def compute_indicators(
    data: list[dict],
    config: dict,
    market_data: list[dict] | None = None,
) -> Strategy3Indicators:
    close = float(data[-1]["close"])
    recent_high = _max(data[-int(config["pullback_lookback_days"]):], "high")
    high_120 = _max(data[-120:], "high")
    return_60 = _return(data, 60)
    index_return_60 = _return(market_data, 60) if market_data else 0.0
    ma60 = _ma(data, 60)
    ma60_20_days_ago = _ma(data[:-20], 60) if len(data) >= 80 else 0.0

    v5 = _avg(data[-5:], "volume")
    v10 = _avg(data[-10:], "volume")
    v20 = _avg(data[-20:], "volume")
    down_days = [row for row in data[-20:] if float(row["close"]) < float(row["open"])]
    down_day_avg_volume = _avg(down_days, "volume") if down_days else 0.0

    last5 = data[-5:]
    close_values = [float(row["close"]) for row in last5]
    high5 = max(float(row["high"]) for row in last5)
    low5 = min(float(row["low"]) for row in last5)

    return Strategy3Indicators(
        ma5=_ma(data, 5),
        ma10=_ma(data, 10),
        ma20=_ma(data, 20),
        ma60=ma60,
        ma120=_ma(data, 120),
        return_3=_return(data, 3),
        return_20=_return(data, 20),
        return_60=return_60,
        return_120=_return(data, 120),
        high_120=high_120,
        drawdown_from_high_120=(high_120 - close) / high_120 if high_120 > 0 else 0.0,
        relative_strength_60=return_60 - index_return_60,
        ma60_slope_20=(ma60 / ma60_20_days_ago - 1) if ma60_20_days_ago > 0 else 0.0,
        recent_high=recent_high,
        pullback_pct=(recent_high - close) / recent_high if recent_high > 0 else 0.0,
        range_5=(high5 - low5) / close if close > 0 else 0.0,
        close_range_5=(max(close_values) - min(close_values)) / close if close > 0 else 0.0,
        volume_ratio_5_20=v5 / v20 if v20 > 0 else 0.0,
        v5=v5,
        v10=v10,
        v20=v20,
        down_day_volume_ratio=down_day_avg_volume / v20 if v20 > 0 else 0.0,
        current_close=close,
    )


def _ma(data: list[dict], days: int) -> float:
    if len(data) < days:
        return 0.0
    return _avg(data[-days:], "close")


def _avg(data: list[dict], field: str) -> float:
    if not data:
        return 0.0
    return sum(float(row[field]) for row in data) / len(data)


def _max(data: list[dict], field: str) -> float:
    if not data:
        return 0.0
    return max(float(row[field]) for row in data)


def _return(data: list[dict] | None, days: int) -> float:
    if not data or len(data) <= days:
        return 0.0
    base = float(data[-days - 1]["close"])
    if base <= 0:
        return 0.0
    return float(data[-1]["close"]) / base - 1


"""Strategy4 topic index OHLC analysis."""
from __future__ import annotations


UNOBSERVED_TOPIC_INDEX = "UNOBSERVED_TOPIC_INDEX"


def analyze_topic_index(rows: list[dict], *, min_required_rows: int = 60) -> dict:
    """Calculate trend/breakout/volume/risk context from topic index OHLC."""
    rows = sorted(rows or [], key=lambda r: str(r.get("date") or ""))
    if len(rows) < min_required_rows:
        return _unobserved("INSUFFICIENT_TOPIC_INDEX_ROWS", rows)

    closes = [_float(r.get("close")) for r in rows]
    amounts = [_float(r.get("amount") or r.get("turnover")) for r in rows]
    latest = rows[-1]
    latest_close = closes[-1]
    ma5 = _avg(closes[-5:])
    ma10 = _avg(closes[-10:])
    ma20 = _avg(closes[-20:])
    ma60 = _avg(closes[-60:]) if len(closes) >= 60 else _avg(closes)
    ma20_prev = _avg(closes[-40:-20]) if len(closes) >= 40 else ma20
    ma60_prev = _avg(closes[-120:-60]) if len(closes) >= 120 else ma60

    ret1 = _return(closes, 1)
    ret3 = _return(closes, 3)
    ret5 = _return(closes, 5)
    ret10 = _return(closes, 10)
    ret20 = _return(closes, 20)
    ret60 = _return(closes, 60)
    high20 = max(_float(r.get("high")) for r in rows[-20:])
    high60 = max(_float(r.get("high")) for r in rows[-60:]) if len(rows) >= 60 else high20
    prev_high20 = max(_float(r.get("high")) for r in rows[-21:-1]) if len(rows) >= 21 else high20
    amount_ma5 = _avg(amounts[-5:])
    amount_ma20 = _avg(amounts[-20:])
    amount_ratio_5_20 = amount_ma5 / amount_ma20 if amount_ma20 > 0 else 0.0
    amount_ratio_1_20 = amounts[-1] / amount_ma20 if amount_ma20 > 0 else 0.0
    drawdown20 = latest_close / high20 - 1.0 if high20 > 0 else 0.0
    down_days_5 = sum(1 for i in range(max(1, len(closes) - 4), len(closes)) if closes[i] < closes[i - 1])
    large_down_5 = sum(
        1 for i in range(max(1, len(closes) - 4), len(closes))
        if closes[i - 1] > 0 and closes[i] / closes[i - 1] - 1 <= -0.03
    )

    trend_score = 0.0
    if latest_close > ma5:
        trend_score += 4
    if latest_close > ma10:
        trend_score += 4
    if latest_close > ma20:
        trend_score += 5
    if latest_close > ma60:
        trend_score += 3
    if ma20 > ma20_prev:
        trend_score += 4

    breakout_score = 0.0
    latest_high = _float(latest.get("high"))
    breakout20 = latest_high >= prev_high20 if prev_high20 > 0 else False
    new_high60 = latest_high >= high60 if high60 > 0 else False
    if breakout20:
        breakout_score += 8
    if new_high60:
        breakout_score += 7

    volume_score = 0.0
    if amount_ratio_5_20 >= 1.0:
        volume_score += min(8.0, (amount_ratio_5_20 - 1.0) / 0.5 * 8)
    if amount_ratio_1_20 >= 1.2:
        volume_score += min(7.0, (amount_ratio_1_20 - 1.2) / 0.8 * 7)

    risk_flags: list[str] = []
    risk_penalty = 0.0
    if latest_close < ma20:
        risk_flags.append("close_below_ma20")
        risk_penalty -= 6
    if drawdown20 <= -0.12:
        risk_flags.append("drawdown_from_high_20")
        risk_penalty -= 6
    if down_days_5 >= 3:
        risk_flags.append("three_down_days_5")
        risk_penalty -= 4
    if large_down_5:
        risk_flags.append("large_down_day_5")
        risk_penalty -= 4

    phase = _phase(trend_score, breakout_score, risk_penalty, ret5, drawdown20, latest_close, ma20)
    return {
        "observed": True,
        "status": "observed",
        "latest_date": str(latest.get("date") or ""),
        "rows": len(rows),
        "phase": phase,
        "topic_return_1d": round(ret1, 4),
        "topic_return_3d": round(ret3, 4),
        "topic_return_5d": round(ret5, 4),
        "topic_return_10d": round(ret10, 4),
        "topic_return_20d": round(ret20, 4),
        "topic_return_60d": round(ret60, 4),
        "ma5": round(ma5, 4),
        "ma10": round(ma10, 4),
        "ma20": round(ma20, 4),
        "ma60": round(ma60, 4),
        "ma20_slope": round(ma20 / ma20_prev - 1.0, 4) if ma20_prev > 0 else 0.0,
        "ma60_slope": round(ma60 / ma60_prev - 1.0, 4) if ma60_prev > 0 else 0.0,
        "new_high_20": bool(breakout20),
        "new_high_60": bool(new_high60),
        "breakout_20": bool(breakout20),
        "drawdown_from_high_20": round(drawdown20, 4),
        "drawdown_from_high_60": round(latest_close / high60 - 1.0, 4) if high60 > 0 else 0.0,
        "amount_ratio_5_20": round(amount_ratio_5_20, 4),
        "amount_ratio_1_20": round(amount_ratio_1_20, 4),
        "topic_index_trend_score": round(min(20.0, trend_score), 2),
        "topic_index_breakout_score": round(min(15.0, breakout_score), 2),
        "topic_index_volume_score": round(min(15.0, volume_score), 2),
        "topic_index_risk_penalty": round(risk_penalty, 2),
        "topic_index_risk_flags": risk_flags,
    }


def _unobserved(status: str, rows: list[dict]) -> dict:
    return {
        "observed": False,
        "status": status,
        "latest_date": str(rows[-1].get("date") or "") if rows else "",
        "rows": len(rows),
        "phase": UNOBSERVED_TOPIC_INDEX,
        "topic_index_trend_score": 0.0,
        "topic_index_breakout_score": 0.0,
        "topic_index_volume_score": 0.0,
        "topic_index_risk_penalty": 0.0,
        "topic_index_risk_flags": [status],
    }


def _phase(trend_score: float, breakout_score: float, risk_penalty: float, ret5: float, drawdown20: float, close: float, ma20: float) -> str:
    if risk_penalty <= -10 or close < ma20 * 0.98:
        return "WEAK_NOISE"
    if ret5 >= 0.08 and drawdown20 > -0.03:
        return "HIGH_RISK_CLIMAX"
    if breakout_score >= 8 and trend_score >= 12:
        return "EARLY_ACCELERATION"
    if trend_score >= 12:
        return "MAIN_TREND"
    if trend_score >= 8 and drawdown20 > -0.12:
        return "PULLBACK_REPAIR"
    return "WEAK_NOISE"


def _return(values: list[float], days: int) -> float:
    if len(values) <= days or values[-days - 1] <= 0:
        return 0.0
    return values[-1] / values[-days - 1] - 1.0


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _float(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0

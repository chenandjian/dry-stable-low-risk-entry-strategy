"""Formal Strategy6 long-term trend and volatility-squeeze gate."""
from __future__ import annotations

from strategy6.models import Strategy6StrongTrendSqueeze
from strategy6.ttm_squeeze import _ema_series, calculate_ttm_squeeze


FORMAL_SQUEEZE_CONFIG = {
    "enabled": True,
    "bb_period": 20,
    "bb_stddev": 2.0,
    "kc_ema_period": 20,
    "kc_atr_period": 20,
    "kc_atr_multiplier": 1.5,
    "momentum_period": 20,
    "bullish_squeeze_min_days": 3,
    "max_ranking_bonus": 4,
}


def evaluate_strong_trend_squeeze(rows: list[dict] | None) -> Strategy6StrongTrendSqueeze:
    """Evaluate the fixed all-of formal prefilter as of the last row."""
    result = Strategy6StrongTrendSqueeze()
    rows = rows or []
    if len(rows) < 250:
        result.reasons = ["TREND_SQUEEZE_HISTORY_LT_250"]
        return result

    closes = [float(row["close"]) for row in rows]
    recent = rows[-250:]
    squeeze = calculate_ttm_squeeze(rows, FORMAL_SQUEEZE_CONFIG)
    ema150 = _ema_series(closes, 150)[-1]
    ema200 = _ema_series(closes, 200)[-1]
    if ema150 is None or ema200 is None or squeeze.status == "INSUFFICIENT_DATA":
        result.reasons = ["TREND_SQUEEZE_DATA_INSUFFICIENT"]
        return result

    close = closes[-1]
    low_250 = min(float(row["low"]) for row in recent)
    high_250 = max(float(row["high"]) for row in recent)
    result.calculable = True
    result.close = round(close, 4)
    result.low_250 = round(low_250, 4)
    result.high_250 = round(high_250, 4)
    result.close_to_low_ratio = round(close / low_250, 6) if low_250 > 0 else 0.0
    result.close_to_high_ratio = round(close / high_250, 6) if high_250 > 0 else 0.0
    result.ema150 = round(float(ema150), 4)
    result.ema200 = round(float(ema200), 4)
    result.squeeze_on = squeeze.squeeze_on
    result.bb_upper = squeeze.bb_upper
    result.bb_lower = squeeze.bb_lower
    result.kc_upper = squeeze.kc_upper
    result.kc_lower = squeeze.kc_lower
    result.apply_rules()
    return result

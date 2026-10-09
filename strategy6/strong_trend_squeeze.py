"""Formal Strategy6 long-term trend and volatility-squeeze gate."""
from __future__ import annotations

from collections import deque

from strategy6.models import Strategy6StrongTrendSqueeze
from strategy6.ttm_squeeze import (
    _ema_series, _sma_series, _wilder_atr_series, _population_stddev,
    _bands_inside_keltner, _valid_ohlc_rows, calculate_ttm_squeeze,
)


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

SQUEEZE_DIAGNOSTIC_REASONS = {"BB_NOT_INSIDE_KC"}


def main_chain_trend_reasons(result: Strategy6StrongTrendSqueeze) -> list[str]:
    """Return only the long-term trend failures used by the main chain."""
    return [reason for reason in result.reasons if reason not in SQUEEZE_DIAGNOSTIC_REASONS]


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


def evaluate_strong_trend_squeeze_history(rows: list[dict]) -> list[Strategy6StrongTrendSqueeze]:
    """Causal daily prefilter replay using the same math and rule model."""
    invalid_at = next((i for i, row in enumerate(rows) if not _valid_ohlc_rows([row])), len(rows))
    valid_rows = rows[:invalid_at]
    closes = [float(row['close']) for row in valid_rows]
    ema150, ema200 = _ema_series(closes, 150), _ema_series(closes, 200)
    bb_middle = _sma_series(closes, FORMAL_SQUEEZE_CONFIG['bb_period'])
    kc_middle = _ema_series(closes, FORMAL_SQUEEZE_CONFIG['kc_ema_period'])
    atr = _wilder_atr_series(valid_rows, FORMAL_SQUEEZE_CONFIG['kc_atr_period'])
    highs, lows, result = deque(), deque(), []
    for i, row in enumerate(rows):
        if i < 249:
            item = Strategy6StrongTrendSqueeze(reasons=['TREND_SQUEEZE_HISTORY_LT_250'])
        else:
            item = Strategy6StrongTrendSqueeze(reasons=['TREND_SQUEEZE_DATA_INSUFFICIENT'])
        if i < invalid_at:
            high, low = float(row['high']), float(row['low'])
            while highs and float(rows[highs[-1]]['high']) <= high:
                highs.pop()
            while lows and float(rows[lows[-1]]['low']) >= low:
                lows.pop()
            highs.append(i)
            lows.append(i)
            while highs[0] <= i-250:
                highs.popleft()
            while lows[0] <= i-250:
                lows.popleft()
            if i >= 249:
                deviation = _population_stddev(closes[i-19:i+1])
                bb_upper = bb_middle[i] + FORMAL_SQUEEZE_CONFIG['bb_stddev']*deviation
                bb_lower = bb_middle[i] - FORMAL_SQUEEZE_CONFIG['bb_stddev']*deviation
                kc_upper = kc_middle[i] + FORMAL_SQUEEZE_CONFIG['kc_atr_multiplier']*atr[i]
                kc_lower = kc_middle[i] - FORMAL_SQUEEZE_CONFIG['kc_atr_multiplier']*atr[i]
                low_250, high_250 = float(rows[lows[0]]['low']), float(rows[highs[0]]['high'])
                item = Strategy6StrongTrendSqueeze(
                    calculable=True, close=round(closes[i], 4), low_250=round(low_250, 4),
                    high_250=round(high_250, 4), close_to_low_ratio=round(closes[i]/low_250, 6),
                    close_to_high_ratio=round(closes[i]/high_250, 6),
                    ema150=round(ema150[i], 4), ema200=round(ema200[i], 4),
                    squeeze_on=_bands_inside_keltner(bb_upper, bb_lower, kc_upper, kc_lower),
                    bb_upper=bb_upper, bb_lower=bb_lower, kc_upper=kc_upper, kc_lower=kc_lower,
                )
                item.apply_rules()
        result.append(item)
    return result

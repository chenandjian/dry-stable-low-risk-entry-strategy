"""Strategy4 second-wave trigger detection."""
from __future__ import annotations

from strategy4.models import SecondWaveResult


def evaluate_second_wave(data: list[dict]) -> SecondWaveResult:
    if len(data) < 10:
        return SecondWaveResult(False, reject_reasons=["INSUFFICIENT_DATA"])

    close = float(data[-1]["close"])
    open_ = float(data[-1]["open"])
    low = float(data[-1]["low"])
    ma5 = _ma(data, 5)
    ma10 = _ma(data, 10)
    volume = float(data[-1].get("volume") or 0)
    avg_volume_5 = sum(float(r.get("volume") or 0) for r in data[-6:-1]) / 5

    signals: list[str] = []
    if close > ma5:
        signals.append("close_above_ma5")
    if close > ma10:
        signals.append("close_above_ma10")
    if close > open_:
        signals.append("bullish_close")
    if min(open_, close) > low and (min(open_, close) - low) / close >= 0.02:
        signals.append("lower_shadow_repair")
    if avg_volume_5 > 0 and 1.05 <= volume / avg_volume_5 <= 1.8:
        signals.append("moderate_volume_expansion")

    passed = "close_above_ma5" in signals and ("bullish_close" in signals or "lower_shadow_repair" in signals)
    return SecondWaveResult(passed=passed, signals=signals, reject_reasons=[] if passed else ["NO_SECOND_WAVE_TRIGGER"])


def _ma(data: list[dict], days: int) -> float:
    closes = [float(r["close"]) for r in data[-days:]]
    return sum(closes) / len(closes)


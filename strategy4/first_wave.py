"""Strategy4 first-wave confirmation."""
from __future__ import annotations

from strategy4.models import FirstWaveResult


def evaluate_first_wave(data: list[dict], config: dict) -> FirstWaveResult:
    if not data:
        return FirstWaveResult(False, reject_reasons=["INSUFFICIENT_DATA"])

    long = int(config.get("first_wave_lookback_long", 20))
    window = data[-long:] if len(data) >= long else data
    closes = [float(r["close"]) for r in window]
    low = min(closes)
    high = max(closes)
    first_wave_return = (high - low) / low if low > 0 else 0.0
    strong_days = _count_strong_days(window)

    reasons: list[str] = []
    passed = False
    if first_wave_return >= float(config.get("min_first_wave_return_20d", 0.35)):
        passed = True
        reasons.append("return_20d_strong")
    elif _short_return(data, int(config.get("first_wave_lookback_short", 10))) >= float(config.get("min_first_wave_return_10d", 0.25)):
        passed = True
        reasons.append("return_10d_strong")
    elif strong_days >= int(config.get("min_strong_day_count_10d", 2)):
        passed = True
        reasons.append("strong_day_cluster")

    return FirstWaveResult(
        passed=passed,
        first_wave_return=round(first_wave_return, 4),
        strong_day_count=strong_days,
        reasons=reasons,
        reject_reasons=[] if passed else ["NO_FIRST_WAVE"],
    )


def _short_return(data: list[dict], days: int) -> float:
    window = data[-days:] if len(data) >= days else data
    closes = [float(r["close"]) for r in window]
    low = min(closes)
    high = max(closes)
    return (high - low) / low if low > 0 else 0.0


def _count_strong_days(data: list[dict]) -> int:
    count = 0
    for prev, row in zip(data, data[1:]):
        prev_close = float(prev["close"])
        close = float(row["close"])
        if prev_close > 0 and (close - prev_close) / prev_close >= 0.08:
            count += 1
    return count


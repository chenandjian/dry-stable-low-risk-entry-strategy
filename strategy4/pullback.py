"""Strategy4 healthy pullback detection."""
from __future__ import annotations

from strategy4.models import PullbackResult


def evaluate_pullback(data: list[dict], config: dict) -> PullbackResult:
    if len(data) < 5:
        return PullbackResult(False, reject_reasons=["INSUFFICIENT_DATA"])

    closes = [float(r["close"]) for r in data]
    high_idx = max(range(len(closes)), key=lambda i: closes[i])
    after_high = data[high_idx + 1:]
    if not after_high:
        return PullbackResult(False, reject_reasons=["NO_PULLBACK_AFTER_HIGH"])

    lows_after = [float(r["low"]) for r in after_high]
    low_rel_idx = min(range(len(lows_after)), key=lambda i: lows_after[i])
    high = closes[high_idx]
    low = lows_after[low_rel_idx]
    pct = (high - low) / high if high > 0 else 0.0
    days = low_rel_idx + 1

    rejects: list[str] = []
    if pct < float(config.get("pullback_min_pct", 0.08)):
        rejects.append("PULLBACK_TOO_SHALLOW")
    if pct > float(config.get("pullback_max_pct", 0.25)):
        rejects.append("PULLBACK_TOO_DEEP")
    if days < int(config.get("pullback_min_days", 2)):
        rejects.append("PULLBACK_TOO_SHORT")
    if days > int(config.get("pullback_max_days", 8)):
        rejects.append("PULLBACK_TOO_LONG")
    if _has_consecutive_heavy_bear_days(after_high):
        rejects.append("CONSECUTIVE_HEAVY_BEAR_DAYS")

    return PullbackResult(
        passed=not rejects,
        pullback_pct=round(pct, 4),
        pullback_days=days,
        reasons=[] if rejects else ["healthy_pullback"],
        reject_reasons=rejects,
    )


def _has_consecutive_heavy_bear_days(rows: list[dict]) -> bool:
    if len(rows) < 2:
        return False
    volumes = [float(r.get("volume") or 0) for r in rows]
    avg_volume = sum(volumes) / len(volumes) if volumes else 0.0
    streak = 0
    for row in rows:
        open_ = float(row["open"])
        close = float(row["close"])
        volume = float(row.get("volume") or 0)
        drop = (close - open_) / open_ if open_ > 0 else 0.0
        if drop <= -0.04 and volume >= avg_volume * 1.2:
            streak += 1
            if streak >= 2:
                return True
        else:
            streak = 0
    return False


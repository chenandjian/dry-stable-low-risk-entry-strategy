"""Strategy6 upper pressure risk tags."""
from __future__ import annotations

from strategy6.models import Strategy6Indicators


def apply_pressure_tags(rows: list[dict], ind: Strategy6Indicators) -> None:
    if ind.highest_close_120 > 0:
        room = ind.highest_close_120 / ind.current_price - 1 if ind.current_price > 0 else 0.0
        if 0 <= room < 0.03 and ind.volume_ratio_5_20 < 1.3:
            ind.warn_tags.append("PRESSURE_NEAR_HIGH")
    if _has_upper_shadow_pressure(rows, ind):
        ind.warn_tags.append("UPPER_SHADOW_PRESSURE")


def _has_upper_shadow_pressure(rows: list[dict], ind: Strategy6Indicators) -> bool:
    if ind.v20 <= 0 or ind.current_price <= 0:
        return False
    for row in rows[-60:]:
        span = row["high"] - row["low"]
        if span <= 0:
            continue
        upper_shadow_ratio = (row["high"] - max(row["open"], row["close"])) / span
        near = abs(ind.current_price - row["high"]) / ind.current_price <= 0.05
        if upper_shadow_ratio >= 0.45 and row["volume"] >= ind.v20 * 1.8 and near:
            return True
    return False


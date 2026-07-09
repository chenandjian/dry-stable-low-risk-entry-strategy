"""Strategy6 sector context derived from cached Strategy4 topic data."""
from __future__ import annotations


def evaluate_sector_context(stock_return_10: float, topic_rows: list[dict] | None) -> dict:
    rows = sorted([row for row in (topic_rows or []) if isinstance(row, dict)], key=lambda r: str(r.get("date") or ""))
    if len(rows) <= 20:
        return {
            "sector_strength_status": "UNKNOWN",
            "relative_strength_10_sector": 0.0,
            "sector_return_10": 0.0,
            "sector_return_20": 0.0,
        }

    ret10 = _return(rows, 10)
    ret20 = _return(rows, 20)
    if ret10 >= 0.05 and ret20 >= 0.08:
        status = "SECTOR_STRONG"
    elif ret10 <= 0 and ret20 <= 0:
        status = "SECTOR_WEAK"
    else:
        status = "SECTOR_NEUTRAL"

    return {
        "sector_strength_status": status,
        "relative_strength_10_sector": round(stock_return_10 - ret10, 6),
        "sector_return_10": round(ret10, 6),
        "sector_return_20": round(ret20, 6),
    }


def _return(rows: list[dict], days: int) -> float:
    if len(rows) <= days:
        return 0.0
    base = float(rows[-days - 1].get("close") or 0.0)
    close = float(rows[-1].get("close") or 0.0)
    return close / base - 1.0 if base > 0 and close > 0 else 0.0

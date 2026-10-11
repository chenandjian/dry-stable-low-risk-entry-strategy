"""Read-only rising support-zone diagnostic for batch evaluation."""
from __future__ import annotations

from datetime import date
from math import isfinite

from strategy6.ttm_squeeze import _wilder_atr_series

WINDOW_DAYS = 60
MERGE_ATR = 0.5
TOLERANCE = 0.01
MODEL_VERSION = "RISING_SUPPORT_ZONES_V1"
REASONS = {
    "INSUFFICIENT": "有效支撑区不足两个",
    "LOWER_SUPPORT": "后续支撑低于固定基准的容差下沿",
    "NO_RISE": "最近支撑区没有超过1%的真实抬高",
    "SUPPORT_BROKEN": "后续价格已跌破支撑防护条件",
    "MATCHED": "支撑区域抬高且当前仍守住",
    "DATA_INSUFFICIENT": "至少需要60根完整日线",
    "DATA_INVALID": "日线价格或日期无效",
}


def evaluate_rising_support(rows: list[dict] | None) -> dict:
    result = dict(modelVersion=MODEL_VERSION, matched=None, status="DATA_INSUFFICIENT",
                  reason="DATA_INSUFFICIENT", reasonText=REASONS["DATA_INSUFFICIENT"],
                  evaluationDate=None, windowStart=None, zones=[], supportPrice=None,
                  distancePct=None, pendingLow=None, windowDays=WINDOW_DAYS,
                  mergeWidthAtr=MERGE_ATR, tolerancePct=TOLERANCE * 100)
    if not rows or len(rows) < WINDOW_DAYS:
        return result
    selected = []
    previous_date = None
    try:
        for row in rows:
            day = date.fromisoformat(row["date"])
            prices = {key: float(row[key]) for key in ("open", "high", "low", "close")}
            if (previous_date is not None and day <= previous_date
                    or not all(isfinite(value) and value > 0 for value in prices.values())
                    or prices["low"] > min(prices["open"], prices["close"])
                    or prices["high"] < max(prices["open"], prices["close"])):
                raise ValueError("invalid OHLC or date order")
            selected.append(dict(date=day.isoformat(), **prices))
            previous_date = day
    except (KeyError, TypeError, ValueError, OverflowError):
        result.update(status="DATA_INVALID", reason="DATA_INVALID", reasonText=REASONS["DATA_INVALID"])
        return result
    pivots, pending = _confirmed_lows(selected)
    pivots = [p for p in pivots if p["index"] >= len(selected) - WINDOW_DAYS]
    zones = _merge_zones(selected, pivots)
    checks = [_check_chain(selected, zones, count) for count in (2, 3)]
    chosen = next((item for item in checks if item["matched"]), checks[1] if len(zones) >= 3 else checks[0])
    matched = chosen["matched"]
    support = chosen.get("support")
    result.update(
        matched=matched, status="MATCHED" if matched else "NOT_MATCHED",
        reason=chosen["reason"], reasonText=REASONS[chosen["reason"]],
        evaluationDate=selected[-1]["date"], windowStart=selected[-WINDOW_DAYS]["date"],
        zones=[{key: round(value, 6) if isinstance(value, float) else value
                for key, value in zone.items() if key not in ("firstIndex", "lastIndex")}
               for zone in zones],
        supportPrice=round(support, 6) if support is not None else None,
        distancePct=round((selected[-1]["close"] / support - 1) * 100, 4) if support else None,
        pendingLow=dict(date=selected[pending]["date"], price=selected[pending]["low"])
        if pending is not None and pending >= len(selected) - WINDOW_DAYS else None,
    )
    return result


def _confirmed_lows(rows: list[dict]) -> tuple[list[dict], int | None]:
    atr = _wilder_atr_series(rows, 14)
    pivots = []
    peak, trough = 13, None
    for i in range(14, len(rows)):
        row = rows[i]
        if trough is None:
            if row["close"] >= rows[peak]["close"]:
                peak = i
                continue
            if rows[peak]["close"] - row["close"] < atr[i]:
                continue
            trough = min(range(peak + 1, i + 1), key=lambda j: rows[j]["low"])
        if row["low"] < rows[trough]["low"]:
            trough = i
        # Only completed bars after the low can confirm it; new lows restart confirmation.
        if (i - trough >= 2 and row["close"] >= rows[trough]["low"] + atr[trough]
                and all(rows[j]["close"] > rows[trough]["low"] for j in (i - 1, i))):
            pivots.append(dict(index=trough, date=rows[trough]["date"], low=rows[trough]["low"],
                               confirmedDate=row["date"], atr=atr[trough]))
            peak, trough = i, None
    return pivots, trough


def _merge_zones(rows: list[dict], pivots: list[dict]) -> list[dict]:
    zones = []
    for pivot in pivots:
        if zones:
            zone = zones[-1]
            lowest = min(range(zone["firstIndex"], pivot["index"] + 1), key=lambda j: rows[j]["low"])
            ceiling = max(zone["upperLow"], pivot["low"])
            # Total width is anchored once, not rolled down with each new touch.
            if ceiling - rows[lowest]["low"] <= zone["anchorAtr"] * MERGE_ATR:
                zone.update(lastIndex=pivot["index"], endDate=pivot["date"],
                            confirmedDate=pivot["confirmedDate"], low=rows[lowest]["low"],
                            lowDate=rows[lowest]["date"], upperLow=ceiling, touchCount=zone["touchCount"] + 1)
                continue
        zones.append(dict(firstIndex=pivot["index"], lastIndex=pivot["index"],
                          startDate=pivot["date"], endDate=pivot["date"], lowDate=pivot["date"],
                          low=pivot["low"], upperLow=pivot["low"], anchorAtr=pivot["atr"],
                          confirmedDate=pivot["confirmedDate"], touchCount=1))
    return zones


def _check_chain(rows: list[dict], zones: list[dict], count: int) -> dict:
    if len(zones) < count:
        return dict(matched=False, reason="INSUFFICIENT")
    chain = zones[-count:]
    benchmark, rise = chain[0]["low"], False
    for zone in chain[1:]:
        if zone["low"] < benchmark * (1 - TOLERANCE):
            return dict(matched=False, reason="LOWER_SUPPORT", support=benchmark)
        rise = rise or zone["low"] > benchmark * (1 + TOLERANCE)
        benchmark = max(benchmark, zone["low"])
    if not rise:
        return dict(matched=False, reason="NO_RISE", support=benchmark)
    for row in rows[chain[-1]["lastIndex"] + 1:]:
        if row["low"] < benchmark * (1 - TOLERANCE) or row["close"] < benchmark:
            return dict(matched=False, reason="SUPPORT_BROKEN", support=benchmark)
    return dict(matched=True, reason="MATCHED", support=benchmark)

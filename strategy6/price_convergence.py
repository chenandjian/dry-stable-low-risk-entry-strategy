"""Conservative, read-only joint support/pressure convergence diagnostic."""
from __future__ import annotations

from strategy6.rising_support import (
    WINDOW_DAYS, _confirmed_lows, _merge_zones, _check_chain, evaluate_rising_support,
)

REASONS = {
    "MATCHED": "支撑抬高、压力下移，交替整理区间收窄且未破坏",
    "LOW_NOT_RISING": "有效支撑尚未形成抬高结构或已经破坏",
    "HIGH_NOT_LOWER": "最近有效压力没有形成降低结构",
    "INSUFFICIENT_HIGHS": "已确认压力区域不足两个",
    "TIME_NOT_PAIRED": "支撑与压力证据未形成同段交替整理",
    "NO_RANGE_CONTRACTION": "上下边界没有形成有效收窄区间",
    "UPPER_BREACH": "旧压力已被刺破或突破，结构需重新确认",
    "SUPPORT_BROKEN": "支撑已破坏，不属于当前有效收敛",
}


def evaluate_price_convergence(rows: list[dict] | None) -> dict:
    base = evaluate_rising_support(rows)
    result = dict(modelVersion="PRICE_CONVERGENCE_V1", matched=None, status=base["status"],
                  reason=base["reason"], reasonText=base["reasonText"],
                  evaluationDate=base["evaluationDate"], windowStart=base["windowStart"],
                  supportPrice=None, pressurePrice=None, contractionPct=None,
                  previousWidth=None, currentWidth=None, breachDate=None, breachType=None,
                  lowZones=base["zones"], highZones=[], matchedLowZones=[], matchedHighZones=[])
    if base["matched"] is None:
        return result
    selected = [dict(date=r["date"], **{key: float(r[key]) for key in ("open", "high", "low", "close")})
                for r in rows]
    cut = len(selected) - WINDOW_DAYS
    pivots, _ = _confirmed_lows(selected)
    lows = _merge_zones(selected, [p for p in pivots if p["index"] >= cut])
    # Vertical reflection preserves true range/ATR and reuses causal low confirmation.
    mirrored = [dict(date=r["date"], open=-r["open"], close=-r["close"],
                     low=-r["high"], high=-r["low"]) for r in selected]
    peaks, pending = _confirmed_lows(mirrored)
    raw = _merge_zones(mirrored, [p for p in peaks if p["index"] >= cut])
    highs = [dict(firstIndex=z["firstIndex"], lastIndex=z["lastIndex"],
                  startDate=z["startDate"], endDate=z["endDate"], highDate=z["lowDate"],
                  high=-z["low"], confirmedDate=z["confirmedDate"], touchCount=z["touchCount"])
             for z in raw]
    result["highZones"] = [_public_zone(z) for z in highs]
    candidates = []
    for nh in (2, 3):
        if len(highs) < nh or _pressure_shape(highs[-nh:]) is None:
            continue
        for nl in (2, 3):
            if len(lows) >= nl and _check_chain(selected, lows, nl)["matched"]:
                candidates.append(_evaluate_pair(selected, lows[-nl:], highs[-nh:]))
    if candidates:
        chosen = next((x for x in candidates if x["reason"] == "MATCHED"),
                      next((x for x in candidates if x["reason"] == "UPPER_BREACH"), candidates[0]))
        result.update(chosen)
        result["matched"] = chosen["reason"] == "MATCHED"
        result["status"] = "MATCHED" if result["matched"] else "NOT_MATCHED"
    else:
        forming = ((base["matched"] or base["reason"] == "INSUFFICIENT")
                   and (len(highs) < 2 and pending is not None and pending >= cut
                        or len(lows) < 2 and base["pendingLow"] is not None))
        reason = "LOW_NOT_RISING" if not base["matched"] else (
            "INSUFFICIENT_HIGHS" if len(highs) < 2 else "HIGH_NOT_LOWER")
        result.update(matched=False, status="FORMING" if forming else "NOT_MATCHED", reason=reason)
    result["reasonText"] = REASONS[result["reason"]]
    return result


def _pressure_shape(chain: list[dict]) -> float | None:
    benchmark, lowered = chain[0]["high"], False
    for zone in chain[1:]:
        if zone["high"] > benchmark * 1.01:
            return None
        lowered = lowered or zone["high"] < benchmark * .99
        benchmark = min(benchmark, zone["high"])
    return benchmark if lowered else None


def _evaluate_pair(rows: list[dict], lows: list[dict], highs: list[dict]) -> dict:
    nodes = sorted([(z["lowDate"], "L") for z in lows] + [(z["highDate"], "H") for z in highs])
    overlap = max(lows[0]["firstIndex"], highs[0]["firstIndex"]) < min(
        lows[-1]["lastIndex"], highs[-1]["lastIndex"])
    alternating = len(nodes) >= 4 and all(
        nodes[i][0] != nodes[i - 1][0] and nodes[i][1] != nodes[i - 1][1]
        for i in range(1, len(nodes)))
    if not overlap or not alternating:
        return dict(reason="TIME_NOT_PAIRED")
    old_width = highs[0]["high"] - lows[0]["low"]
    new_width = highs[-1]["high"] - lows[-1]["low"]
    if old_width <= 0 or new_width <= 0 or new_width >= old_width:
        return dict(reason="NO_RANGE_CONTRACTION")
    support = _check_chain(rows, lows, len(lows))
    if not support["matched"]:
        return dict(reason="SUPPORT_BROKEN")
    pressure = _pressure_shape(highs)
    if pressure is None:
        return dict(reason="HIGH_NOT_LOWER")
    evidence = dict(supportPrice=round(support["support"], 6), pressurePrice=round(pressure, 6),
                    previousWidth=round(old_width, 6), currentWidth=round(new_width, 6),
                    contractionPct=round((1 - new_width / old_width) * 100, 4),
                    matchedLowZones=[_public_zone(z) for z in lows],
                    matchedHighZones=[_public_zone(z) for z in highs])
    for row in rows[highs[-1]["lastIndex"] + 1:]:
        if row["high"] > pressure * 1.01 or row["close"] > pressure:
            return dict(reason="UPPER_BREACH", breachDate=row["date"],
                        breachType="CLOSE" if row["close"] > pressure else "WICK", **evidence)
    return dict(reason="MATCHED", **evidence)


def _public_zone(zone: dict) -> dict:
    return {key: round(value, 6) if isinstance(value, float) else value
            for key, value in zone.items() if key not in ("firstIndex", "lastIndex")}

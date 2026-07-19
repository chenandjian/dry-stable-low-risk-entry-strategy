"""Strict non-overlapping phase segmentation for Strategy6."""
from __future__ import annotations

from strategy6.models import Strategy6Phase, Strategy6Start


def segment_phases(rows: list[dict], start: Strategy6Start, config: dict) -> Strategy6Phase:
    if not rows or not start.start_date:
        return Strategy6Phase(status="START_NOT_FOUND")

    start_index = next(
        (idx for idx, row in enumerate(rows) if str(row.get("date") or "") == start.start_date),
        -1,
    )
    if start_index < 0:
        return Strategy6Phase(status="START_NOT_FOUND")

    signal_index = len(rows) - 1
    start_age_days = signal_index - start_index
    tail_start_index, tail_metrics = _select_tail_start(rows, start_index, config)
    consolidation_start_index = start_index + 1
    consolidation_days = max(0, tail_start_index - consolidation_start_index)
    base = Strategy6Phase(
        start_index=start_index,
        consolidation_start_index=consolidation_start_index,
        tail_start_index=tail_start_index,
        signal_index=signal_index,
        start_date=rows[start_index]["date"],
        consolidation_start_date=rows[consolidation_start_index]["date"]
        if consolidation_start_index < len(rows) else "",
        tail_start_date=rows[tail_start_index]["date"],
        signal_date=rows[signal_index]["date"],
        start_age_days=start_age_days,
        consolidation_days=consolidation_days,
        tail_days=len(rows) - tail_start_index,
        tail_segmentation_status=tail_metrics["status"],
        tail_segmentation_score=tail_metrics["score"],
        tail_range_contraction_ratio=tail_metrics["range_ratio"],
        tail_atr_contraction_ratio=tail_metrics["atr_ratio"],
        tail_body_contraction_ratio=tail_metrics["body_ratio"],
    )
    if start_age_days < int(config["start_age_min_days"]):
        base.status = "START_TOO_RECENT"
        base.lifecycle_status = "START_CONFIRMED"
        return base
    if start_age_days > int(config["start_age_max_days"]):
        base.status = "START_TOO_OLD"
        base.lifecycle_status = "EXPIRED"
        return base
    if consolidation_days < int(config["consolidation_min_days"]):
        base.status = "CONSOLIDATION_TOO_SHORT"
        return base
    if consolidation_days > int(config["consolidation_max_days"]):
        base.status = "CONSOLIDATION_TOO_LONG"
        return base
    if not (
        start_index < consolidation_start_index < tail_start_index <= signal_index
    ):
        base.status = "PHASE_ORDER_INVALID"
        return base
    base.status = "PHASE_VALID"
    base.valid = True
    base.lifecycle_status = "SETUP_FORMING"
    return base


def _select_tail_start(rows: list[dict], start_index: int, config: dict) -> tuple[int, dict]:
    fallback_days = int(config["tail_window_days"])
    fallback_start = min(len(rows) - 1, max(start_index + 2, len(rows) - fallback_days))
    fallback = {
        "status": "FALLBACK_FIXED" if config.get("dynamic_tail_enabled", True) else "FIXED_WINDOW",
        "score": 0,
        "range_ratio": 0.0,
        "atr_ratio": 0.0,
        "body_ratio": 0.0,
    }
    if not config.get("dynamic_tail_enabled", True):
        return fallback_start, fallback

    baseline_days = int(config["dynamic_tail_baseline_days"])
    min_days = int(config["dynamic_tail_min_days"])
    max_days = min(int(config["dynamic_tail_max_days"]), len(rows) - start_index - 2)
    best_fallback_score = 0
    for days in range(max_days, min_days - 1, -1):
        tail_start = len(rows) - days
        baseline_start = tail_start - baseline_days
        if baseline_start <= start_index or tail_start <= start_index + 1:
            continue
        tail = rows[tail_start:]
        baseline = rows[baseline_start:tail_start]
        metrics = _contraction_metrics(tail, baseline, config)
        best_fallback_score = max(best_fallback_score, metrics["score"])
        if metrics["score"] >= int(config["dynamic_tail_min_score"]) and not _has_breakdown(tail, baseline):
            metrics["status"] = "DYNAMIC_CONTRACTION"
            return tail_start, metrics
    fallback["score"] = best_fallback_score
    return fallback_start, fallback


def _contraction_metrics(tail: list[dict], baseline: list[dict], config: dict) -> dict:
    tail_range = _price_range(tail)
    base_range = _price_range(baseline)
    tail_atr = _average_true_range(tail)
    base_atr = _average_true_range(baseline)
    tail_volume = _average(tail, "volume")
    base_volume = _average(baseline, "volume")
    tail_body = _average_body_ratio(tail)
    base_body = _average_body_ratio(baseline)
    range_ratio = tail_range / base_range if base_range > 0 else 0.0
    atr_ratio = tail_atr / base_atr if base_atr > 0 else 0.0
    volume_ratio = tail_volume / base_volume if base_volume > 0 else 0.0
    body_ratio = tail_body / base_body if base_body > 0 else 0.0
    score = sum((
        0 < range_ratio <= float(config["dynamic_tail_range_ratio_max"]),
        0 < atr_ratio <= float(config["dynamic_tail_atr_ratio_max"]),
        0 < volume_ratio <= float(config["dynamic_tail_volume_ratio_max"]),
        0 < body_ratio <= float(config["dynamic_tail_body_ratio_max"]),
    ))
    return {
        "status": "DYNAMIC_CONTRACTION",
        "score": int(score),
        "range_ratio": round(range_ratio, 6),
        "atr_ratio": round(atr_ratio, 6),
        "body_ratio": round(body_ratio, 6),
    }


def _price_range(rows: list[dict]) -> float:
    if not rows:
        return 0.0
    base = sum(float(row["close"]) for row in rows) / len(rows)
    return (max(float(row["high"]) for row in rows) - min(float(row["low"]) for row in rows)) / base if base > 0 else 0.0


def _average_true_range(rows: list[dict]) -> float:
    if not rows:
        return 0.0
    values = [float(row["high"]) - float(row["low"]) for row in rows]
    return sum(values) / len(values)


def _average(rows: list[dict], key: str) -> float:
    return sum(float(row[key]) for row in rows) / len(rows) if rows else 0.0


def _average_body_ratio(rows: list[dict]) -> float:
    values = [abs(float(row["close"]) - float(row["open"])) / float(row["close"]) for row in rows if float(row["close"]) > 0]
    return sum(values) / len(values) if values else 0.0


def _has_breakdown(tail: list[dict], baseline: list[dict]) -> bool:
    baseline_volume = _average(baseline, "volume")
    for previous, current in zip(tail, tail[1:]):
        previous_close = float(previous["close"])
        day_return = (float(current["close"]) - previous_close) / previous_close if previous_close > 0 else 0.0
        if day_return <= -0.07 and float(current["volume"]) >= baseline_volume * 1.5:
            return True
    return False

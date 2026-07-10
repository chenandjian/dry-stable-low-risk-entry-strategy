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
    tail_days = int(config["tail_window_days"])
    tail_start_index = max(0, len(rows) - tail_days)
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

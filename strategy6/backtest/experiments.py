"""Strategy6 legacy and authoritative-path experiment filters."""
from __future__ import annotations

from strategy6.backtest.metrics import calculate_trade_metrics
from strategy6.backtest.snapshot import authoritative_tail_paths, brooks_setup_types


BROOKS_STATUS_EXPERIMENTS = {
    "E9_BROOKS_STATUS_SECOND_ENTRY_LONG_READY": "SECOND_ENTRY_LONG_READY",
    "E9_BROOKS_STATUS_FAILED_BEAR_BREAKOUT": "FAILED_BEAR_BREAKOUT",
    "E9_BROOKS_STATUS_MICRO_DOUBLE_BOTTOM": "MICRO_DOUBLE_BOTTOM",
    "E9_BROOKS_STATUS_ORDERLY_COMPRESSION_AT_SUPPORT": "ORDERLY_COMPRESSION_AT_SUPPORT",
    "E9_BROOKS_STATUS_BARB_WIRE_WAIT": "BARB_WIRE_WAIT",
    "E9_BROOKS_STATUS_BROOKS_SUPPORT_READY": "BROOKS_SUPPORT_READY",
    "E9_BROOKS_STATUS_BROOKS_FAILED_BREAKOUT_READY": "BROOKS_FAILED_BREAKOUT_READY",
    "E9_BROOKS_STATUS_BROOKS_BREAKOUT_READY": "BROOKS_BREAKOUT_READY",
}

BROOKS_STRUCTURE_EXPERIMENTS = {
    "E10_BROOKS_STRUCTURE_SECOND_ENTRY_LONG_READY": "SECOND_ENTRY_LONG_READY",
    "E10_BROOKS_STRUCTURE_FAILED_BEAR_BREAKOUT": "FAILED_BEAR_BREAKOUT",
    "E10_BROOKS_STRUCTURE_MICRO_DOUBLE_BOTTOM": "MICRO_DOUBLE_BOTTOM",
    "E10_BROOKS_STRUCTURE_ORDERLY_COMPRESSION_AT_SUPPORT": "ORDERLY_COMPRESSION_AT_SUPPORT",
    "E10_BROOKS_STRUCTURE_BEAR_FOLLOW_THROUGH_FAILED": "BEAR_FOLLOW_THROUGH_FAILED",
}

DERIVED_EXPERIMENT_IDS = [
    "E1_DUAL_DEFAULT",
    "E2_BOX_ONLY_INCREMENT",
    "E3_BOTH_ONLY",
    "E4_BOX_COMPACT_READY",
    "E5_BOX_SUPPORT_READY",
    "E5_BOX_STABLE",
    "E5_BOX_BREAKOUT_READY",
    "E6_BROOKS_ONLY",
    "E7_ORIGINAL_OR_BOX_OR_BROOKS",
    "E8_MULTI_PATH_ONLY",
    *BROOKS_STATUS_EXPERIMENTS,
    *BROOKS_STRUCTURE_EXPERIMENTS,
]


def filter_experiment_signals(signals: list[dict], experiment_id: str) -> list[dict]:
    if experiment_id == "E0_ORIGINAL_BASELINE":
        return [item for item in signals if item.get("tail_path") in {"ORIGINAL", "BOTH"}]
    if experiment_id == "E1_DUAL_DEFAULT":
        return [item for item in signals if item.get("tail_path") in {"ORIGINAL", "BOX", "BOTH"}]
    if experiment_id == "E2_BOX_ONLY_INCREMENT":
        return [item for item in signals if item.get("tail_path") == "BOX"]
    if experiment_id == "E3_BOTH_ONLY":
        return [item for item in signals if item.get("tail_path") == "BOTH"]
    if experiment_id == "E4_BOX_COMPACT_READY":
        return [
            item for item in signals
            if item.get("tail_path") in {"BOX", "BOTH"} and bool(item.get("compact_kline_pass"))
        ]
    status_by_experiment = {
        "E5_BOX_SUPPORT_READY": "BOX_SUPPORT_READY",
        "E5_BOX_STABLE": "BOX_STABLE",
        "E5_BOX_BREAKOUT_READY": "BOX_BREAKOUT_READY",
        "E5_BOX_BROKEN": "BOX_BROKEN",
    }
    if experiment_id in status_by_experiment:
        expected = status_by_experiment[experiment_id]
        return [item for item in signals if item.get("box_status") == expected]
    if experiment_id == "E6_BROOKS_ONLY":
        return [item for item in signals if _is_brooks_only(item)]
    if experiment_id == "E7_ORIGINAL_OR_BOX_OR_BROOKS":
        return [item for item in signals if authoritative_tail_paths(item)]
    if experiment_id == "E8_MULTI_PATH_ONLY":
        return [item for item in signals if _passed_path_count(item) >= 2]
    if experiment_id in BROOKS_STATUS_EXPERIMENTS:
        expected = BROOKS_STATUS_EXPERIMENTS[experiment_id]
        return [item for item in signals if str(item.get("brooks_status") or "") == expected]
    if experiment_id in BROOKS_STRUCTURE_EXPERIMENTS:
        expected = BROOKS_STRUCTURE_EXPERIMENTS[experiment_id]
        return [item for item in signals if expected in brooks_setup_types(item)]
    raise ValueError(f"unknown Strategy6 experiment: {experiment_id}")


def group_authoritative_path_metrics(records: list[dict]) -> dict[str, dict]:
    grouped = {path: [] for path in ("ORIGINAL", "BOX", "BROOKS")}
    for item in records:
        if not item.get("exit_date"):
            continue
        for path in authoritative_tail_paths(item):
            grouped[path].append(item)
    return {
        path: calculate_trade_metrics(items)
        for path, items in grouped.items()
        if items
    }


def group_brooks_structure_metrics(records: list[dict]) -> dict[str, dict]:
    grouped: dict[str, list[dict]] = {}
    for item in records:
        if not item.get("exit_date"):
            continue
        for setup_type in brooks_setup_types(item):
            grouped.setdefault(setup_type, []).append(item)
    return {
        setup_type: calculate_trade_metrics(items)
        for setup_type, items in sorted(grouped.items())
    }


def _is_brooks_only(item: dict) -> bool:
    if authoritative_tail_paths(item) == ["BROOKS"]:
        return True
    return (
        bool(item.get("brooks_tail_pass"))
        and not bool(item.get("original_tail_pass"))
        and not bool(item.get("box_tail_pass"))
    )


def _passed_path_count(item: dict) -> int:
    try:
        explicit = int(item.get("passed_path_count") or 0)
    except (TypeError, ValueError):
        explicit = 0
    return max(explicit, len(authoritative_tail_paths(item)))


def summarize_incremental_value(
    *,
    baseline: dict,
    dual: dict,
    displaced_original_trades: int,
) -> dict:
    return {
        "incremental_net_profit": round(float(dual.get("net_profit", 0)) - float(baseline.get("net_profit", 0)), 8),
        "incremental_max_drawdown": round(float(dual.get("max_drawdown", 0)) - float(baseline.get("max_drawdown", 0)), 8),
        "incremental_trades": int(dual.get("trades", 0)) - int(baseline.get("trades", 0)),
        "incremental_unfilled_rate": round(float(dual.get("unfilled_rate", 0)) - float(baseline.get("unfilled_rate", 0)), 8),
        "displaced_original_trades": int(displaced_original_trades),
    }

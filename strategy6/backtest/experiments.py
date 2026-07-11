"""Strategy6 dual-path experiment filters and incremental comparison."""
from __future__ import annotations


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
    raise ValueError(f"unknown Strategy6 experiment: {experiment_id}")


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

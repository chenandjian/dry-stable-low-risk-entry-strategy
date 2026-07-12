"""Training-only robust selector for Strategy6 optimization stages."""
from __future__ import annotations

import math

from strategy6.backtest.optimization import (
    build_pareto_frontier,
    calculate_robust_score,
    evaluate_neighbor_stability,
)
from strategy6.backtest.validation import OOSAccessError


DEFAULT_HARD_GATES = {
    "min_trades": 30,
    "min_expectancy_r": 0.10,
    "min_profit_factor": 1.20,
    "min_win_loss_ratio": 2.50,
    "max_drawdown": 0.20,
    "max_top5_concentration": 0.55,
    "max_single_month_concentration": 0.35,
}


def evaluate_coarse_gates(metrics: dict, *, evaluation_step: int) -> dict:
    min_trades = max(1, math.ceil(DEFAULT_HARD_GATES["min_trades"] / max(1, evaluation_step)))
    avg_win = float(metrics.get("avg_win_r", 0))
    avg_loss = abs(float(metrics.get("avg_loss_r", 0)))
    win_loss_ratio = avg_win / avg_loss if avg_loss > 0 else (float("inf") if avg_win > 0 else 0.0)
    checks = {
        "min_trades": int(metrics.get("trades", 0)) >= min_trades,
        "min_expectancy_r": float(metrics.get("expectancy_r", 0)) >= 0.05,
        "min_profit_factor": float(metrics.get("profit_factor", 0)) >= 1.10,
        "min_win_loss_ratio": win_loss_ratio >= 2.0,
        "max_drawdown": float(metrics.get("max_drawdown", float("inf"))) <= 0.25,
    }
    return {"passed": all(checks.values()), "checks": checks, "win_loss_ratio": win_loss_ratio}


def build_selection_metrics(
    *,
    trade_metrics: dict,
    fixed_risk_metrics: dict,
    concentration: dict,
) -> dict:
    """Normalize existing backtest outputs into the selector's audited schema."""
    return {
        **trade_metrics,
        "max_drawdown": float(fixed_risk_metrics.get("max_drawdown", float("inf"))),
        "net_return": float(fixed_risk_metrics.get("net_return", 0)),
        "top5_profit_concentration": float(concentration.get("top_five_profit_share", float("inf"))),
        "single_month_profit_concentration": float(concentration.get("single_month_profit_share", float("inf"))),
    }


def evaluate_hard_gates(metrics: dict, gates: dict | None = None) -> dict:
    limits = {**DEFAULT_HARD_GATES, **(gates or {})}
    avg_win = float(metrics.get("avg_win_r", 0))
    avg_loss = abs(float(metrics.get("avg_loss_r", 0)))
    win_loss_ratio = avg_win / avg_loss if avg_loss > 0 else (float("inf") if avg_win > 0 else 0.0)
    checks = {
        "min_trades": int(metrics.get("trades", 0)) >= int(limits["min_trades"]),
        "min_expectancy_r": float(metrics.get("expectancy_r", 0)) >= float(limits["min_expectancy_r"]),
        "min_profit_factor": float(metrics.get("profit_factor", 0)) >= float(limits["min_profit_factor"]),
        "min_win_loss_ratio": win_loss_ratio >= float(limits["min_win_loss_ratio"]),
        "max_drawdown": float(metrics.get("max_drawdown", float("inf"))) <= float(limits["max_drawdown"]),
        "top5_concentration": float(metrics.get("top5_profit_concentration", float("inf"))) <= float(limits["max_top5_concentration"]),
        "single_month_concentration": float(metrics.get("single_month_profit_concentration", float("inf"))) <= float(limits["max_single_month_concentration"]),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "win_loss_ratio": win_loss_ratio,
    }


def select_stage_trials(
    trials: list[dict],
    *,
    max_finalists: int = 3,
    coarse_evaluation_step: int | None = None,
) -> dict:
    _assert_training_only(trials)
    eligible = []
    rejections: dict[str, list[str]] = {}
    for trial in trials:
        parameter_id = str(trial.get("parameter_set_id") or "")
        reasons = []
        if trial.get("status") not in {"COMPLETED", "COMPLETED_WITH_SKIPS"}:
            reasons.append("INCOMPLETE_OR_FAILED_TRIAL")
        metrics = trial.get("training_metrics") or {}
        gate_result = (
            evaluate_coarse_gates(metrics, evaluation_step=coarse_evaluation_step)
            if coarse_evaluation_step is not None
            else evaluate_hard_gates(metrics)
        )
        reasons.extend(key.upper() for key, passed in gate_result["checks"].items() if not passed)
        robust = calculate_robust_score(metrics)
        neighbor = evaluate_neighbor_stability(
            current_score=float(robust["robust_score"]),
            neighbors=list(trial.get("neighbor_metrics") or []),
        )
        if not neighbor["stable"]:
            reasons.append("UNSTABLE_NEIGHBORHOOD")
        if reasons:
            rejections[parameter_id] = reasons
            continue
        eligible.append({
            **trial,
            **metrics,
            **robust,
            "win_loss_ratio": gate_result["win_loss_ratio"],
            "neighbor_stable": True,
            "neighbor": neighbor,
        })

    pareto = build_pareto_frontier(eligible)
    pareto.sort(
        key=lambda item: (
            float(item.get("robust_score", 0)),
            float(item.get("expectancy_r", 0)),
            float(item.get("profit_factor", 0)),
            -float(item.get("max_drawdown", 1)),
        ),
        reverse=True,
    )
    finalists = [str(item["parameter_set_id"]) for item in pareto[:max(0, max_finalists)]]
    return {
        "decision": "FULL_RERUN_REQUIRED" if finalists else "KEEP_PREVIOUS_STAGE",
        "finalist_parameter_set_ids": finalists,
        "pareto_parameter_set_ids": [str(item["parameter_set_id"]) for item in pareto],
        "eligible": eligible,
        "rejections": rejections,
    }


def confirm_validation_metrics(training_metrics: dict, validation_metrics: dict) -> dict:
    validation_gates = evaluate_hard_gates(validation_metrics)
    train_expectancy = float(training_metrics.get("expectancy_r", 0))
    train_pf = float(training_metrics.get("profit_factor", 0))
    expectancy_retained = (
        True if train_expectancy <= 0
        else float(validation_metrics.get("expectancy_r", 0)) >= train_expectancy * 0.60
    )
    pf_retained = (
        True if train_pf <= 0 or not math.isfinite(train_pf)
        else float(validation_metrics.get("profit_factor", 0)) >= train_pf * 0.60
    )
    checks = {
        "validation_hard_gates": validation_gates["passed"],
        "expectancy_retention_60pct": expectancy_retained,
        "profit_factor_retention_60pct": pf_retained,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "validation_gate_checks": validation_gates["checks"],
    }


def _assert_training_only(value, path: str = "root") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            lowered = str(key).lower()
            if "validation" in lowered:
                raise OOSAccessError(f"selector cannot read validation data at {path}.{key}")
            if "oos" in lowered:
                raise OOSAccessError(f"selector cannot read OOS data at {path}.{key}")
            _assert_training_only(nested, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _assert_training_only(nested, f"{path}[{index}]")

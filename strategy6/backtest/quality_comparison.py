"""Deterministic comparison helpers for Strategy6 main-chain research."""
from __future__ import annotations


def _candidate_key(row: dict) -> tuple[str, str, str]:
    return (
        str(row.get("code") or ""),
        str(row.get("evaluation_date") or row.get("signal_date") or ""),
        str(row.get("setup_id") or ""),
    )


def compare_candidate_records(baseline: list[dict], optimized: list[dict]) -> dict:
    baseline_by_key = {_candidate_key(row): row for row in baseline}
    optimized_by_key = {_candidate_key(row): row for row in optimized}
    baseline_keys = set(baseline_by_key)
    optimized_keys = set(optimized_by_key)
    return {
        "baseline_count": len(baseline_by_key),
        "optimized_count": len(optimized_by_key),
        "common_count": len(baseline_keys & optimized_keys),
        "added": [optimized_by_key[key] for key in sorted(optimized_keys - baseline_keys)],
        "removed": [baseline_by_key[key] for key in sorted(baseline_keys - optimized_keys)],
    }


def quality_gate(metrics: dict) -> dict:
    avg_loss = abs(float(metrics.get("avg_loss_r") or 0.0))
    payoff = float(metrics.get("avg_win_r") or 0.0) / avg_loss if avg_loss > 0 else 0.0
    checks = {
        "trades_gte_60": int(metrics.get("trades") or 0) >= 60,
        "expectancy_positive": float(metrics.get("expectancy_r") or 0.0) > 0,
        "profit_factor_gte_1_2": float(metrics.get("profit_factor") or 0.0) >= 1.2,
        "payoff_gte_2": payoff >= 2.0,
        "max_drawdown_lte_20pct": float(metrics.get("max_drawdown") or 1.0) <= 0.20,
    }
    return {"passed": all(checks.values()), "checks": checks, "payoff_ratio": payoff}


def select_best_stage(stages: list[dict]) -> dict | None:
    eligible = [
        stage for stage in stages
        if quality_gate(stage.get("train") or {})["passed"]
        and quality_gate(stage.get("validation") or {})["passed"]
    ]
    if not eligible:
        return None
    return max(
        eligible,
        key=lambda stage: (
            float((stage.get("validation") or {}).get("expectancy_r") or 0.0),
            float((stage.get("validation") or {}).get("profit_factor") or 0.0),
            -float((stage.get("validation") or {}).get("max_drawdown") or 1.0),
            float((stage.get("train") or {}).get("expectancy_r") or 0.0),
        ),
    )

"""Deterministic constrained parameter research without production writes."""
from __future__ import annotations

import copy
import itertools
import random
from statistics import median

from strategy6.backtest.validation import OOSAccessError, validate_parameter_combination


def sample_parameter_sets(
    production_config: dict,
    space: dict[str, list],
    *,
    max_trials: int,
    random_seed: int,
) -> list[dict]:
    keys = sorted(space)
    combinations = list(itertools.product(*(space[key] for key in keys)))
    rng = random.Random(random_seed)
    rng.shuffle(combinations)
    result = []
    for values in combinations:
        config = copy.deepcopy(production_config)
        for key, value in zip(keys, values):
            _set_nested(config, key, value)
        validate_parameter_combination(config)
        result.append(config)
        if len(result) >= max_trials:
            break
    return result


def check_constraints(metrics: dict, constraints: dict) -> dict:
    if any(str(key).lower().startswith("oos") for key in metrics):
        raise OOSAccessError("optimizer cannot read OOS metrics")
    checks = {
        "min_total_trades": float(metrics.get("trades", 0)) >= float(constraints.get("min_total_trades", 0)),
        "min_expectancy_r": float(metrics.get("expectancy_r", 0)) >= float(constraints.get("min_expectancy_r", float("-inf"))),
        "min_profit_factor": float(metrics.get("profit_factor", 0)) >= float(constraints.get("min_profit_factor", 0)),
        "max_drawdown_pct": float(metrics.get("max_drawdown", 0)) <= float(constraints.get("max_drawdown_pct", float("inf"))),
    }
    return {"passed": all(checks.values()), "checks": checks}


def build_pareto_frontier(trials: list[dict]) -> list[dict]:
    frontier = []
    for candidate in trials:
        dominated = False
        for other in trials:
            if other is candidate:
                continue
            at_least_as_good = (
                float(other.get("expectancy_r", 0)) >= float(candidate.get("expectancy_r", 0))
                and float(other.get("profit_factor", 0)) >= float(candidate.get("profit_factor", 0))
                and float(other.get("max_drawdown", 0)) <= float(candidate.get("max_drawdown", 0))
            )
            strictly_better = (
                float(other.get("expectancy_r", 0)) > float(candidate.get("expectancy_r", 0))
                or float(other.get("profit_factor", 0)) > float(candidate.get("profit_factor", 0))
                or float(other.get("max_drawdown", 0)) < float(candidate.get("max_drawdown", 0))
            )
            if at_least_as_good and strictly_better:
                dominated = True
                break
        if not dominated:
            frontier.append(candidate)
    return frontier


def evaluate_neighbor_stability(*, current_score: float, neighbors: list[dict]) -> dict:
    if not neighbors:
        return {"passed_neighbor_ratio": 0.0, "neighbor_score_median": 0.0, "stable": False}
    passed_ratio = sum(bool(item.get("passed")) for item in neighbors) / len(neighbors)
    score_median = median(float(item.get("robust_score", 0)) for item in neighbors)
    stable = passed_ratio >= 0.60 and score_median >= float(current_score) * 0.85
    return {
        "passed_neighbor_ratio": passed_ratio,
        "neighbor_score_median": score_median,
        "stable": stable,
    }


def calculate_robust_score(metrics: dict) -> dict:
    expectancy = max(0.0, min(1.0, float(metrics.get("expectancy_r", 0)) / 0.30))
    profit_factor = max(0.0, min(1.0, (float(metrics.get("profit_factor", 0)) - 1.0) / 2.0))
    drawdown = float(metrics.get("max_drawdown", 1.0))
    net_return = float(metrics.get("net_return", 0))
    calmar = net_return / drawdown if drawdown > 0 else (3.0 if net_return > 0 else 0.0)
    calmar_score = max(0.0, min(1.0, calmar / 3.0))
    sample_score = max(0.0, min(1.0, float(metrics.get("trades", 0)) / 200.0))
    available_score = 30 * expectancy + 20 * profit_factor + 15 * calmar_score + 10 * sample_score
    return {
        "robust_score": round(available_score, 6),
        "maximum_available_score": 75,
        "missing_components": ["rolling_window_consistency", "box_incremental_value"],
    }


def _set_nested(config: dict, dotted_key: str, value) -> None:
    parts = dotted_key.split(".")
    current = config
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value

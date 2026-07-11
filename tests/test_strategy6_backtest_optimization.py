import copy

import pytest

from strategy6.backtest.optimization import (
    build_pareto_frontier,
    check_constraints,
    evaluate_neighbor_stability,
    sample_parameter_sets,
)
from strategy6.backtest.validation import OOSAccessError


SPACE = {
    "box_tail.normal_box_width_max": [0.12, 0.15, 0.18],
    "box_tail.min_box_low_test_count": [2, 3],
}


def test_parameter_sampling_is_repeatable_and_does_not_mutate_production_config():
    production = {"box_tail": {"normal_box_width_max": 0.18, "min_box_low_test_count": 2}}
    before = copy.deepcopy(production)
    first = sample_parameter_sets(production, SPACE, max_trials=4, random_seed=20260711)
    second = sample_parameter_sets(production, SPACE, max_trials=4, random_seed=20260711)
    assert first == second
    assert len(first) == 4
    assert production == before


def test_constraints_and_oos_metrics_are_not_available_to_selector():
    constraints = {"min_total_trades": 100, "min_expectancy_r": 0.05, "min_profit_factor": 1.1, "max_drawdown_pct": 0.25}
    assert check_constraints({"trades": 120, "expectancy_r": 0.1, "profit_factor": 1.5, "max_drawdown": 0.2}, constraints)["passed"]
    assert not check_constraints({"trades": 20, "expectancy_r": 0.1, "profit_factor": 1.5, "max_drawdown": 0.2}, constraints)["passed"]
    with pytest.raises(OOSAccessError):
        check_constraints({"trades": 120, "oos_net_return": 0.5}, constraints)


def test_pareto_frontier_excludes_dominated_trials():
    trials = [
        {"id": "A", "expectancy_r": 0.10, "profit_factor": 1.5, "max_drawdown": 0.15},
        {"id": "B", "expectancy_r": 0.08, "profit_factor": 1.4, "max_drawdown": 0.20},
        {"id": "C", "expectancy_r": 0.12, "profit_factor": 1.3, "max_drawdown": 0.12},
    ]
    assert {item["id"] for item in build_pareto_frontier(trials)} == {"A", "C"}


def test_neighbor_stability_requires_broad_plateau_not_isolated_peak():
    result = evaluate_neighbor_stability(
        current_score=100,
        neighbors=[{"passed": True, "robust_score": 90}, {"passed": True, "robust_score": 85}, {"passed": False, "robust_score": 10}],
    )
    assert result["passed_neighbor_ratio"] == 2 / 3
    assert result["stable"] is True
    isolated = evaluate_neighbor_stability(
        current_score=100,
        neighbors=[{"passed": False, "robust_score": 20}, {"passed": False, "robust_score": 10}],
    )
    assert isolated["stable"] is False

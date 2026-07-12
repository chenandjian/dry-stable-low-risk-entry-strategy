import pytest

from strategy6.backtest.selector import (
    build_selection_metrics,
    confirm_validation_metrics,
    evaluate_hard_gates,
    select_stage_trials,
)
from strategy6.backtest.validation import OOSAccessError


PASSING = {
    "trades": 50,
    "expectancy_r": 0.20,
    "profit_factor": 1.50,
    "avg_win_r": 2.0,
    "avg_loss_r": -0.7,
    "max_drawdown": 0.15,
    "top5_profit_concentration": 0.40,
    "single_month_profit_concentration": 0.25,
}


@pytest.mark.parametrize(
    ("field", "value", "failed_gate"),
    [
        ("trades", 29, "min_trades"),
        ("expectancy_r", 0.09, "min_expectancy_r"),
        ("profit_factor", 1.19, "min_profit_factor"),
        ("avg_win_r", 1.5, "min_win_loss_ratio"),
        ("max_drawdown", 0.201, "max_drawdown"),
        ("top5_profit_concentration", 0.551, "top5_concentration"),
        ("single_month_profit_concentration", 0.351, "single_month_concentration"),
    ],
)
def test_hard_gates_cover_quality_sample_drawdown_and_concentration(field, value, failed_gate):
    result = evaluate_hard_gates({**PASSING, field: value})

    assert result["passed"] is False
    assert result["checks"][failed_gate] is False


def test_hard_gates_accept_approved_boundary_metrics():
    result = evaluate_hard_gates(PASSING)

    assert result["passed"] is True
    assert result["win_loss_ratio"] == pytest.approx(2.0 / 0.7)


def test_selection_metrics_use_existing_trade_portfolio_and_concentration_field_names():
    metrics = build_selection_metrics(
        trade_metrics={**PASSING, "max_drawdown": 0.99},
        fixed_risk_metrics={"max_drawdown": 0.12, "net_return": 0.30},
        concentration={"top_five_profit_share": 0.42, "single_month_profit_share": 0.28},
    )

    assert metrics["max_drawdown"] == 0.12
    assert metrics["net_return"] == 0.30
    assert metrics["top5_profit_concentration"] == 0.42
    assert metrics["single_month_profit_concentration"] == 0.28
    assert evaluate_hard_gates(metrics)["passed"] is True


def test_selector_reads_training_metrics_only_and_rejects_validation_or_oos_payloads():
    trial = {
        "parameter_set_id": "p1", "status": "COMPLETED",
        "training_metrics": PASSING,
        "validation_metrics": {"expectancy_r": 9},
    }
    with pytest.raises(OOSAccessError, match="validation"):
        select_stage_trials([trial])

    trial.pop("validation_metrics")
    trial["training_metrics"] = {**PASSING, "oos_profit_factor": 9}
    with pytest.raises(OOSAccessError, match="OOS"):
        select_stage_trials([trial])


def test_selector_keeps_previous_stage_when_all_trials_are_failed_or_ineligible():
    result = select_stage_trials([
        {"parameter_set_id": "failed", "status": "FAILED", "training_metrics": PASSING},
        {
            "parameter_set_id": "negative", "status": "COMPLETED",
            "training_metrics": {**PASSING, "expectancy_r": -0.1},
        },
    ])

    assert result["decision"] == "KEEP_PREVIOUS_STAGE"
    assert result["finalist_parameter_set_ids"] == []
    assert set(result["rejections"]) == {"failed", "negative"}


def test_selector_builds_pareto_and_returns_at_most_three_stable_finalists():
    trials = []
    for index, expectancy in enumerate((0.12, 0.16, 0.20, 0.18), start=1):
        trials.append({
            "parameter_set_id": f"p{index}",
            "status": "COMPLETED",
            "training_metrics": {
                **PASSING,
                "expectancy_r": expectancy,
                "profit_factor": 1.30 + index * 0.05,
                "max_drawdown": 0.18 - index * 0.01,
            },
            "neighbor_metrics": [
                {"passed": True, "robust_score": 90},
                {"passed": True, "robust_score": 88},
                {"passed": False, "robust_score": 86},
            ],
        })

    result = select_stage_trials(trials)

    assert result["decision"] == "FULL_RERUN_REQUIRED"
    assert 1 <= len(result["finalist_parameter_set_ids"]) <= 3
    assert set(result["finalist_parameter_set_ids"]) <= set(result["pareto_parameter_set_ids"])
    assert all(item["neighbor_stable"] for item in result["eligible"])


def test_selector_rejects_isolated_peak_with_unstable_neighbors():
    result = select_stage_trials([{
        "parameter_set_id": "isolated", "status": "COMPLETED",
        "training_metrics": PASSING,
        "neighbor_metrics": [
            {"passed": True, "robust_score": 90},
            {"passed": False, "robust_score": 20},
            {"passed": False, "robust_score": 10},
        ],
    }])

    assert result["decision"] == "KEEP_PREVIOUS_STAGE"
    assert "UNSTABLE_NEIGHBORHOOD" in result["rejections"]["isolated"]


def test_validation_confirmation_requires_hard_gates_and_sixty_percent_retention():
    train = {**PASSING, "expectancy_r": 0.20, "profit_factor": 1.50}
    passed = confirm_validation_metrics(
        train,
        {**PASSING, "expectancy_r": 0.12, "profit_factor": 1.20},
    )
    failed = confirm_validation_metrics(
        train,
        {**PASSING, "expectancy_r": 0.11, "profit_factor": 1.20},
    )

    assert passed["passed"] is True
    assert failed["passed"] is False
    assert failed["checks"]["expectancy_retention_60pct"] is False


def test_negative_training_metric_never_weakens_validation_absolute_gate():
    result = confirm_validation_metrics(
        {**PASSING, "expectancy_r": -0.1, "profit_factor": 0.8},
        {**PASSING, "expectancy_r": 0.09, "profit_factor": 1.19},
    )

    assert result["passed"] is False
    assert result["checks"]["validation_hard_gates"] is False


def test_infinite_training_profit_factor_does_not_require_infinite_validation_pf():
    result = confirm_validation_metrics(
        {**PASSING, "profit_factor": float("inf")},
        {**PASSING, "profit_factor": 1.20},
    )

    assert result["checks"]["profit_factor_retention_60pct"] is True

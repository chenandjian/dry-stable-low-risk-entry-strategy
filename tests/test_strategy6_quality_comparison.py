from strategy6.backtest.quality_comparison import (
    compare_candidate_records,
    quality_gate,
    select_best_stage,
)


def test_candidate_comparison_reports_common_added_and_removed_records():
    baseline = [
        {"code": "000001", "evaluation_date": "2025-01-02", "setup_id": "a"},
        {"code": "000002", "evaluation_date": "2025-01-03", "setup_id": "b"},
    ]
    optimized = [
        {"code": "000001", "evaluation_date": "2025-01-02", "setup_id": "a"},
        {"code": "000003", "evaluation_date": "2025-01-04", "setup_id": "c"},
    ]

    result = compare_candidate_records(baseline, optimized)

    assert result["common_count"] == 1
    assert [row["code"] for row in result["added"]] == ["000003"]
    assert [row["code"] for row in result["removed"]] == ["000002"]


def test_quality_gate_requires_sample_expectancy_pf_payoff_and_drawdown():
    passing = {
        "trades": 60, "expectancy_r": 0.10, "profit_factor": 1.30,
        "avg_win_r": 2.5, "avg_loss_r": 1.0, "max_drawdown": 0.15,
    }

    assert quality_gate(passing)["passed"] is True
    assert quality_gate({**passing, "trades": 59})["passed"] is False
    assert quality_gate({**passing, "profit_factor": 1.19})["passed"] is False
    assert quality_gate({**passing, "expectancy_r": 0.0})["passed"] is False


def test_best_stage_must_pass_both_train_and_validation_before_ranking():
    stages = [
        {"stage_id": "B1", "train": {"trades": 80, "expectancy_r": 0.2, "profit_factor": 1.5, "avg_win_r": 3, "avg_loss_r": 1, "max_drawdown": 0.1},
         "validation": {"trades": 80, "expectancy_r": -0.1, "profit_factor": 0.8, "avg_win_r": 3, "avg_loss_r": 1, "max_drawdown": 0.1}},
        {"stage_id": "B2", "train": {"trades": 70, "expectancy_r": 0.1, "profit_factor": 1.3, "avg_win_r": 2.5, "avg_loss_r": 1, "max_drawdown": 0.15},
         "validation": {"trades": 65, "expectancy_r": 0.08, "profit_factor": 1.25, "avg_win_r": 2.2, "avg_loss_r": 1, "max_drawdown": 0.18}},
    ]

    selected = select_best_stage(stages)

    assert selected["stage_id"] == "B2"


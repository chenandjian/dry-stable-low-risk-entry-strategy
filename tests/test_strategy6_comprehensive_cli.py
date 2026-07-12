from argparse import Namespace

import pytest

from scanner import db
from strategy6.backtest.cli import build_parser
from strategy6.backtest.comprehensive_runner import (
    assert_campaign_run_identity,
    assert_stage_can_start,
    campaign_status,
    execute_campaign_stage,
    initialize_campaign,
    recover_interrupted_trials,
)
from strategy6.validation import DEFAULT_STRATEGY6_CONFIG


def test_cli_exposes_comprehensive_commands_and_research_budget_options():
    parser = build_parser()

    plan = parser.parse_args(["comprehensive-plan", "--campaign-id", "c1"])
    run = parser.parse_args([
        "comprehensive-run", "--campaign-id", "c1",
        "--max-joint-trials", "12", "--evaluation-step", "5",
    ])
    status = parser.parse_args(["comprehensive-status", "--campaign-id", "c1"])
    report = parser.parse_args(["comprehensive-report", "--campaign-id", "c1"])

    assert plan.command == "comprehensive-plan"
    assert run.max_joint_trials == 12
    assert run.evaluation_step == 5
    assert status.campaign_id == report.campaign_id == "c1"


def test_campaign_initialization_is_idempotent_and_creates_seven_pending_stages(tmp_path):
    db.init_db(str(tmp_path / "campaign.db"))
    kwargs = dict(
        campaign_id="c1",
        base_config=DEFAULT_STRATEGY6_CONFIG,
        strategy_git_commit="abc",
        data_version="v1",
        random_seed=7,
        max_joint_trials=12,
    )

    initialize_campaign(**kwargs)
    initialize_campaign(**kwargs)
    status = campaign_status("c1")

    assert status["campaign"]["status"] == "PENDING"
    assert len(status["stages"]) == 7
    assert [item["stage_order"] for item in status["stages"]] == list(range(1, 8))
    assert len({item["stage_id"] for item in status["stages"]}) == 7


def test_campaign_resume_rejects_different_search_identity(tmp_path):
    db.init_db(str(tmp_path / "identity.db"))
    kwargs = dict(
        campaign_id="c1", base_config=DEFAULT_STRATEGY6_CONFIG,
        strategy_git_commit="abc", data_version="v1", random_seed=7,
        max_joint_trials=12, evaluation_step=5,
    )
    initialize_campaign(**kwargs)

    for changed in (
        {**kwargs, "evaluation_step": 1},
        {**kwargs, "random_seed": 8},
        {**kwargs, "max_joint_trials": 24},
    ):
        with pytest.raises(ValueError, match="campaign identity"):
            initialize_campaign(**changed)


def test_campaign_run_rejects_cli_budget_or_step_different_from_manifest():
    campaign = {"manifest": {"evaluation_step": 5, "max_joint_trials": 24}}

    assert_campaign_run_identity(campaign, Namespace(evaluation_step=5, max_joint_trials=24))
    with pytest.raises(ValueError, match="campaign identity"):
        assert_campaign_run_identity(campaign, Namespace(evaluation_step=1, max_joint_trials=24))
    with pytest.raises(ValueError, match="campaign identity"):
        assert_campaign_run_identity(campaign, Namespace(evaluation_step=5, max_joint_trials=12))


def test_stage_cannot_start_until_all_previous_stages_are_frozen():
    stages = [
        {"stage_id": "one", "stage_order": 1, "status": "RUNNING"},
        {"stage_id": "two", "stage_order": 2, "status": "PENDING"},
    ]
    with pytest.raises(RuntimeError, match="previous stage"):
        assert_stage_can_start(stages, "two")

    stages[0]["status"] = "FROZEN"
    assert_stage_can_start(stages, "two")


def test_interrupted_running_trials_are_requeued_but_completed_trials_are_reused():
    trials = [
        {"trial_id": "done", "status": "COMPLETED"},
        {"trial_id": "running", "status": "RUNNING"},
        {"trial_id": "failed", "status": "FAILED"},
    ]

    recovered = recover_interrupted_trials(trials)

    assert recovered[0]["status"] == "COMPLETED"
    assert recovered[1]["status"] == "INTERRUPTED"
    assert recovered[2]["status"] == "FAILED"


def test_campaign_rejects_changed_database_fingerprint():
    from strategy6.backtest.comprehensive_runner import assert_campaign_data_version

    assert_campaign_data_version({"data_version": "v1"}, "v1")
    with pytest.raises(RuntimeError, match="data version changed"):
        assert_campaign_data_version({"data_version": "v1"}, "v2")


def test_execute_stage_runs_coarse_then_at_most_three_full_confirmations_and_freezes(tmp_path):
    db.init_db(str(tmp_path / "execute.db"))
    initialize_campaign(
        campaign_id="c1", base_config=DEFAULT_STRATEGY6_CONFIG,
        strategy_git_commit="abc", data_version="v1", random_seed=7,
        max_joint_trials=2,
    )
    calls = []

    def fake_run(trial, mode):
        calls.append((trial.trial_id, mode))
        passing = {
            "trades": 50, "expectancy_r": 0.2, "profit_factor": 1.5,
            "avg_win_r": 2.0, "avg_loss_r": 0.7, "max_drawdown": 0.12,
            "net_return": 0.20, "top5_profit_concentration": 0.40,
            "single_month_profit_concentration": 0.25,
        }
        return {
            "run": {"run_id": f"{mode}-{trial.trial_id}", "status": "COMPLETED"},
            "phase_results": {
                "TRAIN": {"selection_metrics": passing},
                "VALIDATION": {"selection_metrics": passing},
            },
        }

    result = execute_campaign_stage("c1", "liquidity_rs", run_trial=fake_run)

    assert result["decision"] == "FROZEN"
    assert result["selected_parameter_set_id"]
    assert any(mode == "COARSE_TRAIN" for _, mode in calls)
    assert 1 <= sum(mode == "FULL_CONFIRMATION" for _, mode in calls) <= 3
    stage = db.get_strategy6_optimization_stages("c1")[0]
    assert stage["status"] == "FROZEN"
    assert stage["selected_parameter_set_id"] == result["selected_parameter_set_id"]


def test_execute_stage_keeps_parent_when_validation_rejects_all_finalists(tmp_path):
    db.init_db(str(tmp_path / "reject.db"))
    initialize_campaign(
        campaign_id="c1", base_config=DEFAULT_STRATEGY6_CONFIG,
        strategy_git_commit="abc", data_version="v1", random_seed=7,
        max_joint_trials=1,
    )

    def fake_run(trial, mode):
        passing = {
            "trades": 50, "expectancy_r": 0.2, "profit_factor": 1.5,
            "avg_win_r": 2.0, "avg_loss_r": 0.7, "max_drawdown": 0.12,
            "net_return": 0.20, "top5_profit_concentration": 0.40,
            "single_month_profit_concentration": 0.25,
        }
        validation = {**passing, "trades": 5, "expectancy_r": -0.2, "profit_factor": 0.5}
        return {
            "run": {"run_id": f"{mode}-{trial.trial_id}", "status": "COMPLETED"},
            "phase_results": {
                "TRAIN": {"selection_metrics": passing},
                "VALIDATION": {"selection_metrics": validation},
            },
        }

    result = execute_campaign_stage("c1", "liquidity_rs", run_trial=fake_run)

    assert result["decision"] == "KEEP_PREVIOUS_STAGE"
    assert result["selected_parameter_set_id"] == result["parent_parameter_set_id"]


def test_first_stage_runs_parent_audit_when_no_training_trial_is_eligible(tmp_path):
    db.init_db(str(tmp_path / "baseline-audit.db"))
    initialize_campaign(
        campaign_id="c1", base_config=DEFAULT_STRATEGY6_CONFIG,
        strategy_git_commit="abc", data_version="v1", random_seed=7,
        max_joint_trials=1,
    )
    calls = []
    failing = {
        "trades": 5, "expectancy_r": -0.2, "profit_factor": 0.5,
        "avg_win_r": 1.0, "avg_loss_r": 1.0, "max_drawdown": 0.4,
        "net_return": -0.1, "top5_profit_concentration": 0.9,
        "single_month_profit_concentration": 0.8,
    }

    def fake_run(trial, mode):
        calls.append((trial.parameter_set_id, mode))
        return {
            "run": {"run_id": f"{mode}-{trial.trial_id}", "status": "COMPLETED"},
            "phase_results": {
                "TRAIN": {"selection_metrics": failing},
                "VALIDATION": {"selection_metrics": failing},
            },
        }

    result = execute_campaign_stage("c1", "liquidity_rs", run_trial=fake_run)

    assert result["decision"] == "KEEP_PREVIOUS_STAGE"
    assert (result["parent_parameter_set_id"], "FULL_CONFIRMATION") in calls
    baseline = next(
        item for item in db.get_strategy6_optimization_trials("c1", "liquidity_rs")
        if item["parameter_set_id"] == result["parent_parameter_set_id"]
    )
    assert baseline["full_run_id"]


def test_full_rerun_resume_reuses_frozen_training_selection_without_validation_reselection(tmp_path):
    db.init_db(str(tmp_path / "resume-full.db"))
    initialize_campaign(
        campaign_id="c1", base_config=DEFAULT_STRATEGY6_CONFIG,
        strategy_git_commit="abc", data_version="v1", random_seed=7,
        max_joint_trials=2,
    )
    passing = {
        "trades": 50, "expectancy_r": 0.2, "profit_factor": 1.5,
        "avg_win_r": 2.0, "avg_loss_r": 0.7, "max_drawdown": 0.12,
        "net_return": 0.20, "top5_profit_concentration": 0.40,
        "single_month_profit_concentration": 0.25,
    }
    full_calls = []
    interrupted = {"done": False}

    def flaky_run(trial, mode):
        if mode == "FULL_CONFIRMATION":
            full_calls.append(trial.trial_id)
            if len(full_calls) == 2 and not interrupted["done"]:
                interrupted["done"] = True
                raise KeyboardInterrupt()
        return {
            "run": {"run_id": f"{mode}-{trial.trial_id}", "status": "COMPLETED"},
            "phase_results": {
                "TRAIN": {"selection_metrics": passing},
                "VALIDATION": {"selection_metrics": passing},
            },
        }

    with pytest.raises(KeyboardInterrupt):
        execute_campaign_stage("c1", "liquidity_rs", run_trial=flaky_run)
    frozen_finalists = db.get_strategy6_optimization_stages("c1")[0]["detail"]["selector"]["finalist_parameter_set_ids"]

    result = execute_campaign_stage("c1", "liquidity_rs", run_trial=flaky_run)

    assert result["decision"] == "FROZEN"
    assert db.get_strategy6_optimization_stages("c1")[0]["detail"]["selector"]["finalist_parameter_set_ids"] == frozen_finalists
    assert full_calls.count(full_calls[0]) == 1

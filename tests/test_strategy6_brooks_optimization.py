from strategy6.backtest.cli import build_parser
from strategy6.backtest.runner import (
    BROOKS_OPTIMIZATION_SPACE,
    _research_strategy_config,
    build_brooks_trial_configs,
)
from strategy6.backtest.validation import build_evaluation_schedule
from strategy6.backtest.models import BacktestRunSpec


def test_cli_exposes_dedicated_brooks_only_optimization_command():
    args = build_parser().parse_args(["brooks-optimize"])

    assert args.command == "brooks-optimize"
    assert args.evaluation_step == 20

    validation = build_parser().parse_args(["brooks-validate", "--trial-index", "15"])
    assert validation.command == "brooks-validate"
    assert validation.evaluation_step == 10
    assert validation.trial_index == 15


def test_brooks_optimization_space_cannot_change_other_strategy6_paths():
    assert BROOKS_OPTIMIZATION_SPACE
    assert all(key.startswith("brooks_tail.") for key in BROOKS_OPTIMIZATION_SPACE)
    assert "brooks_tail.scoring.pass_score_min" in BROOKS_OPTIMIZATION_SPACE
    assert "box_tail.normal_box_width_max" not in BROOKS_OPTIMIZATION_SPACE


def test_research_trial_config_explicitly_uses_quality_v2_without_mutating_base():
    base = {"decision_profile": "formal_original", "watch_min_score": 60}

    research = _research_strategy_config(base)

    assert research["decision_profile"] == "research_quality_v2"
    assert research["watch_min_score"] == 60
    assert base["decision_profile"] == "formal_original"


def test_brooks_coarse_schedule_keeps_consecutive_trigger_windows_and_locks_oos():
    calendar = [f"2024-01-{day:02d}" for day in range(1, 26)] + ["2026-01-02"]

    schedule = build_evaluation_schedule(
        calendar,
        mode="BROOKS_COARSE",
        start="2024-01-01",
        end="2026-01-02",
        evaluation_step=10,
        oos_start="2026-01-01",
    )

    assert schedule.dates == (
        "2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04",
        "2024-01-11", "2024-01-12", "2024-01-13", "2024-01-14",
        "2024-01-21", "2024-01-22", "2024-01-23", "2024-01-24",
    )
    assert "2026-01-02" not in schedule.dates
    assert schedule.final_eligible is False


def test_brooks_validation_schedule_uses_only_held_out_2025_dates():
    calendar = ["2024-12-31"] + [f"2025-01-{day:02d}" for day in range(1, 11)] + ["2026-01-02"]

    schedule = build_evaluation_schedule(
        calendar,
        mode="BROOKS_VALIDATION",
        start="2023-01-01",
        end="2026-01-02",
        evaluation_step=5,
        oos_start="2026-01-01",
    )

    assert schedule.dates == (
        "2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04",
        "2025-01-06", "2025-01-07", "2025-01-08", "2025-01-09",
    )
    assert all(date.startswith("2025-") for date in schedule.dates)


def test_signal_scope_is_part_of_backtest_run_identity():
    common = {
        "experiment_id": "BROOKS_ONLY_0001",
        "strategy_version": "test",
        "strategy_git_commit": "abc",
        "strategy_config": {},
        "backtest_config": {},
        "data_version": "data",
    }

    exclusive = BacktestRunSpec.create(
        **common, research_context={"signal_scope": "BROOKS_ONLY"},
    )
    path = BacktestRunSpec.create(
        **common, research_context={"signal_scope": "BROOKS_PATH"},
    )

    assert exclusive.run_id != path.run_id


def test_brooks_trials_are_baseline_oat_relaxations_then_joint_relaxation():
    base = {
        "brooks_tail": {
            "selling_pressure": {"max_strong_bear_bar_count": 1},
            "price_stability": {"close_range_max": 0.08, "atr_contraction_max": 0.8},
            "volume_dry": {"tail_volume_ratio_max": 0.75},
            "support": {"support_distance_pct": 0.03},
            "trade_trigger": {"max_trigger_distance_atr": 1.5},
            "scoring": {"pass_score_min": 14},
            "second_entry": {
                "low_similarity_tolerance": 0.02,
                "signal_bar_close_position_min": 0.55,
                "signal_bar_max_body_ratio": 0.03,
            },
            "failed_breakout": {"recovery_days": 2, "max_break_distance_atr": 0.8},
        }
    }

    trials = build_brooks_trial_configs(base, max_trials=15)

    assert len(trials) == 15
    assert trials[0]["decision_profile"] == "research_quality_v2"
    assert {key: value for key, value in trials[0].items() if key != "decision_profile"} == base
    for trial in trials[1:7]:
        changed = [
            key for key in BROOKS_OPTIMIZATION_SPACE
            if _nested(trial, key) != _nested(base, key)
        ]
        assert len(changed) == 1
    assert sum(
        _nested(trials[7], key) != _nested(base, key)
        for key in BROOKS_OPTIMIZATION_SPACE
    ) == 6
    for trial in trials[8:14]:
        changed = [
            key for key in BROOKS_OPTIMIZATION_SPACE
            if _nested(trial, key) != _nested(base, key)
        ]
        assert len(changed) == 1
    assert all(_nested(trials[-1], key) != _nested(base, key) for key in BROOKS_OPTIMIZATION_SPACE)


def _nested(value, dotted_key):
    for part in dotted_key.split("."):
        value = value[part]
    return value

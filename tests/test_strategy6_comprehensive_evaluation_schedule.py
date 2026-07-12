import pytest

from strategy6.backtest.models import BacktestRunSpec
from strategy6.backtest.validation import build_evaluation_schedule


CALENDAR = [
    "2022-12-30",
    *[f"2023-01-{day:02d}" for day in range(2, 17)],
    "2024-12-31",
    "2025-01-02",
    "2025-01-03",
    "2026-01-05",
]


def test_coarse_schedule_is_train_only_and_uses_every_fifth_real_trading_day():
    schedule = build_evaluation_schedule(
        CALENDAR,
        mode="COARSE_TRAIN",
        start="2023-01-01",
        end="2025-12-31",
        evaluation_step=5,
        oos_start="2026-01-01",
    )

    assert schedule.mode == "COARSE_TRAIN"
    assert schedule.evaluation_step == 5
    assert schedule.dates == (
        "2023-01-02", "2023-01-07", "2023-01-12", "2024-12-31",
    )
    assert all("2023-" <= date[:5] <= "2024-" for date in schedule.dates)
    assert schedule.final_eligible is False


def test_full_schedule_is_daily_2023_to_2025_and_never_reads_locked_oos():
    schedule = build_evaluation_schedule(
        CALENDAR,
        mode="FULL_CONFIRMATION",
        start="2023-01-01",
        end="2026-12-31",
        evaluation_step=1,
        oos_start="2026-01-01",
    )

    assert schedule.dates[0] == "2023-01-02"
    assert schedule.dates[-1] == "2025-01-03"
    assert "2026-01-05" not in schedule.dates
    assert schedule.final_eligible is True


def test_full_schedule_rejects_non_daily_step_and_coarse_rejects_validation_start():
    with pytest.raises(ValueError, match="daily"):
        build_evaluation_schedule(
            CALENDAR, mode="FULL_CONFIRMATION", start="2023-01-01",
            end="2025-12-31", evaluation_step=5, oos_start="2026-01-01",
        )
    with pytest.raises(ValueError, match="training period"):
        build_evaluation_schedule(
            CALENDAR, mode="COARSE_TRAIN", start="2025-01-01",
            end="2025-12-31", evaluation_step=5, oos_start="2026-01-01",
        )


def test_schedule_rejects_empty_real_index_calendar():
    with pytest.raises(ValueError, match="no evaluation dates"):
        build_evaluation_schedule(
            [], mode="COARSE_TRAIN", start="2023-01-01",
            end="2024-12-31", evaluation_step=5, oos_start="2026-01-01",
        )


def _run(*, evaluation_step=5, parent="p0", mode="COARSE_TRAIN"):
    return BacktestRunSpec.create(
        experiment_id="STAGE_1_TRIAL_1",
        strategy_version="6.0",
        strategy_git_commit="abc",
        strategy_config={"min_relative_strength_20": 0.1},
        backtest_config={},
        data_version="data-v1",
        research_context={
            "run_mode": mode,
            "stage_id": "liquidity_rs",
            "parent_parameter_set_id": parent,
            "evaluation_step": evaluation_step,
            "start_date": "2023-01-01",
            "end_date": "2024-12-31" if mode == "COARSE_TRAIN" else "2025-12-31",
        },
    )


def test_run_identity_includes_schedule_stage_parent_and_date_range():
    baseline = _run()

    assert baseline.evaluation_step == 5
    assert baseline.run_mode == "COARSE_TRAIN"
    assert baseline.stage_id == "liquidity_rs"
    assert baseline.parent_parameter_set_id == "p0"
    assert baseline.start_date == "2023-01-01"
    assert baseline.end_date == "2024-12-31"
    assert baseline.run_id != _run(evaluation_step=1).run_id
    assert baseline.run_id != _run(parent="p-other").run_id
    assert baseline.run_id != _run(mode="FULL_CONFIRMATION").run_id

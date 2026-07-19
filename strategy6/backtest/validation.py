"""Lookahead, split and parameter guards for Strategy6 research."""
from __future__ import annotations

from dataclasses import dataclass


class OOSAccessError(RuntimeError):
    pass


@dataclass(frozen=True)
class EvaluationSchedule:
    mode: str
    evaluation_step: int
    start_date: str
    end_date: str
    dates: tuple[str, ...]
    final_eligible: bool


def build_evaluation_schedule(
    market_calendar: list[str],
    *,
    mode: str,
    start: str,
    end: str,
    evaluation_step: int,
    oos_start: str,
) -> EvaluationSchedule:
    """Build a locked coarse-train or full-confirmation evaluation schedule."""
    if evaluation_step < 1:
        raise ValueError("evaluation_step must be at least 1")
    if mode == "COARSE_TRAIN":
        if start >= "2025-01-01" or end < "2023-01-01":
            raise ValueError("coarse schedule must overlap the 2023-2024 training period")
        effective_start = max(start, "2023-01-01")
        effective_end = min(end, "2024-12-31", _day_before(oos_start))
        all_dates = sorted({date for date in market_calendar if effective_start <= date <= effective_end})
        dates = tuple(all_dates[::evaluation_step])
        final_eligible = False
    elif mode == "BROOKS_COARSE":
        effective_start = max(start, "2023-01-01")
        effective_end = min(end, "2024-12-31", _day_before(oos_start))
        all_dates = sorted({date for date in market_calendar if effective_start <= date <= effective_end})
        dates = _sample_trigger_windows(all_dates, evaluation_step)
        final_eligible = False
    elif mode == "BROOKS_VALIDATION":
        effective_start = max(start, "2025-01-01")
        effective_end = min(end, "2025-12-31", _day_before(oos_start))
        all_dates = sorted({date for date in market_calendar if effective_start <= date <= effective_end})
        dates = _sample_trigger_windows(all_dates, evaluation_step)
        final_eligible = False
    elif mode == "FULL_CONFIRMATION":
        if evaluation_step != 1:
            raise ValueError("full confirmation must use a daily evaluation step")
        effective_start = max(start, "2023-01-01")
        effective_end = min(end, "2025-12-31", _day_before(oos_start))
        dates = tuple(sorted({date for date in market_calendar if effective_start <= date <= effective_end}))
        final_eligible = True
    else:
        raise ValueError(
            "mode must be COARSE_TRAIN, BROOKS_COARSE, "
            "BROOKS_VALIDATION or FULL_CONFIRMATION"
        )
    if effective_start > effective_end:
        raise ValueError("evaluation schedule has no legal date range")
    if not dates:
        raise ValueError("evaluation schedule has no evaluation dates from the real index calendar")
    return EvaluationSchedule(
        mode=mode,
        evaluation_step=evaluation_step,
        start_date=effective_start,
        end_date=effective_end,
        dates=dates,
        final_eligible=final_eligible,
    )


def _sample_trigger_windows(all_dates: list[str], evaluation_step: int) -> tuple[str, ...]:
    """Sample setup anchors while preserving the following 3-day trigger life."""
    selected: set[str] = set()
    for anchor in range(0, len(all_dates), evaluation_step):
        selected.update(all_dates[anchor:anchor + 4])
    return tuple(date for date in all_dates if date in selected)


def _day_before(value: str) -> str:
    from datetime import date, timedelta

    return (date.fromisoformat(value) - timedelta(days=1)).isoformat()


@dataclass(frozen=True)
class TimeSplit:
    train_start: str
    train_end: str
    validation_start: str
    validation_end: str
    oos_start: str
    oos_end: str

    def __post_init__(self):
        if not (
            self.train_start <= self.train_end
            < self.validation_start <= self.validation_end
            < self.oos_start <= self.oos_end
        ):
            raise ValueError("time split ranges must not overlap and must be ordered")

    def phase_for(self, value: str) -> str:
        if self.train_start <= value <= self.train_end:
            return "TRAIN"
        if self.validation_start <= value <= self.validation_end:
            return "VALIDATION"
        if self.oos_start <= value <= self.oos_end:
            return "OOS_LOCKED"
        return "OUTSIDE"


def assert_oos_metrics_unavailable(value_date: str, oos_start: str) -> None:
    if value_date >= oos_start:
        raise OOSAccessError("OOS metrics are locked until manual approval")


def assert_date_visible(requested_date: str, *, as_of_date: str) -> None:
    if requested_date > as_of_date:
        raise ValueError(f"future data access denied: {requested_date} > {as_of_date}")


def validate_parameter_combination(parameters: dict) -> None:
    box = parameters.get("box_tail") or {}
    minimum = box.get("min_box_days")
    maximum = box.get("max_box_days")
    if minimum is not None and maximum is not None and int(minimum) > int(maximum):
        raise ValueError("min_box_days must be <= max_box_days")
    support_position = box.get("support_ready_position_max")
    breakout_position = box.get("breakout_ready_position_min")
    if support_position is not None and breakout_position is not None:
        if float(support_position) >= float(breakout_position):
            raise ValueError("support_ready_position_max must be < breakout_ready_position_min")

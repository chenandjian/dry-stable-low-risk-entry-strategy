"""Lookahead, split and parameter guards for Strategy6 research."""
from __future__ import annotations

from dataclasses import dataclass


class OOSAccessError(RuntimeError):
    pass


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

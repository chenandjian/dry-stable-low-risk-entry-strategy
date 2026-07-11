import pytest

from strategy6.backtest.validation import (
    OOSAccessError,
    TimeSplit,
    assert_date_visible,
    assert_oos_metrics_unavailable,
    validate_parameter_combination,
)


def test_time_split_locks_oos_and_rejects_overlap():
    split = TimeSplit(
        train_start="2023-01-01",
        train_end="2024-12-31",
        validation_start="2025-01-01",
        validation_end="2025-12-31",
        oos_start="2026-01-01",
        oos_end="2026-12-31",
    )
    assert split.phase_for("2025-06-01") == "VALIDATION"
    assert split.phase_for("2026-06-01") == "OOS_LOCKED"
    with pytest.raises(ValueError, match="must not overlap"):
        TimeSplit(
            train_start="2023-01-01",
            train_end="2025-01-02",
            validation_start="2025-01-01",
            validation_end="2025-12-31",
            oos_start="2026-01-01",
            oos_end="2026-12-31",
        )


def test_oos_and_future_data_are_hard_blocked():
    with pytest.raises(OOSAccessError):
        assert_oos_metrics_unavailable("2026-01-01", "2026-01-01")
    with pytest.raises(ValueError, match="future data"):
        assert_date_visible("2025-01-02", as_of_date="2025-01-01")


def test_parameter_validation_allows_fixed_box_length_but_rejects_invalid_order():
    validate_parameter_combination({
        "box_tail": {
            "min_box_days": 10,
            "max_box_days": 10,
            "support_ready_position_max": 0.4,
            "breakout_ready_position_min": 0.75,
        }
    })
    with pytest.raises(ValueError, match="min_box_days"):
        validate_parameter_combination({
            "box_tail": {
                "min_box_days": 11,
                "max_box_days": 10,
                "support_ready_position_max": 0.4,
                "breakout_ready_position_min": 0.75,
            }
        })

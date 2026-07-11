from strategy6.backtest.validation import TimeSplit
from strategy6.backtest.walk_forward import build_walk_forward_windows, lock_oos


def test_walk_forward_reports_insufficient_data_instead_of_fake_window():
    result = build_walk_forward_windows(["2023-01-02", "2024-01-02", "2025-01-02"], train_years=3, validation_years=1)
    assert result["status"] == "INSUFFICIENT_DATA"
    assert result["windows"] == []


def test_walk_forward_windows_do_not_overlap_train_and_validation():
    dates = [f"{year}-01-02" for year in range(2018, 2026)] + [f"{year}-12-30" for year in range(2018, 2026)]
    result = build_walk_forward_windows(dates, train_years=3, validation_years=1)
    assert result["status"] == "READY"
    assert all(item["train_end"] < item["validation_start"] for item in result["windows"])


def test_oos_lock_contains_range_and_data_hash_but_no_metrics():
    split = TimeSplit("2023-01-01", "2024-12-31", "2025-01-01", "2025-12-31", "2026-01-01", "2026-12-31")
    lock = lock_oos(split, data_fingerprint="data-v1", strategy_commit="4cff1ca")
    assert lock["status"] == "OOS_LOCKED"
    assert lock["start_date"] == "2026-01-01"
    assert "metrics" not in lock


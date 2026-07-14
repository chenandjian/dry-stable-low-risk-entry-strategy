import pytest

from strategy6.brooks.metrics import (
    bar_metrics,
    calculate_kline_overlap_ratio,
    count_direction_changes,
    find_swing_lows,
)


def _bar(date, open_price, high, low, close):
    return {
        "date": date,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": 100,
    }


def test_bar_metrics_calculates_body_close_shadows_and_range():
    result = bar_metrics(_bar("2026-01-01", 9.0, 10.0, 8.0, 9.5))

    assert result.valid is True
    assert result.body_ratio == pytest.approx(0.5 / 9.5)
    assert result.close_position == pytest.approx(0.75)
    assert result.upper_shadow_ratio == pytest.approx(0.25)
    assert result.lower_shadow_ratio == pytest.approx(0.5)
    assert result.range_ratio == pytest.approx(2.0 / 9.5)


def test_zero_range_uses_neutral_close_position_and_risk_tag():
    result = bar_metrics(_bar("2026-01-01", 10.0, 10.0, 10.0, 10.0))

    assert result.valid is True
    assert result.close_position == 0.5
    assert "ZERO_RANGE_BAR" in result.risk_tags


def test_invalid_close_is_not_usable():
    result = bar_metrics(_bar("2026-01-01", 0.0, 0.0, 0.0, 0.0))

    assert result.valid is False
    assert "INVALID_CLOSE" in result.risk_tags


def test_overlap_ratio_matches_existing_minimum_range_definition():
    first = _bar("2026-01-01", 10, 11, 9, 10)
    second = _bar("2026-01-02", 10, 10.5, 9.5, 10)

    assert calculate_kline_overlap_ratio(first, second) == 1.0
    second["high"] = second["low"]
    assert calculate_kline_overlap_ratio(first, second) is None


def test_direction_changes_ignore_flat_closes():
    rows = [
        _bar("1", 10, 11, 9, 10),
        _bar("2", 10, 12, 9, 11),
        _bar("3", 11, 12, 9, 10),
        _bar("4", 10, 12, 9, 11),
        _bar("5", 11, 12, 9, 11),
    ]

    assert count_direction_changes(rows) == 2


def test_swing_lows_are_confirmed_by_adjacent_lows_only():
    rows = [
        _bar("1", 10, 11, 10, 10.5),
        _bar("2", 10, 11, 9, 10),
        _bar("3", 10, 11, 10, 10.5),
        _bar("4", 10, 11, 9.2, 10),
        _bar("5", 10, 11, 10, 10.5),
    ]

    assert [(item.index, item.price) for item in find_swing_lows(rows)] == [(1, 9.0), (3, 9.2)]

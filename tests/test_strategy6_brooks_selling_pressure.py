from datetime import date, timedelta

from strategy6.brooks.selling_pressure import analyze_selling_pressure
from strategy6.models import Strategy6Support
from strategy6.validation import resolve_strategy6_config


def _bar(index, *, open_price=10.0, high=10.2, low=9.8, close=10.0):
    return {
        "date": (date(2026, 1, 1) + timedelta(days=index)).isoformat(),
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": 100,
    }


def _config():
    return resolve_strategy6_config({})["brooks_tail"]


def test_strong_bear_bar_with_next_day_break_is_follow_through():
    rows = [_bar(index) for index in range(7)]
    rows[-2] = _bar(5, open_price=10.2, high=10.25, low=9.6, close=9.7)
    rows[-1] = _bar(6, open_price=9.7, high=9.75, low=9.3, close=9.4)

    result = analyze_selling_pressure(rows, Strategy6Support(key_support_price=9.0), _config())

    assert result.strong_bear_bar_count == 2
    assert result.bear_follow_through_count >= 1
    assert result.exhausted is False


def test_bear_bar_without_follow_through_and_midpoint_reclaim_is_exhausted():
    rows = [_bar(index) for index in range(7)]
    rows[-3] = _bar(4, open_price=10.3, high=10.35, low=9.7, close=9.8)
    rows[-2] = _bar(5, open_price=9.85, high=10.1, low=9.75, close=10.05)
    rows[-1] = _bar(6, open_price=10.0, high=10.2, low=9.9, close=10.1)

    result = analyze_selling_pressure(rows, Strategy6Support(key_support_price=9.5), _config())

    assert result.strong_bear_bar_count == 1
    assert result.bear_follow_through_count == 0
    assert result.bear_follow_through_failed is True
    assert result.exhausted is True


def test_three_declining_bear_bars_are_not_exhausted():
    rows = [_bar(index) for index in range(4)]
    rows.extend([
        _bar(4, open_price=10.2, high=10.25, low=9.8, close=9.9),
        _bar(5, open_price=9.9, high=9.95, low=9.5, close=9.6),
        _bar(6, open_price=9.6, high=9.65, low=9.2, close=9.3),
    ])

    result = analyze_selling_pressure(rows, Strategy6Support(key_support_price=9.0), _config())

    assert result.max_consecutive_bear_bars == 3
    assert result.exhausted is False
    assert "BROOKS_CONSECUTIVE_BEAR_BARS" in result.risk_tags


def test_effective_support_break_prevents_exhaustion():
    rows = [_bar(index) for index in range(7)]
    rows[-1] = _bar(6, open_price=9.9, high=10.0, low=9.5, close=9.6)

    result = analyze_selling_pressure(rows, Strategy6Support(key_support_price=10.0), _config())

    assert result.exhausted is False
    assert "BROOKS_SUPPORT_EFFECTIVELY_BROKEN" in result.risk_tags

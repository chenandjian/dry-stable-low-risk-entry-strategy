from datetime import date, timedelta

from strategy6.brooks.context import analyze_brooks_context
from strategy6.models import Strategy6Indicators, Strategy6Start, Strategy6Support
from strategy6.validation import resolve_strategy6_config


def _rows(closes):
    start = date(2026, 1, 1)
    return [
        {
            "date": (start + timedelta(days=index)).isoformat(),
            "open": close * 0.995,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": 100,
        }
        for index, close in enumerate(closes)
    ]


def _inputs(*, grade="A", current=12.0, ma20=11.5, ma50=11.0, start_low=10.0, support=10.8):
    indicators = Strategy6Indicators(current_price=current, ma20=ma20, ma50=ma50, atr14=0.5)
    start = Strategy6Start(start_grade=grade, start_low=start_low)
    support_result = Strategy6Support(key_support_price=support, defense_support_price=10.5)
    return indicators, start, support_result


def test_bull_context_accepts_a_grade_above_support_with_rising_ma20():
    rows = _rows([10 + index * 0.05 for index in range(40)])
    indicators, start, support = _inputs()

    result = analyze_brooks_context(
        rows, indicators, start, support,
        resolve_strategy6_config({})["brooks_tail"],
    )

    assert result.context_type == "BULL_CONTEXT"
    assert result.passed is True
    assert result.watch_only is False
    assert result.ma20_slope > 0


def test_b_grade_is_weak_bull_watch_only():
    rows = _rows([10 + index * 0.05 for index in range(40)])
    indicators, start, support = _inputs(grade="B")

    result = analyze_brooks_context(
        rows, indicators, start, support,
        resolve_strategy6_config({})["brooks_tail"],
    )

    assert result.context_type == "WEAK_BULL_CONTEXT"
    assert result.passed is True
    assert result.watch_only is True


def test_bear_context_rejects_falling_price_below_averages():
    rows = _rows([14 - index * 0.10 for index in range(40)])
    indicators, start, support = _inputs(current=10.1, ma20=11.0, ma50=12.0, support=9.8)

    result = analyze_brooks_context(
        rows, indicators, start, support,
        resolve_strategy6_config({})["brooks_tail"],
    )

    assert result.context_type == "BEAR_CONTEXT"
    assert result.passed is False
    assert result.lower_high_low_sequence_count > 2


def test_context_rejects_effective_support_break():
    rows = _rows([10.0] * 40)
    indicators, start, support = _inputs(current=9.5, ma20=9.7, ma50=9.4, support=10.0)

    result = analyze_brooks_context(
        rows, indicators, start, support,
        resolve_strategy6_config({})["brooks_tail"],
    )

    assert result.passed is False
    assert "BROOKS_SUPPORT_EFFECTIVELY_BROKEN" in result.risk_tags

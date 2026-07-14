from datetime import date, timedelta

from strategy6.brooks.models import BrooksCompactStructureResult, BrooksStructureResult, BrooksTailResult
from strategy6.brooks.trigger import evaluate_brooks_trade_trigger
from strategy6.models import Strategy6Support
from strategy6.validation import resolve_strategy6_config


def _bar(index, *, open_price=10.0, high=10.05, low=9.95, close=10.0):
    return {
        "date": (date(2026, 1, 1) + timedelta(days=index)).isoformat(),
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": 100,
    }


def _tail(signal_date):
    return BrooksTailResult(
        enabled=True,
        passed=True,
        score=18,
        status="SECOND_ENTRY_LONG_READY",
        support_not_broken=True,
        structure=BrooksStructureResult(
            micro_double_bottom=True,
            second_entry_long_ready=True,
            second_entry_signal_date=signal_date,
            second_entry_signal_high=10.10,
            second_entry_trigger_price=10.10,
            setup_types=["MICRO_DOUBLE_BOTTOM", "SECOND_ENTRY_LONG_READY"],
        ),
    )


def _evaluate(rows, tail, *, grade="A", follow_through_days=None):
    config = resolve_strategy6_config({})["brooks_tail"]
    if follow_through_days is not None:
        config["trade_trigger"]["breakout_follow_through_days"] = follow_through_days
    return evaluate_brooks_trade_trigger(
        rows,
        tail,
        Strategy6Support(key_support_price=9.8, pivot_price=10.5),
        start_grade=grade,
        atr14=0.5,
        config=config,
    )


def test_second_entry_signal_day_is_ready_to_trigger_but_not_triggered():
    rows = [_bar(0), _bar(1), _bar(2, high=10.10, close=10.05)]
    result = _evaluate(rows, _tail(rows[-1]["date"]))
    assert result.ready is False
    assert result.second_entry_triggered is False
    assert result.trigger_price == 10.10
    assert result.trigger_valid_until == "2026-01-07"
    assert "BROOKS_TRIGGER_REQUIRES_LATER_SESSION" in result.risk_tags


def test_next_session_break_of_signal_high_confirms_support_trigger():
    rows = [_bar(0), _bar(1), _bar(2, high=10.10, close=10.05), _bar(3, high=10.25, close=10.18)]
    result = _evaluate(rows, _tail(rows[-2]["date"]))
    assert result.ready is True
    assert result.second_entry_triggered is True
    assert result.trigger_type == "BROOKS_SUPPORT_READY"
    assert result.trigger_price == 10.10


def test_failed_breakout_uses_reclaim_high_and_signal_date_for_authoritative_trigger():
    rows = [
        _bar(0),
        _bar(1, high=10.18, low=9.70, close=9.90),
        _bar(2, high=10.30, low=9.95, close=10.20),
    ]
    tail = _tail(rows[0]["date"])
    tail.structure.second_entry_long_ready = False
    tail.structure.failed_bear_breakout = True

    result = _evaluate(rows, tail)

    assert result.ready is True
    assert result.trigger_type == "BROOKS_FAILED_BREAKOUT_READY"
    assert result.trigger_price == 10.18
    assert result.trigger_valid_until == "2026-01-07"


def test_breakout_follow_through_uses_pivot_and_breakout_date_for_authoritative_trigger():
    rows = [
        _bar(0),
        _bar(1, high=10.65, low=10.30, close=10.60),
        _bar(2, high=10.70, low=10.45, close=10.55),
    ]
    tail = _tail(rows[0]["date"])
    tail.structure.second_entry_long_ready = False

    result = _evaluate(rows, tail)

    assert result.ready is True
    assert result.trigger_type == "BROOKS_BREAKOUT_READY"
    assert result.trigger_price == 10.5
    assert result.trigger_valid_until == "2026-01-06"


def test_breakout_follow_through_uses_configured_second_followup_bar():
    rows = [
        _bar(0, close=10.40),
        _bar(1, high=10.65, low=10.30, close=10.60),
        _bar(2, high=10.70, low=10.45, close=10.55),
        _bar(3, high=10.68, low=10.42, close=10.54),
    ]
    tail = _tail(rows[0]["date"])
    tail.structure.second_entry_long_ready = False

    result = _evaluate(rows, tail, follow_through_days=2)

    assert result.ready is True
    assert result.trigger_type == "BROOKS_BREAKOUT_READY"
    assert result.trigger_valid_until == "2026-01-06"


def test_breakout_does_not_roll_forward_after_follow_through_window_expires():
    rows = [_bar(0, close=10.40), _bar(1, high=10.65, low=10.30, close=10.60)]
    rows.extend(
        _bar(index, high=10.70, low=10.45, close=10.55)
        for index in range(2, 9)
    )
    tail = _tail(rows[0]["date"])
    tail.structure.second_entry_long_ready = False

    result = _evaluate(rows, tail, follow_through_days=2)

    assert result.ready is False
    assert result.trigger_price == 10.5
    assert result.trigger_valid_until == "2026-01-06"
    assert "BROOKS_BREAKOUT_FOLLOW_THROUGH_EXPIRED" in result.risk_tags


def test_trigger_expires_after_three_later_sessions():
    rows = [_bar(index) for index in range(7)]
    rows[-1].update({"high": 10.25, "close": 10.18})
    result = _evaluate(rows, _tail(rows[2]["date"]))
    assert result.ready is False
    assert "BROOKS_TRIGGER_EXPIRED" in result.risk_tags


def test_b_grade_and_barb_wire_cannot_be_trade_ready():
    rows = [_bar(0), _bar(1), _bar(2, high=10.10), _bar(3, high=10.25)]
    grade_b = _evaluate(rows, _tail(rows[2]["date"]), grade="B")
    barb_tail = _tail(rows[2]["date"])
    barb_tail.compact_structure = BrooksCompactStructureResult(
        structure_type="BARB_WIRE",
        barb_wire_risk=True,
    )
    barb = _evaluate(rows, barb_tail)
    assert grade_b.ready is False
    assert "BROOKS_GRADE_B_WATCH_ONLY" in grade_b.risk_tags
    assert barb.ready is False
    assert "BARB_WIRE_RISK" in barb.risk_tags

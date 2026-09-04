from __future__ import annotations

from strategy6.body_support import evaluate_body_support
from strategy6.models import Strategy6Phase, Strategy6Support
from strategy6.validation import resolve_strategy6_config


def _bar(
    day: int,
    *,
    open_: float,
    close: float,
    low: float | None = None,
    high: float | None = None,
    volume: float = 100.0,
) -> dict:
    return {
        "date": f"2026-01-{day:02d}",
        "open": open_,
        "high": high if high is not None else max(open_, close) + 0.2,
        "low": low if low is not None else min(open_, close) - 0.2,
        "close": close,
        "volume": volume,
        "amount": volume * close,
    }


def _config() -> dict:
    return resolve_strategy6_config({})["body_support"]


def test_latest_bar_pattern_reports_valid_body_low_failed_break_reclaim():
    rows = [
        _bar(1, open_=10.8, close=10.6, low=10.4),
        _bar(2, open_=10.5, close=10.2, low=10.0),
        _bar(3, open_=10.3, close=10.1, low=9.9),
        _bar(4, open_=10.1, close=10.5, low=9.8),
        _bar(5, open_=10.6, close=10.8, low=10.4),
        _bar(6, open_=10.7, close=10.3, low=10.1),
        _bar(7, open_=10.2, close=10.55, low=9.75, high=10.7),
    ]
    phase = Strategy6Phase(valid=True, tail_start_index=4, tail_days=3)
    support = Strategy6Support(
        key_support_price=10.1,
        support_zone_low=9.9,
        support_zone_high=10.3,
    )

    result = evaluate_body_support(rows, phase, support, _config())

    pattern = result.latest_bar_patterns[0]
    assert pattern.code == "VALID_BODY_LOW"
    assert pattern.name == "有效实体低点"
    assert pattern.matched is True
    assert pattern.status == "CONFIRMING"
    assert pattern.signal_type == "FAILED_BREAK_RECLAIM"
    assert pattern.evaluation_date == "2026-01-07"
    assert pattern.body_bottom == 10.2
    assert pattern.body_top == 10.55
    assert "LATEST_LOW_BREAK_RECLAIMED_BY_BODY" in pattern.reasons
    assert result.score <= 5
    assert result.status == "BODY_SUPPORT_FORMING"


def test_latest_bar_potential_pivot_never_uses_future_confirmation():
    rows = [
        _bar(1, open_=10.9, close=10.7),
        _bar(2, open_=10.7, close=10.5),
        _bar(3, open_=10.5, close=10.3),
        _bar(4, open_=10.3, close=10.1, low=9.8),
    ]
    phase = Strategy6Phase(valid=True, tail_start_index=1, tail_days=3)

    result = evaluate_body_support(rows, phase, Strategy6Support(), _config())

    pattern = result.latest_bar_patterns[0]
    assert pattern.matched is True
    assert pattern.signal_type == "POTENTIAL_BODY_PIVOT"
    assert pattern.status == "CONFIRMING"
    assert result.status != "BODY_SUPPORT_CONFIRMED"


def test_confirmed_body_pivot_requires_two_completed_bars_after_pivot():
    prefix = [
        _bar(1, open_=10.9, close=10.7, low=10.5),
        _bar(2, open_=10.7, close=10.4, low=10.2),
        _bar(3, open_=10.4, close=10.0, low=9.7),
    ]
    phase = Strategy6Phase(valid=True, tail_start_index=0, tail_days=5)
    support = Strategy6Support()

    on_pivot_day = evaluate_body_support(prefix, phase, support, _config())
    after_one = evaluate_body_support(
        prefix + [_bar(4, open_=10.1, close=10.35, low=9.95)],
        phase,
        support,
        _config(),
    )
    after_two = evaluate_body_support(
        prefix
        + [
            _bar(4, open_=10.1, close=10.35, low=9.95),
            _bar(5, open_=10.35, close=10.65, low=10.2),
        ],
        phase,
        support,
        _config(),
    )

    assert on_pivot_day.pivot_count == 0
    assert after_one.pivot_count == 0
    assert after_two.pivot_count == 1
    assert after_two.status in {"BODY_SUPPORT_CONFIRMED", "BODY_SUPPORT_STRONG"}
    assert after_two.score >= 6


def test_body_support_is_limited_to_current_tail_evidence():
    old_structure = [
        _bar(1, open_=10.6, close=10.4),
        _bar(2, open_=10.4, close=10.0, low=9.8),
        _bar(3, open_=10.1, close=10.3),
        _bar(4, open_=10.3, close=10.7),
        _bar(5, open_=10.8, close=10.9),
    ]
    latest_tail = [
        _bar(6, open_=12.0, close=12.1),
        _bar(7, open_=12.1, close=12.2),
        _bar(8, open_=12.2, close=12.3),
    ]
    phase = Strategy6Phase(valid=True, tail_start_index=5, tail_days=3)

    result = evaluate_body_support(
        old_structure + latest_tail,
        phase,
        Strategy6Support(),
        _config(),
    )

    assert result.score < 6
    assert "NO_CURRENT_TAIL_BODY_SUPPORT_EVIDENCE" in result.risks


def test_body_support_can_be_disabled_without_fabricated_scores():
    config = _config()
    config["enabled"] = False

    result = evaluate_body_support(
        [_bar(1, open_=10, close=10.1)],
        Strategy6Phase(),
        Strategy6Support(),
        config,
    )

    assert result.score == 0
    assert result.status == "DISABLED"
    assert result.latest_bar_patterns == []


def test_latest_body_break_caps_previous_support_instead_of_leaving_high_score():
    rows = [
        _bar(1, open_=10.9, close=10.7, low=10.5),
        _bar(2, open_=10.7, close=10.4, low=10.2),
        _bar(3, open_=10.4, close=10.0, low=9.7),
        _bar(4, open_=10.1, close=10.35, low=9.95),
        _bar(5, open_=10.35, close=10.65, low=10.2),
        _bar(6, open_=10.5, close=9.6, low=9.5),
    ]

    result = evaluate_body_support(
        rows,
        Strategy6Phase(valid=True, tail_start_index=0, tail_days=6),
        Strategy6Support(),
        _config(),
    )

    assert result.passed is False
    assert result.score <= 5
    assert result.status == "BODY_SUPPORT_WEAKENED"
    assert "LATEST_BODY_BROKE_SUPPORT_ZONE" in result.risks

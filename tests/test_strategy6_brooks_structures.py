from datetime import date, timedelta

from strategy6.brooks.compact import classify_compact_structure
from strategy6.brooks.models import BrooksContextResult, BrooksSellingPressureResult
from strategy6.brooks.structures import analyze_brooks_structures
from strategy6.models import Strategy6CompactKline, Strategy6Support
from strategy6.validation import resolve_strategy6_config


def _bar(index, *, open_price=10.0, high=10.1, low=9.9, close=10.0):
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


def _compact(passed=True):
    return Strategy6CompactKline(
        enabled=True,
        passed=passed,
        avg_body_ratio=0.01,
        max_body_ratio=0.02,
        close_range=0.03,
        atr5=0.3,
        atr20=0.5,
        atr_contraction_ratio=0.6,
    )


def test_compact_orderly_requires_bull_context_support_and_exhausted_selling():
    rows = [_bar(index, close=10.05) for index in range(5)]
    result = classify_compact_structure(
        rows,
        _compact(),
        BrooksContextResult(context_type="BULL_CONTEXT", passed=True),
        Strategy6Support(key_support_price=10.0),
        BrooksSellingPressureResult(exhausted=True),
        atr14=0.5,
        config=_config(),
    )

    assert result.structure_type == "COMPACT_ORDERLY"
    assert result.barb_wire_risk is False


def test_compact_barb_wire_blocks_orderly_classification():
    rows = [
        _bar(0, open_price=10.0, high=10.4, low=9.6, close=10.1),
        _bar(1, open_price=10.1, high=10.5, low=9.7, close=9.9),
        _bar(2, open_price=9.9, high=10.4, low=9.4, close=10.1),
        _bar(3, open_price=10.1, high=10.5, low=9.6, close=9.9),
        _bar(4, open_price=9.9, high=10.4, low=9.4, close=10.1),
        _bar(5, open_price=10.1, high=10.5, low=9.6, close=9.9),
    ]
    result = classify_compact_structure(
        rows,
        _compact(),
        BrooksContextResult(context_type="BULL_CONTEXT", passed=True),
        Strategy6Support(key_support_price=10.0),
        BrooksSellingPressureResult(exhausted=True),
        atr14=0.5,
        config=_config(),
    )

    assert result.structure_type == "BARB_WIRE"
    assert result.barb_wire_risk is True
    assert result.direction_change_count > 3


def test_compact_bearish_is_rejected_even_when_compact_metrics_pass():
    result = classify_compact_structure(
        [_bar(index, close=10 - index * 0.1) for index in range(5)],
        _compact(),
        BrooksContextResult(context_type="BEAR_CONTEXT", passed=False, lower_high_low_sequence_count=4),
        Strategy6Support(key_support_price=9.0),
        BrooksSellingPressureResult(exhausted=False, bear_follow_through_count=2),
        atr14=0.5,
        config=_config(),
    )

    assert result.structure_type == "COMPACT_BEARISH"


def test_micro_double_bottom_and_second_entry_are_identified_near_support():
    rows = [_bar(index) for index in range(9)]
    rows[2] = _bar(2, open_price=10.0, high=10.1, low=9.80, close=10.02)
    rows[3] = _bar(3, open_price=10.02, high=10.3, low=10.0, close=10.25)
    rows[6] = _bar(6, open_price=9.98, high=10.12, low=9.82, close=10.08)
    rows[7] = _bar(7, open_price=10.08, high=10.2, low=10.02, close=10.15)

    result = analyze_brooks_structures(
        rows,
        Strategy6Support(key_support_price=10.0, support_zone_low=9.8, support_zone_high=10.2),
        BrooksSellingPressureResult(exhausted=True),
        compact_structure_type="COMPACT_ORDERLY",
        atr14=0.5,
        tail_volume_ratio=0.55,
        config=_config(),
    )

    assert result.micro_double_bottom is True
    assert result.second_entry_long_ready is True
    assert result.second_entry_signal_date == rows[6]["date"]
    assert result.second_entry_trigger_price == rows[6]["high"]
    assert "MICRO_DOUBLE_BOTTOM" in result.setup_types


def test_second_low_five_percent_below_first_is_not_a_micro_double_bottom():
    rows = [_bar(index) for index in range(9)]
    rows[2] = _bar(2, low=9.8, close=10.1)
    rows[6] = _bar(6, low=9.3, close=9.6)

    result = analyze_brooks_structures(
        rows,
        Strategy6Support(key_support_price=10.0),
        BrooksSellingPressureResult(exhausted=True),
        compact_structure_type="NO_COMPACT",
        atr14=0.5,
        tail_volume_ratio=0.55,
        config=_config(),
    )

    assert result.micro_double_bottom is False
    assert result.second_entry_long_ready is False


def test_failed_bear_breakout_reclaims_support_within_two_days():
    rows = [_bar(index) for index in range(8)]
    rows[-3] = _bar(5, open_price=10.05, high=10.1, low=9.85, close=9.90)
    rows[-2] = _bar(6, open_price=9.92, high=10.15, low=9.90, close=10.10)
    rows[-1] = _bar(7, open_price=10.10, high=10.2, low=10.0, close=10.15)

    result = analyze_brooks_structures(
        rows,
        Strategy6Support(key_support_price=10.0, support_zone_low=9.9),
        BrooksSellingPressureResult(exhausted=True),
        compact_structure_type="NO_COMPACT",
        atr14=0.5,
        tail_volume_ratio=0.55,
        config=_config(),
    )

    assert result.failed_bear_breakout is True
    assert "FAILED_BEAR_BREAKOUT" in result.setup_types

from datetime import date, timedelta

from strategy6.dry_tail import evaluate_dry_tail
from strategy6.indicators import calculate_indicators
from strategy6.models import Strategy6Indicators, Strategy6Phase
from strategy6.validation import resolve_strategy6_config


def _rows():
    rows = []
    for i in range(30):
        close = 100 + i * 0.02
        volume = 1_000_000 if i < 25 else 100_000
        rows.append({
            "date": (date(2026, 1, 1) + timedelta(days=i)).isoformat(),
            "open": close,
            "high": close * 1.005,
            "low": close * 0.995,
            "close": close,
            "volume": volume,
            "amount": 600_000_000,
        })
    return rows


def test_tail_volume_ratio_uses_non_overlapping_pre_tail_twenty_days():
    config = resolve_strategy6_config({})
    rows, indicators = calculate_indicators(_rows(), config)
    phase = Strategy6Phase(
        status="PHASE_VALID",
        valid=True,
        tail_start_index=25,
        signal_index=29,
    )

    result = evaluate_dry_tail(rows, indicators, phase, config)

    assert result.tail_avg_volume == 100_000
    assert result.pre_tail_avg_volume_20 == 1_000_000
    assert result.tail_volume_ratio == 0.1
    assert result.dry_tail_pass is True


def test_tail_with_falling_lows_is_rejected_even_when_volume_is_dry():
    rows = _rows()
    for offset, low in zip(range(-5, 0), (100.0, 99.9, 99.6, 99.2, 98.8)):
        rows[offset]["low"] = low
        rows[offset]["close"] = low + 0.1
    phase = Strategy6Phase(
        status="PHASE_VALID", valid=True, tail_start_index=len(rows) - 5, signal_index=len(rows) - 1
    )
    ind = Strategy6Indicators(close_range_5=0.02, return_5=-0.03)

    result = evaluate_dry_tail(rows, ind, phase, resolve_strategy6_config({}))

    assert "TAIL_LOW_DECLINING" in result.rejects


def test_tail_new_low_compares_against_independent_pre_tail_window():
    rows = _rows()
    for offset, close in zip(range(-5, 0), (98.0, 98.1, 98.2, 98.2, 98.3)):
        rows[offset].update(open=close, high=close * 1.005, low=close * 0.995, close=close)
    phase = Strategy6Phase(
        status="PHASE_VALID", valid=True, tail_start_index=len(rows) - 5, signal_index=len(rows) - 1
    )
    ind = Strategy6Indicators(close_range_5=0.01, return_5=-0.02)

    result = evaluate_dry_tail(rows, ind, phase, resolve_strategy6_config({}))

    assert "TAIL_NEW_LOW" in result.rejects
    assert "price:no_new_low" not in result.reasons

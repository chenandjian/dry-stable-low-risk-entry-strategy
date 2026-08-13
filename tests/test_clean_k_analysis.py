from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from scanner.clean_k_analysis import (
    CleanKDataError,
    CleanKInputError,
    analyze_clean_k,
)


def _dates(count: int) -> list[str]:
    current = date(2026, 1, 1)
    result = []
    while len(result) < count:
        if current.weekday() < 5:
            result.append(current.isoformat())
        current += timedelta(days=1)
    return result


def _row(day: str, close: float, *, open_: float | None = None, span: float = 2.0,
         volume: float = 1_000_000, turnover: float | None = None) -> dict:
    open_value = close if open_ is None else open_
    half = span / 2
    return {
        "date": day,
        "open": open_value,
        "high": max(open_value, close) + half,
        "low": min(open_value, close) - half,
        "close": close,
        "volume": volume,
        "turnover": turnover if turnover is not None else volume * close,
    }


def _series(target_closes: list[float], *, target_spans: list[float] | None = None,
            warmup: int = 40) -> list[dict]:
    days = _dates(warmup + len(target_closes))
    rows = [_row(days[i], 100 + i * 0.03, span=2.0) for i in range(warmup)]
    spans = target_spans or [2.0] * len(target_closes)
    previous = rows[-1]["close"]
    for offset, (close, span) in enumerate(zip(target_closes, spans)):
        rows.append(_row(days[warmup + offset], close, open_=previous, span=span))
        previous = close
    return rows


def test_smooth_uptrend_is_clean_trend():
    rows = _series([101 + i * 0.45 for i in range(20)], target_spans=[0.3] * 20)
    result = analyze_clean_k(rows, period=20)

    assert result["isClean"] is True
    assert result["structureMode"] == "TREND"
    assert result["trendDirection"] == "UP"
    assert result["cleanKScore"] >= 75


def test_smooth_downtrend_can_be_clean_but_is_explicitly_down():
    rows = _series([108 - i * 0.4 for i in range(20)], target_spans=[0.3] * 20)
    result = analyze_clean_k(rows, period=20)

    assert result["isClean"] is True
    assert result["structureMode"] == "TREND"
    assert result["trendDirection"] == "DOWN"
    assert "CLEAN_DOWNTREND" in result["riskFlags"]


def test_stable_overlapping_base_is_clean():
    closes = [100 + (0.18 if i % 2 else -0.18) for i in range(20)]
    result = analyze_clean_k(_series(closes, target_spans=[1.2] * 20), period=20)

    assert result["isClean"] is True
    assert result["structureMode"] == "BASE"
    assert result["baseCleanScore"] >= 75


def test_orderly_contraction_scores_as_contraction():
    spans = [3.6] * 6 + [2.4] * 7 + [1.1] * 7
    closes = [100 + ((i % 2) * 0.08) for i in range(20)]
    result = analyze_clean_k(_series(closes, target_spans=spans), period=20)

    assert result["structureMode"] in {"BASE", "CONTRACTION"}
    assert result["contractionCleanScore"] >= 75


def test_micro_long_leg_doji_is_not_misclassified_as_dirty():
    rows = _series([100.0] * 20)
    rows[-1].update(open=100.0, high=100.18, low=99.82, close=100.0)
    result = analyze_clean_k(rows, period=20)
    metric = result["barMetrics"][-1]

    assert metric["intradayRangeAtr"] < 0.3
    assert metric["barCleanScore"] >= 95
    assert metric["dirtyExtremeBar"] is False


def test_large_one_sided_rejection_is_mid_score_not_zero_or_perfect():
    rows = _series([100.0] * 20)
    rows[-1].update(open=100.0, high=100.1, low=96.0, close=100.0)
    metric = analyze_clean_k(rows, period=20)["barMetrics"][-1]

    assert 55 <= metric["barCleanScore"] <= 80
    assert metric["barStructureType"] == "ONE_SIDE_LOWER_REJECTION"


def test_large_two_sided_long_leg_doji_is_dirty_but_marubozu_is_clean():
    conflict = _series([100.0] * 20)
    conflict[-1].update(open=100.0, high=103.0, low=97.0, close=100.0)
    directional = _series([100.0] * 20)
    directional[-1].update(open=97.0, high=103.0, low=97.0, close=103.0)

    conflict_metric = analyze_clean_k(conflict, period=20)["barMetrics"][-1]
    directional_metric = analyze_clean_k(directional, period=20)["barMetrics"][-1]

    assert conflict_metric["barCleanScore"] < 65
    assert conflict_metric["dirtyExtremeBar"] is True
    assert directional_metric["barCleanScore"] >= 80
    assert directional_metric["dirtyExtremeBar"] is False


def test_large_gap_with_small_intraday_bar_uses_intraday_range_for_significance():
    rows = _series([100.0] * 20)
    rows[-1].update(open=104.0, high=104.2, low=103.8, close=104.0)
    metric = analyze_clean_k(rows, period=20)["barMetrics"][-1]

    assert metric["trueRangeAtr"] > metric["intradayRangeAtr"]
    assert metric["intradayRangeAtr"] < 0.3
    assert metric["barCleanScore"] >= 90


def test_one_price_events_are_safe_and_reduce_confidence():
    rows = _series([100.0] * 20)
    for row in rows[-8:]:
        row.update(open=100.0, high=100.0, low=100.0, close=100.0)
    result = analyze_clean_k(rows, period=20)

    assert result["eventBarCount"] == 8
    assert result["confidence"] < 0.7
    assert result["isClean"] is False
    assert "LOW_CONFIDENCE" in result["riskFlags"]
    assert all(math.isfinite(value) for value in (
        result["cleanKScore"], result["sequenceCleanScore"], result["structureScore"]
    ))


def test_suspended_zero_volume_rows_are_excluded_before_taking_period():
    rows = _series([101 + i * 0.3 for i in range(20)])
    suspended = {
        "date": "2026-03-31",
        "open": 106.7,
        "high": 106.7,
        "low": 106.7,
        "close": 106.7,
        "volume": 0,
        "turnover": 0,
    }
    rows.insert(-4, suspended)
    result = analyze_clean_k(rows, period=20)

    assert result["evaluatedBarCount"] == 20
    assert result["suspendedCount"] == 1
    assert suspended["date"] not in {item["tradeDate"] for item in result["barMetrics"]}


def test_noisy_alternating_sequence_is_not_clean():
    closes = [100, 108, 99, 110, 98, 109, 97, 111, 99, 108,
              96, 110, 98, 111, 97, 109, 96, 112, 98, 107]
    spans = [2, 8, 3, 10, 2, 9, 3, 11, 2, 8, 3, 10, 2, 9, 3, 11, 2, 8, 3, 10]
    result = analyze_clean_k(_series(closes, target_spans=spans), period=20)

    assert result["isClean"] is False
    assert result["cleanKScore"] < 75 or result["sequenceCleanScore"] < 70


def test_period_selects_exactly_latest_effective_bars_and_respects_target_date():
    rows = _series([100 + i * 0.2 for i in range(25)])
    target = rows[-3]["date"]
    result = analyze_clean_k(rows, period=20, target_trade_date=target)

    assert len(result["barMetrics"]) == 20
    assert result["endDate"] == target
    assert result["barMetrics"][-1]["tradeDate"] == target


@pytest.mark.parametrize("period", [9, 121])
def test_period_outside_supported_range_is_rejected(period):
    with pytest.raises(CleanKInputError):
        analyze_clean_k(_series([100.0] * 20), period=period)


def test_fractional_period_is_rejected_instead_of_truncated():
    with pytest.raises(CleanKInputError, match="integer"):
        analyze_clean_k(_series([100.0] * 20), period=20.5)


def test_insufficient_atr_warmup_is_rejected():
    rows = _series([100.0] * 20, warmup=10)
    with pytest.raises(CleanKDataError, match="ATR"):
        analyze_clean_k(rows, period=20)


def test_invalid_ohlc_is_rejected_instead_of_silently_scored():
    rows = _series([100.0] * 20)
    rows[-1]["high"] = 90.0
    with pytest.raises(CleanKDataError, match="OHLC"):
        analyze_clean_k(rows, period=20)


def test_zero_volume_nonflat_bar_is_invalid_not_silently_treated_as_suspension():
    rows = _series([100.0] * 20)
    rows[-1].update(open=100.0, high=101.0, low=99.0, close=100.5, volume=0, turnover=0)

    with pytest.raises(CleanKDataError, match="zero-volume"):
        analyze_clean_k(rows, period=20)


def test_missing_volume_is_invalid_not_silently_treated_as_suspension():
    rows = _series([100.0] * 20)
    del rows[-1]["volume"]

    with pytest.raises(CleanKDataError, match="OHLC structure"):
        analyze_clean_k(rows, period=20)


def test_unclean_downtrend_is_not_labeled_clean_downtrend():
    closes = [108 - index * 0.4 for index in range(20)]
    rows = _series(closes, target_spans=[6.0] * 20)
    result = analyze_clean_k(rows, period=20)

    assert result["structureMode"] == "TREND"
    assert result["trendDirection"] == "DOWN"
    assert result["isClean"] is False
    assert "CLEAN_DOWNTREND" not in result["riskFlags"]

from __future__ import annotations

from datetime import date, timedelta

import pytest

from scanner.clean_k_analysis import CleanKInputError
from scanner.clean_k_v2 import analyze_clean_k_v2, resolve_clean_k_v2_config


def _dates(count: int) -> list[str]:
    current = date(2026, 1, 1)
    result = []
    while len(result) < count:
        if current.weekday() < 5:
            result.append(current.isoformat())
        current += timedelta(days=1)
    return result


def _rows_from_closes(closes: list[float], *, warmup: int = 40) -> list[dict]:
    days = _dates(warmup + len(closes))
    rows = []
    previous = 96.0
    for index in range(warmup):
        close = 96.0 + index * 0.10
        rows.append(_bar(days[index], previous, close, pad=0.8))
        previous = close
    for offset, close in enumerate(closes):
        rows.append(_bar(days[warmup + offset], previous, close, pad=0.35))
        previous = close
    return rows


def _bar(day: str, open_: float, close: float, *, pad: float) -> dict:
    return {
        "date": day,
        "open": open_,
        "high": max(open_, close) + pad,
        "low": min(open_, close) - pad,
        "close": close,
        "volume": 1_000_000,
        "turnover": close * 1_000_000,
    }


def test_directional_expansion_is_not_a_dirty_extreme():
    rows = _rows_from_closes([100.0] * 19 + [104.0])
    rows[-1].update(open=100.0, high=104.2, low=99.8, close=104.0)

    result = analyze_clean_k_v2(rows, period=20)
    metric = result["barMetrics"][-1]

    assert metric["barStructureType"] == "DIRECTIONAL_EXPANSION"
    assert metric["dirtyExtremeBar"] is False
    assert metric["barCleanScore"] >= 75
    assert result["barStats"]["directionalExpansionCount"] == 1


def test_large_gap_reversal_is_not_exempted_as_directional_expansion():
    rows = _rows_from_closes([100.0] * 20)
    rows[-1].update(open=104.0, high=104.5, low=97.0, close=97.2)

    result = analyze_clean_k_v2(rows, period=20)
    metric = result["barMetrics"][-1]

    assert metric["barStructureType"] == "GAP_REVERSAL_EXPANSION"
    assert metric["dirtyExtremeBar"] is True
    assert result["barStats"]["gapReversalExpansionCount"] == 1


def test_large_two_sided_conflict_remains_dirty():
    rows = _rows_from_closes([100.0] * 20)
    rows[-1].update(open=100.0, high=104.0, low=96.0, close=100.0)

    result = analyze_clean_k_v2(rows, period=20)
    metric = result["barMetrics"][-1]

    assert metric["barStructureType"] == "CONFLICT_EXPANSION"
    assert metric["dirtyExtremeBar"] is True
    assert result["barStats"]["conflictExpansionCount"] == 1


def test_robust_base_width_ignores_one_extreme_wick():
    closes = [100.0 + (0.15 if index % 2 else -0.15) for index in range(20)]
    rows = _rows_from_closes(closes)
    rows[-10]["high"] = 125.0

    result = analyze_clean_k_v2(rows, period=20)

    assert result["structureScores"]["robustBaseCleanScore"] >= 65
    assert result["structureScores"]["legacyBaseCleanScore"] <= 30


def test_base_to_trend_is_a_legal_composite_structure():
    base = [100.0 + (0.12 if index % 2 else -0.12) for index in range(10)]
    trend = [101.0 + index * 0.9 for index in range(10)]

    result = analyze_clean_k_v2(_rows_from_closes(base + trend), period=20)

    assert result["window"]["structure"] == "BASE_TO_TREND"
    assert result["window"]["structureScore"] >= 65
    assert result["transitions"] == ["BASE_TO_TREND"]
    assert len(result["segments"]) == 2
    assert result["current"]["days"] <= result["segments"][-1]["days"]


def test_orderly_trend_pullback_trend_is_not_called_chaotic():
    first_leg = [100.0 + index * 0.9 for index in range(7)]
    pullback = [105.0 - index * 0.45 for index in range(5)]
    second_leg = [103.6 + index * 1.0 for index in range(8)]

    result = analyze_clean_k_v2(
        _rows_from_closes(first_leg + pullback + second_leg), period=20
    )

    assert result["window"]["structure"] == "TREND_PULLBACK_TREND"
    assert result["transitions"] == ["TREND_PULLBACK_TREND"]
    assert result["window"]["isClean"] is True


def test_current_result_finds_longest_clean_suffix_after_noisy_history():
    noisy = [100, 108, 97, 109, 96, 110, 95, 109, 96, 108, 95, 107]
    current = [100.0 + index * 0.65 for index in range(8)]

    result = analyze_clean_k_v2(_rows_from_closes(noisy + current), period=20)

    assert result["window"]["score"] < result["current"]["score"]
    assert result["current"]["isClean"] is True
    assert 7 <= result["current"]["days"] <= 9
    assert result["current"]["startDate"] == result["barMetrics"][-result["current"]["days"]]["tradeDate"]


def test_random_wide_whipsaw_cannot_be_rescued_by_segment_search():
    closes = [100, 111, 94, 113, 92, 110, 91, 114, 93, 112,
              90, 115, 92, 113, 89, 116, 91, 114, 90, 112]

    result = analyze_clean_k_v2(_rows_from_closes(closes), period=20)

    assert result["window"]["isClean"] is False
    assert result["window"]["structure"] == "CHAOTIC"
    assert "CHAOTIC_STRUCTURE" in result["window"]["blockingReasons"]
    assert result["current"]["isClean"] is False


def test_v2_keeps_v1_top_level_contract_as_window_aliases():
    result = analyze_clean_k_v2(
        _rows_from_closes([100.0 + index * 0.4 for index in range(20)]),
        period=20,
        stock_code="300888",
    )

    assert result["modelVersion"] == "CLEAN_K_V2"
    assert result["cleanKScore"] == result["window"]["score"]
    assert result["isClean"] == result["window"]["isClean"]
    assert result["structureMode"] == result["window"]["structure"]
    assert result["stockCode"] == "300888"
    assert "legacyV1" in result


def test_one_price_event_suffix_cannot_crash_or_become_a_clean_current_segment():
    rows = _rows_from_closes([100.0] * 20)
    for row in rows[-6:]:
        row.update(open=100.0, high=100.0, low=100.0, close=100.0)

    result = analyze_clean_k_v2(rows, period=20)

    assert result["barStats"]["eventBarCount"] == 6
    assert result["current"]["isClean"] is False
    assert result["current"]["days"] == 0
    assert "TOO_MANY_TRAILING_EVENTS" in result["current"]["blockingReasons"]


def test_v2_rejects_weight_groups_that_do_not_sum_to_one():
    with pytest.raises(CleanKInputError, match="sum to 1"):
        resolve_clean_k_v2_config({"window_structure_weight": 0.70})

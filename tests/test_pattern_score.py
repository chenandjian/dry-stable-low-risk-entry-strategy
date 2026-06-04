# tests/test_pattern_score.py
import pytest
from analyzer.pattern_score import score_pattern, PatternScoreResult
from scanner.pattern_detector import CupHandleResult


def test_perfect_cup_handle_scores_high():
    r = CupHandleResult(
        found=True,
        cup_depth_pct=22.0,
        cup_duration=65,
        lip_deviation_pct=3.0,
        handle_depth_pct=5.0,
        handle_duration=12,
        handle_low_price=58.0,
        left_high_price=65.0,
        cup_low_price=52.0,
        right_high_price=62.0,
        left_high_idx=40,
        right_high_idx=120,
        cup_low_idx=80,
        handle_low_idx=135,
    )
    data = _make_basic_data(200)
    result = score_pattern(r, data)
    assert result.total_score > 0
    assert result.pattern_type != "无有效形态"


def test_no_pattern():
    r = CupHandleResult(found=False)
    result = score_pattern(r, [])
    assert result.total_score == 0
    assert result.pattern_type == "无有效形态"


def test_vcp_scores_when_contractions_tighten():
    r = CupHandleResult(found=False)
    data = _make_vcp_data()

    result = score_pattern(r, data)

    assert result.vcp_score >= 13
    assert result.total_score == result.vcp_score
    assert "VCP" in result.pattern_type


def _make_basic_data(n):
    import random
    random.seed(1)
    data = []
    for i in range(n):
        c = 50.0 + random.uniform(-5, 5)
        data.append({
            "date": f"2026-{i//20 + 1:02d}-{i%20 + 1:02d}",
            "open": c * random.uniform(0.98, 1.02),
            "high": c * random.uniform(1.01, 1.05),
            "low": c * random.uniform(0.95, 0.99),
            "close": c,
            "volume": random.uniform(5_000_000, 15_000_000),
        })
    return data


def _make_vcp_data():
    closes = []
    volumes = []

    # Prior uptrend: 40 -> 60
    for i in range(50):
        closes.append(40 + i * 0.4)
        volumes.append(12_000_000)

    # Three tightening contractions: 25%, 12%, 6%, each with lower volume.
    points = [
        (60, 45, 10_000_000),
        (58, 51, 7_000_000),
        (57, 53.6, 4_000_000),
    ]
    for high, low, vol in points:
        for i in range(5):
            closes.append(high - (high - low) * (i / 4))
            volumes.append(vol)
        for i in range(5):
            closes.append(low + (high - low) * 0.7 * (i / 4))
            volumes.append(vol * 0.9)

    # Tight area close to pivot.
    for c in [55.5, 56.0, 56.2, 56.5, 56.7, 56.8]:
        closes.append(c)
        volumes.append(3_500_000)

    data = []
    for i, c in enumerate(closes):
        data.append({
            "date": f"2025-{i // 20 + 1:02d}-{i % 20 + 1:02d}",
            "open": c * 0.995,
            "high": c * 1.01,
            "low": c * 0.99,
            "close": c,
            "volume": volumes[i],
            "turnover": c * volumes[i],
        })
    return data

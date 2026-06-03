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

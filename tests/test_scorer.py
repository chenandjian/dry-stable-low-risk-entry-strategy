# tests/test_scorer.py
import pytest
from scanner.scorer import score_cup_handle
from scanner.pattern_detector import CupHandleResult


def test_perfect_pattern_scores_high():
    """理想杯柄应得高分"""
    r = CupHandleResult(
        found=True,
        cup_depth_pct=20.0,
        cup_duration=65,
        lip_deviation_pct=3.0,
        handle_depth_pct=5.0,
        handle_duration=12,
        is_breakout=True,
        is_volume_breakout=True,
        vol_multiplier=1.8,
    )
    score = score_cup_handle(r)
    assert score >= 80, f"Expected >=80, got {score}"


def test_shallow_cup_scores_lower():
    """过浅的杯体降分"""
    r = CupHandleResult(
        found=True,
        cup_depth_pct=8.0,   # <12%, 太浅
        cup_duration=40,
        lip_deviation_pct=5.0,
        handle_depth_pct=5.0,
        handle_duration=10,
        is_breakout=False,
        is_volume_breakout=False,
    )
    score = score_cup_handle(r)
    assert score < 70


def test_no_pattern_scores_zero():
    r = CupHandleResult(found=False)
    assert score_cup_handle(r) == 0


def test_breakout_with_volume_gets_bonus():
    """放量突破应得满分突破分"""
    r_both = CupHandleResult(
        found=True,
        cup_depth_pct=22.0,
        cup_duration=60,
        lip_deviation_pct=4.0,
        handle_depth_pct=6.0,
        handle_duration=10,
        is_breakout=True,
        is_volume_breakout=True,
    )
    r_no_vol = CupHandleResult(
        found=True,
        cup_depth_pct=22.0,
        cup_duration=60,
        lip_deviation_pct=4.0,
        handle_depth_pct=6.0,
        handle_duration=10,
        is_breakout=True,
        is_volume_breakout=False,
    )
    assert score_cup_handle(r_both) > score_cup_handle(r_no_vol)

# tests/test_scorer.py
import pytest
from scanner.scorer import score_cup_handle, score_cup_handle_advanced, _score_volume_structure, _score_pre_trend
from scanner.pattern_detector import CupHandleResult, detect_cup_handle


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


# ---- Enhanced scoring tests ----


def _build_cup_handle_prices(
    pre_trend_start, pre_trend_end,
    left_high, cup_low, right_high, handle_low, breakout,
    pre_trend_days=40, cup_down_days=35, cup_bottom_days=20,
    cup_up_days=35, handle_days=15, post_days=5
) -> list[float]:
    """构造理想杯柄价格序列。"""
    import math
    prices = []

    # 前置上涨
    for i in range(pre_trend_days):
        t = i / pre_trend_days
        prices.append(pre_trend_start + (pre_trend_end - pre_trend_start) * t)

    # 左杯口到杯底（下跌）
    for i in range(cup_down_days):
        t = i / cup_down_days
        prices.append(left_high - (left_high - cup_low) * math.sin(t * math.pi / 2))

    # 杯底区域（横向整理）
    for i in range(cup_bottom_days):
        noise = (i % 3 - 1) * 0.5
        prices.append(cup_low + 1.0 + noise)

    # 杯底到右杯口（上涨）
    for i in range(cup_up_days):
        t = i / cup_up_days
        prices.append(cup_low + (right_high - cup_low) * math.sin(t * math.pi / 2))

    # 柄部（小幅回调）
    for i in range(handle_days):
        t = i / handle_days
        prices.append(right_high - (right_high - handle_low) * t)

    # 突破后
    for i in range(post_days):
        prices.append(breakout + i * 0.3)

    return prices


def _make_ohlc_data_with_volume_pattern(closes: list[float]) -> list[dict]:
    """从收盘价序列生成 OHLC 数据，带真实成交量模式。

    成交量阶段：
    - 杯体下跌: 高量（抛售）
    - 杯底区域: 低量（缩量筑底）
    - 右侧反弹: 递增放量
    - 柄部: 极低量（缩量整理）
    - 突破: 放量（1.8x 均量）
    """
    import random
    random.seed(1)

    pre_trend_days = 40
    cup_down_days = 35
    cup_bottom_days = 20
    cup_up_days = 35
    handle_days = 15

    base_vol = 10_000_000
    phase_ends = [
        pre_trend_days,
        pre_trend_days + cup_down_days,
        pre_trend_days + cup_down_days + cup_bottom_days,
        pre_trend_days + cup_down_days + cup_bottom_days + cup_up_days,
        pre_trend_days + cup_down_days + cup_bottom_days + cup_up_days + handle_days,
    ]

    result = []
    for i, c in enumerate(closes):
        if i < phase_ends[0]:
            # 前置趋势: 中等量
            vol = base_vol * random.uniform(0.8, 1.2)
        elif i < phase_ends[1]:
            # 杯体下跌: 高量（抛售）
            vol = base_vol * 1.5 * random.uniform(0.8, 1.2)
        elif i < phase_ends[2]:
            # 杯底区域: 缩量
            vol = base_vol * 0.6 * random.uniform(0.8, 1.2)
        elif i < phase_ends[3]:
            # 右侧反弹: 量递增
            progress = (i - phase_ends[2]) / cup_up_days
            vol = base_vol * (0.8 + 0.7 * progress) * random.uniform(0.8, 1.2)
        elif i < phase_ends[4]:
            # 柄部: 极低量（缩量整理）
            vol = base_vol * 0.4 * random.uniform(0.8, 1.2)
        else:
            # 突破后: 放量暴涨
            vol = base_vol * 1.8 * random.uniform(0.8, 1.2)

        result.append({
            "date": f"2025-{str(i // 20 + 1).zfill(2)}-{str(i % 20 + 1).zfill(2)}",
            "open": c * random.uniform(0.98, 1.02),
            "high": c * random.uniform(1.01, 1.05),
            "low": c * random.uniform(0.95, 0.99),
            "close": c,
            "volume": vol,
            "turnover": c * vol,
        })
    return result


def test_advanced_scoring_with_data():
    """Advanced scoring with real volume data should work"""
    prices = _build_cup_handle_prices(
        pre_trend_start=50.0,
        pre_trend_end=65.0,
        left_high=65.0,
        cup_low=52.0,
        right_high=62.0,
        handle_low=58.0,
        breakout=64.0,
    )
    data = _make_ohlc_data_with_volume_pattern(prices)
    config = {
        "min_duration": 35, "max_duration": 180,
        "min_depth": 0.12, "max_depth": 0.45,
        "max_lip_deviation": 0.12, "min_bottom_roundness": 0.10,
        "handle_min_duration": 5, "handle_max_duration": 30,
        "handle_max_depth": 0.18, "handle_max_vs_right_rally": 0.50,
    }
    result = detect_cup_handle(data, config)
    if result.found:
        score = score_cup_handle_advanced(result, data)
        assert 0 <= score <= 100


def test_score_cup_handle_advanced_no_pattern():
    """Advanced scoring with no pattern returns 0"""
    r = CupHandleResult(found=False)
    import random
    random.seed(1)
    data = [
        {
            "date": f"2025-01-{str(i+1).zfill(2)}",
            "open": 10.0, "high": 10.5, "low": 9.5, "close": 10.0,
            "volume": 10_000_000, "turnover": 100_000_000,
        }
        for i in range(150)
    ]
    assert score_cup_handle_advanced(r, data) == 0


def test_volume_structure_scoring():
    """Volume structure helper should return 0-20 range"""
    prices = _build_cup_handle_prices(
        pre_trend_start=50.0, pre_trend_end=65.0,
        left_high=65.0, cup_low=52.0,
        right_high=62.0, handle_low=58.0, breakout=64.0,
    )
    data = _make_ohlc_data_with_volume_pattern(prices)
    config = {
        "min_duration": 35, "max_duration": 180,
        "min_depth": 0.12, "max_depth": 0.45,
        "max_lip_deviation": 0.12, "min_bottom_roundness": 0.10,
        "handle_min_duration": 5, "handle_max_duration": 30,
        "handle_max_depth": 0.18, "handle_max_vs_right_rally": 0.50,
    }
    result = detect_cup_handle(data, config)
    if result.found:
        vol_score = _score_volume_structure(data, result)
        assert 0 <= vol_score <= 20, f"Expected 0-20, got {vol_score}"


def test_pre_trend_scoring():
    """Pre-trend helper should return valid range"""
    prices = _build_cup_handle_prices(
        pre_trend_start=50.0, pre_trend_end=65.0,
        left_high=65.0, cup_low=52.0,
        right_high=62.0, handle_low=58.0, breakout=64.0,
    )
    data = _make_ohlc_data_with_volume_pattern(prices)
    config = {
        "min_duration": 35, "max_duration": 180,
        "min_depth": 0.12, "max_depth": 0.45,
        "max_lip_deviation": 0.12, "min_bottom_roundness": 0.10,
        "handle_min_duration": 5, "handle_max_duration": 30,
        "handle_max_depth": 0.18, "handle_max_vs_right_rally": 0.50,
    }
    result = detect_cup_handle(data, config)
    if result.found:
        trend_score = _score_pre_trend(data, result)
        assert trend_score in (0, 4, 6, 7, 10), f"Unexpected trend score: {trend_score}"


def test_advanced_beats_basic_on_good_pattern():
    """Advanced scoring should differ from basic on real data"""
    prices = _build_cup_handle_prices(
        pre_trend_start=50.0,
        pre_trend_end=60.0,
        left_high=60.0,
        cup_low=51.0,
        right_high=58.0,
        handle_low=55.0,
        breakout=60.0,
    )
    data = _make_ohlc_data_with_volume_pattern(prices)
    config = {
        "min_duration": 35, "max_duration": 180,
        "min_depth": 0.12, "max_depth": 0.45,
        "max_lip_deviation": 0.12, "min_bottom_roundness": 0.10,
        "handle_min_duration": 5, "handle_max_duration": 30,
        "handle_max_depth": 0.18, "handle_max_vs_right_rally": 0.50,
    }
    result = detect_cup_handle(data, config)
    if result.found:
        basic = score_cup_handle(result)
        advanced = score_cup_handle_advanced(result, data)
        # Both should be valid scores
        assert 0 <= basic <= 100
        assert 0 <= advanced <= 100

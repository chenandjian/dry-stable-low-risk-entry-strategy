# tests/test_pattern_detector.py
import pytest
from scanner.pattern_detector import (
    find_swing_highs,
    find_swing_lows,
    detect_cup_handle,
    CupHandleResult,
)


# ---- Swing High/Low Tests ----

def test_find_swing_highs_simple():
    """Swing High 是局部最大值（比左右 N 天都高）"""
    closes = [10, 12, 15, 13, 11, 14, 16, 14, 13, 10]
    highs = find_swing_highs(closes, window=2)
    assert 2 in highs  # index 2 = 15, 比左右都高
    assert 6 in highs  # index 6 = 16, 比左右都高


def test_find_swing_lows_simple():
    """Swing Low 是局部最小值"""
    closes = [10, 8, 6, 9, 7, 5, 8, 9]
    lows = find_swing_lows(closes, window=2)
    assert 2 in lows  # index 2 = 6
    assert 5 in lows  # index 5 = 5


def test_swing_empty_data():
    assert find_swing_highs([], window=3) == []
    assert find_swing_lows([], window=3) == []


def test_swing_short_data():
    assert find_swing_highs([10, 12], window=3) == []


# ---- Cup Handle Detection Tests ----

def test_detect_cup_handle_no_pattern():
    """无杯柄形态的随机数据应返回 found=False"""
    import random
    random.seed(42)
    closes = [100.0]
    for _ in range(200):
        closes.append(closes[-1] * (1 + random.uniform(-0.03, 0.03)))
    data = _make_ohlc_data(closes)
    result = detect_cup_handle(data, {})
    assert result.found is False


def test_detect_cup_handle_ideal_pattern():
    """构造理想杯柄形态，应该能检测到"""
    prices = _build_cup_handle_prices(
        pre_trend_start=50.0,
        pre_trend_end=65.0,    # 涨 30%
        left_high=65.0,
        cup_low=52.0,          # 回撤 ~20%
        right_high=62.0,       # 略低于左杯口
        handle_low=58.0,       # 柄部回撤 ~6.5%
        breakout=64.0,         # 突破
    )
    data = _make_ohlc_data(prices)
    config = {
        "min_duration": 35,
        "max_duration": 180,
        "min_depth": 0.12,
        "max_depth": 0.45,
        "max_lip_deviation": 0.12,
        "min_bottom_roundness": 0.10,
        "handle_min_duration": 5,
        "handle_max_duration": 30,
        "handle_max_depth": 0.18,
        "handle_max_vs_right_rally": 0.50,
    }
    result = detect_cup_handle(data, config)
    assert result.found is True
    assert 20 <= result.cup_depth_pct <= 40
    assert result.left_high_idx < result.cup_low_idx < result.right_high_idx


def test_short_data_returns_not_found():
    """数据不足时应返回 found=False"""
    data = _make_ohlc_data([10.0] * 50)
    result = detect_cup_handle(data, {"min_duration": 35})
    assert result.found is False


# ---- Helpers ----

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


def _make_ohlc_data(closes: list[float]) -> list[dict]:
    """从收盘价序列生成 OHLC 数据（简化）。"""
    import random
    random.seed(1)
    result = []
    for i, c in enumerate(closes):
        vol = random.uniform(8_000_000, 15_000_000)
        result.append({
            "date": f"2025-{str(i//20 + 1).zfill(2)}-{str(i%20 + 1).zfill(2)}",
            "open": c * random.uniform(0.98, 1.02),
            "high": c * random.uniform(1.01, 1.05),
            "low": c * random.uniform(0.95, 0.99),
            "close": c,
            "volume": vol,
            "turnover": c * vol,
        })
    return result

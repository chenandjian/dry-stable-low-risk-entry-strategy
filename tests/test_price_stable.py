# tests/test_price_stable.py
import pytest
from analyzer.price_stable import score_price_stable, PriceStableResult
import random


def test_stable_price_scores_high():
    """波动收窄、低点抬高的稳定走势应得高分"""
    random.seed(1)
    data = _make_stable_data(
        range_contraction=True,
        no_new_lows=True,
        higher_lows=True,
        above_ma=True,
        atr_declining=True,
    )
    result = score_price_stable(data)
    assert result.total_score >= 7
    assert result.verdict == "可低吸"


def test_unstable_price_scores_low():
    """持续下跌、波动扩大的走势应得低分"""
    data = _make_stable_data(
        range_contraction=False,
        no_new_lows=False,
        higher_lows=False,
        above_ma=False,
        atr_declining=False,
    )
    result = score_price_stable(data)
    assert result.total_score < 6
    assert result.verdict != "可低吸"


def test_new_low_caps_score():
    """创20日新低封顶5分"""
    data = _make_stable_data(
        range_contraction=False,
        no_new_lows=False,  # has new 20-day low
        higher_lows=False,
        above_ma=False,
        atr_declining=False,
        force_new_low=True,
    )
    result = score_price_stable(data)
    assert result.total_score <= 5


def test_empty_data():
    result = score_price_stable([])
    assert result.total_score == 0


def _make_stable_data(range_contraction, no_new_lows, higher_lows, above_ma, atr_declining, force_new_low=False):
    """Generate ~50 days of OHLC data for price stability testing."""
    random.seed(42)
    n = 50
    prices = []
    base = 50.0

    # Build price sequence
    if no_new_lows:
        # Gradual recovery from a dip
        for i in range(n):
            t = i / n
            p = 42.0 + 8.0 * t + random.uniform(-0.3, 0.3)
            if force_new_low and i == n - 1:
                p = 39.0  # new 20-day low
            prices.append(p)
    else:
        # Downtrend
        for i in range(n):
            p = base - i * 0.15 + random.uniform(-0.5, 0.5)
            if force_new_low and i == n - 1:
                p = 35.0
            prices.append(p)

    data = []
    for i, close in enumerate(prices):
        # Control range (high-low spread)
        if range_contraction and i >= n - 5:
            spread = 0.3 + random.uniform(0, 0.1)  # narrow
        else:
            spread = 1.2 + random.uniform(0, 0.5)  # wide

        high = close + spread / 2
        low = close - spread / 2
        open_p = close - random.uniform(-0.2, 0.2) * spread
        vol = random.uniform(5_000_000, 12_000_000)

        data.append({
            "date": f"2026-{str(30 + i // 20).zfill(2)}-{str((i % 20) + 1).zfill(2)}",
            "open": open_p,
            "high": high,
            "low": low,
            "close": close,
            "volume": vol,
        })

    return data

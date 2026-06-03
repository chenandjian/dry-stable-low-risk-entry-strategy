# tests/test_liquidity_filter.py
import pytest
from scanner.liquidity_filter import passes_liquidity_filter, _avg


def test_avg():
    assert _avg([1, 2, 3]) == 2.0
    assert _avg([10]) == 10.0
    assert _avg([]) == 0.0


def test_passes_with_sufficient_liquidity():
    """流动性充足的股票应通过"""
    data = _make_data(close=40.0, volume=10_000_000, count=30)
    config = {
        "enabled": True,
        "avg_turnover_days": 20,
        "min_avg_turnover": 100_000_000,
        "min_avg_volume": 5_000_000,
        "min_latest_turnover": 80_000_000,
    }
    assert passes_liquidity_filter(data, config) is True


def test_fails_low_turnover():
    """成交额不足应拒绝"""
    data = _make_data(close=1.0, volume=1_000_000, count=30)
    config = {
        "enabled": True,
        "avg_turnover_days": 20,
        "min_avg_turnover": 100_000_000,
        "min_avg_volume": 5_000_000,
        "min_latest_turnover": 80_000_000,
    }
    assert passes_liquidity_filter(data, config) is False


def test_disabled_filter_always_passes():
    """流动性过滤关闭时直接通过"""
    data = _make_data(close=0.01, volume=100, count=5)
    config = {"enabled": False}
    assert passes_liquidity_filter(data, config) is True


def test_empty_data_fails():
    """空数据不通过"""
    assert passes_liquidity_filter([], {"enabled": True}) is False


def test_insufficient_days():
    """数据天数不足时不通过"""
    data = _make_data(close=40.0, volume=10_000_000, count=5)
    config = {"enabled": True, "avg_turnover_days": 20}
    assert passes_liquidity_filter(data, config) is False


def _make_data(close: float, volume: int, count: int) -> list[dict]:
    return [
        {
            "date": f"2026-06-{str(i+1).zfill(2)}",
            "open": close * 0.99,
            "high": close * 1.02,
            "low": close * 0.98,
            "close": close,
            "volume": volume,
            "turnover": close * volume,
        }
        for i in range(count)
    ]

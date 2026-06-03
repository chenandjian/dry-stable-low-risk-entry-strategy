# tests/test_edge_cases.py
import pytest
from scanner.liquidity_filter import passes_liquidity_filter
from scanner.pattern_detector import detect_cup_handle, CupHandleResult
from scanner.scorer import score_cup_handle


def test_liquidity_missing_turnover_field():
    """数据缺少 turnover 字段时用 volume*close 估算"""
    data = []
    for i in range(30):
        data.append({
            "date": f"2026-06-{str(i+1).zfill(2)}",
            "open": 40.0, "high": 41.0, "low": 39.0, "close": 40.5,
            "volume": 10_000_000,
            # 没有 turnover 字段
        })
    config = {
        "enabled": True,
        "avg_turnover_days": 20,
        "min_avg_turnover": 100_000_000,
        "min_avg_volume": 5_000_000,
        "min_latest_turnover": 80_000_000,
    }
    # 10,000,000 * 40.5 = 405,000,000 > 100M, should pass
    assert passes_liquidity_filter(data, config) is True


def test_liquidity_zero_volume():
    """成交量为0的退市股应被过滤"""
    data = []
    for i in range(30):
        data.append({
            "date": f"2026-06-{str(i+1).zfill(2)}",
            "open": 5.0, "high": 5.0, "low": 5.0, "close": 5.0,
            "volume": 0, "turnover": 0,
        })
    config = {
        "enabled": True,
        "avg_turnover_days": 20,
        "min_avg_turnover": 1,
        "min_avg_volume": 1,
        "min_latest_turnover": 1,
    }
    assert passes_liquidity_filter(data, config) is False


def test_extreme_price_data():
    """极端价格不应导致评分崩溃"""
    r = CupHandleResult(
        found=True,
        cup_depth_pct=99.0,    # 极端深度
        cup_duration=200,       # 极端长
        lip_deviation_pct=50.0, # 极端偏差
        handle_depth_pct=50.0,  # 极端柄部
        handle_duration=50,     # 极端长
        is_breakout=False,
        is_volume_breakout=False,
    )
    score = score_cup_handle(r)
    assert 0 <= score <= 100  # 评分始终在有效范围


def test_pattern_empty_data_array():
    """空数据数组不应崩溃"""
    result = detect_cup_handle([], {})
    assert isinstance(result, CupHandleResult)
    assert result.found is False

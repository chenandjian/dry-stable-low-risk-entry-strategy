# tests/test_backtester.py
import pytest
from scanner.backtester import (
    BacktestResult, BacktestReport, _calc_forward,
    _aggregate, run_backtest, backtest_report_to_dict,
)


def test_calc_forward_returns():
    """前向收益率计算"""
    br = BacktestResult()
    detect_close = 100.0
    breakout_price = 105.0
    future = [
        {"close": 102.0, "low": 101.0},  # day 1
        {"close": 103.0, "low": 100.0},  # day 2
        {"close": 104.0, "low": 102.0},  # day 3
        {"close": 101.0, "low": 99.0},   # day 4
        {"close": 106.0, "low": 103.0},  # day 5
        {"close": 108.0, "low": 104.0},  # day 6
        {"close": 107.0, "low": 105.0},  # day 7
        {"close": 110.0, "low": 106.0},  # day 8
        {"close": 112.0, "low": 108.0},  # day 9
        {"close": 115.0, "low": 110.0},  # day 10
        # ... more days for 20d, 60d tests
    ]
    # Extend for longer horizons
    for i in range(50):
        future.append({"close": 120.0 + i * 0.5, "low": 118.0 + i * 0.5})

    _calc_forward(br, detect_close, breakout_price, future)

    assert br.ret_5d is not None
    assert br.ret_5d == 6.0  # (106 - 100) / 100 * 100
    assert br.hit_5d is True
    assert br.false_breakout_5d is True  # low of day 4 = 99 < 105 * 0.97


def test_backtest_report_to_dict():
    """报告转字典"""
    report = BacktestReport(
        total_patterns=10,
        total_stocks_tested=100,
        hit_rate_10d=65.5,
        avg_return_10d=3.2,
    )
    d = backtest_report_to_dict(report)
    assert d["total_patterns"] == 10
    assert d["hit_rates"]["10d"] == 65.5
    assert d["avg_returns"]["10d"] == 3.2


def test_empty_backtest():
    """空回测不崩溃"""
    report = BacktestReport()
    _aggregate(report, [])
    assert report.total_patterns == 0


def test_aggregate_statistics():
    """聚合统计计算"""
    r1 = BacktestResult(ret_10d=5.0, hit_10d=True, false_breakout_10d=False, stop_loss_hit_10d=False)
    r2 = BacktestResult(ret_10d=-2.0, hit_10d=False, false_breakout_10d=True, stop_loss_hit_10d=False)
    r3 = BacktestResult(ret_10d=8.0, hit_10d=True, false_breakout_10d=False, stop_loss_hit_10d=False)

    report = BacktestReport()
    _aggregate(report, [r1, r2, r3])

    assert report.avg_return_10d == round((5.0 - 2.0 + 8.0) / 3, 2)
    assert report.hit_rate_10d == round(2 / 3 * 100, 1)
    assert report.false_breakout_rate_10d == round(1 / 3 * 100, 1)

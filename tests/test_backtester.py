# tests/test_backtester.py
import pytest
from scanner.backtester import (
    BacktestResult, BacktestReport, _calc_forward,
    _aggregate, run_backtest, backtest_report_to_dict,
)


def test_calc_forward_returns():
    """前向收益率计算"""
    br = BacktestResult(pattern_kind="cup_handle")
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
        by_dry_stable_verdict={"可低吸": {"count": 2, "avg_ret_10d": 2.0}},
        results=[BacktestResult(code="600000", verdict="可低吸", ret_10d=2.0)],
    )
    d = backtest_report_to_dict(report)
    assert d["total_patterns"] == 10
    assert d["hit_rates"]["10d"] == 65.5
    assert d["avg_returns"]["10d"] == 3.2
    assert d["by_dry_stable_verdict"]["可低吸"]["count"] == 2
    assert d["results"][0]["verdict"] == "可低吸"


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


def test_stop_loss_hit_none_excluded_from_denominator():
    """ROUND3-003: stop_loss_hit=None samples excluded from stop-loss hit rate."""
    r1 = BacktestResult(actual_stop_loss=9.0, stop_loss_hit_10d=True)
    r2 = BacktestResult(actual_stop_loss=0.0, stop_loss_hit_10d=None)  # no valid stop
    r3 = BacktestResult(actual_stop_loss=9.0, stop_loss_hit_10d=False)

    report = BacktestReport()
    _aggregate(report, [r1, r2, r3])

    # Only r1 and r3 have valid stop_loss; denominator = 2
    assert report.stop_loss_hit_rate_10d == 50.0  # 1 hit / 2 valid


def test_stop_loss_hit_only_set_when_actual_stop_valid():
    """ROUND3-003: _calc_forward only sets stop_loss_hit when actual_stop_loss > 0."""
    br = BacktestResult(actual_stop_loss=0.0)  # no valid stop
    detect_close = 100.0
    breakout_price = 105.0
    future = [{"close": 102.0, "low": 98.0} for _ in range(10)]

    _calc_forward(br, detect_close, breakout_price, future)

    # stop_loss_hit should remain None (default) when no valid stop
    assert br.stop_loss_hit_5d is None
    assert br.stop_loss_hit_10d is None
    assert br.stop_loss_hit_20d is None


def test_false_breakout_none_for_vcp_patterns():
    """ROUND3-004: VCP patterns get false_breakout=None, excluded from aggregate."""
    # Cup-handle with valid breakout: false_breakout computed
    br_ch = BacktestResult(pattern_kind="cup_handle")
    detect_close = 100.0
    breakout_price = 105.0
    future = [{"close": 102.0, "low": 101.0} for _ in range(10)]
    _calc_forward(br_ch, detect_close, breakout_price, future)
    # breakout_price=105, min_low=101, 101 < 105*0.97=101.85 → false_breakout=True
    assert br_ch.false_breakout_5d is True

    # VCP with breakout_price=0: false_breakout should be None
    br_vcp = BacktestResult(pattern_kind="vcp")
    _calc_forward(br_vcp, detect_close, 0.0, future)
    assert br_vcp.false_breakout_5d is None

    # VCP with any breakout_price: still None (not cup_handle)
    br_vcp2 = BacktestResult(pattern_kind="vcp")
    _calc_forward(br_vcp2, detect_close, 105.0, future)
    assert br_vcp2.false_breakout_5d is None

    # Aggregate: mixing cup_handle and VCP, VCP excluded from false_breakout denom
    report = BacktestReport()
    _aggregate(report, [br_ch, br_vcp])
    # Only br_ch has valid false_breakout (True), br_vcp's None is excluded
    assert report.false_breakout_rate_5d == 100.0  # 1/1


def test_run_backtest_accepts_market_data_injection(monkeypatch, tmp_path):
    """ROUND3-006: run_backtest uses injected market_data instead of fetching live."""
    from scanner import backtester
    from scanner import db as db_mod

    db_path = tmp_path / "cuphandle.db"
    db_mod.init_db(str(db_path))

    # Prepare OHLC data for a stock
    dates = []
    for i in range(400):
        dates.append(f"2025-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}")
    ohlc = [{"date": d, "open": 10.0, "high": 10.5, "low": 9.5, "close": 10.2, "volume": 1_000_000, "turnover": 10_200_000} for d in dates]
    db_mod.save_ohlc("600000", ohlc)

    injected_market = [{"date": d, "open": 3000, "high": 3010, "low": 2990, "close": 3005, "volume": 1_000_000} for d in dates]

    fetch_called = []

    def fake_fetch_market(symbol=None):
        fetch_called.append(symbol)
        return [{"date": "2025-12-25", "open": 3100, "high": 3110, "low": 3090, "close": 3105, "volume": 2_000_000}]

    monkeypatch.setattr(backtester, "fetch_market_index_daily", fake_fetch_market)

    config = {
        "data": {"database_path": str(db_path), "daily_kline_days": 250},
        "cup": {"max_duration": 60},
        "handle": {"max_duration": 20},
        "breakout": {},
        "scoring": {"medium_threshold": 70},
        "liquidity": {"min_listing_days": 250},
        "market_environment": {"index_symbol": "000001"},
    }

    def fake_fetch(code):
        return db_mod.get_ohlc(code)

    # Run with injected market_data
    report = run_backtest(
        [{"code": "600000", "name": "Test"}],
        fake_fetch,
        config,
        window_min=250,
        max_stocks=1,
        market_data=injected_market,
    )

    # Live fetch should NOT have been called
    assert fetch_called == []
    assert report.total_stocks_tested == 1

    # Run WITHOUT injection → should call live fetch
    report2 = run_backtest(
        [{"code": "600000", "name": "Test"}],
        fake_fetch,
        config,
        window_min=350,  # require more data than available to avoid actual pattern detection
        max_stocks=1,
    )
    assert len(fetch_called) > 0


def test_insufficient_future_data_excluded_from_hit_rate():
    """ROUND4-001: hit_* defaults to None, excluded from denominator when future data short."""
    # Sample with full 10d future → valid hit
    r_full = BacktestResult(pattern_kind="cup_handle")
    full_future = [{"close": 105.0, "low": 100.0} for _ in range(20)]
    _calc_forward(r_full, 100.0, 105.0, full_future)
    # hit_10d should be set (bool)
    assert r_full.hit_10d is not None

    # Sample with only 5d future → 10d and up are None
    r_short = BacktestResult(pattern_kind="cup_handle")
    short_future = [{"close": 102.0, "low": 101.0} for _ in range(5)]
    _calc_forward(r_short, 100.0, 105.0, short_future)
    # 5d IS set (5 ≤ 5)
    assert r_short.hit_5d is not None
    # 10d, 20d, 60d are NOT set (insufficient data)
    assert r_short.hit_10d is None
    assert r_short.hit_20d is None
    assert r_short.hit_60d is None
    assert r_short.false_breakout_10d is None

    # Aggregate: denominator for 10d should be 1 (only r_full), not 2
    report = BacktestReport()
    _aggregate(report, [r_full, r_short])
    assert report.hit_rate_10d == 100.0  # r_full hit → 1/1


def test_insufficient_future_data_excluded_from_false_breakout_rate():
    """ROUND4-001: false_breakout defaults to None, excluded when future data insufficient."""
    r_full = BacktestResult(pattern_kind="cup_handle")
    r_short = BacktestResult(pattern_kind="cup_handle")
    full_future = [{"close": 105.0, "low": 104.0} for _ in range(20)]
    short_future = [{"close": 102.0, "low": 101.0} for _ in range(5)]

    _calc_forward(r_full, 100.0, 110.0, full_future)
    _calc_forward(r_short, 100.0, 110.0, short_future)

    # r_short should not contribute to 10d/20d false_breakout stats
    assert r_short.false_breakout_5d is not None  # 5d IS computed
    assert r_short.false_breakout_10d is None     # 10d NOT computed

    report = BacktestReport()
    _aggregate(report, [r_full, r_short])
    # Denominator is 1 (only r_full), not 2
    assert report.false_breakout_rate_10d == 100.0  # r_full: min_low=104 < 110*0.97=106.7 → true fb, 1/1 valid


def test_score_stratify_excludes_insufficient_data_hits():
    """ROUND4-001: _score_stratify excludes None hit/ret from rate calculations."""
    r_full = BacktestResult(score=80, ret_10d=5.0, hit_10d=True)
    r_short = BacktestResult(score=80, ret_10d=None, hit_10d=None)

    report = BacktestReport()
    from scanner.backtester import _score_stratify
    _score_stratify(report, [r_full, r_short])

    assert len(report.by_score_range) == 1
    assert report.by_score_range[0]["count"] == 2
    # hit_rate uses only the 1 sample with valid hit_10d
    assert report.by_score_range[0]["hit_rate_10d"] == 100.0

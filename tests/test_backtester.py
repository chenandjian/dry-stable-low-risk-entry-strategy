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
        "data": {"database_path": str(db_path), "daily_kline_days": 250, "backtest_window_days": 250},
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
        max_stocks=1,
        market_data=injected_market,
    )

    # Live fetch should NOT have been called
    assert fetch_called == []
    assert report.total_stocks_tested == 1

    # Run WITHOUT injection → should call live fetch
    # Set backtest_window_days higher than available data to avoid actual pattern detection
    config2 = {**config, "data": {**config["data"], "backtest_window_days": 350}}
    report2 = run_backtest(
        [{"code": "600000", "name": "Test"}],
        fake_fetch,
        config2,
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


# ── BUG-002: backtest loop boundaries ───────────────────────────────

def test_backtest_loop_boundary_exact_fit_evaluates_once(monkeypatch, tmp_path):
    """Data length = backtest_window + 60 → one strategy evaluation.

    BUG-002: range(250, 310) was empty for len=310, now range(250, 311) yields 1.
    """
    from scanner import backtester, db as db_mod

    db_path = tmp_path / "cuphandle.db"
    db_mod.init_db(str(db_path))

    backtest_window = 250
    min_forward = 60
    total_rows = backtest_window + min_forward  # 310

    dates = [f"2025-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}" for i in range(total_rows)]
    ohlc = [{"date": d, "open": 10.0, "high": 10.5, "low": 9.5, "close": 10.2, "volume": 1_000_000, "turnover": 10_200_000} for d in dates]
    db_mod.save_ohlc("600000", ohlc)

    eval_calls = []

    class FakeEngine:
        def __init__(self, config): pass
        def evaluate_at(self, data, code="", name="", market_data=None):
            eval_calls.append(len(data))
            return type("Eval", (), {"passed": False, "result": type("R", (), {"score": 0})(), "dry_stable": None})()

    monkeypatch.setattr(backtester, "CupHandleStrategyEngine", FakeEngine)
    monkeypatch.setattr(backtester, "fetch_market_index_daily", lambda symbol=None: [])

    config = {
        "data": {"database_path": str(db_path), "backtest_window_days": backtest_window},
        "liquidity": {"min_listing_days": backtest_window},
        "cup": {"max_duration": 60},
        "handle": {"max_duration": 20},
        "breakout": {},
        "scoring": {"medium_threshold": 70},
    }

    def fake_fetch(code):
        return db_mod.get_ohlc(code)

    report = backtester.run_backtest(
        [{"code": "600000", "name": "Test"}],
        fake_fetch,
        config,
        max_stocks=1,
    )
    assert report.total_stocks_tested == 1
    assert len(eval_calls) == 1


def test_backtest_loop_boundary_one_short_skips(monkeypatch, tmp_path):
    """Data length = backtest_window + 59 → no evaluation (insufficient forward)."""
    from scanner import backtester, db as db_mod

    db_path = tmp_path / "cuphandle.db"
    db_mod.init_db(str(db_path))

    backtest_window = 250
    total_rows = backtest_window + 59  # 309

    dates = [f"2025-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}" for i in range(total_rows)]
    ohlc = [{"date": d, "open": 10.0, "high": 10.5, "low": 9.5, "close": 10.2, "volume": 1_000_000, "turnover": 10_200_000} for d in dates]
    db_mod.save_ohlc("600001", ohlc)

    eval_calls = []

    class FakeEngine:
        def __init__(self, config): pass
        def evaluate_at(self, data, code="", name="", market_data=None):
            eval_calls.append(len(data))
            return type("Eval", (), {"passed": False, "result": type("R", (), {"score": 0})(), "dry_stable": None})()

    monkeypatch.setattr(backtester, "CupHandleStrategyEngine", FakeEngine)
    monkeypatch.setattr(backtester, "fetch_market_index_daily", lambda symbol=None: [])

    config = {
        "data": {"database_path": str(db_path), "backtest_window_days": backtest_window},
        "liquidity": {"min_listing_days": backtest_window},
        "cup": {"max_duration": 60},
        "handle": {"max_duration": 20},
        "breakout": {},
        "scoring": {"medium_threshold": 70},
    }

    def fake_fetch(code):
        return db_mod.get_ohlc(code)

    report = backtester.run_backtest(
        [{"code": "600001", "name": "Test"}],
        fake_fetch,
        config,
        max_stocks=1,
    )
    # len(data) = 309 < 250 + 60 → skipped before loop
    assert len(eval_calls) == 0


def test_backtest_loop_boundary_two_fits_evaluates_twice(monkeypatch, tmp_path):
    """Data length = backtest_window + 61 → two strategy evaluations."""
    from scanner import backtester, db as db_mod

    db_path = tmp_path / "cuphandle.db"
    db_mod.init_db(str(db_path))

    backtest_window = 250
    total_rows = backtest_window + 61  # 311

    dates = [f"2025-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}" for i in range(total_rows)]
    ohlc = [{"date": d, "open": 10.0, "high": 10.5, "low": 9.5, "close": 10.2, "volume": 1_000_000, "turnover": 10_200_000} for d in dates]
    db_mod.save_ohlc("600002", ohlc)

    eval_calls = []

    class FakeEngine:
        def __init__(self, config): pass
        def evaluate_at(self, data, code="", name="", market_data=None):
            eval_calls.append(len(data))
            return type("Eval", (), {"passed": False, "result": type("R", (), {"score": 0})(), "dry_stable": None})()

    monkeypatch.setattr(backtester, "CupHandleStrategyEngine", FakeEngine)
    monkeypatch.setattr(backtester, "fetch_market_index_daily", lambda symbol=None: [])

    config = {
        "data": {"database_path": str(db_path), "backtest_window_days": backtest_window},
        "liquidity": {"min_listing_days": backtest_window},
        "cup": {"max_duration": 60},
        "handle": {"max_duration": 20},
        "breakout": {},
        "scoring": {"medium_threshold": 70},
    }

    def fake_fetch(code):
        return db_mod.get_ohlc(code)

    report = backtester.run_backtest(
        [{"code": "600002", "name": "Test"}],
        fake_fetch,
        config,
        max_stocks=1,
    )
    assert report.total_stocks_tested == 1
    # n=311, range(250, 311-60+1)=range(250,252) → [250,251] → 2 calls
    assert len(eval_calls) == 2


# ── RECHECK-003: real path consistency ──────────────────────────────

def _make_ohlc_window(n_days: int, base_price: float = 20.0):
    """Build simple OHLC rows, n_days trading days."""
    rows = []
    for i in range(n_days):
        rows.append({
            "date": f"2025-{(i // 22) + 1:02d}-{(i % 22) + 1:02d}",
            "open": base_price + i * 0.01,
            "high": base_price + i * 0.01 + 0.1,
            "low": base_price + i * 0.01 - 0.1,
            "close": base_price + i * 0.01,
            "volume": 10_000_000,
            "turnover": 200_000_000,
        })
    return rows


def _evaluation_core(evaluation):
    """Extract core strategy result fields for cross-path comparison."""
    dry = evaluation.dry_stable or {}
    return {
        "passed": evaluation.passed,
        "score": evaluation.result.score,
        "pattern_kind": evaluation.result.pattern_kind,
        "verdict_key": dry.get("decision", {}).get("verdict_key"),
        "key_pattern_type": dry.get("pattern_score", {}).get("key_pattern_type"),
        "stop_loss": dry.get("key_prices", {}).get("stop_loss"),
        "entry_zone_low": dry.get("key_prices", {}).get("entry_zone_low"),
        "entry_zone_high": dry.get("key_prices", {}).get("entry_zone_high"),
    }


def test_scan_backtest_consistent_core_results_same_judgment_date(monkeypatch, tmp_path):
    """FINAL-003: scan_all + run_backtest produce identical core results.

    Uses real CupHandleStrategyEngine.  Scan and backtest look at the same
    judgment date with the same stock window and market data.
    """
    from scanner import engine, backtester, db as db_mod, stock_pool
    from scanner.strategy_engine import CupHandleStrategyEngine as RealEngine

    db_path = tmp_path / "cuphandle.db"
    db_mod.init_db(str(db_path))

    window_days = 120
    forward_days = 60
    total_rows = window_days + forward_days  # 180
    ohlc = _make_ohlc_window(total_rows)
    db_mod.save_ohlc("600000", ohlc)

    # judgment date = last day of the first window_days
    decision_data = ohlc[:window_days]
    decision_date = decision_data[-1]["date"]

    # Non-empty fixed market data covering full range
    market_full = [
        {"date": d["date"], "open": 3000, "high": 3010, "low": 2990, "close": 3005, "volume": 1_000_000}
        for d in ohlc
    ]

    # ── Scan path ──────────────────────────────────────────────
    scan_calls = []

    class ScanCapturingEngine(RealEngine):
        def evaluate_at(self, data, code="", name="", market_data=None):
            evaluation = super().evaluate_at(data, code=code, name=name, market_data=market_data)
            scan_calls.append({
                "stock_dates": [row["date"] for row in data],
                "market_dates": [row["date"] for row in (market_data or [])],
                "core": _evaluation_core(evaluation),
            })
            return evaluation

    class ImmediateThread:
        def __init__(self, target=None, args=(), daemon=None):
            self.target = target
            self.args = args
        def start(self):
            if self.target:
                self.target(*self.args)
        def join(self):
            return None

    monkeypatch.setattr(engine, "CupHandleStrategyEngine", ScanCapturingEngine)
    monkeypatch.setattr(engine, "DataSourceManager", type("FakeMgr", (), {}))
    monkeypatch.setattr(engine.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(engine, "_fetch_with_retry",
                        lambda *args, **kwargs: engine.FetchResult(
                            data=list(decision_data), primary_source="sina",
                            fallback_source="sina", primary_attempts=1))
    # Scan path market data: only up to decision date
    market_for_scan = [r for r in market_full if r["date"] <= decision_date]
    monkeypatch.setattr(engine, "fetch_market_index_daily", lambda symbol=None: list(market_for_scan))
    monkeypatch.setattr(engine, "passes_liquidity_filter", lambda data, cfg: True)
    monkeypatch.setattr(stock_pool, "get_a_stock_pool",
                        lambda config: [{"code": "600000", "name": "Test"}])

    config = {
        "data": {"database_path": str(db_path),
                 "scan_window_days": window_days, "backtest_window_days": window_days},
        "liquidity": {"enabled": False, "min_listing_days": window_days},
        "scoring": {"medium_threshold": 70},
        "cup": {"max_duration": 60},
        "handle": {"max_duration": 20},
        "breakout": {},
        "market_environment": {"index_symbol": "000001"},
    }

    engine.scan_all(config, worker_count=1)

    assert len(scan_calls) >= 1

    # ── Backtest path ──────────────────────────────────────────
    backtest_calls = []

    class BacktestCapturingEngine(RealEngine):
        def evaluate_at(self, data, code="", name="", market_data=None):
            evaluation = super().evaluate_at(data, code=code, name=name, market_data=market_data)
            backtest_calls.append({
                "stock_dates": [row["date"] for row in data],
                "market_dates": [row["date"] for row in (market_data or [])],
                "core": _evaluation_core(evaluation),
            })
            return evaluation

    monkeypatch.setattr(backtester, "CupHandleStrategyEngine", BacktestCapturingEngine)
    monkeypatch.setattr(backtester, "fetch_market_index_daily", lambda symbol=None: list(market_full))

    def fake_fetch_fn(code):
        return db_mod.get_ohlc(code)

    backtester.run_backtest(
        [{"code": "600000", "name": "Test"}],
        fake_fetch_fn, config, max_stocks=1,
    )

    # Find backtest call at same judgment date
    bt_same = [c for c in backtest_calls if c["stock_dates"][-1] == decision_date]
    assert len(bt_same) >= 1
    bt_call = bt_same[0]

    # ── Assertions ─────────────────────────────────────────────
    scan_call = scan_calls[0]

    # Same stock window dates
    assert scan_call["stock_dates"] == bt_call["stock_dates"]

    # Same core results
    assert scan_call["core"] == bt_call["core"]

    # No future data in market window
    assert all(date <= decision_date for date in bt_call["market_dates"])
    assert all(date <= decision_date for date in scan_call["market_dates"])


def test_scan_all_respects_min_listing_days_fetch(monkeypatch, tmp_path):
    """RECHECK-003: scan_all passes min_listing_days to data fetch, not daily_kline_days."""
    from scanner import engine, stock_pool

    db_path = tmp_path / "cuphandle.db"
    engine.db.init_db(str(db_path))

    fetch_kline_days = []

    def fake_fetch_with_retry(code, ds, *args, kline_days=None, **kwargs):
        fetch_kline_days.append(kline_days)
        data = _make_ohlc_window(kline_days)
        return engine.FetchResult(data=data, primary_source=ds, fallback_source="sina", primary_attempts=1)

    class ImmediateThread:
        def __init__(self, target=None, args=(), daemon=None):
            self.target = target
            self.args = args
        def start(self):
            if self.target:
                self.target(*self.args)
        def join(self):
            return None

    monkeypatch.setattr(engine, "DataSourceManager", type("FakeMgr", (), {}))
    monkeypatch.setattr(engine.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(engine, "_fetch_with_retry", fake_fetch_with_retry)
    monkeypatch.setattr(engine, "fetch_market_index_daily", lambda symbol=None: [])
    monkeypatch.setattr(engine, "passes_liquidity_filter", lambda data, cfg: True)
    monkeypatch.setattr(stock_pool, "get_a_stock_pool", lambda config: [{"code": "600000", "name": "Test"}])

    class FakeEngine:
        def __init__(self, config): pass
        def evaluate_at(self, data, code="", name="", market_data=None):
            r = type("R", (), {"found": False, "score": 0, "pattern_kind": "none"})()
            return type("Eval", (), {"passed": False, "result": r, "dry_stable": None})()

    monkeypatch.setattr(engine, "CupHandleStrategyEngine", FakeEngine)

    config = {
        "data": {"database_path": str(db_path), "scan_window_days": 200},
        "liquidity": {"enabled": False, "min_listing_days": 350},
        "scoring": {"medium_threshold": 70},
        "cup": {"max_duration": 60},
        "handle": {"max_duration": 20},
        "breakout": {},
    }

    engine.scan_all(config, worker_count=1)

    # Fetch must use min_listing_days=350, not scan_window_days=200
    assert fetch_kline_days == [350]


def _analyze_config(tmp_path):
    from scanner import db as db_mod
    db_path = tmp_path / "cuphandle.db"
    db_mod.init_db(str(db_path))
    config_path = tmp_path / "config.yaml"
    import yaml
    cfg = {
        "data": {"database_path": str(db_path), "scan_window_days": 200},
        "liquidity": {"min_listing_days": 351},
        "market_environment": {"index_symbol": "000001"},
        "output": {"log_dir": str(tmp_path / "logs"), "output_dir": str(tmp_path / "output")},
    }
    (tmp_path / "logs").mkdir(exist_ok=True)
    (tmp_path / "output").mkdir(exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f)
    return config_path


def test_cmd_analyze_sina_success_passes_min_listing_days(monkeypatch, tmp_path):
    """FINAL-002-1: Sina succeeds → only sina called with min_listing_days."""
    import main
    from scanner import sina_source, tencent_source, index_source

    config_path = _analyze_config(tmp_path)
    fetch_args = []

    monkeypatch.setattr(sina_source, "fetch_sina_daily",
                        lambda code, days=None: (fetch_args.append(("sina", days)), _make_ohlc_window(days))[-1])
    monkeypatch.setattr(tencent_source, "fetch_tencent_daily",
                        lambda code, days=None: (fetch_args.append(("tencent", days)), None)[-1])
    monkeypatch.setattr(index_source, "fetch_market_index_daily", lambda symbol=None: [])

    class Args:
        config = str(config_path)
        stock = "600000"

    main.cmd_analyze(Args())
    assert ("sina", 351) in fetch_args


def test_cmd_analyze_sina_fails_tencent_succeeds(monkeypatch, tmp_path):
    """FINAL-002-2: Sina fails → tencent called with same min_listing_days."""
    import main
    from scanner import sina_source, tencent_source, index_source

    config_path = _analyze_config(tmp_path)
    fetch_args = []

    monkeypatch.setattr(sina_source, "fetch_sina_daily",
                        lambda code, days=None: (fetch_args.append(("sina", days)), None)[-1])
    monkeypatch.setattr(tencent_source, "fetch_tencent_daily",
                        lambda code, days=None: (fetch_args.append(("tencent", days)), _make_ohlc_window(days))[-1])
    monkeypatch.setattr(index_source, "fetch_market_index_daily", lambda symbol=None: [])

    class Args:
        config = str(config_path)
        stock = "600000"

    main.cmd_analyze(Args())
    assert ("sina", 351) in fetch_args
    assert ("tencent", 351) in fetch_args


def test_cmd_analyze_both_sources_fail_returns_cleanly(monkeypatch, tmp_path, caplog):
    """FINAL-002-3: Both sources fail → clean exit with error log, no TypeError."""
    import main
    from scanner import sina_source, tencent_source, index_source

    config_path = _analyze_config(tmp_path)

    monkeypatch.setattr(sina_source, "fetch_sina_daily", lambda code, days=None: None)
    monkeypatch.setattr(tencent_source, "fetch_tencent_daily", lambda code, days=None: None)
    monkeypatch.setattr(index_source, "fetch_market_index_daily", lambda symbol=None: [])

    class Args:
        config = str(config_path)
        stock = "600000"

    # Must not raise TypeError / UnboundLocalError
    main.cmd_analyze(Args())
    assert "Cannot fetch data" in caplog.text

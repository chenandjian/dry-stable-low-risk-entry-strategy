from datetime import date, timedelta

from scanner.strategy1_backtest_models import (
    Strategy1BacktestOpportunity,
    Strategy1BacktestSignal,
)


def _ohlc(count=30, start=10.0):
    rows = []
    first_day = date(2025, 1, 1)
    for i in range(count):
        price = start + i * 0.1
        rows.append({
            "date": (first_day + timedelta(days=i)).isoformat(),
            "open": round(price, 2),
            "high": round(price + 0.4, 2),
            "low": round(price - 0.4, 2),
            "close": round(price + 0.1, 2),
            "volume": 1_000_000 + i,
            "turnover": (1_000_000 + i) * price,
        })
    return rows


def test_calculate_strategy1_execution_outcome_next_open_enters_next_day():
    from scanner.strategy1_backtester import calculate_strategy1_execution_outcome

    data = _ohlc(8)
    opp = Strategy1BacktestOpportunity(
        first_detected_date="2025-01-03",
        stop_loss=9.0,
    )
    date_to_index = {row["date"]: idx for idx, row in enumerate(data)}

    calculate_strategy1_execution_outcome(opp, data, date_to_index)

    assert opp.entry_date == "2025-01-04"
    assert opp.entry_price == data[3]["open"]
    assert opp.exit_reason in {"TARGET", "STOP", "UNRESOLVED"}
    assert opp.available_forward_days == 5


def test_calculate_strategy1_execution_outcome_adds_short_term_quality_tag():
    from scanner.strategy1_backtester import calculate_strategy1_execution_outcome

    data = _ohlc(8)
    opp = Strategy1BacktestOpportunity(
        first_detected_date="2025-01-03",
        stop_loss=9.0,
        quality_tags=["PRICE_STABLE_STRONG"],
        quality_layer="strong",
    )
    date_to_index = {row["date"]: idx for idx, row in enumerate(data)}

    calculate_strategy1_execution_outcome(opp, data, date_to_index)

    assert "SHORT_TERM_RISK_CONTROL" in opp.quality_tags
    assert opp.short_term_exit_note


def test_strategy1_quality_tags_classify_price_stability_and_breakout():
    from scanner.strategy1_quality import build_strategy1_quality_layer, build_strategy1_quality_tags

    tags = build_strategy1_quality_tags(
        price_stable_score=8,
        verdict_key="WATCH_BREAKOUT",
        has_short_term_diagnostic=True,
    )

    assert tags == ["PRICE_STABLE_EXTREME", "BREAKOUT_OBSERVE", "SHORT_TERM_RISK_CONTROL"]
    assert build_strategy1_quality_layer(tags) == "premium"


def test_calculate_strategy1_execution_outcome_blocks_gap_below_stop():
    from scanner.strategy1_backtester import calculate_strategy1_execution_outcome

    data = _ohlc(5)
    data[3]["open"] = 8.5
    opp = Strategy1BacktestOpportunity(first_detected_date="2025-01-03", stop_loss=9.0)
    date_to_index = {row["date"]: idx for idx, row in enumerate(data)}

    calculate_strategy1_execution_outcome(opp, data, date_to_index)

    assert opp.exit_reason == "NO_ENTRY_GAP_BELOW_STOP"
    assert opp.entry_date == ""


def test_calculate_horizon_performance_uses_entry_price_and_short_horizons():
    from scanner.strategy1_backtester import calculate_horizon_performance

    future = [
        {"date": "2025-01-02", "high": 10.2, "low": 9.8, "close": 10.1},
        {"date": "2025-01-03", "high": 10.8, "low": 9.9, "close": 10.7},
        {"date": "2025-01-04", "high": 10.9, "low": 10.0, "close": 10.8},
    ]

    hp = calculate_horizon_performance(future, entry_price=10.0, stop_loss=9.0, horizon_days=3)

    assert hp.result == "TARGET"
    assert hp.days_to_target == 2
    assert hp.end_return == 0.08


def test_calculate_horizon_performance_unobserved_when_future_short():
    from scanner.strategy1_backtester import calculate_horizon_performance

    hp = calculate_horizon_performance(_ohlc(2), entry_price=10.0, stop_loss=9.0, horizon_days=3)

    assert hp.result == "UNOBSERVED"
    assert hp.end_return is None


def test_merge_strategy1_signals_splits_after_ten_counted_misses():
    from scanner.strategy1_backtester import merge_strategy1_signals

    signals = [
        Strategy1BacktestSignal(code="600000", evaluation_date="2025-01-01", evaluation_index=1, score=70, pattern_kind="cup_handle"),
        Strategy1BacktestSignal(code="600000", evaluation_date="2025-01-15", evaluation_index=14, score=80, pattern_kind="cup_handle"),
    ]
    eval_results = {idx: "SCORE_BELOW_THRESHOLD" for idx in range(2, 14)}

    opportunities = merge_strategy1_signals(signals, eval_results)

    assert len(opportunities) == 2
    assert opportunities[0].first_detected_date == "2025-01-01"
    assert opportunities[1].first_detected_date == "2025-01-15"


def test_merge_strategy1_signals_carries_first_signal_quality_fields():
    from scanner.strategy1_backtester import merge_strategy1_signals

    signals = [
        Strategy1BacktestSignal(
            code="600000",
            evaluation_date="2025-01-01",
            evaluation_index=1,
            score=70,
            pattern_kind="cup_handle",
            volume_dry_score=8,
            price_stable_score=7,
            verdict_key="WATCH_BREAKOUT",
        )
    ]

    opportunities = merge_strategy1_signals(signals, {1: "PASSED"})

    assert opportunities[0].price_stable_score == 7
    assert opportunities[0].volume_dry_score == 8
    assert opportunities[0].verdict_key == "WATCH_BREAKOUT"
    assert "PRICE_STABLE_STRONG" in opportunities[0].quality_tags
    assert "BREAKOUT_OBSERVE" in opportunities[0].quality_tags


def test_merge_strategy1_signals_keeps_close_hits_in_one_opportunity():
    from scanner.strategy1_backtester import merge_strategy1_signals

    signals = [
        Strategy1BacktestSignal(code="600000", evaluation_date="2025-01-01", evaluation_index=1, score=70, pattern_kind="cup_handle"),
        Strategy1BacktestSignal(code="600000", evaluation_date="2025-01-05", evaluation_index=5, score=80, pattern_kind="cup_handle"),
    ]
    eval_results = {idx: "SCORE_BELOW_THRESHOLD" for idx in range(2, 5)}

    opportunities = merge_strategy1_signals(signals, eval_results)

    assert len(opportunities) == 1
    assert opportunities[0].signal_count == 2
    assert opportunities[0].max_score == 80


def test_apply_strategy1_time_exit_replaces_later_target():
    from scanner.strategy1_backtester import apply_strategy1_time_exit

    data = _ohlc(10)
    opp = Strategy1BacktestOpportunity(
        entry_date="2025-01-02",
        entry_price=10.0,
        exit_reason="TARGET",
        exit_date="2025-01-08",
        exit_price=10.5,
        holding_days=7,
    )
    date_to_index = {row["date"]: idx for idx, row in enumerate(data)}

    changed = apply_strategy1_time_exit(opp, data, date_to_index, {"enabled": True, "time_exit_days": 3})

    assert changed is True
    assert opp.exit_reason == "TIME_EXIT"
    assert opp.exit_date == "2025-01-04"
    assert opp.holding_days == 3


def test_run_strategy1_stock_backtest_uses_engine_and_disabled_experiment_equivalent(monkeypatch):
    import scanner.strategy1_backtester as backtester

    data = _ohlc(40)
    calls = []

    class FakeEngine:
        strategy_version = "fake-v1"

        def __init__(self, config):
            self.config_hash = "hash"

        def evaluate_at(self, window, code="", name="", market_data=None):
            calls.append((window[-1]["date"], code, name, list(market_data or [])))
            result = type("Result", (), {
                "pattern_kind": "cup_handle",
                "score": 75,
                "cup_depth_pct": 0.2,
                "cup_duration": 60,
                "handle_depth_pct": 0.1,
                "handle_duration": 8,
                "lip_deviation_pct": 0.03,
                "is_breakout": False,
                "is_volume_breakout": False,
                "breakout_price": 11.0,
            })()
            dry = {
                "volume_dry": {"score": 8},
                "price_stable": {"score": 7},
                "pattern_score": {"score": 14, "key_pattern_type": "cup_handle"},
                "decision": {"verdict_key": "BUY_LOW"},
                "risk_reward": {"risk_percent": 5.0, "rr1": 2.0},
                "key_prices": {"entry_zone_low": 10.0, "entry_zone_high": 12.0, "stop_loss": 9.0, "target_1": 12.0, "target_2": 13.0},
            }
            return type("Eval", (), {
                "passed": True,
                "result": result,
                "dry_stable": dry,
                "strategy_version": "fake-v1",
                "config_hash": "hash",
                "to_dict": lambda self: {"passed": True, "score": 75},
            })()

    monkeypatch.setattr(backtester, "CupHandleStrategyEngine", FakeEngine)
    config = {"data": {"scan_window_days": 30, "backtest_window_days": 30}, "liquidity": {"min_listing_days": 30}}

    baseline = backtester.run_strategy1_stock_backtest(
        "600000", "Test", data, config, "2025-01-30", "2025-02-03", experiment={"enabled": False},
    )
    missing = backtester.run_strategy1_stock_backtest(
        "600000", "Test", data, config, "2025-01-30", "2025-02-03", experiment=None,
    )

    assert baseline["raw_signals_count"] == missing["raw_signals_count"]
    assert baseline["opportunities_count"] == missing["opportunities_count"]
    assert baseline["signals"][0].evaluation_date == "2025-01-30"
    assert calls


def test_run_strategy1_stock_backtest_uses_backtest_window_not_min_listing_days(monkeypatch):
    import scanner.strategy1_backtester as backtester

    data = _ohlc(40)
    calls = []

    class FakeEngine:
        strategy_version = "fake-v1"

        def __init__(self, config):
            self.config_hash = "hash"

        def evaluate_at(self, window, code="", name="", market_data=None):
            calls.append(window[-1]["date"])
            return type("Eval", (), {
                "passed": False,
                "result": type("Result", (), {})(),
                "dry_stable": {},
                "strategy_version": "fake-v1",
                "config_hash": "hash",
                "to_dict": lambda self: {"passed": False},
            })()

    monkeypatch.setattr(backtester, "CupHandleStrategyEngine", FakeEngine)
    config = {
        "data": {"scan_window_days": 30, "backtest_window_days": 30},
        "liquidity": {"min_listing_days": 35},
    }

    result = backtester.run_strategy1_stock_backtest(
        "600000", "Test", data, config, "2025-01-30", "2025-02-03",
    )

    assert result["raw_signals_count"] == 0
    assert calls == ["2025-01-30", "2025-01-31", "2025-02-01", "2025-02-02", "2025-02-03"]
    assert "INSUFFICIENT_LISTING_DAYS" not in result["eval_results"].values()

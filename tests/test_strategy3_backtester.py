"""策略3本地 DB 回测核心计算测试。"""
from strategy3.backtest_models import Strategy3BacktestOpportunity, Strategy3BacktestSignal
from strategy3.backtester import (
    calculate_strategy3_execution_outcome,
    merge_strategy3_signals,
    run_strategy3_stock_backtest,
)
from strategy3.models import (
    Strategy3Evaluation,
    Strategy3Indicators,
    Strategy3Risk,
    Strategy3TradeQuality,
)


def _row(date, open_=10.0, high=10.2, low=9.8, close=10.0, volume=1_000_000):
    return {
        "date": date,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "turnover": close * volume,
    }


def _passed_eval(code="000001", name="样本", evaluation_date="2026-01-05"):
    return Strategy3Evaluation(
        passed=True,
        code=code,
        name=name,
        evaluation_date=evaluation_date,
        total_score=88,
        level="核心候选",
        current_close=10.0,
        trend_score=22,
        pullback_score=21,
        volume_stability_score=18,
        second_breakout_score=13,
        risk_reward_score=14,
        indicators=Strategy3Indicators(
            current_close=10.0,
            pullback_pct=0.15,
            volume_ratio_5_20=0.55,
            market_return_60=0.03,
            has_market_data=True,
        ),
        risk=Strategy3Risk(
            support_price=9.7,
            stop_loss=9.5,
            target_1=11.5,
            risk_ratio=0.05,
            rr1=3.0,
            tactical_support=9.7,
            tactical_stop_loss=9.5,
            tactical_risk_ratio=0.05,
            tactical_rr1=3.0,
        ),
        trade_quality=Strategy3TradeQuality(
            trade_quality_score=82,
            volume_dry_score=17,
            price_stability_score=16,
            cannot_fall_score=15,
            balance_powerless_score=13,
            support_distance_pct=0.03,
            target_price=11.5,
            target_room_pct=0.15,
            estimated_rr=3.0,
            trade_state="LOW_ABSORB",
            trade_state_label="低吸",
            trigger_reasons=["volume:strong_dry"],
            risk_warnings=[],
            invalid_conditions=[],
        ),
        score_reasons=["trend:close>=ma60"],
        reject_reasons=[],
    )


def test_strategy3_next_open_entry_uses_next_trading_day_open():
    opp = Strategy3BacktestOpportunity(
        code="000001",
        first_detected_date="2026-01-02",
        stop_loss=9.5,
        target_price=11.0,
    )
    rows = [
        _row("2026-01-02", open_=10.0, high=10.2, low=9.9, close=10.0),
        _row("2026-01-05", open_=10.1, high=10.5, low=10.0, close=10.3),
    ]

    calculate_strategy3_execution_outcome(opp, rows, {"2026-01-02": 0, "2026-01-05": 1})

    assert opp.execution_model == "NEXT_OPEN"
    assert opp.entry_date == "2026-01-05"
    assert opp.entry_price == 10.1


def test_strategy3_same_day_target_and_stop_uses_stop_first():
    opp = Strategy3BacktestOpportunity(
        code="000001",
        first_detected_date="2026-01-02",
        stop_loss=9.5,
        target_price=10.8,
    )
    rows = [
        _row("2026-01-02", close=10.0),
        _row("2026-01-05", open_=10.0, high=10.9, low=9.4, close=10.2),
    ]

    calculate_strategy3_execution_outcome(opp, rows, {"2026-01-02": 0, "2026-01-05": 1})

    assert opp.exit_reason == "STOP"
    assert opp.exit_price == 9.5
    assert opp.realized_return < 0


def test_strategy3_no_entry_gap_below_stop():
    opp = Strategy3BacktestOpportunity(
        code="000001",
        first_detected_date="2026-01-02",
        stop_loss=9.5,
        target_price=11.0,
    )
    rows = [
        _row("2026-01-02", close=10.0),
        _row("2026-01-05", open_=9.4, high=9.6, low=9.2, close=9.3),
    ]

    calculate_strategy3_execution_outcome(opp, rows, {"2026-01-02": 0, "2026-01-05": 1})

    assert opp.entry_price == 0
    assert opp.exit_reason == "NO_ENTRY_GAP_BELOW_STOP"


def test_strategy3_no_entry_gap_too_high():
    opp = Strategy3BacktestOpportunity(
        code="000001",
        first_detected_date="2026-01-02",
        stop_loss=9.5,
        target_price=11.0,
    )
    rows = [
        _row("2026-01-02", close=10.0),
        _row("2026-01-05", open_=11.05, high=11.2, low=10.9, close=11.1),
    ]

    calculate_strategy3_execution_outcome(opp, rows, {"2026-01-02": 0, "2026-01-05": 1})

    assert opp.entry_price == 0
    assert opp.exit_reason == "NO_ENTRY_GAP_TOO_HIGH"


def _sig(date, idx, code="000001", score=80):
    return Strategy3BacktestSignal(
        code=code,
        name="样本",
        evaluation_date=date,
        evaluation_index=idx,
        total_score=score,
        current_close=10.0,
        stop_loss=9.5,
        target_price=11.0,
        risk_ratio=0.05,
        rr1=2.0,
    )


def test_strategy3_merge_9_counted_missed_days_same_opportunity():
    hits = [_sig("2026-01-02", 10), _sig("2026-01-15", 20)]
    eval_results = {10: "PASSED", 20: "PASSED"}
    for idx in range(11, 20):
        eval_results[idx] = "SCORE_BELOW_THRESHOLD"

    opportunities = merge_strategy3_signals(hits, eval_results)

    assert len(opportunities) == 1
    assert opportunities[0].signal_count == 2


def test_strategy3_merge_10_counted_missed_days_new_opportunity():
    hits = [_sig("2026-01-02", 10), _sig("2026-01-16", 21)]
    eval_results = {10: "PASSED", 21: "PASSED"}
    for idx in range(11, 21):
        eval_results[idx] = "SCORE_BELOW_THRESHOLD"

    opportunities = merge_strategy3_signals(hits, eval_results)

    assert len(opportunities) == 2


def test_strategy3_merge_ignores_insufficient_data_for_cooldown():
    hits = [_sig("2026-01-02", 10), _sig("2026-01-16", 21)]
    eval_results = {10: "PASSED", 21: "PASSED"}
    for idx in range(11, 16):
        eval_results[idx] = "SCORE_BELOW_THRESHOLD"
    for idx in range(16, 21):
        eval_results[idx] = "INSUFFICIENT_DATA"

    opportunities = merge_strategy3_signals(hits, eval_results)

    assert len(opportunities) == 1


def test_strategy3_stock_backtest_does_not_pass_future_rows_to_engine():
    rows = [_row(f"2026-01-0{i}", close=10.0 + i * 0.1) for i in range(1, 8)]
    market_rows = [_row(f"2026-01-0{i}", close=100.0 + i) for i in range(1, 8)]
    seen_windows = []
    seen_market_windows = []

    class FakeEngine:
        def __init__(self, config):
            pass

        def evaluate_at(self, history, *, code="", name="", market_data=None):
            seen_windows.append([row["date"] for row in history])
            seen_market_windows.append([row["date"] for row in market_data or []])
            return _passed_eval(code=code, name=name, evaluation_date=history[-1]["date"])

    result = run_strategy3_stock_backtest(
        "000001",
        "样本",
        rows,
        {
            "strategy3": {"minimum_required_days": 3, "strategy_window_days": 4},
            "liquidity": {"enabled": False, "min_listing_days": 4},
        },
        "2026-01-03",
        "2026-01-05",
        engine_factory=FakeEngine,
        market_data=market_rows,
    )

    assert seen_windows
    assert all(window[-1] <= "2026-01-05" for window in seen_windows)
    assert all("2026-01-06" not in window and "2026-01-07" not in window for window in seen_windows)
    assert seen_market_windows
    assert all(window[-1] <= "2026-01-05" for window in seen_market_windows)
    assert all("2026-01-06" not in window and "2026-01-07" not in window for window in seen_market_windows)
    assert result["raw_signals_count"] == 3


def test_strategy3_stock_backtest_records_signal_snapshot_and_execution():
    rows = [
        _row("2026-01-01", close=9.8),
        _row("2026-01-02", close=9.9),
        _row("2026-01-03", close=10.0),
        _row("2026-01-04", close=10.1),
        _row("2026-01-05", open_=10.2, high=11.6, low=10.0, close=11.0),
    ]

    class FakeEngine:
        def __init__(self, config):
            pass

        def evaluate_at(self, history, *, code="", name="", market_data=None):
            if history[-1]["date"] == "2026-01-04":
                return _passed_eval(code=code, name=name, evaluation_date="2026-01-04")
            return Strategy3Evaluation(
                passed=False,
                code=code,
                name=name,
                evaluation_date=history[-1]["date"],
                status_reason="SCORE_BELOW_THRESHOLD",
            )

    result = run_strategy3_stock_backtest(
        "000001",
        "样本",
        rows,
        {
            "strategy3": {"minimum_required_days": 3, "strategy_window_days": 4},
            "liquidity": {"enabled": False, "min_listing_days": 4},
        },
        "2026-01-03",
        "2026-01-04",
        engine_factory=FakeEngine,
    )

    assert result["raw_signals_count"] == 1
    signal = result["signals"][0]
    assert signal.total_score == 88
    assert signal.trade_state == "LOW_ABSORB"
    assert signal.trade_quality_score == 82
    assert signal.evaluation_snapshot["trade_state"] == "LOW_ABSORB"
    assert signal.evaluation_snapshot["market_return_60"] == 0.03
    assert signal.evaluation_snapshot["has_market_data"] is True
    opp = result["opportunities"][0]
    assert opp["entry_date"] == "2026-01-05"
    assert opp["entry_price"] == 10.2
    assert opp["exit_reason"] == "TARGET"

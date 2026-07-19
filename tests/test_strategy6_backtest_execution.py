from strategy6.backtest.config import resolve_backtest_config
from strategy6.backtest.execution import calculate_transaction_costs, simulate_frozen_trade
from strategy6.backtest.models import BacktestSignal


def _signal(**overrides):
    snapshot = {
        "buy_zone_low": 9.8,
        "buy_zone_high": 10.2,
        "suggested_limit_price": 10.0,
        "stop_loss_price": 9.5,
        "objective_target_2": 11.5,
        "key_support_price": 9.6,
        "tail_path": "BOX",
        "candidate_type": "KEY_CANDIDATE",
    }
    snapshot.update(overrides)
    return BacktestSignal(
        parameter_set_id="s6ps-a", code="000001", name="样本",
        evaluation_date="2025-01-02", setup_id="setup-1", tail_path="BOX",
        candidate_type="KEY_CANDIDATE", snapshot=snapshot,
    )


def _row(date, open_price, high, low, close, volume=1000):
    return {"date": date, "open": open_price, "high": high, "low": low, "close": close, "volume": volume}


def test_next_day_open_in_zone_fills_and_t_plus_one_blocks_same_day_stop():
    rows = [
        _row("2025-01-02", 10, 10.1, 9.9, 10),
        _row("2025-01-03", 10, 10.3, 9.4, 10.1),
        _row("2025-01-06", 9.4, 9.6, 9.2, 9.3),
    ]
    outcome = simulate_frozen_trade(
        _signal(), rows, ["2025-01-02", "2025-01-03", "2025-01-06"], resolve_backtest_config({})
    )
    assert outcome.order.status == "FILLED"
    assert outcome.trade.entry_date == "2025-01-03"
    assert outcome.trade.intraday_stop_breach is True
    assert outcome.trade.exit_date == "2025-01-06"
    assert outcome.trade.exit_reason == "STOP_GAP"


def test_missing_bar_and_zero_volume_do_not_create_fake_fill():
    rows = [
        _row("2025-01-02", 10, 10.1, 9.9, 10),
        _row("2025-01-06", 10, 10.1, 9.9, 10, volume=0),
    ]
    outcome = simulate_frozen_trade(
        _signal(), rows,
        ["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07"],
        resolve_backtest_config({}),
    )
    assert outcome.trade is None
    assert outcome.order.status == "EXPIRED_NO_FILL"
    assert "UNKNOWN_NO_BAR" in outcome.audit_tags
    assert "ZERO_VOLUME" in outcome.audit_tags


def test_open_outside_buy_zone_cancels_conservatively():
    high_open = simulate_frozen_trade(
        _signal(), [_row("2025-01-02", 10, 10, 10, 10), _row("2025-01-03", 10.5, 10.6, 10.4, 10.5)],
        ["2025-01-02", "2025-01-03"], resolve_backtest_config({}),
    )
    low_open = simulate_frozen_trade(
        _signal(), [_row("2025-01-02", 10, 10, 10, 10), _row("2025-01-03", 9.7, 10.1, 9.6, 10)],
        ["2025-01-02", "2025-01-03"], resolve_backtest_config({}),
    )
    assert high_open.order.fill_reason == "CANCEL_OPEN_ABOVE_BUY_ZONE"
    assert low_open.order.fill_reason == "CANCEL_OPEN_BELOW_BUY_ZONE"


def test_same_day_stop_and_target_after_entry_uses_stop_first():
    rows = [
        _row("2025-01-02", 10, 10, 10, 10),
        _row("2025-01-03", 10, 10.2, 9.8, 10),
        _row("2025-01-06", 10.2, 11.6, 9.4, 10.5),
    ]
    outcome = simulate_frozen_trade(
        _signal(), rows, [row["date"] for row in rows], resolve_backtest_config({})
    )
    assert outcome.trade.exit_reason == "STOP"
    assert outcome.trade.exit_price < 9.5


def test_one_word_limit_down_defers_stop_until_first_sellable_day():
    rows = [
        _row("2025-01-02", 10, 10, 10, 10),
        _row("2025-01-03", 10, 10.2, 9.8, 10),
        _row("2025-01-06", 9.0, 9.0, 9.0, 9.0),
        _row("2025-01-07", 8.8, 9.0, 8.7, 8.9),
    ]
    outcome = simulate_frozen_trade(
        _signal(), rows, [row["date"] for row in rows], resolve_backtest_config({})
    )
    assert "ONE_WORD_LIMIT_DOWN_EXIT_DELAY" in outcome.audit_tags
    assert outcome.trade.exit_date == "2025-01-07"
    assert outcome.trade.exit_reason == "STOP_GAP"


def test_transaction_costs_include_minimum_commission_tax_transfer_and_slippage():
    costs = calculate_transaction_costs(
        entry_price=10.0, exit_price=11.0, shares=100,
        costs=resolve_backtest_config({})["costs"],
    )
    assert costs["buy_commission"] == 5.0
    assert costs["sell_commission"] == 5.0
    assert costs["sell_tax"] == 0.55
    assert costs["total"] > 10.55


def test_one_day_entry_delay_starts_buy_window_on_second_market_day():
    rows = [
        _row("2025-01-02", 10, 10, 10, 10),
        _row("2025-01-03", 10.5, 10.6, 10.4, 10.5),
        _row("2025-01-06", 10.0, 10.2, 9.8, 10.0),
        _row("2025-01-07", 11.6, 11.7, 11.4, 11.6),
    ]
    config = resolve_backtest_config({"execution": {"entry_delay_days": 1}})
    outcome = simulate_frozen_trade(_signal(), rows, [row["date"] for row in rows], config)
    assert outcome.order.status == "FILLED"
    assert outcome.trade.entry_date == "2025-01-06"


def test_zero_fill_multiplier_rejects_fill_deterministically():
    rows = [
        _row("2025-01-02", 10, 10, 10, 10),
        _row("2025-01-03", 10, 10.2, 9.8, 10),
    ]
    config = resolve_backtest_config({"execution": {"fill_rate_multiplier": 0.0}})
    outcome = simulate_frozen_trade(_signal(), rows, [row["date"] for row in rows], config)
    assert outcome.order.status == "EXPIRED_NO_FILL"
    assert outcome.order.fill_reason == "STRESS_FILL_RATE_REJECTED"


def test_truncated_calendar_does_not_fake_max_holding_exit_before_holding_period():
    rows = [
        _row("2024-12-18", 10, 10, 10, 10),
        _row("2024-12-19", 10, 10.2, 9.8, 10),
        _row("2024-12-20", 10.1, 10.3, 9.9, 10.1),
        _row("2024-12-31", 10.2, 10.4, 10.0, 10.2),
    ]
    signal = _signal()
    signal.evaluation_date = "2024-12-18"
    outcome = simulate_frozen_trade(
        signal, rows, [row["date"] for row in rows], resolve_backtest_config({}),
    )

    assert outcome.trade.exit_date == ""
    assert outcome.trade.exit_reason == "UNRESOLVED_NO_EXIT_BAR"

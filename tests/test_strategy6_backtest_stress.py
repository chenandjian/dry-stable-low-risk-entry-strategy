from strategy6.backtest.config import resolve_backtest_config
from strategy6.backtest.stress import (
    build_stress_scenarios,
    replay_frozen_signals,
    replay_stress_scenarios,
)
from strategy6.backtest.models import BacktestSignal


def test_stress_scenarios_are_explicit_and_do_not_mutate_base_config():
    base = resolve_backtest_config({})
    original_buy_slippage = base["costs"]["buy_slippage_bps"]
    scenarios = build_stress_scenarios(base)
    assert {item["name"] for item in scenarios} == {"BASE", "HIGH_COST", "LOW_FILL", "ONE_DAY_DELAY"}
    high_cost = next(item for item in scenarios if item["name"] == "HIGH_COST")
    assert high_cost["config"]["costs"]["buy_slippage_bps"] == 30
    delay = next(item for item in scenarios if item["name"] == "ONE_DAY_DELAY")
    assert delay["config"]["execution"]["entry_delay_days"] == 1
    assert base["costs"]["buy_slippage_bps"] == original_buy_slippage


def test_stress_replay_returns_metrics_for_executable_scenarios():
    signal = BacktestSignal(
        parameter_set_id="p", code="000001", name="样本", evaluation_date="2025-01-02",
        setup_id="setup", tail_path="BOX", candidate_type="KEY_CANDIDATE",
        snapshot={"buy_zone_low": 9.8, "buy_zone_high": 10.2, "suggested_limit_price": 10,
                  "stop_loss_price": 9.5, "objective_target_2": 11.5},
    )
    rows = [
        {"date": "2025-01-02", "open": 10, "high": 10, "low": 10, "close": 10, "volume": 1000},
        {"date": "2025-01-03", "open": 10, "high": 10.2, "low": 9.8, "close": 10, "volume": 1000},
        {"date": "2025-01-06", "open": 11.5, "high": 11.6, "low": 11.4, "close": 11.5, "volume": 1000},
    ]
    result = replay_stress_scenarios(
        [signal], load_rows=lambda code: rows,
        market_dates=[row["date"] for row in rows], base_config=resolve_backtest_config({}),
    )
    assert set(result) >= {"BASE", "HIGH_COST", "LOW_FILL", "ONE_DAY_DELAY"}
    assert result["BASE"]["orders"] == 1
    assert result["HIGH_COST"]["metrics"]["trades"] == 1


def test_frozen_replays_do_not_let_brooks_watch_consume_later_ready_setup():
    common = {
        "tail_path": "NONE",
        "tail_paths": ["BROOKS"],
        "brooks_tail_pass": True,
    }
    watch = BacktestSignal(
        parameter_set_id="p", code="000001", name="样本", evaluation_date="2025-01-02",
        setup_id="same-setup", tail_path="NONE", candidate_type="WATCH_CANDIDATE",
        snapshot={**common, "brooks_trade_ready": False, "brooks_status": "SECOND_ENTRY_LONG_READY"},
    )
    ready = BacktestSignal(
        parameter_set_id="p", code="000001", name="样本", evaluation_date="2025-01-03",
        setup_id="same-setup", tail_path="NONE", candidate_type="KEY_CANDIDATE",
        snapshot={
            **common,
            "brooks_trade_ready": True,
            "brooks_status": "BROOKS_SUPPORT_READY",
            "buy_zone_low": 9.8,
            "buy_zone_high": 10.2,
            "suggested_limit_price": 10.0,
            "stop_loss_price": 9.5,
            "objective_target_2": 11.5,
        },
    )
    rows = [
        {"date": "2025-01-02", "open": 10, "high": 10.2, "low": 9.8, "close": 10, "volume": 1000},
        {"date": "2025-01-03", "open": 10, "high": 10.2, "low": 9.8, "close": 10, "volume": 1000},
        {"date": "2025-01-06", "open": 10, "high": 10.2, "low": 9.8, "close": 10, "volume": 1000},
        {"date": "2025-01-07", "open": 10, "high": 11.6, "low": 9.9, "close": 11.5, "volume": 1000},
    ]
    market_dates = [row["date"] for row in rows]
    config = resolve_backtest_config({})

    replay = replay_frozen_signals(
        [watch, ready], load_rows=lambda code: rows, market_dates=market_dates, config=config,
    )
    stress = replay_stress_scenarios(
        [watch, ready], load_rows=lambda code: rows, market_dates=market_dates, base_config=config,
    )

    assert replay["orders"] == 1
    assert replay["setup_ids"] == ["same-setup"]
    assert replay["trades"][0]["signal_date"] == "2025-01-03"
    assert stress["BASE"]["orders"] == 1
    assert stress["BASE"]["metrics"]["trades"] == 1

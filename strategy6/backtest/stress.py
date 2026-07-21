"""Explicit conservative stress scenarios."""
from __future__ import annotations

import copy
from dataclasses import asdict

from strategy6.backtest.execution import simulate_frozen_trade
from strategy6.backtest.metrics import calculate_trade_metrics
from strategy6.backtest.snapshot import is_trade_ready_snapshot


MIN_STRESS_CLOSED_TRADE_RETENTION = 0.50


def build_execution_tuning_configs(base_config: dict) -> list[dict]:
    result = []
    for buy_days in (1, 2, 3, 5):
        for hold_days in (10, 15, 20, 30):
            config = copy.deepcopy(base_config)
            config["execution"]["buy_zone_valid_days"] = buy_days
            config["execution"]["max_holding_days"] = hold_days
            validate_replay_config(config, base_config)
            result.append({
                "buy_zone_valid_days": buy_days,
                "max_holding_days": hold_days,
                "config": config,
            })
    return result


def validate_replay_config(config: dict, base_config: dict) -> None:
    for key, baseline in base_config["costs"].items():
        if float(config["costs"].get(key, float("-inf"))) < float(baseline):
            raise ValueError(f"execution replay cost {key} cannot be lower than BASE")
    execution = config["execution"]
    baseline_execution = base_config["execution"]
    if execution.get("use_t_plus_one") is not True:
        raise ValueError("T+1 execution semantics cannot be disabled")
    if execution.get("same_day_stop_target") != "STOP_FIRST":
        raise ValueError("same-day stop/target semantics must remain STOP_FIRST")
    for key in ("entry_mode", "below_buy_zone_open_mode", "intraday_limit_fill_mode"):
        if execution.get(key) != baseline_execution.get(key):
            raise ValueError(f"execution semantic {key} cannot change during tuning")


def evaluate_stress_acceptance(results: dict) -> dict:
    base = results.get("BASE") or {}
    base_metrics = base.get("metrics") or {}
    base_closed_trades = int(base_metrics.get("trades") or 0)
    checks = {}
    retention = {}
    for name in ("HIGH_COST", "LOW_FILL", "ONE_DAY_DELAY"):
        scenario = results.get(name) or {}
        metrics = scenario.get("metrics") or {}
        expectancy = float(metrics.get("expectancy_r", 0))
        profit_factor = float(metrics.get("profit_factor", 0))
        closed_trades = int(metrics.get("trades") or 0)
        retention[name] = (
            closed_trades / base_closed_trades if base_closed_trades > 0 else 0.0
        )
        checks[name] = bool(
            base.get("status") == "COMPLETED"
            and base_closed_trades > 0
            and scenario.get("status") == "COMPLETED"
            and int(scenario.get("orders") or 0) > 0
            and closed_trades > 0
            and retention[name] >= MIN_STRESS_CLOSED_TRADE_RETENTION
            and not (expectancy < 0 and profit_factor < 1.0)
        )
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "closed_trade_retention": retention,
    }


def build_stress_scenarios(base_config: dict) -> list[dict]:
    scenarios = [{"name": "BASE", "config": copy.deepcopy(base_config)}]

    high_cost = copy.deepcopy(base_config)
    high_cost["costs"]["buy_slippage_bps"] = (
        float(base_config["costs"]["buy_slippage_bps"]) + 20.0
    )
    high_cost["costs"]["sell_slippage_bps"] = (
        float(base_config["costs"]["sell_slippage_bps"]) + 20.0
    )
    validate_replay_config(high_cost, base_config)
    scenarios.append({"name": "HIGH_COST", "config": high_cost})

    low_fill = copy.deepcopy(base_config)
    low_fill["execution"]["fill_rate_multiplier"] = (
        float(base_config["execution"].get("fill_rate_multiplier", 1.0)) * 0.70
    )
    validate_replay_config(low_fill, base_config)
    scenarios.append({"name": "LOW_FILL", "config": low_fill})

    delayed = copy.deepcopy(base_config)
    delayed["execution"]["entry_delay_days"] = (
        int(base_config["execution"].get("entry_delay_days", 0)) + 1
    )
    validate_replay_config(delayed, base_config)
    scenarios.append({"name": "ONE_DAY_DELAY", "config": delayed})

    return scenarios


def replay_stress_scenarios(signals, *, load_rows, market_dates: list[str], base_config: dict) -> dict:
    results = {}
    for scenario in build_stress_scenarios(base_config):
        name = scenario["name"]
        orders = 0
        trades = []
        seen: set[str] = set()
        for signal in sorted(signals, key=lambda item: (item.evaluation_date, item.code)):
            if not is_trade_ready_snapshot({"tail_path": signal.tail_path, **signal.snapshot}):
                continue
            if signal.setup_id in seen:
                continue
            seen.add(signal.setup_id)
            outcome = simulate_frozen_trade(signal, load_rows(signal.code), market_dates, scenario["config"])
            orders += 1
            if outcome.trade is None:
                continue
            trade = asdict(outcome.trade)
            trade["net_profit"] = trade["net_return"] * trade["entry_price"] * 100
            trades.append(trade)
        results[name] = {
            "status": "COMPLETED", "orders": orders,
            "unfilled_rate": (orders - len(trades)) / orders if orders else 0.0,
            "metrics": calculate_trade_metrics([item for item in trades if item.get("exit_date")]),
            "trades": trades,
        }
    return results


def replay_frozen_signals(signals, *, load_rows, market_dates: list[str], config: dict) -> dict:
    """Replay execution only; signal snapshots and setup identities remain frozen."""
    orders = 0
    trades = []
    setup_ids = []
    seen: set[str] = set()
    for signal in sorted(signals, key=lambda item: (item.evaluation_date, item.code)):
        if not is_trade_ready_snapshot({"tail_path": signal.tail_path, **signal.snapshot}):
            continue
        if signal.setup_id in seen:
            continue
        seen.add(signal.setup_id)
        setup_ids.append(signal.setup_id)
        outcome = simulate_frozen_trade(signal, load_rows(signal.code), market_dates, config)
        orders += 1
        if outcome.trade is None:
            continue
        trade = asdict(outcome.trade)
        trade["net_profit"] = trade["net_return"] * trade["entry_price"] * 100
        trades.append(trade)
    return {
        "orders": orders,
        "unfilled_rate": (orders - len(trades)) / orders if orders else 0.0,
        "trades": trades,
        "metrics": calculate_trade_metrics([item for item in trades if item.get("exit_date")]),
        "setup_ids": setup_ids,
    }

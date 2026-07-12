"""Explicit conservative stress scenarios."""
from __future__ import annotations

import copy
from dataclasses import asdict

from strategy6.backtest.execution import simulate_frozen_trade
from strategy6.backtest.metrics import calculate_trade_metrics


def build_stress_scenarios(base_config: dict) -> list[dict]:
    scenarios = [{"name": "BASE", "config": copy.deepcopy(base_config)}]

    high_cost = copy.deepcopy(base_config)
    high_cost["costs"]["buy_slippage_bps"] = 30.0
    high_cost["costs"]["sell_slippage_bps"] = 30.0
    scenarios.append({"name": "HIGH_COST", "config": high_cost})

    low_fill = copy.deepcopy(base_config)
    low_fill["execution"]["fill_rate_multiplier"] = 0.70
    scenarios.append({"name": "LOW_FILL", "config": low_fill})

    delayed = copy.deepcopy(base_config)
    delayed["execution"]["entry_delay_days"] = 1
    scenarios.append({"name": "ONE_DAY_DELAY", "config": delayed})

    perturbed = copy.deepcopy(base_config)
    perturbed["parameter_perturbation_pct"] = 0.05
    scenarios.append({"name": "PARAMETER_PERTURBATION", "config": perturbed})
    return scenarios


def replay_stress_scenarios(signals, *, load_rows, market_dates: list[str], base_config: dict) -> dict:
    results = {}
    for scenario in build_stress_scenarios(base_config):
        name = scenario["name"]
        if name == "PARAMETER_PERTURBATION":
            results[name] = {"status": "COVERED_BY_PARAMETER_TRIALS", "orders": 0, "metrics": {}}
            continue
        orders = 0
        trades = []
        seen: set[str] = set()
        for signal in sorted(signals, key=lambda item: (item.evaluation_date, item.code)):
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
            "metrics": calculate_trade_metrics(trades),
        }
    return results

"""Explicit conservative stress scenarios."""
from __future__ import annotations

import copy


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

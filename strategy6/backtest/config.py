"""Backtest-only configuration. Production strategy config remains read-only."""
from __future__ import annotations

import copy


DEFAULT_BACKTEST_CONFIG = {
    "price_mode": "forward_adjusted",
    "signal_generation_mode": "AS_OF_REBUILD",
    "signal_selection_mode": "LEGACY_SETUP_ID",
    "confidence_label": "RESEARCH_ONLY_CURRENT_UNIVERSE",
    "costs": {
        "commission_bps": 3.0,
        "minimum_commission": 5.0,
        "sell_tax_bps": 5.0,
        "transfer_fee_bps": 0.1,
        "buy_slippage_bps": 10.0,
        "sell_slippage_bps": 10.0,
    },
    "execution": {
        "entry_mode": "FROZEN_TRADE_PLAN",
        "below_buy_zone_open_mode": "CANCEL",
        "intraday_limit_fill_mode": "LIMIT_PLUS_SLIPPAGE",
        "buy_zone_valid_days": 3,
        "max_holding_days": 20,
        "same_day_stop_target": "STOP_FIRST",
        "use_t_plus_one": True,
    },
    "position": {
        "initial_equity": 1_000_000.0,
        "risk_per_trade": 0.01,
        "max_position_pct": 0.20,
        "max_concurrent_positions": 10,
        "max_single_stock_exposure_pct": 0.20,
    },
    "optimization": {
        "enabled": True,
        "method": "STRATIFIED_RANDOM",
        "max_trials": 2000,
        "random_seed": 20260711,
        "use_oos_for_selection": False,
        "require_manual_approval": True,
        "auto_write_production_config": False,
    },
}


def resolve_backtest_config(config: dict | None) -> dict:
    resolved = copy.deepcopy(DEFAULT_BACKTEST_CONFIG)
    for key, value in (config or {}).items():
        if key not in resolved:
            continue
        if isinstance(resolved[key], dict) and isinstance(value, dict):
            resolved[key].update(value)
        else:
            resolved[key] = value
    if resolved["price_mode"] != "forward_adjusted":
        raise ValueError("price_mode must be forward_adjusted")
    if resolved["signal_generation_mode"] != "AS_OF_REBUILD":
        raise ValueError("signal_generation_mode must be AS_OF_REBUILD")
    if resolved["signal_selection_mode"] not in {"LEGACY_SETUP_ID", "FIRST_EVENT_PER_START"}:
        raise ValueError("unsupported signal_selection_mode")
    if resolved["execution"].get("entry_mode") not in {"FROZEN_TRADE_PLAN", "ARCHETYPE_TRIGGERED"}:
        raise ValueError("unsupported entry_mode")
    if resolved["optimization"].get("auto_write_production_config"):
        raise ValueError("production config writes are forbidden")
    return resolved

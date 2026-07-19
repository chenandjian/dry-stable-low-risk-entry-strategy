import copy

import pytest

from strategy6.backtest.config import resolve_backtest_config
from strategy6.backtest.stress import (
    build_execution_tuning_configs,
    evaluate_stress_acceptance,
    replay_frozen_signals,
    replay_stress_scenarios,
    validate_replay_config,
)
from strategy6.backtest.models import BacktestSignal


def test_execution_tuning_changes_only_buy_validity_and_holding_period():
    base = resolve_backtest_config({})
    configs = build_execution_tuning_configs(base)

    assert len(configs) == 16
    assert {(item["buy_zone_valid_days"], item["max_holding_days"]) for item in configs} == {
        (buy_days, hold_days)
        for buy_days in (1, 2, 3, 5)
        for hold_days in (10, 15, 20, 30)
    }
    for item in configs:
        config = item["config"]
        assert config["costs"] == base["costs"]
        assert config["execution"]["use_t_plus_one"] is True
        assert config["execution"]["same_day_stop_target"] == "STOP_FIRST"


def test_replay_validation_forbids_lower_costs_or_execution_semantic_changes():
    base = resolve_backtest_config({})
    lower_cost = copy.deepcopy(base)
    lower_cost["costs"]["buy_slippage_bps"] = 0
    no_t1 = copy.deepcopy(base)
    no_t1["execution"]["use_t_plus_one"] = False
    target_first = copy.deepcopy(base)
    target_first["execution"]["same_day_stop_target"] = "TARGET_FIRST"

    with pytest.raises(ValueError, match="cost"):
        validate_replay_config(lower_cost, base)
    with pytest.raises(ValueError, match=r"T\+1"):
        validate_replay_config(no_t1, base)
    with pytest.raises(ValueError, match="STOP_FIRST"):
        validate_replay_config(target_first, base)


def test_stress_acceptance_rejects_negative_expectancy_and_subunit_pf():
    passing = {
        "HIGH_COST": {"metrics": {"expectancy_r": 0.01, "profit_factor": 1.01}},
        "LOW_FILL": {"metrics": {"expectancy_r": -0.01, "profit_factor": 1.10}},
        "ONE_DAY_DELAY": {"metrics": {"expectancy_r": 0.02, "profit_factor": 0.90}},
    }
    failing = copy.deepcopy(passing)
    failing["LOW_FILL"]["metrics"] = {"expectancy_r": -0.01, "profit_factor": 0.99}

    assert evaluate_stress_acceptance(passing)["passed"] is True
    result = evaluate_stress_acceptance(failing)
    assert result["passed"] is False
    assert result["checks"]["LOW_FILL"] is False


def test_execution_replay_uses_frozen_signals_without_strategy_reevaluation():
    signal = BacktestSignal(
        parameter_set_id="p1", code="000001", name="样本",
        evaluation_date="2025-01-02", setup_id="frozen-setup",
        tail_path="BOX", candidate_type="KEY_CANDIDATE",
        snapshot={
            "buy_zone_low": 9.8, "buy_zone_high": 10.2,
            "suggested_limit_price": 10.0, "stop_loss_price": 9.5,
            "objective_target_2": 11.5,
        },
    )
    rows = [
        {"date": "2025-01-02", "open": 10, "high": 10, "low": 10, "close": 10, "volume": 1000},
        {"date": "2025-01-03", "open": 10, "high": 10.2, "low": 9.8, "close": 10, "volume": 1000},
        {"date": "2025-01-06", "open": 11.5, "high": 11.6, "low": 11.4, "close": 11.5, "volume": 1000},
    ]

    result = replay_frozen_signals(
        [signal], load_rows=lambda code: rows,
        market_dates=[item["date"] for item in rows],
        config=resolve_backtest_config({}),
    )

    assert result["orders"] == 1
    assert result["metrics"]["trades"] == 1
    assert result["trades"][0]["signal_date"] == "2025-01-02"
    assert result["setup_ids"] == ["frozen-setup"]


def test_stress_replay_returns_auditable_metrics_for_exactly_three_scenarios():
    signal = BacktestSignal(
        parameter_set_id="p1", code="000001", name="样本",
        evaluation_date="2025-01-02", setup_id="stress-setup",
        tail_path="BOX", candidate_type="KEY_CANDIDATE",
        snapshot={
            "buy_zone_low": 9.8, "buy_zone_high": 10.2,
            "suggested_limit_price": 10.0, "stop_loss_price": 9.5,
            "objective_target_2": 11.5,
        },
    )
    rows = [
        {"date": "2025-01-02", "open": 10, "high": 10, "low": 10, "close": 10, "volume": 1000},
        {"date": "2025-01-03", "open": 10, "high": 10.2, "low": 9.8, "close": 10, "volume": 1000},
        {"date": "2025-01-06", "open": 11.5, "high": 11.6, "low": 11.4, "close": 11.5, "volume": 1000},
    ]

    result = replay_stress_scenarios(
        [signal], load_rows=lambda code: rows,
        market_dates=[item["date"] for item in rows],
        base_config=resolve_backtest_config({}),
    )

    assert set(result) == {"BASE", "HIGH_COST", "LOW_FILL", "ONE_DAY_DELAY"}
    for scenario in result.values():
        assert scenario["status"] == "COMPLETED"
        assert "orders" in scenario
        assert "unfilled_rate" in scenario
        assert "metrics" in scenario

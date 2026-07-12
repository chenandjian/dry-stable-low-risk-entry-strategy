from strategy6.backtest.config import resolve_backtest_config
from strategy6.backtest.stress import build_stress_scenarios, replay_stress_scenarios
from strategy6.backtest.models import BacktestSignal


def test_stress_scenarios_are_explicit_and_do_not_mutate_base_config():
    base = resolve_backtest_config({})
    original_buy_slippage = base["costs"]["buy_slippage_bps"]
    scenarios = build_stress_scenarios(base)
    assert {item["name"] for item in scenarios} >= {"BASE", "HIGH_COST", "LOW_FILL", "ONE_DAY_DELAY", "PARAMETER_PERTURBATION"}
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

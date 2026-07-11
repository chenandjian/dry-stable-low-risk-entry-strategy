from strategy6.backtest.config import resolve_backtest_config
from strategy6.backtest.stress import build_stress_scenarios


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

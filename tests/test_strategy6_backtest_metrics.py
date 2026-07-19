import math

from strategy6.backtest.metrics import (
    calculate_concentration,
    calculate_max_drawdown,
    calculate_trade_metrics,
    group_trade_metrics,
)


TRADES = [
    {"code": "A", "tail_path": "BOX", "box_status": "BOX_STABLE", "net_return": 0.10, "r_multiple": 2.0, "net_profit": 1000, "exit_date": "2025-01-10"},
    {"code": "B", "tail_path": "ORIGINAL", "box_status": "NO_BOX", "net_return": -0.05, "r_multiple": -1.0, "net_profit": -500, "exit_date": "2025-02-10"},
    {"code": "A", "tail_path": "BOTH", "box_status": "BOX_SUPPORT_READY", "net_return": 0.04, "r_multiple": 1.0, "net_profit": 400, "exit_date": "2025-02-20"},
]


def test_trade_metrics_include_expectancy_profit_factor_and_zero_case():
    metrics = calculate_trade_metrics(TRADES)
    assert metrics["trades"] == 3
    assert metrics["win_rate"] == 2 / 3
    assert metrics["expectancy_r"] == (2 + -1 + 1) / 3
    assert metrics["profit_factor"] == 2.8
    assert calculate_trade_metrics([])["trades"] == 0


def test_max_drawdown_uses_peak_to_trough_equity():
    assert calculate_max_drawdown([100, 120, 90, 110]) == 0.25


def test_path_grouping_and_profit_concentration_are_explicit():
    grouped = group_trade_metrics(TRADES, "tail_path")
    assert set(grouped) == {"BOX", "ORIGINAL", "BOTH"}
    concentration = calculate_concentration(TRADES)
    assert concentration["top_stock"] == "A"
    assert concentration["single_stock_profit_share"] > 1.0
    assert "SINGLE_STOCK_PROFIT_CONCENTRATION" in concentration["risk_tags"]

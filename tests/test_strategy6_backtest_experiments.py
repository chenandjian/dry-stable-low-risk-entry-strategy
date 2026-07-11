from strategy6.backtest.experiments import filter_experiment_signals, summarize_incremental_value


SIGNALS = [
    {"code": "A", "tail_path": "ORIGINAL", "box_status": "NO_BOX", "compact_kline_pass": False},
    {"code": "B", "tail_path": "BOX", "box_status": "BOX_SUPPORT_READY", "compact_kline_pass": True},
    {"code": "C", "tail_path": "BOTH", "box_status": "BOX_STABLE", "compact_kline_pass": False},
]


def test_e0_to_e5_filters_preserve_path_attribution():
    assert [s["code"] for s in filter_experiment_signals(SIGNALS, "E0_ORIGINAL_BASELINE")] == ["A", "C"]
    assert len(filter_experiment_signals(SIGNALS, "E1_DUAL_DEFAULT")) == 3
    assert [s["code"] for s in filter_experiment_signals(SIGNALS, "E2_BOX_ONLY_INCREMENT")] == ["B"]
    assert [s["code"] for s in filter_experiment_signals(SIGNALS, "E3_BOTH_ONLY")] == ["C"]
    assert [s["code"] for s in filter_experiment_signals(SIGNALS, "E4_BOX_COMPACT_READY")] == ["B"]
    assert [s["code"] for s in filter_experiment_signals(SIGNALS, "E5_BOX_SUPPORT_READY")] == ["B"]


def test_incremental_value_reports_capital_displacement_not_only_profit():
    result = summarize_incremental_value(
        baseline={"net_profit": 10_000, "max_drawdown": 0.10, "trades": 20, "unfilled_rate": 0.1},
        dual={"net_profit": 12_000, "max_drawdown": 0.14, "trades": 25, "unfilled_rate": 0.2},
        displaced_original_trades=3,
    )
    assert result["incremental_net_profit"] == 2000
    assert result["incremental_max_drawdown"] == 0.04
    assert result["displaced_original_trades"] == 3

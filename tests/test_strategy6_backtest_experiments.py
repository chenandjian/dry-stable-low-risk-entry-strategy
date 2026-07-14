from strategy6.backtest.experiments import (
    filter_experiment_signals,
    group_authoritative_path_metrics,
    summarize_incremental_value,
)
from strategy6.backtest.runner import _derive_experiment_metrics, build_phase_selection_results


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


def test_e6_to_e10_use_authoritative_paths_and_brooks_evidence_without_changing_legacy_enum():
    brooks_only = {
        "code": "D", "tail_path": "NONE", "tail_paths": ["BROOKS"],
        "original_tail_pass": False, "box_tail_pass": False, "brooks_tail_pass": True,
        "passed_path_count": 1, "brooks_status": "SECOND_ENTRY_LONG_READY",
        "brooks_result": {"structure": {"setup_types": ["MICRO_DOUBLE_BOTTOM"]}},
    }
    multi = {
        "code": "E", "tail_path": "ORIGINAL", "tail_paths": ["ORIGINAL", "BROOKS"],
        "original_tail_pass": True, "box_tail_pass": False, "brooks_tail_pass": True,
        "passed_path_count": 2, "brooks_status": "FAILED_BEAR_BREAKOUT",
        "brooks_result": {"structure": {"setup_types": ["FAILED_BEAR_BREAKOUT"]}},
    }
    flag_only_brooks = {
        "code": "F", "tail_path": "NONE", "original_tail_pass": False,
        "box_tail_pass": False, "brooks_tail_pass": True,
        "brooks_status": "ORDERLY_COMPRESSION_AT_SUPPORT",
        "brooks_result": {"structure": {"setup_types": ["ORDERLY_COMPRESSION_AT_SUPPORT"]}},
    }
    signals = SIGNALS + [brooks_only, multi, flag_only_brooks]

    assert [s["code"] for s in filter_experiment_signals(signals, "E6_BROOKS_ONLY")] == ["D", "F"]
    assert [s["code"] for s in filter_experiment_signals(signals, "E7_ORIGINAL_OR_BOX_OR_BROOKS")] == [
        "A", "B", "C", "D", "E", "F",
    ]
    assert [s["code"] for s in filter_experiment_signals(signals, "E8_MULTI_PATH_ONLY")] == ["C", "E"]
    assert [s["code"] for s in filter_experiment_signals(
        signals, "E9_BROOKS_STATUS_SECOND_ENTRY_LONG_READY"
    )] == ["D"]
    assert [s["code"] for s in filter_experiment_signals(
        signals, "E10_BROOKS_STRUCTURE_FAILED_BEAR_BREAKOUT"
    )] == ["E"]

    assert [s["code"] for s in filter_experiment_signals(SIGNALS, "E0_ORIGINAL_BASELINE")] == ["A", "C"]
    assert [s["code"] for s in filter_experiment_signals(SIGNALS, "E1_DUAL_DEFAULT")] == ["A", "B", "C"]
    metrics = group_authoritative_path_metrics([{
        **flag_only_brooks,
        "r_multiple": 1.5,
        "net_return": 0.08,
        "net_profit": 800,
    }])
    assert metrics["BROOKS"]["trades"] == 1


def test_runner_adds_parallel_three_path_and_brooks_breakdowns_without_overwriting_legacy_metrics():
    trades = [
        {
            "code": "D", "signal_date": "2025-01-02", "exit_date": "2025-01-10",
            "tail_path": "NONE", "tail_paths": ["BROOKS"], "tail_primary_path": "BROOKS",
            "tail_path_summary": "BROOKS", "passed_path_count": 1,
            "brooks_status": "SECOND_ENTRY_LONG_READY", "brooks_setup_types": ["MICRO_DOUBLE_BOTTOM"],
            "candidate_type": "KEY_CANDIDATE", "market_status": "MARKET_OK", "pattern_type": "VCP",
            "r_multiple": 2.0, "net_return": 0.1, "net_profit": 1000,
        }
    ]

    experiments = _derive_experiment_metrics(trades)
    assert experiments["E6_BROOKS_ONLY"]["trades"] == 1
    assert experiments["E7_ORIGINAL_OR_BOX_OR_BROOKS"]["trades"] == 1
    assert experiments["E9_BROOKS_STATUS_SECOND_ENTRY_LONG_READY"]["trades"] == 1
    assert experiments["E10_BROOKS_STRUCTURE_MICRO_DOUBLE_BOTTOM"]["trades"] == 1

    phases = build_phase_selection_results(trades, {
        "initial_equity": 1_000_000,
        "risk_per_trade": 0.01,
        "max_position_pct": 0.1,
        "max_concurrent_positions": 5,
    })
    breakdowns = phases["VALIDATION"]["breakdowns"]
    assert breakdowns["tail_path"]["NONE"]["trades"] == 1
    assert breakdowns["authoritative_tail_path"]["BROOKS"]["trades"] == 1
    assert breakdowns["tail_primary_path"]["BROOKS"]["trades"] == 1
    assert breakdowns["tail_path_summary"]["BROOKS"]["trades"] == 1
    assert breakdowns["brooks_status"]["SECOND_ENTRY_LONG_READY"]["trades"] == 1


def test_incremental_value_reports_capital_displacement_not_only_profit():
    result = summarize_incremental_value(
        baseline={"net_profit": 10_000, "max_drawdown": 0.10, "trades": 20, "unfilled_rate": 0.1},
        dual={"net_profit": 12_000, "max_drawdown": 0.14, "trades": 25, "unfilled_rate": 0.2},
        displaced_original_trades=3,
    )
    assert result["incremental_net_profit"] == 2000
    assert result["incremental_max_drawdown"] == 0.04
    assert result["displaced_original_trades"] == 3

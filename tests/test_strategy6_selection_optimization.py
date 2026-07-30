import json
import sqlite3
from datetime import date, timedelta

from strategy6.backtest.selection_optimization import (
    audit_score_components,
    assess_score_calibration,
    build_selection_trial_configs,
    evaluate_frozen_selection_trials,
    build_selection_comparison_markdown,
    replay_selection_trial,
    build_score_audit_markdown,
    load_score_audit_rows,
    rebuild_frozen_selection_diagnostics,
)
from strategy6.models import (
    Strategy6SelectionDiagnostics,
    Strategy6SetupQuality,
    Strategy6Support,
    Strategy6TailRegime,
    Strategy6TradePlan,
)
from strategy6.selection_diagnostics import evaluate_selection_diagnostics
from strategy6.market import compute_relative_strength_periods
from strategy6.filters import (
    selection_blocks_ready,
    selection_hard_filter_reasons,
    selection_rr,
)
from strategy6.validation import resolve_strategy6_config


def test_score_audit_reports_saturation_pair_correlation_and_non_monotonic_total():
    rows = [
        {
            "strong_start_score": 10 + index,
            "pattern_score_component": 5 + index,
            "support_score": 20,
            "tail_score": 10 + index,
            "objective_rr_score": 10,
            "relative_strength_risk_score": 5 + index,
            "total_score": 60 + index * 10,
            "r_multiple": outcome,
        }
        for index, outcome in enumerate((0.5, -1.0, 0.2, -0.8))
    ]

    audit = audit_score_components(rows)

    assert audit["sample_size"] == 4
    assert audit["components"]["support_score"]["saturation_ratio"] == 1.0
    assert audit["components"]["objective_rr_score"]["saturation_ratio"] == 1.0
    assert audit["pairwise_spearman"]["strong_start_score|tail_score"] == 1.0
    assert audit["total_score_monotonic"] is False
    assert audit["score_bands"][-1]["mean_r"] == -0.8
    assessment = assess_score_calibration(audit)
    assert "strong_start_score|tail_score" in assessment["duplicate_pairs"]
    assert assessment["automatic_weight_change_allowed"] is False


def test_score_audit_ignores_missing_outcomes_and_marks_small_samples():
    rows = [
        {"total_score": 70, "support_score": 20, "r_multiple": None},
        {"total_score": 80, "support_score": 20, "r_multiple": 1.0},
    ]

    audit = audit_score_components(rows)

    assert audit["sample_size"] == 1
    assert audit["reliable"] is False
    assert audit["components"]["support_score"]["sample_size"] == 1
    assert assess_score_calibration(audit)["decision"] == "BLOCKED_INSUFFICIENT_SAMPLE"


def test_score_audit_loader_joins_trade_to_exact_signal_date_and_report_is_explicit():
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE strategy6_backtest_signals (
            run_id TEXT, parameter_set_id TEXT, code TEXT,
            evaluation_date TEXT, snapshot_json TEXT
        );
        CREATE TABLE strategy6_backtest_trades (
            run_id TEXT, parameter_set_id TEXT, code TEXT,
            signal_date TEXT, exit_date TEXT, r_multiple REAL
        );
        """
    )
    snapshot = {
        "strong_start_score": 18,
        "pattern_score_component": 16,
        "support_score": 20,
        "tail_score": 17,
        "objective_rr_score": 10,
        "relative_strength_risk_score": 9,
        "total_score": 90,
    }
    conn.execute(
        "INSERT INTO strategy6_backtest_signals VALUES (?, ?, ?, ?, ?)",
        ("run-1", "p-1", "000001", "2025-01-02", json.dumps(snapshot)),
    )
    conn.execute(
        "INSERT INTO strategy6_backtest_trades VALUES (?, ?, ?, ?, ?, ?)",
        ("run-1", "p-1", "000001", "2025-01-02", "2025-01-10", -1.0),
    )

    rows = load_score_audit_rows(conn, "run-1", "p-1")
    report = build_score_audit_markdown(
        audit_score_components(rows),
        run_id="run-1",
        parameter_set_id="p-1",
    )

    assert rows[0]["support_score"] == 20
    assert rows[0]["r_multiple"] == -1.0
    assert "run-1" in report
    assert "样本不足" in report
    assert "support_score" in report


def test_selection_diagnostics_exposes_independent_facts_without_classifying_candidate():
    start = date(2025, 1, 1)
    stock_rows = []
    market_rows = []
    for index in range(80):
        day = (start + timedelta(days=index)).isoformat()
        stock_close = 10 + index * 0.15
        market_close = 100 + index * 0.5
        stock_rows.append({
            "date": day, "open": stock_close, "high": stock_close * 1.01,
            "low": stock_close * 0.99, "close": stock_close, "volume": 1_000_000,
        })
        market_rows.append({
            "date": day, "open": market_close, "high": market_close * 1.01,
            "low": market_close * 0.99, "close": market_close, "volume": 2_000_000,
        })
    market = {
        "sh000001": market_rows,
        "sz399001": market_rows,
        "sz399006": market_rows,
        "hs300": market_rows,
    }

    result = evaluate_selection_diagnostics(
        stock_rows,
        code="300001",
        support=Strategy6Support(
            support_status="PATTERN_SUPPORT",
            support_reaction_score=6,
            support_reaction_reasons=["SUPPORT_TEST_RECOVERED"],
        ),
        tail_regime=Strategy6TailRegime(
            status="BROKEN",
            risks=["TAIL_REGIME_LOW_DETERIORATING"],
        ),
        trade_plan=Strategy6TradePlan(objective_rr_1=1.8, objective_rr_2=3.2),
        setup_quality=Strategy6SetupQuality(relative_strength_trend="IMPROVING"),
        market_data_by_symbol=market,
        expected_trade_date=stock_rows[-1]["date"],
    )

    assert result.matched_market_symbol == "sz399006"
    assert result.matched_market_status == "MARKET_STRONG"
    assert result.relative_strength_5 > 0
    assert result.relative_strength_60 > 0
    assert result.relative_strength_periods_observed == [5, 10, 20, 60]
    assert result.relative_strength_trend == "IMPROVING"
    assert result.support_confirmation_status == "CONFIRMED"
    assert result.recent_tail_status == "DETERIORATING"
    assert result.conservative_rr == 1.8


def test_selection_diagnostics_marks_unrecovered_support_break_failed():
    result = evaluate_selection_diagnostics(
        [],
        code="600001",
        support=Strategy6Support(
            support_status="PATTERN_SUPPORT",
            support_reaction_score=8,
            support_reaction_risk_tags=["SUPPORT_VOLUME_BREAK_UNRECOVERED"],
        ),
        tail_regime=Strategy6TailRegime(status="INSUFFICIENT_BASELINE"),
        trade_plan=Strategy6TradePlan(),
        setup_quality=Strategy6SetupQuality(),
        market_data_by_symbol=None,
    )

    assert result.support_confirmation_status == "FAILED"
    assert result.matched_market_symbol == "sh000001"
    assert result.matched_market_status == "UNKNOWN"


def test_relative_strength_keeps_legacy_periods_when_rs60_history_is_unavailable():
    start = date(2025, 1, 1)
    stock_rows = []
    market_rows = []
    for index in range(40):
        day = (start + timedelta(days=index)).isoformat()
        stock_rows.append({"date": day, "close": 10 + index * 0.2})
        market_rows.append({"date": day, "close": 100 + index * 0.5})

    periods = compute_relative_strength_periods(
        stock_rows,
        {"hs300": market_rows},
        expected_trade_date=stock_rows[-1]["date"],
    )

    assert set(periods) == {5, 10, 20}


def test_selection_optimization_defaults_are_audit_only():
    config = resolve_strategy6_config({})
    diagnostics = Strategy6SelectionDiagnostics(
        support_confirmation_status="FAILED",
        recent_tail_status="DETERIORATING",
        relative_strength_trend="FADING",
        matched_market_status="MARKET_RISK",
        conservative_rr=0.5,
    )

    assert selection_hard_filter_reasons(diagnostics, config) == []
    assert selection_blocks_ready(diagnostics, config) is False
    assert selection_rr(Strategy6TradePlan(objective_rr_2=3.0), diagnostics, config) == 3.0


def test_selection_optimization_rules_have_independent_and_explicit_effects():
    diagnostics = Strategy6SelectionDiagnostics(
        support_confirmation_status="FAILED",
        recent_tail_status="DETERIORATING",
        relative_strength_trend="FADING",
        matched_market_status="MARKET_WEAK",
        conservative_rr=1.2,
    )
    config = resolve_strategy6_config({
        "strategy6": {
            "selection_optimization": {
                "support_confirmation_enabled": True,
                "conservative_rr_enabled": True,
                "rs_fading_downgrade_enabled": True,
                "tail_deterioration_filter_enabled": True,
                "matched_market_downgrade_enabled": True,
            },
        },
    })

    assert selection_hard_filter_reasons(diagnostics, config) == [
        "SUPPORT_CONFIRMATION_FAILED",
        "RECENT_TAIL_DETERIORATING",
    ]
    assert selection_blocks_ready(diagnostics, config) is True
    assert selection_rr(Strategy6TradePlan(objective_rr_2=3.0), diagnostics, config) == 1.2


def test_partial_support_only_blocks_key_and_ready_when_experiment_is_enabled():
    diagnostics = Strategy6SelectionDiagnostics(
        support_confirmation_status="PARTIAL",
        relative_strength_trend="IMPROVING",
        matched_market_status="MARKET_STRONG",
    )
    config = resolve_strategy6_config({
        "strategy6": {
            "selection_optimization": {"support_confirmation_enabled": True},
        },
    })

    assert selection_hard_filter_reasons(diagnostics, config) == []
    assert selection_blocks_ready(diagnostics, config) is True


def test_selection_trials_change_one_rule_at_a_time_before_combined_trial():
    trials = build_selection_trial_configs(resolve_strategy6_config({}))

    assert [trial["experiment_id"] for trial in trials] == [
        "S6_SELECT_E0_BASELINE",
        "S6_SELECT_E1_SUPPORT",
        "S6_SELECT_E2_CONSERVATIVE_RR",
        "S6_SELECT_E3_RS_FADING",
        "S6_SELECT_E4_TAIL_DETERIORATION",
        "S6_SELECT_E5_MATCHED_MARKET",
        "S6_SELECT_E6_COMBINED",
    ]
    for trial in trials[1:-1]:
        enabled = [
            key for key, value in trial["config"]["selection_optimization"].items()
            if value
        ]
        assert len(enabled) == 1
    assert all(trials[-1]["config"]["selection_optimization"].values())


def test_frozen_selection_replay_downgrades_or_removes_without_rebuilding_indicators():
    signal = {
        "code": "000001",
        "evaluation_date": "2025-01-02",
        "setup_id": "setup-1",
        "candidate_type": "KEY_CANDIDATE",
        "snapshot": {
            "code": "000001",
            "evaluation_date": "2025-01-02",
            "setup_id": "setup-1",
            "candidate_type": "KEY_CANDIDATE",
            "support_confirmation_status": "PARTIAL",
            "recent_tail_status": "STABLE",
            "relative_strength_trend": "IMPROVING",
            "matched_market_status": "MARKET_STRONG",
            "conservative_rr": 1.2,
        },
    }
    trade = {
        "setup_id": "setup-1", "signal_date": "2025-01-02",
        "exit_date": "2025-01-10", "r_multiple": 1.5,
    }
    support_config = resolve_strategy6_config({
        "strategy6": {
            "selection_optimization": {"support_confirmation_enabled": True},
        },
    })
    rr_config = resolve_strategy6_config({
        "strategy6": {
            "selection_optimization": {"conservative_rr_enabled": True},
        },
    })

    downgraded = replay_selection_trial([signal], [trade], support_config)
    removed = replay_selection_trial([signal], [trade], rr_config)

    assert downgraded["signals"][0]["candidate_type"] == "WATCH_CANDIDATE"
    assert downgraded["downgraded_count"] == 1
    assert len(downgraded["trades"]) == 1
    assert downgraded["actionable_trades"] == []
    assert downgraded["actionable_trade_metrics"]["trades"] == 0
    assert removed["signals"] == []
    assert removed["removed_count"] == 1
    assert removed["trades"] == []


def test_frozen_selection_replay_reports_actionable_tiers_separately():
    signals = [
        {
            "code": f"00000{index}",
            "evaluation_date": "2025-01-02",
            "setup_id": f"setup-{candidate_type}",
            "candidate_type": candidate_type,
            "snapshot": {
                "objective_rr_2": 3.0,
                "conservative_rr": 2.0,
                "recent_tail_status": "STABLE",
            },
        }
        for index, candidate_type in enumerate(
            ("READY_CANDIDATE", "KEY_CANDIDATE", "WATCH_CANDIDATE"),
            start=1,
        )
    ]
    trades = [
        {
            "setup_id": signal["setup_id"],
            "signal_date": signal["evaluation_date"],
            "exit_date": "2025-01-10",
            "r_multiple": outcome,
        }
        for signal, outcome in zip(signals, (2.0, 1.0, -1.0))
    ]

    replay = replay_selection_trial(signals, trades, resolve_strategy6_config({}))

    assert len(replay["trades"]) == 3
    assert len(replay["actionable_trades"]) == 2
    assert replay["actionable_trade_metrics"]["trades"] == 2
    assert replay["actionable_trade_metrics"]["expectancy_r"] == 1.5


def test_frozen_selection_metrics_exclude_trades_without_an_exit():
    signal = {
        "code": "000001",
        "evaluation_date": "2025-12-31",
        "setup_id": "open-setup",
        "candidate_type": "KEY_CANDIDATE",
        "snapshot": {
            "objective_rr_2": 3.0,
            "conservative_rr": 2.0,
            "recent_tail_status": "STABLE",
        },
    }
    open_trade = {
        "setup_id": "open-setup",
        "signal_date": "2025-12-31",
        "exit_date": None,
        "r_multiple": 0.0,
    }

    replay = replay_selection_trial(
        [signal],
        [open_trade],
        resolve_strategy6_config({}),
    )

    assert replay["trades"] == [open_trade]
    assert replay["closed_trades"] == []
    assert replay["trade_metrics"]["trades"] == 0
    assert replay["actionable_trade_metrics"]["trades"] == 0


def test_frozen_selection_replay_filters_trade_by_setup_and_exact_signal_date():
    signals = [
        {
            "code": "000001", "evaluation_date": day, "setup_id": "same-setup",
            "candidate_type": "WATCH_CANDIDATE",
            "snapshot": {
                "objective_rr_2": 3.0,
                "conservative_rr": conservative_rr,
                "recent_tail_status": "STABLE",
            },
        }
        for day, conservative_rr in (("2025-01-02", 2.0), ("2025-01-03", 1.0))
    ]
    trades = [
        {
            "setup_id": "same-setup", "signal_date": day,
            "exit_date": "2025-01-10", "r_multiple": outcome,
        }
        for day, outcome in (("2025-01-02", 1.0), ("2025-01-03", -1.0))
    ]
    config = resolve_strategy6_config({
        "strategy6": {
            "selection_optimization": {"conservative_rr_enabled": True},
        },
    })

    replay = replay_selection_trial(signals, trades, config)

    assert [trade["signal_date"] for trade in replay["trades"]] == ["2025-01-02"]


def test_frozen_trial_comparison_keeps_train_and_validation_separate():
    signals = []
    trades = []
    for day, rr, outcome in (
        ("2024-06-03", 2.0, 1.0),
        ("2025-06-03", 1.0, -1.0),
    ):
        setup_id = f"setup-{day}"
        signals.append({
            "code": "000001", "evaluation_date": day, "setup_id": setup_id,
            "candidate_type": "WATCH_CANDIDATE",
            "snapshot": {
                "objective_rr_2": 3.0, "conservative_rr": rr,
                "recent_tail_status": "STABLE",
            },
        })
        trades.append({
            "setup_id": setup_id, "signal_date": day,
            "exit_date": day, "r_multiple": outcome,
        })
    trials = build_selection_trial_configs(resolve_strategy6_config({}))[:3]

    result = evaluate_frozen_selection_trials(signals, trades, trials)

    baseline = result[0]
    conservative = result[2]
    assert baseline["train"]["trade_metrics"]["trades"] == 1
    assert baseline["validation"]["trade_metrics"]["trades"] == 1
    assert conservative["train"]["trade_metrics"]["trades"] == 1
    assert conservative["validation"]["trade_metrics"]["trades"] == 0
    assert conservative["validation"]["removed_count"] == 1
    report = build_selection_comparison_markdown(
        result,
        source_run_id="run-1",
        parameter_set_id="p-1",
    )
    assert "S6_SELECT_E2_CONSERVATIVE_RR" in report
    assert "训练期" in report
    assert "验证期" in report


def test_frozen_diagnostic_rebuild_slices_stock_and_market_at_signal_date():
    calls = []

    class FakeEvaluation:
        def to_candidate_dict(self):
            return {
                "selection_diagnostics_version": "S6_SELECTION_DIAGNOSTICS_V1",
                "relative_strength_5": 0.12,
                "support_confirmation_status": "CONFIRMED",
                "recent_tail_status": "STABLE",
                "conservative_rr": 2.1,
            }

    class FakeEngine:
        def evaluate_at(self, rows, **kwargs):
            calls.append((rows[-1]["date"], kwargs["market_data_by_symbol"]["hs300"][-1]["date"]))
            return FakeEvaluation()

    rows = [
        {"date": day, "close": 10.0, "open": 10.0, "high": 10.1, "low": 9.9, "volume": 1}
        for day in ("2025-01-01", "2025-01-02", "2025-01-03")
    ]
    signals = [{
        "code": "000001",
        "name": "测试",
        "evaluation_date": "2025-01-02",
        "setup_id": "frozen-setup",
        "candidate_type": "KEY_CANDIDATE",
        "snapshot": {"total_score": 80},
    }]

    result = rebuild_frozen_selection_diagnostics(
        signals,
        stock_rows_by_code={"000001": rows},
        market_data_by_symbol={"hs300": rows},
        engine=FakeEngine(),
        minimum_history=1,
    )

    assert calls == [("2025-01-02", "2025-01-02")]
    assert result["failed"] == []
    assert result["signals"][0]["setup_id"] == "frozen-setup"
    assert result["signals"][0]["snapshot"]["total_score"] == 80
    assert result["signals"][0]["snapshot"]["conservative_rr"] == 2.1

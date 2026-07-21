from __future__ import annotations

from types import SimpleNamespace

import pytest

from strategy6.backtest.config import resolve_backtest_config
from strategy6.backtest.tail_regime_research import (
    _filter_stress_results_for_research_periods,
    _partition_closed_trades,
    _remaining_rejects_after_regime,
    _research_gate,
    classify_tail_regime_group,
    replay_tail_regime_labels,
    run_tail_regime_research,
)


class _RecordingEngine:
    config = {"decision_profile": "formal_original"}

    def __init__(self, calls: list[tuple[str, str]]):
        self.calls = calls

    def evaluate_at(self, rows, *, code, name, trading_days_override, market_data_by_symbol):
        evaluation_date = rows[-1]["date"]
        self.calls.append((code, evaluation_date))
        fixed_pass = code in {"BOTH", "FIXED_ONLY"}
        regime_status = "CONFIRMED" if code in {"BOTH", "REGIME_ONLY"} else "NO_REGIME_CHANGE"
        return SimpleNamespace(to_candidate_dict=lambda: {
            "code": code,
            "name": name,
            "evaluation_date": evaluation_date,
            "original_tail_pass": fixed_pass,
            "tail_regime_status": regime_status,
            "tail_regime_start_date": evaluation_date if regime_status == "CONFIRMED" else "",
            "tail_regime_days": 5 if regime_status == "CONFIRMED" else 0,
            "tail_regime_delta_bic": 12.5 if regime_status == "CONFIRMED" else 0.0,
            "tail_regime_reasons": ["ROBUST_BIC_CHANGE_POINT"] if regime_status == "CONFIRMED" else [],
            "tail_regime_risks": [],
            "reject_reasons": [] if fixed_pass else ["TAIL_VOLUME_NOT_DRY"],
        })


def _rows(*dates: str) -> list[dict]:
    return [
        {"date": value, "open": 10, "high": 10.2, "low": 9.8, "close": 10, "volume": 1_000_000}
        for value in dates
    ]


def _market_rows(*dates: str) -> dict[str, list[dict]]:
    return {
        symbol: _rows(*dates)
        for symbol in ("sh000001", "sz399001", "sz399006", "hs300")
    }


def _passing_stress_results() -> dict:
    def scenario(trades: int) -> dict:
        return {
            "status": "COMPLETED",
            "orders": 30,
            "metrics": {
                "trades": trades,
                "expectancy_r": 0.1,
                "profit_factor": 1.2,
            },
        }

    return {
        "BASE": scenario(30),
        "HIGH_COST": scenario(30),
        "LOW_FILL": scenario(21),
        "ONE_DAY_DELAY": scenario(18),
    }


@pytest.mark.parametrize(
    ("fixed_pass", "regime_status", "expected"),
    [
        (True, "CONFIRMED", "BOTH"),
        (True, "FORMING", "FIXED_ONLY"),
        (False, "CONFIRMED", "REGIME_ONLY"),
        (False, "BROKEN", "NEITHER"),
    ],
)
def test_tail_regime_group_is_defined_only_by_fixed_pass_and_confirmation(
    fixed_pass, regime_status, expected,
):
    assert classify_tail_regime_group({
        "original_tail_pass": fixed_pass,
        "tail_regime_status": regime_status,
    }) == expected


def test_replay_is_as_of_skips_missing_bar_and_never_reads_locked_oos():
    calls: list[tuple[str, str]] = []
    data_by_code = {
        code: {"name": code, "rows": _rows("2025-12-30", "2025-12-31", "2026-01-02")}
        for code in ("BOTH", "FIXED_ONLY", "REGIME_ONLY", "NEITHER")
    }
    data_by_code["NEITHER"]["rows"] = _rows("2025-12-30", "2026-01-02")

    result = replay_tail_regime_labels(
        data_by_code=data_by_code,
        evaluation_dates=["2025-12-31", "2026-01-02"],
        market_data_by_symbol=_market_rows("2025-12-30", "2025-12-31", "2026-01-02"),
        reference_market_dates=["2025-12-30", "2025-12-31", "2026-01-02"],
        engine_factory=lambda: _RecordingEngine(calls),
        minimum_history=1,
        oos_start="2026-01-01",
    )

    assert {(row["code"], row["group"]) for row in result["daily_labels"]} == {
        ("BOTH", "BOTH"),
        ("FIXED_ONLY", "FIXED_ONLY"),
        ("REGIME_ONLY", "REGIME_ONLY"),
    }
    assert all(evaluation_date == "2025-12-31" for _, evaluation_date in calls)
    assert result["oos_status"] == "OOS_LOCKED"
    assert result["locked_date_count"] == 1


def test_replay_passes_only_market_rows_visible_on_evaluation_date():
    observed_market_dates: list[list[str]] = []

    class MarketRecordingEngine:
        def evaluate_at(self, rows, **kwargs):
            observed_market_dates.append([
                row["date"]
                for values in kwargs["market_data_by_symbol"].values()
                for row in values
            ])
            return SimpleNamespace(to_candidate_dict=lambda: {
                "original_tail_pass": False,
                "tail_regime_status": "NO_REGIME_CHANGE",
            })

    replay_tail_regime_labels(
        data_by_code={"000001": {"name": "样本", "rows": _rows("2025-01-02", "2025-01-03")}},
        evaluation_dates=["2025-01-02"],
        market_data_by_symbol=_market_rows("2025-01-02", "2025-01-03"),
        reference_market_dates=["2025-01-02", "2025-01-03"],
        engine_factory=MarketRecordingEngine,
        minimum_history=1,
        oos_start="2026-01-01",
    )

    assert observed_market_dates == [["2025-01-02"] * 4]


def test_research_is_blocked_when_any_required_real_index_is_missing():
    calls: list[tuple[str, str]] = []

    result = replay_tail_regime_labels(
        data_by_code={"BOTH": {"name": "样本", "rows": _rows("2025-01-02")}},
        evaluation_dates=["2025-01-02"],
        market_data_by_symbol={"sh000001": _rows("2025-01-02")},
        reference_market_dates=["2025-01-02"],
        engine_factory=lambda: _RecordingEngine(calls),
        minimum_history=1,
    )

    assert result["status"] == "BLOCKED_INDEX_HISTORY"
    assert set(result["missing_index_symbols"]) == {"sz399001", "sz399006", "hs300"}
    assert result["daily_labels"] == []
    assert calls == []


def test_research_is_blocked_when_an_index_misses_post_signal_execution_date():
    market = _market_rows("2025-01-02", "2025-01-03")
    market["hs300"] = _rows("2025-01-02")

    result = replay_tail_regime_labels(
        data_by_code={"BOTH": {"name": "样本", "rows": _rows("2025-01-02")}},
        evaluation_dates=["2025-01-02"],
        market_data_by_symbol=market,
        reference_market_dates=["2025-01-02", "2025-01-03"],
        engine_factory=lambda: _RecordingEngine([]),
        minimum_history=1,
    )

    assert result["status"] == "BLOCKED_INDEX_HISTORY"
    assert result["missing_index_symbols"] == ["hs300"]
    assert result["index_coverage"]["hs300"]["missing_dates"] == ["2025-01-03"]


def test_research_is_blocked_when_all_indexes_miss_reference_calendar_end_date():
    result = replay_tail_regime_labels(
        data_by_code={"BOTH": {"name": "样本", "rows": _rows("2025-01-02")}},
        evaluation_dates=["2025-01-02"],
        market_data_by_symbol=_market_rows("2025-01-02"),
        reference_market_dates=["2025-01-02", "2025-01-03"],
        engine_factory=lambda: _RecordingEngine([]),
        minimum_history=1,
    )

    assert result["status"] == "BLOCKED_INDEX_HISTORY"
    assert set(result["missing_index_symbols"]) == {
        "sh000001", "sz399001", "sz399006", "hs300",
    }


def test_research_rejects_empty_or_incomplete_reference_market_calendar():
    common = {
        "data_by_code": {"BOTH": {"name": "样本", "rows": _rows("2025-01-02")}},
        "evaluation_dates": ["2025-01-02"],
        "market_data_by_symbol": _market_rows("2025-01-02"),
        "engine_factory": lambda: _RecordingEngine([]),
        "minimum_history": 1,
    }

    with pytest.raises(ValueError, match="reference market calendar"):
        replay_tail_regime_labels(**common, reference_market_dates=[])
    with pytest.raises(ValueError, match="evaluation dates"):
        replay_tail_regime_labels(
            **common,
            reference_market_dates=["2025-01-03"],
        )


def test_research_gate_uses_regime_only_trades_not_fixed_tail_performance():
    def regime_trades(period: str) -> list[dict]:
        return [
            {
                "tail_regime_group": "REGIME_ONLY",
                "r_multiple": 3.0 if index < 12 else -1.0,
                "net_return": 0.03 if index < 12 else -0.01,
                "net_profit": 300.0 if index < 12 else -100.0,
                "signal_date": f"{period}-01-{index + 1:02d}",
            }
            for index in range(15)
        ]

    fixed_losses = [
        {
            "tail_regime_group": "FIXED_ONLY",
            "r_multiple": -5.0,
            "net_return": -0.05,
            "net_profit": -500.0,
        }
        for _ in range(10)
    ]

    gate_without_stress = _research_gate(
        regime_trades("2024") + fixed_losses,
        regime_trades("2025") + fixed_losses,
    )

    assert gate_without_stress["status"] == "CONTINUE_SHADOW"
    assert "STRESS_REPLAYS_REQUIRED" in gate_without_stress["reasons"]

    passing_stress = _passing_stress_results()
    gate_with_stress = _research_gate(
        regime_trades("2024") + fixed_losses,
        regime_trades("2025") + fixed_losses,
        stress_results=passing_stress,
    )

    assert gate_with_stress["status"] == "PASS"
    assert gate_with_stress["regime_only_closed_trades"] == 30
    assert gate_with_stress["stress_status"] == "PASS"


def test_research_gate_treats_profitable_zero_loss_period_as_infinite_win_loss_ratio():
    def all_wins(year: str) -> list[dict]:
        return [
            {
                "tail_regime_group": "REGIME_ONLY",
                "r_multiple": 1.0,
                "net_return": 0.01,
                "net_profit": 100.0,
                "signal_date": f"{year}-01-{index + 1:02d}",
            }
            for index in range(15)
        ]

    stress = _passing_stress_results()

    gate = _research_gate(all_wins("2024"), all_wins("2025"), stress_results=stress)

    assert gate["status"] == "PASS"
    assert not any("AVG_WIN_LOSS" in reason for reason in gate["reasons"])


def test_research_rejects_non_formal_decision_profile():
    class ResearchProfileEngine(_RecordingEngine):
        config = {"decision_profile": "research_quality_v2"}

    with pytest.raises(ValueError, match="formal_original"):
        run_tail_regime_research(
            parameter_set_id="s6ps-test",
            data_by_code={"BOTH": {"name": "样本", "rows": _rows("2025-01-02")}},
            evaluation_dates=["2025-01-02"],
            market_data_by_symbol=_market_rows("2025-01-02", "2025-01-03"),
            reference_market_dates=["2025-01-02", "2025-01-03"],
            backtest_config={},
            engine_factory=lambda: ResearchProfileEngine([]),
            minimum_history=1,
        )


def test_label_replay_rejects_non_formal_decision_profile():
    class ResearchProfileEngine(_RecordingEngine):
        config = {"decision_profile": "research_quality_v2"}

    with pytest.raises(ValueError, match="formal_original"):
        replay_tail_regime_labels(
            data_by_code={"BOTH": {"name": "样本", "rows": _rows("2025-01-02")}},
            evaluation_dates=["2025-01-02"],
            market_data_by_symbol=_market_rows("2025-01-02"),
            reference_market_dates=["2025-01-02"],
            engine_factory=lambda: ResearchProfileEngine([]),
            minimum_history=1,
        )


def test_wait_breakout_snapshot_is_not_sent_to_execution(monkeypatch):
    class WaitingEngine:
        config = {"decision_profile": "formal_original"}

        def evaluate_at(self, rows, **kwargs):
            return SimpleNamespace(to_candidate_dict=lambda: {
                "code": "000001",
                "name": "等待突破",
                "evaluation_date": rows[-1]["date"],
                "candidate_type": "WATCH_CANDIDATE",
                "entry_archetype": "WAIT_BREAKOUT",
                "original_tail_pass": True,
                "tail_paths": ["ORIGINAL"],
                "tail_regime_status": "NO_REGIME_CHANGE",
            })

    def fail_execution(*args, **kwargs):
        raise AssertionError("WAIT_BREAKOUT must not enter execution")

    monkeypatch.setattr(
        "strategy6.backtest.tail_regime_research.simulate_frozen_trade",
        fail_execution,
    )
    result = run_tail_regime_research(
        parameter_set_id="s6ps-test",
        data_by_code={"000001": {"name": "等待突破", "rows": _rows("2025-01-02")}},
        evaluation_dates=["2025-01-02"],
        market_data_by_symbol=_market_rows("2025-01-02", "2025-01-03"),
        reference_market_dates=["2025-01-02", "2025-01-03"],
        backtest_config={},
        engine_factory=WaitingEngine,
        minimum_history=1,
    )

    assert result["signals"] == []
    assert result["orders"] == []


def test_execution_cannot_read_stock_or_market_rows_from_locked_oos():
    class ReadyEngine:
        config = {"decision_profile": "formal_original"}

        def evaluate_at(self, rows, **kwargs):
            return SimpleNamespace(to_candidate_dict=lambda: {
                "code": "000001",
                "name": "样本",
                "evaluation_date": rows[-1]["date"],
                "candidate_type": "KEY_CANDIDATE",
                "entry_archetype": "SUPPORT_BUY",
                "original_tail_pass": True,
                "tail_paths": ["ORIGINAL"],
                "tail_regime_status": "NO_REGIME_CHANGE",
                "buy_zone_low": 9.8,
                "buy_zone_high": 10.2,
                "suggested_limit_price": 10.0,
                "stop_loss_price": 9.5,
                "objective_target_2": 11.5,
            })

    result = run_tail_regime_research(
        parameter_set_id="s6ps-oos",
        data_by_code={
            "000001": {
                "name": "样本",
                "rows": _rows("2025-12-31", "2026-01-02", "2026-01-05"),
            },
        },
        evaluation_dates=["2025-12-31"],
        market_data_by_symbol=_market_rows("2025-12-31", "2026-01-02", "2026-01-05"),
        reference_market_dates=["2025-12-31", "2026-01-02", "2026-01-05"],
        backtest_config=resolve_backtest_config({}),
        engine_factory=ReadyEngine,
        minimum_history=1,
        oos_start="2026-01-01",
    )

    assert result["orders"][0]["status"] == "EXPIRED_NO_FILL"
    assert result["trades"] == []


def test_oos_lock_date_cannot_be_moved_later_by_caller():
    with pytest.raises(ValueError, match="2026-01-01"):
        replay_tail_regime_labels(
            data_by_code={},
            evaluation_dates=[],
            market_data_by_symbol=_market_rows("2025-01-02"),
            reference_market_dates=["2025-01-02"],
            engine_factory=lambda: _RecordingEngine([]),
            minimum_history=1,
            oos_start="2027-01-01",
        )


def test_regime_hypothesis_keeps_structural_tail_rejections():
    remaining = _remaining_rejects_after_regime(
        reject_reasons=[
            "TAIL_VOLUME_NOT_DRY",
            "TAIL_CLOSE_RANGE_GT_8PCT",
            "BIG_DOWN_VOLUME",
            "TAIL_NEW_LOW",
            "TAIL_LOW_DECLINING",
            "TAIL_RETURN_5_TOO_WEAK",
            "TAIL_SINGLE_DROP_TOO_WEAK",
            "OBJECTIVE_RR_TOO_LOW",
        ],
        dry_tail_rejects=[
            "TAIL_VOLUME_NOT_DRY",
            "TAIL_CLOSE_RANGE_GT_8PCT",
            "BIG_DOWN_VOLUME",
            "TAIL_NEW_LOW",
            "TAIL_LOW_DECLINING",
            "TAIL_RETURN_5_TOO_WEAK",
            "TAIL_SINGLE_DROP_TOO_WEAK",
        ],
    )

    assert remaining == [
        "BIG_DOWN_VOLUME",
        "TAIL_NEW_LOW",
        "TAIL_LOW_DECLINING",
        "TAIL_RETURN_5_TOO_WEAK",
        "TAIL_SINGLE_DROP_TOO_WEAK",
        "OBJECTIVE_RR_TOO_LOW",
    ]


def test_train_metrics_exclude_trades_that_close_in_validation_period():
    train, validation, cross_period = _partition_closed_trades([
        {
            "signal_date": "2024-12-30",
            "entry_date": "2024-12-31",
            "exit_date": "2025-01-03",
        },
        {
            "signal_date": "2024-12-20",
            "entry_date": "2024-12-23",
            "exit_date": "2024-12-30",
        },
        {
            "signal_date": "2025-01-06",
            "entry_date": "2025-01-07",
            "exit_date": "2025-01-10",
        },
    ])

    assert len(train) == 1
    assert len(validation) == 1
    assert len(cross_period) == 1
    assert cross_period[0]["exit_date"] == "2025-01-03"


def test_stress_metrics_exclude_cross_period_trades():
    valid_loss = {
        "signal_date": "2024-12-20",
        "exit_date": "2024-12-30",
        "r_multiple": -1.0,
        "net_return": -0.01,
        "net_profit": -100.0,
    }
    cross_period_win = {
        "signal_date": "2024-12-30",
        "exit_date": "2025-01-03",
        "r_multiple": 10.0,
        "net_return": 0.10,
        "net_profit": 1_000.0,
    }
    raw = {
        name: {
            "status": "COMPLETED",
            "orders": 2,
            "trades": [valid_loss, cross_period_win],
            "metrics": {"trades": 2, "expectancy_r": 4.5, "profit_factor": 10.0},
        }
        for name in ("BASE", "HIGH_COST", "LOW_FILL", "ONE_DAY_DELAY")
    }

    filtered = _filter_stress_results_for_research_periods(raw)

    assert filtered["BASE"]["metrics"]["trades"] == 1
    assert filtered["BASE"]["metrics"]["expectancy_r"] == -1.0
    assert filtered["BASE"]["cross_period_trade_count"] == 1


def test_replay_skips_dates_before_fixed_2023_research_start():
    calls: list[tuple[str, str]] = []

    result = replay_tail_regime_labels(
        data_by_code={
            "BOTH": {"name": "样本", "rows": _rows("2022-12-30", "2023-01-03")},
        },
        evaluation_dates=["2022-12-30", "2023-01-03"],
        market_data_by_symbol=_market_rows("2023-01-03"),
        reference_market_dates=["2023-01-03"],
        engine_factory=lambda: _RecordingEngine(calls),
        minimum_history=1,
    )

    assert calls == [("BOTH", "2023-01-03")]
    assert result["pre_research_date_count"] == 1

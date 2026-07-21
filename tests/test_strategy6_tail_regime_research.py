from __future__ import annotations

from types import SimpleNamespace

import pytest

from strategy6.backtest.tail_regime_research import (
    _research_gate,
    classify_tail_regime_group,
    replay_tail_regime_labels,
    run_tail_regime_research,
)


class _RecordingEngine:
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
        market_data_by_symbol={"sh000001": _rows("2025-12-30", "2025-12-31", "2026-01-02")},
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
        market_data_by_symbol={"sh000001": _rows("2025-01-02", "2025-01-03")},
        engine_factory=MarketRecordingEngine,
        minimum_history=1,
        oos_start="2026-01-01",
    )

    assert observed_market_dates == [["2025-01-02"]]


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

    gate = _research_gate(
        regime_trades("2024") + fixed_losses,
        regime_trades("2025") + fixed_losses,
    )

    assert gate["status"] == "PASS"
    assert gate["regime_only_closed_trades"] == 30


def test_research_rejects_non_formal_decision_profile():
    class ResearchProfileEngine(_RecordingEngine):
        config = {"decision_profile": "research_quality_v2"}

    with pytest.raises(ValueError, match="formal_original"):
        run_tail_regime_research(
            parameter_set_id="s6ps-test",
            data_by_code={"BOTH": {"name": "样本", "rows": _rows("2025-01-02")}},
            evaluation_dates=["2025-01-02"],
            market_data_by_symbol={"sh000001": _rows("2025-01-02", "2025-01-03")},
            backtest_config={},
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
        market_data_by_symbol={"sh000001": _rows("2025-01-02", "2025-01-03")},
        backtest_config={},
        engine_factory=WaitingEngine,
        minimum_history=1,
    )

    assert result["signals"] == []
    assert result["orders"] == []

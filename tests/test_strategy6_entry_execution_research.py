from strategy6.backtest.config import resolve_backtest_config
from strategy6.backtest.entry_execution_research import (
    evaluate_entry_execution_trials,
    rebuild_frozen_entry_archetypes,
)
from strategy6.backtest.models import BacktestSignal


def _signal(date: str, setup_id: str) -> BacktestSignal:
    return BacktestSignal(
        parameter_set_id="p",
        code="000001",
        name="样本",
        evaluation_date=date,
        setup_id=setup_id,
        tail_path="BOX",
        candidate_type="KEY_CANDIDATE",
        snapshot={
            "code": "000001",
            "start_date": "2025-01-01",
            "decision_profile": "formal_original",
            "tail_path": "BOX",
            "entry_archetype": "SUPPORT_PULLBACK",
            "buy_zone_low": 9.8,
            "buy_zone_high": 10.2,
            "suggested_limit_price": 10.0,
            "stop_loss_price": 9.5,
            "objective_target_2": 11.5,
        },
    )


def test_entry_execution_trials_isolate_first_event_and_archetype_dimensions():
    signals = [_signal("2025-01-02", "setup-a"), _signal("2025-01-03", "setup-b")]
    rows = [
        {"date": "2025-01-02", "open": 10, "high": 10.2, "low": 9.8, "close": 10, "volume": 1000},
        {"date": "2025-01-03", "open": 10.5, "high": 10.6, "low": 10.3, "close": 10.4, "volume": 1000},
        {"date": "2025-01-04", "open": 10.0, "high": 10.2, "low": 9.8, "close": 10, "volume": 1000},
        {"date": "2025-01-05", "open": 11.5, "high": 11.6, "low": 11.4, "close": 11.5, "volume": 1000},
    ]

    results = evaluate_entry_execution_trials(
        signals,
        load_rows=lambda code: rows,
        market_dates=[row["date"] for row in rows],
        base_config=resolve_backtest_config({"execution": {"buy_zone_valid_days": 2}}),
        train_end="2024-12-31",
        validation_end="2025-12-31",
    )
    by_id = {item["experiment_id"]: item for item in results}

    assert by_id["S6_EXEC_E0_LEGACY"]["orders_count"] == 2
    assert by_id["S6_EXEC_E1_FIRST_EVENT"]["orders_count"] == 1
    assert by_id["S6_EXEC_E2_ARCHETYPE"]["orders_count"] == 2
    assert by_id["S6_EXEC_E3_COMBINED"]["orders_count"] == 1
    assert by_id["S6_EXEC_E3_COMBINED"]["orders"][0]["candidate_event_id"].startswith("s6event-")
    assert by_id["S6_EXEC_E3_COMBINED"]["orders"][0]["entry_mode"] == "ARCHETYPE_TRIGGERED"


def test_entry_execution_trial_gate_requires_both_periods_and_minimum_validation_trades():
    results = evaluate_entry_execution_trials(
        [], load_rows=lambda code: [], market_dates=[], base_config=resolve_backtest_config({}),
        train_end="2024-12-31", validation_end="2025-12-31",
    )

    assert all(item["gate"]["passed"] is False for item in results)
    assert all("TRAIN_EXPECTANCY_NOT_POSITIVE" in item["gate"]["reasons"] for item in results)
    assert all("VALIDATION_TRADES_LT_30" in item["gate"]["reasons"] for item in results)


def test_entry_archetype_rebuild_is_as_of_and_only_enriches_execution_identity():
    signal = _signal("2025-01-03", "setup-a")
    signal.snapshot.pop("entry_archetype")
    rows = [
        {"date": "2025-01-02", "close": 10},
        {"date": "2025-01-03", "close": 10},
        {"date": "2025-01-04", "close": 99},
    ]
    market = {"hs300": list(rows)}

    class Evaluation:
        def to_candidate_dict(self):
            return {
                "entry_archetype": "PIVOT_BREAKOUT",
                "brooks_trigger_price": 10.4,
                "decision_profile": "formal_original",
                "buy_zone_low": 1.0,
            }

    class Engine:
        def __init__(self):
            self.last_stock_date = ""
            self.last_market_date = ""

        def evaluate_at(self, visible_rows, **kwargs):
            self.last_stock_date = visible_rows[-1]["date"]
            self.last_market_date = kwargs["market_data_by_symbol"]["hs300"][-1]["date"]
            return Evaluation()

    engine = Engine()
    result = rebuild_frozen_entry_archetypes(
        [signal], stock_rows_by_code={"000001": rows}, market_data_by_symbol=market,
        engine=engine, minimum_history=1,
    )

    assert result["failed"] == []
    assert engine.last_stock_date == "2025-01-03"
    assert engine.last_market_date == "2025-01-03"
    assert result["signals"][0].snapshot["entry_archetype"] == "PIVOT_BREAKOUT"
    assert result["signals"][0].snapshot["brooks_trigger_price"] == 10.4
    assert result["signals"][0].snapshot["buy_zone_low"] == 9.8

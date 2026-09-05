import copy

from strategy6.backtest.config import resolve_backtest_config
from strategy6.backtest.execution import ExecutionOutcome
from strategy6.backtest.models import BacktestOrder, BacktestSignal, BacktestTrade
from strategy6.backtest.service import run_parameter_research
from strategy6.backtest.runner import (
    _evaluate_stock_payload,
    _initialize_stock_worker,
    _stock_result_validation_error,
    _is_research_run_complete,
    resolve_run_completion_status,
)


def _rows():
    rows = []
    for day in range(1, 10):
        rows.append({
            "date": f"2025-01-{day:02d}", "open": 10.0,
            "high": 11.6 if day == 8 else 10.2,
            "low": 9.8, "close": 10.0, "volume": 1000,
        })
    return rows


class FakeEvaluation:
    def __init__(self, date):
        self.date = date

    def to_candidate_dict(self):
        return {
            "code": "000001", "name": "样本", "evaluation_date": self.date,
            "candidate_type": "KEY_CANDIDATE", "total_score": 88,
            "tail_path": "BOX", "tail_pass": True,
            "original_tail_pass": False, "original_tail_score": 10,
            "box_tail_pass": True, "box_tail_score": 18, "tail_score": 18,
            "start_date": "2025-01-01", "pattern_type": "VCP", "pivot_price": 10.5,
            "box_start_date": "2025-01-02", "box_end_date": self.date,
            "box_status": "BOX_SUPPORT_READY", "compact_kline_pass": True,
            "entry_archetype": "SUPPORT_PULLBACK", "setup_quality_score": 21,
            "support_reaction_score": 8, "start_event_quality_score": 17,
            "path_evidence_score": 13, "score_model_version": "S6_QUALITY_V2",
            "buy_zone_low": 9.8, "buy_zone_high": 10.2, "suggested_limit_price": 10.0,
            "stop_loss_price": 9.5, "objective_target_2": 11.5,
        }


class FakeEngine:
    def evaluate_at(self, rows, **kwargs):
        return FakeEvaluation(rows[-1]["date"])


def test_service_keeps_daily_signals_but_only_one_order_per_setup_and_skips_oos():
    result = run_parameter_research(
        parameter_set_id="s6ps-test",
        data_by_code={"000001": {"name": "样本", "rows": _rows()}},
        evaluation_dates=["2025-01-03", "2025-01-04", "2026-01-02"],
        market_data_by_symbol={"hs300": _rows(), "sh000001": _rows()},
        backtest_config=resolve_backtest_config({"execution": {"buy_zone_valid_days": 3}}),
        engine_factory=lambda: FakeEngine(),
        minimum_history=1,
        oos_start="2026-01-01",
    )
    assert len(result["signals"]) == 2
    assert len(result["orders"]) == 1
    assert len(result["trades"]) == 1
    assert result["trades"][0]["tail_path"] == "BOX"
    assert result["trades"][0]["entry_archetype"] == "SUPPORT_PULLBACK"
    assert result["entry_archetype_metrics"]["SUPPORT_PULLBACK"]["trades"] == 1
    assert result["setup_quality_metrics"]["20-24"]["trades"] == 1


def test_first_event_selection_executes_once_when_setup_id_changes_within_same_start_cycle():
    class RollingSetupEvaluation(FakeEvaluation):
        def to_candidate_dict(self):
            return {
                **super().to_candidate_dict(),
                "pivot_price": 10.5 if self.date == "2025-01-03" else 10.7,
                "box_start_date": "2025-01-01" if self.date == "2025-01-03" else "2025-01-02",
            }

    class RollingSetupEngine:
        def evaluate_at(self, rows, **kwargs):
            return RollingSetupEvaluation(rows[-1]["date"])

    result = run_parameter_research(
        parameter_set_id="s6ps-first-event",
        data_by_code={"000001": {"name": "样本", "rows": _rows()}},
        evaluation_dates=["2025-01-03", "2025-01-04"],
        market_data_by_symbol={"hs300": _rows(), "sh000001": _rows()},
        backtest_config=resolve_backtest_config({
            "signal_selection_mode": "FIRST_EVENT_PER_START",
            "execution": {"buy_zone_valid_days": 3},
        }),
        engine_factory=lambda: RollingSetupEngine(), minimum_history=1, oos_start="2026-01-01",
    )

    assert len({item["setup_id"] for item in result["signals"]}) == 2
    assert len({item["candidate_event_id"] for item in result["signals"]}) == 1
    assert len(result["orders"]) == 1
    assert result["orders"][0]["signal_selection_mode"] == "FIRST_EVENT_PER_START"
    assert result["orders"][0]["candidate_event_sequence"] == 1


def test_service_keeps_wait_breakout_signal_without_creating_order():
    class WaitingEvaluation(FakeEvaluation):
        def to_candidate_dict(self):
            return {
                **super().to_candidate_dict(),
                "candidate_type": "WATCH_CANDIDATE",
                "entry_archetype": "WAIT_BREAKOUT",
                "suggested_limit_price": None,
            }

    class WaitingEngine:
        def evaluate_at(self, rows, **kwargs):
            return WaitingEvaluation(rows[-1]["date"])

    result = run_parameter_research(
        parameter_set_id="s6ps-wait",
        data_by_code={"000001": {"name": "样本", "rows": _rows()}},
        evaluation_dates=["2025-01-03"],
        market_data_by_symbol={"hs300": _rows()},
        backtest_config=resolve_backtest_config({}),
        engine_factory=lambda: WaitingEngine(), minimum_history=1, oos_start="2026-01-01",
    )

    assert len(result["signals"]) == 1
    assert result["signals"][0]["entry_archetype"] == "WAIT_BREAKOUT"
    assert result["orders"] == []
    assert result["trades"] == []


def test_brooks_only_watch_signal_does_not_consume_setup_before_cross_day_trade_trigger():
    class CrossDayEvaluation:
        def __init__(self, date):
            self.date = date

        def to_candidate_dict(self):
            ready = self.date >= "2025-01-04"
            return {
                "code": "000001", "name": "样本", "evaluation_date": self.date,
                "candidate_type": "KEY_CANDIDATE" if ready else "WATCH_CANDIDATE",
                "total_score": 88, "tail_path": "NONE", "tail_paths": ["BROOKS"],
                "tail_path_summary": "BROOKS", "tail_primary_path": "BROOKS",
                "passed_path_count": 1, "tail_pass": True,
                "original_tail_pass": False, "box_tail_pass": False,
                "brooks_tail_pass": True,
                "brooks_status": "BROOKS_SUPPORT_READY" if ready else "SECOND_ENTRY_LONG_READY",
                "brooks_trade_ready": ready,
                "brooks_result": {"structure": {
                    "setup_types": ["SECOND_ENTRY_LONG_READY"],
                    "first_recent_low_date": "2025-01-01",
                    "second_recent_low_date": "2025-01-02",
                    "second_entry_signal_date": "2025-01-03",
                }},
                "start_date": "2025-01-01", "pattern_type": "VCP", "pivot_price": 10.5,
                "buy_zone_low": 9.8, "buy_zone_high": 10.2, "suggested_limit_price": 10.0,
                "stop_loss_price": 9.5, "objective_target_2": 11.5,
            }

    class CrossDayEngine:
        def evaluate_at(self, rows, **kwargs):
            return CrossDayEvaluation(rows[-1]["date"])

    result = run_parameter_research(
        parameter_set_id="s6ps-brooks-cross-day",
        data_by_code={"000001": {"name": "样本", "rows": _rows()}},
        evaluation_dates=["2025-01-03", "2025-01-04"],
        market_data_by_symbol={"hs300": _rows(), "sh000001": _rows()},
        backtest_config=resolve_backtest_config({"execution": {"buy_zone_valid_days": 3}}),
        engine_factory=lambda: CrossDayEngine(), minimum_history=1, oos_start="2026-01-01",
    )

    assert [item["brooks_trade_ready"] for item in result["signals"]] == [False, True]
    assert len(result["orders"]) == 1
    assert result["orders"][0]["signal_date"] == "2025-01-04"
    assert result["orders"][0]["tail_path"] == "NONE"
    assert result["orders"][0]["tail_paths"] == ["BROOKS"]


def test_brooks_only_scope_excludes_original_and_multi_path_signals_before_execution():
    class ScopedEvaluation:
        def __init__(self, date):
            self.date = date

        def to_candidate_dict(self):
            date = self.date
            if date.endswith("01"):
                paths = ["ORIGINAL"]
            elif date.endswith("02"):
                paths = ["ORIGINAL", "BROOKS"]
            else:
                paths = ["BROOKS"]
            return {
                "code": "000001", "name": "样本", "evaluation_date": date,
                "candidate_type": "KEY_CANDIDATE", "total_score": 88,
                "tail_path": "NONE", "tail_paths": paths,
                "tail_path_summary": "MULTI" if len(paths) > 1 else paths[0],
                "tail_primary_path": paths[-1], "passed_path_count": len(paths),
                "tail_pass": True, "original_tail_pass": "ORIGINAL" in paths,
                "box_tail_pass": False, "brooks_tail_pass": "BROOKS" in paths,
                "brooks_trade_ready": "BROOKS" in paths,
                "brooks_status": "BROOKS_SUPPORT_READY",
                "brooks_result": {"structure": {"setup_types": ["MICRO_DOUBLE_BOTTOM"]}},
                "start_date": "2024-12-01", "pattern_type": "VCP", "pivot_price": 10.5,
                "buy_zone_low": 9.8, "buy_zone_high": 10.2,
                "suggested_limit_price": 10.0, "stop_loss_price": 9.5,
                "objective_target_2": 11.5,
            }

    class ScopedEngine:
        def evaluate_at(self, rows, **kwargs):
            return ScopedEvaluation(rows[-1]["date"])

    dates = ["2025-01-01", "2025-01-02", "2025-01-03"]
    result = run_parameter_research(
        parameter_set_id="s6ps-brooks-only-scope",
        data_by_code={"000001": {"name": "样本", "rows": _rows()}},
        evaluation_dates=dates,
        market_data_by_symbol={"sh000001": _rows()},
        backtest_config=resolve_backtest_config({}),
        engine_factory=lambda: ScopedEngine(),
        minimum_history=1,
        oos_start="2026-01-01",
        signal_scope="BROOKS_ONLY",
    )

    assert [item["evaluation_date"] for item in result["signals"]] == ["2025-01-03"]
    assert all(item["tail_paths"] == ["BROOKS"] for item in result["signals"])
    assert all(item["tail_paths"] == ["BROOKS"] for item in result["orders"])
    assert all(item["tail_paths"] == ["BROOKS"] for item in result["trades"])


def test_brooks_path_scope_includes_overlap_but_requires_its_own_trade_trigger():
    snapshots = [
        {
            "evaluation_date": "2025-01-01", "tail_paths": ["ORIGINAL"],
            "brooks_trade_ready": False,
        },
        {
            "evaluation_date": "2025-01-02", "tail_paths": ["ORIGINAL", "BROOKS"],
            "brooks_trade_ready": False,
        },
        {
            "evaluation_date": "2025-01-03", "tail_paths": ["ORIGINAL", "BROOKS"],
            "brooks_trade_ready": True,
        },
    ]

    class Evaluation:
        def __init__(self, snapshot):
            self.snapshot = snapshot

        def to_candidate_dict(self):
            paths = self.snapshot["tail_paths"]
            return {
                "code": "000001", "name": "样本",
                "candidate_type": "KEY_CANDIDATE", "total_score": 88,
                "tail_path": "NONE", "tail_paths": paths,
                "original_tail_pass": "ORIGINAL" in paths, "box_tail_pass": False,
                "brooks_tail_pass": "BROOKS" in paths,
                "brooks_trade_ready": self.snapshot["brooks_trade_ready"],
                "brooks_status": "BROOKS_SUPPORT_READY",
                "brooks_result": {"structure": {"setup_types": ["MICRO_DOUBLE_BOTTOM"]}},
                "start_date": self.snapshot["evaluation_date"], "pattern_type": "VCP",
                "pivot_price": 10.5, "buy_zone_low": 9.8, "buy_zone_high": 10.2,
                "suggested_limit_price": 10.0, "stop_loss_price": 9.5,
                "objective_target_2": 11.5,
            }

    class Engine:
        def evaluate_at(self, rows, **kwargs):
            date = rows[-1]["date"]
            return Evaluation(next(item for item in snapshots if item["evaluation_date"] == date))

    result = run_parameter_research(
        parameter_set_id="s6ps-brooks-path-scope",
        data_by_code={"000001": {"name": "样本", "rows": _rows()}},
        evaluation_dates=[item["evaluation_date"] for item in snapshots],
        market_data_by_symbol={"sh000001": _rows()},
        backtest_config=resolve_backtest_config({}), engine_factory=lambda: Engine(),
        minimum_history=1, oos_start="2026-01-01", signal_scope="BROOKS_PATH",
    )

    assert [item["evaluation_date"] for item in result["signals"]] == ["2025-01-02", "2025-01-03"]
    assert [item["signal_date"] for item in result["orders"]] == ["2025-01-03"]


def test_service_group_metrics_use_only_closed_trades(monkeypatch):
    snapshot = {
        "tail_path": "BOTH", "tail_paths": ["ORIGINAL", "BOX", "BROOKS"],
        "tail_primary_path": "BROOKS", "tail_path_summary": "MULTI",
        "original_tail_pass": True, "box_tail_pass": True, "brooks_tail_pass": True,
        "brooks_trade_ready": True, "brooks_status": "BROOKS_SUPPORT_READY",
        "brooks_setup_types": ["MICRO_DOUBLE_BOTTOM"],
    }
    signals = [
        BacktestSignal(
            parameter_set_id="p", code="000001", name="样本", evaluation_date="2025-01-03",
            setup_id="closed", tail_path="BOTH", candidate_type="KEY_CANDIDATE", snapshot=snapshot,
        ),
        BacktestSignal(
            parameter_set_id="p", code="000001", name="样本", evaluation_date="2025-01-04",
            setup_id="unresolved", tail_path="BOTH", candidate_type="KEY_CANDIDATE", snapshot=snapshot,
        ),
    ]
    monkeypatch.setattr("strategy6.backtest.service.rebuild_stock_signals", lambda **kwargs: signals)

    def simulate(signal, stock_rows, market_dates, config):
        order = BacktestOrder(
            order_id=f"order-{signal.setup_id}", signal=signal,
            created_date=signal.evaluation_date, expire_date="2025-01-10", status="FILLED",
        )
        trade = BacktestTrade(
            trade_id=f"trade-{signal.setup_id}", code=signal.code,
            signal_date=signal.evaluation_date, entry_date="2025-01-06", entry_price=10.0,
            exit_date="2025-01-10" if signal.setup_id == "closed" else "",
            exit_price=11.0 if signal.setup_id == "closed" else 0.0,
            net_return=0.1 if signal.setup_id == "closed" else 0.0,
            r_multiple=2.0 if signal.setup_id == "closed" else 0.0,
        )
        return ExecutionOutcome(order=order, trade=trade)

    monkeypatch.setattr("strategy6.backtest.service.simulate_frozen_trade", simulate)
    result = run_parameter_research(
        parameter_set_id="p", data_by_code={"000001": {"name": "样本", "rows": _rows()}},
        evaluation_dates=["2025-01-03", "2025-01-04"],
        market_data_by_symbol={"hs300": _rows()}, backtest_config=resolve_backtest_config({}),
        engine_factory=lambda: FakeEngine(), minimum_history=1, oos_start="2026-01-01",
    )

    assert len(result["trades"]) == 2
    assert result["summary"]["trades"] == 1
    assert result["path_metrics"]["BOTH"]["trades"] == 1
    assert result["authoritative_path_metrics"]["BROOKS"]["trades"] == 1
    assert result["tail_primary_path_metrics"]["BROOKS"]["trades"] == 1
    assert result["tail_path_summary_metrics"]["MULTI"]["trades"] == 1
    assert result["brooks_status_metrics"]["BROOKS_SUPPORT_READY"]["trades"] == 1
    assert result["brooks_structure_metrics"]["MICRO_DOUBLE_BOTTOM"]["trades"] == 1


def test_service_does_not_mutate_strategy_or_backtest_config():
    strategy_config = {"box_tail": {"enabled": False}}
    backtest_config = resolve_backtest_config({})
    before_strategy = copy.deepcopy(strategy_config)
    before_backtest = copy.deepcopy(backtest_config)
    run_parameter_research(
        parameter_set_id="s6ps-test", data_by_code={}, evaluation_dates=[],
        market_data_by_symbol={}, backtest_config=backtest_config,
        engine_factory=lambda: FakeEngine(), minimum_history=1, oos_start="2026-01-01",
    )
    assert strategy_config == before_strategy
    assert backtest_config == before_backtest


def test_run_with_any_failed_stock_is_not_marked_clean_completed():
    assert resolve_run_completion_status(total=100, completed=100, skipped=0, failed=0) == "COMPLETED"
    assert resolve_run_completion_status(total=100, completed=99, skipped=0, failed=1) == "COMPLETED_WITH_ERRORS"
    assert resolve_run_completion_status(total=100, completed=90, skipped=10, failed=0) == "COMPLETED_WITH_SKIPS"
    assert resolve_run_completion_status(total=100, completed=90, skipped=0, failed=0) == "INCOMPLETE"
    assert _is_research_run_complete("COMPLETED") is True
    assert _is_research_run_complete("COMPLETED_WITH_SKIPS") is True
    assert _is_research_run_complete("COMPLETED_WITH_ERRORS") is False


def test_process_worker_evaluates_raw_stock_rows_without_database_access():
    _initialize_stock_worker({
        "parameter_set_id": "s6ps-worker",
        "evaluation_dates": ["2025-01-03"],
        "market_data_by_symbol": {},
        "backtest_config": resolve_backtest_config({}),
        "strategy_config": {"enable_market_filter": False},
        "minimum_history": 1,
        "oos_start": "2026-01-01",
    })

    result = _evaluate_stock_payload({"code": "000001", "name": "样本", "rows": _rows()})

    assert result["code"] == "000001"
    assert result["status"] == "COMPLETED"
    assert set(result["result"]) >= {"signals", "orders", "trades"}


def test_worker_result_validation_reports_duplicate_signal_dates():
    error = _stock_result_validation_error("000001", {
        "signals": [
            {"code": "000001", "evaluation_date": "2025-01-03", "setup_id": "a"},
            {"code": "000001", "evaluation_date": "2025-01-03", "setup_id": "b"},
        ]
    })
    assert "DUPLICATE_SIGNAL_DATE" in error
    assert "2025-01-03" in error

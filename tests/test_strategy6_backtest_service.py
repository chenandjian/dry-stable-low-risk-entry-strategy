import copy

from strategy6.backtest.config import resolve_backtest_config
from strategy6.backtest.service import run_parameter_research
from strategy6.backtest.runner import resolve_run_completion_status


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

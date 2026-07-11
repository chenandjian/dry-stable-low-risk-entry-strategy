from strategy6.backtest.snapshot import build_setup_id, rebuild_stock_signals
from strategy6.engine import StrongVcpTailEngine


class FakeEvaluation:
    def __init__(self, date, tail_path="BOX", box_score=18):
        self._candidate = {
            "code": "000001",
            "name": "样本",
            "evaluation_date": date,
            "candidate_type": "KEY_CANDIDATE",
            "tail_path": tail_path,
            "tail_pass": True,
            "original_tail_pass": tail_path in {"ORIGINAL", "BOTH"},
            "original_tail_score": 16,
            "box_tail_pass": tail_path in {"BOX", "BOTH"},
            "box_tail_score": box_score,
            "tail_score": max(16, box_score) if tail_path == "BOTH" else box_score,
            "start_date": "2025-01-01",
            "pattern_type": "VCP",
            "pivot_price": 10.5,
            "box_start_date": "2025-01-03",
            "box_end_date": date,
        }

    def to_candidate_dict(self):
        return dict(self._candidate)


class CapturingEngine:
    def __init__(self):
        self.calls = []

    def evaluate_at(self, rows, **kwargs):
        market = kwargs["market_data_by_symbol"]
        self.calls.append((rows[-1]["date"], max(row["date"] for values in market.values() for row in values)))
        return FakeEvaluation(rows[-1]["date"])


def _rows():
    return [
        {"date": f"2025-01-{day:02d}", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100}
        for day in range(1, 8)
    ]


def test_asof_rebuild_never_passes_future_stock_or_market_rows():
    engine = CapturingEngine()
    market = {"hs300": _rows(), "sh000001": _rows()}
    signals = rebuild_stock_signals(
        code="000001",
        name="样本",
        rows=_rows(),
        evaluation_dates=["2025-01-05", "2025-01-06"],
        market_data_by_symbol=market,
        parameter_set_id="s6ps-a",
        engine=engine,
        minimum_history=1,
    )
    assert engine.calls == [("2025-01-05", "2025-01-05"), ("2025-01-06", "2025-01-06")]
    assert [signal.evaluation_date for signal in signals] == ["2025-01-05", "2025-01-06"]


def test_setup_id_is_stable_but_parameter_set_keeps_snapshots_independent():
    snapshot = FakeEvaluation("2025-01-05").to_candidate_dict()
    assert build_setup_id(snapshot) == build_setup_id(dict(snapshot))
    first = rebuild_stock_signals(
        code="000001", name="样本", rows=_rows(), evaluation_dates=["2025-01-05"],
        market_data_by_symbol={"hs300": _rows()}, parameter_set_id="s6ps-a",
        engine=CapturingEngine(), minimum_history=1,
    )[0]
    second = rebuild_stock_signals(
        code="000001", name="样本", rows=_rows(), evaluation_dates=["2025-01-05"],
        market_data_by_symbol={"hs300": _rows()}, parameter_set_id="s6ps-b",
        engine=CapturingEngine(), minimum_history=1,
    )[0]
    assert first.setup_id == second.setup_id
    assert first.parameter_set_id != second.parameter_set_id


def test_failed_box_never_raises_original_path_score_in_snapshot():
    class OriginalEngine(CapturingEngine):
        def evaluate_at(self, rows, **kwargs):
            result = FakeEvaluation(rows[-1]["date"], tail_path="ORIGINAL", box_score=19)
            result._candidate.update({
                "box_tail_pass": False,
                "tail_score": 16,
            })
            return result

    signal = rebuild_stock_signals(
        code="000001", name="样本", rows=_rows(), evaluation_dates=["2025-01-05"],
        market_data_by_symbol={"hs300": _rows()}, parameter_set_id="s6ps-a",
        engine=OriginalEngine(), minimum_history=1,
    )[0]
    assert signal.snapshot["tail_score"] == signal.snapshot["original_tail_score"] == 16


def test_asof_rebuild_normalizes_raw_database_rows_before_real_engine_evaluation():
    from tests.test_strategy6_core_rules import build_strategy6_candidate_data

    rows = build_strategy6_candidate_data()
    raw_rows = [
        {
            "date": row["date"],
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": row["volume"],
            "turnover": row.get("amount", 0),
        }
        for row in rows
    ]
    evaluation_date = raw_rows[-1]["date"]

    rebuild_stock_signals(
        code="000001",
        name="样本",
        rows=raw_rows,
        evaluation_dates=[evaluation_date],
        market_data_by_symbol={},
        parameter_set_id="s6ps-raw-db",
        engine=StrongVcpTailEngine({"strategy6": {"enable_market_filter": False}}),
        minimum_history=1,
    )

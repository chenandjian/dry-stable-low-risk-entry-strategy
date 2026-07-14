from strategy6.backtest.snapshot import build_setup_id, rebuild_stock_signals
from strategy6.engine import StrongVcpTailEngine


class FakeEvaluation:
    def __init__(self, date, tail_path="BOX", box_score=18, **overrides):
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
        self._candidate.update(overrides)

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
    assert build_setup_id(snapshot) == "s6setup-098716efbee10b7d82fb"
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


def test_brooks_setup_id_uses_visible_structure_anchors_without_changing_legacy_identity():
    legacy = FakeEvaluation("2025-01-05").to_candidate_dict()
    brooks = {
        **legacy,
        "tail_path": "NONE",
        "tail_paths": ["BROOKS"],
        "brooks_result": {
            "structure": {
                "setup_types": ["MICRO_DOUBLE_BOTTOM"],
                "first_recent_low_date": "2025-01-02",
                "second_recent_low_date": "2025-01-04",
                "second_entry_signal_date": "2025-01-05",
            }
        },
    }
    later_structure = {
        **brooks,
        "brooks_result": {
            "structure": {
                **brooks["brooks_result"]["structure"],
                "second_recent_low_date": "2025-01-05",
            }
        },
    }

    assert build_setup_id(legacy) == "s6setup-098716efbee10b7d82fb"
    assert build_setup_id(brooks) != build_setup_id(legacy)
    assert build_setup_id(brooks) != build_setup_id(later_structure)


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


def test_asof_rebuild_does_not_repeat_last_signal_when_stock_has_no_bar_on_market_date():
    engine = CapturingEngine()
    signals = rebuild_stock_signals(
        code="000001",
        name="样本",
        rows=_rows()[:5],
        evaluation_dates=["2025-01-05", "2025-01-06"],
        market_data_by_symbol={"hs300": _rows()},
        parameter_set_id="s6ps-no-bar",
        engine=engine,
        minimum_history=1,
    )

    assert [signal.evaluation_date for signal in signals] == ["2025-01-05"]
    assert [call[0] for call in engine.calls] == ["2025-01-05"]


def test_brooks_only_snapshot_is_kept_without_extending_legacy_tail_path_enum():
    class BrooksOnlyEngine(CapturingEngine):
        def evaluate_at(self, rows, **kwargs):
            return FakeEvaluation(
                rows[-1]["date"],
                tail_path="NONE",
                tail_paths=["BROOKS"],
                tail_path_summary="BROOKS",
                tail_primary_path="BROOKS",
                passed_path_count=1,
                brooks_tail_pass=True,
                brooks_status="MICRO_DOUBLE_BOTTOM",
            )

    signals = rebuild_stock_signals(
        code="000001", name="样本", rows=_rows(), evaluation_dates=["2025-01-05"],
        market_data_by_symbol={"hs300": _rows()}, parameter_set_id="s6ps-brooks",
        engine=BrooksOnlyEngine(), minimum_history=1,
    )

    assert len(signals) == 1
    assert signals[0].tail_path == "NONE"
    assert signals[0].snapshot["tail_paths"] == ["BROOKS"]


def test_asof_brooks_trigger_waits_for_next_visible_session_and_ignores_future_bar():
    class CrossDayBrooksEngine:
        def evaluate_at(self, rows, **kwargs):
            triggered = any(
                row["date"] > "2025-01-05" and float(row["high"]) > 10.5
                for row in rows
            )
            return FakeEvaluation(
                rows[-1]["date"],
                tail_path="NONE",
                candidate_type="KEY_CANDIDATE" if triggered else "WATCH_CANDIDATE",
                tail_paths=["BROOKS"],
                tail_path_summary="BROOKS",
                tail_primary_path="BROOKS",
                passed_path_count=1,
                brooks_tail_pass=True,
                brooks_status="SECOND_ENTRY_LONG_READY",
                brooks_trade_ready=triggered,
                brooks_result={
                    "structure": {
                        "setup_types": ["SECOND_ENTRY_LONG_READY"],
                        "first_recent_low_date": "2025-01-02",
                        "second_recent_low_date": "2025-01-04",
                        "second_entry_signal_date": "2025-01-05",
                    },
                    "trade_trigger": {"ready": triggered},
                },
            )

    rows = _rows()
    rows[4]["high"] = 10.2
    rows[5]["high"] = 10.6
    rows[6]["high"] = 12.0
    signals = rebuild_stock_signals(
        code="000001", name="样本", rows=rows,
        evaluation_dates=["2025-01-05", "2025-01-06"],
        market_data_by_symbol={"hs300": rows}, parameter_set_id="s6ps-cross-day",
        engine=CrossDayBrooksEngine(), minimum_history=1,
    )

    assert [signal.evaluation_date for signal in signals] == ["2025-01-05", "2025-01-06"]
    assert [signal.snapshot["brooks_trade_ready"] for signal in signals] == [False, True]
    assert [signal.candidate_type for signal in signals] == ["WATCH_CANDIDATE", "KEY_CANDIDATE"]

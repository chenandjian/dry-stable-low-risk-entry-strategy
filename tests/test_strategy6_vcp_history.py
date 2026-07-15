from types import SimpleNamespace


def _rows():
    return [
        {
            "date": f"2026-01-0{day}",
            "open": 10.0,
            "high": 10.2,
            "low": 9.8,
            "close": 10.0,
            "volume": 1_000_000,
        }
        for day in range(1, 6)
    ]


class _FakeEngine:
    def __init__(self, formal_by_date, calls):
        self.formal_by_date = formal_by_date
        self.calls = calls

    def evaluate_at(self, rows, *, market_data_by_symbol, **kwargs):
        evaluation_date = rows[-1]["date"]
        market_latest = {
            symbol: values[-1]["date"] if values else ""
            for symbol, values in market_data_by_symbol.items()
        }
        self.calls.append((evaluation_date, market_latest))
        candidate_type, score = self.formal_by_date.get(
            evaluation_date,
            ("REJECTED", 0),
        )
        return SimpleNamespace(
            candidate_type=candidate_type,
            score=SimpleNamespace(total_score=score),
        )


def _evaluate(formal_by_date, *, origin="2026-01-03", current="2026-01-05"):
    from strategy6.vcp_history import evaluate_vcp_candidate_history

    calls = []
    engine = _FakeEngine(formal_by_date, calls)
    result = evaluate_vcp_candidate_history(
        rows=_rows(),
        market_data_by_symbol={"hs300": _rows()},
        strategy_config={"minimum_trading_days": 1},
        code="000001",
        name="测试股票",
        origin_start_date=origin,
        evaluation_date=current,
        engine_factory=lambda config: engine,
    )
    return result, calls


def test_vcp_history_ignores_formal_candidate_before_current_origin():
    result, calls = _evaluate({"2026-01-02": ("WATCH_CANDIDATE", 61)})

    assert result.qualified is False
    assert result.candidate_date == ""
    assert [date for date, _ in calls] == [
        "2026-01-05",
        "2026-01-04",
        "2026-01-03",
    ]


def test_vcp_history_accepts_latest_formal_candidate_inside_current_origin():
    result, calls = _evaluate({"2026-01-04": ("WATCH_CANDIDATE", 63)})

    assert result.qualified is True
    assert result.candidate_date == "2026-01-04"
    assert result.candidate_type == "WATCH_CANDIDATE"
    assert result.candidate_score == 63
    assert result.source == "DAILY_AS_OF_REPLAY"
    assert result.origin_start_date == "2026-01-03"
    assert [date for date, _ in calls] == ["2026-01-05", "2026-01-04"]


def test_vcp_history_accepts_formal_candidate_on_evaluation_date():
    result, calls = _evaluate({"2026-01-05": ("KEY_CANDIDATE", 78)})

    assert result.qualified is True
    assert result.candidate_date == "2026-01-05"
    assert result.candidate_type == "KEY_CANDIDATE"
    assert [date for date, _ in calls] == ["2026-01-05"]


def test_vcp_history_slices_stock_and_market_rows_as_of_each_date():
    result, calls = _evaluate({})

    assert result.qualified is False
    for evaluation_date, market_latest in calls:
        assert market_latest["hs300"] == evaluation_date

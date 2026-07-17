from datetime import date, timedelta
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


def _trend_rows(closes):
    start = date(2026, 1, 1)
    return [
        {
            "date": (start + timedelta(days=index)).isoformat(),
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": 1_000_000,
        }
        for index, close in enumerate(closes)
    ]


def _evaluate_continuity(closes, *, candidate_index, pattern_index):
    from strategy6.vcp_history import evaluate_vcp_candidate_history

    rows = _trend_rows(closes)
    candidate_date = rows[candidate_index]["date"]
    pattern_date = rows[pattern_index]["date"]
    engine = _FakeEngine({candidate_date: ("WATCH_CANDIDATE", 63)}, [])
    return evaluate_vcp_candidate_history(
        rows=rows,
        market_data_by_symbol={},
        strategy_config={
            "minimum_trading_days": 1,
            "vcp_history_max_start_loss_pct": 0.15,
            "vcp_history_max_drawdown_pct": 0.20,
            "vcp_history_bearish_trend_days": 5,
        },
        code="000001",
        name="测试股票",
        origin_start_date=rows[0]["date"],
        evaluation_date=rows[-1]["date"],
        pattern_start_date=pattern_date,
        engine_factory=lambda config: engine,
    )


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


def test_vcp_history_rejects_candidate_that_loses_more_than_15pct_before_pattern_start():
    closes = [10.0] * 60 + [9.7, 9.3, 8.9, 8.5, 8.0] + [8.0] * 10

    result = _evaluate_continuity(closes, candidate_index=59, pattern_index=64)

    assert result.qualified is False


def test_vcp_history_rejects_deep_intermediate_drawdown_even_after_price_recovers():
    closes = [10.0] * 60 + [9.0, 8.4, 7.8, 8.5, 9.2, 9.6] + [9.6] * 10

    result = _evaluate_continuity(closes, candidate_index=59, pattern_index=65)

    assert result.qualified is False


def test_vcp_history_rejects_persistent_bearish_alignment_at_pattern_start():
    closes = [10.0 + index * 0.01 for index in range(60)]
    closes += [10.55 - 0.06 * (index + 1) for index in range(15)]
    closes += [9.65] * 10

    result = _evaluate_continuity(closes, candidate_index=59, pattern_index=74)

    assert result.qualified is False


def test_vcp_history_keeps_healthy_sideways_candidate_qualified():
    closes = [10.0] * 60 + [9.9, 10.1, 9.8, 10.0, 9.9, 10.05] + [10.05] * 10

    result = _evaluate_continuity(closes, candidate_index=59, pattern_index=65)

    assert result.qualified is True


def test_vcp_history_accepts_new_formal_candidate_after_pattern_start():
    closes = [10.0] * 60 + [9.0, 8.5, 8.0, 7.8, 7.7, 7.6] + [7.7] * 10
    rows = _trend_rows(closes)
    pattern_index = 65
    candidate_index = 70
    engine = _FakeEngine({rows[candidate_index]["date"]: ("WATCH_CANDIDATE", 65)}, [])
    from strategy6.vcp_history import evaluate_vcp_candidate_history

    result = evaluate_vcp_candidate_history(
        rows=rows,
        market_data_by_symbol={},
        strategy_config={
            "minimum_trading_days": 1,
            "vcp_history_max_start_loss_pct": 0.15,
            "vcp_history_max_drawdown_pct": 0.20,
            "vcp_history_bearish_trend_days": 5,
        },
        code="000001",
        name="测试股票",
        origin_start_date=rows[0]["date"],
        evaluation_date=rows[-1]["date"],
        pattern_start_date=rows[pattern_index]["date"],
        engine_factory=lambda config: engine,
    )

    assert result.qualified is True
    assert result.candidate_date == rows[candidate_index]["date"]


def test_vcp_history_does_not_use_older_candidate_after_latest_candidate_is_invalidated():
    from strategy6.vcp_history import evaluate_vcp_candidate_history

    closes = [8.0] * 55 + [8.0, 8.5, 9.0, 9.5, 10.0, 9.5, 9.0, 8.7, 8.5, 8.4]
    closes += [8.4] * 10
    rows = _trend_rows(closes)
    older_index = 55
    latest_index = 59
    pattern_index = 64
    engine = _FakeEngine({
        rows[older_index]["date"]: ("WATCH_CANDIDATE", 61),
        rows[latest_index]["date"]: ("WATCH_CANDIDATE", 65),
    }, [])

    result = evaluate_vcp_candidate_history(
        rows=rows,
        market_data_by_symbol={},
        strategy_config={
            "minimum_trading_days": 1,
            "vcp_history_max_start_loss_pct": 0.15,
            "vcp_history_max_drawdown_pct": 0.20,
            "vcp_history_bearish_trend_days": 5,
        },
        code="000001",
        name="测试股票",
        origin_start_date=rows[0]["date"],
        evaluation_date=rows[-1]["date"],
        pattern_start_date=rows[pattern_index]["date"],
        engine_factory=lambda config: engine,
    )

    assert result.qualified is False

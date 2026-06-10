from scanner.backtester import summarize_by_verdict, BacktestResult


def test_summarize_by_verdict_groups_results():
    rows = [
        {"verdict": "可低吸", "ret_10d": 5.0},
        {"verdict": "可低吸", "ret_10d": -1.0},
        {"verdict": "突破确认", "ret_10d": 2.0},
    ]

    result = summarize_by_verdict(rows)

    assert result["可低吸"]["count"] == 2
    assert result["可低吸"]["avg_ret_10d"] == 2.0
    assert result["突破确认"]["count"] == 1


def test_summarize_excludes_none_returns_from_average():
    """ROUND5-001: ret_10d=None must not be treated as 0.0."""
    rows = [
        {"verdict": "可低吸", "ret_10d": 10.0},
        {"verdict": "可低吸", "ret_10d": None},
    ]
    result = summarize_by_verdict(rows)
    assert result["可低吸"]["count"] == 2
    assert result["可低吸"]["observed_10d_count"] == 1
    assert result["可低吸"]["avg_ret_10d"] == 10.0


def test_summarize_real_zero_distinct_from_none():
    """ROUND5-001: Real ret_10d=0.0 must survive, None must be excluded."""
    rows = [
        {"verdict": "可低吸", "ret_10d": 0.0},
        {"verdict": "可低吸", "ret_10d": None},
    ]
    result = summarize_by_verdict(rows)
    assert result["可低吸"]["observed_10d_count"] == 1
    assert result["可低吸"]["avg_ret_10d"] == 0.0


def test_summarize_all_none_returns_none_average():
    """ROUND5-001: When no observable returns, avg_ret_10d must be None, not 0."""
    rows = [
        {"verdict": "可低吸", "ret_10d": None},
        {"verdict": "可低吸", "ret_10d": None},
    ]
    result = summarize_by_verdict(rows)
    assert result["可低吸"]["count"] == 2
    assert result["可低吸"]["observed_10d_count"] == 0
    assert result["可低吸"]["avg_ret_10d"] is None


def test_summarize_works_with_backtest_result_objects():
    """ROUND5-001: Both dict and BacktestResult inputs work correctly."""
    r1 = BacktestResult(verdict="可低吸", ret_10d=5.0)
    r2 = BacktestResult(verdict="可低吸", ret_10d=None)
    result = summarize_by_verdict([r1, r2])
    assert result["可低吸"]["count"] == 2
    assert result["可低吸"]["observed_10d_count"] == 1
    assert result["可低吸"]["avg_ret_10d"] == 5.0

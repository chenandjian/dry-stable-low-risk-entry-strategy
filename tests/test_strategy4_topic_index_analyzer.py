from strategy4.topic_index_analyzer import analyze_topic_index


def _row(idx, close, amount=1000):
    return {
        "date": f"2026-05-{idx + 1:02d}",
        "open": close * 0.99,
        "high": close * 1.02,
        "low": close * 0.98,
        "close": close,
        "amount": amount,
        "volume": amount / 10,
    }


def test_analyze_topic_index_detects_trend_breakout_and_volume():
    closes = [100 + i * 0.8 for i in range(61)]
    rows = [_row(i, close, amount=1000 + i * 20) for i, close in enumerate(closes)]

    ctx = analyze_topic_index(rows, min_required_rows=20)

    assert ctx["observed"] is True
    assert ctx["status"] == "observed"
    assert ctx["phase"] in {"EARLY_ACCELERATION", "MAIN_TREND"}
    assert ctx["topic_index_trend_score"] > 0
    assert ctx["topic_index_breakout_score"] > 0
    assert ctx["topic_return_20d"] > 0
    assert ctx["latest_date"] == rows[-1]["date"]


def test_analyze_topic_index_marks_insufficient_rows_unobserved():
    ctx = analyze_topic_index([_row(0, 100)], min_required_rows=20)

    assert ctx["observed"] is False
    assert ctx["status"] == "INSUFFICIENT_TOPIC_INDEX_ROWS"
    assert ctx["phase"] == "UNOBSERVED_TOPIC_INDEX"

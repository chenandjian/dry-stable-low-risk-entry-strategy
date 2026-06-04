from scanner.backtester import summarize_by_verdict


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

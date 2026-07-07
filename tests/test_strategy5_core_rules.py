from strategy5.engine import ShortSprintSupportEngine
from strategy5.support import evaluate_support_status


def _row(i, close=10.0, high=None, low=None, volume=1000, turnover=30):
    day = i + 1
    return {
        "date": f"2026-{(day // 28) % 12 + 1:02d}-{(day % 28) + 1:02d}",
        "open": round(close * 0.995, 4),
        "high": round(high if high is not None else close * 1.01, 4),
        "low": round(low if low is not None else close * 0.99, 4),
        "close": round(close, 4),
        "volume": volume,
        "turnover": turnover,
    }


def build_strong_data(length=1100):
    data = []
    for i in range(length):
        close = 10 + i * 0.01
        data.append(_row(i, close=close, volume=1_000_000 + i * 10, turnover=30))

    base = data[-21]["close"]
    for j in range(20):
        close = base * (1 + 0.012 * (j + 1))
        data[-20 + j].update({
            "open": round(close * 0.995, 4),
            "high": round(close * 1.01, 4),
            "low": round(close * 0.99, 4),
            "close": round(close, 4),
            "volume": 2_000_000 + j * 10_000,
            "turnover": 35,
        })

    return data


def test_engine_outputs_candidate_with_strength_high_support_and_scores():
    data = build_strong_data()

    result = ShortSprintSupportEngine({}).evaluate_at(data, code="000001", name="平安银行")

    assert result.passed is True
    assert result.code == "000001"
    assert result.candidate_type in {"KEY_CANDIDATE", "WATCH_CANDIDATE"}
    assert result.classification in {"highlight", "observe"}
    assert result.indicators.strength_trigger in {"ret_20d", "ret_10d", "ret_5d", "single_day_surge"}
    assert result.indicators.high_trigger in {"near_120d_high", "new_120d_high"}
    assert result.support.support_status.startswith("SPRINT_")
    assert result.support.support_score > 0
    assert 0 <= result.score.technical_score <= 35
    assert 0 <= result.score.capital_score <= 30
    assert 0 <= result.score.trend_score <= 20
    assert 0 <= result.score.support_quality_score <= 15
    assert 0 <= result.score.total_score <= 100


def test_volume_up_decline_is_rejected_with_stable_reason():
    data = build_strong_data()
    data[-1]["close"] = round(data[-2]["close"] * 0.92, 4)
    data[-1]["open"] = round(data[-2]["close"], 4)
    data[-1]["high"] = round(data[-2]["close"] * 1.01, 4)
    data[-1]["low"] = round(data[-1]["close"] * 0.98, 4)
    data[-1]["volume"] = data[-20]["volume"] * 3

    result = ShortSprintSupportEngine({}).evaluate_at(data, code="000001", name="平安银行")

    assert result.passed is False
    assert result.candidate_type == "REJECTED"
    assert "CONSOLIDATION_VOLUME_UP_DECLINE" in result.reject_reasons


def test_insufficient_history_is_rejected_with_stable_reason():
    result = ShortSprintSupportEngine({}).evaluate_at(build_strong_data(length=200), code="000001", name="平安银行")

    assert result.passed is False
    assert "INSUFFICIENT_KLINE_DAYS" in result.reject_reasons


def test_support_status_priority_prefers_ma5_before_ma10():
    support = evaluate_support_status(close=100, ma5=99, ma10=98, ma20=96, ma50=92)

    assert support.support_status == "SPRINT_MA5_SUPPORT"
    assert support.main_support_ma == "MA5"
    assert support.support_score == 10


def test_support_status_marks_ma50_testing_as_watch_quality():
    support = evaluate_support_status(close=100, ma5=110, ma10=108, ma20=106, ma50=96)

    assert support.support_status == "SPRINT_MA50_TESTING"
    assert support.main_support_ma == "MA50"
    assert support.support_score == 4

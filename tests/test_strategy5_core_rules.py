from strategy5.engine import ShortSprintSupportEngine
from strategy5.filters import hard_filter_reasons
from strategy5.indicators import calculate_indicators, normalize_rows
from strategy5.models import Strategy5Indicators
from strategy5.validation import resolve_strategy5_config
from strategy5.support import evaluate_support_status
from datetime import date, timedelta


def _row(i, close=10.0, high=None, low=None, volume=1000, turnover=30):
    day = date(2022, 1, 1) + timedelta(days=i)
    return {
        "date": day.isoformat(),
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
        close = base * (1 + 0.014 * (j + 1))
        data[-20 + j].update({
            "open": round(close * 0.995, 4),
            "high": round(close * 1.01, 4),
            "low": round(close * 0.99, 4),
            "close": round(close, 4),
            "volume": 2_000_000 + j * 10_000,
            "turnover": 35,
        })

    return data


def build_50d_quality_catchup_data(length=1100, *, recent_10d_amplitude=0.08):
    data = []
    for i in range(length):
        close = 10 + i * 0.01
        data.append(_row(i, close=close, volume=1_000_000 + i * 10, turnover=35))

    start = data[-51]["close"]
    for j in range(50):
        progress = (j + 1) / 50
        close = start * (1 + 0.50 * progress)
        data[-50 + j].update({
            "open": round(close * 0.995, 4),
            "high": round(close * 1.01, 4),
            "low": round(close * 0.99, 4),
            "close": round(close, 4),
            "volume": 2_000_000 + j * 5_000,
            "turnover": 40,
        })

    base_21 = data[-21]["close"]
    for j in range(20):
        progress = (j + 1) / 20
        close = base_21 * (1 + 0.06 * progress)
        data[-20 + j].update({
            "open": round(close * 0.995, 4),
            "high": round(close * 1.01, 4),
            "low": round(close * 0.99, 4),
            "close": round(close, 4),
            "volume": 2_500_000 + j * 3_000,
            "turnover": 45,
        })

    if recent_10d_amplitude > 0.08:
        base_11 = data[-11]["close"]
        for j in range(10):
            close = base_11 * (1 + 0.006 * (j + 1))
            data[-10 + j].update({
                "open": round(close, 4),
                "high": round(base_11 * (1 + recent_10d_amplitude * 0.65), 4),
                "low": round(base_11 * (1 - recent_10d_amplitude * 0.45), 4),
                "close": round(close, 4),
                "volume": 2_500_000 + j * 3_000,
                "turnover": 45,
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


def test_50d_quality_catchup_strength_can_enter_candidate_when_short_windows_do_not_trigger():
    data = build_50d_quality_catchup_data()

    result = ShortSprintSupportEngine({}).evaluate_at(data, code="000001", name="平安银行")

    assert result.passed is True
    assert result.indicators.strength_trigger == "ret_50d"
    assert result.indicators.recent_50d_return >= 0.35
    assert result.indicators.recent_20d_return < 0.25
    assert result.indicators.recent_10d_return < 0.15
    assert result.indicators.recent_5d_return < 0.10


def test_50d_quality_catchup_requires_stable_recent_consolidation():
    data = build_50d_quality_catchup_data(recent_10d_amplitude=0.38)

    result = ShortSprintSupportEngine({}).evaluate_at(data, code="000001", name="平安银行")

    assert result.passed is False
    assert result.indicators.recent_50d_return >= 0.35
    assert result.indicators.strength_trigger == ""
    assert "SHORT_TERM_STRENGTH_FAILED" in result.reject_reasons


def test_insufficient_history_is_rejected_with_stable_reason():
    result = ShortSprintSupportEngine({}).evaluate_at(build_strong_data(length=200), code="000001", name="平安银行")

    assert result.passed is False
    assert result.status_reason == "TRADING_DAYS_LT_500"
    assert "TRADING_DAYS_LT_500" in result.reject_reasons
    assert "INSUFFICIENT_KLINE_DAYS" not in result.reject_reasons


def test_compact_window_with_trading_days_override_matches_full_window():
    data = build_strong_data(length=800)
    engine = ShortSprintSupportEngine({})

    full = engine.evaluate_at(data, code="000001", name="平安银行")
    compact = engine.evaluate_at(
        data[-260:],
        code="000001",
        name="平安银行",
        trading_days_override=len(data),
    )

    assert compact.to_candidate_dict() == full.to_candidate_dict()


def test_pre_normalized_rows_match_raw_indicator_calculation():
    data = build_strong_data(length=800)
    cfg = resolve_strategy5_config({})

    raw = calculate_indicators(data, cfg)
    normalized = calculate_indicators(normalize_rows(data), cfg, rows_normalized=True)

    assert normalized == raw


def test_trading_days_filter_accepts_configured_minimum_boundary():
    cfg = resolve_strategy5_config({})
    indicators = Strategy5Indicators(trading_days=cfg["minimum_trading_days"])

    assert "TRADING_DAYS_LT_500" not in hard_filter_reasons(indicators, cfg)

    indicators.trading_days = cfg["minimum_trading_days"] - 1

    assert "TRADING_DAYS_LT_500" in hard_filter_reasons(indicators, cfg)


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

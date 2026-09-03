from __future__ import annotations

from datetime import date, timedelta

import scanner.db as db
from strategy6 import STRATEGY6_TYPE
from strategy6.engine import StrongVcpTailEngine
from strategy6.filters import hard_filter_reasons
from strategy6.models import (
    Strategy6DryTail,
    Strategy6Indicators,
    Strategy6Phase,
    Strategy6Pattern,
    Strategy6StrongTrendSqueeze,
    Strategy6Start,
    Strategy6Support,
    Strategy6TradePlan,
)
from strategy6.strong_trend_squeeze import evaluate_strong_trend_squeeze


def _row(index: int, close: float, *, high: float | None = None, low: float | None = None) -> dict:
    day = date(2024, 1, 1) + timedelta(days=index)
    return {
        "date": day.isoformat(),
        "open": close,
        "high": close + 0.12 if high is None else high,
        "low": close - 0.12 if low is None else low,
        "close": close,
        "volume": 1_000_000,
        "amount": 600_000_000,
    }


def _passing_rows() -> list[dict]:
    rows = [_row(index, 12.0 + index * 0.032) for index in range(280)]
    base = rows[-21]["close"]
    for offset in range(20):
        close = base + offset * 0.002
        rows[-20 + offset] = _row(260 + offset, close, high=close + 0.08, low=close - 0.08)
    return rows


def test_strong_trend_squeeze_accepts_uptrend_high_position_and_current_squeeze():
    result = evaluate_strong_trend_squeeze(_passing_rows())

    assert result.passed is True
    assert result.reasons == []
    assert result.close > 10
    assert result.close >= result.low_250 * 1.30
    assert result.high_250 * 0.70 <= result.close <= result.high_250
    assert result.ema150 > result.ema200
    assert result.close > result.ema150
    assert result.close > result.ema200
    assert result.squeeze_on is True
    assert result.bb_upper < result.kc_upper
    assert result.bb_lower > result.kc_lower


def test_strong_trend_squeeze_reports_each_business_rule_with_stable_codes():
    result = Strategy6StrongTrendSqueeze(
        calculable=True,
        close=10.0,
        low_250=8.0,
        high_250=20.0,
        ema150=10.5,
        ema200=11.0,
        squeeze_on=False,
    )

    result.apply_rules()

    assert result.reasons == [
        "CLOSE_LE_10",
        "CLOSE_LT_52W_LOW_1_30",
        "CLOSE_LT_52W_HIGH_0_70",
        "EMA150_LE_EMA200",
        "CLOSE_LE_EMA150",
        "CLOSE_LE_EMA200",
        "BB_NOT_INSIDE_KC",
    ]
    assert result.passed is False


def test_strong_trend_squeeze_includes_30_and_70_percent_boundaries():
    result = Strategy6StrongTrendSqueeze(
        calculable=True,
        close=13.0,
        low_250=10.0,
        high_250=13.0 / 0.70,
        ema150=12.0,
        ema200=11.0,
        squeeze_on=True,
    )

    result.apply_rules()

    assert result.passed is True
    assert result.reasons == []


def test_strong_trend_squeeze_rejects_insufficient_history_explicitly():
    result = evaluate_strong_trend_squeeze(_passing_rows()[:249])

    assert result.passed is False
    assert result.calculable is False
    assert result.reasons == ["TREND_SQUEEZE_HISTORY_LT_250"]


def test_strong_trend_squeeze_treats_missing_rows_as_insufficient_history():
    result = evaluate_strong_trend_squeeze(None)

    assert result.passed is False
    assert result.reasons == ["TREND_SQUEEZE_HISTORY_LT_250"]


def test_hard_filter_uses_new_filter_and_no_longer_applies_old_ma120_ma250_rules():
    config = StrongVcpTailEngine({}).config
    indicators = Strategy6Indicators(
        trading_days=500,
        current_price=20.0,
        ma5=20.0,
        ma10=20.0,
        ma20=20.0,
        ma50=20.0,
        ma120=10.0,
        ma250=30.0,
        amount_avg_10=10.0,
        amount_avg_30=10.0,
        amount_avg_60=10.0,
    )
    trend = Strategy6StrongTrendSqueeze(passed=True, calculable=True)

    reasons = hard_filter_reasons(
        [],
        indicators,
        Strategy6Start(start_type="NORMAL_STRONG_BREAKOUT", start_grade="A", high_trigger="near_120d_high"),
        Strategy6Phase(valid=True, status="VALID"),
        Strategy6Pattern(pattern_type="PLATFORM"),
        Strategy6Support(support_status="VALID", support_test_count=1),
        Strategy6DryTail(),
        Strategy6TradePlan(objective_rr_2=10.0),
        config,
        strong_trend_squeeze=trend,
    )

    assert "CLOSE_LE_MA250" not in reasons
    assert "MA120_LE_MA250" not in reasons


def test_strong_trend_squeeze_is_hard_filter_but_does_not_remove_strong_start_requirement():
    config = StrongVcpTailEngine({}).config
    indicators = Strategy6Indicators(
        trading_days=500,
        current_price=20.0,
        ma5=20.0,
        ma10=20.0,
        ma20=20.0,
        ma50=20.0,
        ma120=20.0,
        ma250=20.0,
        amount_avg_10=10.0,
        amount_avg_30=10.0,
        amount_avg_60=10.0,
    )
    trend = Strategy6StrongTrendSqueeze(
        passed=False,
        calculable=True,
        reasons=["BB_NOT_INSIDE_KC"],
    )

    reasons = hard_filter_reasons(
        [], indicators, Strategy6Start(), Strategy6Phase(valid=True, status="VALID"),
        Strategy6Pattern(pattern_type="PLATFORM"),
        Strategy6Support(support_status="VALID", support_test_count=1),
        Strategy6DryTail(), Strategy6TradePlan(objective_rr_2=10.0), config,
        strong_trend_squeeze=trend,
    )

    assert "BB_NOT_INSIDE_KC" in reasons
    assert "NO_STRONG_START" in reasons


def test_ttm_diagnostic_score_is_not_added_to_strategy6_ranking(monkeypatch):
    evaluation = StrongVcpTailEngine({}).evaluate_at(
        _passing_rows(),
        code="000001",
        name="平安银行",
    )

    assert evaluation.ranking_score == evaluation.score.total_score
    assert evaluation.to_candidate_dict()["strong_trend_squeeze_pass"] is True


def test_strong_trend_squeeze_audit_fields_survive_candidate_persistence(tmp_path):
    db.init_db(str(tmp_path / "strong-trend-squeeze.db"))
    db.create_scan_task("s6-trend", "2026-09-03 10:00:00", strategy_type=STRATEGY6_TYPE)
    candidate = StrongVcpTailEngine({}).evaluate_at(
        _passing_rows(), code="000001", name="平安银行",
    ).to_candidate_dict()

    db.upsert_strategy6_candidate("s6-trend", candidate)
    saved = db.get_strategy6_candidate("000001", task_id="s6-trend")

    assert saved["strong_trend_squeeze_pass"] is True
    assert saved["strong_trend_squeeze_status"] == "PASSED"
    assert saved["trend_ema150"] > saved["trend_ema200"]
    assert saved["trend_squeeze_on"] is True
    assert saved["strong_trend_squeeze_reasons"] == []
    assert saved["strong_trend_squeeze_model_version"] == "S6_STRONG_TREND_SQUEEZE_V1"

from datetime import date, timedelta

from strategy3.engine import StrongPullbackSecondBreakoutEngine


def make_strategy3_candidate_bars(days=220):
    start = date(2025, 1, 1)
    rows = []
    for i in range(days):
        if i < 120:
            close = 10.0 + i * 0.055
        elif i < 160:
            close = 16.6 + (i - 120) * 0.035
        elif i < 175:
            close = 18.0 + (i - 160) * 0.52
        elif i < 205:
            close = 24.5 - (i - 175) * 0.095
        else:
            close = 22.30 + (i - 205) * 0.040
        volume = 1_000_000 if i < 175 else 650_000
        if i >= days - 3:
            volume = 760_000
        rows.append({
            "date": (start + timedelta(days=i)).strftime("%Y-%m-%d"),
            "open": round(close * 0.995, 2),
            "high": round(close * 1.012, 2),
            "low": round(close * 0.988, 2),
            "close": round(close, 2),
            "volume": volume,
            "turnover": round(close * volume, 2),
        })
    return rows


def test_engine_passes_healthy_strong_pullback():
    engine = StrongPullbackSecondBreakoutEngine({"liquidity": {"min_listing_days": 350}})
    result = engine.evaluate_at(make_strategy3_candidate_bars(), code="000001", name="样本")

    assert result.passed is True
    assert result.status_reason is None
    assert result.total_score >= 75
    assert result.level in {"观察候选", "核心候选"}
    assert result.risk.stop_loss > 0
    assert result.risk.rr1 >= 1.5
    assert 0.08 <= result.indicators.pullback_pct <= 0.30


def test_engine_rejects_deep_drawdown():
    data = make_strategy3_candidate_bars()
    data[-1]["close"] = round(data[-1]["close"] * 0.55, 2)
    data[-1]["open"] = data[-1]["close"]
    data[-1]["high"] = round(data[-1]["close"] * 1.01, 2)
    data[-1]["low"] = round(data[-1]["close"] * 0.99, 2)

    engine = StrongPullbackSecondBreakoutEngine({"liquidity": {"min_listing_days": 350}})
    result = engine.evaluate_at(data, code="000002")

    assert result.passed is False
    assert result.status_reason in {"DEEP_DRAWDOWN_FROM_HIGH", "PULLBACK_TOO_DEEP"}


def test_engine_rejects_recent_overheated():
    data = make_strategy3_candidate_bars()
    data[-1]["close"] = round(data[-4]["close"] * 1.12, 2)
    data[-1]["open"] = round(data[-1]["close"] * 0.99, 2)
    data[-1]["high"] = round(data[-1]["close"] * 1.01, 2)
    data[-1]["low"] = round(data[-1]["close"] * 0.98, 2)

    engine = StrongPullbackSecondBreakoutEngine({"liquidity": {"min_listing_days": 350}})
    result = engine.evaluate_at(data, code="000003")

    assert result.passed is False
    assert result.status_reason == "RECENT_OVERHEATED"


def test_engine_rejects_insufficient_strategy_data():
    engine = StrongPullbackSecondBreakoutEngine({"liquidity": {"min_listing_days": 350}})
    result = engine.evaluate_at(make_strategy3_candidate_bars(days=100), code="000004")

    assert result.passed is False
    assert result.status_reason == "INSUFFICIENT_STRATEGY_DATA"

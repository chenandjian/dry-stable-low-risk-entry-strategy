from datetime import date, timedelta

from strategy3.engine import StrongPullbackSecondBreakoutEngine
from strategy3.indicators import compute_indicators
from strategy3.models import Strategy3Indicators
from strategy3.risk import compute_strategy3_risk


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


def make_dry_cannot_fall_bars(days=220, scenario="healthy"):
    rows = make_strategy3_candidate_bars(days)
    base_closes = [
        22.90, 22.72, 22.60, 22.48, 22.35,
        22.25, 22.18, 22.12, 22.05, 22.02,
        22.10, 22.00, 22.12, 22.05, 22.08,
        22.06, 22.08, 22.09, 22.12, 22.15,
    ]
    base_volumes = [
        1_250_000, 1_220_000, 1_210_000, 1_190_000, 1_180_000,
        1_160_000, 1_140_000, 1_130_000, 1_120_000, 1_100_000,
        700_000, 690_000, 680_000, 670_000, 660_000,
        450_000, 420_000, 380_000, 360_000, 340_000,
    ]
    opens = [
        23.05, 22.88, 22.75, 22.65, 22.50,
        22.45, 22.36, 22.28, 22.21, 22.16,
        22.25, 22.18, 22.10, 22.16, 22.06,
        22.07, 22.05, 22.11, 22.10, 22.16,
    ]

    if scenario == "bear_drift":
        base_closes[-5:] = [21.80, 21.55, 21.30, 21.05, 20.75]
        opens[-5:] = [21.95, 21.70, 21.45, 21.20, 20.92]
    elif scenario == "support_failed":
        base_closes[-1] = 21.05
        opens[-1] = 21.22
    elif scenario == "support_failed_recent":
        base_closes[-3] = 21.35
        opens[-3] = 21.52
    elif scenario == "atr_expanding":
        base_closes[-5:] = [22.02, 21.90, 21.82, 21.74, 21.68]
        opens[-5:] = [22.14, 22.02, 21.94, 21.84, 21.76]
    elif scenario == "big_down_volume":
        base_closes[-2] = 21.02
        opens[-2] = 22.10
        base_volumes[-2] = 1_600_000

    for offset, close in enumerate(base_closes, start=days - 20):
        idx = offset
        open_ = opens[offset - (days - 20)]
        volume = base_volumes[offset - (days - 20)]
        if scenario == "atr_expanding" and idx >= days - 5:
            high = max(open_, close) + 1.20
            low = min(open_, close) - 1.05
        elif idx >= days - 5:
            high = max(open_, close) + 0.12
            low = min(open_, close) - 0.10
        else:
            high = max(open_, close) + 0.45
            low = min(open_, close) - 0.45
        rows[idx].update({
            "open": round(open_, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(close, 2),
            "volume": volume,
            "turnover": round(close * volume, 2),
        })
    return rows


def make_extreme_balance_bars(days=220, scenario="healthy"):
    rows = make_dry_cannot_fall_bars(days)
    closes = [22.08, 22.14, 22.07, 22.13, 22.06, 22.11]
    volumes = [430_000, 410_000, 390_000, 370_000, 350_000, 330_000]

    if scenario == "single_day_spike":
        closes = [22.08, 23.05, 22.92, 22.86, 22.80, 22.74]

    for idx, close in zip(range(days - 6, days), closes):
        volume = volumes[idx - (days - 6)]
        rows[idx].update({
            "open": round(close, 2),
            "high": round(close + 0.10, 2),
            "low": round(close - 0.10, 2),
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


def test_strategy3_indicators_include_dry_cannot_fall_quality_fields():
    engine = StrongPullbackSecondBreakoutEngine({"liquidity": {"min_listing_days": 350}})
    ind = compute_indicators(make_dry_cannot_fall_bars(), engine.config)

    assert ind.v3 > 0
    assert ind.return_5 > -0.03
    assert ind.no_new_low is True
    assert ind.support_test_count >= 2
    assert ind.support_valid is True
    assert ind.bear_body_shrink is True
    assert ind.lower_shadow_count >= 2
    assert ind.down_volume_ratio_5 <= 0.60
    assert 0 < ind.atr_ratio_5_20 <= 0.75


def test_strategy3_indicators_include_extreme_balance_quality_fields():
    engine = StrongPullbackSecondBreakoutEngine({"liquidity": {"min_listing_days": 350}})
    ind = compute_indicators(make_extreme_balance_bars(), engine.config)

    assert 0 < ind.range_5 < ind.range_10 < ind.range_20
    assert ind.range_compression_ok is True
    assert ind.direction_efficiency_5 <= 0.35
    assert ind.max_up_5 <= 0.03
    assert ind.max_down_5 >= -0.03
    assert 0.35 <= ind.avg_close_position_5 <= 0.65


def test_volume_stability_v2_rewards_dry_cannot_fall_quality():
    engine = StrongPullbackSecondBreakoutEngine({"liquidity": {"min_listing_days": 350}})
    result = engine.evaluate_at(make_dry_cannot_fall_bars(), code="000010")

    assert result.volume_stability_score >= 17
    assert "volume:no_new_low" in result.score_reasons
    assert "volume:support_test_count>=2" in result.score_reasons
    assert "volume:atr_contracted" in result.score_reasons


def test_volume_stability_v3_rewards_extreme_balance_quality():
    engine = StrongPullbackSecondBreakoutEngine({"liquidity": {"min_listing_days": 350}})
    result = engine.evaluate_at(make_extreme_balance_bars(), code="000016")

    assert result.volume_stability_score >= 18
    assert "volume:direction_efficiency_low" in result.score_reasons
    assert "volume:max_daily_move_balanced" in result.score_reasons
    assert "volume:close_position_balanced" in result.score_reasons
    assert "volume:range_compression_sequence" in result.score_reasons


def test_volume_stability_v3_does_not_reward_single_day_spike_as_extreme_balance():
    engine = StrongPullbackSecondBreakoutEngine({"liquidity": {"min_listing_days": 350}})
    result = engine.evaluate_at(make_extreme_balance_bars(scenario="single_day_spike"), code="000017")

    assert result.indicators.max_up_5 > 0.03
    assert "volume:max_daily_move_balanced" not in result.score_reasons
    assert "volume:direction_efficiency_low" not in result.score_reasons


def test_volume_stability_rejects_shrinking_bear_drift():
    result = StrongPullbackSecondBreakoutEngine({"liquidity": {"min_listing_days": 350}}).evaluate_at(
        make_dry_cannot_fall_bars(scenario="bear_drift"),
        code="000011",
    )

    assert result.passed is False
    assert "SHRINKING_BEAR_DRIFT" in result.reject_reasons


def test_volume_stability_rejects_support_failure():
    result = StrongPullbackSecondBreakoutEngine({"liquidity": {"min_listing_days": 350}}).evaluate_at(
        make_dry_cannot_fall_bars(scenario="support_failed"),
        code="000012",
    )

    assert result.passed is False
    assert "SUPPORT_TEST_FAILED" in result.reject_reasons


def test_volume_stability_rejects_recent_support_failure_even_if_current_recovers():
    result = StrongPullbackSecondBreakoutEngine({"liquidity": {"min_listing_days": 350}}).evaluate_at(
        make_dry_cannot_fall_bars(scenario="support_failed_recent"),
        code="000015",
    )

    assert result.passed is False
    assert "SUPPORT_TEST_FAILED" in result.reject_reasons


def test_volume_stability_rejects_downside_volatility_expansion():
    result = StrongPullbackSecondBreakoutEngine({"liquidity": {"min_listing_days": 350}}).evaluate_at(
        make_dry_cannot_fall_bars(scenario="atr_expanding"),
        code="000013",
    )

    assert result.passed is False
    assert "DOWNSIDE_VOLATILITY_EXPANDING" in result.reject_reasons


def test_volume_stability_rejects_big_down_volume():
    result = StrongPullbackSecondBreakoutEngine({"liquidity": {"min_listing_days": 350}}).evaluate_at(
        make_dry_cannot_fall_bars(scenario="big_down_volume"),
        code="000014",
    )

    assert result.passed is False
    assert "DRY_HEAVY_DOWNSIDE_VOLUME" in result.reject_reasons


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


def test_relative_strength_60_subtracts_market_index_return():
    stock = make_strategy3_candidate_bars()
    market = []
    for row in stock:
        market.append({
            **row,
            "close": 20.0,
            "open": 20.0,
            "high": 20.2,
            "low": 19.8,
        })
    market[-61]["close"] = 10.0
    market[-1]["close"] = 11.0

    ind = compute_indicators(
        stock,
        {"pullback_lookback_days": 60},
        market_data=market,
    )

    assert abs(ind.relative_strength_60 - (ind.return_60 - 0.10)) < 1e-9


def test_risk_model_uses_tactical_support_but_keeps_structural_risk_visible():
    start = date(2026, 1, 1)
    data = []
    for i in range(80):
        row = {
            "date": (start + timedelta(days=i)).strftime("%Y-%m-%d"),
            "open": 95.0,
            "high": 100.0,
            "low": 92.0,
            "close": 95.0,
            "volume": 1_000_000,
            "turnover": 95_000_000,
        }
        if i == 65:
            row.update({"open": 109.0, "high": 112.0, "low": 108.0, "close": 110.0})
        if i == 70:
            row.update({"open": 89.0, "high": 90.0, "low": 80.0, "close": 88.0})
        if i == 79:
            row.update({"open": 99.0, "high": 101.0, "low": 99.0, "close": 100.0})
        data.append(row)
    ind = Strategy3Indicators(
        current_close=100.0,
        ma20=96.0,
        ma60=90.0,
        recent_high=112.0,
    )

    risk, rejects, score, reasons = compute_strategy3_risk(
        data,
        ind,
        {
            "support_lookback_days": 20,
            "pullback_lookback_days": 60,
            "max_risk_ratio": 0.08,
        },
    )

    assert risk.structural_support == 80.0
    assert risk.structural_risk_ratio > 0.20
    assert risk.tactical_support == 96.0
    assert risk.support_price == risk.tactical_support
    assert risk.stop_loss == risk.tactical_stop_loss
    assert risk.risk_ratio == risk.tactical_risk_ratio
    assert risk.risk_ratio < 0.08
    assert "RISK_RATIO_TOO_HIGH" not in rejects
    assert score > 0
    assert "tactical_support:ma20" in reasons


def test_risk_model_exposes_key_support_zone_and_status():
    result = StrongPullbackSecondBreakoutEngine({"liquidity": {"min_listing_days": 350}}).evaluate_at(
        make_strategy3_candidate_bars(),
        code="000020",
    )

    assert result.passed is True
    assert result.risk.short_support > 0
    assert result.risk.key_support > 0
    assert result.risk.strong_support > 0
    assert result.risk.key_support_zone_low < result.risk.key_support < result.risk.key_support_zone_high
    assert result.risk.support_status in {"VALID", "TESTING"}
    assert result.risk.break_status == "NOT_BROKEN"
    assert result.risk.nearest_support_distance >= 0
    assert result.risk.support_sources


def test_risk_model_uses_nearest_support_zone_for_tactical_risk_when_key_support_is_far():
    start = date(2026, 1, 1)
    data = []
    for i in range(80):
        data.append({
            "date": (start + timedelta(days=i)).strftime("%Y-%m-%d"),
            "open": 98.0,
            "high": 101.0,
            "low": 97.0,
            "close": 99.0,
            "volume": 1_000_000,
            "turnover": 99_000_000,
        })
    data[-1].update({"open": 99.5, "high": 101.0, "low": 99.0, "close": 100.0})
    ind = Strategy3Indicators(
        current_close=100.0,
        ma20=96.0,
        ma60=90.0,
        recent_high=112.0,
        short_support=96.0,
        short_support_zone_low=95.0,
        short_support_zone_high=97.0,
        key_support=88.0,
        key_support_zone_low=86.0,
        key_support_zone_high=90.0,
        strong_support=82.0,
        strong_support_zone_low=80.0,
        strong_support_zone_high=84.0,
        support_status="VALID",
        break_status="NOT_BROKEN",
        support_sources=["min_close_10"],
    )

    risk, rejects, score, reasons = compute_strategy3_risk(
        data,
        ind,
        {
            "support_lookback_days": 20,
            "pullback_lookback_days": 60,
            "max_risk_ratio": 0.08,
            "support_stop_buffer_pct": 0.01,
        },
    )

    assert risk.key_support == 88.0
    assert risk.tactical_support == 96.0
    assert risk.support_quality == "short_support"
    assert risk.tactical_risk_ratio < 0.08
    assert "RISK_RATIO_TOO_HIGH" not in rejects
    assert score > 0
    assert "tactical_support:short_support" in reasons


def test_support_zone_does_not_reject_intraday_pierce_when_close_recovers():
    data = make_dry_cannot_fall_bars()
    data[-1].update({
        "open": 22.18,
        "high": 22.30,
        "low": 21.60,
        "close": 22.12,
        "volume": 340_000,
        "turnover": round(22.12 * 340_000, 2),
    })

    result = StrongPullbackSecondBreakoutEngine({"liquidity": {"min_listing_days": 350}}).evaluate_at(
        data,
        code="000021",
    )

    assert "SUPPORT_TEST_FAILED" not in result.reject_reasons
    assert "KEY_SUPPORT_FAILED" not in result.reject_reasons
    assert result.risk.support_status in {"VALID", "TESTING"}


def test_support_zone_rejects_two_consecutive_closes_below_key_zone():
    data = make_dry_cannot_fall_bars()
    for idx, close in [(-2, 21.35), (-1, 21.25)]:
        data[idx].update({
            "open": round(close + 0.10, 2),
            "high": round(close + 0.18, 2),
            "low": round(close - 0.12, 2),
            "close": close,
            "volume": 500_000,
            "turnover": round(close * 500_000, 2),
        })

    result = StrongPullbackSecondBreakoutEngine({"liquidity": {"min_listing_days": 350}}).evaluate_at(
        data,
        code="000022",
    )

    assert result.passed is False
    assert "SUPPORT_TEST_FAILED" in result.reject_reasons
    assert "KEY_SUPPORT_FAILED" in result.reject_reasons
    assert result.risk.support_status == "FAILED"
    assert result.risk.break_status == "EFFECTIVE_BREAK"


def test_support_zone_rejects_single_high_volume_close_below_key_zone():
    data = make_dry_cannot_fall_bars()
    data[-1].update({
        "open": 22.05,
        "high": 22.12,
        "low": 21.20,
        "close": 21.30,
        "volume": 1_700_000,
        "turnover": round(21.30 * 1_700_000, 2),
    })

    result = StrongPullbackSecondBreakoutEngine({"liquidity": {"min_listing_days": 350}}).evaluate_at(
        data,
        code="000023",
    )

    assert result.passed is False
    assert "SUPPORT_TEST_FAILED" in result.reject_reasons
    assert "KEY_SUPPORT_FAILED" in result.reject_reasons
    assert result.risk.support_status == "FAILED"
    assert result.risk.break_status == "EFFECTIVE_BREAK"

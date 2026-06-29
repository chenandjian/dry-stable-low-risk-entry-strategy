from datetime import date, timedelta

from strategy3.engine import StrongPullbackSecondBreakoutEngine
from strategy3.indicators import compute_indicators
from strategy3.models import Strategy3Indicators, Strategy3Risk
from strategy3.risk import compute_strategy3_risk
from strategy3.validation import resolve_strategy3_config
from strategy3.volume_stability import evaluate_volume_stability


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
        high_multiplier = 1.05 if i == 174 else 1.012
        rows.append({
            "date": (start + timedelta(days=i)).strftime("%Y-%m-%d"),
            "open": round(close * 0.995, 2),
            "high": round(close * high_multiplier, 2),
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



def _flat_volume_rows(days=20):
    start = date(2026, 1, 1)
    return [
        {
            "date": (start + timedelta(days=i)).strftime("%Y-%m-%d"),
            "open": 10.0,
            "high": 10.2,
            "low": 9.8,
            "close": 10.0,
            "volume": 1_000_000,
            "turnover": 10_000_000,
        }
        for i in range(days)
    ]


def _quality_data(days=60):
    start = date(2026, 1, 1)
    rows = []
    for i in range(days):
        close = 10.0 + min(i, days - 10) * 0.01
        rows.append({
            "date": (start + timedelta(days=i)).strftime("%Y-%m-%d"),
            "open": round(close * 0.998, 2),
            "high": round(close * 1.006, 2),
            "low": round(close * 0.994, 2),
            "close": round(close, 2),
            "volume": 1_000_000,
            "turnover": round(close * 1_000_000, 2),
        })
    return rows


def _quality_indicators(**overrides):
    values = dict(
        current_close=10.0,
        volume_ratio_5_20=0.48,
        v3=420_000,
        v5=480_000,
        v10=700_000,
        v20=1_000_000,
        volume_percentile_60=0.12,
        down_volume_ratio_5=0.42,
        down_day_volume_ratio=0.55,
        has_big_down_volume=False,
        range_5=0.028,
        range_10=0.055,
        range_20=0.095,
        range_compression_ok=True,
        close_range_5=0.018,
        atr_ratio_5_20=0.62,
        max_up_5=0.018,
        max_down_5=-0.015,
        direction_efficiency_5=0.22,
        avg_abs_return_5=0.009,
        avg_close_position_5=0.55,
        no_new_low=True,
        new_low_count_5=0,
        bear_body_shrink=True,
        bear_body_expanding=False,
        down_return_contracting=True,
        lower_shadow_count=2,
        support_valid=True,
        support_status="VALID",
        break_status="NOT_BROKEN",
        support_sources=["min_close_10", "ma20"],
    )
    values.update(overrides)
    return Strategy3Indicators(**values)


def _quality_risk(**overrides):
    values = dict(
        support_price=9.75,
        stop_loss=9.60,
        target_1=11.50,
        risk_ratio=0.04,
        rr1=3.75,
        tactical_support=9.75,
        tactical_stop_loss=9.60,
        tactical_risk_ratio=0.04,
        tactical_rr1=3.75,
        key_support=9.70,
        key_support_zone_low=9.55,
        key_support_zone_high=9.85,
        support_status="VALID",
        break_status="NOT_BROKEN",
        nearest_support_distance=0.025,
        support_sources=["min_close_10", "ma20"],
    )
    values.update(overrides)
    return Strategy3Risk(**values)


def _quality_config(**overrides):
    cfg = resolve_strategy3_config({"liquidity": {"min_listing_days": 350}})
    cfg.update(overrides)
    return cfg


def test_engine_keeps_legacy_candidate_fields_and_adds_trade_quality():
    result = StrongPullbackSecondBreakoutEngine({"liquidity": {"min_listing_days": 350}}).evaluate_at(
        make_strategy3_candidate_bars(),
        code="000030",
        name="兼容样本",
    )

    assert result.passed is True
    assert result.total_score >= 75
    assert result.risk.rr1 >= 1.5
    assert result.trade_quality.trade_state in {"LOW_ABSORB", "WATCH", "WAIT_BREAKOUT"}
    assert result.trade_quality.trade_state_label in {"低吸", "观察", "等待突破"}
    assert result.trade_quality.trade_quality_score >= 0
    assert result.trade_quality.volume_dry_score >= 0
    assert result.trade_quality.price_stability_score >= 0
    assert result.trade_quality.cannot_fall_score >= 0
    assert result.trade_quality.balance_powerless_score >= 0
    assert isinstance(result.trade_quality.trigger_reasons, list)
    assert isinstance(result.trade_quality.risk_warnings, list)
    assert isinstance(result.trade_quality.invalid_conditions, list)


def test_trade_quality_marks_low_absorb_when_dry_stable_near_support_with_good_rr():
    from strategy3.trade_quality import evaluate_trade_quality

    quality = evaluate_trade_quality(
        _quality_data(),
        _quality_indicators(),
        _quality_risk(),
        _quality_config(),
    )

    assert quality.trade_state == "LOW_ABSORB"
    assert quality.trade_state_label == "低吸"
    assert quality.volume_dry_score >= 15
    assert quality.price_stability_score >= 15
    assert quality.cannot_fall_score >= 14
    assert quality.balance_powerless_score >= 12
    assert quality.support_distance_pct <= 0.04
    assert quality.target_room_pct >= 0.10
    assert quality.estimated_rr >= 2.0
    assert "volume:extreme_dry" in quality.trigger_reasons
    assert "price:stable" in quality.trigger_reasons
    assert "support:near_tactical_support" in quality.trigger_reasons
    assert quality.invalid_conditions == []


def test_trade_quality_does_not_low_absorb_when_price_stable_but_volume_not_dry():
    from strategy3.trade_quality import evaluate_trade_quality

    quality = evaluate_trade_quality(
        _quality_data(),
        _quality_indicators(
            volume_ratio_5_20=0.96,
            volume_percentile_60=0.62,
            v3=980_000,
            v5=960_000,
            v10=940_000,
            v20=1_000_000,
        ),
        _quality_risk(),
        _quality_config(),
    )

    assert quality.trade_state != "LOW_ABSORB"
    assert quality.volume_dry_score < 15
    assert "risk:volume_not_dry_enough" in quality.risk_warnings


def test_trade_quality_marks_sideways_setup_as_watch_not_low_absorb():
    from strategy3.trade_quality import evaluate_trade_quality

    quality = evaluate_trade_quality(
        _quality_data(),
        _quality_indicators(
            volume_ratio_5_20=0.68,
            volume_percentile_60=0.42,
            v3=680_000,
            v5=690_000,
            v10=710_000,
            v20=1_000_000,
        ),
        _quality_risk(),
        _quality_config(),
    )

    assert quality.trade_state == "WATCH"
    assert quality.trade_state_label == "观察"
    assert quality.price_stability_score >= 15
    assert quality.volume_dry_score < 15


def test_engine_rejects_downtrend_dry_stable_as_avoid():
    result = StrongPullbackSecondBreakoutEngine({"liquidity": {"min_listing_days": 350}}).evaluate_at(
        make_dry_cannot_fall_bars(),
        code="000031",
    )

    assert result.passed is False
    assert "BELOW_MA60_AND_WEAK_TREND" in result.reject_reasons
    assert result.trade_quality.trade_state == "AVOID"
    assert "TREND_REJECTED" in result.trade_quality.invalid_conditions


def test_trade_quality_avoids_extreme_dry_when_price_is_not_stable():
    from strategy3.trade_quality import evaluate_trade_quality

    quality = evaluate_trade_quality(
        _quality_data(),
        _quality_indicators(
            range_5=0.11,
            close_range_5=0.09,
            atr_ratio_5_20=1.35,
            max_down_5=-0.055,
            range_compression_ok=False,
        ),
        _quality_risk(),
        _quality_config(),
    )

    assert quality.trade_state == "AVOID"
    assert "PRICE_NOT_STABLE" in quality.invalid_conditions
    assert "DOWNSIDE_VOLATILITY_EXPANDING" in quality.invalid_conditions


def test_trade_quality_waits_for_breakout_when_support_is_too_far_but_setup_is_good():
    from strategy3.trade_quality import evaluate_trade_quality

    quality = evaluate_trade_quality(
        _quality_data(),
        _quality_indicators(),
        _quality_risk(
            support_price=9.45,
            tactical_support=9.45,
            tactical_stop_loss=9.30,
            risk_ratio=0.07,
            tactical_risk_ratio=0.07,
            rr1=2.14,
            tactical_rr1=2.14,
            nearest_support_distance=0.055,
        ),
        _quality_config(),
    )

    assert quality.trade_state == "WAIT_BREAKOUT"
    assert quality.trade_state_label == "等待突破"
    assert quality.support_distance_pct > 0.04
    assert "risk:support_too_far_for_low_absorb" in quality.risk_warnings


def test_trade_quality_avoids_when_rr_is_insufficient_even_near_support():
    from strategy3.trade_quality import evaluate_trade_quality

    quality = evaluate_trade_quality(
        _quality_data(),
        _quality_indicators(),
        _quality_risk(target_1=10.30, rr1=0.75, tactical_rr1=0.75),
        _quality_config(),
    )

    assert quality.trade_state == "AVOID"
    assert "RR_TOO_LOW" in quality.invalid_conditions
    assert quality.estimated_rr < 1.5


def test_trade_quality_does_not_low_absorb_when_rr_is_good_but_price_not_stable():
    from strategy3.trade_quality import evaluate_trade_quality

    quality = evaluate_trade_quality(
        _quality_data(),
        _quality_indicators(
            range_5=0.095,
            close_range_5=0.075,
            max_up_5=0.052,
            avg_abs_return_5=0.026,
            range_compression_ok=False,
        ),
        _quality_risk(rr1=3.0, tactical_rr1=3.0),
        _quality_config(),
    )

    assert quality.trade_state != "LOW_ABSORB"
    assert "PRICE_NOT_STABLE" in quality.invalid_conditions


def test_trade_quality_avoids_heavy_volume_breakdown():
    from strategy3.trade_quality import evaluate_trade_quality

    quality = evaluate_trade_quality(
        _quality_data(),
        _quality_indicators(
            has_big_down_volume=True,
            support_status="FAILED",
            break_status="EFFECTIVE_BREAK",
            new_low_count_5=2,
            no_new_low=False,
            bear_body_expanding=True,
        ),
        _quality_risk(support_status="FAILED", break_status="EFFECTIVE_BREAK"),
        _quality_config(),
    )

    assert quality.trade_state == "AVOID"
    assert "VOLUME_BREAKDOWN" in quality.invalid_conditions
    assert "KEY_SUPPORT_FAILED" in quality.invalid_conditions
    assert "CONTINUOUS_NEW_LOW" in quality.invalid_conditions
    assert "BEAR_BODY_EXPANDING" in quality.invalid_conditions


def test_volume_stability_rewards_support_tests_only_within_approved_range():
    cfg = resolve_strategy3_config({"liquidity": {"min_listing_days": 350}})
    data = _flat_volume_rows()
    base = dict(
        volume_ratio_5_20=0.75,
        return_3=0.01,
        return_5=0.03,
        close_range_5=0.04,
        support_price_10=9.7,
        support_valid=True,
        support_status="VALID",
        atr_ratio_5_20=0.80,
        no_new_low=True,
        down_volume_ratio_5=0.40,
        current_close=10.0,
    )

    healthy = Strategy3Indicators(**base, support_test_count=2)
    over_tested = Strategy3Indicators(**base, support_test_count=3)

    _, healthy_score, healthy_reasons = evaluate_volume_stability(healthy, data, cfg)
    _, over_score, over_reasons = evaluate_volume_stability(over_tested, data, cfg)

    assert "support_test_count=2" in healthy_reasons
    assert "support_test_count>2" in over_reasons
    assert not any(r.startswith("support_test_count>=") for r in over_reasons)
    assert over_score == healthy_score - 2


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
    assert "volume:support_test_count>2" in result.score_reasons
    assert not any(r.startswith("volume:support_test_count>=") for r in result.score_reasons)
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

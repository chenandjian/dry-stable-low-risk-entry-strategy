from datetime import date, timedelta
from dataclasses import replace

from strategy6.engine import StrongVcpTailEngine
from strategy6.filters import classify_candidate
from strategy6.indicators import calculate_indicators
from strategy6.market import build_market_snapshot
from strategy6.models import (
    Strategy6BoxTail,
    Strategy6CompactKline,
    Strategy6DryTail,
    Strategy6Indicators,
    Strategy6Score,
    Strategy6TradePlan,
    Strategy6VcpObservation,
    Strategy6VcpQuality,
)
from strategy6.strong_start import evaluate_strong_start
from strategy6.scorer import _relative_strength_risk_score
from strategy6.validation import resolve_strategy6_config


def _row(i, close=10.0, open_price=None, high=None, low=None, volume=1_000_000, amount=600_000_000):
    day = date(2024, 1, 1) + timedelta(days=i)
    open_price = close * 0.995 if open_price is None else open_price
    return {
        "date": day.isoformat(),
        "open": round(open_price, 4),
        "high": round(high if high is not None else max(open_price, close) * 1.01, 4),
        "low": round(low if low is not None else min(open_price, close) * 0.99, 4),
        "close": round(close, 4),
        "volume": volume,
        "amount": amount,
    }


def build_strategy6_candidate_data(length=760):
    data = []
    for i in range(length):
        close = 10 + i * 0.008
        data.append(_row(i, close=close, volume=1_000_000, amount=650_000_000))

    base = data[-21]["close"]
    close = base * 1.12
    data[-20].update({
        "open": round(close * 0.96, 4),
        "high": round(close * 1.015, 4),
        "low": round(close * 0.955, 4),
        "close": round(close, 4),
        "volume": 2_600_000,
        "amount": 1_400_000_000,
    })

    pivot = data[-20]["close"]
    closes = [pivot * v for v in (
        0.90, 0.93, 0.96, 0.99, 1.02, 0.99, 0.96, 0.92, 0.96,
        0.97, 0.99, 1.01, 1.03, 1.05, 1.07, 1.06, 1.07, 1.08, 1.07,
    )]
    volumes = [
        1_600_000, 1_550_000, 1_450_000, 1_400_000, 1_300_000,
        1_250_000, 1_150_000, 1_100_000, 1_000_000,
        900_000, 850_000, 800_000, 750_000, 700_000,
        550_000, 500_000, 460_000, 430_000, 400_000,
    ]
    for j, close in enumerate(closes):
        data[-19 + j].update({
            "open": round(close * 0.998, 4),
            "high": round(close * 1.015, 4),
            "low": round(close * 0.985, 4),
            "close": round(close, 4),
            "volume": volumes[j],
            "amount": 1_200_000_000,
        })
    return data


def build_strategy6_pattern_candidate_data():
    data = build_strategy6_candidate_data()
    pivot = data[-20]["close"]
    factors = [
        1.02, 0.90, 1.00, 0.92, 0.99, 0.94, 0.985,
        0.95, 0.98, 0.96, 0.975, 0.965, 0.975, 0.97,
        0.972, 0.973, 0.974, 0.973, 0.974,
    ]
    volumes = [
        1_800_000, 1_700_000, 1_450_000, 1_350_000, 1_100_000,
        1_000_000, 800_000, 730_000, 580_000, 520_000, 410_000,
        370_000, 330_000, 300_000, 280_000, 260_000, 240_000,
        220_000, 200_000,
    ]
    for offset, (factor, volume) in enumerate(zip(factors, volumes)):
        close = pivot * factor
        data[-19 + offset].update({
            "open": round(close * 0.998, 4),
            "high": round(close * 1.01, 4),
            "low": round(close * 0.99, 4),
            "close": round(close, 4),
            "volume": volume,
            "amount": 1_200_000_000,
        })
    return data


def test_engine_outputs_full_candidate_trade_plan():
    result = StrongVcpTailEngine({}).evaluate_at(
        build_strategy6_candidate_data(),
        code="000001",
        name="平安银行",
        sector_name="银行",
    )
    candidate = result.to_candidate_dict()

    assert result.passed is True
    assert result.candidate_type in {"READY_CANDIDATE", "KEY_CANDIDATE", "WATCH_CANDIDATE"}
    assert result.start.start_type in {"NORMAL_STRONG_BREAKOUT", "VOLUME_LIMIT_UP", "LOW_VOLUME_LIMIT_UP", "ONE_WORD_LIMIT_UP"}
    assert result.start.start_grade in {"S", "A", "B"}
    assert result.start.high_trigger in {"near_120d_high", "new_120d_high"}
    assert result.support.support_status in {
        "PATTERN_SUPPORT",
        "MA5_SUPPORT",
        "MA10_SUPPORT",
        "MA20_SUPPORT",
        "MA50_TESTING",
        "KEY_SUPPORT_VALID",
    }
    assert candidate["key_support_price"] > 0
    assert candidate["support_zone_low"] < candidate["support_zone_high"]
    assert candidate["suggested_buy_price"] is not None
    assert candidate["stop_loss_price"] < candidate["suggested_buy_price"]
    assert candidate["target_price_1"] > candidate["suggested_buy_price"]
    assert candidate["target_price_2"] > candidate["suggested_buy_price"]
    assert candidate["target_price_3"] > candidate["suggested_buy_price"]
    assert candidate["risk_reward_ratio_2"] >= 1.5
    assert 0 <= candidate["total_score"] <= 100
    assert candidate["lifecycle_status"] in {"READY", "BUY_ZONE", "SETUP_FORMING", "BREAKOUT_CONFIRMED", "EXTENDED"}
    assert candidate["sector_name"] == "银行"
    assert candidate["original_tail_pass"] == result.dry_tail.dry_tail_pass
    assert candidate["original_tail_score"] == result.dry_tail.dry_stable_score
    assert candidate["box_tail_enabled"] is True
    assert candidate["tail_pass"] == bool(candidate["tail_paths"])
    assert candidate["tail_path"] in {"ORIGINAL", "BOX", "BOTH", "NONE"}
    assert candidate["start_event_quality_score"] >= 0
    assert candidate["start_follow_through_return_5"] >= -1
    assert candidate["start_gain_retention_ratio"] >= 0
    assert candidate["start_max_close_drawdown_5"] <= 0
    assert isinstance(candidate["start_failure_reasons"], list)
    assert candidate["tail_segmentation_status"]
    assert candidate["tail_segmentation_score"] >= 0
    assert candidate["setup_quality_score"] >= 0
    assert candidate["support_reaction_score"] >= 0
    assert candidate["path_evidence_score"] >= 0
    assert candidate["entry_archetype"] in {
        "SUPPORT_PULLBACK", "PIVOT_BREAKOUT", "FAILED_BREAKOUT_RECLAIM",
        "WAIT_BREAKOUT", "NONE",
    }
    assert candidate["score_model_version"] == "S6_QUALITY_V2"


def test_engine_candidate_dict_exposes_safe_vcp_observation_defaults():
    result = StrongVcpTailEngine({
        "strategy6": {"vcp_observer_enabled": False},
    }).evaluate_at(
        build_strategy6_candidate_data(),
        code="000001",
        name="平安银行",
    )

    candidate = result.to_candidate_dict()

    assert candidate["vcp_observation_eligible"] is False
    assert candidate["vcp_lifecycle_status"] == "VCP_NONE"
    assert candidate["vcp_origin_start_date"] == ""
    assert candidate["vcp_pattern_start_date"] == ""
    assert candidate["vcp_pattern_end_date"] == ""
    assert candidate["vcp_contraction_count"] == 0
    assert candidate["vcp_contractions"] == []
    assert candidate["vcp_pivot_price"] == 0.0
    assert candidate["vcp_structure_low"] == 0.0
    assert candidate["vcp_distance_to_pivot_pct"] == 0.0
    assert candidate["vcp_breakout_date"] == ""
    assert candidate["vcp_days_since_breakout"] == 0
    assert candidate["vcp_observation_reasons"] == []
    assert candidate["vcp_observation_risk_tags"] == []
    assert candidate["vcp_invalidation_reason"] == ""


def test_vcp_observation_is_orthogonal_to_main_strategy_decision(monkeypatch):
    import strategy6.engine as engine_mod

    data = build_strategy6_candidate_data()
    monkeypatch.setattr(
        engine_mod,
        "evaluate_vcp_observation",
        lambda rows, config, **kwargs: Strategy6VcpObservation(),
        raising=False,
    )
    baseline = StrongVcpTailEngine({}).evaluate_at(data, code="000001")

    monkeypatch.setattr(
        engine_mod,
        "evaluate_vcp_observation",
        lambda rows, config, **kwargs: Strategy6VcpObservation(
            eligible=True,
            lifecycle_status="VCP_EXTENDED",
            pivot_price=12.0,
            structure_low=10.0,
            risk_tags=["VCP_PRICE_EXTENDED"],
        ),
        raising=False,
    )
    observed = StrongVcpTailEngine({}).evaluate_at(data, code="000001")

    assert observed.vcp_observation.lifecycle_status == "VCP_EXTENDED"
    assert observed.pattern == baseline.pattern
    assert observed.score == baseline.score
    assert observed.candidate_type == baseline.candidate_type
    assert observed.classification == baseline.classification
    assert observed.reject_reasons == baseline.reject_reasons
    assert observed.trade_plan == baseline.trade_plan


def test_vcp_quality_is_serialized_but_does_not_change_main_strategy(monkeypatch):
    import strategy6.engine as engine_mod

    data = build_strategy6_candidate_data()
    monkeypatch.setattr(
        engine_mod,
        "evaluate_vcp_observation",
        lambda rows, config, **kwargs: Strategy6VcpObservation(
            eligible=True,
            lifecycle_status="VCP_NEAR_PIVOT",
        ),
    )
    monkeypatch.setattr(
        engine_mod,
        "evaluate_vcp_quality",
        lambda rows, current: Strategy6VcpQuality(
            scored=True,
            score=94,
            grade="TOP",
            contraction_score=17,
            range_score=23,
            volume_score=24,
            low_score=15,
            time_score=10,
            pivot_score=5,
            reasons=["VCP_QUALITY_RANGE_TIGHT"],
            warnings=[],
            model_version="VCP_QUALITY_V1",
        ),
        raising=False,
    )
    high = StrongVcpTailEngine({}).evaluate_at(data, code="000001")

    monkeypatch.setattr(
        engine_mod,
        "evaluate_vcp_quality",
        lambda rows, current: Strategy6VcpQuality(
            scored=True,
            score=41,
            grade="WEAK",
            model_version="VCP_QUALITY_V1",
        ),
        raising=False,
    )
    low = StrongVcpTailEngine({}).evaluate_at(data, code="000001")

    assert high.candidate_type == low.candidate_type
    assert high.classification == low.classification
    assert high.reject_reasons == low.reject_reasons
    assert high.score == low.score
    assert high.trade_plan == low.trade_plan
    assert high.vcp_observation.eligible == low.vcp_observation.eligible
    high_candidate = high.to_candidate_dict()
    low_candidate = low.to_candidate_dict()
    assert high_candidate["vcp_quality_score"] == 94
    assert high_candidate["vcp_quality_grade"] == "TOP"
    assert high_candidate["vcp_quality_model_version"] == "VCP_QUALITY_V1"
    assert low_candidate["vcp_quality_score"] == 41
    assert low_candidate["vcp_quality_grade"] == "WEAK"


def test_vcp_observation_does_not_bypass_strategy6_data_and_liquidity_floor(monkeypatch):
    import strategy6.engine as engine_mod

    monkeypatch.setattr(
        engine_mod,
        "evaluate_vcp_observation",
        lambda rows, config, **kwargs: Strategy6VcpObservation(
            eligible=True,
            lifecycle_status="VCP_NEAR_PIVOT",
            pivot_price=12.0,
            structure_low=10.0,
        ),
    )
    result = StrongVcpTailEngine({
        "strategy6": {
            "min_avg_amount_60d_yi": 100,
            "min_avg_amount_30d_yi": 100,
            "min_avg_amount_10d_yi": 100,
        },
    }).evaluate_at(build_strategy6_candidate_data(), code="000001")

    assert result.vcp_observation.eligible is False
    assert result.vcp_observation.lifecycle_status == "VCP_NONE"
    assert "VCP_BASE_FILTER_FAILED" in result.vcp_observation.risk_tags
    assert "AVG60D_LT_MIN" in result.vcp_observation.risk_tags


def test_engine_outputs_brooks_and_authoritative_three_path_fields():
    result = StrongVcpTailEngine({}).evaluate_at(
        build_strategy6_candidate_data(),
        code="000001",
        name="平安银行",
    )
    candidate = result.to_candidate_dict()

    assert isinstance(candidate["tail_paths"], list)
    assert candidate["tail_path_summary"] in {"NONE", "ORIGINAL", "BOX", "BROOKS", "MULTI"}
    assert candidate["tail_primary_path"] in {"NONE", "ORIGINAL", "BOX", "BROOKS"}
    assert candidate["tail_pass"] == bool(candidate["tail_paths"])
    assert candidate["tail_score"] == candidate["path_evidence_score"]
    assert 0 <= candidate["tail_score"] <= 15
    assert candidate["brooks_status"]
    assert isinstance(candidate["brooks_result"], dict)


def test_engine_candidate_dict_exposes_authoritative_brooks_trigger_price():
    from strategy6.brooks.models import BrooksTradeTriggerResult

    result = StrongVcpTailEngine({}).evaluate_at(
        build_strategy6_candidate_data(),
        code="000001",
        name="平安银行",
    )
    result.brooks_tail.trade_trigger = BrooksTradeTriggerResult(
        ready=True,
        trigger_type="BROOKS_FAILED_BREAKOUT_READY",
        trigger_price=12.34,
        trigger_valid_until="2026-07-20",
    )

    candidate = result.to_candidate_dict()

    assert candidate["brooks_trigger_price"] == 12.34
    assert candidate["brooks_result"]["trade_trigger"]["trigger_price"] == 12.34


def test_engine_brooks_disabled_preserves_legacy_two_path_summary():
    result = StrongVcpTailEngine({
        "strategy6": {"brooks_tail": {"enabled": False}},
    }).evaluate_at(build_strategy6_candidate_data(), code="000001")
    candidate = result.to_candidate_dict()

    assert candidate["brooks_tail_enabled"] is False
    assert candidate["brooks_tail_pass"] is False
    assert candidate["brooks_tail_score"] == 0
    assert candidate["tail_path"] in {"NONE", "ORIGINAL", "BOX", "BOTH"}
    assert candidate["tail_paths"] == [
        path for path, passed in (
            ("ORIGINAL", candidate["original_tail_pass"]),
            ("BOX", candidate["box_tail_pass"]),
        ) if passed
    ]
    assert candidate["tail_pass"] == (candidate["original_tail_pass"] or candidate["box_tail_pass"])


def test_engine_brooks_only_waiting_candidate_dict_has_no_ready_or_buy_semantics(monkeypatch):
    from strategy6.brooks.models import BrooksTailResult, BrooksTradeTriggerResult
    import strategy6.engine as engine_mod

    monkeypatch.setattr(
        engine_mod,
        "evaluate_dry_tail",
        lambda *args, **kwargs: Strategy6DryTail(
            dry_tail_pass=False,
            dry_stable_score=8,
            tail_volume_ratio=0.55,
        ),
    )
    monkeypatch.setattr(
        engine_mod,
        "evaluate_box_tail",
        lambda *args, **kwargs: Strategy6BoxTail(
            enabled=True,
            passed=False,
            score=10,
            compact_kline=Strategy6CompactKline(enabled=True, passed=True),
        ),
    )
    monkeypatch.setattr(
        engine_mod,
        "analyze_brooks_tail",
        lambda *args, **kwargs: BrooksTailResult(
            enabled=True,
            passed=True,
            score=18,
            status="SECOND_ENTRY_LONG_READY",
        ),
    )
    monkeypatch.setattr(
        engine_mod,
        "evaluate_brooks_trade_trigger",
        lambda *args, **kwargs: BrooksTradeTriggerResult(ready=False),
    )
    monkeypatch.setattr(
        engine_mod,
        "calculate_trade_plan",
        lambda indicators, support, config, **kwargs: Strategy6TradePlan(
            objective_rr_2=3.0,
            suggested_buy_price=indicators.current_price,
        ),
    )
    monkeypatch.setattr(
        engine_mod,
        "score_strategy6",
        lambda *args, **kwargs: Strategy6Score(total_score=95, tail_score=18),
    )

    result = StrongVcpTailEngine({"strategy6": {"enable_market_filter": False}}).evaluate_at(
        build_strategy6_candidate_data(),
        code="000001",
        name="平安银行",
    )
    candidate = result.to_candidate_dict()

    assert candidate["tail_paths"] == ["BROOKS"]
    assert candidate["brooks_trade_ready"] is False
    assert candidate["candidate_type"] == "WATCH_CANDIDATE"
    assert candidate["classification"] == "observe"
    assert candidate["lifecycle_status"] == "SETUP_FORMING"
    assert "等待触发" in candidate["suggestion"]


def test_rr2_below_minimum_rejects_candidate():
    data = build_strategy6_candidate_data()
    for row in data[-20:]:
        row["high"] = round(row["close"] * 1.004, 4)
        row["low"] = round(row["close"] * 0.99, 4)
    cfg = {
        "strategy6": {
            "rr2_min_watch": 4.0,
            "rr2_min_key": 4.5,
            "rr2_min_ready": 5.0,
        }
    }

    result = StrongVcpTailEngine(cfg).evaluate_at(data, code="000001", name="平安银行")

    assert result.passed is False
    assert result.candidate_type == "REJECTED"
    assert "RR2_LT_4_0" in result.reject_reasons


def test_big_down_volume_is_hard_rejected():
    data = build_strategy6_candidate_data()
    data[-1]["open"] = data[-2]["close"]
    data[-1]["close"] = round(data[-2]["close"] * 0.92, 4)
    data[-1]["high"] = round(data[-2]["close"] * 1.01, 4)
    data[-1]["low"] = round(data[-1]["close"] * 0.99, 4)
    data[-1]["volume"] = 3_000_000

    result = StrongVcpTailEngine({}).evaluate_at(data, code="000001", name="平安银行")

    assert result.passed is False
    assert "BIG_DOWN_VOLUME" in result.reject_reasons


def test_suspended_quote_reuses_history_but_cannot_become_candidate():
    result = StrongVcpTailEngine({}).evaluate_at(
        build_strategy6_candidate_data(),
        code="000001",
        name="平安银行",
        quote_status="suspended",
    )

    assert result.passed is False
    assert result.quote_status == "suspended"
    assert "LATEST_TRADE_SUSPENDED" in result.reject_reasons

    no_trade = StrongVcpTailEngine({}).evaluate_at(
        build_strategy6_candidate_data(),
        code="000001",
        quote_status="no_trade",
    )
    assert no_trade.passed is False
    assert "LATEST_TRADE_NO_TRADE" in no_trade.reject_reasons


def test_consolidation_limits_are_hard_filters_by_start_grade():
    data = build_strategy6_candidate_data()
    # S-grade start allows 25% range_5. This deliberately exceeds it while
    # staying below the absolute 50% range_10 floor, so the grade-specific
    # consolidation rule is the only reason to reject.
    base = data[-6]["close"]
    data[-5]["high"] = round(base * 1.16, 4)
    data[-5]["low"] = round(base * 0.88, 4)

    result = StrongVcpTailEngine({}).evaluate_at(data, code="000001", name="平安银行")

    assert result.passed is False
    assert "CONSOLIDATION_RANGE_5_GT_S_LIMIT" in result.reject_reasons


def test_support_requires_recent_valid_support_test():
    data = build_strategy6_candidate_data()
    # Keep MA20 support but make all recent lows stay well above the selected
    # support so "横盘必须有支撑测试" is not satisfied.
    for row in data[-10:]:
        row["open"] = round(row["close"] * 1.055, 4)
        row["low"] = round(row["close"] * 1.05, 4)
        row["high"] = round(row["close"] * 1.06, 4)

    result = StrongVcpTailEngine({}).evaluate_at(data, code="000001", name="平安银行")

    assert result.passed is False
    assert "NO_VALID_SUPPORT_TEST" in result.reject_reasons


def test_one_word_limit_up_without_followup_confirmation_is_watch_only():
    data = build_strategy6_candidate_data()
    idx = -3
    for offset in range(-5, 0):
        data[offset]["volume"] = 320_000 + (offset + 5) * 10_000
        data[offset]["amount"] = 1_200_000_000
    prev_close = data[idx - 1]["close"]
    limit_price = round(prev_close * 1.10, 2)
    data[idx].update({
        "open": limit_price,
        "high": limit_price,
        "low": limit_price,
        "close": limit_price,
        "volume": 300_000,
        "amount": 1_400_000_000,
    })
    for offset, multiplier in ((-2, 1.002), (-1, 1.003)):
        close = round(limit_price * multiplier, 4)
        data[offset].update({
            "open": round(close * 0.998, 4),
            "high": round(close * 1.01, 4),
            "low": round(close * 0.992, 4),
            "close": close,
            "volume": 260_000 if offset == -2 else 240_000,
            "amount": 1_200_000_000,
        })

    result = StrongVcpTailEngine({"strategy6": {"tail_close_range_5": 0.12}}).evaluate_at(data, code="000001", name="平安银行")
    candidate = result.to_candidate_dict()

    assert result.passed is True
    assert result.start.start_type == "ONE_WORD_LIMIT_UP"
    assert result.candidate_type == "WATCH_CANDIDATE"
    assert "ONE_WORD_LIMIT_UP_UNCONFIRMED" in candidate["warn_tags"]


def test_upper_shadow_pressure_downgrades_key_candidate_to_watch():
    engine = StrongVcpTailEngine({"strategy6": {"enable_market_filter": False}})
    result = engine.evaluate_at(build_strategy6_candidate_data(), code="000001", name="平安银行")
    result.indicators.current_price = (
        result.support.support_zone_low + result.support.support_zone_high
    ) / 2
    result.indicators.warn_tags = []
    result.score = replace(result.score, total_score=90, pattern_score_component=20)

    baseline_type, *_ = classify_candidate(
        result.indicators, result.start, result.phase, result.pattern, result.support,
        result.dry_tail, result.trade_plan, result.score, [], engine.config,
    )
    result.indicators.warn_tags = ["UPPER_SHADOW_PRESSURE"]
    pressured_type, *_ = classify_candidate(
        result.indicators, result.start, result.phase, result.pattern, result.support,
        result.dry_tail, result.trade_plan, result.score, [], engine.config,
    )

    assert baseline_type in {"READY_CANDIDATE", "KEY_CANDIDATE"}
    assert pressured_type == "WATCH_CANDIDATE"


def test_one_word_limit_up_confirmation_requires_close_above_start_low():
    data = build_strategy6_candidate_data()
    idx = -4
    prev_close = data[idx - 1]["close"]
    limit_price = round(prev_close * 1.10, 2)
    data[idx].update({
        "open": limit_price,
        "high": limit_price,
        "low": limit_price,
        "close": limit_price,
        "volume": 300_000,
        "amount": 1_400_000_000,
    })
    for offset, multiplier in ((-3, 0.996), (-2, 0.994), (-1, 0.993)):
        close = round(limit_price * multiplier, 4)
        data[offset].update({
            "open": round(close * 0.998, 4),
            "high": round(close * 1.006, 4),
            "low": round(close * 0.99, 4),
            "close": close,
            "volume": 220_000,
            "amount": 1_200_000_000,
        })

    result = StrongVcpTailEngine({"strategy6": {"tail_close_range_5": 0.12}}).evaluate_at(data, code="000001", name="平安银行")
    candidate = result.to_candidate_dict()

    assert result.start.start_type == "ONE_WORD_LIMIT_UP"
    assert result.start.days_since_start >= 3
    assert result.passed is True
    assert result.candidate_type == "WATCH_CANDIDATE"
    assert "ONE_WORD_LIMIT_UP_UNCONFIRMED" in candidate["warn_tags"]


def test_breakout_confirmation_requires_quality_breakout_not_extended_chase():
    data = build_strategy6_pattern_candidate_data()
    current = data[-1]["close"]
    for row in data[-20:-1]:
        row["high"] = round(current * 1.005, 4)
        row["close"] = round(min(row["close"], current * 1.002), 4)
    pivot = max(row["close"] for row in data[-20:-1])
    data[-1].update({
        "open": round(pivot * 1.05, 4),
        "high": round(pivot * 1.105, 4),
        "low": round(pivot * 1.04, 4),
        "close": round(pivot * 1.09, 4),
        "volume": 900_000,
    })

    result = StrongVcpTailEngine({"strategy6": {"tail_close_range_5": 0.12}}).evaluate_at(data, code="000001", name="平安银行")

    assert result.lifecycle_status != "BREAKOUT_CONFIRMED"
    assert result.passed is False


def test_close_below_key_support_shape_failure_marks_failed():
    data = build_strategy6_candidate_data()
    initial = StrongVcpTailEngine({}).evaluate_at(data, code="000001", name="平安银行")
    key_support = initial.support.key_support_price
    for offset, multiplier in ((-2, 0.965), (-1, 0.955)):
        data[offset].update({
            "open": round(key_support * (multiplier + 0.004), 4),
            "high": round(key_support * (multiplier + 0.01), 4),
            "low": round(key_support * (multiplier - 0.01), 4),
            "close": round(key_support * multiplier, 4),
            "volume": 430_000,
        })

    result = StrongVcpTailEngine({}).evaluate_at(data, code="000001", name="平安银行")

    assert result.passed is False
    assert result.lifecycle_status == "FAILED"
    assert "CLOSE_LT_KEY_SUPPORT_0_96" in result.reject_reasons


def test_b_grade_strong_start_is_watch_only_even_with_high_score():
    data = build_strategy6_candidate_data()
    engine = StrongVcpTailEngine({})
    result = engine.evaluate_at(data, code="000001", name="平安银行")
    b_start = replace(result.start, start_type="B_GRADE_MOMENTUM", start_grade="B")

    candidate_type, *_ = classify_candidate(
        result.indicators,
        b_start,
        result.phase,
        result.pattern,
        result.support,
        result.dry_tail,
        result.trade_plan,
        result.score,
        [],
        engine.config,
    )

    assert result.trade_plan.objective_rr_2 >= engine.config["rr2_min_ready"]
    assert candidate_type == "WATCH_CANDIDATE"


def test_upper_shadow_pressure_deducts_risk_control_score():
    data = build_strategy6_candidate_data()
    clean = StrongVcpTailEngine({}).evaluate_at(data, code="000001", name="平安银行")
    pressure = data[-8]
    pressure["high"] = round(data[-1]["close"] * 1.02, 4)
    pressure["open"] = round(pressure["high"] * 0.90, 4)
    pressure["close"] = round(pressure["high"] * 0.91, 4)
    pressure["low"] = round(pressure["high"] * 0.89, 4)
    pressure["volume"] = 2_000_000

    pressured = StrongVcpTailEngine({}).evaluate_at(data, code="000001", name="平安银行")

    assert "UPPER_SHADOW_PRESSURE" in pressured.indicators.warn_tags
    assert pressured.score.risk_control_score == max(0, clean.score.risk_control_score - 2)


def test_close_below_ma5_is_not_marked_ma5_support():
    data = build_strategy6_candidate_data()
    data[-1]["close"] = round(data[-1]["close"] * 0.96, 4)

    result = StrongVcpTailEngine({}).evaluate_at(data, code="000001", name="平安银行")

    assert result.support.support_status != "MA5_SUPPORT"


def test_config_rejects_invalid_filter_mode():
    try:
        resolve_strategy6_config({"strategy6": {"market_filter_mode": "invalid"}})
    except ValueError as exc:
        assert "market_filter_mode" in str(exc)
    else:
        raise AssertionError("invalid market_filter_mode should fail")


def test_strategy6_defaults_enable_real_market_filter_only():
    cfg = resolve_strategy6_config({})

    assert cfg["enable_market_filter"] is True
    assert cfg["market_filter_mode"] == "downgrade"
    assert "enable_sector_filter" not in cfg
    assert "sector_filter_mode" not in cfg
    assert "sector_min_member_new_high_count" not in cfg
    assert cfg["min_relative_strength_20"] == 0.10
    assert cfg["breakout_extended_max_pct"] == 0.08


def _market_rows(closes, end_date=date(2026, 1, 29)):
    rows = []
    start_date = end_date - timedelta(days=len(closes) - 1)
    for i, close in enumerate(closes):
        rows.append({
            "date": (start_date + timedelta(days=i)).isoformat(),
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": 1_000_000 + i * 1000,
        })
    return rows


def test_market_filter_off_reports_weak_market_without_downgrading():
    data = build_strategy6_candidate_data()
    weak_market = {
        "sh000001": _market_rows([120 - i * 0.2 for i in range(80)]),
        "sz399001": _market_rows([130 - i * 0.2 for i in range(80)]),
        "sz399006": _market_rows([140 - i * 0.2 for i in range(80)]),
    }

    result = StrongVcpTailEngine({"strategy6": {"enable_market_filter": False}}).evaluate_at(
        data,
        code="000001",
        name="平安银行",
        market_data_by_symbol=weak_market,
    )
    candidate = result.to_candidate_dict()

    assert result.passed is True
    assert candidate["market_status"] == "MARKET_WEAK"
    assert candidate["enable_market_filter"] is False
    assert "MARKET_WEAK_DOWNGRADED" not in candidate["warn_tags"]
    assert "MARKET_WEAK_STRICT" not in candidate["warn_tags"]


def test_market_filter_downgrade_moves_ready_or_key_to_watch():
    data = build_strategy6_candidate_data()
    weak_market = {
        "sh000001": _market_rows([120 - i * 0.2 for i in range(80)]),
        "sz399001": _market_rows([130 - i * 0.2 for i in range(80)]),
        "sz399006": _market_rows([140 - i * 0.2 for i in range(80)]),
    }

    result = StrongVcpTailEngine({"strategy6": {"enable_market_filter": True, "market_filter_mode": "downgrade"}}).evaluate_at(
        data,
        code="000001",
        name="平安银行",
        market_data_by_symbol=weak_market,
    )
    candidate = result.to_candidate_dict()

    assert result.passed is True
    assert result.candidate_type == "WATCH_CANDIDATE"
    assert candidate["classification"] == "observe"
    assert candidate["market_status"] == "MARKET_WEAK"
    assert candidate["enable_market_filter"] is True
    assert "MARKET_WEAK_DOWNGRADED" in candidate["warn_tags"]


def test_market_filter_score_only_deducts_score_without_downgrading_candidate_type():
    data = build_strategy6_candidate_data()
    weak_market = {
        "sh000001": _market_rows([120 - i * 0.2 for i in range(80)]),
        "sz399001": _market_rows([130 - i * 0.2 for i in range(80)]),
        "sz399006": _market_rows([140 - i * 0.2 for i in range(80)]),
    }

    score_only = StrongVcpTailEngine({"strategy6": {"enable_market_filter": True, "market_filter_mode": "score_only"}}).evaluate_at(
        data,
        code="000001",
        name="平安银行",
        market_data_by_symbol=weak_market,
    )
    filter_off = StrongVcpTailEngine({"strategy6": {"enable_market_filter": False, "market_filter_mode": "score_only"}}).evaluate_at(
        data,
        code="000001",
        name="平安银行",
        market_data_by_symbol=weak_market,
    )

    assert score_only.passed is True
    assert score_only.candidate_type == filter_off.candidate_type
    assert score_only.score.risk_control_score == max(0, filter_off.score.risk_control_score - 2)
    assert "MARKET_WEAK_DOWNGRADED" not in score_only.indicators.warn_tags


def test_relative_strength_20_is_reported_against_hs300_index():
    data = build_strategy6_candidate_data()
    market = {
        "hs300": _market_rows([100 + i * 0.02 for i in range(80)]),
    }

    result = StrongVcpTailEngine({}).evaluate_at(
        data,
        code="000001",
        name="平安银行",
        market_data_by_symbol=market,
    )
    candidate = result.to_candidate_dict()

    assert candidate["relative_strength_20"] > 0.10


def test_relative_strength_20_below_minimum_rejects_candidate():
    data = build_strategy6_candidate_data()
    market = {
        "hs300": _market_rows([100 * (1.015 ** i) for i in range(80)]),
    }

    result = StrongVcpTailEngine({}).evaluate_at(
        data,
        code="000001",
        name="平安银行",
        market_data_by_symbol=market,
    )

    assert result.passed is False
    assert "RS20_LT_0_1" in result.reject_reasons


def test_missing_market_data_does_not_apply_rs20_filter():
    data = build_strategy6_candidate_data()

    result = StrongVcpTailEngine({}).evaluate_at(
        data,
        code="000001",
        name="平安银行",
    )
    candidate = result.to_candidate_dict()

    assert result.passed is True
    assert candidate["relative_strength_20_observed"] is False
    assert "RS20_LT_0_1" not in result.reject_reasons


def test_stale_hs300_does_not_apply_relative_strength_filter():
    data = build_strategy6_candidate_data()
    stale_hs300 = {
        "hs300": _market_rows(
            [100 + i * 0.02 for i in range(80)],
            end_date=date(2026, 1, 28),
        ),
    }

    result = StrongVcpTailEngine({}).evaluate_at(
        data,
        code="000001",
        market_data_by_symbol=stale_hs300,
    )

    assert result.indicators.relative_strength_20_observed is False
    assert result.indicators.relative_strength_20 == 0
    assert "RS20_LT_0_1" not in result.reject_reasons


def test_relative_strength_does_not_fallback_to_shanghai_index():
    result = StrongVcpTailEngine({}).evaluate_at(
        build_strategy6_candidate_data(),
        code="000001",
        market_data_by_symbol={
            "sh000001": _market_rows([100 + i * 0.02 for i in range(80)]),
        },
    )

    assert result.indicators.relative_strength_20_observed is False
    assert result.indicators.relative_strength_20 == 0


def test_market_snapshot_keeps_hs300_return_when_broad_indexes_are_missing():
    snapshot = build_market_snapshot(
        {"hs300": _market_rows([100 + i * 0.1 for i in range(80)])},
        expected_trade_date="2026-01-29",
    )

    assert snapshot["market_status"] == "UNKNOWN"
    assert snapshot["market_return_20"] > 0


def test_partial_broad_market_data_is_unknown_not_neutral():
    snapshot = build_market_snapshot(
        {
            "sh000001": _market_rows([100 + i * 0.1 for i in range(80)]),
            "hs300": _market_rows([100 + i * 0.05 for i in range(80)]),
        },
        expected_trade_date="2026-01-29",
    )

    assert snapshot["market_status"] == "UNKNOWN"
    assert "MARKET_DATA_PARTIAL" in snapshot["market_reasons"]


def test_two_fresh_broad_indexes_are_enough_for_market_context():
    snapshot = build_market_snapshot(
        {
            "sh000001": _market_rows([100 + i * 0.1 for i in range(80)]),
            "sz399001": _market_rows([120 + i * 0.1 for i in range(80)]),
            "hs300": _market_rows([100 + i * 0.05 for i in range(80)]),
        },
        expected_trade_date="2026-01-29",
    )

    assert snapshot["market_status"] in {"MARKET_STRONG", "MARKET_NEUTRAL", "MARKET_WEAK", "MARKET_RISK"}


def test_market_filter_blocks_key_ready_when_hs300_is_missing():
    broad_market = {
        symbol: _market_rows([100 + i * 0.05 for i in range(80)])
        for symbol in ("sh000001", "sz399001", "sz399006")
    }
    engine = StrongVcpTailEngine({})
    result = engine.evaluate_at(
        build_strategy6_candidate_data(),
        code="000001",
        market_data_by_symbol=broad_market,
    )
    result.indicators.warn_tags = []
    result.indicators.current_price = (
        result.support.support_zone_low + result.support.support_zone_high
    ) / 2
    result.score = replace(result.score, total_score=95)

    candidate_type, *_ = classify_candidate(
        result.indicators, result.start, result.phase, result.pattern, result.support,
        result.dry_tail, result.trade_plan, result.score, [], engine.config,
    )

    assert result.indicators.market_status != "UNKNOWN"
    assert result.indicators.relative_strength_20_observed is False
    assert candidate_type == "WATCH_CANDIDATE"
    assert "RS20_DATA_UNAVAILABLE" in result.indicators.warn_tags


def test_missing_market_data_cannot_receive_relative_strength_points():
    score = _relative_strength_risk_score(
        Strategy6Indicators(
            relative_strength_20=0.20,
            relative_strength_20_observed=False,
        )
    )

    assert score == 5


def test_enabled_market_filter_prevents_key_or_ready_without_market_data():
    engine = StrongVcpTailEngine({})
    result = engine.evaluate_at(build_strategy6_candidate_data(), code="000001", name="平安银行")
    result.indicators.warn_tags = []
    result.indicators.current_price = (
        result.support.support_zone_low + result.support.support_zone_high
    ) / 2

    candidate_type, *_ = classify_candidate(
        result.indicators,
        result.start,
        result.phase,
        result.pattern,
        result.support,
        result.dry_tail,
        result.trade_plan,
        result.score,
        [],
        engine.config,
    )

    assert candidate_type == "WATCH_CANDIDATE"
    assert "MARKET_DATA_UNAVAILABLE" in result.indicators.warn_tags


def test_signal_day_breakout_reaches_breakout_confirmed_lifecycle():
    data = build_strategy6_pattern_candidate_data()
    engine = StrongVcpTailEngine({"strategy6": {"enable_market_filter": False}})
    pivot = engine.evaluate_at(data, code="000001").pattern.pivot_price
    prior_volume = sum(row["volume"] for row in data[-21:-1]) / 20
    data[-1].update({
        "open": round(pivot * 0.995, 4),
        "high": round(pivot * 1.025, 4),
        "low": round(pivot * 0.99, 4),
        "close": round(pivot * 1.02, 4),
        "volume": round(prior_volume * 1.5),
    })

    result = engine.evaluate_at(data, code="000001")

    assert result.pattern.pivot_price == pivot
    assert result.indicators.current_volume_ratio_20 >= 1.3
    assert result.lifecycle_status == "BREAKOUT_CONFIRMED"


def test_signal_day_extended_breakout_reaches_extended_lifecycle():
    data = build_strategy6_pattern_candidate_data()
    engine = StrongVcpTailEngine({"strategy6": {"enable_market_filter": False}})
    pivot = engine.evaluate_at(data, code="000001").pattern.pivot_price
    data[-1].update({
        "open": round(pivot * 1.07, 4),
        "high": round(pivot * 1.11, 4),
        "low": round(pivot * 1.06, 4),
        "close": round(pivot * 1.09, 4),
    })

    result = engine.evaluate_at(data, code="000001")

    assert result.lifecycle_status == "EXTENDED"


def test_unknown_pattern_can_pass_when_filter_is_disabled_or_score_only():
    data = build_strategy6_candidate_data()
    unknown_pattern = {
        "vcp_min_first_range": 0.50,
        "cup_depth_min": 0.40,
        "cup_depth_max": 0.50,
        "platform_max_range": 0.01,
        "enable_market_filter": False,
    }

    disabled = StrongVcpTailEngine({
        "strategy6": {
            **unknown_pattern,
            "pattern_filter_enabled": False,
        }
    }).evaluate_at(data, code="000001")
    score_only = StrongVcpTailEngine({
        "strategy6": {
            **unknown_pattern,
            "pattern_filter_enabled": True,
            "pattern_filter_mode": "score_only",
        }
    }).evaluate_at(data, code="000001")

    for result in (disabled, score_only):
        assert result.pattern.pattern_type == "UNKNOWN"
        assert result.trade_plan.objective_rr_2 >= 1.5
        assert result.passed is True
        assert not any(reason.startswith("PATTERN_UNKNOWN") for reason in result.reject_reasons)
        assert not any(reason.startswith("RR2_LT_") for reason in result.reject_reasons)


def test_newer_strong_start_restarts_the_setup_event():
    data = build_strategy6_candidate_data()
    newer = len(data) - 8
    previous_close = data[newer - 1]["close"]
    close = previous_close * 1.10
    data[newer].update({
        "open": round(previous_close * 1.02, 4),
        "high": round(close, 4),
        "low": round(previous_close * 1.01, 4),
        "close": round(close, 4),
        "volume": 5_000_000,
        "amount": 1_500_000_000,
    })
    engine = StrongVcpTailEngine({})
    rows, ind = calculate_indicators(data, engine.config)

    start = evaluate_strong_start(rows, ind, engine.config, "000001")

    assert start.start_date == rows[newer]["date"]
    assert start.days_since_start == 7


def test_strong_start_grade_uses_event_local_data_not_evaluation_returns():
    data = [_row(i, close=10.0, volume=1_000_000, amount=500_000_000) for i in range(300)]
    idx = len(data) - 20
    data[idx].update({
        "open": 10.1, "high": 10.82, "low": 10.0, "close": 10.8,
        "volume": 3_000_000, "amount": 1_500_000_000,
    })
    for offset in range(1, 20):
        data[idx + offset].update({
            "open": 10.79, "high": 10.85, "low": 10.75, "close": 10.82,
            "volume": 800_000, "amount": 800_000_000,
        })
    engine = StrongVcpTailEngine({})
    rows, ind = calculate_indicators(data, engine.config)

    positive_returns = replace(ind, return_5=0.20, return_10=0.30, return_20=0.50)
    negative_returns = replace(ind, return_5=-0.50, return_10=-0.50, return_20=-0.50)
    baseline = evaluate_strong_start(rows, positive_returns, engine.config, "000001")
    repeated = evaluate_strong_start(rows, negative_returns, engine.config, "000001")

    assert repeated.start_date == baseline.start_date
    assert repeated.start_grade == baseline.start_grade
    assert repeated.event_quality_score == baseline.event_quality_score


def test_low_quality_new_start_does_not_replace_intact_high_quality_event():
    data = [_row(i, close=10.0, volume=1_000_000, amount=500_000_000) for i in range(300)]
    older = len(data) - 30
    data[older].update({
        "open": 10.1, "high": 10.82, "low": 10.0, "close": 10.8,
        "volume": 3_500_000, "amount": 1_500_000_000,
    })
    for offset in range(1, 22):
        data[older + offset].update({
            "open": 10.78, "high": 10.86, "low": 10.74, "close": 10.82,
            "volume": 800_000, "amount": 800_000_000,
        })
    newer = len(data) - 8
    previous_close = data[newer - 1]["close"]
    close = previous_close * 1.08
    data[newer].update({
        "open": round(previous_close * 1.01, 4),
        "high": round(close * 1.001, 4),
        "low": round(previous_close, 4),
        "close": round(close, 4),
        "volume": 5_000_000,
        "amount": 1_500_000_000,
    })
    for offset in range(1, 6):
        retraced = previous_close * (1.01 - offset * 0.003)
        data[newer + offset].update({
            "open": round(retraced * 1.002, 4),
            "high": round(retraced * 1.006, 4),
            "low": round(retraced * 0.994, 4),
            "close": round(retraced, 4),
            "volume": 1_500_000,
            "amount": 1_000_000_000,
        })
    engine = StrongVcpTailEngine({})
    rows, ind = calculate_indicators(data, engine.config)

    start = evaluate_strong_start(rows, ind, engine.config, "000001")

    assert start.start_date == rows[older]["date"]
    assert "START_GAIN_FULLY_RETRACED" not in start.failure_reasons


def test_normal_start_requires_two_yi_and_top_ten_percent_self_amount():
    data = build_strategy6_candidate_data()
    idx = len(data) - 10
    previous_close = data[idx - 1]["close"]
    close = previous_close * 1.08
    data[idx].update({
        "open": round(previous_close * 1.01, 4),
        "high": round(close * 1.005, 4),
        "low": round(previous_close, 4),
        "close": round(close, 4),
        "volume": 5_000_000,
        "amount": 2_000_000_000,
    })
    engine = StrongVcpTailEngine({})
    rows, ind = calculate_indicators(data, engine.config)

    start = evaluate_strong_start(rows, ind, engine.config, "000001")

    assert start.start_date == rows[idx]["date"]
    assert start.start_type == "NORMAL_STRONG_BREAKOUT"
    assert start.start_day_amount >= 2
    assert start.start_day_self_amount_percentile >= 0.90

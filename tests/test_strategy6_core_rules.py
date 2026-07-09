from datetime import date, timedelta

from strategy6.engine import StrongVcpTailEngine
from strategy6.sector import evaluate_sector_context
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
    closes = [pivot * v for v in (0.99, 1.005, 0.995, 1.0, 0.992, 1.003, 0.998, 1.001, 0.997, 1.002,
                                  0.999, 1.004, 1.0, 1.003, 1.001, 1.002, 1.000, 1.003, 1.001)]
    volumes = [1_400_000, 1_300_000, 1_200_000, 1_100_000, 1_000_000,
               950_000, 900_000, 850_000, 800_000, 760_000,
               720_000, 680_000, 640_000, 600_000, 560_000,
               520_000, 500_000, 480_000, 460_000, 440_000]
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
    assert result.support.support_status in {"MA5_SUPPORT", "MA10_SUPPORT", "MA20_SUPPORT", "MA50_TESTING"}
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
    data = build_strategy6_candidate_data()
    pressure = data[-8]
    pressure["high"] = round(data[-1]["close"] * 1.02, 4)
    pressure["open"] = round(pressure["high"] * 0.90, 4)
    pressure["close"] = round(pressure["high"] * 0.91, 4)
    pressure["low"] = round(pressure["high"] * 0.89, 4)
    pressure["volume"] = 2_000_000

    result = StrongVcpTailEngine({}).evaluate_at(data, code="000001", name="平安银行")
    candidate = result.to_candidate_dict()

    assert result.passed is True
    assert result.candidate_type == "WATCH_CANDIDATE"
    assert "UPPER_SHADOW_PRESSURE" in candidate["warn_tags"]


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
    data = build_strategy6_candidate_data()
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
    base = data[-21]["close"]
    close = base * 1.03
    data[-20].update({
        "open": round(close * 0.995, 4),
        "high": round(close * 1.015, 4),
        "low": round(close * 0.985, 4),
        "close": round(close, 4),
        "volume": 1_200_000,
        "amount": 1_400_000_000,
    })
    pivot = data[-20]["close"]
    closes = [pivot * v for v in (1.06, 1.08, 1.10, 1.12, 1.135, 1.15, 1.16, 1.17, 1.178, 1.184,
                                  1.188, 1.191, 1.194, 1.197, 1.199, 1.201, 1.202, 1.203, 1.204)]
    volumes = [1_400_000, 1_300_000, 1_200_000, 1_100_000, 1_000_000,
               950_000, 900_000, 850_000, 800_000, 760_000,
               720_000, 680_000, 640_000, 600_000, 560_000,
               520_000, 500_000, 480_000, 460_000]
    for j, close in enumerate(closes):
        data[-19 + j].update({
            "open": round(close * 0.998, 4),
            "high": round(close * 1.01, 4),
            "low": round(close * 0.985, 4),
            "close": round(close, 4),
            "volume": volumes[j],
            "amount": 1_200_000_000,
        })
    result = StrongVcpTailEngine({
        "strategy6": {
            "tail_close_range_5": 0.12,
            "tail_volume_ratio_5_20": 0.90,
            "ready_min_score": 60,
            "key_min_score": 60,
        }
    }).evaluate_at(data, code="000001", name="平安银行")

    assert result.start.start_grade == "B"
    assert result.passed is True
    assert result.candidate_type == "WATCH_CANDIDATE"


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
    assert pressured.score.risk_control_score == clean.score.risk_control_score - 5


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
    assert cfg["enable_sector_filter"] is True
    assert cfg["sector_filter_mode"] == "downgrade"
    assert cfg["sector_min_member_new_high_count"] == 3
    assert cfg["min_relative_strength_20"] == 0.10


def _market_rows(closes):
    rows = []
    for i, close in enumerate(closes):
        rows.append({
            "date": (date(2024, 1, 1) + timedelta(days=i)).isoformat(),
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
    assert score_only.score.risk_control_score == filter_off.score.risk_control_score - 5
    assert "MARKET_WEAK_DOWNGRADED" not in score_only.indicators.warn_tags


def test_sector_filter_strict_blocks_ready_or_key_but_keeps_watch_candidate():
    data = build_strategy6_candidate_data()

    result = StrongVcpTailEngine({"strategy6": {"enable_sector_filter": True, "sector_filter_mode": "strict"}}).evaluate_at(
        data,
        code="000001",
        name="平安银行",
        sector_context={"sector_strength_status": "SECTOR_WEAK", "relative_strength_10_sector": -0.05},
    )
    candidate = result.to_candidate_dict()

    assert result.passed is True
    assert result.candidate_type == "WATCH_CANDIDATE"
    assert candidate["sector_filter_mode"] == "strict"
    assert "SECTOR_WEAK_STRICT" in candidate["warn_tags"]


def test_sector_filter_downgrade_moves_ready_or_key_to_watch():
    data = build_strategy6_candidate_data()

    result = StrongVcpTailEngine({"strategy6": {"enable_sector_filter": True, "sector_filter_mode": "downgrade"}}).evaluate_at(
        data,
        code="000001",
        name="平安银行",
        sector_context={"sector_strength_status": "SECTOR_WEAK", "relative_strength_10_sector": -0.05},
    )
    candidate = result.to_candidate_dict()

    assert result.passed is True
    assert result.candidate_type == "WATCH_CANDIDATE"
    assert candidate["sector_strength_status"] == "SECTOR_WEAK"
    assert candidate["enable_sector_filter"] is True
    assert "SECTOR_WEAK_DOWNGRADED" in candidate["warn_tags"]


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
        "hs300": _market_rows([100 + i * 0.5 for i in range(80)]),
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


def test_sector_context_classifies_strength_and_relative_strength():
    strong_rows = _market_rows([100 + i * 0.2 for i in range(80)])
    for idx, row in enumerate(strong_rows[-20:]):
        row["close"] += idx * 0.8

    context = evaluate_sector_context(0.20, strong_rows)

    assert context["sector_strength_status"] == "SECTOR_STRONG"
    assert context["relative_strength_10_sector"] > 0

    weak_context = evaluate_sector_context(0.03, _market_rows([100 - i * 0.2 for i in range(80)]))
    assert weak_context["sector_strength_status"] == "SECTOR_WEAK"

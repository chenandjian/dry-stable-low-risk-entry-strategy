from __future__ import annotations

from datetime import date, timedelta
from math import isclose, sqrt

from strategy6.ttm_squeeze import (
    _ema_series,
    _linear_regression_last,
    _population_stddev,
    _wilder_atr_series,
    calculate_ttm_squeeze,
    classify_ttm_state,
)


TTM_CONFIG = {
    "enabled": True,
    "bb_period": 20,
    "bb_stddev": 2.0,
    "kc_ema_period": 20,
    "kc_atr_period": 20,
    "kc_atr_multiplier": 1.5,
    "momentum_period": 20,
    "bullish_squeeze_min_days": 3,
    "max_ranking_bonus": 4,
}


def _row(i: int, close: float = 10.0, *, high: float | None = None, low: float | None = None) -> dict:
    day = date(2026, 1, 1) + timedelta(days=i)
    return {
        "date": day.isoformat(),
        "open": close,
        "high": close + 0.1 if high is None else high,
        "low": close - 0.1 if low is None else low,
        "close": close,
        "volume": 1_000_000,
        "amount": 10_000_000,
    }


def test_ttm_math_uses_population_stddev_seeded_ema_and_linear_regression_last_point():
    assert isclose(_population_stddev([1.0, 2.0, 3.0]), sqrt(2.0 / 3.0))
    assert _ema_series([1.0, 2.0, 3.0, 4.0], 3) == [None, None, 2.0, 3.0]
    assert isclose(_linear_regression_last([1.0, 2.0, 3.0]), 3.0)


def test_ttm_wilder_atr_uses_simple_average_seed_then_wilder_smoothing():
    rows = [
        _row(0, 10.0, high=11.0, low=9.0),
        _row(1, 11.0, high=12.0, low=10.0),
        _row(2, 12.0, high=13.0, low=11.0),
        _row(3, 13.0, high=15.0, low=11.0),
    ]

    atr = _wilder_atr_series(rows, 3)

    assert atr[:2] == [None, None]
    assert isclose(atr[2], 2.0)
    assert isclose(atr[3], 8.0 / 3.0)


def test_ttm_constant_compact_prices_are_inside_keltner_channel():
    result = calculate_ttm_squeeze([_row(i) for i in range(45)], TTM_CONFIG)

    assert result.status == "SQUEEZE_NEUTRAL"
    assert result.squeeze_on is True
    assert result.squeeze_days >= 3
    assert result.bb_upper < result.kc_upper
    assert result.bb_lower > result.kc_lower
    assert result.momentum_direction == "FLAT"
    assert result.score == 2


def test_ttm_state_classifier_covers_all_business_states():
    cases = [
        ({"enabled": False}, "DISABLED", 0),
        ({"calculable": False}, "INSUFFICIENT_DATA", 0),
        ({"squeeze_on": False, "previous_squeeze_on": True, "momentum": 1.0, "previous_momentum": 0.5}, "FIRED_BULLISH", 4),
        ({"squeeze_on": False, "previous_squeeze_on": True, "momentum": 0.2, "previous_momentum": 0.3}, "FIRED_WEAK", 0),
        ({"squeeze_on": True, "squeeze_days": 3, "momentum": 1.0, "previous_momentum": 0.5}, "SQUEEZE_BULLISH", 3),
        ({"squeeze_on": True, "squeeze_days": 2, "momentum": 1.0, "previous_momentum": 0.5}, "SQUEEZE_NEUTRAL", 2),
        ({"squeeze_on": True, "squeeze_days": 4, "momentum": -1.0, "previous_momentum": -0.5}, "SQUEEZE_BEARISH", 0),
        ({"squeeze_on": False, "previous_squeeze_on": False, "momentum": 1.0, "previous_momentum": 0.5}, "OFF", 0),
    ]

    for overrides, expected_status, expected_score in cases:
        result = classify_ttm_state(
            enabled=overrides.get("enabled", True),
            calculable=overrides.get("calculable", True),
            squeeze_on=overrides.get("squeeze_on", False),
            previous_squeeze_on=overrides.get("previous_squeeze_on", False),
            squeeze_days=overrides.get("squeeze_days", 0),
            momentum=overrides.get("momentum"),
            previous_momentum=overrides.get("previous_momentum"),
            close=10.0,
            min_bullish_days=3,
        )
        assert result.status == expected_status
        assert result.score == expected_score


def test_ttm_bearish_and_weak_release_have_stable_risk_codes():
    bearish = classify_ttm_state(
        enabled=True,
        calculable=True,
        squeeze_on=True,
        previous_squeeze_on=True,
        squeeze_days=4,
        momentum=-1.0,
        previous_momentum=-0.5,
        close=10.0,
        min_bullish_days=3,
    )
    weak_release = classify_ttm_state(
        enabled=True,
        calculable=True,
        squeeze_on=False,
        previous_squeeze_on=True,
        squeeze_days=0,
        momentum=0.2,
        previous_momentum=0.3,
        close=10.0,
        min_bullish_days=3,
    )

    assert bearish.risk_tags == ["TTM_SQUEEZE_BEARISH_MOMENTUM"]
    assert weak_release.risk_tags == ["TTM_FIRED_WITHOUT_BULLISH_MOMENTUM"]


def test_ttm_returns_insufficient_instead_of_raising_for_short_or_invalid_ohlc():
    short = calculate_ttm_squeeze([_row(i) for i in range(39)], TTM_CONFIG)
    invalid_rows = [_row(i) for i in range(45)]
    invalid_rows[-1]["low"] = invalid_rows[-1]["high"] + 1.0
    invalid = calculate_ttm_squeeze(invalid_rows, TTM_CONFIG)

    assert short.status == "INSUFFICIENT_DATA"
    assert short.risk_tags == ["TTM_DATA_INSUFFICIENT"]
    assert invalid.status == "INSUFFICIENT_DATA"
    assert invalid.risk_tags == ["TTM_DATA_INSUFFICIENT"]


def test_ttm_disabled_does_not_require_market_data():
    result = calculate_ttm_squeeze([], {**TTM_CONFIG, "enabled": False})

    assert result.status == "DISABLED"
    assert result.score == 0
    assert result.risk_tags == []

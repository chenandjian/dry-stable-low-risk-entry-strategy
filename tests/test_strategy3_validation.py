import pytest

from strategy3.validation import (
    resolve_strategy3_config,
    validate_ohlc_structure,
    validate_ohlc_values,
)


def test_resolve_strategy3_config_defaults():
    cfg = resolve_strategy3_config({"liquidity": {"min_listing_days": 350}})
    assert cfg["enabled"] is True
    assert cfg["strategy_window_days"] == 250
    assert cfg["minimum_required_days"] == 180
    assert cfg["pullback_lookback_days"] == 60
    assert cfg["support_lookback_days"] == 20
    assert cfg["candidate_min_score"] == 75
    assert cfg["core_min_score"] == 85
    assert cfg["max_risk_ratio"] == 0.08
    assert cfg["min_relative_strength_60"] == 0.05


def test_resolve_strategy3_config_accepts_nested_overrides():
    cfg = resolve_strategy3_config({
        "liquidity": {"min_listing_days": 500},
        "strategy3": {
            "strategy_window_days": 300,
            "minimum_required_days": 200,
            "candidate_min_score": 78,
            "core_min_score": 90,
        },
    })
    assert cfg["strategy_window_days"] == 300
    assert cfg["minimum_required_days"] == 200
    assert cfg["candidate_min_score"] == 78
    assert cfg["core_min_score"] == 90


def test_rejects_window_larger_than_listing_days():
    with pytest.raises(ValueError, match="strategy_window_days"):
        resolve_strategy3_config({
            "liquidity": {"min_listing_days": 200},
            "strategy3": {"strategy_window_days": 250},
        })


def test_rejects_invalid_score_order():
    with pytest.raises(ValueError, match="core_min_score"):
        resolve_strategy3_config({
            "liquidity": {"min_listing_days": 350},
            "strategy3": {"candidate_min_score": 90, "core_min_score": 80},
        })


def test_rejects_invalid_pullback_range_order():
    with pytest.raises(ValueError, match="max_pullback_from_high"):
        resolve_strategy3_config({
            "liquidity": {"min_listing_days": 350},
            "strategy3": {
                "min_pullback_from_high": 0.20,
                "max_pullback_from_high": 0.10,
            },
        })


def test_validate_ohlc_structure_rejects_missing_field():
    error = validate_ohlc_structure([{
        "date": "2026-06-25",
        "open": 10,
        "high": 11,
        "low": 9,
        "close": 10.5,
    }])
    assert error == "INVALID_MARKET_DATA"


def test_validate_ohlc_structure_rejects_unsorted_dates():
    rows = [
        {"date": "2026-06-25", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1},
        {"date": "2026-06-24", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1},
    ]
    assert validate_ohlc_structure(rows) == "INVALID_MARKET_DATA"


def test_validate_ohlc_values_rejects_broken_ohlc_relation():
    rows = [
        {"date": "2026-06-24", "open": 10, "high": 9, "low": 8, "close": 10, "volume": 1},
    ]
    assert validate_ohlc_values(rows) == "INVALID_MARKET_DATA"

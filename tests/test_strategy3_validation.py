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
    assert cfg["min_pullback_from_high"] == 0.12
    assert cfg["max_pullback_from_high"] == 0.25
    assert cfg["min_relative_strength_60"] == 0.05
    assert cfg["volume_shrink_ratio"] == 0.70
    assert cfg["dry_return_5_floor"] == 0.02
    assert cfg["dry_volume_ratio"] == 0.60
    assert cfg["dry_extreme_volume_ratio"] == 0.50
    assert cfg["dry_support_lookback_days"] == 10
    assert cfg["dry_support_min_test_count"] == 2
    assert cfg["dry_support_max_test_count"] == 2
    assert cfg["dry_support_break_tolerance"] == 0.98
    assert cfg["dry_atr_expand_reject_ratio"] == 1.20
    assert cfg["dry_balance_direction_efficiency_threshold"] == 0.35
    assert cfg["dry_balance_extreme_direction_efficiency_threshold"] == 0.25
    assert cfg["dry_balance_max_up_5"] == 0.03
    assert cfg["dry_balance_max_down_5"] == -0.03
    assert cfg["dry_balance_close_position_min"] == 0.35
    assert cfg["dry_balance_close_position_max"] == 0.65
    assert cfg["dry_balance_close_range_tight"] == 0.03
    assert cfg["support_zone_pct"] == 0.01
    assert cfg["support_zone_atr_ratio"] == 0.30
    assert cfg["support_effective_break_days"] == 2
    assert cfg["support_big_down_return"] == -0.04
    assert cfg["support_big_down_volume_ratio"] == 1.30
    assert cfg["support_stop_buffer_pct"] == 0.01


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


def test_rejects_invalid_dry_cannot_fall_thresholds():
    with pytest.raises(ValueError, match="dry_support_lookback_days"):
        resolve_strategy3_config({
            "liquidity": {"min_listing_days": 350},
            "strategy3": {"dry_support_lookback_days": 1},
        })
    with pytest.raises(ValueError, match="dry_volume_ratio"):
        resolve_strategy3_config({
            "liquidity": {"min_listing_days": 350},
            "strategy3": {"dry_volume_ratio": 2.1},
        })
    with pytest.raises(ValueError, match="dry_support_min_test_count"):
        resolve_strategy3_config({
            "liquidity": {"min_listing_days": 350},
            "strategy3": {"dry_support_min_test_count": 11},
        })
    with pytest.raises(ValueError, match="dry_support_max_test_count"):
        resolve_strategy3_config({
            "liquidity": {"min_listing_days": 350},
            "strategy3": {"dry_support_max_test_count": 11},
        })
    with pytest.raises(ValueError, match="dry_support_max_test_count"):
        resolve_strategy3_config({
            "liquidity": {"min_listing_days": 350},
            "strategy3": {"dry_support_min_test_count": 3, "dry_support_max_test_count": 2},
        })
    with pytest.raises(ValueError, match="dry_support_break_tolerance"):
        resolve_strategy3_config({
            "liquidity": {"min_listing_days": 350},
            "strategy3": {"dry_support_break_tolerance": 1.2},
        })
    with pytest.raises(ValueError, match="dry_extreme_volume_ratio"):
        resolve_strategy3_config({
            "liquidity": {"min_listing_days": 350},
            "strategy3": {"dry_volume_ratio": 0.60, "dry_extreme_volume_ratio": 0.70},
        })


def test_rejects_invalid_support_zone_thresholds():
    with pytest.raises(ValueError, match="support_zone_pct"):
        resolve_strategy3_config({
            "liquidity": {"min_listing_days": 350},
            "strategy3": {"support_zone_pct": 0.50},
        })
    with pytest.raises(ValueError, match="support_zone_atr_ratio"):
        resolve_strategy3_config({
            "liquidity": {"min_listing_days": 350},
            "strategy3": {"support_zone_atr_ratio": 3.0},
        })
    with pytest.raises(ValueError, match="support_effective_break_days"):
        resolve_strategy3_config({
            "liquidity": {"min_listing_days": 350},
            "strategy3": {"support_effective_break_days": 0},
        })
    with pytest.raises(ValueError, match="support_big_down_volume_ratio"):
        resolve_strategy3_config({
            "liquidity": {"min_listing_days": 350},
            "strategy3": {"support_big_down_volume_ratio": 0.1},
        })
    with pytest.raises(ValueError, match="support_stop_buffer_pct"):
        resolve_strategy3_config({
            "liquidity": {"min_listing_days": 350},
            "strategy3": {"support_stop_buffer_pct": 0.20},
        })


def test_rejects_invalid_extreme_balance_thresholds():
    with pytest.raises(ValueError, match="dry_balance_extreme_direction_efficiency_threshold"):
        resolve_strategy3_config({
            "liquidity": {"min_listing_days": 350},
            "strategy3": {
                "dry_balance_direction_efficiency_threshold": 0.30,
                "dry_balance_extreme_direction_efficiency_threshold": 0.40,
            },
        })
    with pytest.raises(ValueError, match="dry_balance_max_up_5"):
        resolve_strategy3_config({
            "liquidity": {"min_listing_days": 350},
            "strategy3": {"dry_balance_max_up_5": 0.30},
        })
    with pytest.raises(ValueError, match="dry_balance_close_position_max"):
        resolve_strategy3_config({
            "liquidity": {"min_listing_days": 350},
            "strategy3": {
                "dry_balance_close_position_min": 0.70,
                "dry_balance_close_position_max": 0.60,
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

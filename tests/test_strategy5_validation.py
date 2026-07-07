import pytest

from strategy5.validation import resolve_strategy5_config


def test_strategy5_default_config_matches_design():
    cfg = resolve_strategy5_config({})

    assert cfg["enabled"] is True
    assert cfg["kline_days"] == 1100
    assert cfg["minimum_kline_days"] == 260
    assert cfg["minimum_trading_days"] == 500
    assert cfg["min_avg_amount_60d_yi"] == 20
    assert cfg["min_avg_amount_30d_yi"] == 15
    assert cfg["min_avg_amount_10d_yi"] == 10
    assert cfg["strength_ret_20d"] == 0.20
    assert cfg["strength_ret_10d"] == 0.12
    assert cfg["strength_ret_5d"] == 0.08
    assert cfg["single_day_surge_return"] == 0.07
    assert cfg["single_day_surge_volume_ratio"] == 1.8
    assert cfg["near_120d_high_ratio"] == 0.98
    assert cfg["max_amp_5d"] == 0.22
    assert cfg["max_amp_10d"] == 0.45
    assert cfg["max_drawdown_20d"] == -0.30
    assert cfg["max_decline_5d"] == -0.08
    assert cfg["volume_down_return"] == -0.07
    assert cfg["volume_down_ratio"] == 1.5
    assert cfg["ma50_min_ratio"] == 0.92
    assert cfg["key_candidate_min_support_score"] == 8


def test_strategy5_overrides_nested_project_config():
    cfg = resolve_strategy5_config({
        "strategy5": {
            "enabled": False,
            "kline_days": 1200,
            "minimum_trading_days": 900,
            "min_avg_amount_60d_yi": 18,
        }
    })

    assert cfg["enabled"] is False
    assert cfg["kline_days"] == 1200
    assert cfg["minimum_trading_days"] == 900
    assert cfg["min_avg_amount_60d_yi"] == 18


def test_strategy5_rejects_invalid_ranges():
    with pytest.raises(ValueError, match="kline_days"):
        resolve_strategy5_config({"strategy5": {"kline_days": 200}})

    with pytest.raises(ValueError, match="near_120d_high_ratio"):
        resolve_strategy5_config({"strategy5": {"near_120d_high_ratio": 1.2}})

    with pytest.raises(ValueError, match="max_drawdown_20d"):
        resolve_strategy5_config({"strategy5": {"max_drawdown_20d": 0.1}})

import pytest

from strategy5.validation import resolve_strategy5_config


def test_strategy5_default_config_matches_design():
    cfg = resolve_strategy5_config({})

    assert cfg["enabled"] is True
    assert cfg["kline_days"] == 1100
    assert "minimum_kline_days" not in cfg
    assert cfg["minimum_trading_days"] == 500
    assert cfg["min_avg_amount_60d_yi"] == 15
    assert cfg["min_avg_amount_30d_yi"] == 8
    assert cfg["min_avg_amount_10d_yi"] == 5
    assert cfg["kcb_min_avg_amount_60d_yi"] == 50
    assert cfg["kcb_min_avg_amount_30d_yi"] == 30
    assert cfg["kcb_min_avg_amount_10d_yi"] == 20
    assert cfg["strength_ret_20d"] == 0.25
    assert cfg["strength_ret_10d"] == 0.15
    assert cfg["strength_ret_5d"] == 0.10
    assert cfg["strength_ret_50d"] == 0.35
    assert cfg["strength_ret_50d_min_20d"] == 0.05
    assert cfg["strength_ret_50d_ma20_ratio"] == 0.98
    assert cfg["strength_ret_50d_max_amp_10d"] == 0.30
    assert cfg["strength_ret_50d_max_decline_5d"] == -0.06
    assert cfg["single_day_surge_return"] == 0.07
    assert cfg["single_day_surge_volume_ratio"] == 1.8
    assert cfg["near_120d_high_ratio"] == 1.00
    assert cfg["max_amp_5d"] == 0.22
    assert cfg["max_amp_10d"] == 0.45
    assert cfg["max_drawdown_20d"] == -0.30
    assert cfg["max_decline_5d"] == -0.08
    assert cfg["volume_down_return"] == -0.07
    assert cfg["volume_down_ratio"] == 1.5
    assert cfg["ma50_min_ratio"] == 0.92
    assert cfg["key_candidate_min_support_score"] == 8
    assert cfg["volume_dry_min_score_key"] == 14
    assert cfg["volume_dry_min_score_watch"] == 10
    assert cfg["volume_dry_ratio_5_20"] == 0.75
    assert cfg["volume_dry_strong_ratio_5_20"] == 0.65
    assert cfg["volume_dry_extreme_ratio_5_20"] == 0.50


def test_strategy5_overrides_nested_project_config():
    cfg = resolve_strategy5_config({
        "strategy5": {
            "enabled": False,
            "kline_days": 1200,
            "minimum_trading_days": 900,
            "min_avg_amount_60d_yi": 18,
            "kcb_min_avg_amount_60d_yi": 60,
        }
    })

    assert cfg["enabled"] is False
    assert cfg["kline_days"] == 1200
    assert cfg["minimum_trading_days"] == 900
    assert cfg["min_avg_amount_60d_yi"] == 18
    assert cfg["kcb_min_avg_amount_60d_yi"] == 60


def test_strategy5_ignores_legacy_minimum_kline_days_config():
    cfg = resolve_strategy5_config({
        "strategy5": {
            "minimum_kline_days": 120,
            "minimum_trading_days": 500,
        }
    })

    assert "minimum_kline_days" not in cfg
    assert cfg["minimum_trading_days"] == 500


def test_strategy5_rejects_invalid_ranges():
    with pytest.raises(ValueError, match="kline_days"):
        resolve_strategy5_config({"strategy5": {"kline_days": 200}})

    with pytest.raises(ValueError, match="near_120d_high_ratio"):
        resolve_strategy5_config({"strategy5": {"near_120d_high_ratio": 1.2}})

    with pytest.raises(ValueError, match="max_drawdown_20d"):
        resolve_strategy5_config({"strategy5": {"max_drawdown_20d": 0.1}})

    with pytest.raises(ValueError, match="strength_ret_50d_max_decline_5d"):
        resolve_strategy5_config({"strategy5": {"strength_ret_50d_max_decline_5d": 0.1}})

    with pytest.raises(ValueError, match="minimum_trading_days"):
        resolve_strategy5_config({"strategy5": {"minimum_trading_days": 259}})

    with pytest.raises(ValueError, match="volume_dry_min_score_watch"):
        resolve_strategy5_config({"strategy5": {"volume_dry_min_score_watch": 15, "volume_dry_min_score_key": 14}})

    with pytest.raises(ValueError, match="volume_dry_strong_ratio_5_20"):
        resolve_strategy5_config({"strategy5": {"volume_dry_ratio_5_20": 0.70, "volume_dry_strong_ratio_5_20": 0.80}})

    with pytest.raises(ValueError, match="kcb_min_avg_amount_60d_yi"):
        resolve_strategy5_config({"strategy5": {"kcb_min_avg_amount_60d_yi": -1}})

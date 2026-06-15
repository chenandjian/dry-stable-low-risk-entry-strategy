import pytest


def test_normalize_strategy1_experiment_defaults_disabled():
    from scanner.strategy1_backtest_experiments import normalize_experiment_config

    normalized = normalize_experiment_config(None)

    assert normalized["enabled"] is False
    assert normalized["minimum_total_score"] is None
    assert normalized["time_exit_days"] is None
    assert normalized["execution_model"] == "NEXT_OPEN"
    assert normalized["breakout"]["mode"] == "NONE"
    assert normalized["decision"]["allowed_verdict_keys"] == ["BUY_LOW", "WATCH_BREAKOUT", "WAIT_ENTRY"]


def test_normalize_strategy1_experiment_accepts_camel_case_payload():
    from scanner.strategy1_backtest_experiments import normalize_experiment_config

    normalized = normalize_experiment_config({
        "enabled": True,
        "minimumTotalScore": 75,
        "cupMaxDepth": 0.33,
        "handleMaxDepth": 0.12,
        "timeExitDays": 5,
        "executionModel": "SIGNAL_CLOSE_DIAGNOSTIC",
        "breakout": {"mode": "PRICE_AND_VOLUME", "bufferPct": 0.03, "volumeMultiplier": 2.0},
        "decision": {
            "minVolumeDryScore": 8,
            "minPriceStableScore": 7,
            "allowedVerdictKeys": ["BUY_LOW"],
        },
        "risk": {"maxRiskPercent": 6, "minRr1": 2.5},
    })

    assert normalized["enabled"] is True
    assert normalized["minimum_total_score"] == 75
    assert normalized["cup"]["max_depth"] == 0.33
    assert normalized["handle"]["max_depth"] == 0.12
    assert normalized["time_exit_days"] == 5
    assert normalized["execution_model"] == "SIGNAL_CLOSE_DIAGNOSTIC"
    assert normalized["breakout"]["mode"] == "PRICE_AND_VOLUME"
    assert normalized["breakout"]["buffer_pct"] == 0.03
    assert normalized["breakout"]["volume_multiplier"] == 2.0
    assert normalized["decision"]["min_volume_dry_score"] == 8
    assert normalized["decision"]["min_price_stable_score"] == 7
    assert normalized["decision"]["allowed_verdict_keys"] == ["BUY_LOW"]
    assert normalized["risk"]["max_risk_percent"] == 6
    assert normalized["risk"]["min_rr1"] == 2.5


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"minimum_total_score": 101}, "minimum_total_score"),
        ({"cup_max_depth": 1.2}, "cup.max_depth"),
        ({"handle_max_depth": -0.1}, "handle.max_depth"),
        ({"time_exit_days": 4}, "time_exit_days"),
        ({"execution_model": "BAD"}, "execution_model"),
        ({"breakout": {"mode": "BAD"}}, "breakout.mode"),
        ({"decision": {"allowed_verdict_keys": ["BAD"]}}, "allowed_verdict_keys"),
        ({"risk": {"max_risk_percent": -1}}, "risk.max_risk_percent"),
    ],
)
def test_normalize_strategy1_experiment_rejects_invalid_values(payload, message):
    from scanner.strategy1_backtest_experiments import normalize_experiment_config

    with pytest.raises(ValueError, match=message):
        normalize_experiment_config(payload)


def test_apply_signal_experiment_filter_records_first_failed_reason():
    from scanner.strategy1_backtest_experiments import apply_signal_experiment_filter
    from scanner.strategy1_backtest_models import Strategy1BacktestSignal

    signal = Strategy1BacktestSignal(
        score=72,
        cup_depth_pct=0.38,
        handle_depth_pct=0.08,
        volume_dry_score=9,
        price_stable_score=7,
        risk_percent=5.0,
        rr1=2.0,
        verdict_key="BUY_LOW",
    )

    passed, reason = apply_signal_experiment_filter(signal, {
        "enabled": True,
        "minimum_total_score": 75,
        "cup": {"max_depth": 0.33},
        "handle": {},
        "decision": {},
        "risk": {},
        "breakout": {"mode": "NONE"},
    })

    assert passed is False
    assert reason == "MIN_TOTAL_SCORE"
    assert signal.baseline_passed is True
    assert signal.experiment_passed is False
    assert signal.experiment_filter_reason == "MIN_TOTAL_SCORE"


def test_apply_signal_experiment_filter_disabled_preserves_baseline():
    from scanner.strategy1_backtest_experiments import apply_signal_experiment_filter
    from scanner.strategy1_backtest_models import Strategy1BacktestSignal

    signal = Strategy1BacktestSignal(score=10, cup_depth_pct=0.6, verdict_key="REJECT")

    passed, reason = apply_signal_experiment_filter(signal, {"enabled": False, "minimum_total_score": 90})

    assert passed is True
    assert reason == ""
    assert signal.experiment_passed is True
    assert signal.experiment_filter_reason == ""

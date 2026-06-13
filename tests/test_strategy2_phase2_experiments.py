"""Strategy2 Phase 2 experiment layer tests."""

import json

import pytest
from datetime import date, timedelta

from strategy2.backtest_models import BacktestOpportunity, BacktestSignal


def _bar(date, open_=10.0, high=10.0, low=10.0, close=10.0, volume=1000):
    return {
        "date": date,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "turnover": volume * close,
    }


def _bars(count, start=date(2025, 1, 1)):
    return [
        _bar((start + timedelta(days=i)).isoformat(), open_=10.0, high=10.4, low=9.8, close=10.0, volume=10000)
        for i in range(count)
    ]


def _signal(**kwargs):
    values = {
        "code": "000001",
        "name": "test",
        "evaluation_date": "2025-01-10",
        "evaluation_index": 9,
        "score": 72,
        "level": "观察",
        "current_close": 10.0,
        "stop_loss": 9.5,
        "risk_ratio": 0.03,
        "volume_dry_score": 45,
        "price_stable_score": 35,
        "trend_type": "UPTREND_OR_SIDEWAYS",
        "trend_evidence_score": 4,
        "evaluation_snapshot": {"buy_zone_high": 10.8},
    }
    values.update(kwargs)
    return BacktestSignal(**values)


def _opp(**kwargs):
    values = {
        "code": "000001",
        "name": "test",
        "first_detected_date": "2025-01-10",
        "last_detected_date": "2025-01-10",
        "consecutive_hit_days": 1,
        "first_score": 72,
        "max_score": 72,
        "level": "观察",
        "entry_close": 10.0,
        "stop_loss": 9.5,
        "risk_ratio": 0.03,
        "trend_type": "UPTREND_OR_SIDEWAYS",
        "trend_evidence_score": 4,
        "evaluation_snapshot": {"buy_zone_high": 10.8},
    }
    values.update(kwargs)
    return BacktestOpportunity(**values)


def test_normalize_missing_experiment_is_disabled():
    from strategy2.backtest_experiments import normalize_experiment_config

    normalized = normalize_experiment_config(None)

    assert normalized["enabled"] is False
    assert normalized["minimum_total_score"] is None
    assert normalized["time_exit_days"] is None
    assert normalized["entry_confirmation"]["type"] == "NONE"


def test_normalize_accepts_camel_case_payload_and_rejects_invalid_values():
    from strategy2.backtest_experiments import normalize_experiment_config

    normalized = normalize_experiment_config({
        "enabled": True,
        "minimumTotalScore": 75,
        "minimumVolumeDryScore": 40,
        "minimumPriceStableScore": 30,
        "timeExitDays": 5,
        "entryConfirmation": {
            "type": "BREAK_RECENT_5D_HIGH",
            "maxWaitDays": 4,
            "moderateVolumeMaxRatio": 1.6,
        },
        "marketContext": {"enabled": True},
    })

    assert normalized["enabled"] is True
    assert normalized["minimum_total_score"] == 75
    assert normalized["minimum_volume_dry_score"] == 40
    assert normalized["minimum_price_stable_score"] == 30
    assert normalized["time_exit_days"] == 5
    assert normalized["entry_confirmation"]["max_wait_days"] == 4
    assert normalized["entry_confirmation"]["moderate_volume_max_ratio"] == 1.6
    assert normalized["market_context"]["enabled"] is True

    with pytest.raises(ValueError, match="time_exit_days"):
        normalize_experiment_config({"enabled": True, "timeExitDays": 7})


def test_signal_filter_records_first_failed_threshold_reason():
    from strategy2.backtest_experiments import apply_signal_experiment_filter

    signal = _signal(score=72, volume_dry_score=35, price_stable_score=20)
    experiment = {
        "enabled": True,
        "minimum_total_score": 75,
        "minimum_volume_dry_score": 40,
        "minimum_price_stable_score": 30,
    }

    passed, reason = apply_signal_experiment_filter(signal, experiment)

    assert passed is False
    assert reason == "MIN_TOTAL_SCORE"


def test_signal_filter_disabled_always_passes_and_marks_traceability_defaults():
    from strategy2.backtest_experiments import apply_signal_experiment_filter

    signal = _signal(score=10, volume_dry_score=0, price_stable_score=0)

    passed, reason = apply_signal_experiment_filter(signal, {"enabled": False})

    assert passed is True
    assert reason == ""
    assert signal.baseline_passed is True
    assert signal.experiment_passed is True
    assert signal.experiment_filter_reason == ""


def test_entry_confirmation_none_uses_next_open_baseline_entry():
    from strategy2.backtest_experiments import apply_entry_confirmation

    opp = _opp()
    ohlc = [
        _bar("2025-01-10", close=10.0),
        _bar("2025-01-13", open_=10.2, high=10.4, low=10.1, close=10.3),
    ]
    date_to_index = {row["date"]: idx for idx, row in enumerate(ohlc)}
    experiment = {"entry_confirmation": {"type": "NONE", "max_wait_days": 5}}

    confirmed = apply_entry_confirmation(opp, ohlc, date_to_index, experiment)

    assert confirmed is True
    assert opp.entry_confirmation_status == "ENTRY_CONFIRMED"
    assert opp.entry_confirmation_type == "NONE"
    assert opp.entry_confirmation_date == "2025-01-10"


def test_entry_confirmation_breaks_recent_5d_high_without_lookahead():
    from strategy2.backtest_experiments import apply_entry_confirmation

    opp = _opp(first_detected_date="2025-01-08")
    ohlc = [
        _bar("2025-01-01", high=10.0, close=9.8),
        _bar("2025-01-02", high=10.1, close=9.9),
        _bar("2025-01-03", high=10.2, close=10.0),
        _bar("2025-01-06", high=10.3, close=10.1),
        _bar("2025-01-07", high=10.4, close=10.0),
        _bar("2025-01-08", high=10.2, close=10.0),
        _bar("2025-01-09", high=10.45, close=10.5),
        _bar("2025-01-10", open_=10.6, high=10.8, close=10.7),
    ]
    date_to_index = {row["date"]: idx for idx, row in enumerate(ohlc)}
    experiment = {"entry_confirmation": {"type": "BREAK_RECENT_5D_HIGH", "max_wait_days": 2}}

    confirmed = apply_entry_confirmation(opp, ohlc, date_to_index, experiment)

    assert confirmed is True
    assert opp.entry_confirmation_status == "ENTRY_CONFIRMED"
    assert opp.entry_confirmation_date == "2025-01-09"
    assert opp.entry_confirmation_price == 10.5


def test_entry_confirmation_marks_no_confirmation_when_condition_never_hits():
    from strategy2.backtest_experiments import apply_entry_confirmation

    opp = _opp(first_detected_date="2025-01-08")
    ohlc = [
        _bar("2025-01-01", high=10.0, close=9.8),
        _bar("2025-01-02", high=10.1, close=9.9),
        _bar("2025-01-03", high=10.2, close=10.0),
        _bar("2025-01-06", high=10.3, close=10.1),
        _bar("2025-01-07", high=10.4, close=10.0),
        _bar("2025-01-08", high=10.2, close=10.0),
        _bar("2025-01-09", high=10.3, close=10.1),
    ]
    date_to_index = {row["date"]: idx for idx, row in enumerate(ohlc)}
    experiment = {"entry_confirmation": {"type": "BREAK_RECENT_5D_HIGH", "max_wait_days": 1}}

    confirmed = apply_entry_confirmation(opp, ohlc, date_to_index, experiment)

    assert confirmed is False
    assert opp.entry_confirmation_status == "NO_ENTRY_CONFIRMATION"
    assert opp.entry_price == 0.0


def test_time_exit_does_not_override_earlier_stop_or_target():
    from strategy2.backtest_experiments import apply_time_exit

    opp = _opp()
    opp.entry_date = "2025-01-11"
    opp.entry_price = 10.0
    opp.exit_reason = "STOP"
    opp.exit_date = "2025-01-13"
    opp.exit_price = 9.5
    opp.holding_days = 2
    ohlc = [
        _bar("2025-01-10", close=10.0),
        _bar("2025-01-11", open_=10.0, close=10.1),
        _bar("2025-01-13", close=9.4),
        _bar("2025-01-14", close=10.5),
        _bar("2025-01-15", close=10.6),
    ]
    date_to_index = {row["date"]: idx for idx, row in enumerate(ohlc)}

    apply_time_exit(opp, ohlc, date_to_index, {"time_exit_days": 3})

    assert opp.exit_reason == "STOP"
    assert opp.exit_date == "2025-01-13"


def test_time_exit_overrides_later_target_or_stop():
    from strategy2.backtest_experiments import apply_time_exit

    opp = _opp()
    opp.entry_date = "2025-01-11"
    opp.entry_price = 10.0
    opp.exit_reason = "TARGET"
    opp.exit_date = "2025-01-16"
    opp.exit_price = 10.5
    opp.holding_days = 4
    ohlc = [
        _bar("2025-01-10", close=10.0),
        _bar("2025-01-11", open_=10.0, close=10.1),
        _bar("2025-01-13", close=10.2),
        _bar("2025-01-14", close=10.3),
        _bar("2025-01-15", close=10.4),
        _bar("2025-01-16", close=10.5),
    ]
    date_to_index = {row["date"]: idx for idx, row in enumerate(ohlc)}

    apply_time_exit(opp, ohlc, date_to_index, {"time_exit_days": 3})

    assert opp.exit_reason == "TIME_EXIT"
    assert opp.exit_date == "2025-01-14"
    assert opp.exit_price == 10.3


def test_time_exit_sets_exit_when_no_target_or_stop_has_triggered():
    from strategy2.backtest_experiments import apply_time_exit

    opp = _opp()
    opp.entry_date = "2025-01-11"
    opp.entry_price = 10.0
    opp.exit_reason = "UNRESOLVED"
    ohlc = [
        _bar("2025-01-10", close=10.0),
        _bar("2025-01-11", open_=10.0, close=10.1),
        _bar("2025-01-13", close=10.2),
        _bar("2025-01-14", close=10.3),
    ]
    date_to_index = {row["date"]: idx for idx, row in enumerate(ohlc)}

    apply_time_exit(opp, ohlc, date_to_index, {"time_exit_days": 3})

    assert opp.exit_reason == "TIME_EXIT"
    assert opp.exit_date == "2025-01-14"
    assert opp.exit_price == 10.3
    assert opp.holding_days == 3
    assert opp.realized_return == pytest.approx(0.03)


def test_classify_opportunity_type_from_trend_type():
    from strategy2.backtest_experiments import classify_opportunity_type

    assert classify_opportunity_type(_signal(trend_type="UPTREND_OR_SIDEWAYS")) == "CONTINUATION"
    assert classify_opportunity_type(_signal(trend_type="DOWNTREND_REPAIR")) == "REVERSAL"
    assert classify_opportunity_type(_signal(trend_type="")) == "NEUTRAL"


def test_stock_backtest_disabled_experiment_matches_baseline(monkeypatch):
    from strategy2.backtester import run_strategy2_stock_backtest
    from strategy2.engine import ExtremeDryStableStrategyEngine
    from strategy2.models import Strategy2Evaluation, Strategy2Risk, Strategy2Trend
    import scanner.liquidity_filter as liquidity_filter

    monkeypatch.setattr(liquidity_filter, "passes_liquidity_filter", lambda *_args, **_kwargs: True)

    def fake_evaluate_at(self, history, *, code="", name=""):
        return Strategy2Evaluation(
            passed=True,
            code=code,
            name=name,
            volume_dry_score=45,
            price_stable_score=35,
            total_score=72,
            level="观察",
            current_close=history[-1]["close"],
            risk=Strategy2Risk(stop_loss=9.5, risk_ratio=0.03, buy_zone_high=10.8),
            trend=Strategy2Trend(trend_type="UPTREND_OR_SIDEWAYS", total_evidence_score=4),
        )

    monkeypatch.setattr(ExtremeDryStableStrategyEngine, "evaluate_at", fake_evaluate_at)
    ohlc = _bars(75)
    config = {"strategy2": {"minimum_required_days": 60, "strategy_window_days": 70}, "liquidity": {}}

    baseline = run_strategy2_stock_backtest("000001", "test", ohlc, config, "2025-03-01", "2025-03-05")
    disabled = run_strategy2_stock_backtest(
        "000001", "test", ohlc, config, "2025-03-01", "2025-03-05",
        experiment={"enabled": False},
    )

    assert disabled["raw_signals_count"] == baseline["raw_signals_count"]
    assert disabled["opportunities_count"] == baseline["opportunities_count"]
    assert disabled["opportunities"] == baseline["opportunities"]


def test_stock_backtest_experiment_filters_signals_but_keeps_traceability(monkeypatch):
    from strategy2.backtester import run_strategy2_stock_backtest
    from strategy2.engine import ExtremeDryStableStrategyEngine
    from strategy2.models import Strategy2Evaluation, Strategy2Risk, Strategy2Trend
    import scanner.liquidity_filter as liquidity_filter

    monkeypatch.setattr(liquidity_filter, "passes_liquidity_filter", lambda *_args, **_kwargs: True)

    def fake_evaluate_at(self, history, *, code="", name=""):
        score = 72 if history[-1]["date"] == "2025-03-01" else 80
        return Strategy2Evaluation(
            passed=True,
            code=code,
            name=name,
            volume_dry_score=35 if score == 72 else 45,
            price_stable_score=35,
            total_score=score,
            level="观察",
            current_close=history[-1]["close"],
            risk=Strategy2Risk(stop_loss=9.5, risk_ratio=0.03, buy_zone_high=10.8),
            trend=Strategy2Trend(trend_type="UPTREND_OR_SIDEWAYS", total_evidence_score=4),
        )

    monkeypatch.setattr(ExtremeDryStableStrategyEngine, "evaluate_at", fake_evaluate_at)
    ohlc = _bars(70)
    config = {"strategy2": {"minimum_required_days": 60, "strategy_window_days": 70}, "liquidity": {}}

    result = run_strategy2_stock_backtest(
        "000001", "test", ohlc, config, "2025-03-01", "2025-03-02",
        experiment={"enabled": True, "minimum_volume_dry_score": 40},
    )

    assert result["raw_signals_count"] == 2
    assert result["experiment_filtered_days"] == 1
    assert result["opportunities_count"] == 1
    assert result["signals"][0].experiment_passed is False
    assert result["signals"][0].experiment_filter_reason == "MIN_VOLUME_DRY_SCORE"
    assert result["signals"][1].experiment_passed is True


def test_entry_confirmation_horizon_starts_after_confirmed_entry(monkeypatch):
    from strategy2.backtester import run_strategy2_stock_backtest
    from strategy2.engine import ExtremeDryStableStrategyEngine
    from strategy2.models import Strategy2Evaluation, Strategy2Risk, Strategy2Trend
    import scanner.liquidity_filter as liquidity_filter

    monkeypatch.setattr(liquidity_filter, "passes_liquidity_filter", lambda *_args, **_kwargs: True)

    def fake_evaluate_at(self, history, *, code="", name=""):
        return Strategy2Evaluation(
            passed=True,
            code=code,
            name=name,
            volume_dry_score=45,
            price_stable_score=35,
            total_score=80,
            level="观察",
            current_close=history[-1]["close"],
            risk=Strategy2Risk(stop_loss=9.5, risk_ratio=0.03, buy_zone_high=11.0),
            trend=Strategy2Trend(trend_type="UPTREND_OR_SIDEWAYS", total_evidence_score=4),
        )

    monkeypatch.setattr(ExtremeDryStableStrategyEngine, "evaluate_at", fake_evaluate_at)
    ohlc = _bars(63)
    signal_idx = 59
    ohlc[signal_idx]["date"] = "2025-03-01"
    ohlc[signal_idx]["high"] = 10.0
    ohlc[signal_idx]["close"] = 10.0
    ohlc[60].update({"date": "2025-03-02", "open": 10.0, "high": 10.9, "low": 9.8, "close": 10.6})
    ohlc[61].update({"date": "2025-03-03", "open": 10.7, "high": 10.8, "low": 10.6, "close": 10.7})
    ohlc[62].update({"date": "2025-03-04", "open": 10.7, "high": 10.8, "low": 10.6, "close": 10.7})
    config = {"strategy2": {"minimum_required_days": 60, "strategy_window_days": 70}, "liquidity": {}}

    result = run_strategy2_stock_backtest(
        "000001", "test", ohlc, config, "2025-03-01", "2025-03-01",
        experiment={
            "enabled": True,
            "entry_confirmation": {"type": "BREAK_RECENT_5D_HIGH", "max_wait_days": 1},
        },
    )

    opp = result["opportunities"][0]
    horizon_3 = json.loads(opp["horizon_3"])
    assert opp["entry_date"] == "2025-03-03"
    assert horizon_3["result"] == "UNOBSERVED"

from datetime import date, timedelta

from strategy6.entry_quality import (
    entry_quality_blocks_tier,
    entry_quality_hard_filter_reasons,
    evaluate_entry_timing,
    evaluate_probability_adjusted_rr,
)
from strategy6.models import (
    Strategy6EntryTiming,
    Strategy6Indicators,
    Strategy6ProbabilityAdjustedRR,
    Strategy6Support,
    Strategy6TradePlan,
)
from strategy6.validation import resolve_strategy6_config
from strategy6.backtest.selection_optimization import (
    build_entry_quality_trial_configs,
    evaluate_frozen_selection_trials,
    replay_selection_trial,
)


def _rows(closes, *, volumes=None, lows=None, highs=None):
    start = date(2025, 1, 1)
    volumes = volumes or [100.0] * len(closes)
    lows = lows or [value - 1.0 for value in closes]
    highs = highs or [value + 1.0 for value in closes]
    return [
        {
            "date": (start + timedelta(days=index)).isoformat(),
            "open": float(close),
            "high": float(highs[index]),
            "low": float(lows[index]),
            "close": float(close),
            "volume": float(volumes[index]),
        }
        for index, close in enumerate(closes)
    ]


def _support(**overrides):
    values = {
        "support_status": "PATTERN_SUPPORT",
        "key_support_price": 98.0,
        "tactical_support_price": 99.0,
        "support_zone_low": 98.5,
        "support_zone_high": 100.5,
    }
    values.update(overrides)
    return Strategy6Support(**values)


def test_support_pullback_requires_real_price_action_confirmation():
    closes = [100.0] * 20 + [99.0, 98.8, 98.9, 99.1, 99.6]
    volumes = [100.0] * 20 + [70.0, 65.0, 60.0, 55.0, 50.0]
    rows = _rows(
        closes,
        volumes=volumes,
        lows=[value - 0.3 for value in closes],
        highs=[value + 0.5 for value in closes],
    )
    result = evaluate_entry_timing(
        rows,
        Strategy6Indicators(current_price=99.6, current_close_position=0.75),
        _support(),
        entry_archetype="SUPPORT_PULLBACK",
    )

    assert result.state == "SUPPORT_CONFIRMED"
    assert result.executable is True
    assert result.evidence_count >= 3
    assert "ENTRY_NO_NEW_LOW" in result.reasons
    assert "ENTRY_PULLBACK_VOLUME_CONTRACTING" in result.reasons


def test_support_pullback_stays_forming_when_latest_bar_makes_a_new_low():
    closes = [100.0] * 20 + [99.5, 99.2, 99.0, 98.9, 99.1]
    lows = [99.0] * 20 + [99.0, 98.8, 98.6, 98.5, 98.2]
    rows = _rows(closes, lows=lows)

    result = evaluate_entry_timing(
        rows,
        Strategy6Indicators(current_price=99.1, current_close_position=0.7),
        _support(),
        entry_archetype="SUPPORT_PULLBACK",
    )

    assert result.state == "SUPPORT_FORMING"
    assert result.executable is False
    assert "ENTRY_LATEST_NEW_LOW" in result.risk_tags


def test_support_failure_is_an_invalid_entry_state():
    result = evaluate_entry_timing(
        _rows([100.0] * 25),
        Strategy6Indicators(current_price=97.0),
        _support(support_status="SUPPORT_FAILED"),
        entry_archetype="SUPPORT_PULLBACK",
    )

    assert result.state == "INVALID"
    assert result.executable is False


def test_support_break_or_big_down_volume_is_an_invalid_entry_state():
    rows = _rows([100.0] * 25)

    broken = evaluate_entry_timing(
        rows,
        Strategy6Indicators(current_price=97.9),
        _support(),
        entry_archetype="SUPPORT_PULLBACK",
    )
    selloff = evaluate_entry_timing(
        rows,
        Strategy6Indicators(current_price=100.0, has_big_down_volume=True),
        _support(),
        entry_archetype="PIVOT_BREAKOUT",
    )

    assert broken.state == "INVALID"
    assert broken.risk_tags == ["ENTRY_CLOSE_BELOW_SUPPORT_FLOOR"]
    assert selloff.state == "INVALID"
    assert selloff.risk_tags == ["ENTRY_BIG_DOWN_VOLUME"]


def test_existing_breakout_and_reclaim_archetypes_are_confirmed_without_reinterpretation():
    rows = _rows([100.0] * 25)
    ind = Strategy6Indicators(current_price=100.0)

    breakout = evaluate_entry_timing(
        rows, ind, _support(), entry_archetype="PIVOT_BREAKOUT",
    )
    reclaim = evaluate_entry_timing(
        rows, ind, _support(), entry_archetype="FAILED_BREAKOUT_RECLAIM",
    )

    assert breakout.state == "BREAKOUT_CONFIRMED"
    assert breakout.executable is True
    assert reclaim.state == "RECLAIM_CONFIRMED"
    assert reclaim.executable is True


def test_probability_rr_uses_asof_historical_paths_and_rewards_reachable_targets():
    rows = _rows([100.0 + index * 2.0 for index in range(100)])
    result = evaluate_probability_adjusted_rr(
        rows,
        Strategy6Indicators(atr14=2.0),
        Strategy6TradePlan(
            risk_amount=2.0,
            reward_amount_1=2.0,
            reward_amount_2=4.0,
            objective_rr_1=1.0,
            objective_rr_2=2.0,
        ),
        lookback_days=80,
        horizon_days=5,
        minimum_samples=20,
    )

    assert result.reliable is True
    assert result.sample_count == 80
    assert result.target_1_hit_probability == 1.0
    assert result.target_2_hit_probability == 1.0
    assert result.probability_adjusted_r == 2.0


def test_probability_rr_penalizes_targets_that_repeatedly_hit_stop_first():
    rows = _rows([300.0 - index * 2.0 for index in range(100)])
    result = evaluate_probability_adjusted_rr(
        rows,
        Strategy6Indicators(atr14=2.0),
        Strategy6TradePlan(
            risk_amount=2.0,
            reward_amount_1=2.0,
            reward_amount_2=4.0,
            objective_rr_1=1.0,
            objective_rr_2=2.0,
        ),
        lookback_days=80,
        horizon_days=5,
        minimum_samples=20,
    )

    assert result.reliable is True
    assert result.target_1_hit_probability == 0.0
    assert result.target_2_hit_probability == 0.0
    assert result.probability_adjusted_r == -1.0


def test_probability_rr_is_unavailable_when_history_is_insufficient():
    result = evaluate_probability_adjusted_rr(
        _rows([100.0] * 30),
        Strategy6Indicators(atr14=2.0),
        Strategy6TradePlan(
            risk_amount=2.0,
            reward_amount_1=2.0,
            reward_amount_2=4.0,
            objective_rr_1=1.0,
            objective_rr_2=2.0,
        ),
        lookback_days=80,
        horizon_days=20,
        minimum_samples=20,
    )

    assert result.reliable is False
    assert result.status == "INSUFFICIENT_SAMPLE"


def test_probability_rr_uses_stop_first_when_both_barriers_hit_on_same_day():
    rows = _rows([100.0] * 40)
    for index in range(1, len(rows)):
        rows[index]["high"] = 105.0
        rows[index]["low"] = 95.0
    result = evaluate_probability_adjusted_rr(
        rows,
        Strategy6Indicators(atr14=2.0),
        Strategy6TradePlan(
            risk_amount=1.0,
            reward_amount_1=1.0,
            reward_amount_2=2.0,
            objective_rr_1=1.0,
            objective_rr_2=2.0,
        ),
        lookback_days=20,
        horizon_days=3,
        minimum_samples=10,
    )

    assert result.target_1_hit_probability == 0.0
    assert result.target_2_hit_probability == 0.0
    assert result.probability_adjusted_r == -1.0


def test_probability_rr_excludes_invalid_anchor_rows_from_sample_count():
    rows = _rows([100.0 + index for index in range(50)])
    rows[20]["close"] = 0.0
    result = evaluate_probability_adjusted_rr(
        rows,
        Strategy6Indicators(atr14=2.0),
        Strategy6TradePlan(
            risk_amount=2.0,
            reward_amount_1=2.0,
            reward_amount_2=4.0,
            objective_rr_1=1.0,
            objective_rr_2=2.0,
        ),
        lookback_days=30,
        horizon_days=5,
        minimum_samples=1,
    )

    assert result.sample_count == 29


def test_entry_quality_experiments_are_disabled_by_default():
    config = resolve_strategy6_config({})
    timing = Strategy6EntryTiming(state="INVALID", executable=False)
    probability = Strategy6ProbabilityAdjustedRR(
        status="RELIABLE", reliable=True, probability_adjusted_r=-1.0,
    )

    assert entry_quality_hard_filter_reasons(timing, probability, config) == []
    assert entry_quality_blocks_tier("READY_CANDIDATE", timing, probability, config) is False


def test_entry_quality_rules_reject_invalid_or_negative_expectancy_and_downgrade_forming():
    config = resolve_strategy6_config({
        "strategy6": {
            "entry_quality": {
                "entry_timing_enabled": True,
                "probability_rr_enabled": True,
            },
        },
    })
    invalid = Strategy6EntryTiming(state="INVALID", executable=False)
    forming = Strategy6EntryTiming(state="SUPPORT_FORMING", executable=False)
    negative = Strategy6ProbabilityAdjustedRR(
        status="RELIABLE", reliable=True, probability_adjusted_r=-0.1,
    )
    positive = Strategy6ProbabilityAdjustedRR(
        status="RELIABLE", reliable=True, probability_adjusted_r=0.3,
    )

    assert entry_quality_hard_filter_reasons(invalid, positive, config) == [
        "ENTRY_TIMING_INVALID",
    ]
    assert entry_quality_hard_filter_reasons(forming, negative, config) == [
        "PROBABILITY_ADJUSTED_R_LT_0_0",
    ]
    assert entry_quality_blocks_tier("KEY_CANDIDATE", forming, positive, config) is True
    assert entry_quality_blocks_tier(
        "READY_CANDIDATE",
        Strategy6EntryTiming(state="SUPPORT_CONFIRMED", executable=True),
        Strategy6ProbabilityAdjustedRR(
            status="RELIABLE", reliable=True, probability_adjusted_r=0.15,
        ),
        config,
    ) is True


def test_entry_quality_trials_are_single_variable_before_combined():
    trials = build_entry_quality_trial_configs(resolve_strategy6_config({}))

    assert [item["experiment_id"] for item in trials] == [
        "S6_ENTRY_E0_BASELINE",
        "S6_ENTRY_E1_TIMING",
        "S6_ENTRY_E2_PROBABILITY_RR",
        "S6_ENTRY_E3_COMBINED",
    ]
    assert trials[0]["config"]["entry_quality"]["entry_timing_enabled"] is False
    assert trials[1]["config"]["entry_quality"]["entry_timing_enabled"] is True
    assert trials[1]["config"]["entry_quality"]["probability_rr_enabled"] is False
    assert trials[2]["config"]["entry_quality"]["entry_timing_enabled"] is False
    assert trials[2]["config"]["entry_quality"]["probability_rr_enabled"] is True
    assert trials[3]["config"]["entry_quality"]["entry_timing_enabled"] is True
    assert trials[3]["config"]["entry_quality"]["probability_rr_enabled"] is True


def test_frozen_replay_applies_entry_timing_and_probability_rules():
    signal = {
        "code": "000001",
        "evaluation_date": "2025-01-02",
        "setup_id": "setup-1",
        "candidate_type": "KEY_CANDIDATE",
        "snapshot": {
            "objective_rr_2": 3.0,
            "conservative_rr": 2.0,
            "entry_timing_state": "SUPPORT_FORMING",
            "entry_timing_executable": False,
            "probability_rr_status": "RELIABLE",
            "probability_rr_reliable": True,
            "probability_adjusted_r": -0.1,
        },
    }
    trade = {
        "setup_id": "setup-1",
        "signal_date": "2025-01-02",
        "exit_date": "2025-01-10",
        "r_multiple": 1.0,
    }
    trials = build_entry_quality_trial_configs(resolve_strategy6_config({}))

    timing = replay_selection_trial([signal], [trade], trials[1]["config"])
    probability = replay_selection_trial([signal], [trade], trials[2]["config"])

    assert timing["signals"][0]["candidate_type"] == "WATCH_CANDIDATE"
    assert timing["actionable_trade_metrics"]["trades"] == 0
    assert probability["signals"] == []
    assert probability["reason_counts"] == {"PROBABILITY_ADJUSTED_R_LT_0_0": 1}

    comparison = evaluate_frozen_selection_trials([signal], [trade], trials)
    assert comparison[0]["enabled_rules"] == []
    assert comparison[1]["enabled_rules"] == ["entry_timing_enabled"]
    assert comparison[2]["enabled_rules"] == ["probability_rr_enabled"]
    assert comparison[3]["enabled_rules"] == [
        "entry_timing_enabled",
        "probability_rr_enabled",
    ]

from strategy6.models import Strategy6Indicators, Strategy6Support
from strategy6.trade_plan import calculate_trade_plan
from strategy6.validation import resolve_strategy6_config


def test_objective_rr_is_not_manufactured_from_two_r_execution_target():
    ind = Strategy6Indicators(
        current_price=100.0,
        atr14=2.0,
        highest_close_20=102.0,
        highest_close_120=105.0,
        highest_close_250=110.0,
    )
    support = Strategy6Support(
        support_status="MA20_SUPPORT",
        key_support_price=99.0,
        support_zone_low=98.0,
        support_zone_high=101.0,
        pivot_price=102.0,
        box_height=1.0,
    )

    plan = calculate_trade_plan(ind, support, resolve_strategy6_config({}))

    assert plan.objective_target_2 == 102.8
    assert plan.execution_target_2r > plan.objective_target_2
    assert plan.objective_rr_2 < 1.5
    assert plan.risk_reward_ratio_2 == plan.objective_rr_2


def test_stop_buffer_uses_larger_of_three_percent_and_atr():
    ind = Strategy6Indicators(current_price=100.0, atr14=10.0, highest_close_20=120.0)
    support = Strategy6Support(
        support_status="MA20_SUPPORT",
        key_support_price=100.0,
        support_zone_low=99.0,
        support_zone_high=101.0,
        pivot_price=110.0,
        box_height=10.0,
    )

    plan = calculate_trade_plan(ind, support, resolve_strategy6_config({}))

    assert plan.stop_loss_price == 92.0
    assert plan.execution_target_1_5r > plan.suggested_buy_price
    assert plan.execution_target_2_5r > plan.execution_target_2r
    assert plan.execution_target_3_5r > plan.execution_target_2_5r


def test_objective_target_one_never_exceeds_objective_target_two():
    ind = Strategy6Indicators(
        current_price=100.0,
        atr14=1.0,
        highest_close_20=120.0,
        highest_close_120=125.0,
        highest_close_250=130.0,
    )
    support = Strategy6Support(
        support_status="MA20_SUPPORT",
        key_support_price=99.0,
        support_zone_low=98.0,
        support_zone_high=101.0,
        pivot_price=120.0,
        box_height=10.0,
    )

    plan = calculate_trade_plan(ind, support, resolve_strategy6_config({}))

    assert plan.objective_target_1 <= plan.objective_target_2


def test_unknown_pattern_uses_atr_and_historical_pressure_objective_fallback():
    ind = Strategy6Indicators(
        current_price=100.0, atr14=3.0,
        highest_close_20=108.0, highest_close_120=115.0, highest_close_250=120.0,
    )
    support = Strategy6Support(
        support_status="MA20_SUPPORT", key_support_price=99.0,
        support_zone_low=98.0, support_zone_high=101.0,
        pivot_price=0.0, box_height=0.0,
    )

    plan = calculate_trade_plan(
        ind, support,
        resolve_strategy6_config({"strategy6": {"pattern_filter_enabled": False}}),
    )

    assert plan.objective_target_1 == 108.0
    assert plan.objective_target_2 > plan.objective_target_1
    assert plan.objective_rr_2 >= 1.5


def test_wait_breakout_has_audit_trigger_but_no_executable_order_price():
    ind = Strategy6Indicators(
        evaluation_date="2026-07-14", current_price=103.0, atr14=2.0,
        highest_close_20=110.0, highest_close_120=115.0, highest_close_250=120.0,
    )
    support = Strategy6Support(
        support_status="PATTERN_SUPPORT", key_support_price=96.0,
        tactical_support_price=98.0, support_zone_low=98.0, support_zone_high=101.0,
        pivot_price=105.0, box_height=8.0,
    )

    plan = calculate_trade_plan(
        ind, support, resolve_strategy6_config({}), entry_archetype="WAIT_BREAKOUT",
    )

    assert plan.entry_archetype == "WAIT_BREAKOUT"
    assert plan.suggested_buy_price is None
    assert plan.suggested_limit_price is None
    assert plan.buy_zone_low == 105.0
    assert plan.objective_rr_2 > 0


def test_breakout_stop_uses_pivot_failure_instead_of_remote_key_support():
    ind = Strategy6Indicators(
        evaluation_date="2026-07-14", current_price=106.0, atr14=2.0,
        highest_close_20=112.0, highest_close_120=120.0, highest_close_250=125.0,
    )
    support = Strategy6Support(
        support_status="PATTERN_SUPPORT", key_support_price=90.0,
        support_zone_low=89.0, support_zone_high=91.0,
        pivot_price=105.0, box_height=10.0,
    )

    plan = calculate_trade_plan(
        ind, support, resolve_strategy6_config({}), entry_archetype="PIVOT_BREAKOUT",
    )

    assert plan.entry_archetype == "PIVOT_BREAKOUT"
    assert 102.0 < plan.stop_loss_price < 105.0
    assert plan.stop_loss_price > support.key_support_price


def test_support_pullback_stop_uses_nearby_tactical_support_at_entry_price():
    ind = Strategy6Indicators(
        evaluation_date="2026-07-14", current_price=100.0, atr14=2.0,
        highest_close_20=110.0, highest_close_120=120.0, highest_close_250=125.0,
    )
    support = Strategy6Support(
        support_status="KEY_SUPPORT_VALID", key_support_price=90.0,
        tactical_support_price=100.0, support_zone_low=89.0, support_zone_high=91.0,
    )

    plan = calculate_trade_plan(
        ind, support, resolve_strategy6_config({}), entry_archetype="SUPPORT_PULLBACK",
    )

    assert plan.suggested_buy_price == 100.0
    assert 96.0 < plan.stop_loss_price < 100.0
    assert plan.objective_rr_2 > 0

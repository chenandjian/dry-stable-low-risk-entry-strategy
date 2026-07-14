from strategy6.limit_up import calc_limit_up_price
from strategy6.models import Strategy6Indicators, Strategy6Support
from strategy6.trade_plan import calculate_trade_plan
from strategy6.validation import resolve_strategy6_config


def test_trade_plan_starts_next_weekday_and_is_valid_for_three_trading_days():
    ind = Strategy6Indicators(
        evaluation_date="2026-07-10",  # Friday
        current_price=100.0,
        atr14=2.0,
        highest_close_20=110.0,
    )
    support = Strategy6Support(
        support_status="PATTERN_SUPPORT",
        key_support_price=99.0,
        support_zone_low=98.0,
        support_zone_high=101.0,
        pivot_price=110.0,
        box_height=10.0,
    )

    plan = calculate_trade_plan(ind, support, resolve_strategy6_config({}))

    assert plan.signal_date == "2026-07-10"
    assert plan.valid_from_date == "2026-07-13"
    assert plan.valid_until_date == "2026-07-15"
    assert plan.buy_zone_valid_days == 3
    assert plan.suggested_limit_price == plan.suggested_buy_price
    assert "DO_NOT_CHASE_ABOVE_BUY_ZONE" in plan.execution_notes
    assert "ONE_WORD_LIMIT_UP_NO_FILL" in plan.execution_notes
    assert "T1_STOP_UNAVAILABLE_ON_BUY_DAY" in plan.execution_notes


def test_limit_up_price_uses_half_up_tick_rounding():
    assert calc_limit_up_price(10.15, 0.10) == 11.17


def test_start_confirmed_candidate_keeps_phase_signal_date_when_plan_is_not_ready():
    from strategy6.engine import StrongVcpTailEngine
    from tests.test_strategy6_core_rules import build_strategy6_candidate_data

    rows = build_strategy6_candidate_data()
    start_index = len(rows) - 3
    previous = rows[start_index - 1]["close"]
    rows[start_index].update({
        "open": previous * 1.02,
        "high": previous * 1.11,
        "low": previous * 1.01,
        "close": previous * 1.10,
        "volume": 5_000_000,
        "amount": 2_000_000_000,
    })
    start_close = rows[start_index]["close"]
    for offset in (1, 2):
        rows[start_index + offset].update({
            "open": start_close * 0.997,
            "high": start_close * 1.01,
            "low": start_close * 0.99,
            "close": start_close * 1.002,
            "volume": 700_000,
            "amount": 1_000_000_000,
        })

    candidate = StrongVcpTailEngine({"strategy6": {"enable_market_filter": False}}).evaluate_at(
        rows, code="000001"
    ).to_candidate_dict()

    assert candidate["lifecycle_status"] == "START_CONFIRMED"
    assert candidate["signal_date"] == rows[-1]["date"]

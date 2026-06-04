from analyzer.decision import make_dry_stable_decision
from analyzer.key_prices import KeyPricesResult
from analyzer.risk_reward import RiskRewardResult


def _key_prices(current=10.3, zone_low=10.1, zone_high=10.5, pivot=11.0):
    return KeyPricesResult(
        current_price=current,
        entry_zone_low=zone_low,
        entry_zone_high=zone_high,
        pivot=pivot,
        stop_loss=9.8,
        target_1=11.3,
        target_2=11.8,
    )


def _rr(risk_percent=4.8, rr1=2.1, rr2=3.0, can_buy=True):
    return RiskRewardResult(
        risk_percent=risk_percent,
        rr1=rr1,
        rr2=rr2,
        risk_level="低",
        position_advice="30%-40%",
        can_buy=can_buy,
    )


def test_low_buy_requires_price_in_entry_zone():
    decision = make_dry_stable_decision(
        pattern_score=15,
        volume_dry_score=8,
        price_stable_score=8,
        key_prices=_key_prices(current=10.3),
        risk_reward=_rr(),
    )

    assert decision.verdict == "可低吸"
    assert decision.in_low_buy_zone is True


def test_high_scores_above_entry_zone_are_not_low_buy():
    decision = make_dry_stable_decision(
        pattern_score=15,
        volume_dry_score=8,
        price_stable_score=8,
        key_prices=_key_prices(current=10.8),
        risk_reward=_rr(),
    )

    assert decision.verdict == "突破确认"
    assert decision.in_low_buy_zone is False


def test_price_more_than_five_percent_above_pivot_is_chasing():
    decision = make_dry_stable_decision(
        pattern_score=15,
        volume_dry_score=8,
        price_stable_score=8,
        key_prices=_key_prices(current=11.6, pivot=11.0),
        risk_reward=_rr(),
    )

    assert decision.verdict == "不建议买入"
    assert decision.is_chasing is True


def test_hard_rules_block_buying():
    decision = make_dry_stable_decision(
        pattern_score=15,
        volume_dry_score=5,
        price_stable_score=8,
        key_prices=_key_prices(),
        risk_reward=_rr(),
    )

    assert decision.verdict == "不建议买入"
    assert "量能未干" in decision.summary


def test_bad_market_environment_blocks_buying():
    decision = make_dry_stable_decision(
        pattern_score=15,
        volume_dry_score=8,
        price_stable_score=8,
        key_prices=_key_prices(current=10.3),
        risk_reward=_rr(),
        market_status="较差",
    )

    assert decision.verdict == "不建议买入"
    assert "大盘环境较差" in decision.summary

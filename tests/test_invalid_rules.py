from analyzer.decision import make_dry_stable_decision
from analyzer.invalid_rules import find_invalid_conditions
from analyzer.key_prices import KeyPricesResult
from analyzer.risk_reward import RiskRewardResult
from scanner.pattern_detector import CupHandleResult


def _base_data():
    data = []
    for i in range(60):
        close = 50 + i * 0.03
        data.append({
            "date": f"2025-{i // 20 + 1:02d}-{i % 20 + 1:02d}",
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": 10_000_000,
        })
    return data


def _key(current=51.0, low=50.5, high=52.0, pivot=53.0):
    return KeyPricesResult(
        current_price=current,
        entry_zone_low=low,
        entry_zone_high=high,
        pivot=pivot,
        stop_loss=49.0,
        target_1=55.0,
        target_2=57.0,
    )


def _rr():
    return RiskRewardResult(risk_percent=4.0, rr1=2.2, rr2=3.1)


def test_volume_breakdown_is_invalid_condition():
    data = _base_data()
    data[-1]["close"] = data[-2]["close"] * 0.95
    data[-1]["volume"] = 20_000_000

    invalid = find_invalid_conditions(data, _key(), CupHandleResult(found=True))

    assert "最近出现放量大阴线" in invalid


def test_invalid_conditions_block_final_decision():
    decision = make_dry_stable_decision(
        pattern_score=15,
        volume_dry_score=8,
        price_stable_score=8,
        key_prices=_key(current=51.0),
        risk_reward=_rr(),
        invalid_conditions=["最近出现放量大阴线"],
    )

    assert decision.verdict == "不建议买入"
    assert "放量大阴线" in decision.summary


def test_breaking_entry_support_is_invalid():
    invalid = find_invalid_conditions(
        _base_data(),
        _key(current=49.8, low=50.5),
        CupHandleResult(found=True),
    )

    assert "当前价跌破关键支撑" in invalid

from __future__ import annotations

from strategy6.latest_bar_patterns import evaluate_latest_bar_patterns


def _history(latest: dict) -> list[dict]:
    rows = []
    for day in range(1, 16):
        rows.append({
            "date": f"2026-01-{day:02d}",
            "open": 10.0,
            "high": 10.2,
            "low": 9.8,
            "close": 10.0,
            "volume": 1000,
            "amount": 10_000,
        })
    rows.append({"date": "2026-01-16", "volume": 1000, "amount": 10_000, **latest})
    return rows


def test_latest_bar_recognizes_effective_bullish_hammer_with_auditable_metrics():
    pattern = evaluate_latest_bar_patterns(_history({
        "open": 10.0,
        "high": 10.21,
        "low": 9.2,
        "close": 10.2,
    }))[0]

    assert pattern.code == "HAMMER"
    assert pattern.name == "阳线锤子线"
    assert pattern.matched is True
    assert pattern.status == "DETECTED"
    assert pattern.signal_type == "BULLISH_HAMMER"
    assert pattern.metrics["body_ratio"] == 0.19802
    assert pattern.metrics["lower_shadow_to_body"] == 4.0
    assert pattern.metrics["upper_shadow_to_body"] == 0.05
    assert pattern.metrics["range_to_previous_close"] == 0.101
    assert pattern.metrics["range_to_atr14"] >= 0.5


def test_latest_bar_rejects_geometrically_valid_but_too_small_hammer():
    pattern = evaluate_latest_bar_patterns(_history({
        "open": 10.0,
        "high": 10.0105,
        "low": 9.9595,
        "close": 10.01,
    }))[0]

    assert pattern.matched is False
    assert "HAMMER_RANGE_LT_PREVIOUS_CLOSE_0_8PCT" in pattern.risks
    assert "HAMMER_RANGE_LT_ATR14_0_5" in pattern.risks


def test_latest_bar_rejects_hammer_with_excess_upper_shadow():
    pattern = evaluate_latest_bar_patterns(_history({
        "open": 10.0,
        "high": 10.3,
        "low": 9.0,
        "close": 10.2,
    }))[0]

    assert pattern.matched is False
    assert "HAMMER_UPPER_SHADOW_GT_BODY_0_1" in pattern.risks


def test_latest_bar_identifies_bearish_hammer_separately():
    pattern = evaluate_latest_bar_patterns(_history({
        "open": 10.2,
        "high": 10.21,
        "low": 9.2,
        "close": 10.0,
    }))[0]

    assert pattern.matched is True
    assert pattern.name == "阴线锤子线"
    assert pattern.signal_type == "BEARISH_HAMMER"
    assert "BEARISH_HAMMER_REQUIRES_CONFIRMATION" in pattern.risks

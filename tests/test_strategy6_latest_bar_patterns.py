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


def _history_with_context(latest: dict, closes: list[float]) -> list[dict]:
    rows = _history(latest)
    for row, close in zip(rows[-6:-1], closes, strict=True):
        row.update({"open": close, "high": close + 0.2, "low": close - 0.2, "close": close})
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


def test_latest_bar_recognizes_effective_inverted_hammer_after_pullback():
    patterns = evaluate_latest_bar_patterns(_history_with_context({
        "open": 10.0,
        "high": 10.81,
        "low": 9.99,
        "close": 10.2,
    }, [10.8, 10.6, 10.4, 10.2, 10.0]))
    pattern = next(item for item in patterns if item.code == "INVERTED_HAMMER")

    assert pattern.matched is True
    assert pattern.name == "阳线倒锤子线"
    assert pattern.signal_type == "BULLISH_INVERTED_HAMMER"
    assert pattern.metrics["body_ratio"] == 0.243902
    assert pattern.metrics["upper_shadow_to_body"] == 3.05
    assert pattern.metrics["lower_shadow_to_body"] == 0.05
    assert pattern.metrics["context_return_5"] < 0
    assert "INVERTED_HAMMER_REQUIRES_CONFIRMATION" in pattern.risks


def test_latest_bar_labels_same_geometry_as_shooting_star_after_rise():
    patterns = evaluate_latest_bar_patterns(_history_with_context({
        "open": 10.0,
        "high": 10.81,
        "low": 9.99,
        "close": 10.2,
    }, [9.2, 9.4, 9.6, 9.8, 10.0]))
    pattern = next(item for item in patterns if item.code == "INVERTED_HAMMER")

    assert pattern.matched is True
    assert pattern.name == "射击之星风险"
    assert pattern.signal_type == "SHOOTING_STAR"
    assert "SHOOTING_STAR_AFTER_RISE" in pattern.risks


def test_latest_bar_rejects_inverted_hammer_with_excess_lower_shadow():
    patterns = evaluate_latest_bar_patterns(_history_with_context({
        "open": 10.0,
        "high": 10.81,
        "low": 9.95,
        "close": 10.2,
    }, [10.8, 10.6, 10.4, 10.2, 10.0]))
    pattern = next(item for item in patterns if item.code == "INVERTED_HAMMER")

    assert pattern.matched is False
    assert "INVERTED_HAMMER_LOWER_SHADOW_GT_BODY_0_1" in pattern.risks


def test_latest_bar_rejects_geometrically_valid_but_too_small_inverted_hammer():
    patterns = evaluate_latest_bar_patterns(_history_with_context({
        "open": 10.0,
        "high": 10.045,
        "low": 9.9995,
        "close": 10.01,
    }, [10.8, 10.6, 10.4, 10.2, 10.0]))
    pattern = next(item for item in patterns if item.code == "INVERTED_HAMMER")

    assert pattern.matched is False
    assert "INVERTED_HAMMER_RANGE_LT_PREVIOUS_CLOSE_0_8PCT" in pattern.risks
    assert "INVERTED_HAMMER_RANGE_LT_ATR14_0_5" in pattern.risks

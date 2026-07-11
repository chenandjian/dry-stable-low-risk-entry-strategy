from datetime import date, timedelta

from strategy6.box_tail import evaluate_compact_kline


def _row(index, close, *, open_price=None, high=None, low=None, volume=500_000):
    open_price = close * 0.998 if open_price is None else open_price
    return {
        "date": (date(2026, 1, 1) + timedelta(days=index)).isoformat(),
        "open": open_price,
        "high": high if high is not None else close * 1.008,
        "low": low if low is not None else close * 0.992,
        "close": close,
        "volume": volume,
    }


COMPACT_CONFIG = {
    "enabled": True,
    "window_days": 5,
    "avg_body_ratio_max": 0.025,
    "premium_avg_body_ratio_max": 0.018,
    "max_body_ratio_max": 0.04,
    "close_range_max": 0.05,
    "premium_close_range_max": 0.03,
    "min_overlap_ratio": 0.50,
    "premium_overlap_ratio": 0.65,
    "min_overlap_pair_count": 3,
    "max_gap_ratio": 0.03,
    "atr_contraction_ratio_max": 0.80,
    "premium_atr_contraction_ratio_max": 0.65,
}


def _compact_rows():
    return [_row(i, close) for i, close in enumerate([10.00, 10.05, 10.02, 10.08, 10.06])]


def test_compact_kline_passes_tight_overlapping_atr_contracted_tail():
    result = evaluate_compact_kline(
        _compact_rows(),
        atr5=0.12,
        atr20=0.20,
        tail_volume_ratio=0.55,
        premium_tail_volume_ratio_max=0.60,
        has_volume_selloff=False,
        config=COMPACT_CONFIG,
    )

    assert result.passed is True
    assert result.score >= 8
    assert result.premium is True
    assert result.overlap_pair_count >= 3
    assert result.quality_tag == "BOX_COMPACT_READY"


def test_compact_kline_large_body_fails_without_becoming_a_box_hard_failure():
    rows = _compact_rows()
    rows[-1]["open"] = rows[-1]["close"] * 0.94
    rows[-1]["low"] = rows[-1]["open"] * 0.99

    result = evaluate_compact_kline(
        rows,
        atr5=0.12,
        atr20=0.20,
        tail_volume_ratio=0.55,
        premium_tail_volume_ratio_max=0.60,
        has_volume_selloff=False,
        config=COMPACT_CONFIG,
    )

    assert result.passed is False
    assert "COMPACT_MAX_BODY_TOO_LARGE" in result.risk_tags


def test_compact_kline_rejects_insufficient_atr_overlap_gap_and_selloff_data():
    rows = _compact_rows()
    rows[-1]["open"] = rows[-2]["close"] * 1.04
    rows[-1]["high"] = rows[-1]["open"] * 1.01
    rows[-1]["low"] = rows[-1]["open"] * 0.99

    result = evaluate_compact_kline(
        rows,
        atr5=0.19,
        atr20=0.20,
        tail_volume_ratio=0.70,
        premium_tail_volume_ratio_max=0.60,
        has_volume_selloff=True,
        config=COMPACT_CONFIG,
    )

    assert result.passed is False
    assert result.gap_count == 1
    assert "COMPACT_ATR_NOT_CONTRACTED" in result.risk_tags
    assert "COMPACT_GAP_TOO_LARGE" in result.risk_tags
    assert "COMPACT_VOLUME_SELLOFF" in result.risk_tags


def test_compact_kline_disabled_returns_zero_without_calculation():
    result = evaluate_compact_kline(
        _compact_rows(),
        atr5=0.12,
        atr20=0.20,
        tail_volume_ratio=0.55,
        premium_tail_volume_ratio_max=0.60,
        has_volume_selloff=False,
        config={**COMPACT_CONFIG, "enabled": False},
    )

    assert result.enabled is False
    assert result.passed is False
    assert result.score == 0
    assert result.quality_tag == "NONE"


def test_compact_kline_requires_at_least_three_valid_overlapping_pairs():
    rows = _compact_rows()
    rows[1].update({"low": 10.30, "high": 10.40, "open": 10.35, "close": 10.36})
    rows[3].update({"low": 10.40, "high": 10.50, "open": 10.45, "close": 10.46})

    result = evaluate_compact_kline(
        rows,
        atr5=0.12,
        atr20=0.20,
        tail_volume_ratio=0.55,
        premium_tail_volume_ratio_max=0.60,
        has_volume_selloff=False,
        config=COMPACT_CONFIG,
    )

    assert result.overlap_pair_count < 3
    assert result.passed is False
    assert "COMPACT_OVERLAP_INSUFFICIENT" in result.risk_tags


def test_compact_premium_uses_configured_tail_volume_threshold():
    result = evaluate_compact_kline(
        _compact_rows(),
        atr5=0.12,
        atr20=0.20,
        tail_volume_ratio=0.55,
        premium_tail_volume_ratio_max=0.50,
        has_volume_selloff=False,
        config=COMPACT_CONFIG,
    )

    assert result.passed is True
    assert result.premium is False

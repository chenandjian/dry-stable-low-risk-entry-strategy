# tests/test_volume_dry.py
import pytest
from analyzer.volume_dry import score_volume_dry, VolumeDryResult


def test_high_score_when_volume_is_very_dry():
    """极度缩量应得高分"""
    data = _make_dry_data(
        recent_vs_ma20=0.60,       # V5 is 60% of MA20
        recent_vs_ma50=0.50,       # V5 is 50% of MA50
        shrinking=True,            # V1 > V2 > V3
        down_day_vol_ratio=0.70,   # down days have low volume
        has_extreme_low=True,      # one day in V5 at 35% of MA50
        no_breakdown=True,
    )
    result = score_volume_dry(data)
    assert result.total_score >= 7
    assert result.verdict == "可低吸"


def test_low_score_when_volume_is_not_dry():
    """成交量未萎缩应得低分"""
    data = _make_dry_data(
        recent_vs_ma20=1.2,
        recent_vs_ma50=1.1,
        shrinking=False,
        down_day_vol_ratio=1.3,
        has_extreme_low=False,
        no_breakdown=True,
    )
    result = score_volume_dry(data)
    assert result.total_score < 6
    assert result.verdict != "可低吸"


def test_breakdown_caps_score():
    """放量大阴线封顶5分"""
    data = _make_dry_data(
        recent_vs_ma20=0.60,
        recent_vs_ma50=0.50,
        shrinking=True,
        down_day_vol_ratio=0.50,
        has_extreme_low=True,
        no_breakdown=False,  # has breakdown candle at the end
    )
    result = score_volume_dry(data)
    assert result.total_score <= 5


def test_empty_data():
    result = score_volume_dry([])
    assert result.total_score == 0


def _make_dry_data(recent_vs_ma20, recent_vs_ma50, shrinking, down_day_vol_ratio, has_extreme_low, no_breakdown):
    """Generate deterministic test data for volume dry scoring.

    Builds 50 OHLC records from oldest (index 0) to newest (index 49).
    Volumes are deterministic — no random noise — so ratios are predictable.
    """
    base_vol = 10_000_000.0
    ma50_vol = base_vol * 1.1  # 11_000_000

    v5_target = base_vol * recent_vs_ma20  # target average for last 5 days

    data = []
    for i in range(50):
        # ---- volume ----
        if i >= 45:             # last 5 days: V5 segment
            vol = v5_target
        elif i >= 40:           # days 5-10 ago: V2 segment
            if shrinking:
                vol = v5_target * 1.25   # higher than V5
            else:
                vol = v5_target * 0.90   # flat / rising
        elif i >= 35:           # days 10-15 ago: V1 segment
            if shrinking:
                vol = v5_target * 1.50   # clearly highest
            else:
                vol = v5_target * 1.00
        else:                   # older fill: close to base_vol
            vol = base_vol

        # ---- close ----
        # Alternate around 50 to create up/down days
        close = 50.0 + (0.5 if i % 2 == 0 else -0.5)

        # ---- down-day volume adjustment ----
        prev_close = 50.0 if len(data) == 0 else data[-1]["close"]
        is_down = close < prev_close
        if is_down:
            vol *= down_day_vol_ratio

        # ---- extreme low volume in last 5 days (i == 47, third-from-last) ----
        if i == 47 and has_extreme_low:
            vol = ma50_vol * 0.35  # 35% of MA50 → well below 0.50 threshold

        # ---- breakdown candle in last 3 days ----
        if i >= 47 and not no_breakdown:
            # Override close and volume for a breakdown day:
            # drop >= 3% + volume spike >= 1.5x MA20
            if i == 47:
                close = prev_close * 0.95       # -5% drop
            elif i == 48:
                close = data[-1]["close"] * 0.95
            else:  # i == 49
                close = data[-1]["close"] * 0.95
            vol = base_vol * 1.8  # 1.8x base_vol — well above 1.5x MA20
            is_down = True  # stays a down day but volume already set

        data.append({
            "date": f"2026-{str(6).zfill(2)}-{str(i + 1).zfill(2)}",
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": vol,
        })

    return data

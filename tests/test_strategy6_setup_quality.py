from datetime import date, timedelta

from strategy6.models import Strategy6Phase, Strategy6Start
from strategy6.setup_quality import evaluate_setup_quality


def _rows(length=90):
    result = []
    for index in range(length):
        close = 10.0 + index * 0.01
        result.append({
            "date": (date(2024, 1, 1) + timedelta(days=index)).isoformat(),
            "open": close * 0.997,
            "high": close * 1.015,
            "low": close * 0.985,
            "close": close,
            "volume": 1_000_000,
            "amount": 600_000_000,
        })
    return result


def _phase(rows, start_index=55, tail_days=7):
    return Strategy6Phase(
        valid=True,
        start_index=start_index,
        consolidation_start_index=start_index + 1,
        tail_start_index=len(rows) - tail_days,
        signal_index=len(rows) - 1,
    )


def _market(rows, daily_gain=0.0005):
    close = 3000.0
    market = []
    for row in rows:
        close *= 1 + daily_gain
        market.append({"date": row["date"], "close": close, "volume": 1_000_000})
    return {"hs300": market}


def test_setup_quality_rewards_retention_dry_down_volume_and_contraction():
    rows = _rows()
    start_index = 55
    previous = rows[start_index - 1]["close"]
    rows[start_index].update({"close": previous * 1.10, "high": previous * 1.11, "low": previous, "volume": 3_000_000})
    for index in range(start_index + 1, len(rows)):
        drift = (index - start_index) * 0.001
        close = previous * (1.08 + drift)
        tail = index >= len(rows) - 7
        rows[index].update({
            "open": close * (0.999 if tail else 0.995),
            "high": close * (1.005 if tail else 1.018),
            "low": close * (0.995 if tail else 0.982),
            "close": close,
            "volume": 350_000 if tail else 700_000,
        })
    phase = _phase(rows, start_index)
    start = Strategy6Start(start_date=rows[start_index]["date"], start_low=rows[start_index]["low"])

    quality = evaluate_setup_quality(rows, start, phase, _market(rows))

    assert quality.score >= 18
    assert quality.gain_retention_ratio >= 0.70
    assert quality.distribution_day_count == 0
    assert quality.volatility_contraction_ratio < 0.60
    assert quality.relative_strength_trend in {"IMPROVING", "STABLE"}
    assert "DISTRIBUTION_PRESSURE_HIGH" not in quality.risk_tags


def test_setup_quality_flags_distribution_fading_strength_and_failed_breakouts():
    rows = _rows()
    start_index = 55
    previous = rows[start_index - 1]["close"]
    rows[start_index].update({"close": previous * 1.10, "high": previous * 1.11, "low": previous, "volume": 3_000_000})
    for index in range(start_index + 1, len(rows)):
        close = previous * (1.12 - (index - start_index) * 0.004)
        volume = 1_800_000 if index in {65, 70, 75, 80} else 700_000
        if index in {65, 70, 75, 80}:
            close *= 0.97
        rows[index].update({
            "open": close * 1.02,
            "high": close * 1.03,
            "low": close * 0.98,
            "close": close,
            "volume": volume,
        })
    # Two breakout-and-fail sequences inside the consolidation.
    for breakout_index in (62, 72):
        pivot = max(row["close"] for row in rows[breakout_index - 20:breakout_index])
        rows[breakout_index]["close"] = pivot * 1.02
        rows[breakout_index + 2]["close"] = pivot * 0.97
    last_base = rows[-7]["close"]
    for offset, row in enumerate(rows[-6:], start=1):
        row["close"] = last_base * (0.96 ** offset)
        row["open"] = row["close"] * 1.02
        row["high"] = row["open"] * 1.01
        row["low"] = row["close"] * 0.98
        row["volume"] = 1_900_000
    phase = _phase(rows, start_index)
    start = Strategy6Start(start_date=rows[start_index]["date"], start_low=rows[start_index]["low"])

    quality = evaluate_setup_quality(rows, start, phase, _market(rows, daily_gain=0.0015))

    assert quality.distribution_day_count >= 3
    assert quality.failed_breakout_count >= 2
    assert quality.relative_strength_trend == "FADING"
    assert "DISTRIBUTION_PRESSURE_HIGH" in quality.risk_tags
    assert "REPEATED_FAILED_BREAKOUTS" in quality.risk_tags
    assert "RELATIVE_STRENGTH_FADING" in quality.risk_tags


def test_setup_quality_does_not_invent_relative_strength_without_fresh_hs300():
    rows = _rows()
    phase = _phase(rows)
    start = Strategy6Start(start_date=rows[55]["date"], start_low=rows[55]["low"])

    quality = evaluate_setup_quality(rows, start, phase, {})

    assert quality.relative_strength_trend == "UNKNOWN"
    assert "RS_TREND_UNAVAILABLE" in quality.reasons

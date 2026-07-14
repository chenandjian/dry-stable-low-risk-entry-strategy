"""Consolidation quality evidence for Strategy6."""
from __future__ import annotations

from strategy6.market import compute_relative_strength_periods
from strategy6.models import Strategy6Phase, Strategy6SetupQuality, Strategy6Start


def evaluate_setup_quality(
    rows: list[dict],
    start: Strategy6Start,
    phase: Strategy6Phase,
    market_data_by_symbol: dict[str, list[dict]] | None,
) -> Strategy6SetupQuality:
    if not rows or phase.start_index < 1 or phase.signal_index < phase.start_index:
        return Strategy6SetupQuality(reasons=["SETUP_QUALITY_DATA_UNAVAILABLE"])

    setup_rows = rows[phase.start_index + 1:phase.signal_index + 1]
    prior_close = float(rows[phase.start_index - 1]["close"])
    current_close = float(rows[phase.signal_index]["close"])
    max_close = max(float(row["close"]) for row in rows[phase.start_index:phase.signal_index + 1])
    max_gain = _return(prior_close, max_close)
    retained_gain = _return(prior_close, current_close)
    gain_retention = max(0.0, min(1.5, retained_gain / max_gain)) if max_gain > 0 else 0.0
    distribution_days = _distribution_day_count(rows, phase.start_index + 1, phase.signal_index)
    up_down_ratio = _up_down_volume_ratio(rows, phase.start_index + 1, phase.signal_index)
    volatility_ratio = _volatility_contraction_ratio(rows, phase)
    failed_breakouts = _failed_breakout_count(rows, phase.start_index + 1, phase.signal_index)
    rs_trend, rs_reasons = _relative_strength_trend(rows, market_data_by_symbol)

    score = (
        _retention_score(gain_retention)
        + _distribution_score(distribution_days)
        + _volume_balance_score(up_down_ratio)
        + _contraction_score(volatility_ratio)
        + {"IMPROVING": 3, "STABLE": 2, "MIXED": 1}.get(rs_trend, 0)
        + (2 if failed_breakouts == 0 else 1 if failed_breakouts == 1 else 0)
    )
    reasons = [
        f"gain_retention={gain_retention:.3f}",
        f"distribution_days={distribution_days}",
        f"up_down_volume={up_down_ratio:.3f}",
        f"volatility_contraction={volatility_ratio:.3f}",
        f"failed_breakouts={failed_breakouts}",
        f"rs_trend={rs_trend}",
        *rs_reasons,
    ]
    risks: list[str] = []
    if gain_retention < 0.35:
        risks.append("START_GAIN_POORLY_RETAINED")
    if distribution_days >= 3:
        risks.append("DISTRIBUTION_PRESSURE_HIGH")
    if setup_rows and up_down_ratio < 0.75:
        risks.append("DOWN_VOLUME_DOMINATES")
    if volatility_ratio > 1.0:
        risks.append("VOLATILITY_NOT_CONTRACTING")
    if rs_trend == "FADING":
        risks.append("RELATIVE_STRENGTH_FADING")
    if failed_breakouts >= 2:
        risks.append("REPEATED_FAILED_BREAKOUTS")
    return Strategy6SetupQuality(
        score=max(0, min(25, int(score))),
        gain_retention_ratio=round(gain_retention, 6),
        distribution_day_count=distribution_days,
        up_down_volume_ratio=round(up_down_ratio, 6),
        volatility_contraction_ratio=round(volatility_ratio, 6),
        failed_breakout_count=failed_breakouts,
        relative_strength_trend=rs_trend,
        reasons=reasons,
        risk_tags=risks,
    )


def _distribution_day_count(rows: list[dict], start: int, end: int) -> int:
    count = 0
    for index in range(max(1, start), end + 1):
        previous = rows[index - 1]
        current = rows[index]
        day_return = _return(float(previous["close"]), float(current["close"]))
        prior = rows[max(0, index - 20):index]
        average_volume = sum(float(row["volume"]) for row in prior) / len(prior) if prior else 0.0
        if (
            day_return <= -0.02
            and float(current["volume"]) >= float(previous["volume"])
            and float(current["volume"]) >= average_volume
        ):
            count += 1
    return count


def _up_down_volume_ratio(rows: list[dict], start: int, end: int) -> float:
    up: list[float] = []
    down: list[float] = []
    for index in range(max(1, start), end + 1):
        current = rows[index]
        previous = rows[index - 1]
        day_return = _return(float(previous["close"]), float(current["close"]))
        if day_return > 0:
            up.append(float(current["volume"]))
        elif day_return < 0:
            down.append(float(current["volume"]))
    if not down:
        return 2.0 if up else 1.0
    if not up:
        return 0.0
    return (sum(up) / len(up)) / (sum(down) / len(down))


def _volatility_contraction_ratio(rows: list[dict], phase: Strategy6Phase) -> float:
    tail = rows[phase.tail_start_index:phase.signal_index + 1]
    baseline_end = phase.tail_start_index
    baseline_start = max(phase.consolidation_start_index, baseline_end - 20)
    baseline = rows[baseline_start:baseline_end]
    tail_range = _average_true_range(tail)
    baseline_range = _average_true_range(baseline)
    return tail_range / baseline_range if baseline_range > 0 else 0.0


def _failed_breakout_count(rows: list[dict], start: int, end: int) -> int:
    failures = 0
    index = max(20, start)
    while index <= end:
        prior_high = max(float(row["close"]) for row in rows[index - 20:index])
        if float(rows[index]["close"]) > prior_high * 1.005:
            follow_end = min(end + 1, index + 4)
            if any(float(row["close"]) < prior_high * 0.995 for row in rows[index + 1:follow_end]):
                failures += 1
                index = follow_end
                continue
        index += 1
    return failures


def _relative_strength_trend(
    rows: list[dict],
    market_data_by_symbol: dict[str, list[dict]] | None,
) -> tuple[str, list[str]]:
    periods = compute_relative_strength_periods(
        rows,
        market_data_by_symbol,
        expected_trade_date=str(rows[-1].get("date") or ""),
    )
    if periods is None:
        return "UNKNOWN", ["RS_TREND_UNAVAILABLE"]
    rs5, rs10, rs20 = periods[5], periods[10], periods[20]
    slope5, slope10, slope20 = rs5 / 5, rs10 / 10, rs20 / 20
    if slope5 >= slope10 - 0.001 and slope10 >= slope20 - 0.001:
        return "IMPROVING", []
    if slope5 < slope20 - 0.003:
        return "FADING", []
    if max(slope5, slope10, slope20) - min(slope5, slope10, slope20) <= 0.002:
        return "STABLE", []
    return "MIXED", []


def _average_true_range(rows: list[dict]) -> float:
    if not rows:
        return 0.0
    return sum(float(row["high"]) - float(row["low"]) for row in rows) / len(rows)


def _retention_score(value: float) -> int:
    return 6 if value >= 0.75 else 4 if value >= 0.55 else 2 if value >= 0.35 else 0


def _distribution_score(count: int) -> int:
    return 5 if count == 0 else 3 if count == 1 else 1 if count == 2 else 0


def _volume_balance_score(value: float) -> int:
    return 4 if value >= 1.20 else 2 if value >= 0.90 else 0


def _contraction_score(value: float) -> int:
    return 5 if 0 < value <= 0.65 else 3 if value <= 0.80 else 1 if value <= 1.0 else 0


def _return(previous: float, current: float) -> float:
    return current / previous - 1.0 if previous > 0 else 0.0

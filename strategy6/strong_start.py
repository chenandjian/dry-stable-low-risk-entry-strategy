"""Strategy6 strong start detection."""
from __future__ import annotations

from strategy6.indicators import _return_between
from strategy6.limit_up import get_limit_up_pct, is_limit_up_day, is_one_word_limit_up, is_touched_limit_up_failed
from strategy6.models import Strategy6Indicators, Strategy6Start


PASSING_START_TYPES = {"NORMAL_STRONG_BREAKOUT", "VOLUME_LIMIT_UP", "LOW_VOLUME_LIMIT_UP", "ONE_WORD_LIMIT_UP"}


def evaluate_strong_start(rows: list[dict], ind: Strategy6Indicators, config: dict, code: str) -> Strategy6Start:
    best = Strategy6Start(limit_up_pct=get_limit_up_pct(code))
    start_idx = max(1, len(rows) - int(config["start_lookback_days"]) - 1)
    for idx in range(start_idx, len(rows)):
        candidate = _build_start_candidate(rows, idx, config, code)
        # Prefer event quality over recency. Recency only wins when the two
        # events are close enough in quality to represent the same setup.
        if (
            candidate.start_type in PASSING_START_TYPES
            and candidate.start_grade in {"S", "A"}
            and not candidate.failure_reasons
        ):
            if _prefer_event(candidate, best):
                best = candidate
        elif best.start_type not in PASSING_START_TYPES and _rank(candidate) >= _rank(best):
            best = candidate
    best.high_trigger = _high_trigger(ind, config)
    if best.start_type not in PASSING_START_TYPES:
        momentum_grade, momentum_index = _momentum_start(rows, ind)
        if momentum_grade == "B" and momentum_index >= 0:
            row = rows[momentum_index]
            best = Strategy6Start(
                start_date=row["date"],
                start_type="B_GRADE_MOMENTUM",
                start_grade="B",
                start_low=row["low"],
                days_since_start=len(rows) - momentum_index - 1,
                limit_up_pct=get_limit_up_pct(code),
                high_trigger=_high_trigger(ind, config),
            )
    return best


def find_historical_start_anchor(
    rows: list[dict],
    config: dict,
    code: str,
    *,
    end_index: int,
) -> Strategy6Start | None:
    """Return the strongest event-day start at or before a VCP's first peak."""
    if end_index < 1:
        return None
    first = max(1, end_index - int(config["start_lookback_days"]))
    candidates = [
        _build_start_candidate(rows, index, config, code)
        for index in range(first, min(end_index, len(rows) - 1) + 1)
    ]
    passing = [item for item in candidates if item.start_type in PASSING_START_TYPES]
    if not passing:
        return None
    return max(passing, key=lambda item: (item.event_quality_score, item.start_date))


def _build_start_candidate(rows: list[dict], idx: int, config: dict, code: str) -> Strategy6Start:
    prev = rows[idx - 1]
    row = rows[idx]
    v20 = _avg_prior_volume(rows, idx, 20)
    day_return = _return_between(prev["close"], row["close"])
    volume_ratio = row["volume"] / v20 if v20 > 0 else 0.0
    close_position = _close_position(row)
    amount_yi = row["amount"] / 100_000_000
    self_amount_percentile = _prior_amount_percentile(rows, idx, 60)
    one_word = is_one_word_limit_up(code, prev["close"], row["open"], row["high"], row["low"], row["close"])
    limit_up = is_limit_up_day(code, prev["close"], row["close"])
    touched_failed = is_touched_limit_up_failed(code, prev["close"], row["high"], row["close"])
    start_type = "NONE"
    if one_word:
        start_type = "ONE_WORD_LIMIT_UP"
    elif limit_up and volume_ratio >= config["limit_up_volume_ratio"]:
        start_type = "VOLUME_LIMIT_UP"
    elif limit_up and config["low_volume_limit_up_min_ratio"] <= volume_ratio < config["limit_up_volume_ratio"]:
        start_type = "LOW_VOLUME_LIMIT_UP"
    elif (
        day_return >= config["normal_start_return"]
        and volume_ratio >= config["normal_start_volume_ratio"]
        and close_position >= config["normal_start_close_position"]
        and amount_yi >= config["normal_start_min_amount_yi"]
        and self_amount_percentile >= config["normal_start_self_amount_percentile"]
    ):
        start_type = "NORMAL_STRONG_BREAKOUT"
    elif touched_failed:
        start_type = "TOUCHED_LIMIT_UP_FAILED"

    candidate = Strategy6Start(
        start_date=row["date"],
        start_type=start_type,
        start_day_return=day_return,
        start_day_volume_ratio=round(volume_ratio, 6),
        start_day_amount=round(amount_yi, 4),
        start_day_close_position=round(close_position, 6),
        start_day_self_amount_percentile=round(self_amount_percentile, 6),
        start_low=row["low"],
        is_limit_up=limit_up,
        is_one_word_limit_up=one_word,
        limit_up_pct=get_limit_up_pct(code),
        days_since_start=len(rows) - idx - 1,
    )
    if start_type in PASSING_START_TYPES:
        _apply_event_quality(candidate, rows, idx, prev["close"])
        candidate.start_grade = _grade(candidate.event_quality_score)
    return candidate


def _momentum_start(rows: list[dict], ind: Strategy6Indicators) -> tuple[str, int]:
    if ind.return_5 >= 0.08 and len(rows) > 5:
        return "B", len(rows) - 6
    if ind.return_10 >= 0.12 and len(rows) > 10:
        return "B", len(rows) - 11
    if ind.return_20 >= 0.20 and len(rows) > 20:
        return "B", len(rows) - 21
    return "NONE", -1


def _grade(event_quality_score: int) -> str:
    if event_quality_score >= 16:
        return "S"
    if event_quality_score >= 11:
        return "A"
    if event_quality_score >= 8:
        return "B"
    return "NONE"


def _apply_event_quality(
    start: Strategy6Start,
    rows: list[dict],
    idx: int,
    previous_close: float,
) -> None:
    start_close = float(rows[idx]["close"])
    follow = rows[idx + 1:min(len(rows), idx + 6)]
    last_close = float(follow[-1]["close"]) if follow else start_close
    observed_closes = [start_close, *(float(row["close"]) for row in follow)]
    max_close = max(observed_closes)
    max_gain = _return_between(previous_close, max_close)
    retained_gain = _return_between(previous_close, last_close)
    retention = retained_gain / max_gain if max_gain > 0 else 0.0
    start.follow_through_return_5 = round(_return_between(start_close, last_close), 6)
    start.gain_retention_ratio = round(max(0.0, min(1.5, retention)), 6)
    start.max_close_drawdown_5 = round(
        min(0.0, min(_return_between(start_close, close) for close in observed_closes)),
        6,
    )

    failures: list[str] = []
    if start.start_type != "ONE_WORD_LIMIT_UP" and follow and min(observed_closes[1:]) < start.start_low:
        failures.append("START_LOW_BROKEN")
    if len(follow) >= 3 and last_close <= previous_close * 1.005:
        failures.append("START_GAIN_FULLY_RETRACED")
    prior = rows[idx]
    for row in follow:
        day_return = _return_between(float(prior["close"]), float(row["close"]))
        if day_return <= -0.04 and float(row["volume"]) >= float(prior["volume"]) * 1.2:
            failures.append("START_FOLLOW_THROUGH_DISTRIBUTION")
            break
        prior = row
    start.failure_reasons = failures

    type_score = {
        "NORMAL_STRONG_BREAKOUT": 6,
        "LOW_VOLUME_LIMIT_UP": 7,
        "VOLUME_LIMIT_UP": 8,
        "ONE_WORD_LIMIT_UP": 6,
    }.get(start.start_type, 0)
    return_score = 3 if start.start_day_return >= 0.09 else 2 if start.start_day_return >= 0.07 else 1
    volume_score = 3 if start.start_day_volume_ratio >= 2.5 else 2 if start.start_day_volume_ratio >= 2.0 else 1
    close_score = 2 if start.start_day_close_position >= 0.75 else 1 if start.start_day_close_position >= 0.65 else 0
    attention_score = 2 if start.start_day_self_amount_percentile >= 0.90 else 1 if start.start_day_self_amount_percentile >= 0.80 else 0
    if not follow:
        retention_score = 1
    elif start.gain_retention_ratio >= 0.80:
        retention_score = 4
    elif start.gain_retention_ratio >= 0.60:
        retention_score = 3
    elif start.gain_retention_ratio >= 0.40:
        retention_score = 1
    else:
        retention_score = 0
    follow_score = 1 if start.follow_through_return_5 >= 0.03 else 0
    failure_penalty = min(6, len(failures) * 3)
    start.event_quality_score = max(0, min(
        20,
        type_score + return_score + volume_score + close_score
        + attention_score + retention_score + follow_score - failure_penalty,
    ))


def _prefer_event(candidate: Strategy6Start, current: Strategy6Start) -> bool:
    if current.start_type not in PASSING_START_TYPES or current.failure_reasons:
        return True
    quality_diff = candidate.event_quality_score - current.event_quality_score
    if quality_diff > 2:
        return True
    if quality_diff < -2:
        return False
    if candidate.start_date != current.start_date:
        return candidate.start_date > current.start_date
    return _rank(candidate) > _rank(current)


def _high_trigger(ind: Strategy6Indicators, config: dict) -> str:
    if ind.highest_close_120 <= 0:
        return ""
    if ind.highest_close_20 >= ind.highest_close_120:
        return "new_120d_high"
    if ind.highest_close_20 >= ind.highest_close_120 * config["near_120d_high_ratio"]:
        return "near_120d_high"
    return ""


def _rank(start: Strategy6Start) -> int:
    type_rank = {
        "NONE": 0,
        "TOUCHED_LIMIT_UP_FAILED": 1,
        "NORMAL_STRONG_BREAKOUT": 2,
        "LOW_VOLUME_LIMIT_UP": 3,
        "VOLUME_LIMIT_UP": 4,
        "ONE_WORD_LIMIT_UP": 5,
        "B_GRADE_MOMENTUM": 2,
    }.get(start.start_type, 0)
    grade_rank = {"NONE": 0, "B": 1, "A": 2, "S": 3}.get(start.start_grade, 0)
    return type_rank * 10 + grade_rank


def _close_position(row: dict) -> float:
    span = row["high"] - row["low"]
    return (row["close"] - row["low"]) / span if span > 0 else 1.0


def _avg_prior_volume(rows: list[dict], idx: int, days: int) -> float:
    start = max(0, idx - days)
    selected = rows[start:idx]
    return sum(r["volume"] for r in selected) / len(selected) if selected else 0.0


def _prior_amount_percentile(rows: list[dict], idx: int, days: int) -> float:
    start = max(0, idx - days)
    selected = [float(row.get("amount") or 0.0) for row in rows[start:idx]]
    current = float(rows[idx].get("amount") or 0.0)
    if not selected or current <= 0:
        return 0.0
    return sum(1 for value in selected if value <= current) / len(selected)

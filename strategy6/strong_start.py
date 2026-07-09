"""Strategy6 strong start detection."""
from __future__ import annotations

from strategy6.indicators import _return_between
from strategy6.limit_up import get_limit_up_pct, is_limit_up_day, is_one_word_limit_up, is_touched_limit_up_failed
from strategy6.models import Strategy6Indicators, Strategy6Start


PASSING_START_TYPES = {"NORMAL_STRONG_BREAKOUT", "VOLUME_LIMIT_UP", "LOW_VOLUME_LIMIT_UP", "ONE_WORD_LIMIT_UP"}


def evaluate_strong_start(rows: list[dict], ind: Strategy6Indicators, config: dict, code: str) -> Strategy6Start:
    best = Strategy6Start(limit_up_pct=get_limit_up_pct(code))
    start_idx = max(1, len(rows) - 20)
    for idx in range(start_idx, len(rows)):
        prev = rows[idx - 1]
        row = rows[idx]
        v20 = _avg_prior_volume(rows, idx, 20)
        day_return = _return_between(prev["close"], row["close"])
        volume_ratio = row["volume"] / v20 if v20 > 0 else 0.0
        close_position = _close_position(row)
        amount_yi = row["amount"] / 100_000_000
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
            start_low=row["low"],
            is_limit_up=limit_up,
            is_one_word_limit_up=one_word,
            limit_up_pct=get_limit_up_pct(code),
            days_since_start=len(rows) - idx - 1,
        )
        candidate.start_grade = _grade(candidate, ind)
        if _rank(candidate) > _rank(best):
            best = candidate
    best.high_trigger = _high_trigger(ind, config)
    if best.start_type == "NONE":
        best.start_grade = _grade(best, ind)
        if best.start_grade == "B":
            best.start_type = "B_GRADE_MOMENTUM"
    return best


def _grade(start: Strategy6Start, ind: Strategy6Indicators) -> str:
    if (
        ind.return_20 >= 0.40
        or ind.return_10 >= 0.25
        or ind.return_5 >= 0.15
        or start.start_type in {"VOLUME_LIMIT_UP", "ONE_WORD_LIMIT_UP"}
        or (start.start_day_return >= 0.09 and start.start_day_volume_ratio >= 2.5)
    ):
        return "S"
    if (
        ind.return_20 >= 0.30
        or ind.return_10 >= 0.20
        or ind.return_5 >= 0.12
        or start.start_type in {"NORMAL_STRONG_BREAKOUT", "LOW_VOLUME_LIMIT_UP"}
    ):
        return "A"
    if ind.return_20 >= 0.20 or ind.return_10 >= 0.12 or ind.return_5 >= 0.08:
        return "B"
    return "NONE"


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

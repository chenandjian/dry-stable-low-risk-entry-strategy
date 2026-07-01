"""Strategy4 leader scoring."""
from __future__ import annotations

from strategy4.models import LeaderScore

LOCKED_LIMIT_SHAPES = {"ONE_WORD_LIMIT_UP", "T_LIMIT_UP", "LIMIT_UP_CLOSE"}


def score_leader_candidate(snapshot: dict) -> LeaderScore:
    rank_score = max(0.0, 25.0 - (int(snapshot.get("rank_in_topic") or 99) - 1) * 6)
    amount_score = max(0.0, 20.0 - (int(snapshot.get("amount_rank") or 99) - 1) * 4)
    early_score = 15.0 if snapshot.get("started_early") else 0.0
    limit_shape = str(snapshot.get("limit_shape") or "")
    consecutive = int(snapshot.get("consecutive_limit_count") or 0)
    limit_score = 0.0
    if limit_shape in LOCKED_LIMIT_SHAPES:
        limit_score += 12.0
    limit_score += min(8.0, consecutive * 4.0)
    rs_score = min(10.0, max(0.0, float(snapshot.get("relative_strength_vs_topic") or 0) / 0.10 * 10))
    recognition = min(10.0, len(snapshot.get("recognition_sources") or []) * 5.0)
    strength = min(100.0, rank_score + amount_score + early_score + limit_score + rs_score + recognition)

    tradability = 0.0
    if limit_shape != "ONE_WORD_LIMIT_UP":
        tradability += 30.0
    turnover = float(snapshot.get("turnover_rate") or 0)
    if 0.02 <= turnover <= 0.18:
        tradability += 20.0
    if not snapshot.get("is_climax"):
        tradability += 20.0
    if snapshot.get("has_pullback_buy_point"):
        tradability += 20.0
    if snapshot.get("executable_volatility"):
        tradability += 10.0

    reasons: list[str] = []
    status = "HOT_TOPIC_NO_BUY_POINT"
    min_strength = float(snapshot.get("min_leader_strength_score") or 88)
    if limit_shape == "ONE_WORD_LIMIT_UP" or (consecutive >= 2 and limit_shape in LOCKED_LIMIT_SHAPES):
        status = "LOCKED_LEADER_WATCH"
        reasons.append("LOCKED_ATTENTION")
    elif strength >= min_strength and tradability >= 70:
        status = "LEADER_CONFIRMED"

    leader_type = "SPACE_LEADER" if int(snapshot.get("rank_in_topic") or 99) == 1 else "VOLUME_LEADER"
    return LeaderScore(
        code=str(snapshot.get("code") or ""),
        name=str(snapshot.get("name") or ""),
        topic_id=str(snapshot.get("topic_id") or ""),
        topic_name=str(snapshot.get("topic_name") or ""),
        leader_type=leader_type,
        leader_strength_score=round(strength, 2),
        tradability_score=round(tradability, 2),
        status=status,
        reasons=reasons,
    )

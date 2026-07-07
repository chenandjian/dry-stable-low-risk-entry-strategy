"""Derive Strategy4 leader snapshots from topic members and stock K-lines."""
from __future__ import annotations

import scanner.db as db
from strategy4.config import resolve_strategy4_config

DERIVED_SOURCE = "historical_kline_derived"


def derive_leaders_for_topic(topic: dict, *, evaluation_date: str, config: dict | None = None) -> list[dict]:
    """Rank topic members as leaders using only OHLC rows <= evaluation_date."""
    cfg = resolve_strategy4_config(config or {})
    derived_cfg = cfg.get("derived_source") or {}
    members = db.get_strategy4_topic_members(str(topic.get("topic_id") or ""), evaluation_date=evaluation_date)
    if len(members) < int(derived_cfg.get("min_member_count", 1)):
        return []

    topic_context = _topic_context(topic)
    scored: list[dict] = []
    for member in members:
        code = str(member.get("code") or "")
        rows = [r for r in (db.get_ohlc(code) or []) if str(r.get("date") or "") <= evaluation_date[:10]]
        if len(rows) < 10:
            continue
        metrics = _metrics(rows, topic_context)
        scored.append({
            "topic_id": topic.get("topic_id", ""),
            "topic_name": topic.get("topic_name", ""),
            "code": code,
            "name": member.get("name", ""),
            "source": DERIVED_SOURCE,
            "snapshot_source": DERIVED_SOURCE,
            "source_modes": [DERIVED_SOURCE],
            "membership_source": member.get("source", ""),
            "membership_mode": member.get("membership_mode", "current_members_proxy"),
            "return_1d": metrics["return_1d"],
            "return_5d": metrics["return_5d"],
            "return_10d": metrics["return_10d"],
            "return_20d": metrics["return_20d"],
            "amount_1d": metrics["amount_1d"],
            "amount": metrics["amount_1d"],
            "avg_amount_5d": metrics["avg_amount_5d"],
            "avg_amount_10d": metrics["avg_amount_10d"],
            "relative_strength_vs_topic": max(0.0, metrics["leader_rs_10d"], metrics["leader_rs_20d"]),
            "raw_snapshot": {
                **metrics,
                "membership_mode": member.get("membership_mode", "current_members_proxy"),
                "source_modes": [DERIVED_SOURCE],
            },
        })

    scored.sort(key=lambda item: (float(item["relative_strength_vs_topic"]), float(item["return_20d"]), float(item["amount_1d"])), reverse=True)
    max_leaders = int(derived_cfg.get("max_leaders_per_topic", 5))
    for rank, item in enumerate(scored, start=1):
        item["return_rank_in_topic"] = rank
        item["amount_rank_in_topic"] = _amount_rank(item, scored)
        item["leader_strength_score"] = _leader_score(item, rank)
        item["derived_leader_score"] = item["leader_strength_score"]
        item["tradability_score"] = 80.0
        item["leader_type"] = "SPACE_LEADER" if rank == 1 else "VOLUME_LEADER"
        item["status"] = "LEADER_CONFIRMED" if item["leader_strength_score"] >= 60 else "HOT_TOPIC_NO_BUY_POINT"
        item["raw_snapshot"]["return_rank_in_topic"] = rank
        item["raw_snapshot"]["amount_rank_in_topic"] = item["amount_rank_in_topic"]
    return scored[:max_leaders]


def _topic_context(topic: dict) -> dict:
    raw = topic.get("raw_snapshot") or {}
    context = raw.get("topic_index_context") if isinstance(raw, dict) else {}
    return context if isinstance(context, dict) else {}


def _metrics(rows: list[dict], topic_context: dict) -> dict:
    ret1 = _return_over(rows, 1)
    ret5 = _return_over(rows, 5)
    ret10 = _return_over(rows, 10)
    ret20 = _return_over(rows, 20)
    amount_1d = _amount(rows[-1])
    latest_date = str(rows[-1].get("date") or "")
    return {
        "latest_date": latest_date,
        "return_1d": ret1,
        "return_5d": ret5,
        "return_10d": ret10,
        "return_20d": ret20,
        "amount_1d": amount_1d,
        "avg_amount_5d": _avg_amount(rows, 5),
        "avg_amount_10d": _avg_amount(rows, 10),
        "leader_rs_5d": round(ret5 - float(topic_context.get("topic_return_5d") or 0), 4),
        "leader_rs_10d": round(ret10 - float(topic_context.get("topic_return_10d") or 0), 4),
        "leader_rs_20d": round(ret20 - float(topic_context.get("topic_return_20d") or 0), 4),
    }


def _leader_score(item: dict, rank: int) -> float:
    rank_score = max(0.0, 30.0 - (rank - 1) * 8.0)
    rs_score = min(30.0, max(0.0, float(item.get("relative_strength_vs_topic") or 0) / 0.15 * 30.0))
    return_score = min(25.0, max(float(item.get("return_10d") or 0) / 0.20, float(item.get("return_20d") or 0) / 0.35, 0.0) * 25.0)
    amount_score = 15.0 if float(item.get("amount_1d") or 0) > 0 else 0.0
    return round(min(100.0, rank_score + rs_score + return_score + amount_score), 2)


def _amount_rank(item: dict, items: list[dict]) -> int:
    ordered = sorted(items, key=lambda i: float(i.get("amount_1d") or 0), reverse=True)
    for idx, candidate in enumerate(ordered, start=1):
        if candidate.get("code") == item.get("code"):
            return idx
    return len(items)


def _return_over(rows: list[dict], days: int) -> float:
    if len(rows) <= days:
        return 0.0
    prev = float(rows[-days - 1].get("close") or 0)
    close = float(rows[-1].get("close") or 0)
    return round(close / prev - 1.0, 4) if prev > 0 else 0.0


def _amount(row: dict) -> float:
    return float(row.get("turnover") or row.get("amount") or 0)


def _avg_amount(rows: list[dict], days: int) -> float:
    selected = rows[-days:]
    return round(sum(_amount(r) for r in selected) / len(selected), 2) if selected else 0.0

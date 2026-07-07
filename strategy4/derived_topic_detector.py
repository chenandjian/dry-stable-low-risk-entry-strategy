"""Derive Strategy4 hot-topic snapshots from historical topic index K-lines."""
from __future__ import annotations

import scanner.db as db
from strategy4.config import resolve_strategy4_config
from strategy4.topic_index_analyzer import analyze_topic_index

DERIVED_SOURCE = "historical_kline_derived"


def derive_hot_topics_for_date(evaluation_date: str, config: dict | None = None) -> list[dict]:
    """Build derived hot-topic snapshots using only topic index rows <= evaluation_date."""
    cfg = resolve_strategy4_config(config or {})
    derived_cfg = cfg.get("derived_source") or {}
    if not derived_cfg.get("enabled", True):
        return []

    max_topics = int(derived_cfg.get("max_topics_per_day", 30))
    top_n = int(derived_cfg.get("topic_top_n", 20))
    min_rows = int(derived_cfg.get("min_topic_index_rows") or (cfg.get("topic_index") or {}).get("min_required_rows", 60))
    history_days = int((cfg.get("topic_index") or {}).get("history_days", 250))
    min_watch_score = float(derived_cfg.get("min_topic_hot_score", 60))
    min_confirm_score = float(derived_cfg.get("min_confirmed_topic_hot_score", 75))

    topics: list[dict] = []
    for meta in db.get_strategy4_topic_index_topics(end_date=evaluation_date)[:max_topics]:
        topic_id = str(meta.get("topic_id") or "")
        rows = db.get_strategy4_topic_index_ohlc(topic_id, end_date=evaluation_date, max_rows=history_days)
        context = analyze_topic_index(rows, min_required_rows=min_rows)
        if not context.get("observed"):
            continue
        breadth = _breadth_snapshot(topic_id, evaluation_date)
        score = _derived_hot_score(context, breadth)
        if score < min_watch_score:
            status = "NOISE_TOPIC"
        elif score >= min_confirm_score and context.get("phase") not in {"WEAK_NOISE", "HIGH_RISK_CLIMAX"}:
            status = "CONFIRMED_HOT"
        else:
            status = "WATCH_HOT"
        source_modes = [DERIVED_SOURCE]
        raw_snapshot = {
            "derived_hot_score": round(score, 2),
            "topic_index_context": context,
            "breadth_snapshot": breadth,
            "source_modes": source_modes,
            "membership_mode": breadth.get("membership_mode", ""),
        }
        topics.append({
            "topic_id": topic_id,
            "topic_name": meta.get("topic_name", ""),
            "topic_type": meta.get("topic_type", ""),
            "source": DERIVED_SOURCE,
            "snapshot_source": DERIVED_SOURCE,
            "source_modes": source_modes,
            "snapshot_time": f"{evaluation_date[:10]} 15:00:00",
            "status": status,
            "hot_topic_score": round(score, 2),
            "derived_hot_score": round(score, 2),
            "price_strength_score": round(float(context.get("topic_index_trend_score") or 0), 2),
            "amount_strength_score": round(float(context.get("topic_index_volume_score") or 0), 2),
            "fund_flow_score": 0.0,
            "breadth_score": round(breadth.get("breadth_score", 0.0), 2),
            "leader_limit_score": round(breadth.get("leader_limit_score", 0.0), 2),
            "breakout_score": round(float(context.get("topic_index_breakout_score") or 0), 2),
            "signal_count": _signal_count(context, breadth),
            "noise_reason": "" if status != "NOISE_TOPIC" else ",".join(context.get("topic_index_risk_flags") or ["derived_score_low"]),
            "leading_stock_code": breadth.get("leading_stock_code", ""),
            "leading_stock_name": breadth.get("leading_stock_name", ""),
            "topic_index_source": context.get("source", ""),
            "topic_index_latest_date": context.get("latest_date", ""),
            "topic_index_rows": int(context.get("rows") or 0),
            "topic_index_observed": True,
            "topic_index_status": context.get("status", ""),
            "topic_index_trend_score": round(float(context.get("topic_index_trend_score") or 0), 2),
            "topic_index_breakout_score": round(float(context.get("topic_index_breakout_score") or 0), 2),
            "topic_index_volume_score": round(float(context.get("topic_index_volume_score") or 0), 2),
            "topic_index_risk_penalty": round(float(context.get("topic_index_risk_penalty") or 0), 2),
            "topic_index_phase": context.get("phase", ""),
            "membership_mode": breadth.get("membership_mode", ""),
            "merge_confidence": "derived_only",
            "merge_warnings": breadth.get("warnings", []),
            "raw_snapshot": raw_snapshot,
        })
    topics.sort(key=lambda item: float(item.get("hot_topic_score") or 0), reverse=True)
    return topics[:top_n]


def _derived_hot_score(context: dict, breadth: dict) -> float:
    score = 0.0
    score += min(25.0, float(context.get("topic_index_trend_score") or 0) / 20.0 * 25.0)
    ret5 = float(context.get("topic_return_5d") or 0)
    ret10 = float(context.get("topic_return_10d") or 0)
    score += min(20.0, max(ret5 / 0.05, ret10 / 0.08, 0.0) * 20.0)
    score += min(20.0, float(context.get("topic_index_breakout_score") or 0) / 15.0 * 20.0)
    score += min(15.0, float(context.get("topic_index_volume_score") or 0) / 15.0 * 15.0)
    drawdown = abs(min(0.0, float(context.get("drawdown_from_high_20") or 0)))
    score += max(0.0, 10.0 - drawdown / 0.12 * 10.0)
    score += min(10.0, float(breadth.get("breadth_ratio") or 0) / 0.6 * 10.0)
    score += float(context.get("topic_index_risk_penalty") or 0)
    return max(0.0, min(100.0, score))


def _breadth_snapshot(topic_id: str, evaluation_date: str) -> dict:
    members = db.get_strategy4_topic_members(topic_id, evaluation_date=evaluation_date)
    if not members:
        return {
            "membership_mode": "unobserved_members",
            "warnings": ["UNOBSERVED_DERIVED_MEMBERS"],
            "breadth_ratio": 0.0,
            "breadth_score": 0.0,
            "leader_limit_score": 0.0,
        }
    up_count = 0
    observed = 0
    best = None
    best_ret = -999.0
    mode = members[0].get("membership_mode", "")
    for member in members:
        rows = [r for r in (db.get_ohlc(member.get("code", "")) or []) if str(r.get("date") or "") <= evaluation_date[:10]]
        if len(rows) < 2:
            continue
        observed += 1
        prev = float(rows[-2].get("close") or 0)
        close = float(rows[-1].get("close") or 0)
        ret = close / prev - 1.0 if prev > 0 else 0.0
        if ret > 0:
            up_count += 1
        if ret > best_ret:
            best_ret = ret
            best = member
    breadth_ratio = up_count / observed if observed else 0.0
    return {
        "membership_mode": mode or "current_members_proxy",
        "warnings": ["current_members_proxy"] if mode == "current_members_proxy" else [],
        "member_count": len(members),
        "observed_member_count": observed,
        "up_count": up_count,
        "breadth_ratio": round(breadth_ratio, 4),
        "breadth_score": min(10.0, breadth_ratio / 0.6 * 10.0),
        "leader_limit_score": 10.0 if best_ret >= 0.095 else 0.0,
        "leading_stock_code": best.get("code", "") if best else "",
        "leading_stock_name": best.get("name", "") if best else "",
    }


def _signal_count(context: dict, breadth: dict) -> int:
    count = 0
    if float(context.get("topic_return_5d") or 0) >= 0.05:
        count += 1
    if context.get("new_high_20"):
        count += 1
    if float(context.get("amount_ratio_5_20") or 0) >= 1.0:
        count += 1
    if float(breadth.get("breadth_ratio") or 0) >= 0.5:
        count += 1
    if context.get("phase") in {"EARLY_ACCELERATION", "MAIN_TREND"}:
        count += 1
    return count

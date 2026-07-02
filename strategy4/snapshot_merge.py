"""Merge Strategy4 live external and historical K-line derived snapshots."""
from __future__ import annotations

DERIVED_SOURCE = "historical_kline_derived"
LIVE_MODE = "live_external"


def merge_topics(live_topics: list[dict], derived_topics: list[dict], config: dict | None = None) -> list[dict]:
    policy = (config or {}).get("merge_policy") or {}
    merged: dict[str, dict] = {}
    for topic in live_topics or []:
        key = _topic_key(topic)
        item = dict(topic)
        item.setdefault("snapshot_source", LIVE_MODE)
        item["source_modes"] = _dedupe_modes(item.get("source_modes") or [LIVE_MODE])
        item["live_hot_score"] = float(item.get("hot_topic_score") or 0)
        item.setdefault("merge_confidence", "live_only")
        item.setdefault("merge_warnings", [])
        merged[key] = item
    for topic in derived_topics or []:
        key = _topic_key(topic)
        derived = dict(topic)
        derived["source_modes"] = _dedupe_modes(derived.get("source_modes") or [DERIVED_SOURCE])
        derived["derived_hot_score"] = float(derived.get("derived_hot_score") or derived.get("hot_topic_score") or 0)
        if key not in merged:
            derived.setdefault("snapshot_source", DERIVED_SOURCE)
            derived.setdefault("merge_confidence", "derived_only")
            derived.setdefault("merge_warnings", [])
            merged[key] = derived
            continue
        live = merged[key]
        warnings = list(live.get("merge_warnings") or [])
        derived_phase = str(derived.get("topic_index_phase") or "")
        derived_status = str(derived.get("status") or "")
        status = live.get("status", "")
        if policy.get("block_buyable_on_derived_weak_noise", True) and (derived_phase == "WEAK_NOISE" or derived_status == "NOISE_TOPIC"):
            warnings.append("derived_weak_noise")
            if status in {"CONFIRMED_HOT", "LOCKED_HOT_TOPIC"}:
                status = "WATCH_HOT"
        if policy.get("block_buyable_on_derived_high_risk_climax", True) and derived_phase == "HIGH_RISK_CLIMAX":
            warnings.append("derived_high_risk_climax")
            if status in {"CONFIRMED_HOT", "LOCKED_HOT_TOPIC"}:
                status = "WATCH_HOT"
        live["snapshot_source"] = "merged"
        live["source_modes"] = _dedupe_modes(list(live.get("source_modes") or []) + list(derived.get("source_modes") or []))
        live["live_hot_score"] = float(live.get("live_hot_score") or live.get("hot_topic_score") or 0)
        live["derived_hot_score"] = float(derived.get("derived_hot_score") or derived.get("hot_topic_score") or 0)
        live["hot_topic_score"] = max(float(live.get("hot_topic_score") or 0), float(derived.get("hot_topic_score") or 0))
        live["status"] = status
        live["merge_confidence"] = "high" if not warnings else "conflict"
        live["merge_warnings"] = _dedupe_modes(warnings)
        live["membership_mode"] = derived.get("membership_mode") or live.get("membership_mode", "")
        live["topic_index_phase"] = derived.get("topic_index_phase") or live.get("topic_index_phase", "")
        live["topic_index_latest_date"] = derived.get("topic_index_latest_date") or live.get("topic_index_latest_date", "")
        live["raw_snapshot"] = {
            **(live.get("raw_snapshot") or {}),
            "live_snapshot": live.get("raw_snapshot") or {},
            "derived_snapshot": derived,
            "source_modes": live["source_modes"],
            "merge_warnings": live["merge_warnings"],
        }
    items = list(merged.values())
    items.sort(key=lambda item: float(item.get("hot_topic_score") or 0), reverse=True)
    return items


def merge_leaders(live_leaders: list[dict], derived_leaders: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for leader in live_leaders or []:
        key = _leader_key(leader)
        item = dict(leader)
        item.setdefault("snapshot_source", LIVE_MODE)
        item["source_modes"] = _dedupe_modes(item.get("source_modes") or [LIVE_MODE])
        item["live_leader_score"] = float(item.get("leader_strength_score") or 0)
        item.setdefault("merge_warnings", [])
        merged[key] = item
    for leader in derived_leaders or []:
        key = _leader_key(leader)
        derived = dict(leader)
        derived["source_modes"] = _dedupe_modes(derived.get("source_modes") or [DERIVED_SOURCE])
        derived["derived_leader_score"] = float(derived.get("derived_leader_score") or derived.get("leader_strength_score") or 0)
        if key not in merged:
            derived.setdefault("snapshot_source", DERIVED_SOURCE)
            derived.setdefault("merge_confidence", "derived_only")
            derived.setdefault("merge_warnings", [])
            merged[key] = derived
            continue
        live = merged[key]
        live["snapshot_source"] = "merged"
        live["source_modes"] = _dedupe_modes(list(live.get("source_modes") or []) + list(derived.get("source_modes") or []))
        live["live_leader_score"] = float(live.get("live_leader_score") or live.get("leader_strength_score") or 0)
        live["derived_leader_score"] = derived["derived_leader_score"]
        live["leader_strength_score"] = max(float(live.get("leader_strength_score") or 0), float(derived.get("leader_strength_score") or 0))
        live["tradability_score"] = max(float(live.get("tradability_score") or 0), float(derived.get("tradability_score") or 0))
        live["membership_mode"] = derived.get("membership_mode") or live.get("membership_mode", "")
        live["merge_confidence"] = "high"
        live["raw_snapshot"] = {
            **(live.get("raw_snapshot") or {}),
            "derived_snapshot": derived,
            "source_modes": live["source_modes"],
        }
    items = list(merged.values())
    items.sort(key=lambda item: (float(item.get("leader_strength_score") or 0), float(item.get("tradability_score") or 0)), reverse=True)
    return items


def _topic_key(topic: dict) -> str:
    return f"{topic.get('topic_type', '')}:{str(topic.get('topic_name') or '').strip().lower()}"


def _leader_key(leader: dict) -> str:
    return f"{leader.get('topic_id', '')}:{leader.get('code', '')}"


def _dedupe_modes(values) -> list[str]:
    result: list[str] = []
    for value in values or []:
        if value and value not in result:
            result.append(value)
    return result

"""Strategy4 hot-topic lifecycle tracking rules."""
from __future__ import annotations

import datetime as dt
from typing import Any


TOPIC_ACTIVE_HOT = "ACTIVE_HOT"
TOPIC_COOLING_WATCH = "COOLING_WATCH"
TOPIC_SECOND_WAVE_WATCH = "SECOND_WAVE_WATCH"
TOPIC_RISK_REPAIR = "RISK_REPAIR"
TOPIC_INVALIDATED = "INVALIDATED"
TOPIC_EXPIRED = "EXPIRED"

LEADER_ACTIVE = "LEADER_ACTIVE"
LEADER_PULLBACK_TRACKING = "PULLBACK_TRACKING"
LEADER_SECOND_WAVE_READY = "SECOND_WAVE_READY"
LEADER_LOCKED_WATCH = "LOCKED_WATCH"
LEADER_INVALIDATED = "INVALIDATED"
LEADER_EXPIRED = "EXPIRED"

TRACKABLE_TOPIC_STATUSES = {"CONFIRMED_HOT", "LOCKED_HOT_TOPIC"}
TRACKABLE_LEADER_STATUSES = {"LEADER_CONFIRMED", "LOCKED_LEADER_WATCH", "HOT_TOPIC_NO_BUY_POINT"}
BUYABLE_TOPIC_TRACKING_STATUSES = {TOPIC_ACTIVE_HOT, TOPIC_COOLING_WATCH, TOPIC_SECOND_WAVE_WATCH}
BUYABLE_LEADER_TRACKING_STATUSES = {LEADER_PULLBACK_TRACKING, LEADER_SECOND_WAVE_READY}


def is_trackable_topic_snapshot(topic: dict, config: dict, existing: dict | None = None) -> bool:
    """Return whether an observable topic snapshot may create/update tracking state."""
    if existing:
        return True
    status = str(topic.get("status") or "")
    score = float(topic.get("hot_topic_score") or topic.get("derived_hot_score") or 0)
    return status in TRACKABLE_TOPIC_STATUSES and score >= float(config.get("min_hot_topic_score", 85))


def is_trackable_leader_snapshot(leader: dict, config: dict, existing: dict | None = None) -> bool:
    """Return whether an observable leader snapshot may create/update tracking state."""
    if existing:
        return True
    status = str(leader.get("status") or "")
    score = float(leader.get("leader_strength_score") or leader.get("derived_leader_score") or 0)
    return status in TRACKABLE_LEADER_STATUSES and score >= float(config.get("min_leader_strength_score", 88))


def tracking_phase_for_age(age_calendar_days: int, config: dict) -> str:
    tracking = config.get("tracking") or {}
    if age_calendar_days > int(tracking.get("max_calendar_days", 120)):
        return "expired"
    if age_calendar_days <= int(tracking.get("strong_attention_days", 20)):
        return "strong_attention"
    if age_calendar_days <= int(tracking.get("golden_second_wave_days", 60)):
        return "golden_second_wave"
    return "extension"


def build_topic_tracking_state(
    topic: dict,
    *,
    evaluation_date: str,
    config: dict,
    existing: dict | None = None,
    topic_index_context: dict | None = None,
    refresh_confirmation: bool = True,
) -> dict:
    """Build a persisted topic tracking state from one observable snapshot."""
    existing = existing or {}
    topic_index_context = topic_index_context or _topic_index_context(topic)
    first_date = existing.get("first_detected_date") or evaluation_date[:10]
    age = _calendar_age(first_date, evaluation_date)
    phase = tracking_phase_for_age(age, config)
    status = str(topic.get("status") or existing.get("source_status") or "")
    is_confirmed = status in TRACKABLE_TOPIC_STATUSES
    last_confirmed = (
        evaluation_date[:10]
        if is_confirmed and refresh_confirmation
        else existing.get("last_confirmed_date", first_date)
    )
    topic_phase = str(topic_index_context.get("phase") or topic.get("topic_index_phase") or existing.get("topic_index_phase") or "")
    risk_flags = _list(topic_index_context.get("topic_index_risk_flags") or topic.get("risk_flags") or topic.get("merge_warnings"))
    invalid_reason = ""
    tracking_status = _topic_status_for_phase(age, phase)

    if phase == "expired":
        tracking_status = TOPIC_EXPIRED
        invalid_reason = "TRACKING_EXPIRED"
    elif topic_phase == "WEAK_NOISE":
        tracking_status = TOPIC_INVALIDATED
        invalid_reason = "WEAK_NOISE"
    elif _has_breakdown_risk(risk_flags):
        tracking_status = TOPIC_INVALIDATED
        invalid_reason = ",".join(risk_flags)
    elif topic_phase == "HIGH_RISK_CLIMAX":
        tracking_status = TOPIC_RISK_REPAIR
        invalid_reason = "HIGH_RISK_CLIMAX"

    latest_score = float(topic.get("hot_topic_score") or topic.get("derived_hot_score") or existing.get("latest_hot_score") or 0)
    peak_score = max(float(existing.get("peak_hot_score") or 0), latest_score)
    source_modes = _dedupe(_list(existing.get("source_modes")) + _list(topic.get("source_modes")))
    return {
        "topic_id": str(topic.get("topic_id") or existing.get("topic_id") or ""),
        "topic_name": str(topic.get("topic_name") or existing.get("topic_name") or ""),
        "topic_type": str(topic.get("topic_type") or existing.get("topic_type") or ""),
        "first_detected_date": first_date,
        "last_confirmed_date": last_confirmed,
        "last_evaluated_date": evaluation_date[:10],
        "age_calendar_days": age,
        "tracking_status": tracking_status,
        "tracking_phase": phase,
        "source_status": status,
        "peak_hot_score": round(peak_score, 2),
        "latest_hot_score": round(latest_score, 2),
        "topic_index_phase": topic_phase,
        "topic_index_latest_date": str(topic_index_context.get("latest_date") or topic.get("topic_index_latest_date") or ""),
        "source_modes": source_modes,
        "membership_mode": str(topic.get("membership_mode") or existing.get("membership_mode") or ""),
        "invalid_reason": invalid_reason,
        "risk_flags": risk_flags,
        "raw_snapshot": {
            "topic": topic,
            "topic_index_context": topic_index_context,
        },
    }


def build_leader_tracking_state(
    leader: dict,
    *,
    evaluation_date: str,
    config: dict,
    topic_state: dict,
    existing: dict | None = None,
    evaluation: dict | None = None,
    refresh_confirmation: bool = True,
) -> dict:
    """Build a persisted leader tracking state tied to a tracked topic."""
    existing = existing or {}
    evaluation = evaluation or {}
    first_date = existing.get("first_detected_date") or evaluation_date[:10]
    age = int(topic_state.get("age_calendar_days") or _calendar_age(first_date, evaluation_date))
    phase = str(topic_state.get("tracking_phase") or tracking_phase_for_age(age, config))
    status = str(leader.get("status") or existing.get("source_status") or "")
    rr = evaluation.get("risk_reward")
    pullback = evaluation.get("pullback")
    reward_risk = _attr(rr, "reward_risk_ratio", existing.get("reward_risk_ratio", 0.0))
    risk_ratio = _attr(rr, "risk_ratio", existing.get("risk_ratio", 0.0))
    risk_flags = _list(existing.get("risk_flags"))
    invalid_reason = ""

    if topic_state.get("tracking_status") == TOPIC_EXPIRED or phase == "expired":
        tracking_status = LEADER_EXPIRED
        invalid_reason = "TOPIC_EXPIRED"
    elif topic_state.get("tracking_status") == TOPIC_INVALIDATED:
        tracking_status = LEADER_INVALIDATED
        invalid_reason = "TOPIC_INVALIDATED"
    elif evaluation.get("passed"):
        tracking_status = LEADER_SECOND_WAVE_READY
    elif status == "LOCKED_LEADER_WATCH":
        tracking_status = LEADER_LOCKED_WATCH
    elif status in TRACKABLE_LEADER_STATUSES:
        tracking_status = LEADER_PULLBACK_TRACKING
    else:
        tracking_status = existing.get("tracking_status") or LEADER_ACTIVE

    if phase == "extension" and tracking_status == LEADER_SECOND_WAVE_READY:
        tracking = config.get("tracking") or {}
        if float(reward_risk or 0) < float(tracking.get("extension_min_reward_risk_ratio", 2.0)):
            tracking_status = LEADER_INVALIDATED
            invalid_reason = "EXTENSION_REWARD_RISK_TOO_LOW"
            risk_flags.append(invalid_reason)
        if float(risk_ratio or 0) > float(tracking.get("extension_max_risk_ratio", 0.12)):
            tracking_status = LEADER_INVALIDATED
            invalid_reason = "EXTENSION_RISK_TOO_HIGH"
            risk_flags.append(invalid_reason)

    latest_score = float(leader.get("leader_strength_score") or leader.get("derived_leader_score") or existing.get("latest_leader_score") or 0)
    peak_score = max(float(existing.get("peak_leader_score") or 0), latest_score)
    last_confirmed = (
        evaluation_date[:10]
        if status in TRACKABLE_LEADER_STATUSES and refresh_confirmation
        else existing.get("last_confirmed_date", first_date)
    )
    return {
        "topic_id": str(leader.get("topic_id") or topic_state.get("topic_id") or existing.get("topic_id") or ""),
        "topic_name": str(leader.get("topic_name") or topic_state.get("topic_name") or existing.get("topic_name") or ""),
        "code": str(leader.get("code") or existing.get("code") or ""),
        "name": str(leader.get("name") or existing.get("name") or ""),
        "first_detected_date": first_date,
        "last_confirmed_date": last_confirmed,
        "last_evaluated_date": evaluation_date[:10],
        "tracking_status": tracking_status,
        "tracking_phase": phase,
        "source_status": status,
        "peak_leader_score": round(peak_score, 2),
        "latest_leader_score": round(latest_score, 2),
        "first_wave_high": float(existing.get("first_wave_high") or leader.get("first_wave_high") or 0),
        "first_wave_high_date": str(existing.get("first_wave_high_date") or leader.get("first_wave_high_date") or ""),
        "pullback_pct": float(_attr(pullback, "pullback_pct", leader.get("pullback_pct") or existing.get("pullback_pct") or 0)),
        "pullback_days": int(_attr(pullback, "pullback_days", leader.get("pullback_days") or existing.get("pullback_days") or 0)),
        "support_price": float(_attr(rr, "support_price", existing.get("support_price") or 0)),
        "stop_loss": float(_attr(rr, "stop_loss", existing.get("stop_loss") or 0)),
        "target_price": float(_attr(rr, "target_price", existing.get("target_price") or 0)),
        "risk_ratio": float(risk_ratio or 0),
        "reward_risk_ratio": float(reward_risk or 0),
        "candidate_origin": "tracking_pool",
        "topic_first_detected_date": str(topic_state.get("first_detected_date") or ""),
        "topic_last_confirmed_date": str(topic_state.get("last_confirmed_date") or ""),
        "leader_first_detected_date": first_date,
        "leader_last_confirmed_date": last_confirmed,
        "tracking_age_days": age,
        "membership_mode": str(leader.get("membership_mode") or topic_state.get("membership_mode") or existing.get("membership_mode") or ""),
        "invalid_reason": invalid_reason,
        "risk_flags": _dedupe(risk_flags),
        "raw_snapshot": {
            "leader": leader,
            "evaluation_status": evaluation.get("status", ""),
            "topic_tracking_status": topic_state.get("tracking_status", ""),
        },
    }


def can_generate_tracking_candidate(topic_state: dict, leader_state: dict) -> bool:
    return (
        topic_state.get("tracking_status") in BUYABLE_TOPIC_TRACKING_STATUSES
        and leader_state.get("tracking_status") in BUYABLE_LEADER_TRACKING_STATUSES
    )


def tracking_candidate_metadata(topic_state: dict, leader_state: dict, *, origin: str = "tracking_pool") -> dict:
    return {
        "candidate_origin": origin,
        "tracking_topic_status": topic_state.get("tracking_status", ""),
        "tracking_leader_status": leader_state.get("tracking_status", ""),
        "topic_first_detected_date": topic_state.get("first_detected_date", ""),
        "topic_last_confirmed_date": topic_state.get("last_confirmed_date", ""),
        "leader_first_detected_date": leader_state.get("first_detected_date", ""),
        "leader_last_confirmed_date": leader_state.get("last_confirmed_date", ""),
        "tracking_age_days": int(topic_state.get("age_calendar_days") or leader_state.get("tracking_age_days") or 0),
        "tracking_phase": topic_state.get("tracking_phase") or leader_state.get("tracking_phase") or "",
        "tracking_reasons": _tracking_reasons(topic_state, leader_state),
        "tracking_risk_flags": _dedupe(_list(topic_state.get("risk_flags")) + _list(leader_state.get("risk_flags"))),
        "invalid_conditions": _dedupe([
            v for v in [topic_state.get("invalid_reason"), leader_state.get("invalid_reason")] if v
        ]),
    }


def _topic_status_for_phase(age: int, phase: str) -> str:
    if phase == "expired":
        return TOPIC_EXPIRED
    if phase == "strong_attention":
        return TOPIC_ACTIVE_HOT
    if phase == "golden_second_wave":
        return TOPIC_SECOND_WAVE_WATCH
    return TOPIC_COOLING_WATCH if age <= 120 else TOPIC_EXPIRED


def _topic_index_context(topic: dict) -> dict:
    raw = topic.get("raw_snapshot") if isinstance(topic.get("raw_snapshot"), dict) else {}
    ctx = raw.get("topic_index_context") if isinstance(raw, dict) else {}
    return ctx if isinstance(ctx, dict) else {}


def _calendar_age(first_date: str, evaluation_date: str) -> int:
    try:
        first = dt.date.fromisoformat(str(first_date)[:10])
        current = dt.date.fromisoformat(str(evaluation_date)[:10])
    except ValueError:
        return 0
    return max(0, (current - first).days)


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _has_breakdown_risk(flags: list[str]) -> bool:
    markers = ("BREAKDOWN", "BELOW_MA60", "VOLUME_BREAKDOWN", "DRAWDOWN_TOO_DEEP")
    return any(any(marker in str(flag).upper() for marker in markers) for flag in flags)


def _tracking_reasons(topic_state: dict, leader_state: dict) -> list[str]:
    reasons = [str(topic_state.get("tracking_status") or ""), str(leader_state.get("tracking_status") or "")]
    if leader_state.get("reward_risk_ratio"):
        reasons.append("reward_risk_ok")
    return [r for r in _dedupe(reasons) if r]


def _list(value) -> list:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple) or isinstance(value, set):
        return list(value)
    return [value]


def _dedupe(values: list) -> list:
    result = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result

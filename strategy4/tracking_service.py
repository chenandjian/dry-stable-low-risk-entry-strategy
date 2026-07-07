"""Strategy4 lifecycle tracking pool service."""
from __future__ import annotations

import scanner.db as db
from strategy4.config import resolve_strategy4_config
from strategy4.engine import HotLeaderSecondWaveEngine
from strategy4.topic_index_filters import topic_index_context_passes_filters
from strategy4.topic_index_service import topic_index_context_from_history
from strategy4.tracking_rules import (
    BUYABLE_TOPIC_TRACKING_STATUSES,
    can_generate_tracking_candidate,
    build_leader_tracking_state,
    build_topic_tracking_state,
    is_trackable_leader_snapshot,
    is_trackable_topic_snapshot,
    tracking_candidate_metadata,
)


class Strategy4TrackingService:
    """Persist and evaluate Strategy4 hot-topic/leader lifecycle state."""

    def __init__(self, config: dict | None = None):
        self.project_config = config or {}
        self.config = resolve_strategy4_config(config or {})
        self.tracking_config = self.config.get("tracking") or {}

    @property
    def enabled(self) -> bool:
        return bool(self.tracking_config.get("enabled", True))

    def update_from_snapshots(
        self,
        task_id: str,
        evaluation_date: str,
        topics: list[dict],
        leaders: list[dict],
        candidates: list[dict] | None = None,
    ) -> tuple[list[dict], list[dict]]:
        """Update DB-backed tracking pool from current observable snapshots."""
        if not self.enabled:
            return [], []
        candidate_by_key = {
            (str(item.get("topic_id") or ""), str(item.get("code") or "")): item
            for item in (candidates or [])
        }
        topic_states: dict[str, dict] = {}
        for topic in topics:
            topic_id = str(topic.get("topic_id") or "")
            if not topic_id:
                continue
            existing = db.get_strategy4_tracked_topic(topic_id)
            if not is_trackable_topic_snapshot(topic, self.config, existing):
                continue
            state = build_topic_tracking_state(
                topic,
                evaluation_date=evaluation_date,
                config=self.config,
                existing=existing,
            )
            db.upsert_strategy4_tracked_topic(state)
            self._event(
                task_id=task_id,
                evaluation_date=evaluation_date,
                entity_type="topic",
                topic_id=topic_id,
                previous_status=(existing or {}).get("tracking_status", ""),
                new_status=state.get("tracking_status", ""),
                event_type="ENTER_POOL" if not existing else "REFRESH",
                reason=state.get("invalid_reason", "") or state.get("tracking_status", ""),
                metrics=state,
            )
            topic_states[topic_id] = state

        leader_states: list[dict] = []
        for leader in leaders:
            topic_id = str(leader.get("topic_id") or "")
            code = str(leader.get("code") or "")
            if not topic_id or not code:
                continue
            topic_state = topic_states.get(topic_id) or db.get_strategy4_tracked_topic(topic_id)
            if not topic_state:
                continue
            existing = db.get_strategy4_tracked_leader(topic_id, code)
            if not is_trackable_leader_snapshot(leader, self.config, existing):
                continue
            candidate = candidate_by_key.get((topic_id, code))
            state = build_leader_tracking_state(
                leader,
                evaluation_date=evaluation_date,
                config=self.config,
                topic_state=topic_state,
                existing=existing,
                evaluation=_evaluation_from_candidate(candidate) if candidate else None,
            )
            db.upsert_strategy4_tracked_leader(state)
            self._event(
                task_id=task_id,
                evaluation_date=evaluation_date,
                entity_type="leader",
                topic_id=topic_id,
                code=code,
                previous_status=(existing or {}).get("tracking_status", ""),
                new_status=state.get("tracking_status", ""),
                event_type="ENTER_POOL" if not existing else "REFRESH",
                reason=state.get("invalid_reason", "") or state.get("tracking_status", ""),
                metrics=state,
            )
            leader_states.append(state)
        return list(topic_states.values()), leader_states

    def build_candidates_from_pool(
        self,
        *,
        task_id: str,
        evaluation_date: str,
        project_config: dict | None = None,
    ) -> list[dict]:
        """Evaluate active tracked leaders using local OHLC only."""
        if not self.enabled:
            return []
        self._advance_pool_to(task_id=task_id, evaluation_date=evaluation_date)
        project_config = project_config or self.project_config
        engine = HotLeaderSecondWaveEngine({"strategy4": self.config})
        topic_index_cfg = self.config.get("topic_index") or {}
        min_rows = int(topic_index_cfg.get("min_required_rows", 60))
        max_rows = int(topic_index_cfg.get("history_days", 250))
        candidates: list[dict] = []
        topics = db.get_strategy4_tracked_topics(include_expired=False)
        for topic_state in topics:
            if topic_state.get("tracking_status") not in BUYABLE_TOPIC_TRACKING_STATUSES:
                continue
            topic_context = topic_index_context_from_history(
                topic_state,
                evaluation_date=evaluation_date,
                min_required_rows=min_rows,
                max_rows=max_rows,
            )
            if not topic_context.get("observed"):
                continue
            if not topic_index_context_passes_filters(topic_context, self.config):
                continue
            leaders = db.get_strategy4_tracked_leaders(topic_id=topic_state.get("topic_id"), include_expired=False)
            for leader_state in leaders:
                candidate = self._evaluate_tracked_leader(
                    task_id=task_id,
                    evaluation_date=evaluation_date,
                    topic_state=topic_state,
                    leader_state=leader_state,
                    topic_context=topic_context,
                    engine=engine,
                    project_config=project_config,
                )
                if candidate:
                    candidates.append(candidate)
        return candidates

    def _advance_pool_to(self, *, task_id: str, evaluation_date: str) -> None:
        """Advance persisted lifecycle state without pretending a new source confirmed it."""
        refreshed_topics: dict[str, dict] = {}
        for topic in db.get_strategy4_tracked_topics(include_expired=True):
            topic_id = str(topic.get("topic_id") or "")
            if not topic_id:
                continue
            refreshed = build_topic_tracking_state(
                {},
                evaluation_date=evaluation_date,
                config=self.config,
                existing=topic,
                refresh_confirmation=False,
            )
            db.upsert_strategy4_tracked_topic(refreshed)
            if refreshed.get("tracking_status") != topic.get("tracking_status"):
                self._event(
                    task_id=task_id,
                    evaluation_date=evaluation_date,
                    entity_type="topic",
                    topic_id=topic_id,
                    previous_status=topic.get("tracking_status", ""),
                    new_status=refreshed.get("tracking_status", ""),
                    event_type="EXPIRE" if refreshed.get("tracking_status") == "EXPIRED" else "STATUS_CHANGE",
                    reason=refreshed.get("invalid_reason", "") or refreshed.get("tracking_status", ""),
                    metrics=refreshed,
                )
            refreshed_topics[topic_id] = refreshed

        for leader in db.get_strategy4_tracked_leaders(include_expired=True):
            topic_id = str(leader.get("topic_id") or "")
            code = str(leader.get("code") or "")
            topic_state = refreshed_topics.get(topic_id) or db.get_strategy4_tracked_topic(topic_id)
            if not topic_state:
                continue
            refreshed = build_leader_tracking_state(
                {},
                evaluation_date=evaluation_date,
                config=self.config,
                topic_state=topic_state,
                existing=leader,
                refresh_confirmation=False,
            )
            db.upsert_strategy4_tracked_leader(refreshed)
            if refreshed.get("tracking_status") != leader.get("tracking_status"):
                self._event(
                    task_id=task_id,
                    evaluation_date=evaluation_date,
                    entity_type="leader",
                    topic_id=topic_id,
                    code=code,
                    previous_status=leader.get("tracking_status", ""),
                    new_status=refreshed.get("tracking_status", ""),
                    event_type="EXPIRE" if refreshed.get("tracking_status") == "EXPIRED" else "STATUS_CHANGE",
                    reason=refreshed.get("invalid_reason", "") or refreshed.get("tracking_status", ""),
                    metrics=refreshed,
                )

    def _evaluate_tracked_leader(
        self,
        *,
        task_id: str,
        evaluation_date: str,
        topic_state: dict,
        leader_state: dict,
        topic_context: dict,
        engine: HotLeaderSecondWaveEngine,
        project_config: dict,
    ) -> dict | None:
        code = str(leader_state.get("code") or "")
        history = [
            row for row in (db.get_ohlc(code) or [])
            if str(row.get("date") or "") <= evaluation_date[:10]
        ]
        if len(history) < 10:
            return None
        support = min(float(row["low"]) for row in history[-10:])
        target = max(float(row["high"]) for row in history[-60:])
        evaluation = engine.evaluate_at(
            history,
            code=code,
            name=str(leader_state.get("name") or ""),
            leader_context={
                "support_price": support,
                "target_price": target,
                "is_core_leader": str((leader_state.get("raw_snapshot") or {}).get("leader_type") or "") == "SPACE_LEADER",
            },
        )
        refreshed_leader = build_leader_tracking_state(
            leader_state,
            evaluation_date=evaluation_date,
            config=self.config,
            topic_state=topic_state,
            existing=leader_state,
            evaluation=evaluation,
        )
        db.upsert_strategy4_tracked_leader(refreshed_leader)
        self._event(
            task_id=task_id,
            evaluation_date=evaluation_date,
            entity_type="leader",
            topic_id=topic_state.get("topic_id", ""),
            code=code,
            previous_status=leader_state.get("tracking_status", ""),
            new_status=refreshed_leader.get("tracking_status", ""),
            event_type="CANDIDATE" if evaluation.get("passed") else "REFRESH",
            reason=refreshed_leader.get("invalid_reason", "") or refreshed_leader.get("tracking_status", ""),
            metrics=refreshed_leader,
        )
        if not evaluation.get("passed") or not can_generate_tracking_candidate(topic_state, refreshed_leader):
            return None

        first_wave = evaluation.get("first_wave")
        pullback = evaluation.get("pullback")
        second_wave = evaluation.get("second_wave")
        rr = evaluation.get("risk_reward")
        metadata = tracking_candidate_metadata(topic_state, refreshed_leader, origin="tracking_pool")
        snapshot = {
            "status": evaluation.get("status"),
            "snapshot_source": "tracking_pool",
            "source_modes": _dedupe(_list(topic_state.get("source_modes")) + _list(leader_state.get("source_modes"))),
            "membership_mode": topic_state.get("membership_mode") or leader_state.get("membership_mode", ""),
            "candidate_origin": "tracking_pool",
            "topic_index_context": topic_context,
            "topic_index_phase": topic_context.get("phase", ""),
            "topic_index_latest_date": topic_context.get("latest_date", ""),
            "tracking_reasons": metadata["tracking_reasons"],
            "tracking_risk_flags": metadata["tracking_risk_flags"],
        }
        return {
            "topic_id": topic_state.get("topic_id", ""),
            "topic_name": topic_state.get("topic_name", ""),
            "code": code,
            "name": leader_state.get("name", ""),
            "evaluation_date": history[-1].get("date", evaluation_date[:10]),
            "status": "BUYABLE_SECOND_WAVE",
            "strategy4_score": min(
                100.0,
                float(topic_state.get("latest_hot_score") or 0) * 0.4
                + float(leader_state.get("latest_leader_score") or 0) * 0.3
                + 30.0,
            ),
            "hot_topic_score": float(topic_state.get("latest_hot_score") or 0),
            "leader_strength_score": float(leader_state.get("latest_leader_score") or 0),
            "tradability_score": float((leader_state.get("raw_snapshot") or {}).get("tradability_score") or 80),
            "first_wave_score": 20 if first_wave and first_wave.passed else 0,
            "pullback_score": 20 if pullback and pullback.passed else 0,
            "second_wave_score": 20 if second_wave and second_wave.passed else 0,
            "reward_risk_score": 20 if rr and rr.passed else 0,
            "leader_type": (leader_state.get("raw_snapshot") or {}).get("leader_type", ""),
            "first_wave_return": first_wave.first_wave_return if first_wave else 0.0,
            "pullback_pct": pullback.pullback_pct if pullback else 0.0,
            "pullback_days": pullback.pullback_days if pullback else 0,
            "current_close": float(history[-1]["close"]),
            "support_price": rr.support_price if rr else 0.0,
            "stop_loss": rr.stop_loss if rr else 0.0,
            "target_price": rr.target_price if rr else 0.0,
            "risk_ratio": rr.risk_ratio if rr else 0.0,
            "reward_risk_ratio": rr.reward_risk_ratio if rr else 0.0,
            "entry_note": "跟踪池二波",
            "reject_reason": "",
            "snapshot_source": "tracking_pool",
            "source_modes": snapshot["source_modes"],
            "membership_mode": snapshot["membership_mode"],
            "evaluation_snapshot": snapshot,
            **metadata,
        }

    def _event(
        self,
        *,
        task_id: str,
        evaluation_date: str,
        entity_type: str,
        topic_id: str,
        previous_status: str,
        new_status: str,
        event_type: str,
        reason: str,
        metrics: dict,
        code: str = "",
    ) -> None:
        db.insert_strategy4_tracking_event({
            "evaluation_date": evaluation_date[:10],
            "task_id": task_id,
            "entity_type": entity_type,
            "topic_id": topic_id,
            "code": code,
            "previous_status": previous_status,
            "new_status": new_status,
            "event_type": event_type,
            "reason": reason,
            "metrics_snapshot": metrics,
        })


def merge_tracking_candidates(current: list[dict], tracking: list[dict]) -> list[dict]:
    """Merge current-hot and tracking-pool candidates preserving old fields."""
    by_key: dict[tuple[str, str], dict] = {}
    for item in current:
        key = (str(item.get("topic_id") or ""), str(item.get("code") or ""))
        by_key[key] = {"candidate_origin": "current_hot", **item}
    for item in tracking:
        key = (str(item.get("topic_id") or ""), str(item.get("code") or ""))
        if key in by_key:
            merged = {**item, **by_key[key]}
            merged.update({
                "candidate_origin": "merged_current_and_tracking",
                "tracking_topic_status": item.get("tracking_topic_status", ""),
                "tracking_leader_status": item.get("tracking_leader_status", ""),
                "topic_first_detected_date": item.get("topic_first_detected_date", ""),
                "topic_last_confirmed_date": item.get("topic_last_confirmed_date", ""),
                "leader_first_detected_date": item.get("leader_first_detected_date", ""),
                "leader_last_confirmed_date": item.get("leader_last_confirmed_date", ""),
                "tracking_age_days": item.get("tracking_age_days", 0),
                "tracking_phase": item.get("tracking_phase", ""),
                "tracking_reasons": item.get("tracking_reasons", []),
                "tracking_risk_flags": item.get("tracking_risk_flags", []),
                "invalid_conditions": item.get("invalid_conditions", []),
            })
            by_key[key] = merged
        else:
            by_key[key] = item
    return list(by_key.values())


def _evaluation_from_candidate(candidate: dict | None) -> dict:
    if not candidate:
        return {}
    return {
        "passed": candidate.get("status") == "BUYABLE_SECOND_WAVE",
        "status": candidate.get("status", ""),
        "risk_reward": {
            "support_price": candidate.get("support_price", 0.0),
            "stop_loss": candidate.get("stop_loss", 0.0),
            "target_price": candidate.get("target_price", 0.0),
            "risk_ratio": candidate.get("risk_ratio", 0.0),
            "reward_risk_ratio": candidate.get("reward_risk_ratio", 0.0),
        },
        "pullback": {
            "pullback_pct": candidate.get("pullback_pct", 0.0),
            "pullback_days": candidate.get("pullback_days", 0),
        },
    }


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

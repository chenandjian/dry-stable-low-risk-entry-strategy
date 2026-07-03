"""In-memory Strategy4 lifecycle tracking replay for backtests."""
from __future__ import annotations

from strategy4.tracking_rules import (
    BUYABLE_LEADER_TRACKING_STATUSES,
    BUYABLE_TOPIC_TRACKING_STATUSES,
    build_leader_tracking_state,
    build_topic_tracking_state,
    is_trackable_leader_snapshot,
    is_trackable_topic_snapshot,
    tracking_candidate_metadata,
)


class Strategy4TrackingReplayPool:
    """Replay tracking state by evaluation date without writing production DB."""

    def __init__(self, config: dict):
        self.config = config
        self.topics: dict[str, dict] = {}
        self.leaders: dict[tuple[str, str], dict] = {}

    def update_from_snapshots(self, evaluation_date: str, topics: list[dict], leaders: list[dict]) -> None:
        updated_topics: dict[str, dict] = {}
        for topic in topics:
            topic_id = str(topic.get("topic_id") or "")
            if not topic_id:
                continue
            existing = self.topics.get(topic_id)
            if not is_trackable_topic_snapshot(topic, self.config, existing):
                continue
            state = build_topic_tracking_state(
                topic,
                evaluation_date=evaluation_date,
                config=self.config,
                existing=existing,
            )
            self.topics[topic_id] = state
            updated_topics[topic_id] = state

        for leader in leaders:
            topic_id = str(leader.get("topic_id") or "")
            code = str(leader.get("code") or "")
            if not topic_id or not code:
                continue
            topic_state = updated_topics.get(topic_id) or self.topics.get(topic_id)
            if not topic_state:
                continue
            key = (topic_id, code)
            existing = self.leaders.get(key)
            if not is_trackable_leader_snapshot(leader, self.config, existing):
                continue
            state = build_leader_tracking_state(
                leader,
                evaluation_date=evaluation_date,
                config=self.config,
                topic_state=topic_state,
                existing=existing,
            )
            self.leaders[key] = state

    def advance_to(self, evaluation_date: str) -> None:
        """Refresh lifecycle age/status for all tracked entities on a replay date."""
        for topic_id, topic in list(self.topics.items()):
            self.topics[topic_id] = build_topic_tracking_state(
                {},
                evaluation_date=evaluation_date,
                config=self.config,
                existing=topic,
                refresh_confirmation=False,
            )
        for key, leader in list(self.leaders.items()):
            topic_state = self.topics.get(key[0])
            if not topic_state:
                continue
            self.leaders[key] = build_leader_tracking_state(
                {},
                evaluation_date=evaluation_date,
                config=self.config,
                topic_state=topic_state,
                existing=leader,
                refresh_confirmation=False,
            )

    def active_topics(self) -> list[dict]:
        return [
            topic for topic in self.topics.values()
            if topic.get("tracking_status") in BUYABLE_TOPIC_TRACKING_STATUSES
        ]

    def active_leaders_for_topic(self, topic_id: str) -> list[dict]:
        return [
            leader for (leader_topic_id, _), leader in self.leaders.items()
            if leader_topic_id == topic_id
            and leader.get("tracking_status") in BUYABLE_LEADER_TRACKING_STATUSES
        ]

    def metadata_for(self, topic: dict, leader: dict, *, origin: str = "tracking_pool") -> dict:
        return tracking_candidate_metadata(topic, leader, origin=origin)

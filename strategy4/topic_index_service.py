"""Strategy4 topic index cache/fetch/analyze service."""
from __future__ import annotations

from datetime import datetime, timedelta

import scanner.db as db
from strategy4.topic_index_analyzer import UNOBSERVED_TOPIC_INDEX, analyze_topic_index
from strategy4.topic_index_source import TopicIndexSourceError, fetch_topic_index_ohlc


class TopicIndexService:
    """Ensure Strategy4 topic index K-lines are observable and audited."""

    def __init__(self, config: dict):
        self.config = config or {}
        self.topic_index_config = self.config.get("topic_index") or {}

    def ensure_topic_index_context(self, topic: dict) -> dict:
        topic_id = _topic_id(topic)
        topic_name = str(topic.get("topic_name") or "")
        topic_type = str(topic.get("topic_type") or "concept")
        min_rows = int(self.topic_index_config.get("min_required_rows", 60))
        history_days = int(self.topic_index_config.get("history_days", 250))
        source_chain = list(self.topic_index_config.get("preferred_sources") or ["akshare_ths", "akshare_eastmoney"])
        if self.topic_index_config.get("enabled", True) is False:
            return _unobserved_context("TOPIC_INDEX_DISABLED", topic_id)

        target_date = _target_trade_date(datetime.now())
        cached = db.get_strategy4_topic_index_ohlc(topic_id, max_rows=history_days)
        if len(cached) >= min_rows and str(cached[-1].get("date") or "") >= target_date:
            ctx = analyze_topic_index(cached, min_required_rows=min_rows)
            return {**ctx, "source": cached[-1].get("source", ""), "topic_id": topic_id}

        end = datetime.now().date()
        start = end - timedelta(days=max(history_days * 2, 120))
        try:
            rows, meta = fetch_topic_index_ohlc(
                topic_name=topic_name,
                topic_type=topic_type,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                preferred_sources=source_chain,
            )
            db.save_strategy4_topic_index_ohlc(
                topic_id=topic_id,
                topic_name=topic_name,
                topic_type=topic_type,
                source=meta.get("source", ""),
                rows=rows,
                source_topic_code=meta.get("source_topic_code", ""),
                source_topic_name=meta.get("source_topic_name", topic_name),
            )
            db.save_strategy4_topic_index_fetch_status(
                topic_id=topic_id,
                topic_name=topic_name,
                topic_type=topic_type,
                source=meta.get("source", ""),
                source_topic_code=meta.get("source_topic_code", ""),
                source_topic_name=meta.get("source_topic_name", topic_name),
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                status="completed",
                latest_date=rows[-1]["date"] if rows else "",
                rows_count=len(rows),
            )
            if rows and str(rows[-1].get("date") or "") < target_date:
                return _unobserved_context("STALE_TOPIC_INDEX", topic_id, rows=rows)
            ctx = analyze_topic_index(rows, min_required_rows=min_rows)
            return {**ctx, "source": meta.get("source", ""), "topic_id": topic_id}
        except (TopicIndexSourceError, Exception) as exc:
            db.save_strategy4_topic_index_fetch_status(
                topic_id=topic_id,
                topic_name=topic_name,
                topic_type=topic_type,
                source=",".join(source_chain),
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                status="source_failed",
                error_code="SOURCE_FAILED",
                error_message=str(exc),
            )
            return _unobserved_context("UNOBSERVED_TOPIC_INDEX", topic_id, error=str(exc))


def topic_index_context_from_history(topic: dict, *, evaluation_date: str, min_required_rows: int = 60, max_rows: int = 250) -> dict:
    """Build topic index context for backtest using only rows <= evaluation_date."""
    topic_id = str(topic.get("topic_id") or "")
    rows = db.get_strategy4_topic_index_ohlc(topic_id, end_date=evaluation_date, max_rows=max_rows)
    if len(rows) < min_required_rows:
        return _unobserved_context("UNOBSERVED_TOPIC_INDEX", topic_id, rows=rows)
    ctx = analyze_topic_index(rows, min_required_rows=min_required_rows)
    return {**ctx, "source": rows[-1].get("source", ""), "topic_id": topic_id}


def _target_trade_date(now: datetime) -> str:
    current = now.date()
    if now.weekday() < 5 and (now.hour, now.minute) >= (15, 10):
        return current.isoformat()
    current -= timedelta(days=1)
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current.isoformat()


def _topic_id(topic: dict) -> str:
    return str(topic.get("topic_id") or f"{topic.get('topic_type', 'concept')}:{topic.get('topic_name', '')}")


def _unobserved_context(status: str, topic_id: str, *, rows: list[dict] | None = None, error: str = "") -> dict:
    rows = rows or []
    return {
        "topic_id": topic_id,
        "observed": False,
        "status": status,
        "latest_date": rows[-1].get("date", "") if rows else "",
        "rows": len(rows),
        "phase": UNOBSERVED_TOPIC_INDEX,
        "source": "",
        "topic_index_trend_score": 0.0,
        "topic_index_breakout_score": 0.0,
        "topic_index_volume_score": 0.0,
        "topic_index_risk_penalty": 0.0,
        "topic_index_risk_flags": [status] + ([error] if error else []),
    }

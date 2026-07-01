"""Strategy4 scan orchestration."""
from __future__ import annotations

import logging
import time

import scanner.db as db
from strategy4.config import resolve_strategy4_config
from strategy4.engine import HotLeaderSecondWaveEngine
from strategy4.leader import score_leader_candidate
from strategy4.price_limit import PriceLimitResolver
from strategy4.topic_scoring import score_hot_topic
from strategy4.topic_source import TopicSourceError, TopicSourceService

logger = logging.getLogger(__name__)

STRATEGY4_TYPE = "STRATEGY_4_HOT_LEADER_SECOND_WAVE"


def scan_strategy4_all(config: dict, progress_callback=None, task_id: str | None = None, **kwargs) -> dict:
    """Run Strategy4 scan.

    Phase 1 keeps external topic sources behind adapters. If no injected/mock
    topic source is supplied, this records an explicit data-source failure
    instead of silently returning fake hot topics.
    """
    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)
    cfg = resolve_strategy4_config(config)
    task_id = task_id or time.strftime("s4-%Y%m%d-%H%M%S")
    start = time.time()

    source = kwargs.get("topic_source")
    if source is None:
        topic_service = TopicSourceService()
        try:
            raw_topics = topic_service.fetch_topics()
        except TopicSourceError as exc:
            error = f"STRATEGY4_TOPIC_SOURCE_FAILED: {exc}"
            logger.warning(error)
            stats = {
                "total": 0,
                "total_stocks": 0,
                "processed": 0,
                "scanned": 0,
                "skipped": 0,
                "failed": 1,
                "candidates_found": 0,
                "elapsed_seconds": round(time.time() - start, 1),
                "error": error,
            }
            return {"topics": [], "leaders": [], "candidates": [], "stats": stats, "task_id": task_id, "config": cfg}
        scored = [score_hot_topic(t, cfg) for t in raw_topics]
        topics = [_topic_to_dict(t) for t in sorted(scored, key=lambda t: t.hot_topic_score, reverse=True)[: cfg["watch_hot_topic_top_n"]]]
        db.replace_strategy4_hot_topics(task_id, topics)
        leaders, candidates = _build_leaders_and_candidates_from_topics(topics, config, cfg, topic_service=topic_service)
        db.replace_strategy4_leaders(task_id, leaders)
        for candidate in candidates:
            db.upsert_strategy4_candidate(task_id, candidate)
        stats = {
            "total": len(leaders),
            "total_stocks": len(leaders),
            "processed": len(leaders),
            "scanned": len(leaders),
            "skipped": 0,
            "failed": 0,
            "candidates_found": len(candidates),
            "elapsed_seconds": round(time.time() - start, 1),
            "hot_topics_found": len(topics),
            "leaders_found": len(leaders),
        }
        return {"topics": topics, "leaders": leaders, "candidates": candidates, "stats": stats, "task_id": task_id}

    if source is False:
        error = "STRATEGY4_TOPIC_SOURCE_NOT_CONFIGURED"
        logger.warning(error)
        stats = {
            "total": 0,
            "total_stocks": 0,
            "processed": 0,
            "scanned": 0,
            "skipped": 0,
            "failed": 1,
            "candidates_found": 0,
            "elapsed_seconds": round(time.time() - start, 1),
            "error": error,
        }
        return {"topics": [], "leaders": [], "candidates": [], "stats": stats, "task_id": task_id, "config": cfg}

    result = source(config=config, task_id=task_id)
    topics = result.get("topics", [])
    leaders = result.get("leaders", [])
    candidates = result.get("candidates", [])
    db.replace_strategy4_hot_topics(task_id, topics)
    db.replace_strategy4_leaders(task_id, leaders)
    for candidate in candidates:
        db.upsert_strategy4_candidate(task_id, candidate)
    stats = {
        "total": len(leaders),
        "total_stocks": len(leaders),
        "processed": len(leaders),
        "scanned": len(leaders),
        "skipped": 0,
        "failed": 0,
        "candidates_found": len(candidates),
        "elapsed_seconds": round(time.time() - start, 1),
        "hot_topics_found": len(topics),
        "leaders_found": len(leaders),
    }
    if progress_callback:
        progress_callback("completed", stats["processed"], stats["total_stocks"], "策略4扫描完成")
    return {"topics": topics, "leaders": leaders, "candidates": candidates, "stats": stats, "task_id": task_id}


def _topic_to_dict(topic) -> dict:
    return {
        "topic_id": topic.topic_id,
        "topic_name": topic.topic_name,
        "topic_type": topic.topic_type,
        "source": topic.source,
        "snapshot_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": topic.status,
        "hot_topic_score": topic.hot_topic_score,
        "price_strength_score": topic.price_strength_score,
        "amount_strength_score": topic.amount_strength_score,
        "fund_flow_score": topic.fund_flow_score,
        "breadth_score": topic.breadth_score,
        "leader_limit_score": topic.leader_limit_score,
        "breakout_score": topic.breakout_score,
        "signal_count": topic.signal_count,
        "noise_reason": topic.noise_reason,
        "leading_stock_code": topic.leading_stock_code,
        "leading_stock_name": topic.leading_stock_name,
        "raw_snapshot": topic.raw_snapshot,
    }


def _build_leaders_and_candidates_from_topics(
    topics: list[dict],
    project_config: dict,
    strategy_config: dict,
    *,
    topic_service: TopicSourceService | None = None,
) -> tuple[list[dict], list[dict]]:
    resolver = PriceLimitResolver()
    engine = HotLeaderSecondWaveEngine({"strategy4": strategy_config})
    leaders: list[dict] = []
    candidates: list[dict] = []

    for topic in topics:
        leader_inputs = _leader_inputs_for_topic(topic, strategy_config, topic_service)
        for rank, leader_input in enumerate(leader_inputs, start=1):
            code = leader_input["code"]
            name = leader_input["name"]
            info = resolver.resolve(code, name)
            limit_shape = leader_input.get("limit_shape", "")
            leader_score = score_leader_candidate({
                "code": code,
                "name": name,
                "topic_id": topic.get("topic_id"),
                "topic_name": topic.get("topic_name"),
                "rank_in_topic": rank,
                "amount_rank": rank,
                "started_early": True,
                "limit_shape": limit_shape,
                "consecutive_limit_count": int((topic.get("raw_snapshot") or {}).get("leader_limit_count") or 0),
                "relative_strength_vs_topic": max(0.0, float(leader_input.get("return_1d") or 0) - float(topic.get("raw_snapshot", {}).get("return_1d") or 0)),
                "recognition_sources": leader_input.get("recognition_sources") or ["topic_member"],
                "turnover_rate": 0.05,
                "is_climax": False,
                "has_pullback_buy_point": False,
                "executable_volatility": True,
            })
            leader = {
                "topic_id": topic.get("topic_id", ""),
                "topic_name": topic.get("topic_name", ""),
                "code": code,
                "name": name,
                "leader_type": leader_score.leader_type,
                "leader_strength_score": leader_score.leader_strength_score,
                "tradability_score": leader_score.tradability_score,
                "price_limit_rule": info.rule,
                "limit_shape": limit_shape,
                "limit_pct": info.limit_pct,
                "return_1d": leader_input.get("return_1d", 0.0),
                "amount_1d": leader_input.get("amount", 0.0),
                "consecutive_limit_count": 0,
                "relative_strength_vs_topic": 0.0,
                "membership_source": leader_input.get("membership_source", ""),
                "status": leader_score.status,
                "raw_snapshot": leader_input,
            }
            leaders.append(leader)

            data = db.get_ohlc(code)
            if not data:
                continue
            evaluation = engine.evaluate_at(
                data,
                code=code,
                name=name,
                leader_context={"support_price": min(float(r["low"]) for r in data[-10:]), "target_price": max(float(r["high"]) for r in data[-60:]) if len(data) >= 60 else max(float(r["high"]) for r in data)},
            )
            rr = evaluation.get("risk_reward")
            pullback = evaluation.get("pullback")
            first_wave = evaluation.get("first_wave")
            if evaluation.get("passed") and rr and pullback and first_wave:
                candidates.append({
                    "topic_id": topic.get("topic_id", ""),
                    "topic_name": topic.get("topic_name", ""),
                    "code": code,
                    "name": name,
                    "evaluation_date": data[-1].get("date", ""),
                    "status": "BUYABLE_SECOND_WAVE",
                    "strategy4_score": min(100, topic.get("hot_topic_score", 0) * 0.4 + leader_score.leader_strength_score * 0.3 + 30),
                    "hot_topic_score": topic.get("hot_topic_score", 0),
                    "leader_strength_score": leader_score.leader_strength_score,
                    "tradability_score": leader_score.tradability_score,
                    "first_wave_score": 20,
                    "pullback_score": 20,
                    "second_wave_score": 20,
                    "reward_risk_score": 20,
                    "leader_type": leader_score.leader_type,
                    "price_limit_rule": info.rule,
                    "limit_shape": limit_shape,
                    "first_wave_return": first_wave.first_wave_return,
                    "pullback_pct": pullback.pullback_pct,
                    "pullback_days": pullback.pullback_days,
                    "current_close": float(data[-1]["close"]),
                    "support_price": rr.support_price,
                    "stop_loss": rr.stop_loss,
                    "target_price": rr.target_price,
                    "risk_ratio": rr.risk_ratio,
                    "reward_risk_ratio": rr.reward_risk_ratio,
                    "entry_note": "热点龙头二波",
                    "reject_reason": "",
                    "evaluation_snapshot": {"status": evaluation.get("status")},
                })
    return leaders, candidates


def _leader_inputs_for_topic(topic: dict, strategy_config: dict, topic_service: TopicSourceService | None) -> list[dict]:
    inputs: list[dict] = []
    if topic_service is not None:
        try:
            inputs.extend(topic_service.fetch_topic_members(topic.get("topic_name", ""), topic.get("topic_type", "")))
        except TopicSourceError:
            pass

    code = str(topic.get("leading_stock_code") or "")
    if not code:
        raw = topic.get("raw_snapshot") or {}
        code = str(raw.get("leading_stock_code") or "")
    if not code:
        code = _resolve_code_by_name(str(topic.get("leading_stock_name") or ""))
    if code:
        inputs.append({
            "code": code,
            "name": str(topic.get("leading_stock_name") or code),
            "return_1d": 0.0,
            "amount": 0.0,
            "membership_source": "akshare_ths_leading_stock",
            "recognition_sources": ["topic_leader"],
        })

    deduped = {}
    for item in inputs:
        if item.get("code"):
            item.setdefault("membership_source", "akshare_ths_member")
            deduped[item["code"]] = item
    sorted_items = sorted(
        deduped.values(),
        key=lambda item: (float(item.get("return_1d") or 0), float(item.get("amount") or 0)),
        reverse=True,
    )
    return sorted_items[: int(strategy_config.get("max_total_leaders_per_topic", 3))]


def _resolve_code_by_name(name: str) -> str:
    if not name:
        return ""
    try:
        for stock in db.get_stock_pool():
            if stock.get("name") == name:
                return str(stock.get("code") or "")
    except Exception:
        return ""
    return ""

"""Strategy4 scan orchestration."""
from __future__ import annotations

import logging
import time
from datetime import datetime

import scanner.db as db
from scanner.daily_data_service import (
    DEFAULT_DAILY_SOURCES,
    FetchResult,
    build_cache_freshness_context,
    encode_source_errors,
    fetch_with_retry,
)
from scanner.data_source import DataSourceManager
from strategy4.config import resolve_strategy4_config
from strategy4.engine import HotLeaderSecondWaveEngine
from strategy4.leader import score_leader_candidate
from strategy4.price_limit import PriceLimitResolver
from strategy4.topic_scoring import score_hot_topic
from strategy4.topic_source import TopicSourceError, TopicSourceService

logger = logging.getLogger(__name__)

STRATEGY4_TYPE = "STRATEGY_4_HOT_LEADER_SECOND_WAVE"
BUYABLE_TOPIC_STATUSES = {"CONFIRMED_HOT", "LOCKED_HOT_TOPIC"}
LEADER_TOPIC_STATUSES = BUYABLE_TOPIC_STATUSES | {"WATCH_HOT"}


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
        leaders, candidates, scan_stats = _build_leaders_and_candidates_from_topics(
            topics,
            config,
            cfg,
            task_id=task_id,
            progress_callback=progress_callback,
            topic_service=topic_service,
            fetch_daily_fn=kwargs.get("fetch_daily_fn"),
            force_refresh_daily=bool(kwargs.get("force_refresh_daily", False)),
        )
        db.replace_strategy4_leaders(task_id, leaders)
        for candidate in candidates:
            db.upsert_strategy4_candidate(task_id, candidate)
        stats = {
            **scan_stats,
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
    task_id: str,
    progress_callback=None,
    topic_service: TopicSourceService | None = None,
    fetch_daily_fn=None,
    force_refresh_daily: bool = False,
) -> tuple[list[dict], list[dict], dict]:
    resolver = PriceLimitResolver()
    engine = HotLeaderSecondWaveEngine({"strategy4": strategy_config})
    daily_sources = project_config.get("data", {}).get("daily_sources") or DEFAULT_DAILY_SOURCES
    kline_days = int(
        project_config.get("liquidity", {}).get("min_listing_days")
        or project_config.get("data", {}).get("scan_window_days")
        or 250
    )
    mgr = DataSourceManager()
    leaders: list[dict] = []
    candidates: list[dict] = []
    work_items: list[dict] = []
    stocks_by_code: dict[str, dict] = {}

    for topic in topics:
        if topic.get("status") not in LEADER_TOPIC_STATUSES:
            continue
        leader_inputs = _leader_inputs_for_topic(topic, strategy_config, topic_service)
        for rank, leader_input in enumerate(leader_inputs, start=1):
            code = leader_input["code"]
            name = leader_input["name"]
            if not code:
                continue
            stocks_by_code.setdefault(code, {"code": code, "name": name, "market": _infer_market(code)})
            work_items.append({"topic": topic, "leader_input": leader_input, "rank": rank})

    task_stocks = list(stocks_by_code.values())
    db.save_task_stocks(task_id, task_stocks)
    stats = {
        "total": len(task_stocks),
        "total_stocks": len(task_stocks),
        "processed": 0,
        "scanned": 0,
        "skipped": 0,
        "failed": 0,
    }
    daily_by_code: dict[str, tuple[list[dict] | None, FetchResult | None]] = {}
    candidate_codes: set[str] = set()

    for item in work_items:
        topic = item["topic"]
        leader_input = item["leader_input"]
        rank = item["rank"]
        code = leader_input["code"]
        name = leader_input["name"]
        info = resolver.resolve(code, name)

        if code not in daily_by_code:
            db.update_task_stock(
                task_id,
                code,
                status="fetching",
                primary_source=daily_sources[0],
                fallback_source=daily_sources[-1],
                started_at=_now(),
            )
            data, fetch_result = _load_strategy4_daily_data(
                code,
                daily_sources=daily_sources,
                kline_days=kline_days,
                mgr=mgr,
                fetch_daily_fn=fetch_daily_fn,
                force_refresh_daily=force_refresh_daily,
            )
            daily_by_code[code] = (data, fetch_result)
            stats["processed"] += 1
            if not data:
                stats["failed"] += 1
                _mark_task_stock_failed(task_id, code, fetch_result)
                if progress_callback:
                    progress_callback("scanning", stats["processed"], stats["total_stocks"], f"{code} {name}")
            else:
                stats["scanned"] += 1
                _mark_task_stock_scanned(task_id, code, data, fetch_result)
                if progress_callback:
                    progress_callback("scanning", stats["processed"], stats["total_stocks"], f"{code} {name}")

        data, fetch_result = daily_by_code[code]
        if not data:
            leaders.append(_leader_snapshot_for_failed_daily(topic, leader_input, rank, info))
            continue

        limit_shape = _resolve_limit_shape(resolver, info, data, leader_input)
        evaluation = engine.evaluate_at(
            data,
            code=code,
            name=name,
            leader_context={
                "support_price": min(float(r["low"]) for r in data[-10:]),
                "target_price": max(float(r["high"]) for r in data[-60:]) if len(data) >= 60 else max(float(r["high"]) for r in data),
            },
        )
        rr = evaluation.get("risk_reward")
        pullback = evaluation.get("pullback")
        first_wave = evaluation.get("first_wave")
        second_wave = evaluation.get("second_wave")
        leader_score = _score_leader(topic, leader_input, rank, limit_shape, evaluation, strategy_config)
        leaders.append(_leader_snapshot(topic, leader_input, leader_score, info, limit_shape, data))

        if (
            topic.get("status") in BUYABLE_TOPIC_STATUSES
            and leader_score.status == "LEADER_CONFIRMED"
            and evaluation.get("passed")
            and rr
            and pullback
            and first_wave
        ):
            candidate = {
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
                "first_wave_score": 20 if first_wave.passed else 0,
                "pullback_score": 20 if pullback.passed else 0,
                "second_wave_score": 20 if second_wave and second_wave.passed else 0,
                "reward_risk_score": 20 if rr.passed else 0,
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
                "evaluation_snapshot": {
                    "status": evaluation.get("status"),
                    "first_wave_reasons": first_wave.reasons,
                    "pullback_reasons": pullback.reasons,
                    "second_wave_signals": second_wave.signals if second_wave else [],
                    "reward_risk_reject_reasons": rr.reject_reasons,
                },
            }
            candidates.append(candidate)
            candidate_codes.add(code)
            db.update_task_stock(
                task_id,
                code,
                status="candidate",
                kline_latest_date=data[-1].get("date"),
                finished_at=_now(),
            )
            if progress_callback:
                progress_callback("discovery", stats["processed"], stats["total_stocks"], f"{code} {name}", discovery=candidate)

    stats["candidates_found"] = len(candidates)
    for code, (data, _) in daily_by_code.items():
        if data and code not in candidate_codes:
            db.update_task_stock(task_id, code, status="scanned", finished_at=_now())
    return leaders, candidates, stats


def _score_leader(topic: dict, leader_input: dict, rank: int, limit_shape: str, evaluation: dict, strategy_config: dict):
    topic_return_1d = float((topic.get("raw_snapshot") or {}).get("return_1d") or 0)
    return score_leader_candidate({
        "code": leader_input.get("code", ""),
        "name": leader_input.get("name", ""),
        "topic_id": topic.get("topic_id"),
        "topic_name": topic.get("topic_name"),
        "rank_in_topic": rank,
        "amount_rank": rank,
        "started_early": True,
        "limit_shape": limit_shape,
        "consecutive_limit_count": int((topic.get("raw_snapshot") or {}).get("leader_limit_count") or 0),
        "relative_strength_vs_topic": max(0.0, float(leader_input.get("return_1d") or 0) - topic_return_1d),
        "recognition_sources": leader_input.get("recognition_sources") or ["topic_member"],
        "turnover_rate": float(leader_input.get("turnover_rate") or 0.05),
        "is_climax": bool(leader_input.get("is_climax", False)),
        "has_pullback_buy_point": bool(evaluation.get("passed")),
        "executable_volatility": True,
        "min_leader_strength_score": strategy_config.get("min_leader_strength_score", 88),
    })


def _leader_snapshot(topic: dict, leader_input: dict, leader_score, info, limit_shape: str, data: list[dict]) -> dict:
    return {
        "topic_id": topic.get("topic_id", ""),
        "topic_name": topic.get("topic_name", ""),
        "code": leader_input.get("code", ""),
        "name": leader_input.get("name", ""),
        "leader_type": leader_score.leader_type,
        "leader_strength_score": leader_score.leader_strength_score,
        "tradability_score": leader_score.tradability_score,
        "price_limit_rule": info.rule,
        "limit_shape": limit_shape,
        "limit_pct": info.limit_pct,
        "return_1d": _return_over(data, 1),
        "return_5d": _return_over(data, 5),
        "return_10d": _return_over(data, 10),
        "return_20d": _return_over(data, 20),
        "amount_1d": _amount(data[-1]),
        "avg_amount_5d": _avg_amount(data, 5),
        "avg_amount_10d": _avg_amount(data, 10),
        "first_wave_max_amount": max(_amount(r) for r in data[-20:]),
        "last_non_limit_amount": _last_non_limit_amount(data, limit_shape),
        "consecutive_limit_count": int((topic.get("raw_snapshot") or {}).get("leader_limit_count") or 0),
        "relative_strength_vs_topic": max(0.0, float(leader_input.get("return_1d") or 0) - float((topic.get("raw_snapshot") or {}).get("return_1d") or 0)),
        "membership_source": leader_input.get("membership_source", ""),
        "status": leader_score.status,
        "raw_snapshot": {**leader_input, "leader_reasons": leader_score.reasons},
    }


def _leader_snapshot_for_failed_daily(topic: dict, leader_input: dict, rank: int, info) -> dict:
    leader_score = score_leader_candidate({
        "code": leader_input.get("code", ""),
        "name": leader_input.get("name", ""),
        "topic_id": topic.get("topic_id"),
        "topic_name": topic.get("topic_name"),
        "rank_in_topic": rank,
        "amount_rank": rank,
        "started_early": True,
        "recognition_sources": leader_input.get("recognition_sources") or ["topic_member"],
        "min_leader_strength_score": 101,
    })
    return {
        "topic_id": topic.get("topic_id", ""),
        "topic_name": topic.get("topic_name", ""),
        "code": leader_input.get("code", ""),
        "name": leader_input.get("name", ""),
        "leader_type": leader_score.leader_type,
        "leader_strength_score": leader_score.leader_strength_score,
        "tradability_score": leader_score.tradability_score,
        "price_limit_rule": info.rule,
        "limit_shape": "",
        "limit_pct": info.limit_pct,
        "return_1d": leader_input.get("return_1d", 0.0),
        "amount_1d": leader_input.get("amount", 0.0),
        "consecutive_limit_count": 0,
        "relative_strength_vs_topic": 0.0,
        "membership_source": leader_input.get("membership_source", ""),
        "status": "DATA_SOURCE_FAILED",
        "raw_snapshot": leader_input,
    }


def _load_strategy4_daily_data(
    code: str,
    *,
    daily_sources: list[str],
    kline_days: int,
    mgr: DataSourceManager,
    fetch_daily_fn=None,
    force_refresh_daily: bool = False,
) -> tuple[list[dict] | None, FetchResult | None]:
    cached = db.get_ohlc(code, max_rows=kline_days)
    if cached and not force_refresh_daily:
        return cached, FetchResult(
            data=cached,
            primary_source="cache",
            fallback_source="cache",
            from_cache=True,
            quote_status="cache",
        )
    fetcher = fetch_daily_fn or fetch_with_retry
    if fetch_daily_fn is not None:
        result = fetcher(
            code,
            primary_ds=daily_sources[0],
            retry_attempts=2,
            fallback_attempts=2,
            mgr=mgr,
            source_chain=daily_sources,
            kline_days=kline_days,
            force_refresh=force_refresh_daily,
        )
    else:
        context = build_cache_freshness_context(now=datetime.now())
        result = fetcher(
            code,
            daily_sources[0],
            retry_attempts=2,
            fallback_attempts=2,
            mgr=mgr,
            source_chain=daily_sources,
            kline_days=kline_days,
            freshness_context=context,
            force_refresh=force_refresh_daily,
        )
    if isinstance(result, FetchResult):
        return result.data, result
    return result, FetchResult(data=result, primary_source="custom", fallback_source="custom")


def _mark_task_stock_failed(task_id: str, code: str, fetch_result: FetchResult | None):
    db.update_task_stock(
        task_id,
        code,
        status="failed",
        status_reason="策略4龙头日线数据拉取失败",
        primary_source=fetch_result.primary_source if fetch_result else "",
        fallback_source=fetch_result.fallback_source if fetch_result else "",
        primary_attempts=fetch_result.primary_attempts if fetch_result else 0,
        fallback_attempts=fetch_result.fallback_attempts if fetch_result else 0,
        primary_error=fetch_result.primary_error if fetch_result else None,
        fallback_error=fetch_result.fallback_error if fetch_result else None,
        source_errors=encode_source_errors(fetch_result.source_errors if fetch_result else {}),
        finished_at=_now(),
    )


def _mark_task_stock_scanned(task_id: str, code: str, data: list[dict], fetch_result: FetchResult | None):
    db.update_task_stock(
        task_id,
        code,
        status="scanned",
        primary_source=fetch_result.primary_source if fetch_result else "",
        fallback_source=fetch_result.fallback_source if fetch_result else "",
        primary_attempts=fetch_result.primary_attempts if fetch_result else 0,
        fallback_attempts=fetch_result.fallback_attempts if fetch_result else 0,
        source_errors=encode_source_errors(fetch_result.source_errors if fetch_result else {}),
        kline_latest_date=data[-1].get("date") if data else None,
        kline_fetched_at=fetch_result.kline_fetched_at if fetch_result else None,
        kline_target_trade_date=fetch_result.kline_target_trade_date if fetch_result else None,
        quote_status=fetch_result.quote_status if fetch_result else None,
        finished_at=_now(),
    )


def _resolve_limit_shape(resolver: PriceLimitResolver, info, data: list[dict], leader_input: dict) -> str:
    if leader_input.get("limit_shape"):
        return str(leader_input.get("limit_shape"))
    if len(data) < 2:
        return ""
    try:
        return resolver.classify_shape(info, data[-1], prev_close=float(data[-2]["close"]))
    except Exception:
        return ""


def _return_over(data: list[dict], days: int) -> float:
    if len(data) <= days:
        return 0.0
    prev = float(data[-days - 1]["close"])
    close = float(data[-1]["close"])
    return round((close - prev) / prev, 4) if prev > 0 else 0.0


def _amount(row: dict) -> float:
    return float(row.get("turnover") or row.get("amount") or 0)


def _avg_amount(data: list[dict], days: int) -> float:
    rows = data[-days:]
    return round(sum(_amount(r) for r in rows) / len(rows), 2) if rows else 0.0


def _last_non_limit_amount(data: list[dict], latest_limit_shape: str) -> float:
    if latest_limit_shape not in {"ONE_WORD_LIMIT_UP", "T_LIMIT_UP", "LIMIT_UP_CLOSE"}:
        return _amount(data[-1])
    return _amount(data[-2]) if len(data) >= 2 else _amount(data[-1])


def _infer_market(code: str) -> str:
    return "SH" if code.startswith(("6", "9")) else "SZ"


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


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

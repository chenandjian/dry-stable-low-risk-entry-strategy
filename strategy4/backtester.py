"""Strategy4 historical snapshot backtester.

The backtester prefers persisted Strategy4 live snapshots when present. When
historical_kline_derived is enabled, missing live snapshots may be reconstructed
only from observable topic index and member stock OHLC rows truncated to the
evaluation date.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

import scanner.db as db
from strategy4.config import resolve_strategy4_config
from strategy4.derived_leader_detector import derive_leaders_for_topic
from strategy4.derived_topic_detector import derive_hot_topics_for_date
from strategy4.engine import HotLeaderSecondWaveEngine
from strategy4.price_limit import (
    LIMIT_SHAPE_ONE_WORD_LIMIT_UP,
    LIMIT_SHAPE_T_LIMIT_UP,
    PriceLimitResolver,
)
from strategy4.snapshot_merge import merge_leaders, merge_topics
from strategy4.topic_index_filters import topic_index_context_passes_filters
from strategy4.topic_index_service import topic_index_context_from_history
from strategy4.tracking_backtest import Strategy4TrackingReplayPool
from strategy4.backtest_models import (
    Strategy4BacktestOpportunity,
    Strategy4BacktestResult,
    Strategy4BacktestSignal,
    Strategy4BacktestSummary,
    Strategy4UnobservedDay,
)


BACKTEST_BUYABLE_TOPIC_STATUSES = {"CONFIRMED_HOT", "LOCKED_HOT_TOPIC"}
BACKTEST_LEADER_STATUSES = {"LEADER_CONFIRMED", "LOCKED_LEADER_WATCH", "HOT_TOPIC_NO_BUY_POINT"}


def run_strategy4_parameter_experiments(
    *,
    db_path: str,
    start_date: str,
    end_date: str,
    base_config: dict,
    experiment_grid: list[dict],
) -> dict[str, Strategy4BacktestResult]:
    """Run a set of Strategy4 backtest experiments over observable snapshots."""
    results: dict[str, Strategy4BacktestResult] = {}
    derived_snapshot_cache: dict[tuple[str, str], tuple[list[dict], list[dict]]] = {}
    ohlc_cache: dict[str, list[dict] | None] = {}
    for experiment in experiment_grid:
        name = str(experiment.get("name") or f"experiment_{len(results) + 1}")
        cfg = copy.deepcopy(base_config or {})
        strategy_cfg = dict(cfg.get("strategy4") or {})
        strategy_cfg.update({k: v for k, v in experiment.items() if k != "name"})
        if (
            "min_leader_strength_score" in strategy_cfg
            and float(strategy_cfg.get("core_leader_strength_score", 0) or 0)
            < float(strategy_cfg["min_leader_strength_score"])
        ):
            strategy_cfg["core_leader_strength_score"] = strategy_cfg["min_leader_strength_score"]
        if (
            "min_reward_risk_ratio" in strategy_cfg
            and float(strategy_cfg.get("core_leader_min_reward_risk_ratio", 0) or 0)
            > float(strategy_cfg["min_reward_risk_ratio"])
        ):
            strategy_cfg["core_leader_min_reward_risk_ratio"] = strategy_cfg["min_reward_risk_ratio"]
        if (
            "max_risk_ratio" in strategy_cfg
            and float(strategy_cfg.get("aggressive_max_risk_ratio", 0) or 0)
            < float(strategy_cfg["max_risk_ratio"])
        ):
            strategy_cfg["aggressive_max_risk_ratio"] = strategy_cfg["max_risk_ratio"]
        cfg["strategy4"] = strategy_cfg
        results[name] = run_strategy4_snapshot_backtest(
            db_path=db_path,
            start_date=start_date,
            end_date=end_date,
            config_snapshot=cfg,
            task_id=name,
            derived_snapshot_cache=derived_snapshot_cache,
            ohlc_cache=ohlc_cache,
        )
    return results


def run_strategy4_snapshot_backtest(
    *,
    db_path: str,
    start_date: str,
    end_date: str,
    config_snapshot: dict,
    task_id: str = "strategy4-backtest",
    derived_snapshot_cache: dict[tuple[str, str], tuple[list[dict], list[dict]]] | None = None,
    ohlc_cache: dict[str, list[dict] | None] | None = None,
) -> Strategy4BacktestResult:
    """Replay Strategy4 snapshots over a date range using local OHLC only."""
    db.init_db(db_path)
    config_snapshot = copy.deepcopy(config_snapshot or {})
    cfg = resolve_strategy4_config(config_snapshot)
    engine = HotLeaderSecondWaveEngine({"strategy4": cfg})
    result = Strategy4BacktestResult(task_id=task_id, config_snapshot=config_snapshot)
    tracking_pool = Strategy4TrackingReplayPool(cfg) if (cfg.get("tracking") or {}).get("enabled", True) else None

    for evaluation_date in _evaluation_dates(start_date, end_date):
        result.summary.evaluation_days += 1
        snapshot_task_id = _snapshot_task_for_exact_date(evaluation_date)
        derived_topics, derived_leaders = _derived_snapshots_for_date_cached(
            evaluation_date,
            cfg,
            derived_snapshot_cache,
        )
        topics: list[dict] = []
        leaders: list[dict] = []
        if not snapshot_task_id:
            if derived_topics and not derived_leaders:
                result.summary.unobserved_members_days += 1
                result.unobserved.append(Strategy4UnobservedDay(
                    evaluation_date=evaluation_date,
                    reason_code="UNOBSERVED_DERIVED_MEMBERS",
                    detail="Derived hot topics exist but no observable member leader snapshots are available.",
                ))
            elif derived_topics:
                topics = derived_topics
                leaders = derived_leaders
                result.summary.derived_snapshot_days += 1
                if any(t.get("membership_mode") == "current_members_proxy" for t in derived_topics):
                    result.summary.current_members_proxy_days += 1
            elif tracking_pool is None or not tracking_pool.active_topics():
                result.summary.unobserved_snapshot_days += 1
                result.unobserved.append(Strategy4UnobservedDay(
                    evaluation_date=evaluation_date,
                    reason_code="UNOBSERVED_TOPIC_SNAPSHOT",
                    detail="No Strategy4 live or derived hot-topic snapshot exists for this evaluation date.",
                ))
                continue
        else:
            live_topics = db.get_strategy4_hot_topics(snapshot_task_id)
            live_leaders = db.get_strategy4_leaders(snapshot_task_id)
            result.summary.live_snapshot_days += 1
            if derived_topics:
                topics = merge_topics(live_topics, derived_topics, {"merge_policy": cfg.get("merge_policy", {})})
                leaders = merge_leaders(live_leaders, derived_leaders)
                result.summary.merged_snapshot_days += 1
            else:
                topics = live_topics
                leaders = live_leaders

        if tracking_pool is not None and (topics or leaders):
            tracking_pool.update_from_snapshots(evaluation_date, topics, leaders)
        if tracking_pool is not None:
            tracking_pool.advance_to(evaluation_date)
            result.summary.tracking_pool_topics = max(result.summary.tracking_pool_topics, len(tracking_pool.topics))
            result.summary.tracking_pool_leaders = max(result.summary.tracking_pool_leaders, len(tracking_pool.leaders))

        selected_topics = _select_topics_for_experiment(topics, cfg)
        leaders_by_topic = _leaders_by_topic(leaders, cfg)
        if selected_topics or (tracking_pool and tracking_pool.active_topics()):
            result.summary.observed_snapshot_days += 1

        emitted_keys: set[tuple[str, str, str]] = set()
        for topic in selected_topics:
            topic_index_context = _topic_index_context_for_backtest(topic, cfg, evaluation_date)
            if not topic_index_context.get("observed"):
                result.summary.unobserved_topic_index_days += 1
                result.unobserved.append(Strategy4UnobservedDay(
                    evaluation_date=evaluation_date,
                    reason_code="UNOBSERVED_TOPIC_INDEX",
                    detail=f"{topic.get('topic_id') or topic.get('topic_name')} has no observable topic index K-line history.",
                ))
                continue
            if not topic_index_context_passes_filters(topic_index_context, cfg):
                continue
            for leader in leaders_by_topic.get(topic.get("topic_id", ""), []):
                signal = _evaluate_leader_snapshot(
                    topic,
                    leader,
                    engine,
                    cfg,
                    evaluation_date,
                    topic_index_context=topic_index_context,
                    ohlc_cache=ohlc_cache,
                )
                if signal is None:
                    continue
                signal.evaluation_snapshot.setdefault("candidate_origin", "current_hot")
                result.signals.append(signal)
                opp = _opportunity_from_signal(signal)
                ohlc = _get_ohlc(signal.code, ohlc_cache) or []
                calculate_strategy4_execution_outcome(opp, ohlc)
                result.opportunities.append(opp)
                emitted_keys.add((topic.get("topic_id", ""), leader.get("code", ""), evaluation_date))

        if tracking_pool is not None:
            for topic in tracking_pool.active_topics():
                topic_index_context = _topic_index_context_for_backtest(topic, cfg, evaluation_date)
                if not topic_index_context.get("observed"):
                    continue
                if not topic_index_context_passes_filters(topic_index_context, cfg):
                    continue
                for leader in tracking_pool.active_leaders_for_topic(topic.get("topic_id", "")):
                    key = (topic.get("topic_id", ""), leader.get("code", ""), evaluation_date)
                    if key in emitted_keys:
                        for signal in result.signals:
                            if (
                                signal.topic_id == key[0]
                                and signal.code == key[1]
                                and signal.evaluation_date == key[2]
                            ):
                                signal.evaluation_snapshot["candidate_origin"] = "merged_current_and_tracking"
                        continue
                    signal = _evaluate_leader_snapshot(
                        topic,
                        leader,
                        engine,
                        cfg,
                        evaluation_date,
                        topic_index_context=topic_index_context,
                        ohlc_cache=ohlc_cache,
                    )
                    if signal is None:
                        continue
                    metadata = tracking_pool.metadata_for(topic, leader, origin="tracking_pool")
                    signal.evaluation_snapshot.update(metadata)
                    signal.evaluation_snapshot["candidate_origin"] = "tracking_pool"
                    result.signals.append(signal)
                    opp = _opportunity_from_signal(signal)
                    ohlc = _get_ohlc(signal.code, ohlc_cache) or []
                    calculate_strategy4_execution_outcome(opp, ohlc)
                    result.opportunities.append(opp)
                    result.summary.tracking_pool_signals += 1
                    _count_tracking_age_bucket(result.summary, int(metadata.get("tracking_age_days") or 0))

    _finalize_summary(result.summary, result.signals, result.opportunities)
    return result


def calculate_strategy4_execution_outcome(
    opp: Strategy4BacktestOpportunity,
    ohlc_data: list[dict],
) -> Strategy4BacktestOpportunity:
    """Calculate Strategy4 opportunity outcome with the NEXT_OPEN model."""
    opp.execution_model = "NEXT_OPEN"
    date_to_index = {row["date"]: i for i, row in enumerate(ohlc_data)}
    signal_idx = date_to_index.get(opp.first_detected_date)
    if signal_idx is None or signal_idx + 1 >= len(ohlc_data):
        opp.exit_reason = "UNOBSERVED_ENTRY"
        return opp

    entry_day = ohlc_data[signal_idx + 1]
    signal_day = ohlc_data[signal_idx]
    resolver = PriceLimitResolver()
    info = resolver.resolve(opp.code, opp.name)
    limit_shape = resolver.classify_shape(info, entry_day, prev_close=float(signal_day["close"]))
    if limit_shape == LIMIT_SHAPE_ONE_WORD_LIMIT_UP:
        opp.exit_reason = "NO_ENTRY_LIMIT_UP_UNBUYABLE"
        return opp
    if limit_shape == LIMIT_SHAPE_T_LIMIT_UP:
        opp.exit_reason = "NO_ENTRY_OPEN_LIMIT_UNOBSERVED"
        return opp

    entry_price = float(entry_day["open"])
    if entry_price <= opp.stop_loss:
        opp.exit_reason = "NO_ENTRY_GAP_BELOW_STOP"
        return opp

    opp.entry_date = entry_day["date"]
    opp.entry_price = entry_price
    future_from_entry = ohlc_data[signal_idx + 1:]
    opp.available_forward_days = len(future_from_entry)

    stop_hit = None
    target_hit = None
    for offset, row in enumerate(future_from_entry, start=1):
        if stop_hit is None and float(row["low"]) <= opp.stop_loss:
            stop_hit = (offset, row["date"], opp.stop_loss)
        if target_hit is None and opp.target_price > 0 and float(row["high"]) >= opp.target_price:
            target_hit = (offset, row["date"], opp.target_price)

    selected = None
    if stop_hit and target_hit:
        selected = stop_hit if stop_hit[0] <= target_hit[0] else target_hit
        opp.exit_reason = "STOP" if selected is stop_hit else "TARGET"
    elif stop_hit:
        selected = stop_hit
        opp.exit_reason = "STOP"
    elif target_hit:
        selected = target_hit
        opp.exit_reason = "TARGET"
    else:
        opp.exit_reason = "UNRESOLVED" if future_from_entry else "UNOBSERVED_FORWARD"
        opp.holding_days = len(future_from_entry)

    if selected:
        opp.holding_days = selected[0]
        opp.exit_date = selected[1]
        opp.exit_price = selected[2]
        opp.realized_return = opp.exit_price / opp.entry_price - 1.0
    elif future_from_entry and opp.entry_price > 0:
        opp.exit_date = future_from_entry[-1]["date"]
        opp.exit_price = float(future_from_entry[-1]["close"])
        opp.realized_return = opp.exit_price / opp.entry_price - 1.0
    return opp


def generate_strategy4_optimization_report(
    *,
    db_path: str,
    start_date: str,
    end_date: str,
    base_config: dict,
    experiment_grid: list[dict],
    report_path: str,
) -> dict[str, Strategy4BacktestResult]:
    """Run experiments and write a Markdown optimization report."""
    results = run_strategy4_parameter_experiments(
        db_path=db_path,
        start_date=start_date,
        end_date=end_date,
        base_config=base_config,
        experiment_grid=experiment_grid,
    )
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).write_text(
        _render_report(db_path, start_date, end_date, results),
        encoding="utf-8",
    )
    return results


def _evaluate_leader_snapshot(
    topic: dict,
    leader: dict,
    engine: HotLeaderSecondWaveEngine,
    cfg: dict,
    evaluation_date: str,
    topic_index_context: dict | None = None,
    ohlc_cache: dict[str, list[dict] | None] | None = None,
) -> Strategy4BacktestSignal | None:
    code = str(leader.get("code") or "")
    ohlc = _get_ohlc(code, ohlc_cache) or []
    history = [row for row in ohlc if str(row.get("date") or "") <= evaluation_date]
    if len(history) < 10:
        return None

    support = min(float(row["low"]) for row in history[-10:])
    target = max(float(row["high"]) for row in history[-60:])
    evaluation = engine.evaluate_at(
        history,
        code=code,
        name=str(leader.get("name") or ""),
        leader_context={
            "support_price": support,
            "target_price": target,
            "is_core_leader": str(leader.get("leader_type") or "") == "SPACE_LEADER",
        },
    )
    if not evaluation.get("passed"):
        return None

    first_wave = evaluation.get("first_wave")
    pullback = evaluation.get("pullback")
    rr = evaluation.get("risk_reward")
    return Strategy4BacktestSignal(
        code=code,
        name=str(leader.get("name") or ""),
        topic_id=str(topic.get("topic_id") or ""),
        topic_name=str(topic.get("topic_name") or ""),
        evaluation_date=evaluation_date,
        evaluation_index=len(history) - 1,
        hot_topic_score=float(topic.get("hot_topic_score") or 0),
        leader_strength_score=float(leader.get("leader_strength_score") or 0),
        tradability_score=float(leader.get("tradability_score") or 0),
        first_wave_return=float(first_wave.first_wave_return if first_wave else 0),
        pullback_pct=float(pullback.pullback_pct if pullback else 0),
        pullback_days=int(pullback.pullback_days if pullback else 0),
        support_price=float(rr.support_price if rr else 0),
        stop_loss=float(rr.stop_loss if rr else 0),
        target_price=float(rr.target_price if rr else 0),
        risk_ratio=float(rr.risk_ratio if rr else 0),
        reward_risk_ratio=float(rr.reward_risk_ratio if rr else 0),
        evaluation_snapshot={
            "snapshot_date": evaluation_date,
            **_source_metadata(topic, leader),
            "topic_status": topic.get("status"),
            "leader_status": leader.get("status"),
            "engine_status": evaluation.get("status"),
            **_market_index_metadata(code, evaluation_date),
            **_topic_index_metadata(topic_index_context or {}),
        },
    )


def _get_ohlc(code: str, cache: dict[str, list[dict] | None] | None = None) -> list[dict] | None:
    if cache is None:
        return db.get_ohlc(code)
    if code not in cache:
        cache[code] = db.get_ohlc(code)
    return copy.deepcopy(cache[code])


def _opportunity_from_signal(signal: Strategy4BacktestSignal) -> Strategy4BacktestOpportunity:
    return Strategy4BacktestOpportunity(
        code=signal.code,
        name=signal.name,
        topic_id=signal.topic_id,
        topic_name=signal.topic_name,
        first_detected_date=signal.evaluation_date,
        hot_topic_score=signal.hot_topic_score,
        leader_strength_score=signal.leader_strength_score,
        tradability_score=signal.tradability_score,
        first_wave_return=signal.first_wave_return,
        pullback_pct=signal.pullback_pct,
        pullback_days=signal.pullback_days,
        support_price=signal.support_price,
        stop_loss=signal.stop_loss,
        target_price=signal.target_price,
        risk_ratio=signal.risk_ratio,
        reward_risk_ratio=signal.reward_risk_ratio,
        evaluation_snapshot=signal.evaluation_snapshot,
    )


def _select_topics_for_experiment(topics: list[dict], cfg: dict) -> list[dict]:
    min_score = float(cfg.get("min_hot_topic_score", 85))
    min_signals = int(cfg.get("min_hot_topic_signal_count", 2))
    top_n = int(cfg.get("hot_topic_top_n", 8))
    selected = []
    for topic in sorted(topics, key=lambda item: float(item.get("hot_topic_score") or 0), reverse=True):
        if len(selected) >= top_n:
            break
        if str(topic.get("status") or "") not in BACKTEST_BUYABLE_TOPIC_STATUSES:
            continue
        score = float(topic.get("hot_topic_score") or 0)
        signals = int(topic.get("signal_count") or 0)
        if score >= min_score and signals >= min_signals:
            selected.append(topic)
            continue
        if _locked_attention_score(topic) >= float(cfg.get("min_locked_attention_score", 18)):
            selected.append(topic)
    return selected


def _leaders_by_topic(leaders: list[dict], cfg: dict) -> dict[str, list[dict]]:
    min_score = float(cfg.get("min_leader_strength_score", 88))
    grouped: dict[str, list[dict]] = {}
    for leader in leaders:
        if float(leader.get("leader_strength_score") or 0) < min_score:
            continue
        if str(leader.get("status") or "") not in BACKTEST_LEADER_STATUSES:
            continue
        grouped.setdefault(str(leader.get("topic_id") or ""), []).append(leader)
    for items in grouped.values():
        items.sort(key=lambda item: float(item.get("leader_strength_score") or 0), reverse=True)
    return grouped


def _locked_attention_score(topic: dict) -> float:
    raw = topic.get("raw_snapshot") or {}
    if not isinstance(raw, dict):
        raw = {}
    bonus = 10.0 if raw.get("locked_attention") else 0.0
    return float(topic.get("leader_limit_score") or 0) + bonus


def _market_index_metadata(code: str, evaluation_date: str) -> dict:
    symbol = _market_index_symbol_for_code(code)
    rows = db.get_market_index_ohlc(symbol, end_date=evaluation_date, max_rows=120)
    return {
        "market_index_symbol": symbol,
        "market_index_latest_date": rows[-1]["date"] if rows else "",
        "market_index_rows": len(rows),
        "market_index_observed": bool(rows),
    }


def _market_index_symbol_for_code(code: str) -> str:
    normalized = str(code or "")
    if normalized.startswith(("300", "301")):
        return "sz399006"
    if normalized.startswith("688"):
        return "sh000688"
    if normalized.startswith(("000", "001", "002", "003")):
        return "sz399001"
    return "sh000001"


def _topic_index_context_for_backtest(topic: dict, cfg: dict, evaluation_date: str) -> dict:
    topic_index_cfg = cfg.get("topic_index") or {}
    min_rows = int(topic_index_cfg.get("min_required_rows", 60))
    max_rows = int(topic_index_cfg.get("history_days", 250))
    return topic_index_context_from_history(topic, evaluation_date=evaluation_date, min_required_rows=min_rows, max_rows=max_rows)


def _topic_index_metadata(context: dict) -> dict:
    return {
        "topic_index_source": context.get("source", ""),
        "topic_index_latest_date": context.get("latest_date", ""),
        "topic_index_rows": int(context.get("rows") or 0),
        "topic_index_observed": bool(context.get("observed")),
        "topic_index_status": context.get("status", ""),
        "topic_index_phase": context.get("phase", ""),
        "topic_return_1d": context.get("topic_return_1d", 0.0),
        "topic_return_5d": context.get("topic_return_5d", 0.0),
        "topic_return_10d": context.get("topic_return_10d", 0.0),
        "topic_return_20d": context.get("topic_return_20d", 0.0),
    }


def _derived_snapshots_for_date(evaluation_date: str, cfg: dict) -> tuple[list[dict], list[dict]]:
    source_modes = cfg.get("source_modes") or {}
    derived_cfg = cfg.get("derived_source") or {}
    if not source_modes.get("historical_kline_derived_enabled", True) or not derived_cfg.get("enabled", True):
        return [], []
    topics = derive_hot_topics_for_date(evaluation_date, cfg)
    leaders: list[dict] = []
    for topic in topics:
        topic_leaders = derive_leaders_for_topic(topic, evaluation_date=evaluation_date, config=cfg)
        leaders.extend(topic_leaders)
        if topic_leaders:
            raw = topic.setdefault("raw_snapshot", {})
            if isinstance(raw, dict):
                raw["derived_leaders"] = topic_leaders
    return topics, leaders


def _derived_snapshots_for_date_cached(
    evaluation_date: str,
    cfg: dict,
    cache: dict[tuple[str, str], tuple[list[dict], list[dict]]] | None,
) -> tuple[list[dict], list[dict]]:
    if cache is None:
        return _derived_snapshots_for_date(evaluation_date, cfg)
    key = (evaluation_date[:10], _derived_snapshot_cache_key(cfg))
    if key not in cache:
        cache[key] = copy.deepcopy(_derived_snapshots_for_date(evaluation_date, cfg))
    return copy.deepcopy(cache[key])


def _derived_snapshot_cache_key(cfg: dict) -> str:
    relevant = {
        "source_modes": cfg.get("source_modes") or {},
        "topic_index": cfg.get("topic_index") or {},
        "derived_source": cfg.get("derived_source") or {},
    }
    return json.dumps(relevant, sort_keys=True, ensure_ascii=False, default=str)


def _source_metadata(topic: dict, leader: dict) -> dict:
    modes: list[str] = []
    for value in list(topic.get("source_modes") or []) + list(leader.get("source_modes") or []):
        if value and value not in modes:
            modes.append(value)
    return {
        "snapshot_source": topic.get("snapshot_source") or leader.get("snapshot_source") or topic.get("source", ""),
        "source_modes": modes,
        "merge_confidence": topic.get("merge_confidence") or leader.get("merge_confidence", ""),
        "merge_warnings": topic.get("merge_warnings") or leader.get("merge_warnings") or [],
        "membership_mode": topic.get("membership_mode") or leader.get("membership_mode", ""),
    }


def _snapshot_task_for_exact_date(evaluation_date: str) -> str | None:
    conn = db.get_conn()
    row = conn.execute(
        """SELECT h.task_id
           FROM strategy4_hot_topics h
           JOIN scan_tasks t ON t.id = h.task_id
           WHERE substr(h.snapshot_time, 1, 10) = ?
             AND t.strategy_type = 'STRATEGY_4_HOT_LEADER_SECOND_WAVE'
             AND t.status = 'completed'
           GROUP BY h.task_id
           ORDER BY MAX(h.snapshot_time) DESC
           LIMIT 1""",
        (evaluation_date,),
    ).fetchone()
    return row[0] if row else None


def _evaluation_dates(start_date: str, end_date: str) -> list[str]:
    dates = _cached_observable_dates(start_date, end_date)
    if dates:
        return dates
    return _calendar_dates(start_date, end_date)


def _cached_observable_dates(start_date: str, end_date: str) -> list[str]:
    conn = db.get_conn()
    start = start_date[:10]
    end = end_date[:10]
    rows = conn.execute(
        """SELECT date FROM market_index_ohlc WHERE date BETWEEN ? AND ?
           UNION
           SELECT substr(snapshot_time, 1, 10) AS date
           FROM strategy4_hot_topics
           WHERE substr(snapshot_time, 1, 10) BETWEEN ? AND ?
           UNION
           SELECT date FROM strategy4_topic_index_ohlc WHERE date BETWEEN ? AND ?
           ORDER BY date""",
        (start, end, start, end, start, end),
    ).fetchall()
    return [row[0] for row in rows]


def _calendar_dates(start_date: str, end_date: str) -> list[str]:
    start = dt.date.fromisoformat(start_date[:10])
    end = dt.date.fromisoformat(end_date[:10])
    if end < start:
        raise ValueError("end_date must be >= start_date")
    days = []
    current = start
    while current <= end:
        days.append(current.isoformat())
        current += dt.timedelta(days=1)
    return days


def _finalize_summary(
    summary: Strategy4BacktestSummary,
    signals: list[Strategy4BacktestSignal],
    opportunities: list[Strategy4BacktestOpportunity],
) -> None:
    summary.total_signals = len(signals)
    summary.total_opportunities = len(opportunities)
    entered = [opp for opp in opportunities if opp.entry_price > 0]
    summary.entered_opportunities = len(entered)
    summary.no_entry_count = len([opp for opp in opportunities if opp.entry_price <= 0])
    summary.stop_count = len([opp for opp in opportunities if opp.exit_reason == "STOP"])
    summary.target_count = len([opp for opp in opportunities if opp.exit_reason == "TARGET"])
    summary.unresolved_count = len([opp for opp in opportunities if opp.exit_reason == "UNRESOLVED"])
    summary.unobserved_forward_count = len([
        opp for opp in opportunities
        if opp.exit_reason in {"UNOBSERVED_ENTRY", "UNOBSERVED_FORWARD"}
    ])
    returns = [opp.realized_return for opp in entered if opp.exit_reason not in {"UNOBSERVED_ENTRY", "UNOBSERVED_FORWARD"}]
    if returns:
        summary.avg_realized_return = sum(returns) / len(returns)
        gross_profit = sum(v for v in returns if v > 0)
        gross_loss = abs(sum(v for v in returns if v < 0))
        summary.profit_factor = gross_profit / gross_loss if gross_loss > 0 else None
    for opp in opportunities:
        snapshot = opp.evaluation_snapshot or {}
        modes = snapshot.get("source_modes") or []
        origin = snapshot.get("candidate_origin") or "current_hot"
        if origin == "tracking_pool":
            summary.tracking_pool_opportunities += 1
        elif origin == "current_hot":
            summary.current_hot_opportunities += 1
        elif origin == "merged_current_and_tracking":
            summary.current_hot_opportunities += 1
            summary.tracking_pool_opportunities += 1
        if modes == ["historical_kline_derived"]:
            summary.derived_only_opportunities += 1
        if "live_external" in modes and "historical_kline_derived" in modes:
            summary.live_and_derived_confirmed_opportunities += 1


def _count_tracking_age_bucket(summary: Strategy4BacktestSummary, age: int) -> None:
    if age <= 20:
        summary.tracking_age_1_20_count += 1
    elif age <= 60:
        summary.tracking_age_21_60_count += 1
    else:
        summary.tracking_age_61_120_count += 1


def _render_report(
    db_path: str,
    start_date: str,
    end_date: str,
    results: dict[str, Strategy4BacktestResult],
) -> str:
    coverage = _coverage(db_path)
    lines = [
        "# 策略4 Phase 2 回测与参数优化报告",
        "",
        f"- 回测区间：{start_date} 至 {end_date}",
        f"- 数据库：`{db_path}`",
        f"- daily_ohlc：{coverage['daily_rows']} 行，{coverage['daily_stocks']} 只，{coverage['daily_min']} 至 {coverage['daily_max']}",
        f"- market_index_ohlc：{coverage['index_rows']} 行，{coverage['index_min']} 至 {coverage['index_max']}",
        f"- strategy4_topic_index_ohlc：{coverage['topic_index_rows']} 行（{coverage['topic_index_note']}）",
        f"- strategy4_hot_topics：{coverage['topic_rows']} 行，{coverage['topic_min']} 至 {coverage['topic_max']}",
        f"- strategy4_leaders：{coverage['leader_rows']} 行",
        "",
        "## 参数实验结果",
        "",
        "| 实验 | 可观察日 | 不可观察日 | 不可观察率 | 池题材 | 池龙头 | 信号 | 即时机会 | 跟踪池机会 | 总机会 | 入场 | 未入场 | 目标 | 止损 | 平均收益 | PF | 平均盈利 | 平均亏损 | 平均盈亏比 | 跟踪年龄分布 | 月度分布 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for name, result in results.items():
        s = result.summary
        metrics = _result_metrics(result)
        pf = "--" if s.profit_factor is None else f"{s.profit_factor:.2f}"
        lines.append(
            f"| {name} | {s.observed_snapshot_days} | {s.unobserved_snapshot_days} | {metrics['unobserved_rate']} | "
            f"{s.tracking_pool_topics} | {s.tracking_pool_leaders} | {s.total_signals} | "
            f"{s.current_hot_opportunities} | {s.tracking_pool_opportunities} | {s.total_opportunities} | {s.entered_opportunities} | "
            f"{s.no_entry_count} | {s.target_count} | {s.stop_count} | {s.avg_realized_return:.2%} | {pf} | "
            f"{metrics['avg_win']} | {metrics['avg_loss']} | {metrics['avg_win_loss_ratio']} | "
            f"{metrics['tracking_age_distribution']} | {metrics['monthly_distribution']} |"
        )
    opportunity_lines = _opportunity_detail_lines(results)
    if opportunity_lines:
        lines.extend([
            "",
            "## 机会明细",
            "",
            "| 实验 | 股票 | 题材 | 来源 | 发现日 | 入场日 | 退出原因 | 收益 | RR | 风险 | 回踩 | 回踩天数 | 跟踪天数 | 板块源 | 板块K线日期 | 板块阶段 |",
            "|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---|",
            *opportunity_lines,
        ])
    best_name, best_result = _best_result(results)
    lines.extend([
        "",
        "## 最佳参数组合",
        "",
        *_best_result_lines(best_name, best_result),
        "",
        "## 结论",
        "",
        *_conclusion_lines(coverage, results),
        "",
        "## 失效场景",
        "",
        "- 缺少历史热点题材快照时，回测日标记为 `UNOBSERVED_TOPIC_SNAPSHOT`。",
        "- 缺少行业/题材指数历史缓存时，报告标记为 `UNOBSERVED_TOPIC_INDEX`，不伪造板块指数走势。",
        "- 次日一字涨停不可成交时，机会标记为 `NO_ENTRY_LIMIT_UP_UNBUYABLE`。",
        "- 次日 T 字涨停或开盘涨停回封时，机会标记为 `NO_ENTRY_OPEN_LIMIT_UNOBSERVED`，不假设能按开盘价成交。",
        "- 历史快照未覆盖完整热点周期时，参数实验可能只反映单日市场状态。",
        "",
        "## 过拟合风险",
        "",
        "目前可观察策略4样本过少。若直接根据单日热点榜调参，会把参数拟合到一个截面，而不是二波交易规律。",
    ])
    return "\n".join(lines) + "\n"


def _opportunity_detail_lines(results: dict[str, Strategy4BacktestResult]) -> list[str]:
    lines: list[str] = []
    for name, result in results.items():
        for opp in result.opportunities:
            snapshot = opp.evaluation_snapshot or {}
            entry_date = opp.entry_date or "--"
            realized = "--" if opp.entry_price <= 0 else f"{opp.realized_return:.2%}"
            lines.append(
                f"| {name} | {opp.code} {opp.name} | {opp.topic_name} | {snapshot.get('candidate_origin', 'current_hot')} | {opp.first_detected_date} | "
                f"{entry_date} | {opp.exit_reason or '--'} | {realized} | {opp.reward_risk_ratio:.2f} | "
                f"{opp.risk_ratio:.2%} | {opp.pullback_pct:.2%} | {opp.pullback_days} | "
                f"{snapshot.get('tracking_age_days', 0) or 0} | "
                f"{snapshot.get('topic_index_source', '') or '--'} | {snapshot.get('topic_index_latest_date', '') or '--'} | "
                f"{snapshot.get('topic_index_phase', '') or '--'} |"
            )
    return lines


def _result_metrics(result: Strategy4BacktestResult) -> dict:
    s = result.summary
    total_days = s.evaluation_days or 0
    unobserved_rate = s.unobserved_snapshot_days / total_days if total_days else 0.0
    entered_returns = [
        opp.realized_return
        for opp in result.opportunities
        if opp.entry_price > 0 and opp.exit_reason not in {"UNOBSERVED_ENTRY", "UNOBSERVED_FORWARD"}
    ]
    wins = [v for v in entered_returns if v > 0]
    losses = [v for v in entered_returns if v < 0]
    avg_win = sum(wins) / len(wins) if wins else None
    avg_loss = sum(losses) / len(losses) if losses else None
    avg_win_loss_ratio = abs(avg_win / avg_loss) if avg_win is not None and avg_loss and avg_loss < 0 else None
    monthly: dict[str, int] = {}
    for opp in result.opportunities:
        month = str(opp.first_detected_date or "")[:7] or "unknown"
        monthly[month] = monthly.get(month, 0) + 1
    return {
        "unobserved_rate": f"{unobserved_rate:.1%}",
        "avg_win": "--" if avg_win is None else f"{avg_win:.2%}",
        "avg_loss": "--" if avg_loss is None else f"{avg_loss:.2%}",
        "avg_win_loss_ratio": "--" if avg_win_loss_ratio is None else f"{avg_win_loss_ratio:.2f}",
        "tracking_age_distribution": (
            f"1-20:{s.tracking_age_1_20_count}, "
            f"21-60:{s.tracking_age_21_60_count}, "
            f"61-120:{s.tracking_age_61_120_count}"
        ),
        "monthly_distribution": ", ".join(f"{k}:{v}" for k, v in sorted(monthly.items())) or "--",
    }


def _best_result(results: dict[str, Strategy4BacktestResult]) -> tuple[str, Strategy4BacktestResult] | tuple[None, None]:
    if not results:
        return None, None
    entered = [
        (name, result)
        for name, result in results.items()
        if result.summary.entered_opportunities > 0
    ]
    if entered:
        minimum_sampled = [
            item for item in entered
            if item[1].summary.entered_opportunities >= 5
        ]
        pool = minimum_sampled or entered
        return max(
            pool,
            key=lambda item: (
                item[1].summary.profit_factor or 0.0,
                item[1].summary.avg_realized_return,
                item[1].summary.entered_opportunities,
            ),
        )
    opportunities = [
        (name, result)
        for name, result in results.items()
        if result.summary.total_opportunities > 0
    ]
    if opportunities:
        return max(opportunities, key=lambda item: item[1].summary.total_opportunities)
    return next(iter(results.items()))


def _best_result_lines(name: str | None, result: Strategy4BacktestResult | None) -> list[str]:
    if not name or not result:
        return ["本次没有可用实验结果。"]
    s = result.summary
    if s.entered_opportunities <= 0:
        if s.total_opportunities > 0:
            return [
                f"本次机会数最多的实验是 `{name}`，共产生 {s.total_opportunities} 个信号机会，但没有可观察的 T+1 入场。",
                "由于缺少可执行入场和后续收益，不能计算可信 PF、平均盈亏比或胜率。",
                "正式参数建议：暂不升级生产默认值，保留当前参数作为观察基线。",
            ]
        return [
            "本次没有可证明更优的参数组合。所有实验组均为 0 信号、0 机会。",
            "正式参数建议：保留当前默认参数作为观察基线，暂不升级生产默认值。",
        ]
    pf = "--" if s.profit_factor is None else f"{s.profit_factor:.2f}"
    return [
        f"当前表现最好的可执行实验是 `{name}`：入场 {s.entered_opportunities}，平均收益 {s.avg_realized_return:.2%}，PF {pf}。",
        "是否升级正式参数仍需结合样本量、月度集中度和最大连续亏损审查；样本不足时不建议自动升级。",
    ]


def _conclusion_lines(coverage: dict, results: dict[str, Strategy4BacktestResult]) -> list[str]:
    max_opportunities = max((r.summary.total_opportunities for r in results.values()), default=0)
    max_entered = max((r.summary.entered_opportunities for r in results.values()), default=0)
    lines = [
        f"当前策略4真实快照覆盖 {coverage['topic_snapshot_days']} 个交易日，历史样本仍偏少。",
        f"行业/题材指数缓存覆盖 {coverage['topic_index_topics']} 个题材、{coverage['topic_index_rows']} 行，日期范围 {coverage['topic_index_min']} 至 {coverage['topic_index_max']}。",
        "本次回测仅使用历史快照、跟踪池历史状态，以及 evaluation_date 当日及之前的真实板块K线和个股K线，不使用未来数据。",
        f"跟踪池最大入池题材数 {max((r.summary.tracking_pool_topics for r in results.values()), default=0)}，最大入池龙头数 {max((r.summary.tracking_pool_leaders for r in results.values()), default=0)}。",
    ]
    if max_entered <= 0:
        lines.append(
            f"参数实验最多产生 {max_opportunities} 个机会，但没有可观察入场，因此证据不足以升级正式参数。"
        )
    else:
        lines.append(
            f"参数实验最多产生 {max_opportunities} 个机会、{max_entered} 个可观察入场；正式升级仍需检查样本量和集中度。"
        )
    return lines


def _coverage(db_path: str) -> dict:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    daily = con.execute(
        "SELECT COUNT(*) rows, COUNT(DISTINCT code) stocks, MIN(date) min_date, MAX(date) max_date FROM daily_ohlc"
    ).fetchone()
    index = con.execute(
        "SELECT COUNT(*) rows, MIN(date) min_date, MAX(date) max_date FROM market_index_ohlc"
    ).fetchone()
    topics = con.execute(
        "SELECT COUNT(*) rows, COUNT(DISTINCT substr(snapshot_time, 1, 10)) days, MIN(snapshot_time) min_date, MAX(snapshot_time) max_date FROM strategy4_hot_topics"
    ).fetchone()
    leaders = con.execute("SELECT COUNT(*) rows FROM strategy4_leaders").fetchone()
    topic_index_rows = 0
    topic_index_topics = 0
    topic_index_min = ""
    topic_index_max = ""
    topic_index_note = "UNOBSERVED_TOPIC_INDEX: no topic/industry index history table found"
    if _table_exists(con, "strategy4_topic_index_ohlc"):
        topic_index = con.execute(
            "SELECT COUNT(*) rows, COUNT(DISTINCT topic_id) topics, MIN(date) min_date, MAX(date) max_date FROM strategy4_topic_index_ohlc"
        ).fetchone()
        topic_index_rows = topic_index["rows"]
        topic_index_topics = topic_index["topics"]
        topic_index_min = topic_index["min_date"] or ""
        topic_index_max = topic_index["max_date"] or ""
        topic_index_note = "observable" if topic_index_rows else "UNOBSERVED_TOPIC_INDEX: empty topic index cache"
    return {
        "daily_rows": daily["rows"],
        "daily_stocks": daily["stocks"],
        "daily_min": daily["min_date"],
        "daily_max": daily["max_date"],
        "index_rows": index["rows"],
        "index_min": index["min_date"],
        "index_max": index["max_date"],
        "topic_rows": topics["rows"],
        "topic_snapshot_days": topics["days"],
        "topic_min": topics["min_date"],
        "topic_max": topics["max_date"],
        "leader_rows": leaders["rows"],
        "topic_index_rows": topic_index_rows,
        "topic_index_topics": topic_index_topics,
        "topic_index_min": topic_index_min,
        "topic_index_max": topic_index_max,
        "topic_index_note": topic_index_note,
    }


def _table_exists(con: sqlite3.Connection, table_name: str) -> bool:
    return bool(con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone())


def _default_experiments() -> list[dict]:
    common = {
        "hot_topic_top_n": 16,
        "watch_hot_topic_top_n": 16,
        "min_hot_topic_signal_count": 1,
        "min_strong_day_count_10d": 1,
        "pullback_min_days": 1,
        "pullback_max_days": 40,
        "core_leader_min_reward_risk_ratio": 1.0,
        "aggressive_max_risk_ratio": 0.15,
        "derived_source": {
            "topic_top_n": 30,
            "max_topics_per_day": 34,
            "max_leaders_per_topic": 5,
            "min_topic_hot_score": 50,
            "min_confirmed_topic_hot_score": 60,
            "min_member_count": 5,
        },
    }

    def targeted(name: str, **overrides) -> dict:
        item = copy.deepcopy(common)
        item["name"] = name
        derived_confirm = overrides.pop("derived_confirm", None)
        if derived_confirm is not None:
            item["derived_source"]["min_confirmed_topic_hot_score"] = derived_confirm
        phases = overrides.pop("phases", None)
        if phases is not None:
            item["topic_index_filters"] = {"allowed_phases": phases}
        item.update(overrides)
        return item

    return [
        {"name": "baseline"},
        targeted(
            "confirm60_leader40_fw10_pb35_risk12_rr10",
            min_hot_topic_score=60,
            min_leader_strength_score=40,
            min_first_wave_return_10d=0.05,
            min_first_wave_return_20d=0.10,
            pullback_min_pct=0.05,
            pullback_max_pct=0.35,
            max_risk_ratio=0.12,
            min_reward_risk_ratio=1.0,
        ),
        targeted(
            "confirm60_leader40_fw10_pb35_risk10_rr10",
            min_hot_topic_score=60,
            min_leader_strength_score=40,
            min_first_wave_return_10d=0.05,
            min_first_wave_return_20d=0.10,
            pullback_min_pct=0.05,
            pullback_max_pct=0.35,
            max_risk_ratio=0.10,
            min_reward_risk_ratio=1.0,
        ),
        targeted(
            "early_only_risk10_pb35",
            min_hot_topic_score=60,
            min_leader_strength_score=40,
            min_first_wave_return_10d=0.05,
            min_first_wave_return_20d=0.10,
            pullback_min_pct=0.05,
            pullback_max_pct=0.35,
            max_risk_ratio=0.10,
            min_reward_risk_ratio=1.0,
            phases=["EARLY_ACCELERATION"],
        ),
        targeted(
            "main_only_pb35_risk12",
            min_hot_topic_score=60,
            min_leader_strength_score=40,
            min_first_wave_return_10d=0.05,
            min_first_wave_return_20d=0.10,
            pullback_min_pct=0.05,
            pullback_max_pct=0.35,
            max_risk_ratio=0.12,
            min_reward_risk_ratio=1.0,
            phases=["MAIN_TREND"],
        ),
        targeted(
            "confirm65_leader50_fw15_pb35_risk12_rr10",
            derived_confirm=65,
            min_hot_topic_score=65,
            min_leader_strength_score=50,
            min_first_wave_return_10d=0.10,
            min_first_wave_return_20d=0.15,
            pullback_min_pct=0.05,
            pullback_max_pct=0.35,
            max_risk_ratio=0.12,
            min_reward_risk_ratio=1.0,
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Strategy4 snapshot backtest experiments.")
    parser.add_argument("--db", default="data/cuphandle.db")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    results = generate_strategy4_optimization_report(
        db_path=args.db,
        start_date=args.start,
        end_date=args.end,
        base_config={"strategy4": {}},
        experiment_grid=_default_experiments(),
        report_path=args.report,
    )
    print(json.dumps({name: asdict(result.summary) for name, result in results.items()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

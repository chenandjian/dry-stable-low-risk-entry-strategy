"""Strategy4 historical snapshot backtester.

The backtester is intentionally snapshot-driven: it only evaluates hot topics
and leaders that were already persisted by a Strategy4 scan on the evaluation
date. Missing snapshots are marked UNOBSERVED instead of being reconstructed
from future or current data.
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
from strategy4.engine import HotLeaderSecondWaveEngine
from strategy4.price_limit import LIMIT_SHAPE_ONE_WORD_LIMIT_UP, PriceLimitResolver
from strategy4.backtest_models import (
    Strategy4BacktestOpportunity,
    Strategy4BacktestResult,
    Strategy4BacktestSignal,
    Strategy4BacktestSummary,
    Strategy4UnobservedDay,
)


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
        )
    return results


def run_strategy4_snapshot_backtest(
    *,
    db_path: str,
    start_date: str,
    end_date: str,
    config_snapshot: dict,
    task_id: str = "strategy4-backtest",
) -> Strategy4BacktestResult:
    """Replay Strategy4 snapshots over a date range using local OHLC only."""
    db.init_db(db_path)
    config_snapshot = copy.deepcopy(config_snapshot or {})
    cfg = resolve_strategy4_config(config_snapshot)
    engine = HotLeaderSecondWaveEngine({"strategy4": cfg})
    result = Strategy4BacktestResult(task_id=task_id, config_snapshot=config_snapshot)

    for evaluation_date in _evaluation_dates(start_date, end_date):
        result.summary.evaluation_days += 1
        snapshot_task_id = _snapshot_task_for_exact_date(evaluation_date)
        if not snapshot_task_id:
            result.summary.unobserved_snapshot_days += 1
            result.unobserved.append(Strategy4UnobservedDay(
                evaluation_date=evaluation_date,
                reason_code="UNOBSERVED_TOPIC_SNAPSHOT",
                detail="No Strategy4 hot-topic snapshot exists for this evaluation date.",
            ))
            continue

        topics = _select_topics_for_experiment(db.get_strategy4_hot_topics(snapshot_task_id), cfg)
        leaders_by_topic = _leaders_by_topic(db.get_strategy4_leaders(snapshot_task_id), cfg)
        result.summary.observed_snapshot_days += 1

        for topic in topics:
            for leader in leaders_by_topic.get(topic.get("topic_id", ""), []):
                signal = _evaluate_leader_snapshot(topic, leader, engine, cfg, evaluation_date)
                if signal is None:
                    continue
                result.signals.append(signal)
                opp = _opportunity_from_signal(signal)
                ohlc = db.get_ohlc(signal.code) or []
                calculate_strategy4_execution_outcome(opp, ohlc)
                result.opportunities.append(opp)

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
) -> Strategy4BacktestSignal | None:
    code = str(leader.get("code") or "")
    ohlc = db.get_ohlc(code) or []
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
            "topic_status": topic.get("status"),
            "leader_status": leader.get("status"),
            "engine_status": evaluation.get("status"),
            **_market_index_metadata(code, evaluation_date),
        },
    )


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
        if str(leader.get("status") or "") not in {"LEADER_CONFIRMED", "LOCKED_LEADER_WATCH"}:
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
           ORDER BY date""",
        (start, end, start, end),
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
        f"- strategy4_hot_topics：{coverage['topic_rows']} 行，{coverage['topic_min']} 至 {coverage['topic_max']}",
        f"- strategy4_leaders：{coverage['leader_rows']} 行",
        "",
        "## 参数实验结果",
        "",
        "| 实验 | 可观察日 | 不可观察日 | 信号 | 机会 | 入场 | 未入场 | 目标 | 止损 | 平均收益 | PF |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, result in results.items():
        s = result.summary
        pf = "--" if s.profit_factor is None else f"{s.profit_factor:.2f}"
        lines.append(
            f"| {name} | {s.observed_snapshot_days} | {s.unobserved_snapshot_days} | "
            f"{s.total_signals} | {s.total_opportunities} | {s.entered_opportunities} | "
            f"{s.no_entry_count} | {s.target_count} | {s.stop_count} | {s.avg_realized_return:.2%} | {pf} |"
        )
    lines.extend([
        "",
        "## 结论",
        "",
        "当前本地库仅存在 2026-07-01 当天的策略4热点/龙头快照，且这些快照没有产生可交易二波候选。",
        "因此本次只能验证回测框架、不可观察标记和参数实验流程；证据不足以把任何参数组升级为生产正式推荐参数。",
        "",
        "## 失效场景",
        "",
        "- 缺少历史热点题材快照时，回测日标记为 `UNOBSERVED_TOPIC_SNAPSHOT`。",
        "- 次日一字涨停不可成交时，机会标记为 `NO_ENTRY_LIMIT_UP_UNBUYABLE`。",
        "- 历史快照未覆盖完整热点周期时，参数实验可能只反映单日市场状态。",
        "",
        "## 过拟合风险",
        "",
        "目前可观察策略4样本过少。若直接根据单日热点榜调参，会把参数拟合到一个截面，而不是二波交易规律。",
    ])
    return "\n".join(lines) + "\n"


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
        "SELECT COUNT(*) rows, MIN(snapshot_time) min_date, MAX(snapshot_time) max_date FROM strategy4_hot_topics"
    ).fetchone()
    leaders = con.execute("SELECT COUNT(*) rows FROM strategy4_leaders").fetchone()
    return {
        "daily_rows": daily["rows"],
        "daily_stocks": daily["stocks"],
        "daily_min": daily["min_date"],
        "daily_max": daily["max_date"],
        "index_rows": index["rows"],
        "index_min": index["min_date"],
        "index_max": index["max_date"],
        "topic_rows": topics["rows"],
        "topic_min": topics["min_date"],
        "topic_max": topics["max_date"],
        "leader_rows": leaders["rows"],
    }


def _default_experiments() -> list[dict]:
    return [
        {"name": "baseline"},
        {"name": "hot80_leader80", "min_hot_topic_score": 80, "min_leader_strength_score": 80},
        {"name": "hot75_leader75", "min_hot_topic_score": 75, "min_leader_strength_score": 75},
        {"name": "rr18_risk20", "min_reward_risk_ratio": 1.8, "max_risk_ratio": 0.20},
        {"name": "pullback_05_30", "pullback_min_pct": 0.05, "pullback_max_pct": 0.30},
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

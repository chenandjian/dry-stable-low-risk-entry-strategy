"""Orchestration for one frozen Strategy6 parameter set."""
from __future__ import annotations

from dataclasses import asdict

from strategy6.backtest.data import market_calendar_from_indexes
from strategy6.backtest.execution import simulate_frozen_trade
from strategy6.backtest.experiments import group_authoritative_path_metrics, group_brooks_structure_metrics
from strategy6.backtest.metrics import calculate_concentration, calculate_trade_metrics, group_trade_metrics
from strategy6.backtest.snapshot import (
    authoritative_tail_paths,
    is_trade_ready_snapshot,
    path_metadata,
    quality_score_band,
    rebuild_stock_signals,
)


def run_parameter_research(
    *,
    parameter_set_id: str,
    data_by_code: dict[str, dict],
    evaluation_dates: list[str],
    market_data_by_symbol: dict[str, list[dict]],
    backtest_config: dict,
    engine_factory,
    minimum_history: int,
    oos_start: str,
    signal_scope: str = "ALL",
) -> dict:
    if signal_scope not in {"ALL", "BROOKS_ONLY", "BROOKS_PATH"}:
        raise ValueError(f"unsupported Strategy6 backtest signal scope: {signal_scope}")
    allowed_dates = sorted(set(date for date in evaluation_dates if date < oos_start))
    market_dates = market_calendar_from_indexes(market_data_by_symbol)
    signals = []
    orders = []
    trades = []
    seen_setups: set[str] = set()
    for code in sorted(data_by_code):
        item = data_by_code[code]
        stock_rows = list(item.get("rows") or [])
        engine = engine_factory()
        stock_signals = rebuild_stock_signals(
            code=code,
            name=str(item.get("name") or ""),
            rows=stock_rows,
            evaluation_dates=allowed_dates,
            market_data_by_symbol=market_data_by_symbol,
            parameter_set_id=parameter_set_id,
            engine=engine,
            minimum_history=minimum_history,
        )
        for signal in stock_signals:
            metadata = path_metadata(signal.snapshot)
            signal_record = {
                **signal.snapshot,
                **metadata,
                "parameter_set_id": signal.parameter_set_id,
                "setup_id": signal.setup_id,
                "code": signal.code,
                "name": signal.name,
                "evaluation_date": signal.evaluation_date,
            }
            paths = authoritative_tail_paths(signal_record)
            if signal_scope == "BROOKS_ONLY" and paths != ["BROOKS"]:
                continue
            if signal_scope == "BROOKS_PATH" and "BROOKS" not in paths:
                continue
            signals.append(signal_record)
            if signal_scope in {"BROOKS_ONLY", "BROOKS_PATH"}:
                trade_ready = bool(signal.snapshot.get("brooks_trade_ready")) and is_trade_ready_snapshot(
                    signal.snapshot
                )
            else:
                trade_ready = is_trade_ready_snapshot(signal.snapshot)
            if not trade_ready:
                continue
            if signal.setup_id in seen_setups:
                continue
            seen_setups.add(signal.setup_id)
            outcome = simulate_frozen_trade(signal, stock_rows, market_dates, backtest_config)
            order_record = {
                "order_id": outcome.order.order_id,
                "parameter_set_id": parameter_set_id,
                "setup_id": signal.setup_id,
                "code": code,
                "signal_date": signal.evaluation_date,
                "tail_path": signal.tail_path,
                **metadata,
                "status": outcome.order.status,
                "fill_reason": outcome.order.fill_reason,
                "expire_date": outcome.order.expire_date,
                "audit_tags": outcome.audit_tags,
                "entry_archetype": signal.snapshot.get("entry_archetype", ""),
            }
            orders.append(order_record)
            if outcome.trade is None:
                continue
            trade_record = asdict(outcome.trade)
            trade_record.update({
                "parameter_set_id": parameter_set_id,
                "setup_id": signal.setup_id,
                "tail_path": signal.tail_path,
                **metadata,
                "candidate_type": signal.candidate_type,
                "pattern_type": signal.snapshot.get("pattern_type", "UNKNOWN"),
                "market_status": signal.snapshot.get("market_status", "UNKNOWN"),
                "total_score": signal.snapshot.get("total_score", 0),
                "box_status": signal.snapshot.get("box_status", ""),
                "box_quality_tag": signal.snapshot.get("box_quality_tag", ""),
                "compact_kline_pass": bool(signal.snapshot.get("compact_kline_pass")),
                "net_profit": round(outcome.trade.net_return * outcome.trade.entry_price * 100, 6),
                "stop_loss_price": signal.snapshot.get("stop_loss_price", 0),
                "entry_archetype": signal.snapshot.get("entry_archetype", ""),
                "setup_quality_score": signal.snapshot.get("setup_quality_score", 0),
                "support_reaction_score": signal.snapshot.get("support_reaction_score", 0),
                "start_event_quality_score": signal.snapshot.get("start_event_quality_score", 0),
                "path_evidence_score": signal.snapshot.get("path_evidence_score", 0),
                "score_model_version": signal.snapshot.get("score_model_version", ""),
                "setup_quality_band": quality_score_band(signal.snapshot.get("setup_quality_score", 0)),
                "support_reaction_band": quality_score_band(signal.snapshot.get("support_reaction_score", 0)),
                "start_quality_band": quality_score_band(signal.snapshot.get("start_event_quality_score", 0)),
                "path_evidence_band": quality_score_band(signal.snapshot.get("path_evidence_score", 0)),
            })
            trades.append(trade_record)
    closed_trades = [item for item in trades if item.get("exit_date")]
    metrics = calculate_trade_metrics(closed_trades)
    metrics["unfilled_rate"] = (
        sum(item["status"] != "FILLED" for item in orders) / len(orders) if orders else 0.0
    )
    return {
        "parameter_set_id": parameter_set_id,
        "signals": sorted(signals, key=lambda item: (item.get("evaluation_date", ""), item.get("code", ""))),
        "orders": sorted(orders, key=lambda item: (item["signal_date"], item["code"])),
        "trades": sorted(trades, key=lambda item: (item.get("entry_date", ""), item["code"])),
        "summary": metrics,
        "path_metrics": group_trade_metrics(closed_trades, "tail_path"),
        "authoritative_path_metrics": group_authoritative_path_metrics(closed_trades),
        "tail_primary_path_metrics": group_trade_metrics(closed_trades, "tail_primary_path"),
        "tail_path_summary_metrics": group_trade_metrics(closed_trades, "tail_path_summary"),
        "brooks_status_metrics": group_trade_metrics(closed_trades, "brooks_status"),
        "brooks_structure_metrics": group_brooks_structure_metrics(closed_trades),
        "entry_archetype_metrics": group_trade_metrics(closed_trades, "entry_archetype"),
        "setup_quality_metrics": group_trade_metrics(closed_trades, "setup_quality_band"),
        "support_reaction_metrics": group_trade_metrics(closed_trades, "support_reaction_band"),
        "start_quality_metrics": group_trade_metrics(closed_trades, "start_quality_band"),
        "path_evidence_metrics": group_trade_metrics(closed_trades, "path_evidence_band"),
        "concentration": calculate_concentration(closed_trades),
        "oos_status": "OOS_LOCKED",
    }

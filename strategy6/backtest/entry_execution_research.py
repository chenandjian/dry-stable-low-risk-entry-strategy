"""Frozen-signal research for event selection and entry-archetype execution."""
from __future__ import annotations

import copy
from collections import Counter
from dataclasses import asdict

from strategy6.backtest.execution import simulate_frozen_trade
from strategy6.backtest.data import slice_visible_rows
from strategy6.backtest.metrics import calculate_trade_metrics
from strategy6.backtest.models import BacktestSignal
from strategy6.backtest.snapshot import (
    annotate_candidate_events,
    is_trade_ready_snapshot,
    signal_selection_key,
)


_TRIALS = (
    ("S6_EXEC_E0_LEGACY", "LEGACY_SETUP_ID", "FROZEN_TRADE_PLAN"),
    ("S6_EXEC_E1_FIRST_EVENT", "FIRST_EVENT_PER_START", "FROZEN_TRADE_PLAN"),
    ("S6_EXEC_E2_ARCHETYPE", "LEGACY_SETUP_ID", "ARCHETYPE_TRIGGERED"),
    ("S6_EXEC_E3_COMBINED", "FIRST_EVENT_PER_START", "ARCHETYPE_TRIGGERED"),
)


def rebuild_frozen_entry_archetypes(
    signals: list[BacktestSignal],
    *,
    stock_rows_by_code: dict[str, list[dict]],
    market_data_by_symbol: dict[str, list[dict]],
    engine,
    minimum_history: int = 500,
) -> dict:
    """Enrich old frozen plans with as-of entry identity, never future prices or a new plan."""
    rebuilt_signals = []
    failed = []
    for signal in signals:
        visible_rows = slice_visible_rows(stock_rows_by_code.get(signal.code) or [], signal.evaluation_date)
        if (
            len(visible_rows) < minimum_history
            or not visible_rows
            or str(visible_rows[-1].get("date") or "") != signal.evaluation_date
        ):
            failed.append({
                "code": signal.code,
                "evaluation_date": signal.evaluation_date,
                "reason": "INSUFFICIENT_OR_MISSING_SIGNAL_DATE_HISTORY",
            })
            continue
        visible_market = {
            symbol: slice_visible_rows(rows, signal.evaluation_date)
            for symbol, rows in market_data_by_symbol.items()
        }
        try:
            rebuilt = engine.evaluate_at(
                visible_rows,
                code=signal.code,
                name=signal.name,
                trading_days_override=len(visible_rows),
                market_data_by_symbol=visible_market,
            ).to_candidate_dict()
        except Exception as exc:
            failed.append({
                "code": signal.code,
                "evaluation_date": signal.evaluation_date,
                "reason": f"EVALUATION_FAILED: {exc}",
            })
            continue
        archetype = str(rebuilt.get("entry_archetype") or "")
        if not archetype:
            failed.append({
                "code": signal.code,
                "evaluation_date": signal.evaluation_date,
                "reason": "ENTRY_ARCHETYPE_NOT_REBUILT",
            })
            continue
        snapshot = dict(signal.snapshot)
        snapshot.update({
            "entry_archetype": archetype,
            "brooks_trigger_price": rebuilt.get("brooks_trigger_price"),
            "decision_profile": rebuilt.get("decision_profile") or "legacy_unspecified",
        })
        rebuilt_signals.append(BacktestSignal(
            parameter_set_id=signal.parameter_set_id,
            code=signal.code,
            name=signal.name,
            evaluation_date=signal.evaluation_date,
            setup_id=signal.setup_id,
            tail_path=signal.tail_path,
            candidate_type=signal.candidate_type,
            snapshot=snapshot,
        ))
    return {"signals": rebuilt_signals, "failed": failed}


def evaluate_entry_execution_trials(
    signals: list[BacktestSignal],
    *,
    load_rows,
    market_dates: list[str],
    base_config: dict,
    train_end: str,
    validation_end: str,
) -> list[dict]:
    annotated = annotate_candidate_events(list(signals))
    results = []
    for experiment_id, selection_mode, entry_mode in _TRIALS:
        config = copy.deepcopy(base_config)
        config["signal_selection_mode"] = selection_mode
        config["execution"]["entry_mode"] = entry_mode
        result = _replay_trial(
            annotated,
            load_rows=load_rows,
            market_dates=market_dates,
            config=config,
            validation_end=validation_end,
        )
        train = [trade for trade in result["closed_trades"] if trade["signal_date"] <= train_end]
        validation = [
            trade for trade in result["closed_trades"]
            if train_end < trade["signal_date"] <= validation_end
        ]
        train_metrics = calculate_trade_metrics(train)
        validation_metrics = calculate_trade_metrics(validation)
        results.append({
            "experiment_id": experiment_id,
            "signal_selection_mode": selection_mode,
            "entry_mode": entry_mode,
            **result,
            "train_metrics": train_metrics,
            "validation_metrics": validation_metrics,
            "gate": evaluate_initial_gate(train_metrics, validation_metrics),
        })
    return results


def evaluate_initial_gate(train_metrics: dict, validation_metrics: dict) -> dict:
    reasons = []
    for label, metrics in (("TRAIN", train_metrics), ("VALIDATION", validation_metrics)):
        if float(metrics.get("expectancy_r") or 0) <= 0:
            reasons.append(f"{label}_EXPECTANCY_NOT_POSITIVE")
        if float(metrics.get("profit_factor") or 0) < 1.20:
            reasons.append(f"{label}_PF_LT_1_20")
        if _win_loss_ratio(metrics) < 2.5:
            reasons.append(f"{label}_WIN_LOSS_R_LT_2_5")
    if int(validation_metrics.get("trades") or 0) < 30:
        reasons.append("VALIDATION_TRADES_LT_30")
    return {"passed": not reasons, "reasons": reasons}


def _replay_trial(
    signals: list[BacktestSignal],
    *,
    load_rows,
    market_dates: list[str],
    config: dict,
    validation_end: str,
) -> dict:
    orders = []
    trades = []
    seen: set[str] = set()
    selection_mode = str(config["signal_selection_mode"])
    entry_mode = str(config["execution"]["entry_mode"])
    rows_by_code: dict[str, list[dict]] = {}
    for signal in sorted(signals, key=lambda item: (item.evaluation_date, item.code)):
        if signal.evaluation_date > validation_end or not is_trade_ready_snapshot(signal.snapshot):
            continue
        selection_key = signal_selection_key(signal, selection_mode)
        if selection_key in seen:
            continue
        seen.add(selection_key)
        if signal.code not in rows_by_code:
            rows_by_code[signal.code] = list(load_rows(signal.code) or [])
        outcome = simulate_frozen_trade(signal, rows_by_code[signal.code], market_dates, config)
        event_fields = {
            "candidate_event_id": signal.snapshot.get("candidate_event_id", signal.setup_id),
            "candidate_event_sequence": signal.snapshot.get("candidate_event_sequence", 0),
            "first_candidate_date": signal.snapshot.get("first_candidate_date", ""),
            "first_executable_date": signal.snapshot.get("first_executable_date", ""),
            "entry_archetype": signal.snapshot.get("entry_archetype", ""),
            "signal_selection_mode": selection_mode,
            "entry_mode": entry_mode,
        }
        orders.append({
            "order_id": outcome.order.order_id,
            "setup_id": signal.setup_id,
            "code": signal.code,
            "name": signal.name,
            "signal_date": signal.evaluation_date,
            "status": outcome.order.status,
            "fill_reason": outcome.order.fill_reason,
            "expire_date": outcome.order.expire_date,
            "audit_tags": list(outcome.audit_tags),
            **event_fields,
        })
        if outcome.trade is None:
            continue
        trade = asdict(outcome.trade)
        trade.update({
            "setup_id": signal.setup_id,
            "name": signal.name,
            "net_profit": round(outcome.trade.net_return * outcome.trade.entry_price * 100, 6),
            **event_fields,
        })
        trades.append(trade)
    closed_trades = [trade for trade in trades if trade.get("exit_date")]
    return {
        "signals": [
            {
                "code": signal.code,
                "name": signal.name,
                "evaluation_date": signal.evaluation_date,
                "setup_id": signal.setup_id,
                "candidate_type": signal.candidate_type,
                **{
                    key: signal.snapshot.get(key)
                    for key in (
                        "candidate_event_id", "candidate_event_sequence", "first_candidate_date",
                        "first_executable_date", "is_first_candidate_event", "is_first_executable_event",
                        "entry_archetype",
                    )
                },
            }
            for signal in signals
            if signal.evaluation_date <= validation_end
        ],
        "orders": orders,
        "trades": trades,
        "closed_trades": closed_trades,
        "orders_count": len(orders),
        "filled_count": len(trades),
        "closed_count": len(closed_trades),
        "unfilled_rate": (len(orders) - len(trades)) / len(orders) if orders else 0.0,
        "fill_reason_counts": dict(Counter(order["fill_reason"] for order in orders)),
        "full_metrics": calculate_trade_metrics(closed_trades),
    }


def _win_loss_ratio(metrics: dict) -> float:
    average_loss = float(metrics.get("avg_loss_r") or 0)
    return float(metrics.get("avg_win_r") or 0) / average_loss if average_loss > 0 else 0.0

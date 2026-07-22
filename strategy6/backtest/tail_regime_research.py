"""Historical As-Of comparison for fixed and shadow tail-regime evidence."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, replace
import math

from strategy6.backtest.data import market_calendar_from_indexes, slice_visible_rows
from strategy6.backtest.execution import simulate_frozen_trade
from strategy6.backtest.index_history import validate_index_history_data
from strategy6.backtest.metrics import calculate_trade_metrics, group_trade_metrics
from strategy6.backtest.models import BacktestSignal
from strategy6.backtest.snapshot import build_setup_id, is_trade_ready_snapshot
from strategy6.backtest.stress import evaluate_stress_acceptance, replay_stress_scenarios
from strategy6.box_tail import combine_tail_paths
from strategy6.filters import classify_candidate
from strategy6.scorer import score_strategy6


TAIL_REGIME_GROUPS = ("BOTH", "FIXED_ONLY", "REGIME_ONLY", "NEITHER")
LOCKED_OOS_START = "2026-01-01"
RESEARCH_START = "2023-01-01"
REGIME_SUBSTITUTABLE_REJECTS = {
    "TAIL_VOLUME_BASE_INSUFFICIENT",
    "TAIL_CLOSE_RANGE_GT_8PCT",
    "TAIL_VOLUME_NOT_DRY",
}


def classify_tail_regime_group(snapshot: dict) -> str:
    fixed_pass = bool(snapshot.get("original_tail_pass"))
    regime_confirmed = snapshot.get("tail_regime_status") == "CONFIRMED"
    if fixed_pass and regime_confirmed:
        return "BOTH"
    if fixed_pass:
        return "FIXED_ONLY"
    if regime_confirmed:
        return "REGIME_ONLY"
    return "NEITHER"


def replay_tail_regime_labels(
    *,
    data_by_code: dict[str, dict],
    evaluation_dates: list[str],
    market_data_by_symbol: dict[str, list[dict]],
    reference_market_dates: list[str],
    engine_factory,
    minimum_history: int,
    oos_start: str = "2026-01-01",
) -> dict:
    _require_locked_oos_start(oos_start)
    index_history = _validate_research_indexes(
        market_data_by_symbol,
        evaluation_dates,
        reference_market_dates,
        oos_start,
    )
    if index_history.status != "READY":
        return _blocked_index_result(index_history, evaluation_dates, oos_start)
    market_data_by_symbol = index_history.data_by_symbol
    daily_labels = [
        item["label"]
        for item in _iter_as_of_evaluations(
            data_by_code=data_by_code,
            evaluation_dates=evaluation_dates,
            market_data_by_symbol=market_data_by_symbol,
            engine_factory=engine_factory,
            minimum_history=minimum_history,
            oos_start=oos_start,
        )
    ]
    locked_dates = {date for date in evaluation_dates if date >= oos_start}
    pre_research_dates = {date for date in evaluation_dates if date < RESEARCH_START}
    return {
        "status": "COMPLETED",
        "daily_labels": daily_labels,
        "group_counts": dict(Counter(item["group"] for item in daily_labels)),
        "oos_status": "OOS_LOCKED",
        "oos_start": oos_start,
        "locked_date_count": len(locked_dates),
        "pre_research_date_count": len(pre_research_dates),
    }


def run_tail_regime_research(
    *,
    parameter_set_id: str,
    data_by_code: dict[str, dict],
    evaluation_dates: list[str],
    market_data_by_symbol: dict[str, list[dict]],
    reference_market_dates: list[str],
    backtest_config: dict,
    engine_factory,
    minimum_history: int,
    oos_start: str = "2026-01-01",
    run_stress: bool = True,
) -> dict:
    """Replay labels and execute only eligible fixed or regime-hypothesis signals."""
    _require_locked_oos_start(oos_start)
    index_history = _validate_research_indexes(
        market_data_by_symbol,
        evaluation_dates,
        reference_market_dates,
        oos_start,
    )
    if index_history.status != "READY":
        return {
            **_blocked_index_result(index_history, evaluation_dates, oos_start),
            "parameter_set_id": parameter_set_id,
            "signals": [],
            "orders": [],
            "trades": [],
            "summary": calculate_trade_metrics([]),
            "group_metrics": {},
            "train_metrics": calculate_trade_metrics([]),
            "validation_metrics": calculate_trade_metrics([]),
            "stress_tests": {},
            "gate": {
                "status": "BLOCKED_INDEX_HISTORY",
                "reasons": ["BLOCKED_INDEX_HISTORY"],
                "stress_status": "NOT_RUN",
            },
        }
    market_data_by_symbol = index_history.data_by_symbol
    market_dates = market_calendar_from_indexes(market_data_by_symbol)
    execution_market_dates = [date for date in market_dates if date < oos_start]
    daily_labels: list[dict] = []
    signals: list[dict] = []
    orders: list[dict] = []
    trades: list[dict] = []
    seen_setups: set[tuple[str, str]] = set()
    frozen_regime_signals: list[BacktestSignal] = []

    for item in _iter_as_of_evaluations(
        data_by_code=data_by_code,
        evaluation_dates=evaluation_dates,
        market_data_by_symbol=market_data_by_symbol,
        engine_factory=engine_factory,
        minimum_history=minimum_history,
        oos_start=oos_start,
    ):
        label = item["label"]
        daily_labels.append(label)
        evaluation = item["evaluation"]
        engine = item["engine"]
        if engine.config.get("decision_profile") != "formal_original":
            raise ValueError("tail regime research requires decision_profile=formal_original")
        snapshot = item["snapshot"]
        group = label["group"]
        signal_snapshot = None
        signal_path = ""
        if group in {"BOTH", "FIXED_ONLY"} and snapshot.get("candidate_type") != "REJECTED":
            signal_snapshot = snapshot
            signal_path = "ORIGINAL"
        elif group == "REGIME_ONLY":
            signal_snapshot = _build_regime_only_hypothesis(evaluation, engine.config)
            signal_path = "REGIME"
        if not signal_snapshot:
            continue
        if not is_trade_ready_snapshot(signal_snapshot):
            continue

        setup_id = build_setup_id(signal_snapshot)
        setup_key = (str(snapshot.get("code") or ""), setup_id)
        if setup_key in seen_setups:
            continue
        seen_setups.add(setup_key)
        signal = BacktestSignal(
            parameter_set_id=parameter_set_id,
            code=str(snapshot.get("code") or ""),
            name=str(snapshot.get("name") or ""),
            evaluation_date=str(snapshot.get("evaluation_date") or ""),
            setup_id=setup_id,
            tail_path=signal_path,
            candidate_type=str(signal_snapshot.get("candidate_type") or "REJECTED"),
            snapshot=signal_snapshot,
        )
        signal_record = {
            **signal_snapshot,
            "parameter_set_id": parameter_set_id,
            "setup_id": setup_id,
            "tail_regime_group": group,
            "research_tail_path": signal_path,
        }
        signals.append(signal_record)
        if signal_path == "REGIME":
            frozen_regime_signals.append(signal)
        outcome = simulate_frozen_trade(
            signal,
            _rows_before_oos(item["stock_rows"], oos_start),
            execution_market_dates,
            backtest_config,
        )
        orders.append({
            "order_id": outcome.order.order_id,
            "code": signal.code,
            "signal_date": signal.evaluation_date,
            "setup_id": setup_id,
            "tail_regime_group": group,
            "research_tail_path": signal_path,
            "status": outcome.order.status,
            "fill_reason": outcome.order.fill_reason,
            "expire_date": outcome.order.expire_date,
            "audit_tags": outcome.audit_tags,
        })
        if outcome.trade is not None:
            trade = asdict(outcome.trade)
            trade.update({
                "setup_id": setup_id,
                "tail_regime_group": group,
                "research_tail_path": signal_path,
                "net_profit": round(outcome.trade.net_return * outcome.trade.entry_price * 100, 6),
            })
            trades.append(trade)

    closed_trades = [trade for trade in trades if trade.get("exit_date")]
    train_trades, validation_trades, cross_period_trades = _partition_closed_trades(
        closed_trades,
    )
    stress_tests = {}
    if run_stress and frozen_regime_signals:
        stress_tests = _filter_stress_results_for_research_periods(
            replay_stress_scenarios(
                frozen_regime_signals,
                load_rows=lambda code: _rows_before_oos(
                    list((data_by_code.get(code) or {}).get("rows") or []),
                    oos_start,
                ),
                market_dates=execution_market_dates,
                base_config=backtest_config,
            ),
        )
    return {
        "status": "COMPLETED",
        "parameter_set_id": parameter_set_id,
        "daily_labels": sorted(daily_labels, key=lambda row: (row["evaluation_date"], row["code"])),
        "group_counts": dict(Counter(item["group"] for item in daily_labels)),
        "signals": sorted(signals, key=lambda row: (row["evaluation_date"], row["code"])),
        "orders": sorted(orders, key=lambda row: (row["signal_date"], row["code"])),
        "trades": sorted(trades, key=lambda row: (row.get("entry_date", ""), row["code"])),
        "summary": calculate_trade_metrics(closed_trades),
        "group_metrics": group_trade_metrics(closed_trades, "tail_regime_group"),
        "train_metrics": calculate_trade_metrics(train_trades),
        "validation_metrics": calculate_trade_metrics(validation_trades),
        "cross_period_trades": sorted(
            cross_period_trades,
            key=lambda row: (row.get("signal_date", ""), row.get("code", "")),
        ),
        "stress_tests": stress_tests,
        "gate": _research_gate(
            train_trades,
            validation_trades,
            stress_results=stress_tests,
        ),
        "oos_status": "OOS_LOCKED",
        "oos_start": oos_start,
        "locked_date_count": len({date for date in evaluation_dates if date >= oos_start}),
        "pre_research_date_count": len({date for date in evaluation_dates if date < RESEARCH_START}),
    }


def _iter_as_of_evaluations(
    *,
    data_by_code: dict[str, dict],
    evaluation_dates: list[str],
    market_data_by_symbol: dict[str, list[dict]],
    engine_factory,
    minimum_history: int,
    oos_start: str,
):
    allowed_dates = sorted({
        date for date in evaluation_dates
        if RESEARCH_START <= date < oos_start
    })
    for code in sorted(data_by_code):
        stock = data_by_code[code]
        stock_rows = list(stock.get("rows") or [])
        engine = engine_factory()
        engine_config = getattr(engine, "config", None)
        if (
            isinstance(engine_config, dict)
            and engine_config.get("decision_profile") != "formal_original"
        ):
            raise ValueError("tail regime research requires decision_profile=formal_original")
        for evaluation_date in allowed_dates:
            visible_rows = slice_visible_rows(stock_rows, evaluation_date)
            if len(visible_rows) < minimum_history:
                continue
            if str(visible_rows[-1].get("date") or "") != evaluation_date:
                continue
            visible_market = {
                symbol: slice_visible_rows(rows, evaluation_date)
                for symbol, rows in market_data_by_symbol.items()
            }
            evaluation = engine.evaluate_at(
                visible_rows,
                code=code,
                name=str(stock.get("name") or ""),
                trading_days_override=len(visible_rows),
                market_data_by_symbol=visible_market,
            )
            snapshot = evaluation.to_candidate_dict()
            group = classify_tail_regime_group(snapshot)
            yield {
                "engine": engine,
                "evaluation": evaluation,
                "snapshot": snapshot,
                "stock_rows": stock_rows,
                "label": {
                    "code": code,
                    "name": str(stock.get("name") or ""),
                    "evaluation_date": evaluation_date,
                    "group": group,
                    "fixed_pass": bool(snapshot.get("original_tail_pass")),
                    "fixed_reasons": list(getattr(getattr(evaluation, "dry_tail", None), "rejects", []) or snapshot.get("reject_reasons") or []),
                    "regime_status": str(snapshot.get("tail_regime_status") or ""),
                    "regime_start_date": str(snapshot.get("tail_regime_start_date") or ""),
                    "regime_days": int(snapshot.get("tail_regime_days") or 0),
                    "regime_delta_bic": float(snapshot.get("tail_regime_delta_bic") or 0),
                    "regime_reasons": list(snapshot.get("tail_regime_reasons") or []),
                    "regime_risks": list(snapshot.get("tail_regime_risks") or []),
                },
            }


def _build_regime_only_hypothesis(evaluation, config: dict) -> dict | None:
    """Replace only ORIGINAL tail pass and rerun existing score/classification functions."""
    required = ("dry_tail", "indicators", "start", "phase", "pattern", "support", "trade_plan", "score")
    if any(not hasattr(evaluation, field) for field in required):
        return None
    if evaluation.tail_regime.status != "CONFIRMED" or evaluation.dry_tail.dry_tail_pass:
        return None
    remaining_tail_rejects = _remaining_rejects_after_regime(
        evaluation.dry_tail.rejects,
        evaluation.dry_tail.rejects,
    )
    hypothetical_tail = replace(
        evaluation.dry_tail,
        dry_tail_pass=not remaining_tail_rejects,
        rejects=remaining_tail_rejects,
    )
    hypothetical_score = score_strategy6(
        evaluation.indicators,
        evaluation.start,
        evaluation.phase,
        evaluation.pattern,
        evaluation.support,
        hypothetical_tail,
        evaluation.trade_plan,
        config,
        box_tail=evaluation.box_tail,
        brooks_tail=evaluation.brooks_tail,
        setup_quality=evaluation.setup_quality,
    )
    remaining_rejects = _remaining_rejects_after_regime(
        evaluation.reject_reasons,
        evaluation.dry_tail.rejects,
    )
    candidate_type, classification, lifecycle_status, suggestion = classify_candidate(
        evaluation.indicators,
        evaluation.start,
        evaluation.phase,
        evaluation.pattern,
        evaluation.support,
        hypothetical_tail,
        evaluation.trade_plan,
        hypothetical_score,
        remaining_rejects,
        config,
        box_tail=evaluation.box_tail,
        brooks_tail=evaluation.brooks_tail,
    )
    if candidate_type == "REJECTED":
        return None
    hypothetical = replace(
        evaluation,
        dry_tail=hypothetical_tail,
        tail_paths=combine_tail_paths(hypothetical_tail, evaluation.box_tail, evaluation.brooks_tail),
        score=hypothetical_score,
        candidate_type=candidate_type,
        classification=classification,
        lifecycle_status=lifecycle_status,
        reject_reasons=remaining_rejects,
        suggestion=suggestion,
    )
    snapshot = hypothetical.to_candidate_dict()
    snapshot.update({
        "actual_original_tail_pass": False,
        "tail_regime_hypothesis": True,
        "research_tail_path": "REGIME",
    })
    return snapshot


def _remaining_rejects_after_regime(
    reject_reasons: list[str],
    dry_tail_rejects: list[str],
) -> list[str]:
    substitutable = set(dry_tail_rejects) & REGIME_SUBSTITUTABLE_REJECTS
    return [reason for reason in reject_reasons if reason not in substitutable]


def _research_gate(
    train_trades: list[dict],
    validation_trades: list[dict],
    *,
    stress_results: dict | None = None,
) -> dict:
    regime_train = [
        trade for trade in train_trades
        if trade.get("tail_regime_group") == "REGIME_ONLY"
    ]
    regime_validation = [
        trade for trade in validation_trades
        if trade.get("tail_regime_group") == "REGIME_ONLY"
    ]
    train = calculate_trade_metrics(regime_train)
    validation = calculate_trade_metrics(regime_validation)
    reasons: list[str] = []
    regime_closed = sum(
        trade.get("tail_regime_group") == "REGIME_ONLY"
        for trade in regime_train + regime_validation
    )
    if regime_closed < 30:
        reasons.append("REGIME_ONLY_CLOSED_TRADES_LT_30")
    for period, metrics in (("TRAIN", train), ("VALIDATION", validation)):
        if metrics["expectancy_r"] <= 0:
            reasons.append(f"{period}_EXPECTANCY_NOT_POSITIVE")
        if metrics["profit_factor"] < 1.20:
            reasons.append(f"{period}_PROFIT_FACTOR_LT_1_20")
        ratio = (
            metrics["avg_win_r"] / metrics["avg_loss_r"]
            if metrics["avg_loss_r"] > 0
            else math.inf if metrics["avg_win_r"] > 0
            else 0.0
        )
        if ratio < 2.5:
            reasons.append(f"{period}_AVG_WIN_LOSS_LT_2_5")
    required_stress = ("HIGH_COST", "LOW_FILL", "ONE_DAY_DELAY")
    stress_complete = all(
        (stress_results or {}).get(name, {}).get("status") == "COMPLETED"
        for name in required_stress
    )
    stress_acceptance = (
        evaluate_stress_acceptance(stress_results or {})
        if stress_complete else {"passed": False, "checks": {}}
    )
    if not stress_complete:
        reasons.append("STRESS_REPLAYS_REQUIRED")
    elif not stress_acceptance["passed"]:
        reasons.append("STRESS_ACCEPTANCE_FAILED")
    return {
        "status": "PASS" if not reasons else "CONTINUE_SHADOW",
        "regime_only_closed_trades": regime_closed,
        "reasons": reasons,
        "stress_status": (
            "PASS" if stress_complete and stress_acceptance["passed"]
            else "FAILED" if stress_complete
            else "REQUIRES_REPLAY"
        ),
        "stress_checks": stress_acceptance["checks"],
    }


def _require_locked_oos_start(oos_start: str) -> None:
    if oos_start != LOCKED_OOS_START:
        raise ValueError(f"tail regime research OOS lock must remain {LOCKED_OOS_START}")


def _rows_before_oos(rows: list[dict], oos_start: str) -> list[dict]:
    return [row for row in rows if str(row.get("date") or "") < oos_start]


def _validate_research_indexes(
    market_data_by_symbol: dict[str, list[dict]],
    evaluation_dates: list[str],
    reference_market_dates: list[str],
    oos_start: str,
):
    if not reference_market_dates:
        raise ValueError("tail regime research requires a real reference market calendar")
    requested_dates = sorted({
        date for date in evaluation_dates
        if RESEARCH_START <= date < oos_start
    })
    reference_dates = sorted({
        date for date in reference_market_dates
        if RESEARCH_START <= date < oos_start
    })
    missing_from_reference = sorted(set(requested_dates) - set(reference_dates))
    if missing_from_reference:
        raise ValueError(
            "tail regime research evaluation dates must exist in the reference market calendar"
        )
    required_dates = sorted(set(requested_dates) | set(reference_dates))
    visible_dates = sorted({
        str(row.get("date") or "")
        for rows in market_data_by_symbol.values()
        for row in rows
        if row.get("date") and str(row.get("date")) < oos_start
    })
    if required_dates:
        start_date = required_dates[0]
        end_date = required_dates[-1]
    else:
        start_date = visible_dates[0] if visible_dates else ""
        end_date = visible_dates[-1] if visible_dates else ""
    return validate_index_history_data(
        market_data_by_symbol,
        start_date=start_date,
        end_date=end_date,
        reference_dates=reference_dates,
    )


def _partition_closed_trades(
    closed_trades: list[dict],
) -> tuple[list[dict], list[dict], list[dict]]:
    train: list[dict] = []
    validation: list[dict] = []
    cross_period: list[dict] = []
    for trade in closed_trades:
        signal_date = str(trade.get("signal_date") or "")
        exit_date = str(trade.get("exit_date") or "")
        if RESEARCH_START <= signal_date <= exit_date <= "2024-12-31":
            train.append(trade)
        elif "2025-01-01" <= signal_date <= exit_date <= "2025-12-31":
            validation.append(trade)
        else:
            cross_period.append(trade)
    return train, validation, cross_period


def _filter_stress_results_for_research_periods(results: dict) -> dict:
    filtered: dict = {}
    for name, scenario in results.items():
        trades = list(scenario.get("trades") or [])
        train, validation, cross_period = _partition_closed_trades(
            [trade for trade in trades if trade.get("exit_date")],
        )
        eligible = train + validation
        filtered[name] = {
            **scenario,
            "trades": eligible,
            "metrics": calculate_trade_metrics(eligible),
            "cross_period_trade_count": len(cross_period),
        }
    return filtered


def _blocked_index_result(index_history, evaluation_dates: list[str], oos_start: str) -> dict:
    return {
        "status": "BLOCKED_INDEX_HISTORY",
        "daily_labels": [],
        "group_counts": {},
        "missing_index_symbols": list(index_history.missing_symbols),
        "index_coverage": index_history.coverage,
        "oos_status": "OOS_LOCKED",
        "oos_start": oos_start,
        "locked_date_count": len({date for date in evaluation_dates if date >= oos_start}),
        "pre_research_date_count": len({date for date in evaluation_dates if date < RESEARCH_START}),
    }

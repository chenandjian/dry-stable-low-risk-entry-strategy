"""Strategy1 trusted backtest task service."""

from __future__ import annotations

import datetime
import hashlib
import json

import scanner.db as db
from scanner.strategy1_backtest_experiments import apply_signal_experiment_filter
from scanner.strategy1_backtest_models import Strategy1BacktestSignal
from scanner.strategy1_backtester import (
    apply_strategy1_time_exit,
    calculate_strategy1_execution_outcome,
    merge_strategy1_signals,
)
from scanner.strategy1_backtester import run_strategy1_stock_backtest

STRATEGY1_BACKTEST_ENGINE_VERSION = "strategy1-backtest-v1"
STRATEGY1_STRATEGY_ENGINE_VERSION = "cuphandle-v1"


def calculate_strategy1_daily_ohlc_revision(task_id: str | None = None) -> str:
    """Calculate a deterministic local daily_ohlc revision id."""
    conn = db.get_conn()
    if task_id:
        row = conn.execute(
            "SELECT COUNT(*), MIN(o.date), MAX(o.date), COALESCE(SUM(o.volume),0) "
            "FROM daily_ohlc o "
            "JOIN strategy1_backtest_task_stocks s ON s.code=o.code "
            "WHERE s.task_id=?",
            (task_id,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*), MIN(date), MAX(date), COALESCE(SUM(volume),0) FROM daily_ohlc"
        ).fetchone()
    raw = "|".join(str(part or "") for part in row)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def run_strategy1_backtest_task(
    *,
    task_id: str,
    target_stocks: list[dict],
    config_snapshot: dict,
    payload_snapshot: dict,
    running_state: dict | None = None,
) -> None:
    """Run a Strategy1 local DB backtest task synchronously."""
    processed = 0
    failed = 0
    insufficient = 0
    raw_signals = 0
    opportunities = 0
    actual_start = ""
    actual_end = ""
    observation_end = ""

    try:
        for stock in target_stocks:
            code = stock["code"]
            name = stock.get("name", "")
            if running_state is not None:
                running_state["stats"] = {
                    **running_state.get("stats", {}),
                    "current_code": code,
                    "current_name": name,
                    "processed_stocks": processed,
                }

            rows = db.get_ohlc(code, max_rows=0) or []
            required_days = int((config_snapshot.get("data") or {}).get("backtest_window_days") or 250)
            if len(rows) < required_days:
                insufficient += 1
                db.replace_strategy1_stock_backtest_result(
                    task_id,
                    code,
                    name,
                    {
                        "status": "INSUFFICIENT_DATA",
                        "available_days": len(rows),
                        "required_days": required_days,
                        "earliest_date": rows[0]["date"] if rows else "",
                        "latest_date": rows[-1]["date"] if rows else "",
                        "error_code": "INSUFFICIENT_DATA",
                    },
                )
                processed += 1
                continue

            try:
                result = run_strategy1_stock_backtest(
                    code,
                    name,
                    rows,
                    config_snapshot,
                    payload_snapshot.get("startDate", ""),
                    payload_snapshot.get("endDate", ""),
                    experiment=payload_snapshot.get("experiment"),
                )
                result.update(
                    {
                        "available_days": len(rows),
                        "required_days": required_days,
                        "earliest_date": rows[0]["date"],
                        "latest_date": rows[-1]["date"],
                    }
                )
                db.replace_strategy1_stock_backtest_result(task_id, code, name, result)
                raw_signals += result.get("raw_signals_count", 0)
                opportunities += result.get("opportunities_count", 0)
                signal_dates = [sig.evaluation_date for sig in result.get("signals", [])]
                if signal_dates:
                    actual_start = min([actual_start] + signal_dates) if actual_start else min(signal_dates)
                    actual_end = max([actual_end] + signal_dates) if actual_end else max(signal_dates)
                observation_end = max(observation_end, rows[-1]["date"]) if observation_end else rows[-1]["date"]
            except Exception as exc:
                failed += 1
                db.replace_strategy1_stock_backtest_result(
                    task_id,
                    code,
                    name,
                    {"status": "FAILED", "error_code": "EVALUATION_ERROR", "error_detail": str(exc)},
                )
            processed += 1

        status = "completed" if failed == 0 else "completed_with_errors"
        experiment = payload_snapshot.get("experiment") or {}
        db.update_strategy1_backtest_task(
            task_id,
            status=status,
            credibility_status="EXPERIMENTAL" if experiment.get("enabled") else "RUNNING_UNVERIFIED",
            processed_stocks=processed,
            failed_stocks_count=failed,
            insufficient_stocks_count=insufficient,
            raw_signals_count=raw_signals,
            opportunities_count=opportunities,
            actual_evaluation_start_date=actual_start,
            actual_evaluation_end_date=actual_end,
            observation_data_end_date=observation_end,
            summary_json=json.dumps(db.build_strategy1_backtest_summary(task_id), ensure_ascii=False),
            finished_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        if experiment.get("enabled"):
            credibility = "EXPERIMENTAL"
        else:
            ok, errors = db.validate_strategy1_backtest_integrity(task_id)
            credibility = "TRUSTED_BASELINE" if ok else "INCOMPLETE"
            if errors:
                db.update_strategy1_backtest_task(task_id, error="; ".join(errors))
        db.update_strategy1_backtest_task(task_id, credibility_status=credibility)
    except Exception as exc:
        db.update_strategy1_backtest_task(
            task_id,
            status="failed",
            credibility_status="INCOMPLETE",
            error=str(exc),
            finished_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        raise


def run_strategy1_experiment_from_baseline(
    *,
    experiment_task_id: str,
    baseline_task_id: str,
    experiment_snapshot: dict,
) -> None:
    """Create a fast experiment task by filtering trusted baseline signals."""
    baseline = db.get_strategy1_backtest_task(baseline_task_id)
    if not baseline:
        raise ValueError(f"Baseline task not found: {baseline_task_id}")
    if baseline.get("credibility_status") != "TRUSTED_BASELINE":
        raise ValueError(f"Baseline task is not trusted: {baseline.get('credibility_status')}")

    config_snapshot = baseline.get("config_snapshot") or "{}"
    payload = {
        "startDate": baseline.get("requested_start_date", ""),
        "endDate": baseline.get("requested_end_date", ""),
        "codes": [code for code in (baseline.get("requested_codes") or "").split(",") if code],
        "maxStocks": baseline.get("max_stocks"),
        "baselineTaskId": baseline_task_id,
        "experiment": experiment_snapshot,
        "experiment_snapshot": experiment_snapshot,
    }
    existing = db.get_strategy1_backtest_task(experiment_task_id)
    if not existing:
        db.create_strategy1_backtest_task(experiment_task_id, payload, config_snapshot)

    db.update_strategy1_backtest_task(
        experiment_task_id,
        status="running",
        credibility_status="EXPERIMENTAL",
        baseline_task_id=baseline_task_id,
        requested_start_date=baseline.get("requested_start_date"),
        requested_end_date=baseline.get("requested_end_date"),
        requested_codes=baseline.get("requested_codes"),
        max_stocks=baseline.get("max_stocks"),
        total_stocks=baseline.get("total_stocks") or 0,
        processed_stocks=0,
        config_snapshot=config_snapshot,
        experiment_snapshot=json.dumps(experiment_snapshot, ensure_ascii=False),
        data_revision_id=baseline.get("data_revision_id"),
        data_revision_version=baseline.get("data_revision_version"),
        strategy_engine_version=baseline.get("strategy_engine_version"),
        backtest_engine_version=baseline.get("backtest_engine_version"),
        execution_model=experiment_snapshot.get("execution_model", baseline.get("execution_model") or "NEXT_OPEN"),
        error=None,
    )

    stock_rows = db.get_strategy1_backtest_task_stocks(baseline_task_id)
    processed = 0
    raw_signals_total = 0
    opportunities_total = 0
    for stock in stock_rows:
        code = stock["code"]
        name = stock.get("name") or ""
        signal_rows = db.get_strategy1_backtest_signals(baseline_task_id, code=code, limit=100000)
        signals = [_signal_from_row(row) for row in signal_rows]
        eval_results: dict[int, str] = {}
        experiment_signals: list[Strategy1BacktestSignal] = []
        for signal in signals:
            passed, reason = apply_signal_experiment_filter(signal, experiment_snapshot)
            experiment_signals.append(signal)
            eval_results[signal.evaluation_index] = "PASSED" if passed else reason or "EXPERIMENT_FILTERED"

        passed_signals = [signal for signal in experiment_signals if signal.experiment_passed]
        opportunities = merge_strategy1_signals(passed_signals, eval_results)
        ohlc_rows = db.get_ohlc(code, max_rows=0) or []
        date_to_index = {row["date"]: idx for idx, row in enumerate(ohlc_rows)}
        for opportunity in opportunities:
            calculate_strategy1_execution_outcome(opportunity, ohlc_rows, date_to_index)
            apply_strategy1_time_exit(opportunity, ohlc_rows, date_to_index, experiment_snapshot)

        db.replace_strategy1_stock_backtest_result(
            experiment_task_id,
            code,
            name,
            {
                "signals": experiment_signals,
                "opportunities": opportunities,
                "raw_signals_count": len(experiment_signals),
                "opportunities_count": len(opportunities),
                "evaluation_days": stock.get("evaluation_days") or 0,
                "filtered_days": len(experiment_signals) - len(passed_signals),
                "available_days": stock.get("available_days") or 0,
                "required_days": stock.get("required_days") or 0,
                "earliest_date": stock.get("earliest_date") or "",
                "latest_date": stock.get("latest_date") or "",
                "actual_start_date": stock.get("actual_start_date") or "",
                "actual_end_date": stock.get("actual_end_date") or "",
            },
        )
        processed += 1
        raw_signals_total += len(experiment_signals)
        opportunities_total += len(opportunities)

    summary = db.build_strategy1_backtest_summary(experiment_task_id)
    comparison = db.compare_strategy1_backtest_tasks(experiment_task_id, baseline_task_id)
    db.update_strategy1_backtest_task(
        experiment_task_id,
        status="completed",
        credibility_status="EXPERIMENTAL",
        processed_stocks=processed,
        failed_stocks_count=0,
        insufficient_stocks_count=baseline.get("insufficient_stocks_count") or 0,
        raw_signals_count=raw_signals_total,
        opportunities_count=opportunities_total,
        actual_evaluation_start_date=baseline.get("actual_evaluation_start_date"),
        actual_evaluation_end_date=baseline.get("actual_evaluation_end_date"),
        observation_data_end_date=baseline.get("observation_data_end_date"),
        summary_json=json.dumps(summary, ensure_ascii=False),
        comparison_summary_json=json.dumps(comparison, ensure_ascii=False),
        finished_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def _signal_from_row(row: dict) -> Strategy1BacktestSignal:
    snapshot = {}
    if row.get("evaluation_snapshot"):
        try:
            snapshot = json.loads(row["evaluation_snapshot"])
        except Exception:
            snapshot = {}
    return Strategy1BacktestSignal(
        code=row.get("code") or "",
        name=row.get("name") or "",
        evaluation_date=row.get("evaluation_date") or "",
        evaluation_index=int(row.get("evaluation_index") or 0),
        pattern_kind=row.get("pattern_kind") or "",
        score=int(row.get("score") or 0),
        cup_depth_pct=float(row.get("cup_depth_pct") or 0),
        cup_duration=int(row.get("cup_duration") or 0),
        handle_depth_pct=float(row.get("handle_depth_pct") or 0),
        handle_duration=int(row.get("handle_duration") or 0),
        lip_deviation_pct=float(row.get("lip_deviation_pct") or 0),
        is_breakout=bool(row.get("is_breakout")),
        is_volume_breakout=bool(row.get("is_volume_breakout")),
        breakout_price=float(row.get("breakout_price") or 0),
        current_close=float(row.get("current_close") or 0),
        volume_dry_score=int(row.get("volume_dry_score") or 0),
        price_stable_score=int(row.get("price_stable_score") or 0),
        pattern_score_20=int(row.get("pattern_score_20") or 0),
        verdict_key=row.get("verdict_key") or "",
        risk_percent=float(row.get("risk_percent") or 0),
        rr1=float(row.get("rr1") or 0),
        entry_zone_low=float(row.get("entry_zone_low") or 0),
        entry_zone_high=float(row.get("entry_zone_high") or 0),
        stop_loss=float(row.get("stop_loss") or 0),
        target_1=float(row.get("target_1") or 0),
        target_2=float(row.get("target_2") or 0),
        baseline_passed=bool(row.get("baseline_passed", 1)),
        experiment_passed=bool(row.get("experiment_passed", 1)),
        experiment_filter_reason=row.get("experiment_filter_reason") or "",
        evaluation_snapshot=snapshot,
    )

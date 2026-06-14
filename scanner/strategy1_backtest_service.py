"""Strategy1 trusted backtest task service."""

from __future__ import annotations

import datetime
import hashlib
import json

import scanner.db as db
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

        summary = db.build_strategy1_backtest_summary(task_id)
        status = "completed" if failed == 0 else "completed_with_errors"
        experiment = payload_snapshot.get("experiment") or {}
        credibility = "EXPERIMENTAL" if experiment.get("enabled") else (
            "TRUSTED_BASELINE" if status == "completed" else "INCOMPLETE"
        )
        db.update_strategy1_backtest_task(
            task_id,
            status=status,
            credibility_status=credibility,
            processed_stocks=processed,
            failed_stocks_count=failed,
            insufficient_stocks_count=insufficient,
            raw_signals_count=raw_signals,
            opportunities_count=opportunities,
            actual_evaluation_start_date=actual_start,
            actual_evaluation_end_date=actual_end,
            observation_data_end_date=observation_end,
            summary_json=json.dumps(summary, ensure_ascii=False),
            finished_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
    except Exception as exc:
        db.update_strategy1_backtest_task(
            task_id,
            status="failed",
            credibility_status="INCOMPLETE",
            error=str(exc),
            finished_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        raise

"""策略2回测任务执行服务。"""
import datetime
import hashlib
import json
import logging
import time

import scanner.db as db
from strategy2.backtester import run_strategy2_stock_backtest

logger = logging.getLogger(__name__)


class DataRevisionChangedError(RuntimeError):
    """任务创建后的本地日线内容已经变化。"""


class EngineRevisionChangedError(RuntimeError):
    """任务创建后策略或回测实现版本已经变化。"""


def _now_local() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def calculate_daily_ohlc_revision(snapshot_date: str, codes: list[str] | None = None) -> str:
    """计算指定股票范围和快照日期内 OHLC 内容的稳定 SHA-256。"""
    params = [snapshot_date[:10]]
    query = (
        "SELECT code,date,open,high,low,close,volume,turnover FROM daily_ohlc "
        "WHERE date<=?"
    )
    if codes:
        placeholders = ",".join("?" for _ in codes)
        query += f" AND code IN ({placeholders})"
        params.extend(codes)
    query += " ORDER BY code,date"
    rows = db.get_conn().execute(query, params)
    digest = hashlib.sha256()
    for row in rows:
        digest.update(json.dumps(row, ensure_ascii=True, separators=(",", ":")).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def calculate_task_daily_ohlc_revision(task_id: str, snapshot_date: str) -> str:
    """按任务股票范围计算稳定 OHLC 内容指纹。"""
    rows = db.get_conn().execute(
        "SELECT o.code,o.date,o.open,o.high,o.low,o.close,o.volume,o.turnover "
        "FROM daily_ohlc o "
        "JOIN strategy2_backtest_task_stocks s ON s.code=o.code "
        "WHERE s.task_id=? AND o.date<=? "
        "ORDER BY o.code,o.date",
        (task_id, snapshot_date[:10]),
    )
    digest = hashlib.sha256()
    for row in rows:
        digest.update(json.dumps(row, ensure_ascii=True, separators=(",", ":")).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def validate_task_data_revision(task_id: str) -> None:
    """确认任务仍读取创建时冻结的数据版本。"""
    task = db.get_strategy2_backtest_task(task_id)
    if not task:
        raise ValueError(f"Backtest task not found: {task_id}")
    expected = task.get("data_revision_id")
    revision_version = task.get("data_revision_version")
    actual = calculate_task_daily_ohlc_revision(task_id, task.get("data_snapshot_date") or "")
    if revision_version != db.STRATEGY2_DATA_REVISION_VERSION or not expected or expected != actual:
        db.update_strategy2_backtest_task(
            task_id,
            status="DATA_REVISION_CHANGED",
            credibility_status="PHASE1_INCOMPLETE",
            error=(
                f"DATA_REVISION_CHANGED: version={revision_version or 'missing'} "
                f"expected={expected or 'missing'} actual={actual}"
            ),
        )
        raise DataRevisionChangedError("Local daily OHLC data revision changed")


def validate_task_engine_revision(task_id: str) -> None:
    """Prevent old tasks from mixing results produced by a new implementation."""
    from strategy2.version import (
        STRATEGY2_BACKTEST_ENGINE_VERSION,
        STRATEGY2_STRATEGY_ENGINE_VERSION,
    )

    task = db.get_strategy2_backtest_task(task_id)
    if not task:
        raise ValueError(f"Backtest task not found: {task_id}")
    if (
        task.get("backtest_engine_version") != STRATEGY2_BACKTEST_ENGINE_VERSION
        or task.get("strategy_engine_version") != STRATEGY2_STRATEGY_ENGINE_VERSION
    ):
        db.update_strategy2_backtest_task(
            task_id,
            status="ENGINE_REVISION_CHANGED",
            credibility_status="PHASE1_INCOMPLETE",
            error=(
                "ENGINE_REVISION_CHANGED: "
                f"backtest={task.get('backtest_engine_version') or 'missing'} "
                f"strategy={task.get('strategy_engine_version') or 'missing'}"
            ),
        )
        raise EngineRevisionChangedError("Strategy2 implementation revision changed")


def _finalize_task(task_id: str, cancel_event, elapsed: float) -> None:
    conn = db.get_conn()
    counts = conn.execute(
        "SELECT "
        "SUM(CASE WHEN status IN ('COMPLETED','INSUFFICIENT','FAILED') THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN status='INSUFFICIENT' THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN status IN ('PENDING','RUNNING') THEN 1 ELSE 0 END), "
        "SUM(evaluation_days), SUM(evaluation_error_days), SUM(raw_signals_count), "
        "MIN(actual_eval_start_date), MAX(actual_eval_end_date), MAX(observation_data_end_date), "
        "SUM(experiment_filtered_days), SUM(experiment_volume_filtered_days), "
        "SUM(experiment_score_filtered_days), SUM(entry_confirmation_failed_count), "
        "SUM(time_exit_count) "
        "FROM strategy2_backtest_task_stocks WHERE task_id=?",
        (task_id,),
    ).fetchone()
    processed, failed, insufficient, unfinished = (value or 0 for value in counts[:4])
    evaluations, evaluation_errors, raw_signals = (value or 0 for value in counts[4:7])
    actual_start, actual_end, observation_end = counts[7:10]
    (
        experiment_filtered,
        experiment_volume_filtered,
        experiment_score_filtered,
        entry_confirmation_failed,
        time_exit_count,
    ) = (value or 0 for value in counts[10:15])
    opportunities = conn.execute(
        "SELECT COUNT(*) FROM strategy2_backtest_opportunities WHERE task_id=?", (task_id,)
    ).fetchone()[0]
    stocks_with_opportunities = conn.execute(
        "SELECT COUNT(DISTINCT code) FROM strategy2_backtest_opportunities WHERE task_id=?", (task_id,)
    ).fetchone()[0]
    task_row = db.get_strategy2_backtest_task(task_id) or {}
    experiment_snapshot = {}
    if task_row.get("experiment_snapshot"):
        try:
            experiment_snapshot = json.loads(task_row["experiment_snapshot"])
        except Exception:
            experiment_snapshot = {}
    is_experiment = bool(experiment_snapshot.get("enabled"))

    if cancel_event.is_set():
        status = "CANCELED"
    elif unfinished:
        status = "INTERRUPTED"
    elif failed:
        status = "completed_with_errors"
    else:
        status = "completed"

    summary = db.build_strategy2_backtest_summary(task_id)
    summary["dateRange"] = {
        "actual_evaluation_start_date": actual_start,
        "actual_evaluation_end_date": actual_end,
        "observation_data_end_date": observation_end,
    }
    db.update_strategy2_backtest_task(
        task_id,
        status=status,
        processed_stocks=processed,
        stocks_with_opportunities=stocks_with_opportunities,
        opportunities_count=opportunities,
        insufficient_stocks_count=insufficient,
        failed_stocks_count=failed,
        finished_at=_now_local(),
        elapsed_seconds=round(elapsed, 1),
        actual_evaluation_start_date=actual_start,
        actual_evaluation_end_date=actual_end,
        observation_data_end_date=observation_end,
        completed_evaluations=evaluations,
        raw_signals_count=raw_signals,
        evaluation_error_days=evaluation_errors,
        experiment_filtered_days=experiment_filtered,
        experiment_volume_filtered_days=experiment_volume_filtered,
        experiment_score_filtered_days=experiment_score_filtered,
        entry_confirmation_failed_count=entry_confirmation_failed,
        time_exit_count=time_exit_count,
        summary_json=json.dumps(summary, ensure_ascii=False),
    )
    integrity_ok, integrity_errors = db.validate_strategy2_backtest_integrity(task_id)
    summary["integrity"] = {"passed": integrity_ok, "errors": integrity_errors}
    if is_experiment and integrity_ok:
        credibility_status = "EXPERIMENTAL"
    else:
        credibility_status = "TRUSTED_BASELINE" if integrity_ok else "PHASE1_INCOMPLETE"
    db.update_strategy2_backtest_task(
        task_id,
        credibility_status=credibility_status,
        summary_json=json.dumps(summary, ensure_ascii=False),
    )


def run_strategy2_backtest_task(
    task_id: str,
    target_stocks: list[dict],
    config_snapshot: dict,
    payload_snapshot: dict,
    data_snapshot_date: str,
    cancel_event,
    running_state: dict,
    mode: str,
) -> None:
    """运行指定股票集合，并基于任务全部股票重新最终化。"""
    started = time.monotonic()
    validate_task_engine_revision(task_id)
    validate_task_data_revision(task_id)
    snap_date = data_snapshot_date[:10]
    insufficient_rows = []
    stats = running_state.setdefault("stats", {})
    stats["total_stocks"] = len(target_stocks)
    stats.setdefault("processed_stocks", 0)
    stats.setdefault("opportunities_count", 0)
    stats.setdefault("insufficient_stocks_count", 0)

    try:
        for stock in target_stocks:
            if cancel_event.is_set():
                break
            code = stock["code"]
            name = stock.get("name", "")
            stock_started_at = _now_local()
            stats["current_code"] = code
            stats["current_name"] = name
            db.save_strategy2_backtest_task_stock(
                task_id, code, name=name, status="RUNNING",
                started_at=stock_started_at, finished_at=None,
                error_code=None, error_detail=None,
            )
            try:
                ohlc = db.get_ohlc(code)
                if snap_date and ohlc:
                    ohlc = [row for row in ohlc if row["date"] <= snap_date]
                if not ohlc:
                    required_days = config_snapshot.get("strategy2", {}).get("minimum_required_days", 250)
                    insufficient = {
                        "code": code, "name": name, "reason_code": "NO_LOCAL_DATA",
                        "available_days": 0, "required_days": required_days,
                        "earliest_date": "", "latest_date": "",
                    }
                    insufficient_rows.append(insufficient)
                    db.save_strategy2_backtest_task_stock(
                        task_id, code, status="INSUFFICIENT", error_code="NO_LOCAL_DATA",
                        available_days=0, required_days=required_days,
                        earliest_date="", latest_date="",
                        started_at=stock_started_at, finished_at=_now_local(),
                    )
                    continue

                result = run_strategy2_stock_backtest(
                    code, name, ohlc, config_snapshot,
                    payload_snapshot.get("startDate", ""),
                    payload_snapshot.get("endDate", ""),
                    experiment=payload_snapshot.get("experiment"),
                )
                if result.get("insufficient"):
                    insufficient = result["insufficient"]
                    insufficient_rows.append(insufficient)
                    db.save_strategy2_backtest_task_stock(
                        task_id, code, status="INSUFFICIENT",
                        error_code=insufficient["reason_code"],
                        available_days=insufficient.get("available_days", 0),
                        required_days=insufficient.get("required_days", 0),
                        earliest_date=insufficient.get("earliest_date", ""),
                        latest_date=insufficient.get("latest_date", ""),
                        started_at=stock_started_at, finished_at=_now_local(),
                    )
                    continue

                result["started_at"] = stock_started_at
                result["finished_at"] = _now_local()
                db.replace_strategy2_stock_backtest_result(task_id, code, name, result)
            except Exception as exc:
                db.save_strategy2_backtest_task_stock(
                    task_id, code, status="FAILED",
                    error_code=type(exc).__name__, error_detail=str(exc)[:500],
                    started_at=stock_started_at, finished_at=_now_local(),
                )
                logger.warning("Strategy2 backtest stock %s failed: %s", code, exc)
            finally:
                stats["processed_stocks"] += 1
                stats["opportunities_count"] = db.get_conn().execute(
                    "SELECT COUNT(*) FROM strategy2_backtest_opportunities WHERE task_id=?", (task_id,)
                ).fetchone()[0]
                stats["insufficient_stocks_count"] = db.get_conn().execute(
                    "SELECT COUNT(*) FROM strategy2_backtest_task_stocks "
                    "WHERE task_id=? AND status='INSUFFICIENT'", (task_id,)
                ).fetchone()[0]

        if insufficient_rows:
            db.save_strategy2_backtest_insufficient_stocks(task_id, insufficient_rows)
        validate_task_engine_revision(task_id)
        validate_task_data_revision(task_id)
        _finalize_task(task_id, cancel_event, time.monotonic() - started)
    except Exception as exc:
        if not isinstance(exc, (DataRevisionChangedError, EngineRevisionChangedError)):
            db.update_strategy2_backtest_task(
                task_id, status="failed", credibility_status="PHASE1_INCOMPLETE",
                error=str(exc), finished_at=_now_local(),
            )
        raise
    finally:
        if running_state.get("task_id") == task_id:
            running_state["running"] = False
            running_state["task_id"] = None

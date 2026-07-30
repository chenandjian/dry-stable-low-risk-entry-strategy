import logging
import threading
import time
from collections import deque

from apscheduler.schedulers.background import BackgroundScheduler

import scanner.db as db
from scanner import stock_pool
from strategy6 import STRATEGY6_TYPE
from strategy6.scanner import scan_strategy6_all

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None
_serial_scan_lock = threading.Lock()
_scheduler_events = deque(maxlen=200)
_scheduler_events_lock = threading.Lock()


def record_scheduler_event(
    level: str,
    stage: str,
    message: str,
    *,
    task_id: str | None = None,
    details: dict | None = None,
) -> dict:
    event = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "level": level,
        "stage": stage,
        "message": message,
        "task_id": task_id or "",
        "details": details or {},
    }
    with _scheduler_events_lock:
        _scheduler_events.append(event)
    return event


def get_scheduler_events(limit: int = 200) -> list[dict]:
    limit = max(1, min(int(limit or 200), 200))
    with _scheduler_events_lock:
        events = list(_scheduler_events)
    return events[-limit:]


def clear_scheduler_events():
    with _scheduler_events_lock:
        _scheduler_events.clear()


def _parse_cron_parts(cron: str) -> dict:
    parts = str(cron or "").split()
    if len(parts) != 5:
        raise ValueError(f"Invalid scheduler cron: {cron}")
    return {
        "minute": parts[0],
        "hour": parts[1],
        "day": parts[2],
        "month": parts[3],
        "day_of_week": parts[4],
    }


def _to_apscheduler_day_of_week(day_of_week: str) -> str:
    if day_of_week == "1-5":
        return "mon-fri"
    return day_of_week


def _format_next_run_time(value) -> str:
    if not value:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def get_scheduler_status() -> dict:
    if not _scheduler:
        return {"running": False, "jobs": []}
    jobs = []
    try:
        for job in _scheduler.get_jobs():
            jobs.append(
                {
                    "id": getattr(job, "id", ""),
                    "next_run_time": _format_next_run_time(
                        getattr(job, "next_run_time", None)
                    ),
                    "trigger": str(getattr(job, "trigger", "")),
                }
            )
    except Exception:
        logger.exception("Failed to inspect scheduler jobs")
    return {
        "running": bool(getattr(_scheduler, "running", False)),
        "jobs": jobs,
    }


def _make_scan_task_id(prefix: str) -> str:
    return f"{prefix}-{time.strftime('%Y%m%d-%H%M%S')}"


def _mark_scan_task_failed(task_id: str, error: str):
    conn = db.get_conn()
    conn.execute(
        "UPDATE scan_tasks SET status='failed', error=?, finished_at=? WHERE id=?",
        (error, time.strftime("%Y-%m-%d %H:%M:%S"), task_id),
    )
    conn.commit()


def _finish_scan_task_from_summary(task_id: str, stats: dict) -> dict:
    summary = db.refresh_scan_task_counts(task_id)
    db.finish_scan_task(
        task_id,
        time.strftime("%Y-%m-%d %H:%M:%S"),
        candidates_count=int(
            summary.get("candidates_count") or stats.get("candidates_found") or 0
        ),
        elapsed_seconds=float(stats.get("elapsed_seconds") or 0),
        scanned=int(summary.get("processed") or 0),
        skipped=int(summary.get("skipped") or 0),
    )
    return db.refresh_scan_task_counts(task_id)


def _strategy6_scheduler_progress(task_id: str):
    latest = {
        "scanned": 0,
        "skipped": 0,
        "candidates_count": 0,
        "last_acquisition_event": {},
    }

    def on_progress(stage, current, total, detail, discovery=None):
        if stage in {"data_acquisition", "index_acquisition"}:
            current_value = int(current or 0)
            total_value = int(total or 0)
            last_value = int(latest["last_acquisition_event"].get(stage, -100))
            if current_value == 0 or current_value >= total_value or current_value - last_value >= 100:
                record_scheduler_event(
                    "info",
                    stage,
                    detail or "策略6行情更新中",
                    task_id=task_id,
                    details={"current": current_value, "total": total_value},
                )
                latest["last_acquisition_event"][stage] = current_value
            return
        if stage == "scanning":
            latest["scanned"] = max(latest["scanned"], int(current or 0))
        elif stage == "discovery":
            latest["candidates_count"] = max(
                latest["candidates_count"], int(current or 0)
            )
        db.update_scan_progress(
            task_id,
            scanned=latest["scanned"],
            skipped=latest["skipped"],
            candidates_count=latest["candidates_count"],
        )

    return on_progress


def run_strategy6_scheduled_scan(config: dict) -> dict:
    """Run the project's only scheduled business scan: Strategy6."""
    if not _serial_scan_lock.acquire(blocking=False):
        logger.warning("Strategy6 scheduled scan skipped: previous run is active")
        record_scheduler_event("warning", "skip", "策略6定时扫描跳过：上一轮仍在执行")
        return {"status": "skipped", "reason": "already_running_in_process"}

    task_id = None
    started = time.time()
    try:
        db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
        db.init_db(db_path)

        running = db.get_running_task()
        if running:
            record_scheduler_event(
                "info",
                "skip",
                "策略6定时扫描跳过：已有扫描任务运行中",
                task_id=running.get("id"),
                details={"strategy_type": running.get("strategy_type")},
            )
            return {
                "status": "skipped",
                "reason": "already_running_in_db",
                "running_task_id": running.get("id"),
            }

        stocks = stock_pool.get_a_stock_pool(config)
        if not stocks:
            record_scheduler_event("error", "stock_pool", "策略6定时扫描终止：股票池为空")
            return {"status": "failed", "error": "No stock pool available"}

        task_id = _make_scan_task_id("sched-s6")
        db.create_scan_task(
            task_id,
            time.strftime("%Y-%m-%d %H:%M:%S"),
            total_stocks=len(stocks),
            retry_mode="full",
            strategy_type=STRATEGY6_TYPE,
        )
        db.save_task_stocks(task_id, stocks)
        record_scheduler_event(
            "info",
            "strategy6_full",
            "策略6定时扫描开始",
            task_id=task_id,
            details={"stocks": len(stocks)},
        )

        result = scan_strategy6_all(
            config,
            task_id=task_id,
            stocks=stocks,
            progress_callback=_strategy6_scheduler_progress(task_id),
        )
        summary = _finish_scan_task_from_summary(task_id, result.get("stats", {}))
        record_scheduler_event(
            "info",
            "strategy6_complete",
            "策略6定时扫描完成",
            task_id=task_id,
            details=summary,
        )
        return {
            "status": "completed",
            "strategy6_task_id": task_id,
            "elapsed_seconds": round(time.time() - started, 1),
            "summary": summary,
        }
    except Exception as exc:
        logger.exception("Strategy6 scheduled scan failed")
        record_scheduler_event(
            "error",
            "failed",
            f"策略6定时扫描失败：{exc}",
            task_id=task_id,
        )
        if task_id:
            _mark_scan_task_failed(task_id, str(exc))
        return {
            "status": "failed",
            "error": str(exc),
            "strategy6_task_id": task_id,
        }
    finally:
        _serial_scan_lock.release()


def run_serial_dual_strategy_scan(config: dict) -> dict:
    """Compatibility alias; legacy callers now run Strategy6 only."""
    return run_strategy6_scheduled_scan(config)


def start_scheduler(config: dict):
    """Start the Strategy6-only scheduled scanner."""
    global _scheduler
    sched_cfg = config.get("scheduler", {})
    if not sched_cfg.get("enabled", False):
        logger.info("Scheduler disabled in config")
        record_scheduler_event(
            "info", "scheduler_disabled", "策略6定时任务调度器未启动：配置关闭"
        )
        return

    _scheduler = BackgroundScheduler()
    legacy_cfg = sched_cfg.get("serial_dual_scan", {})
    if legacy_cfg.get("enabled", True):
        cron = legacy_cfg.get("cron", "15 15 * * 1-5")
    else:
        cron = sched_cfg.get("cron", legacy_cfg.get("cron", "15 15 * * 1-5"))
    cron_parts = _parse_cron_parts(cron)
    _scheduler.add_job(
        lambda: run_strategy6_scheduled_scan(config),
        "cron",
        minute=cron_parts["minute"],
        hour=cron_parts["hour"],
        day_of_week=_to_apscheduler_day_of_week(cron_parts["day_of_week"]),
        id="strategy6_scan",
    )
    _scheduler.start()
    logger.info("Strategy6 scheduler started: %s", cron)
    record_scheduler_event(
        "info",
        "scheduler_started",
        "策略6定时任务已启动",
        details={"cron": cron, "runtime": get_scheduler_status()},
    )


def stop_scheduler(wait: bool = True):
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=wait)
        logger.info("Scheduler stopped")
        record_scheduler_event("info", "scheduler_stopped", "策略6定时任务调度器已停止")
    _scheduler = None


def reload_scheduler(config: dict):
    stop_scheduler(wait=False)
    start_scheduler(config)
    record_scheduler_event("info", "scheduler_reloaded", "策略6定时任务配置已重新加载")

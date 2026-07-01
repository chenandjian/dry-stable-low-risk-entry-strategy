import logging
import threading
import time
from collections import deque

from apscheduler.schedulers.background import BackgroundScheduler

from output.csv_writer import write_candidates_csv
import scanner.db as db
from scanner import stock_pool
from scanner.engine import scan_all
from strategy2.scanner import scan_strategy2_all
from strategy3.scanner import STRATEGY3_TYPE, scan_strategy3_all

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
    # APScheduler uses Monday=0 for numeric weekdays. Keep config as cron-style
    # 1-5, but register explicit weekday names to mean Monday-Friday.
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
    """Return actual in-process scheduler runtime state."""
    if not _scheduler:
        return {"running": False, "jobs": []}
    jobs = []
    try:
        for job in _scheduler.get_jobs():
            jobs.append({
                "id": getattr(job, "id", ""),
                "next_run_time": _format_next_run_time(getattr(job, "next_run_time", None)),
                "trigger": str(getattr(job, "trigger", "")),
            })
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


def _finish_scan_task_from_summary(task_id: str, stats: dict):
    summary = db.refresh_scan_task_counts(task_id)
    db.finish_scan_task(
        task_id,
        time.strftime("%Y-%m-%d %H:%M:%S"),
        candidates_count=int(
            summary.get("candidates_count")
            or stats.get("candidates_found")
            or 0
        ),
        elapsed_seconds=float(stats.get("elapsed_seconds") or 0),
        scanned=int(summary.get("processed") or 0),
        skipped=int(summary.get("skipped") or 0),
    )
    return summary


def _get_failed_stocks(task_id: str) -> list[dict]:
    return db.get_task_stocks(task_id, status="failed", limit=100000, offset=0)


def _strategy1_scheduler_progress(task_id: str):
    def on_progress(stage, current, total, detail, discovery=None):
        if stage != "discovery" or not discovery:
            return
        try:
            db.upsert_candidate(task_id, discovery)
        except Exception:
            logger.exception(
                "Serial scan failed to persist strategy1 discovery task=%s detail=%s",
                task_id,
                detail,
            )
            raise

    return on_progress


def run_serial_dual_strategy_scan(config: dict) -> dict:
    """Run Strategy1, retry failed stocks, then run Strategy2 and Strategy3 serially."""
    if not _serial_scan_lock.acquire(blocking=False):
        logger.warning("Serial dual strategy scan skipped: previous run is still active")
        record_scheduler_event(
            "warning",
            "skip",
            "串行定时扫描跳过：上一轮仍在执行",
        )
        return {"status": "skipped", "reason": "already_running_in_process"}

    s1_task_id = None
    s2_task_id = None
    s3_task_id = None
    started = time.time()
    try:
        db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
        db.init_db(db_path)

        running = db.get_running_task()
        if running:
            logger.info(
                "Serial dual strategy scan skipped: DB task already running id=%s strategy=%s",
                running.get("id"),
                running.get("strategy_type"),
            )
            record_scheduler_event(
                "info",
                "skip",
                "串行定时扫描跳过：已有扫描任务运行中",
                task_id=running.get("id"),
                details={"strategy_type": running.get("strategy_type")},
            )
            return {
                "status": "skipped",
                "reason": "already_running_in_db",
                "running_task_id": running.get("id"),
            }

        serial_cfg = config.get("scheduler", {}).get("serial_dual_scan", {})
        retry_rounds = int(serial_cfg.get("strategy1_failed_retry_rounds", 3))
        retry_rounds = max(0, min(10, retry_rounds))

        stocks = stock_pool.get_a_stock_pool(config)
        if not stocks:
            logger.error("Serial dual strategy scan aborted: stock pool is empty")
            record_scheduler_event(
                "error",
                "stock_pool",
                "串行定时扫描终止：股票池为空",
            )
            return {"status": "failed", "error": "No stock pool available"}

        s1_task_id = _make_scan_task_id("sched-s1")
        logger.info(
            "Serial scan stage=strategy1_full task=%s stocks=%d started",
            s1_task_id,
            len(stocks),
        )
        record_scheduler_event(
            "info",
            "strategy1_full",
            "策略1全量扫描开始",
            task_id=s1_task_id,
            details={"stocks": len(stocks)},
        )
        db.create_scan_task(
            s1_task_id,
            time.strftime("%Y-%m-%d %H:%M:%S"),
            total_stocks=len(stocks),
            retry_mode="full",
            strategy_type="STRATEGY_1_CUP_HANDLE",
        )
        db.save_task_stocks(s1_task_id, stocks)
        s1_progress = _strategy1_scheduler_progress(s1_task_id)
        s1_result = scan_all(
            config,
            progress_callback=s1_progress,
            task_id=s1_task_id,
            stocks=stocks,
        )
        s1_summary = db.refresh_scan_task_counts(s1_task_id)
        logger.info(
            "Serial scan stage=strategy1_full task=%s completed summary=%s",
            s1_task_id,
            s1_summary,
        )
        record_scheduler_event(
            "info",
            "strategy1_full",
            "策略1全量扫描完成",
            task_id=s1_task_id,
            details=s1_summary,
        )

        retry_history = []
        for round_no in range(1, retry_rounds + 1):
            failed_stocks = _get_failed_stocks(s1_task_id)
            if not failed_stocks:
                logger.info("Serial scan strategy1 retry stopped: no failed stocks")
                record_scheduler_event(
                    "info",
                    "strategy1_retry",
                    "策略1失败重试停止：无失败股票",
                    task_id=s1_task_id,
                    details={"round": round_no},
                )
                break
            logger.info(
                "Serial scan stage=strategy1_retry round=%d/%d task=%s failed=%d started",
                round_no,
                retry_rounds,
                s1_task_id,
                len(failed_stocks),
            )
            record_scheduler_event(
                "info",
                "strategy1_retry",
                f"策略1失败股票重试开始：第 {round_no}/{retry_rounds} 轮",
                task_id=s1_task_id,
                details={"round": round_no, "failed_before": len(failed_stocks)},
            )
            scan_all(
                config,
                progress_callback=s1_progress,
                task_id=s1_task_id,
                stocks=failed_stocks,
                retry_policy="failed_only",
            )
            s1_summary = db.refresh_scan_task_counts(s1_task_id)
            retry_history.append({
                "round": round_no,
                "failed_before": len(failed_stocks),
                "failed_after": s1_summary.get("failed"),
            })
            logger.info(
                "Serial scan stage=strategy1_retry round=%d/%d task=%s completed summary=%s",
                round_no,
                retry_rounds,
                s1_task_id,
                s1_summary,
            )
            record_scheduler_event(
                "info",
                "strategy1_retry",
                f"策略1失败股票重试完成：第 {round_no}/{retry_rounds} 轮",
                task_id=s1_task_id,
                details=retry_history[-1],
            )

        remaining_failed = len(_get_failed_stocks(s1_task_id))
        if remaining_failed:
            logger.warning(
                "Serial scan strategy1 completed with remaining failed stocks task=%s failed=%d after_retries=%d",
                s1_task_id,
                remaining_failed,
                retry_rounds,
            )
            record_scheduler_event(
                "warning",
                "strategy1_remaining_failed",
                "策略1重试后仍有失败股票",
                task_id=s1_task_id,
                details={"remaining_failed": remaining_failed, "retry_rounds": retry_rounds},
            )
        s1_summary = _finish_scan_task_from_summary(
            s1_task_id,
            s1_result.get("stats", {}),
        )
        logger.info(
            "Serial scan stage=strategy1_all_done task=%s completed summary=%s",
            s1_task_id,
            s1_summary,
        )
        record_scheduler_event(
            "info",
            "strategy1_all_done",
            "策略1流程完整结束，准备启动策略2",
            task_id=s1_task_id,
            details=s1_summary,
        )

        s2_task_id = _make_scan_task_id("sched-s2")
        logger.info(
            "Serial scan stage=strategy2_full task=%s stocks=%d started after strategy1 task=%s; "
            "strategy2 should reuse same-day daily_ohlc/task_stocks freshness when available",
            s2_task_id,
            len(stocks),
            s1_task_id,
        )
        record_scheduler_event(
            "info",
            "strategy2_full",
            "策略2扫描开始，将复用策略1当天已写入的日线数据",
            task_id=s2_task_id,
            details={"stocks": len(stocks), "strategy1_task_id": s1_task_id},
        )
        db.create_scan_task(
            s2_task_id,
            time.strftime("%Y-%m-%d %H:%M:%S"),
            total_stocks=len(stocks),
            retry_mode="full",
            strategy_type="STRATEGY_2_EXTREME_DRY_STABLE",
        )
        db.save_task_stocks(s2_task_id, stocks)
        s2_result = scan_strategy2_all(config, task_id=s2_task_id, stocks=stocks)
        s2_summary = _finish_scan_task_from_summary(
            s2_task_id,
            s2_result.get("stats", {}),
        )
        logger.info(
            "Serial scan stage=strategy2_full task=%s completed summary=%s",
            s2_task_id,
            s2_summary,
        )
        record_scheduler_event(
            "info",
            "strategy2_full",
            "策略2扫描完成，准备启动策略3",
            task_id=s2_task_id,
            details=s2_summary,
        )

        s3_task_id = _make_scan_task_id("sched-s3")
        logger.info(
            "Serial scan stage=strategy3_full task=%s stocks=%d started after strategy2 task=%s; "
            "strategy3 should reuse same-day daily_ohlc/task_stocks freshness when available",
            s3_task_id,
            len(stocks),
            s2_task_id,
        )
        record_scheduler_event(
            "info",
            "strategy3_full",
            "策略3扫描开始，将复用策略1当天已写入的日线数据",
            task_id=s3_task_id,
            details={
                "stocks": len(stocks),
                "strategy1_task_id": s1_task_id,
                "strategy2_task_id": s2_task_id,
            },
        )
        db.create_scan_task(
            s3_task_id,
            time.strftime("%Y-%m-%d %H:%M:%S"),
            total_stocks=len(stocks),
            retry_mode="full",
            strategy_type=STRATEGY3_TYPE,
        )
        db.save_task_stocks(s3_task_id, stocks)
        s3_result = scan_strategy3_all(config, task_id=s3_task_id, stocks=stocks)
        s3_summary = _finish_scan_task_from_summary(
            s3_task_id,
            s3_result.get("stats", {}),
        )
        logger.info(
            "Serial scan stage=strategy3_full task=%s completed summary=%s",
            s3_task_id,
            s3_summary,
        )
        record_scheduler_event(
            "info",
            "strategy3_full",
            "策略3扫描完成",
            task_id=s3_task_id,
            details=s3_summary,
        )

        return {
            "status": "completed",
            "strategy1_task_id": s1_task_id,
            "strategy2_task_id": s2_task_id,
            "strategy3_task_id": s3_task_id,
            "strategy1_remaining_failed": remaining_failed,
            "strategy1_retry_history": retry_history,
            "elapsed_seconds": round(time.time() - started, 1),
        }
    except Exception as exc:
        logger.exception("Serial dual strategy scan failed")
        record_scheduler_event(
            "error",
            "failed",
            f"串行定时扫描失败：{exc}",
            task_id=s3_task_id or s2_task_id or s1_task_id,
            details={
                "strategy1_task_id": s1_task_id,
                "strategy2_task_id": s2_task_id,
                "strategy3_task_id": s3_task_id,
            },
        )
        if s3_task_id:
            _mark_scan_task_failed(s3_task_id, str(exc))
        elif s2_task_id:
            _mark_scan_task_failed(s2_task_id, str(exc))
        elif s1_task_id:
            _mark_scan_task_failed(s1_task_id, str(exc))
        return {
            "status": "failed",
            "error": str(exc),
            "strategy1_task_id": s1_task_id,
            "strategy2_task_id": s2_task_id,
            "strategy3_task_id": s3_task_id,
        }
    finally:
        _serial_scan_lock.release()


def start_scheduler(config: dict):
    """启动定时扫描调度器。"""
    global _scheduler
    sched_cfg = config.get("scheduler", {})

    if not sched_cfg.get("enabled", False):
        logger.info("Scheduler disabled in config")
        record_scheduler_event(
            "info",
            "scheduler_disabled",
            "定时任务调度器未启动：配置关闭",
        )
        return

    _scheduler = BackgroundScheduler()

    serial_cfg = sched_cfg.get("serial_dual_scan", {})
    serial_enabled = serial_cfg.get("enabled", True)

    if serial_enabled:
        cron = serial_cfg.get("cron", "15 15 * * 1-5")
        cron_parts = _parse_cron_parts(cron)
        _scheduler.add_job(
            lambda: run_serial_dual_strategy_scan(config),
            "cron",
            minute=cron_parts["minute"],
            hour=cron_parts["hour"],
            day_of_week=_to_apscheduler_day_of_week(cron_parts["day_of_week"]),
            id="serial_dual_strategy_scan",
        )
        _scheduler.start()
        logger.info("Serial dual strategy scheduler started: %s", cron)
        record_scheduler_event(
            "info",
            "scheduler_started",
            "串行三策略定时任务已启动",
            details={"cron": cron, "runtime": get_scheduler_status()},
        )
        return

    cron = sched_cfg.get("cron", "30 15 * * 1-5")
    cron_parts = _parse_cron_parts(cron)
    skip_if_running = sched_cfg.get("skip_if_running", True)

    _running = [False]

    def job():
        if skip_if_running and _running[0]:
            logger.warning("Previous scan still running, skipping this trigger")
            return
        try:
            _running[0] = True
            db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
            db.init_db(db_path)
            if skip_if_running and db.get_running_task_id():
                logger.info("Scheduled scan skipped because another scan is running")
                return
            logger.info("Scheduled scan started")
            result = scan_all(config)
            stats = result["stats"]
            logger.info(
                "Scheduled scan done: %s candidates, %ss",
                stats["candidates_found"],
                stats["elapsed_seconds"],
            )
            if result["candidates"]:
                output_dir = config.get("output", {}).get("output_dir", "./output_data")
                write_candidates_csv(result["candidates"], output_dir)
        except Exception as e:
            logger.error("Scheduled scan failed: %s", e)
        finally:
            _running[0] = False

    _scheduler.add_job(job, "cron",
                       minute=cron_parts["minute"],
                       hour=cron_parts["hour"],
                       day_of_week=_to_apscheduler_day_of_week(cron_parts["day_of_week"]),
                       id="daily_scan")

    _scheduler.start()
    logger.info(f"Scheduler started: {cron}")
    record_scheduler_event(
        "info",
        "scheduler_started",
        "旧版每日扫描定时任务已启动",
        details={"cron": cron, "runtime": get_scheduler_status()},
    )


def stop_scheduler(wait: bool = True):
    """停止调度器。"""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=wait)
        logger.info("Scheduler stopped")
        record_scheduler_event(
            "info",
            "scheduler_stopped",
            "定时任务调度器已停止",
        )
    _scheduler = None


def reload_scheduler(config: dict):
    """Reload scheduler jobs from the latest config."""
    stop_scheduler(wait=False)
    start_scheduler(config)
    record_scheduler_event(
        "info",
        "scheduler_reloaded",
        "定时任务配置已重新加载",
        details={"runtime": get_scheduler_status()},
    )

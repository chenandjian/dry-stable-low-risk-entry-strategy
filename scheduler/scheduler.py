import logging
import threading
import time

from apscheduler.schedulers.background import BackgroundScheduler

from output.csv_writer import write_candidates_csv
import scanner.db as db
from scanner import stock_pool
from scanner.engine import scan_all
from strategy2.scanner import scan_strategy2_all

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None
_serial_scan_lock = threading.Lock()


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
    """Run Strategy1, retry its failed stocks, then run Strategy2 serially."""
    if not _serial_scan_lock.acquire(blocking=False):
        logger.warning("Serial dual strategy scan skipped: previous run is still active")
        return {"status": "skipped", "reason": "already_running_in_process"}

    s1_task_id = None
    s2_task_id = None
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
            return {"status": "failed", "error": "No stock pool available"}

        s1_task_id = _make_scan_task_id("sched-s1")
        logger.info(
            "Serial scan stage=strategy1_full task=%s stocks=%d started",
            s1_task_id,
            len(stocks),
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

        retry_history = []
        for round_no in range(1, retry_rounds + 1):
            failed_stocks = _get_failed_stocks(s1_task_id)
            if not failed_stocks:
                logger.info("Serial scan strategy1 retry stopped: no failed stocks")
                break
            logger.info(
                "Serial scan stage=strategy1_retry round=%d/%d task=%s failed=%d started",
                round_no,
                retry_rounds,
                s1_task_id,
                len(failed_stocks),
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

        remaining_failed = len(_get_failed_stocks(s1_task_id))
        if remaining_failed:
            logger.warning(
                "Serial scan strategy1 completed with remaining failed stocks task=%s failed=%d after_retries=%d",
                s1_task_id,
                remaining_failed,
                retry_rounds,
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

        s2_task_id = _make_scan_task_id("sched-s2")
        logger.info(
            "Serial scan stage=strategy2_full task=%s stocks=%d started after strategy1 task=%s; "
            "strategy2 should reuse same-day daily_ohlc/task_stocks freshness when available",
            s2_task_id,
            len(stocks),
            s1_task_id,
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

        return {
            "status": "completed",
            "strategy1_task_id": s1_task_id,
            "strategy2_task_id": s2_task_id,
            "strategy1_remaining_failed": remaining_failed,
            "strategy1_retry_history": retry_history,
            "elapsed_seconds": round(time.time() - started, 1),
        }
    except Exception as exc:
        logger.exception("Serial dual strategy scan failed")
        if s2_task_id:
            _mark_scan_task_failed(s2_task_id, str(exc))
        elif s1_task_id:
            _mark_scan_task_failed(s1_task_id, str(exc))
        return {
            "status": "failed",
            "error": str(exc),
            "strategy1_task_id": s1_task_id,
            "strategy2_task_id": s2_task_id,
        }
    finally:
        _serial_scan_lock.release()


def start_scheduler(config: dict):
    """启动定时扫描调度器。"""
    global _scheduler
    sched_cfg = config.get("scheduler", {})

    if not sched_cfg.get("enabled", False):
        logger.info("Scheduler disabled in config")
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
            day_of_week=cron_parts["day_of_week"],
            id="serial_dual_strategy_scan",
        )
        _scheduler.start()
        logger.info("Serial dual strategy scheduler started: %s", cron)
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
                       day_of_week=cron_parts["day_of_week"],
                       id="daily_scan")

    _scheduler.start()
    logger.info(f"Scheduler started: {cron}")


def stop_scheduler():
    """停止调度器。"""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=True)
        logger.info("Scheduler stopped")

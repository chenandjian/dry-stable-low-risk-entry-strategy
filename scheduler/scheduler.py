# scheduler/scheduler.py
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from scanner.engine import scan_all
from output.csv_writer import write_candidates_csv

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def start_scheduler(config: dict):
    """启动定时扫描调度器。"""
    global _scheduler
    sched_cfg = config.get("scheduler", {})

    if not sched_cfg.get("enabled", False):
        logger.info("Scheduler disabled in config")
        return

    cron = sched_cfg.get("cron", "30 15 * * 1-5")
    skip_if_running = sched_cfg.get("skip_if_running", True)

    _scheduler = BackgroundScheduler()
    _running = [False]

    def job():
        if skip_if_running and _running[0]:
            logger.warning("Previous scan still running, skipping this trigger")
            return
        try:
            _running[0] = True
            logger.info("Scheduled scan started")
            result = scan_all(config)
            stats = result["stats"]
            logger.info(f"Scheduled scan done: {stats['candidates_found']} candidates, "
                        f"{stats['elapsed_seconds']}s")
            if result["candidates"]:
                output_dir = config.get("output", {}).get("output_dir", "./output_data")
                write_candidates_csv(result["candidates"], output_dir)
        except Exception as e:
            logger.error(f"Scheduled scan failed: {e}")
        finally:
            _running[0] = False

    _scheduler.add_job(job, "cron",
                       minute=cron.split()[0],
                       hour=cron.split()[1],
                       day_of_week=cron.split()[4],
                       id="daily_scan")

    _scheduler.start()
    logger.info(f"Scheduler started: {cron}")


def stop_scheduler():
    """停止调度器。"""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=True)
        logger.info("Scheduler stopped")

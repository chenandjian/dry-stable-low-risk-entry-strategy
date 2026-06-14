# server.py
import datetime
import json
import logging
import sys
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
from fastapi.middleware.cors import CORSMiddleware
import yaml

import scanner.db as db
from scanner.engine import scan_all, re_evaluate_task
from strategy2.scanner import scan_strategy2_all
from strategy2.validation import resolve_strategy2_config
from scanner.strategy_engine import (
    CupHandleStrategyEngine,
    resolve_strategy_windows,
    select_market_window,
    select_strategy_window,
)
from scanner.index_source import fetch_market_index_daily
from scanner.pattern_detector import CupHandleResult
from scanner.single_stock_backtest import (
    DataCoverageError,
    run_single_stock_cuphandle_backtest,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB, load config, start scheduler if enabled."""
    config = load_config()
    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)
    db.mark_dead_tasks_as_failed()
    # 自动恢复中断的扫描
    interrupted = db.get_interrupted_task()
    if interrupted:
        s_type = interrupted.get("strategy_type", "STRATEGY_1_CUP_HANDLE")
        logger.info(f"Resuming interrupted {s_type} scan: {interrupted['id']} at {interrupted['scanned']}/{interrupted['total_stocks']}")
        import threading, datetime
        _set_running(interrupted["id"], "resume", strategy_type=s_type)
        _running["started_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _running["stats"] = {
            "total_stocks": interrupted["total_stocks"],
            "current_code": "--",
            "current_name": "恢复扫描中",
        }

        if s_type == "STRATEGY_2_EXTREME_DRY_STABLE":
            # BUG-S2-001: 策略2恢复
            def resume_s2():
                try:
                    pending = db.get_pending_stocks(interrupted["id"])
                    def on_progress(stage, current, total, detail, discovery=None):
                        stats = _running.get("stats", {})
                        if stage == "discovery" and discovery:
                            found = stats.get("candidates_found", 0) + 1
                            discoveries = list(stats.get("discoveries") or [])
                            discoveries.insert(0, {
                                "code": discovery["code"], "name": discovery["name"],
                                "total_score": discovery["total_score"],
                                "level": discovery["level"],
                                "risk_ratio": discovery["risk_ratio"],
                            })
                            _running["stats"] = {**stats, "discoveries": discoveries[:20], "candidates_found": found}
                        else:
                            code = detail.split()[0] if detail else ""
                            _running["stats"] = {**stats, "scanned": current, "processed": current, "total_stocks": total, "current_code": code, "current_name": detail[len(code):].strip() if len(detail) > len(code) else detail}
                    result = scan_strategy2_all(config, progress_callback=on_progress, task_id=interrupted["id"], stocks=pending)
                    _running["stats"] = result["stats"]
                    s = result["stats"]
                    db.finish_scan_task(interrupted["id"], finished_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), candidates_count=s.get("candidates_found", 0), elapsed_seconds=s.get("elapsed_seconds", 0), scanned=s.get("scanned", 0), skipped=s.get("skipped", 0))
                    db.refresh_scan_task_counts(interrupted["id"])
                except Exception as e:
                    import traceback
                    logger.error(f"Strategy2 resume failed: {e}\n{traceback.format_exc()}")
                    _running["stats"] = {"error": str(e)}
                    conn = db.get_conn()
                    conn.execute("UPDATE scan_tasks SET status='failed', error=? WHERE id=?", (str(e), interrupted["id"]))
                    conn.commit()
                finally:
                    _clear_running()
            t = threading.Thread(target=resume_s2, daemon=True)
        elif s_type == "STRATEGY_1_CUP_HANDLE":
            # 策略1恢复
            def resume_s1():
                try:
                    def on_progress(stage, current, total, detail, discovery=None):
                        stats = _running.get("stats", {})
                        if stage == "discovery" and discovery:
                            found = stats.get("candidates_found", 0) + 1
                            discoveries = list(stats.get("discoveries") or [])
                            discoveries.insert(0, {"code": discovery["code"], "name": discovery["name"], "score": discovery["score"]})
                            _running["stats"] = {**stats, "discoveries": discoveries[:20], "candidates_found": found}
                        else:
                            code = detail.split()[0] if detail else ""
                            _running["stats"] = {**stats, "scanned": current, "processed": current, "total_stocks": total, "current_code": code, "current_name": detail[len(code):].strip() if len(detail) > len(code) else detail}
                    result = scan_all(config, progress_callback=on_progress, resume_task_id=interrupted["id"])
                    _running["stats"] = result["stats"]
                    _running["candidates"] = result["candidates"]
                    s = result["stats"]
                    db.finish_scan_task(interrupted["id"], finished_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), candidates_count=s.get("candidates_found", 0), elapsed_seconds=s.get("elapsed_seconds", 0), scanned=s.get("scanned", 0), skipped=s.get("skipped", 0))
                    db.refresh_scan_task_counts(interrupted["id"])
                except Exception as e:
                    import traceback
                    logger.error(f"Resume scan failed: {e}\n{traceback.format_exc()}")
                    _running["stats"] = {"error": str(e)}
                    conn = db.get_conn()
                    conn.execute("UPDATE scan_tasks SET status='failed', error=? WHERE id=?", (str(e), interrupted["id"]))
                    conn.commit()
                finally:
                    _clear_running()
            t = threading.Thread(target=resume_s1, daemon=True)
        else:
            # RECHECK-S2-005: 未知 strategy_type — 标记失败，不默认执行
            logger.error(f"Unknown strategy_type '{s_type}' for interrupted task {interrupted['id']} — marking as failed")
            conn = db.get_conn()
            conn.execute(
                "UPDATE scan_tasks SET status='failed', error=? WHERE id=?",
                (f"UNKNOWN_STRATEGY_TYPE: {s_type}", interrupted["id"]),
            )
            conn.commit()
            _clear_running()
            return
        t.start()
    logger.info(f"Database initialized at {db_path}")

    if config.get("scheduler", {}).get("enabled", False):
        from scheduler.scheduler import start_scheduler
        start_scheduler(config)
        logger.info("Scheduler auto-started on server launch")

    # Mark Strategy2 backtests left by a previous process as explicitly resumable.
    try:
        for task_id in db.mark_running_strategy2_backtests_interrupted():
            logger.info("Marked interrupted Strategy2 backtest task: %s", task_id)
    except Exception:
        logger.exception("Failed to mark interrupted Strategy2 backtest tasks")

    yield
    from scheduler.scheduler import stop_scheduler
    stop_scheduler()
    logger.info("Server shutting down")


app = FastAPI(title="CupHandleScan API", lifespan=lifespan)

# CORS for frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Minimal in-memory state for the currently running scan (used by WebSocket push)
_running = {
    "running": False,
    "task_id": None,
    "strategy_type": None,
    "stats": {},
}

# Strategy2 backtest running state — mutually exclusive with scans
_backtest_running = {
    "running": False,
    "task_id": None,
    "started_at": None,
    "stats": {},
    "cancel_event": None,
    "thread": None,
}


def _get_running_task_id() -> str | None:
    """Return the active scan task id from memory or DB."""
    if _running.get("running") and _running.get("task_id"):
        return _running["task_id"]
    try:
        return db.get_running_task_id()
    except RuntimeError:
        return None


def _get_running_strategy_type() -> str | None:
    """Return the active scan's strategy type."""
    if _running.get("running") and _running.get("strategy_type"):
        return _running["strategy_type"]
    return None


def _scan_conflict_response():
    """Return a 409 response if any scan or backtest process is already running."""
    running_id = _get_running_task_id()
    if running_id:
        return JSONResponse(
            {
                "error": "SCAN_ALREADY_RUNNING",
                "message": "当前已有全市场扫描任务正在运行",
                "runningTaskId": running_id,
                "runningStrategyType": _running.get("strategy_type", "STRATEGY_1_CUP_HANDLE"),
            },
            status_code=409,
        )
    if _backtest_running["running"]:
        return JSONResponse(
            {
                "error": "TASK_CONFLICT",
                "message": "当前已有策略2回测任务正在运行",
                "runningTaskId": _backtest_running["task_id"],
            },
            status_code=409,
        )
    return None


def _set_running(task_id: str, mode: str, strategy_type: str = "STRATEGY_1_CUP_HANDLE"):
    _running["running"] = True
    _running["task_id"] = task_id
    _running["mode"] = mode
    _running["strategy_type"] = strategy_type
    _running["stats"] = {}


def _clear_running():
    _running["running"] = False
    _running["task_id"] = None
    _running["started_at"] = None


def _require_task_strategy(task_id: str, expected: str):
    """FINAL-S2-001: 统一任务类型校验。所有绑定策略的接口必须复用。

    Returns:
        (actual_type, None) on match, or (None, error_response) on mismatch.
    """
    if not task_id:
        return None, None
    actual = db.get_task_strategy_type(task_id)
    if actual is None:
        return None, JSONResponse(
            {"error": "TASK_NOT_FOUND", "task_id": task_id},
            status_code=404,
        )
    if actual != expected:
        return None, JSONResponse(
            {
                "error": "TASK_STRATEGY_MISMATCH",
                "task_id": task_id,
                "expected_strategy_type": expected,
                "actual_strategy_type": actual,
            },
            status_code=400,
        )
    return actual, None


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _deep_merge(base: dict, update: dict):
    """Recursively merge update into base. Only updates provided keys."""
    for key, value in update.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


@app.get("/api/scan/start")
async def start_scan():
    import datetime
    from scanner.stock_pool import get_a_stock_pool_result

    config = load_config()
    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)

    conflict = _scan_conflict_response()
    if conflict:
        return conflict

    # Validate strategy windows before creating task (BUG-004)
    try:
        resolve_strategy_windows(config)
    except ValueError as e:
        return JSONResponse(
            {"error": f"Invalid window config: {e}"},
            status_code=400,
        )

    task_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    started_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.create_scan_task(task_id, started_at, total_stocks=0, retry_mode="full",
                        strategy_type="STRATEGY_1_CUP_HANDLE")
    _set_running(task_id, "full", strategy_type="STRATEGY_1_CUP_HANDLE")
    _running["started_at"] = started_at
    _running["stats"] = {
        "total_stocks": 0,
        "current_code": "--",
        "current_name": "获取股票池中…",
    }

    def run():
        pool_result = get_a_stock_pool_result(config)
        stocks = pool_result["stocks"]
        if not stocks:
            _running["stats"] = {"error": "No stock pool available"}
            conn = db.get_conn()
            conn.execute("UPDATE scan_tasks SET status='failed', error=? WHERE id=?", ("No stock pool", task_id))
            conn.commit()
            _clear_running()
            return
        db.update_scan_task_total(task_id, len(stocks), pool_result["source"])
        db.save_task_stocks(task_id, stocks)
        _running["stats"] = {
            "total_stocks": len(stocks),
            "stock_pool_source": pool_result["source"],
            "current_code": "--",
            "current_name": "初始化中",
        }
        try:
            def on_progress(stage, current, total, detail, discovery=None):
                """实时更新扫描进度到内存状态和数据库。"""
                stats = _running.get("stats", {})
                if stage == "discovery" and discovery:
                    found = stats.get("candidates_found", 0) + 1
                    try:
                        db.upsert_candidate(task_id, discovery)
                    except Exception as exc:
                        logger.error("Failed to upsert candidate %s: %s", discovery.get("code", "?"), exc)
                    discoveries = list(stats.get("discoveries") or [])
                    discoveries.insert(0, {
                        "code": discovery["code"],
                        "name": discovery["name"],
                        "score": discovery["score"],
                        "rating": "强候选" if discovery["score"] >= 80 else "中等候选" if discovery["score"] >= 70 else "弱候选",
                        "dry_stable_verdict": discovery.get("dry_stable_verdict", ""),
                        "dry_stable_summary": discovery.get("dry_stable_summary", ""),
                        "volume_dry_score": discovery.get("volume_dry_score", 0),
                        "price_stable_score": discovery.get("price_stable_score", 0),
                        "pattern_score_20": discovery.get("pattern_score_20", 0),
                        "pattern_type": discovery.get("pattern_type", ""),
                        "key_pattern_type": discovery.get("key_pattern_type", ""),
                        "risk_percent": discovery.get("risk_percent", 0),
                        "rr1": discovery.get("rr1", 0),
                        "position_advice": discovery.get("position_advice", ""),
                        "entry_zone_low": discovery.get("entry_zone_low", 0),
                        "entry_zone_high": discovery.get("entry_zone_high", 0),
                        "pivot": discovery.get("pivot", 0),
                        "stop_loss": discovery.get("stop_loss", 0),
                        "target_1": discovery.get("target_1", 0),
                        "target_2": discovery.get("target_2", 0),
                        "market_status": discovery.get("market_status", ""),
                        "market_position_advice": discovery.get("market_position_advice", ""),
                        "is_breakout": discovery["is_breakout"],
                        "is_volume_breakout": discovery.get("is_volume_breakout", False),
                        "cup_depth_pct": discovery["cup_depth_pct"],
                        "cup_duration": discovery["cup_duration"],
                        "handle_depth_pct": discovery["handle_depth_pct"],
                        "vol_multiplier": discovery["vol_multiplier"],
                        "breakout_price": discovery.get("breakout_price", 0),
                        "latest_close": discovery.get("latest_close", 0),
                        "verdict_key": discovery.get("verdict_key", ""),
                    })
                    _running["stats"] = {
                        **stats,
                        "discoveries": discoveries[:20],
                        "candidates_found": found,
                    }
                else:
                    code = detail.split()[0] if detail else ""
                    s = stats.copy()
                    s.update({
                        "scanned": current,
                        "processed": current,
                        "total_stocks": total,
                        "current_code": code,
                        "current_name": detail[len(code):].strip() if len(detail) > len(code) else detail,
                    })
                    s.setdefault("candidates_found", 0)
                    s.setdefault("skipped", 0)
                    s.setdefault("failed", 0)
                    _running["stats"] = s
                db.update_scan_progress(
                    task_id,
                    scanned=_running["stats"].get("scanned", 0),
                    skipped=_running["stats"].get("skipped", 0),
                    candidates_count=_running["stats"].get("candidates_found", 0),
                )

            result = scan_all(
                config,
                progress_callback=on_progress,
                task_id=task_id,
                stocks=stocks,
                retry_policy="normal",
            )

            # Save candidates from scan result (may be empty if progress_callback
            # discovered candidates but scan_all lost them — see re-evaluate below)
            sc = config.get("scoring", {})
            if result["candidates"]:
                db.save_candidates(
                    task_id, result["candidates"],
                    strong=sc.get("strong_threshold", 80),
                    medium=sc.get("medium_threshold", 70),
                )

            s = result["stats"]
            _running["stats"] = s

            # Safety net: if scan found candidates via progress_callback but
            # scan_all lost them, re-evaluate to sync candidates table.
            if not result["candidates"]:
                candidate_count = db.summarize_task_stocks(task_id).get("candidate", 0)
                if candidate_count > 0:
                    logger.info("Sync: re-evaluating %d candidate-marked stocks", candidate_count)
                    re_evaluate_task(config, task_id)
                    s = db.refresh_scan_task_counts(task_id)

            db.finish_scan_task(
                task_id,
                finished_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                candidates_count=s.get("candidates_found", 0),
                elapsed_seconds=s.get("elapsed_seconds", 0),
                scanned=s.get("scanned", 0),
                skipped=s.get("skipped", 0),
            )
            db.refresh_scan_task_counts(task_id)

        except Exception as e:
            import traceback
            logger.error(f"Scan failed: {e}\n{traceback.format_exc()}")
            _running["stats"] = {"error": str(e)}
            conn = db.get_conn()
            conn.execute("UPDATE scan_tasks SET status='failed', error=? WHERE id=?", (str(e), task_id))
            conn.commit()
        finally:
            _clear_running()

    t = threading.Thread(target=run, daemon=True)
    t.start()

    return {
        "task_id": task_id,
        "status": "started",
        "total_stocks": 0,
        "stock_pool_source": "",
    }



@app.get("/api/scan/status")
async def scan_status():
    if _running["running"]:
        summary = db.refresh_scan_task_counts(_running["task_id"]) if _running.get("task_id") else {}
        return {
            "running": True,
            "task_id": _running["task_id"],
            "mode": _running.get("mode", "full"),
            "strategyType": _running.get("strategy_type", "STRATEGY_1_CUP_HANDLE"),
            "stats": {**_running.get("stats", {}), **summary},
        }
    running_task = db.get_running_task()
    if running_task:
        return {"running": True, "task_id": running_task["id"], "mode": "unknown",
                "strategyType": running_task.get("strategy_type", "STRATEGY_1_CUP_HANDLE"), "stats": {}}
    return {"running": False, "task_id": None, "strategyType": None, "stats": {}}


@app.get("/api/scan/tasks")
async def list_tasks():
    """FINAL-S2-005: Strategy1 task list — only S1 running + S1 DB tasks."""
    tasks = []
    # Only include running S1 task
    if _running["running"] and _running.get("strategy_type") == "STRATEGY_1_CUP_HANDLE":
        s = _running.get("stats", {})
        tasks.append({
            "id": _running.get("task_id", "current"),
            "date": _running.get("started_at", ""),
            "scope": f"全市场 · {s.get('total_stocks', '--')}只",
            "running": True,
            "status": "running",
            "candidates": s.get("candidates_found", 0),
            "failed": s.get("failed", 0),
            "skipped": s.get("skipped", 0),
            "scanned": s.get("scanned", 0),
            "total": s.get("total_stocks", 0),
            "stock_pool_source": s.get("stock_pool_source", ""),
            "latest_trade_date": s.get("latest_trade_date", ""),
            "duration": "",
            "strategy_type": "STRATEGY_1_CUP_HANDLE",
        })
    # Add completed scans from DB (skip the running one already added above)
    running_id = _running.get("task_id") if _running["running"] else None
    db_tasks = db.get_scan_tasks(strategy_type="STRATEGY_1_CUP_HANDLE")
    for t in db_tasks:
        if t["id"] != running_id:
            # Compute stats from candidates
            c = db.get_candidates(t["id"])
            if c:
                scores = [x["score"] for x in c]
                t["candidates"] = len(c)
                t["topScore"] = max(scores)
                t["avgScore"] = round(sum(scores)/len(scores), 1)
                t["aGrade"] = sum(1 for x in c if x["score"] >= 80)
                t["breakout"] = sum(1 for x in c if x.get("is_breakout"))
            else:
                t["candidates"] = 0
                t["topScore"] = 0
                t["avgScore"] = 0
                t["aGrade"] = 0
                t["breakout"] = 0
            tasks.append(t)
    return {"tasks": tasks}


@app.get("/api/scan/tasks/{task_id}/stocks")
async def get_task_stocks(task_id: str, status: str = None, page: int = 1, page_size: int = 100):
    """Returns task stocks with strategy_type. 404 if task not found."""
    s_type = db.get_task_strategy_type(task_id)
    if s_type is None:
        return JSONResponse(
            {"error": "TASK_NOT_FOUND", "task_id": task_id},
            status_code=404,
        )

    page = max(page, 1)
    page_size = min(max(page_size, 1), 500)
    offset = (page - 1) * page_size
    stocks = db.get_task_stocks(task_id, status=status, limit=page_size, offset=offset)
    full_summary = db.refresh_scan_task_counts(task_id)
    count = full_summary.get(status, 0) if status else full_summary.get("total_stocks", 0)
    return {
        "task_id": task_id, "strategy_type": s_type, "stocks": stocks, "total": count,
        "summary": full_summary, "page": page, "page_size": page_size,
    }


@app.post("/api/scan/tasks/{task_id}/retry-failed")
async def retry_failed_stocks(task_id: str):
    """FINAL-S2-001: 只接受 Strategy1 任务。Strategy2 返回明确错误。"""
    config = load_config()
    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)

    _, type_err = _require_task_strategy(task_id, "STRATEGY_1_CUP_HANDLE")
    if type_err is not None:
        return type_err

    conflict = _scan_conflict_response()
    if conflict:
        return conflict

    failed = db.get_failed_task_stocks(task_id)
    if not failed:
        return {"task_id": task_id, "status": "no_failed_stocks", "retry_count": 0}

    db.reset_failed_task_stocks(task_id)
    conn = db.get_conn()
    conn.execute("UPDATE scan_tasks SET status='running', retry_mode='failed_only' WHERE id=?", (task_id,))
    conn.commit()
    _set_running(task_id, "failed_only")

    stocks = [{"code": s["code"], "name": s["name"], "market": s.get("market", "")} for s in failed]

    def run_retry():
        import datetime
        try:
            result = scan_all(config, task_id=task_id, stocks=stocks, retry_policy="failed_only")
            s = result["stats"]
            db.finish_scan_task(
                task_id,
                finished_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                candidates_count=s.get("candidates_found", 0),
                elapsed_seconds=s.get("elapsed_seconds", 0),
                scanned=s.get("scanned", 0),
                skipped=s.get("skipped", 0),
            )
            db.refresh_scan_task_counts(task_id)
        except Exception as e:
            import traceback
            logger.error(f"Retry failed stocks failed: {e}\n{traceback.format_exc()}")
            conn = db.get_conn()
            conn.execute("UPDATE scan_tasks SET status='failed', error=? WHERE id=?", (str(e), task_id))
            conn.commit()
        finally:
            _clear_running()

    threading.Thread(target=run_retry, daemon=True).start()
    return {"task_id": task_id, "status": "retry_started", "retry_count": len(stocks)}


@app.post("/api/scan/tasks/{task_id}/re-evaluate")
async def re_evaluate_task_endpoint(task_id: str):
    """Re-run strategy evaluation on existing OHLC data.

    FINAL-S2-001: 只接受 Strategy1 任务。Strategy2 重评不在本期范围。
    """
    config = load_config()
    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)

    _, type_err = _require_task_strategy(task_id, "STRATEGY_1_CUP_HANDLE")
    if type_err is not None:
        return type_err

    conn = db.get_conn()
    task = conn.execute("SELECT id FROM scan_tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        return JSONResponse({"error": "Task not found"}, status_code=404)

    # Set status so frontend can show progress
    conn.execute("UPDATE scan_tasks SET status='re_evaluating' WHERE id=?", (task_id,))
    conn.commit()

    def run_re_eval():
        import datetime
        try:
            result = re_evaluate_task(config, task_id)
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn2 = db.get_conn()
            conn2.execute(
                "UPDATE scan_tasks SET status='completed', candidates_count=?, finished_at=? WHERE id=?",
                (result["candidates_found"], now, task_id),
            )
            conn2.commit()
            logger.info(
                "Re-evaluate %s: %d candidates (added %d, removed %d)",
                task_id, result["candidates_found"],
                result.get("added", 0), result.get("removed", 0),
            )
        except Exception as e:
            import traceback
            logger.error(f"Re-evaluate {task_id} failed: {e}\n{traceback.format_exc()}")
            conn2 = db.get_conn()
            conn2.execute("UPDATE scan_tasks SET status='completed', error=? WHERE id=?", (str(e), task_id))
            conn2.commit()

    threading.Thread(target=run_re_eval, daemon=True).start()
    return {"task_id": task_id, "status": "re_evaluating"}


@app.get("/api/candidates")
async def get_candidates(task_id: str = None):
    """FINAL-S2-001: 如果指定 task_id，只接受 Strategy1。"""
    config = load_config()
    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)

    if task_id:
        _, type_err = _require_task_strategy(task_id, "STRATEGY_1_CUP_HANDLE")
        if type_err is not None:
            return type_err

    # If a specific task is requested, always query DB
    if task_id:
        cands = db.get_candidates(task_id=task_id)
    elif _running.get("running") and _running.get("strategy_type") == "STRATEGY_1_CUP_HANDLE":
        # ACCEPT-S2-002: Only return S1 discoveries during S1 scan
        ds = _running.get("stats", {}).get("discoveries") or []
        return {"candidates": ds, "total": len(ds)}
    else:
        cands = db.get_candidates()
    result = []
    for c in cands:
        result.append({
            "code": c.get("code", ""),
            "name": c.get("name", ""),
            "score": c.get("score", 0),
            "rating": c.get("rating", ""),
            "dry_stable_verdict": c.get("dry_stable_verdict", ""),
            "dry_stable_summary": c.get("dry_stable_summary", ""),
            "volume_dry_score": c.get("volume_dry_score", 0),
            "price_stable_score": c.get("price_stable_score", 0),
            "pattern_score_20": c.get("pattern_score_20", 0),
            "pattern_type": c.get("pattern_type", ""),
            "key_pattern_type": c.get("key_pattern_type", ""),
            "cup_handle_score": c.get("cup_handle_score", 0),
            "vcp_score": c.get("vcp_score", 0),
            "vcp_contractions": c.get("vcp_contractions", 0),
            "risk_percent": c.get("risk_percent", 0),
            "rr1": c.get("rr1", 0),
            "position_advice": c.get("position_advice", ""),
            "entry_zone_low": c.get("entry_zone_low", 0),
            "entry_zone_high": c.get("entry_zone_high", 0),
            "pivot": c.get("pivot", 0),
            "stop_loss": c.get("stop_loss", 0),
            "target_1": c.get("target_1", 0),
            "target_2": c.get("target_2", 0),
            "market_status": c.get("market_status", ""),
            "market_position_advice": c.get("market_position_advice", ""),
            "is_breakout": bool(c.get("is_breakout", 0)),
            "is_volume_breakout": bool(c.get("is_volume_breakout", 0)),
            "latest_close": c.get("latest_close", 0),
            "breakout_price": c.get("breakout_price", 0),
            "cup_depth_pct": c.get("cup_depth_pct", 0),
            "handle_depth_pct": c.get("handle_depth_pct", 0),
            "cup_duration": c.get("cup_duration", 0),
            "vol_multiplier": c.get("vol_multiplier", 0),
            "verdict_key": c.get("verdict_key", ""),
            "positive_factors": c.get("positive_factors", ""),
            "warnings": c.get("warnings", ""),
            "reject_reasons": c.get("reject_reasons", ""),
            "raw_volume_dry_score": c.get("raw_volume_dry_score", 0),
            "raw_price_stable_score": c.get("raw_price_stable_score", 0),
            "score_caps": c.get("score_caps", ""),
        })
    return {"candidates": result, "total": len(result)}


@app.post("/api/stock/{code}/backtest/cup-handle")
async def backtest_cup_handle(code: str, payload: dict):
    """Run single-stock cup-handle strategy backtest."""
    config = load_config()
    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)
    try:
        specified = payload.get("specifiedHandle") or {}
        result = run_single_stock_cuphandle_backtest(
            code,
            payload.get("startDate", ""),
            payload.get("endDate", ""),
            config,
            handle_start_date=specified.get("startDate"),
            handle_end_date=specified.get("endDate"),
        )
        return result
    except ValueError as exc:
        return JSONResponse(
            {"error": "Invalid request", "message": str(exc)},
            status_code=400,
        )
    except DataCoverageError as exc:
        return JSONResponse(exc.to_dict(), status_code=422)
    except Exception as exc:
        logger.exception("Single stock cup-handle backtest failed")
        return JSONResponse(
            {"error": "Backtest failed", "message": str(exc)},
            status_code=500,
        )


@app.get("/api/stock/{code}/ohlc")
async def get_stock_ohlc(code: str):
    """Return full OHLC history for a stock from the database."""
    data = db.get_ohlc(code)
    if not data:
        return JSONResponse({"error": "No data"}, status_code=404)
    return {"code": code, "data": data}


@app.get("/api/candidate/{code}")
async def get_candidate(code: str):
    c = db.get_candidate(code)
    if not c:
        # ACCEPT-S2-002: Only search S1 discoveries during S1 scan
        if _running.get("running") and _running.get("strategy_type") == "STRATEGY_1_CUP_HANDLE":
            ds = _running.get("stats", {}).get("discoveries") or []
            for d in ds:
                if d.get("code") == code:
                    c = d
                    break
    if not c:
        return JSONResponse({"error": "Not found"}, status_code=404)
    trade_plan = {}
    current_analysis = None
    ohlc = db.get_ohlc(code)
    if ohlc:
        cfg = load_config()
        market_idx = cfg.get("market_environment", {}).get("index_symbol")
        # RECHECK-002: use unified resolver, not manual config read
        try:
            windows = resolve_strategy_windows(cfg)
        except ValueError as exc:
            return JSONResponse(
                {"error": f"Invalid window config: {exc}"},
                status_code=400,
            )
        strategy_data = select_strategy_window(ohlc, windows.scan_window_days)
        if strategy_data is not None:
            engine = CupHandleStrategyEngine(cfg)
            # COMPLETION-001: truncate market data to stock decision date
            market_data_full = fetch_market_index_daily(market_idx)
            market_data = select_market_window(
                market_data_full, strategy_data[-1]["date"],
            )
            evaluation = engine.evaluate_at(
                strategy_data, code=code, name=c.get("name", ""),
                market_data=market_data,
            )
            if evaluation.dry_stable:
                trade_plan = evaluation.dry_stable.get("trade_plan", {})
            current_analysis = evaluation.to_dict()

    return {
        "task_id": c.get("task_id", ""),
        "code": c.get("code", ""),
        "name": c.get("name", ""),
        "score": c.get("score", 0),
        "dry_stable_verdict": c.get("dry_stable_verdict", ""),
        "dry_stable_summary": c.get("dry_stable_summary", ""),
        "volume_dry_score": c.get("volume_dry_score", 0),
        "price_stable_score": c.get("price_stable_score", 0),
        "pattern_score_20": c.get("pattern_score_20", 0),
        "pattern_type": c.get("pattern_type", ""),
        "key_pattern_type": c.get("key_pattern_type", ""),
        "cup_handle_score": c.get("cup_handle_score", 0),
        "vcp_score": c.get("vcp_score", 0),
        "risk_percent": c.get("risk_percent", 0),
        "rr1": c.get("rr1", 0),
        "position_advice": c.get("position_advice", ""),
        "entry_zone_low": c.get("entry_zone_low", 0),
        "entry_zone_high": c.get("entry_zone_high", 0),
        "pivot": c.get("pivot", 0),
        "stop_loss": c.get("stop_loss", 0),
        "target_1": c.get("target_1", 0),
        "target_2": c.get("target_2", 0),
        "market_status": c.get("market_status", ""),
        "market_position_advice": c.get("market_position_advice", ""),
        "left_high_price": c.get("left_high_price", 0),
        "cup_low_price": c.get("cup_low_price", 0),
        "right_high_price": c.get("right_high_price", 0),
        "handle_low_price": c.get("handle_low_price", 0),
        "left_high_date": c.get("left_high_date", ""),
        "cup_low_date": c.get("cup_low_date", ""),
        "right_high_date": c.get("right_high_date", ""),
        "handle_low_date": c.get("handle_low_date", ""),
        "cup_depth_pct": c.get("cup_depth_pct", 0),
        "handle_depth_pct": c.get("handle_depth_pct", 0),
        "cup_duration": c.get("cup_duration", 0),
        "handle_duration": c.get("handle_duration", 0),
        "is_breakout": bool(c.get("is_breakout", 0)),
        "is_volume_breakout": bool(c.get("is_volume_breakout", 0)),
        "vol_multiplier": c.get("vol_multiplier", 0),
        "latest_close": c.get("latest_close", 0),
        "latest_turnover": c.get("latest_turnover", 0),
        "lip_deviation_pct": c.get("lip_deviation_pct", 0),
        "verdict_key": c.get("verdict_key", ""),
        "positive_factors": c.get("positive_factors", ""),
        "warnings": c.get("warnings", ""),
        "reject_reasons": c.get("reject_reasons", ""),
        "raw_volume_dry_score": c.get("raw_volume_dry_score", 0),
        "raw_price_stable_score": c.get("raw_price_stable_score", 0),
        "score_caps": c.get("score_caps", ""),
        "trade_plan": trade_plan,
        "analysis_notice": "详情分析基于当前策略配置重新计算，可能与扫描任务产生时的结果不同。",
        "current_analysis": current_analysis,
    }


def _candidate_to_pattern_result(c: dict) -> CupHandleResult:
    """Rebuild a pattern result from persisted candidate fields for detail analysis."""
    return CupHandleResult(
        found=c.get("key_pattern_type") != "vcp",
        code=c.get("code", ""),
        name=c.get("name", ""),
        score=c.get("score", 0),
        cup_depth_pct=c.get("cup_depth_pct", 0) or 0,
        cup_duration=c.get("cup_duration", 0) or 0,
        handle_depth_pct=c.get("handle_depth_pct", 0) or 0,
        handle_duration=c.get("handle_duration", 0) or 0,
        lip_deviation_pct=c.get("lip_deviation_pct", 0) or 0,
        left_high_price=c.get("left_high_price", 0) or 0,
        cup_low_price=c.get("cup_low_price", 0) or 0,
        right_high_price=c.get("right_high_price", 0) or 0,
        handle_low_price=c.get("handle_low_price", 0) or 0,
        left_high_date=c.get("left_high_date", "") or "",
        cup_low_date=c.get("cup_low_date", "") or "",
        right_high_date=c.get("right_high_date", "") or "",
        handle_low_date=c.get("handle_low_date", "") or "",
        is_breakout=bool(c.get("is_breakout", 0)),
        is_volume_breakout=bool(c.get("is_volume_breakout", 0)),
        breakout_price=c.get("breakout_price", 0) or 0,
        vol_multiplier=c.get("vol_multiplier", 0) or 0,
    )


@app.get("/api/config")
async def get_config():
    """Return current configuration (excluding sensitive fields)."""
    config = load_config()
    return {"config": config}


@app.put("/api/config")
async def update_config(data: dict):
    """Update configuration and write to config.yaml.

    Accepts partial config updates. Only specified fields are changed.
    """
    config = load_config()

    # Deep merge: only update provided keys
    _deep_merge(config, data)

    # Validate strategy windows before saving (BUG-004)
    try:
        resolve_strategy_windows(config)
    except ValueError as e:
        return JSONResponse(
            {"status": "error", "message": f"Invalid window config: {e}"},
            status_code=400,
        )

    # Validate strategy2 config before saving (BUG-S2-006)
    if config.get("strategy2", {}).get("enabled", True):
        try:
            resolve_strategy2_config(config)
        except ValueError as e:
            return JSONResponse(
                {"status": "error", "message": f"Invalid strategy2 config: {e}"},
                status_code=400,
            )

    # Write back to config.yaml
    with open("config.yaml", "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    logger.info("Configuration updated")
    return {"status": "ok", "message": "配置已保存"}


@app.websocket("/ws/scan")
async def scan_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.receive_text()
            # Count candidates from running stats
            cand_count = _running.get("stats", {}).get("candidates_found", 0)
            await websocket.send_json({
                "running": _running["running"],
                "stats": _running["stats"],
                "candidate_count": cand_count,
            })
    except WebSocketDisconnect:
        pass


# ====== Strategy2 API ======

@app.post("/api/strategy2/scans")
async def start_strategy2_scan():
    """启动策略2全市场扫描。"""
    import datetime
    from scanner.stock_pool import get_a_stock_pool_result

    config = load_config()
    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)

    strategy2_cfg = config.get("strategy2", {})
    if not strategy2_cfg.get("enabled", True):
        return JSONResponse(
            {"error": "STRATEGY2_DISABLED", "message": "策略2未启用"},
            status_code=400,
        )

    # Validate strategy2 config before creating task (BUG-S2-006)
    try:
        resolve_strategy2_config(config)
    except ValueError as e:
        return JSONResponse(
            {"error": "INVALID_CONFIG", "message": f"策略2配置无效: {e}"},
            status_code=400,
        )

    conflict = _scan_conflict_response()
    if conflict:
        return conflict

    task_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    started_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.create_scan_task(task_id, started_at, total_stocks=0, retry_mode="full",
                        strategy_type="STRATEGY_2_EXTREME_DRY_STABLE")
    _set_running(task_id, "full", strategy_type="STRATEGY_2_EXTREME_DRY_STABLE")
    _running["started_at"] = started_at
    _running["stats"] = {"total_stocks": 0, "current_code": "--", "current_name": "获取股票池中…"}

    def run():
        pool_result = get_a_stock_pool_result(config)
        stocks = pool_result["stocks"]
        if not stocks:
            _running["stats"] = {"error": "No stock pool available"}
            conn = db.get_conn()
            conn.execute("UPDATE scan_tasks SET status='failed', error=? WHERE id=?", ("No stock pool", task_id))
            conn.commit()
            _clear_running()
            return
        db.update_scan_task_total(task_id, len(stocks), pool_result["source"])
        db.save_task_stocks(task_id, stocks)
        _running["stats"] = {
            "total_stocks": len(stocks),
            "stock_pool_source": pool_result["source"],
            "current_code": "--",
            "current_name": "初始化中",
        }
        try:
            def on_progress(stage, current, total, detail, discovery=None):
                stats = _running.get("stats", {})
                if stage == "discovery" and discovery:
                    found = stats.get("candidates_found", 0) + 1
                    discoveries = list(stats.get("discoveries") or [])
                    discoveries.insert(0, {
                        "code": discovery["code"],
                        "name": discovery["name"],
                        "total_score": discovery["total_score"],
                        "level": discovery["level"],
                        "volume_dry_score": discovery["volume_dry_score"],
                        "price_stable_score": discovery["price_stable_score"],
                        "risk_ratio": discovery["risk_ratio"],
                    })
                    _running["stats"] = {**stats, "discoveries": discoveries[:20], "candidates_found": found}
                else:
                    code = detail.split()[0] if detail else ""
                    s = stats.copy()
                    s.update({
                        "scanned": current, "processed": current, "total_stocks": total,
                        "current_code": code,
                        "current_name": detail[len(code):].strip() if len(detail) > len(code) else detail,
                    })
                    s.setdefault("candidates_found", 0)
                    s.setdefault("skipped", 0)
                    s.setdefault("failed", 0)
                    _running["stats"] = s
                db.update_scan_progress(
                    task_id,
                    scanned=_running["stats"].get("scanned", 0),
                    skipped=_running["stats"].get("skipped", 0),
                    candidates_count=_running["stats"].get("candidates_found", 0),
                )

            result = scan_strategy2_all(config, progress_callback=on_progress, task_id=task_id, stocks=stocks)
            s = result["stats"]
            _running["stats"] = s
            db.finish_scan_task(
                task_id,
                finished_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                candidates_count=s.get("candidates_found", 0),
                elapsed_seconds=s.get("elapsed_seconds", 0),
                scanned=s.get("scanned", 0),
                skipped=s.get("skipped", 0),
            )
            db.refresh_scan_task_counts(task_id)
        except Exception as e:
            import traceback
            logger.error(f"Strategy2 scan failed: {e}\n{traceback.format_exc()}")
            _running["stats"] = {"error": str(e)}
            conn = db.get_conn()
            conn.execute("UPDATE scan_tasks SET status='failed', error=? WHERE id=?", (str(e), task_id))
            conn.commit()
        finally:
            _clear_running()

    t = threading.Thread(target=run, daemon=True)
    t.start()

    return {
        "taskId": task_id,
        "strategyType": "STRATEGY_2_EXTREME_DRY_STABLE",
        "status": "running",
    }


@app.get("/api/strategy2/scans/status")
async def strategy2_scan_status():
    """查询策略2扫描状态。"""
    if _running["running"] and _running.get("strategy_type") == "STRATEGY_2_EXTREME_DRY_STABLE":
        summary = db.refresh_scan_task_counts(_running["task_id"]) if _running.get("task_id") else {}
        return {
            "running": True,
            "taskId": _running["task_id"],
            "strategyType": "STRATEGY_2_EXTREME_DRY_STABLE",
            "stats": {**_running.get("stats", {}), **summary},
        }
    # Check DB for running strategy2 tasks
    conn = db.get_conn()
    row = conn.execute(
        "SELECT id FROM scan_tasks WHERE status='running' AND strategy_type='STRATEGY_2_EXTREME_DRY_STABLE' ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    if row:
        return {"running": True, "taskId": row[0], "strategyType": "STRATEGY_2_EXTREME_DRY_STABLE", "stats": {}}
    return {"running": False, "taskId": None, "strategyType": "STRATEGY_2_EXTREME_DRY_STABLE", "stats": {}}


@app.get("/api/strategy2/tasks")
async def strategy2_tasks():
    """查询策略2任务列表（FINAL-S2-005: 隔离S1运行中任务）。"""
    tasks = []
    # Only include running S2 task
    if _running["running"] and _running.get("strategy_type") == "STRATEGY_2_EXTREME_DRY_STABLE":
        s = _running.get("stats", {})
        tasks.append({
            "id": _running.get("task_id", "current"),
            "date": _running.get("started_at", ""),
            "scope": f"全市场 · {s.get('total_stocks', '--')}只",
            "running": True,
            "status": "running",
            "candidates": s.get("candidates_found", 0),
            "total": s.get("total_stocks", 0),
            "scanned": s.get("scanned", 0),
            "skipped": s.get("skipped", 0),
            "failed": s.get("failed", 0),
            "strategy_type": "STRATEGY_2_EXTREME_DRY_STABLE",
        })

    running_id = _running.get("task_id") if _running["running"] else None
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT id, started_at, finished_at, status, total_stocks, scanned, skipped, "
        "candidates_count, elapsed_seconds, failed_count, stock_pool_source, latest_trade_date, strategy_type "
        "FROM scan_tasks WHERE strategy_type='STRATEGY_2_EXTREME_DRY_STABLE' ORDER BY started_at DESC"
    ).fetchall()
    for r in rows:
        if r[0] == running_id:
            continue
        tasks.append({
            "id": r[0], "date": r[1] or "", "finished_at": r[2],
            "running": r[3] == 'running', "status": r[3],
            "total_stocks": r[4], "scanned": r[5], "total": r[4],
            "skipped": r[6], "candidates": r[7], "elapsed_seconds": r[8],
            "duration": f"{r[8]:.0f}s" if r[8] is not None else None,
            "failed": r[9], "stock_pool_source": r[10], "latest_trade_date": r[11],
            "strategy_type": r[12] or "STRATEGY_2_EXTREME_DRY_STABLE",
        })
    return {"tasks": tasks}


@app.post("/api/strategy2/tasks/{task_id}/retry-failed")
async def strategy2_retry_failed_stocks(task_id: str):
    """重试策略2任务中失败的股票。"""
    config = load_config()
    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)

    _, type_err = _require_task_strategy(task_id, "STRATEGY_2_EXTREME_DRY_STABLE")
    if type_err is not None:
        return type_err

    conflict = _scan_conflict_response()
    if conflict:
        return conflict

    failed = db.get_failed_task_stocks(task_id)
    if not failed:
        return {"task_id": task_id, "status": "no_failed_stocks", "retry_count": 0}

    db.reset_failed_task_stocks(task_id)
    conn = db.get_conn()
    conn.execute("UPDATE scan_tasks SET status='running', retry_mode='failed_only' WHERE id=?", (task_id,))
    conn.commit()
    _set_running(task_id, "failed_only", strategy_type="STRATEGY_2_EXTREME_DRY_STABLE")

    stocks = [{"code": s["code"], "name": s["name"], "market": s.get("market", "")} for s in failed]

    def run_retry():
        import datetime
        try:
            from strategy2.scanner import scan_strategy2_all
            result = scan_strategy2_all(config, task_id=task_id, stocks=stocks, retry_policy="failed_only")
            s = result["stats"]
            db.finish_scan_task(
                task_id,
                finished_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                candidates_count=s.get("candidates_found", 0),
                elapsed_seconds=s.get("elapsed_seconds", 0),
                scanned=s.get("scanned", 0),
                skipped=s.get("skipped", 0),
            )
            db.refresh_scan_task_counts(task_id)
        except Exception as e:
            import traceback
            logger.error(f"Strategy2 retry failed stocks failed: {e}\n{traceback.format_exc()}")
            conn = db.get_conn()
            conn.execute("UPDATE scan_tasks SET status='failed', error=? WHERE id=?", (str(e), task_id))
            conn.commit()
        finally:
            _clear_running()

    threading.Thread(target=run_retry, daemon=True).start()
    return {"task_id": task_id, "status": "retry_started", "retry_count": len(stocks)}


@app.post("/api/strategy2/tasks/{task_id}/re-evaluate")
async def strategy2_re_evaluate(task_id: str):
    """用已缓存日线数据重跑策略2评估，不重新拉取数据。"""
    config = load_config()
    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)

    _, type_err = _require_task_strategy(task_id, "STRATEGY_2_EXTREME_DRY_STABLE")
    if type_err is not None:
        return type_err

    conn = db.get_conn()
    task = conn.execute("SELECT id FROM scan_tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        return JSONResponse({"error": "Task not found"}, status_code=404)

    conn.execute("UPDATE scan_tasks SET status='re_evaluating' WHERE id=?", (task_id,))
    conn.commit()

    def run_re_eval():
        import datetime
        try:
            from strategy2.scanner import re_evaluate_strategy2_task
            result = re_evaluate_strategy2_task(config, task_id)
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn2 = db.get_conn()
            conn2.execute(
                "UPDATE scan_tasks SET status='completed', candidates_count=?, finished_at=? WHERE id=?",
                (result["candidates_found"], now, task_id),
            )
            conn2.commit()
            logger.info(
                "Strategy2 re-evaluate %s: %d candidates (added %d, removed %d)",
                task_id, result["candidates_found"],
                result.get("added", 0), result.get("removed", 0),
            )
        except Exception as e:
            import traceback
            logger.error(f"Strategy2 re-evaluate {task_id} failed: {e}\n{traceback.format_exc()}")
            conn2 = db.get_conn()
            conn2.execute("UPDATE scan_tasks SET status='completed', error=? WHERE id=?", (str(e), task_id))
            conn2.commit()

    threading.Thread(target=run_re_eval, daemon=True).start()
    return {"task_id": task_id, "status": "re_evaluating"}


@app.get("/api/strategy2/candidates")
async def strategy2_candidates(task_id: str = None):
    """查询策略2候选列表（RECHECK-S2-003: 验证任务类型）。"""
    config = load_config()
    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)

    if task_id:
        s_type = db.get_task_strategy_type(task_id)
        if s_type is None:
            return JSONResponse({"error": "TASK_NOT_FOUND", "message": "任务不存在"}, status_code=404)
        if s_type != "STRATEGY_2_EXTREME_DRY_STABLE":
            return JSONResponse(
                {"error": "TASK_STRATEGY_MISMATCH", "message": f"任务 {task_id} 不是策略2任务"},
                status_code=400,
            )

    if _running["running"] and _running.get("strategy_type") == "STRATEGY_2_EXTREME_DRY_STABLE" and not task_id:
        ds = _running.get("stats", {}).get("discoveries") or []
        return {"candidates": ds, "total": len(ds)}

    cands = db.get_strategy2_candidates(task_id=task_id)
    return {"candidates": cands, "total": len(cands)}


@app.get("/api/strategy2/candidates/{code}")
async def strategy2_candidate_detail(code: str, task_id: str = None):
    """查询策略2候选详情（RECHECK-S2-003: 验证任务类型）。"""
    config = load_config()
    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)

    if task_id:
        s_type = db.get_task_strategy_type(task_id)
        if s_type is None:
            return JSONResponse({"error": "TASK_NOT_FOUND", "message": "任务不存在"}, status_code=404)
        if s_type != "STRATEGY_2_EXTREME_DRY_STABLE":
            return JSONResponse(
                {"error": "TASK_STRATEGY_MISMATCH", "message": f"任务 {task_id} 不是策略2任务"},
                status_code=400,
            )

    c = db.get_strategy2_candidate(code, task_id=task_id)
    if not c:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return c


# ═══════════════════════════════════════════════════════════════════════════════
# Strategy2 Backtest API
# ═══════════════════════════════════════════════════════════════════════════════

def _backtest_conflict_response():
    """Return 409 if any scan or backtest is running."""
    if _running["running"]:
        return JSONResponse({
            "error": "TASK_CONFLICT",
            "message": "当前已有扫描任务正在运行",
            "runningTaskId": _running["task_id"],
        }, status_code=409)
    if _backtest_running["running"]:
        return JSONResponse({
            "error": "TASK_CONFLICT",
            "message": "当前已有策略2回测任务正在运行",
            "runningTaskId": _backtest_running["task_id"],
        }, status_code=409)
    return None


def _backtest_payload_from_task(task: dict) -> dict:
    return {
        "startDate": task.get("requested_start_date", ""),
        "endDate": task.get("requested_end_date", ""),
        "maxStocks": task.get("max_stocks"),
        "codes": [code for code in (task.get("requested_codes") or "").split(",") if code],
        "executionModel": task.get("execution_model", "NEXT_OPEN"),
    }


def _launch_strategy2_backtest_task(
    *,
    task_id: str,
    target_stocks: list[dict],
    config_snapshot: dict,
    payload_snapshot: dict,
    data_snapshot_date: str,
    mode: str,
):
    """启动统一策略2回测执行器。"""
    from strategy2.backtest_service import run_strategy2_backtest_task

    cancel_event = threading.Event()
    _backtest_running.update({
        "running": True,
        "task_id": task_id,
        "started_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "cancel_event": cancel_event,
        "stats": {
            "total_stocks": len(target_stocks),
            "processed_stocks": 0,
            "current_code": "--",
            "current_name": "--",
            "opportunities_count": 0,
            "insufficient_stocks_count": 0,
        },
    })
    db.update_strategy2_backtest_task(
        task_id,
        status="running",
        credibility_status="RUNNING_UNVERIFIED",
        total_stocks=len(db.get_strategy2_backtest_task_stocks(task_id)),
        error=None,
        finished_at=None,
    )

    def worker():
        try:
            run_strategy2_backtest_task(
                task_id=task_id,
                target_stocks=target_stocks,
                config_snapshot=config_snapshot,
                payload_snapshot=payload_snapshot,
                data_snapshot_date=data_snapshot_date,
                cancel_event=cancel_event,
                running_state=_backtest_running,
                mode=mode,
            )
        except Exception:
            logger.exception("Strategy2 backtest task %s failed", task_id)
        finally:
            if _backtest_running.get("task_id") == task_id:
                _backtest_running["running"] = False
                _backtest_running["task_id"] = None
                _backtest_running["thread"] = None

    thread = threading.Thread(target=worker, daemon=True)
    _backtest_running["thread"] = thread
    thread.start()


def _launch_strategy1_backtest_task(
    *,
    task_id: str,
    target_stocks: list[dict],
    config_snapshot: dict,
    payload_snapshot: dict,
):
    """启动策略1本地数据库回测执行器。"""
    from scanner.strategy1_backtest_service import run_strategy1_backtest_task

    _backtest_running.update({
        "running": True,
        "task_id": task_id,
        "started_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "cancel_event": None,
        "stats": {
            "total_stocks": len(target_stocks),
            "processed_stocks": 0,
            "current_code": "--",
            "current_name": "--",
            "opportunities_count": 0,
        },
    })

    def worker():
        try:
            run_strategy1_backtest_task(
                task_id=task_id,
                target_stocks=target_stocks,
                config_snapshot=config_snapshot,
                payload_snapshot=payload_snapshot,
                running_state=_backtest_running,
            )
        except Exception:
            logger.exception("Strategy1 backtest task %s failed", task_id)
        finally:
            if _backtest_running.get("task_id") == task_id:
                _backtest_running["running"] = False
                _backtest_running["task_id"] = None
                _backtest_running["thread"] = None

    thread = threading.Thread(target=worker, daemon=True)
    _backtest_running["thread"] = thread
    thread.start()


@app.post("/api/strategy1/backtests/experiments/preview")
async def strategy1_backtest_experiment_preview(payload: dict):
    """预览并校验策略1实验配置。"""
    from scanner.strategy1_backtest_experiments import (
        is_experiment_enabled,
        normalize_experiment_config,
    )

    try:
        normalized = normalize_experiment_config(payload)
    except ValueError as exc:
        return JSONResponse({"valid": False, "error": str(exc)}, status_code=422)
    return {
        "valid": True,
        "normalizedExperiment": normalized,
        "credibilityStatus": "EXPERIMENTAL" if is_experiment_enabled(normalized) else "INCOMPLETE",
    }


@app.post("/api/strategy1/backtests")
async def start_strategy1_backtest(payload: dict):
    """启动策略1本地数据库可信回测。"""
    import random as _random
    import string as _string

    from scanner.strategy1_backtest_experiments import (
        is_experiment_enabled,
        normalize_experiment_config,
    )
    from scanner.strategy1_backtest_service import (
        STRATEGY1_BACKTEST_ENGINE_VERSION,
        STRATEGY1_STRATEGY_ENGINE_VERSION,
        calculate_strategy1_daily_ohlc_revision,
    )

    config = load_config()
    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)

    conflict = _backtest_conflict_response()
    if conflict:
        return conflict

    try:
        resolve_strategy_windows(config)
    except ValueError as exc:
        return JSONResponse({"error": "INVALID_CONFIG", "message": str(exc)}, status_code=400)

    try:
        experiment = normalize_experiment_config(payload.get("experiment"))
    except ValueError as exc:
        return JSONResponse({"error": "INVALID_EXPERIMENT", "message": str(exc)}, status_code=422)

    start_date = payload.get("startDate", "")
    end_date = payload.get("endDate", "")
    if start_date and end_date and start_date > end_date:
        return JSONResponse({"error": "INVALID_PARAM", "message": "startDate must be <= endDate"}, status_code=422)

    conn = db.get_conn()
    if conn.execute("SELECT COUNT(*) FROM daily_ohlc").fetchone()[0] == 0:
        return JSONResponse({"error": "NO_LOCAL_DATA", "message": "本地数据库无日线数据"}, status_code=400)

    codes = payload.get("codes") or []
    max_stocks = payload.get("maxStocks")
    if codes:
        pool_by_code = {stock["code"]: stock for stock in db.get_stock_pool()}
        target_stocks = [
            {"code": code, "name": pool_by_code.get(code, {}).get("name", "")}
            for code in codes
        ]
    else:
        pool = db.get_stock_pool()
        if pool:
            target_stocks = [{"code": stock["code"], "name": stock.get("name", "")} for stock in pool]
        else:
            target_stocks = [
                {"code": row[0], "name": ""}
                for row in conn.execute("SELECT DISTINCT code FROM daily_ohlc ORDER BY code").fetchall()
            ]
    if max_stocks:
        target_stocks = target_stocks[: int(max_stocks)]
    if not target_stocks:
        return JSONResponse({"error": "NO_STOCKS", "message": "没有可回测股票"}, status_code=400)

    suffix = ''.join(_random.choices(_string.ascii_lowercase + _string.digits, k=6))
    task_id = datetime.datetime.now().strftime(f"s1bt-%Y%m%d-%H%M%S-{suffix}")
    payload_snapshot = {**payload, "experiment": experiment, "experiment_snapshot": experiment}
    db.create_strategy1_backtest_task(task_id, payload_snapshot, json.dumps(config, ensure_ascii=False))
    db.update_strategy1_backtest_task(
        task_id,
        status="running",
        credibility_status="EXPERIMENTAL" if is_experiment_enabled(experiment) else "RUNNING_UNVERIFIED",
        total_stocks=len(target_stocks),
        backtest_engine_version=STRATEGY1_BACKTEST_ENGINE_VERSION,
        strategy_engine_version=STRATEGY1_STRATEGY_ENGINE_VERSION,
        execution_model=experiment.get("execution_model", "NEXT_OPEN"),
    )
    for stock in target_stocks:
        db.replace_strategy1_stock_backtest_result(
            task_id,
            stock["code"],
            stock.get("name", ""),
            {"status": "PENDING"},
        )
    data_revision_id = calculate_strategy1_daily_ohlc_revision(task_id)
    db.update_strategy1_backtest_task(
        task_id,
        data_revision_id=data_revision_id,
        data_revision_version=db.STRATEGY1_DATA_REVISION_VERSION,
    )

    _launch_strategy1_backtest_task(
        task_id=task_id,
        target_stocks=target_stocks,
        config_snapshot=config,
        payload_snapshot=payload_snapshot,
    )
    return {
        "task_id": task_id,
        "taskId": task_id,
        "status": "running",
        "credibilityStatus": "EXPERIMENTAL" if is_experiment_enabled(experiment) else "RUNNING_UNVERIFIED",
    }


@app.get("/api/strategy1/backtests")
async def strategy1_backtests(page: int = 1, page_size: int = 20, status: str = None):
    config = load_config()
    db.init_db(config.get("data", {}).get("database_path", "data/cuphandle.db"))
    tasks, total = db.get_strategy1_backtest_tasks(page=page, page_size=page_size, status=status)
    return {"tasks": tasks, "total": total, "page": page, "pageSize": page_size}


@app.get("/api/strategy1/backtests/status")
async def strategy1_backtest_status():
    running = bool(_backtest_running.get("running") and str(_backtest_running.get("task_id") or "").startswith("s1bt-"))
    return {
        "running": running,
        "taskId": _backtest_running.get("task_id") if running else None,
        "stats": _backtest_running.get("stats", {}) if running else {},
    }


@app.get("/api/strategy1/backtests/{task_id}/comparison")
async def strategy1_backtest_comparison(task_id: str, baselineTaskId: str):
    config = load_config()
    db.init_db(config.get("data", {}).get("database_path", "data/cuphandle.db"))
    result = db.compare_strategy1_backtest_tasks(task_id, baselineTaskId)
    db.update_strategy1_backtest_task(
        task_id,
        comparison_summary_json=json.dumps(result, ensure_ascii=False),
        baseline_task_id=baselineTaskId,
    )
    return result


@app.get("/api/strategy1/backtests/{task_id}")
async def strategy1_backtest_detail(task_id: str):
    config = load_config()
    db.init_db(config.get("data", {}).get("database_path", "data/cuphandle.db"))
    task = db.get_strategy1_backtest_task(task_id)
    if not task:
        return JSONResponse({"error": "TASK_NOT_FOUND"}, status_code=404)
    return {"task": task, "summary": json.loads(task["summary_json"]) if task.get("summary_json") else None}


@app.get("/api/strategy1/backtests/{task_id}/opportunities")
async def strategy1_backtest_opportunities(task_id: str, code: str = None, limit: int = 500, offset: int = 0):
    config = load_config()
    db.init_db(config.get("data", {}).get("database_path", "data/cuphandle.db"))
    total = db.get_conn().execute(
        "SELECT COUNT(*) FROM strategy1_backtest_opportunities WHERE task_id=?",
        (task_id,),
    ).fetchone()[0]
    return {
        "opportunities": db.get_strategy1_backtest_opportunities(task_id, code=code, limit=limit, offset=offset),
        "total": total,
    }


@app.get("/api/strategy1/backtests/{task_id}/signals")
async def strategy1_backtest_signals(task_id: str, code: str = None, limit: int = 500, offset: int = 0):
    config = load_config()
    db.init_db(config.get("data", {}).get("database_path", "data/cuphandle.db"))
    conn = db.get_conn()
    if code:
        total = conn.execute(
            "SELECT COUNT(*) FROM strategy1_backtest_signals WHERE task_id=? AND code=?",
            (task_id, code),
        ).fetchone()[0]
    else:
        total = conn.execute(
            "SELECT COUNT(*) FROM strategy1_backtest_signals WHERE task_id=?",
            (task_id,),
        ).fetchone()[0]
    return {
        "signals": db.get_strategy1_backtest_signals(task_id, code=code, limit=limit, offset=offset),
        "total": total,
    }


@app.get("/api/strategy1/backtests/{task_id}/stocks")
async def strategy1_backtest_stocks(task_id: str, status: str = None):
    config = load_config()
    db.init_db(config.get("data", {}).get("database_path", "data/cuphandle.db"))
    stocks = db.get_strategy1_backtest_task_stocks(task_id, status=status)
    return {"stocks": stocks, "total": len(stocks)}


@app.post("/api/strategy2/backtests")
async def start_strategy2_backtest(payload: dict):
    """启动策略2本地数据库短线回测。"""
    config = load_config()
    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)

    conflict = _backtest_conflict_response()
    if conflict:
        return conflict

    # ── 参数验证（请求线程内同步完成）──
    import random as _random, string as _string
    codes = payload.get("codes") or []
    has_max = "maxStocks" in payload
    max_stocks_raw = payload.get("maxStocks")

    if has_max and max_stocks_raw is None:
        max_stocks_val = None  # 显式 null → 全市场
    elif not has_max:
        max_stocks_val = 200   # 未传 → 默认 200
    elif isinstance(max_stocks_raw, (int, float)) and max_stocks_raw > 0:
        max_stocks_val = int(max_stocks_raw)
    else:
        return JSONResponse({"error": "INVALID_PARAM", "message": "maxStocks must be positive integer or null"}, status_code=422)

    # 验证日期
    start_date = payload.get("startDate", "")
    end_date = payload.get("endDate", "")
    if start_date and end_date and start_date > end_date:
        return JSONResponse({"error": "INVALID_PARAM", "message": "startDate must be <= endDate"}, status_code=422)

    from strategy2.backtest_experiments import normalize_experiment_config, is_experiment_enabled
    try:
        experiment_snapshot = normalize_experiment_config(payload.get("experiment"))
    except ValueError as exc:
        return JSONResponse({"error": "INVALID_EXPERIMENT", "message": str(exc)}, status_code=422)
    payload = {**payload, "experiment": experiment_snapshot, "experiment_snapshot": experiment_snapshot}
    experiment_enabled = is_experiment_enabled(experiment_snapshot)

    # 检查数据库
    conn = db.get_conn()
    has_data = conn.execute("SELECT COUNT(*) FROM daily_ohlc").fetchone()[0]
    if has_data == 0:
        return JSONResponse({"error": "NO_LOCAL_DATA", "message": "本地数据库无日线数据"}, status_code=400)

    # ── 解析股票范围（请求线程内完成，不跨线程用 conn）──
    if codes:
        resolved_stocks = [{"code": c, "name": ""} for c in codes]
        if max_stocks_val:
            resolved_stocks = resolved_stocks[:max_stocks_val]
    else:
        pool = db.get_stock_pool()
        if not pool:
            codes_list = [r[0] for r in conn.execute("SELECT DISTINCT code FROM daily_ohlc").fetchall()]
            resolved_stocks = [{"code": c, "name": ""} for c in codes_list]
        else:
            resolved_stocks = [{"code": s["code"], "name": s.get("name", "")} for s in pool]
        if max_stocks_val:
            resolved_stocks = resolved_stocks[:max_stocks_val]

    # ── 创建任务 ──
    suffix = ''.join(_random.choices(_string.ascii_lowercase + _string.digits, k=6))
    task_id = datetime.datetime.now().strftime(f"s2bt-%Y%m%d-%H%M%S-{suffix}")
    data_snapshot_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    config_json = json.dumps(config, ensure_ascii=False)
    db.create_strategy2_backtest_task(task_id, payload, config_json)
    from strategy2.version import (
        STRATEGY2_BACKTEST_ENGINE_VERSION,
        STRATEGY2_STRATEGY_ENGINE_VERSION,
    )
    db.update_strategy2_backtest_task(task_id, status="running",
        backtest_engine_version=STRATEGY2_BACKTEST_ENGINE_VERSION,
        strategy_engine_version=STRATEGY2_STRATEGY_ENGINE_VERSION,
        credibility_status="EXPERIMENTAL" if experiment_enabled else "RUNNING_UNVERIFIED",
        execution_model=payload.get("executionModel", "NEXT_OPEN"),
        data_snapshot_date=data_snapshot_date)

    # 初始化所有股票的 PENDING 状态
    for s in resolved_stocks:
        db.save_strategy2_backtest_task_stock(task_id, s["code"],
            name=s.get("name", ""), status="PENDING")

    from strategy2.backtest_service import calculate_task_daily_ohlc_revision
    data_revision_id = calculate_task_daily_ohlc_revision(task_id, data_snapshot_date)
    db.update_strategy2_backtest_task(
        task_id,
        data_revision_id=data_revision_id,
        data_revision_version=db.STRATEGY2_DATA_REVISION_VERSION,
    )
    _launch_strategy2_backtest_task(
        task_id=task_id,
        target_stocks=resolved_stocks,
        config_snapshot=config,
        payload_snapshot=payload,
        data_snapshot_date=data_snapshot_date,
        mode="start",
    )
    return {
        "task_id": task_id, "status": "started",
        "credibilityStatus": "EXPERIMENTAL" if experiment_enabled else "RUNNING_UNVERIFIED",
        "baselineTaskId": payload.get("baselineTaskId"),
        "maxStocks": payload.get("maxStocks", 200),
        "message": "回测任务已启动，只使用本地数据库数据",
    }


@app.post("/api/strategy2/backtests/experiments/preview")
async def strategy2_backtest_experiment_preview(payload: dict):
    """Validate and normalize a Strategy2 experiment payload."""
    config = load_config()
    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)
    from strategy2.backtest_experiments import normalize_experiment_config, is_experiment_enabled
    try:
        normalized = normalize_experiment_config(payload)
    except ValueError as exc:
        return JSONResponse(
            {"valid": False, "error": "INVALID_EXPERIMENT", "message": str(exc)},
            status_code=422,
        )
    return {
        "valid": True,
        "normalizedExperiment": normalized,
        "credibilityStatus": "EXPERIMENTAL" if is_experiment_enabled(normalized) else "RUNNING_UNVERIFIED",
        "warnings": [
            "实验任务不会影响正式扫描规则",
            "实验结论需要与可信基线对比",
        ],
    }

@app.get("/api/strategy2/backtests/status")
async def strategy2_backtest_status():
    """查询当前回测运行状态。"""
    if _backtest_running["running"]:
        return {
            "running": True,
            "taskId": _backtest_running["task_id"],
            "stats": _backtest_running["stats"],
        }
    return {"running": False, "taskId": None, "stats": {}}


@app.get("/api/strategy2/backtests")
async def strategy2_backtests(page: int = 1, page_size: int = 20, status: str = None):
    """查询历史回测任务列表（摘要，不含 config/summary 大字段）。"""
    tasks, total = db.get_strategy2_backtest_tasks(page=page, page_size=page_size, status=status)
    for t in tasks:
        t.pop("config_snapshot", None)
        t.pop("summary_json", None)
    return {"tasks": tasks, "total": total, "page": max(page, 1), "page_size": min(max(page_size, 1), 100)}


@app.get("/api/strategy2/backtests/{task_id}/comparison")
async def strategy2_backtest_comparison(task_id: str, baselineTaskId: str):
    """Compare an EXPERIMENTAL task with a trusted baseline task."""
    config = load_config()
    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)
    result = db.compare_strategy2_backtest_tasks(task_id, baselineTaskId)
    if "task_not_found" in result.get("reasons", []):
        return JSONResponse(result, status_code=404)
    if result.get("comparable"):
        db.update_strategy2_backtest_task(
            task_id,
            baseline_task_id=baselineTaskId,
            comparison_summary_json=json.dumps(result, ensure_ascii=False),
        )
    return result


@app.get("/api/strategy2/backtests/{task_id}")
async def strategy2_backtest_detail(task_id: str):
    """查询回测任务详情和汇总（解析 summary_json）。"""
    task = db.get_strategy2_backtest_task(task_id)
    if not task:
        return JSONResponse({"error": "TASK_NOT_FOUND"}, status_code=404)
    if task.get("summary_json"):
        try:
            task["summary"] = json.loads(task["summary_json"])
        except Exception:
            task["summary"] = None
    return task


@app.get("/api/strategy2/backtests/{task_id}/opportunities")
async def strategy2_backtest_opportunities(
    task_id: str, code: str = None, limit: int = 100, offset: int = 0,
):
    """查询回测机会明细（分页，返回真实总数）。"""
    total = db.get_conn().execute(
        "SELECT COUNT(*) FROM strategy2_backtest_opportunities WHERE task_id=?",
        (task_id,),
    ).fetchone()[0]
    opps = db.get_strategy2_backtest_opportunities(task_id, code=code, limit=limit, offset=offset)
    return {"items": opps, "total": total, "limit": limit, "offset": offset, "hasMore": (offset + limit) < total}


@app.get("/api/strategy2/backtests/{task_id}/signals")
async def strategy2_backtest_signals(
    task_id: str, code: str = None, limit: int = 100, offset: int = 0,
):
    """查询原始命中信号。"""
    conn = db.get_conn()
    if code:
        total = conn.execute(
            "SELECT COUNT(*) FROM strategy2_backtest_signals WHERE task_id=? AND code=?",
            (task_id, code)).fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM strategy2_backtest_signals WHERE task_id=? AND code=? ORDER BY evaluation_index LIMIT ? OFFSET ?",
            (task_id, code, limit, offset)).fetchall()
    else:
        total = conn.execute(
            "SELECT COUNT(*) FROM strategy2_backtest_signals WHERE task_id=?", (task_id,)).fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM strategy2_backtest_signals WHERE task_id=? ORDER BY evaluation_index LIMIT ? OFFSET ?",
            (task_id, limit, offset)).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy2_backtest_signals)")]
    return {"items": [dict(zip(cols, r)) for r in rows], "total": total, "limit": limit, "offset": offset, "hasMore": (offset + limit) < total}


@app.get("/api/strategy2/backtests/{task_id}/insufficient-stocks")
async def strategy2_backtest_insufficient(task_id: str):
    """查询数据不足股票列表。"""
    stocks = db.get_strategy2_backtest_insufficient_stocks(task_id)
    return {"stocks": stocks, "total": len(stocks)}


@app.get("/api/strategy2/backtests/{task_id}/stocks/{code}")
async def strategy2_backtest_stock_history(task_id: str, code: str):
    """查询单只股票在回测任务中的历史命中。"""
    opps = db.get_strategy2_backtest_opportunities(task_id, code=code, limit=500)
    return {"code": code, "opportunities": opps, "total": len(opps)}


@app.get("/api/strategy2/backtests/{task_id}/stocks")
async def strategy2_backtest_stocks(task_id: str, status: str = None):
    """查询任务中的股票状态列表。"""
    stocks = db.get_strategy2_backtest_task_stocks(task_id, status=status)
    return {"stocks": stocks, "total": len(stocks)}


@app.post("/api/strategy2/backtests/{task_id}/resume")
async def strategy2_backtest_resume(task_id: str):
    """恢复中断的回测任务。"""
    task = db.get_strategy2_backtest_task(task_id)
    if not task:
        return JSONResponse({"error": "TASK_NOT_FOUND"}, status_code=404)
    if _backtest_running["running"]:
        return JSONResponse({"error": "TASK_CONFLICT", "message": "已有回测正在运行"}, status_code=409)
    if str(task.get("status", "")).lower() not in {"interrupted", "canceled"}:
        return JSONResponse({"error": "TASK_NOT_RESUMABLE"}, status_code=409)
    target_stocks = [
        stock for stock in db.get_strategy2_backtest_task_stocks(task_id)
        if stock["status"] in {"PENDING", "RUNNING"}
    ]
    if not target_stocks:
        return JSONResponse({"error": "NO_UNFINISHED_STOCKS"}, status_code=409)
    config = json.loads(task["config_snapshot"])
    from strategy2.backtest_service import (
        DataRevisionChangedError,
        EngineRevisionChangedError,
        validate_task_data_revision,
        validate_task_engine_revision,
    )
    try:
        validate_task_engine_revision(task_id)
        validate_task_data_revision(task_id)
    except EngineRevisionChangedError:
        return JSONResponse({"error": "ENGINE_REVISION_CHANGED"}, status_code=409)
    except DataRevisionChangedError:
        return JSONResponse({"error": "DATA_REVISION_CHANGED"}, status_code=409)
    _launch_strategy2_backtest_task(
        task_id=task_id,
        target_stocks=target_stocks,
        config_snapshot=config,
        payload_snapshot=_backtest_payload_from_task(task),
        data_snapshot_date=task.get("data_snapshot_date") or "",
        mode="resume",
    )
    return {"task_id": task_id, "status": "resumed", "target_stocks": len(target_stocks)}


@app.post("/api/strategy2/backtests/{task_id}/cancel")
async def strategy2_backtest_cancel(task_id: str):
    """取消运行中的回测任务（设置取消信号，工作线程完成当前股票后停止）。"""
    if _backtest_running.get("task_id") != task_id:
        return JSONResponse({"error": "TASK_NOT_RUNNING"}, status_code=404)
    if _backtest_running.get("cancel_event"):
        _backtest_running["cancel_event"].set()
        return {"task_id": task_id, "status": "canceling"}
    return JSONResponse({"error": "NO_CANCEL_EVENT"}, status_code=500)


@app.post("/api/strategy2/backtests/{task_id}/retry-failed")
async def strategy2_backtest_retry_failed(task_id: str):
    """重试任务中失败的股票。"""
    task = db.get_strategy2_backtest_task(task_id)
    if not task:
        return JSONResponse({"error": "TASK_NOT_FOUND"}, status_code=404)
    if _backtest_running["running"]:
        return JSONResponse({"error": "TASK_CONFLICT"}, status_code=409)
    if str(task.get("status", "")).lower() == "running":
        return JSONResponse({"error": "TASK_CONFLICT"}, status_code=409)
    target_stocks = db.get_strategy2_backtest_task_stocks(task_id, status="FAILED")
    if not target_stocks:
        return {"task_id": task_id, "status": "no_failed_stocks", "target_stocks": 0}
    config = json.loads(task["config_snapshot"])
    from strategy2.backtest_service import (
        DataRevisionChangedError,
        EngineRevisionChangedError,
        validate_task_data_revision,
        validate_task_engine_revision,
    )
    try:
        validate_task_engine_revision(task_id)
        validate_task_data_revision(task_id)
    except EngineRevisionChangedError:
        return JSONResponse({"error": "ENGINE_REVISION_CHANGED"}, status_code=409)
    except DataRevisionChangedError:
        return JSONResponse({"error": "DATA_REVISION_CHANGED"}, status_code=409)
    _launch_strategy2_backtest_task(
        task_id=task_id,
        target_stocks=target_stocks,
        config_snapshot=config,
        payload_snapshot=_backtest_payload_from_task(task),
        data_snapshot_date=task.get("data_snapshot_date") or "",
        mode="retry_failed",
    )
    return {"task_id": task_id, "status": "retrying", "target_stocks": len(target_stocks)}

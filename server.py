# server.py
import logging
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import yaml

import scanner.db as db
from scanner.engine import scan_all
from analyzer.dry_stable import analyze_dry_stable
from scanner.index_source import fetch_market_index_daily
from scanner.pattern_detector import CupHandleResult

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
        logger.info(f"Resuming interrupted scan: {interrupted['id']} at {interrupted['scanned']}/{interrupted['total_stocks']}")
        import threading, datetime
        _running["running"] = True
        _running["task_id"] = interrupted["id"]
        _running["mode"] = "resume"
        _running["started_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _running["stats"] = {
            "total_stocks": interrupted["total_stocks"],
            "current_code": "--",
            "current_name": "恢复扫描中",
        }
        def resume_scan():
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
            result = scan_all(config, progress_callback=on_progress, resume_task_id=interrupted["id"], stop_event=_stop_event)
            _running["running"] = False
            _running["stats"] = result["stats"]
            _running["candidates"] = result["candidates"]
        t = threading.Thread(target=resume_scan, daemon=True)
        t.start()
    logger.info(f"Database initialized at {db_path}")

    if config.get("scheduler", {}).get("enabled", False):
        from scheduler.scheduler import start_scheduler
        start_scheduler(config)
        logger.info("Scheduler auto-started on server launch")
    yield
    # Shutdown
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
    "stats": {},
}
_stop_event = threading.Event()


def _get_running_task_id() -> str | None:
    """Return the active scan task id from memory or DB."""
    if _running.get("running") and _running.get("task_id"):
        return _running["task_id"]
    try:
        return db.get_running_task_id()
    except RuntimeError:
        return None


def _scan_conflict_response():
    """Return a 409 response if any scan process is already running."""
    running_id = _get_running_task_id()
    if running_id:
        return JSONResponse(
            {"error": "Scan already running", "running_task_id": running_id},
            status_code=409,
        )
    return None


def _set_running(task_id: str, mode: str):
    _stop_event.clear()
    _running["running"] = True
    _running["task_id"] = task_id
    _running["mode"] = mode
    _running["stats"] = {}


def _clear_running():
    _running["running"] = False


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

    pool_result = get_a_stock_pool_result(config)
    stocks = pool_result["stocks"]
    if not stocks:
        return JSONResponse(
            {"error": "No stock pool available", "detail": pool_result.get("error")},
            status_code=503,
        )

    task_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    started_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.create_scan_task(
        task_id,
        started_at,
        total_stocks=len(stocks),
        stock_pool_source=pool_result["source"],
        stock_pool_error=pool_result.get("error"),
        retry_mode="full",
    )
    db.save_task_stocks(task_id, stocks)
    _set_running(task_id, "full")
    _running["started_at"] = started_at
    _running["stats"] = {
        "total_stocks": len(stocks),
        "stock_pool_source": pool_result["source"],
        "current_code": "--",
        "current_name": "初始化中",
    }

    def run():
        try:
            def on_progress(stage, current, total, detail, discovery=None):
                """实时更新扫描进度到内存状态和数据库。"""
                stats = _running.get("stats", {})
                if stage == "discovery" and discovery:
                    found = stats.get("candidates_found", 0) + 1
                    db.upsert_candidate(task_id, discovery)
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
                stop_event=_stop_event,
            )

            if result["candidates"]:
                sc = config.get("scoring", {})
                db.save_candidates(
                    task_id, result["candidates"],
                    strong=sc.get("strong_threshold", 80),
                    medium=sc.get("medium_threshold", 70),
                )

            s = result["stats"]
            _running["stats"] = s
            if not _stop_event.is_set():
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
        "total_stocks": len(stocks),
        "stock_pool_source": pool_result["source"],
    }


@app.post("/api/scan/stop")
async def stop_scan():
    """Stop the currently running scan."""
    if not _running["running"]:
        return {"status": "no_scan_running"}
    _stop_event.set()
    task_id = _running.get("task_id")
    if task_id:
        conn = db.get_conn()
        conn.execute(
            "UPDATE scan_tasks SET status='cancelled', error='User stopped' WHERE id=?",
            (task_id,),
        )
        conn.execute(
            "UPDATE task_stocks SET status='pending', status_reason='scan stopped' WHERE task_id=? AND status='fetching'",
            (task_id,),
        )
        conn.commit()
    return {"status": "stopped", "task_id": task_id}


@app.get("/api/scan/status")
async def scan_status():
    if _running["running"]:
        summary = db.refresh_scan_task_counts(_running["task_id"]) if _running.get("task_id") else {}
        return {
            "running": True,
            "task_id": _running["task_id"],
            "mode": _running.get("mode", "full"),
            "stats": {**summary, **_running.get("stats", {})},
        }
    running_id = db.get_running_task_id()
    if running_id:
        return {"running": True, "task_id": running_id, "mode": "unknown", "stats": {}}
    return {"running": False, "task_id": None, "stats": {}}


@app.get("/api/scan/tasks")
async def list_tasks():
    tasks = []
    # Include current scan if running
    if _running["running"]:
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
        })
    # Add completed scans from DB (skip the running one already added above)
    running_id = _running.get("task_id")
    db_tasks = db.get_scan_tasks()
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
    page = max(page, 1)
    page_size = min(max(page_size, 1), 500)
    offset = (page - 1) * page_size
    stocks = db.get_task_stocks(task_id, status=status, limit=page_size, offset=offset)
    total = db.summarize_task_stocks(task_id)
    count = total.get(status, 0) if status else total["total_stocks"]
    return {"task_id": task_id, "stocks": stocks, "total": count, "page": page, "page_size": page_size}


@app.post("/api/scan/tasks/{task_id}/retry-failed")
async def retry_failed_stocks(task_id: str):
    config = load_config()
    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)

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
            result = scan_all(config, task_id=task_id, stocks=stocks, retry_policy="failed_only", stop_event=_stop_event)
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


@app.post("/api/scan/tasks/{task_id}/resume")
async def resume_task(task_id: str):
    """Resume a stopped/cancelled scan task from where it left off."""
    config = load_config()
    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)

    conflict = _scan_conflict_response()
    if conflict:
        return conflict

    # Reset fetching stocks to pending
    conn = db.get_conn()
    conn.execute(
        "UPDATE task_stocks SET status='pending', status_reason=NULL WHERE task_id=? AND status IN ('fetching','pending')",
        (task_id,),
    )
    conn.execute("UPDATE scan_tasks SET status='running' WHERE id=?", (task_id,))
    conn.commit()

    # Get remaining stocks
    stocks = db.get_pending_stocks(task_id)
    if not stocks:
        return JSONResponse({"error": "No pending stocks to resume"}, status_code=400)

    total = db.summarize_task_stocks(task_id)["total_stocks"]
    scanned = total - len(stocks)
    _set_running(task_id, "resume")
    _running["started_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _running["stats"] = {
        "total_stocks": total,
        "processed": scanned,
        "scanned": scanned,
        "stock_pool_source": "",
        "current_code": "--",
        "current_name": "恢复扫描中",
    }

    def run():
        try:
            def on_progress(stage, current, total_p, detail, discovery=None):
                stats = _running.get("stats", {})
                if stage == "discovery" and discovery:
                    found = stats.get("candidates_found", 0) + 1
                    ds = list(stats.get("discoveries") or [])
                    ds.insert(0, {"code": discovery["code"], "name": discovery["name"], "score": discovery["score"]})
                    _running["stats"] = {**stats, "discoveries": ds[:20], "candidates_found": found}
                else:
                    code = detail.split()[0] if detail else ""
                    nm = detail[len(code):].strip() if len(detail) > len(code) else detail
                    _running["stats"] = {**stats, "scanned": current, "processed": current, "total_stocks": total_p, "current_code": code, "current_name": nm}
            result = scan_all(config, progress_callback=on_progress, resume_task_id=task_id, stop_event=_stop_event)
            _running["running"] = False
            _running["stats"] = result["stats"]
            if result["candidates"]:
                sc = config.get("scoring", {})
                db.save_candidates(task_id, result["candidates"], strong=sc.get("strong_threshold", 80), medium=sc.get("medium_threshold", 70))
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
            logger.error(f"Resume failed: {e}\n{traceback.format_exc()}")
            conn = db.get_conn()
            conn.execute("UPDATE scan_tasks SET status='failed', error=? WHERE id=?", (str(e), task_id))
            conn.commit()
        finally:
            _clear_running()

    threading.Thread(target=run, daemon=True).start()
    return {"task_id": task_id, "status": "resumed", "remaining": len(stocks)}


@app.get("/api/candidates")
async def get_candidates(task_id: str = None):
    # If a specific task is requested, always query DB
    if task_id:
        cands = db.get_candidates(task_id=task_id)
    elif _running["running"]:
        # Return real-time discoveries during active scan
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
        })
    return {"candidates": result, "total": len(result)}


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
        return JSONResponse({"error": "Not found"}, status_code=404)
    trade_plan = {}
    ohlc = db.get_ohlc(code)
    if ohlc:
        pattern_result = _candidate_to_pattern_result(c)
        dry = analyze_dry_stable(pattern_result, ohlc, market_data=fetch_market_index_daily())
        trade_plan = dry.get("trade_plan", {})

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
        "trade_plan": trade_plan,
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

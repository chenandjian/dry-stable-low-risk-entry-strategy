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

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB, load config, start scheduler if enabled."""
    config = load_config()
    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)
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


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@app.get("/api/scan/start")
async def start_scan():
    global _running
    if _running["running"]:
        return JSONResponse({"error": "Scan already running"}, status_code=409)

    import datetime
    _running["running"] = True
    _running["stats"] = {}
    started_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _running["started_at"] = started_at

    config = load_config()

    # Ensure DB is initialized
    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)

    def run():
        task_id = None
        try:
            def on_progress(stage, current, total, detail):
                """实时更新扫描进度到内存状态和数据库。"""
                code = detail.split()[0] if detail else ""
                _running["stats"] = {
                    "scanned": current,
                    "total_stocks": total,
                    "skipped": _running.get("stats", {}).get("skipped", 0),
                    "candidates_found": _running.get("stats", {}).get("candidates_found", 0),
                    "current_code": code,
                    "current_name": detail[len(code):].strip() if len(detail) > len(code) else detail,
                }
                if task_id:
                    db.update_scan_progress(
                        task_id,
                        scanned=current,
                        skipped=_running["stats"].get("skipped", 0),
                        candidates_count=_running["stats"].get("candidates_found", 0),
                    )

            result = scan_all(config, progress_callback=on_progress)
            task_id = result["task_id"]
            _running["task_id"] = task_id

            # Create scan task in DB
            s = result["stats"]
            db.create_scan_task(task_id, started_at, total_stocks=s.get("total_stocks", 0))

            # Save candidates to DB
            if result["candidates"]:
                db.save_candidates(task_id, result["candidates"])

            # Update final stats in memory
            _running["stats"] = s

            # Mark scan as completed in DB
            db.finish_scan_task(
                task_id,
                finished_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                candidates_count=s.get("candidates_found", 0),
                elapsed_seconds=s.get("elapsed_seconds", 0),
                scanned=s.get("scanned", 0),
                skipped=s.get("skipped", 0),
            )

        except Exception as e:
            logger.error(f"Scan failed: {e}")
            if task_id:
                db.finish_scan_task(
                    task_id,
                    finished_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    candidates_count=0,
                    elapsed_seconds=0,
                )
        finally:
            _running["running"] = False

    t = threading.Thread(target=run, daemon=True)
    t.start()
    _running["task_id"] = "pending"

    return {"task_id": _running["task_id"], "status": "started"}


@app.get("/api/scan/status")
async def scan_status():
    if _running["running"]:
        return {
            "running": True,
            "task_id": _running["task_id"],
            "stats": _running["stats"],
        }
    # Check DB for any running task (recovery after restart)
    running_id = db.get_running_task_id()
    if running_id:
        return {"running": True, "task_id": running_id, "stats": {}}
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
            "candidates": s.get("candidates_found", 0),
            "scanned": s.get("scanned", 0),
            "total": s.get("total_stocks", 0),
        })
    # Add completed scans from DB
    db_tasks = db.get_scan_tasks()
    for t in db_tasks:
        tasks.append(t)
    return {"tasks": tasks}


@app.get("/api/candidates")
async def get_candidates():
    # If a scan just completed, prefer its results via DB
    if _running["running"]:
        # During scan, return empty — candidates are finalized after scan
        return {"candidates": [], "total": 0}

    cands = db.get_candidates()
    result = []
    for c in cands:
        result.append({
            "code": c.get("code", ""),
            "name": c.get("name", ""),
            "score": c.get("score", 0),
            "rating": c.get("rating", ""),
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


@app.get("/api/candidate/{code}")
async def get_candidate(code: str):
    c = db.get_candidate(code)
    if not c:
        return JSONResponse({"error": "Not found"}, status_code=404)

    return {
        "code": c.get("code", ""),
        "name": c.get("name", ""),
        "score": c.get("score", 0),
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
    }


@app.get("/api/config")
async def get_config():
    """Return current configuration (excluding sensitive fields)."""
    config = load_config()
    return {"config": config}


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

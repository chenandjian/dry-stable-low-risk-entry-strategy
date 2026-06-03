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
    db.mark_dead_tasks_as_failed()
    # 自动恢复中断的扫描
    interrupted = db.get_interrupted_task()
    if interrupted:
        logger.info(f"Resuming interrupted scan: {interrupted['id']} at {interrupted['scanned']}/{interrupted['total_stocks']}")
        import threading
        def resume_scan():
            _running["running"] = True
            _running["task_id"] = interrupted["id"]
            result = scan_all(config, resume_task_id=interrupted["id"])
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

    # Generate task_id BEFORE starting scan so progress can be tracked
    task_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    _running["task_id"] = task_id
    db.create_scan_task(task_id, started_at, total_stocks=0)

    def run():
        try:
            def on_progress(stage, current, total, detail, discovery=None):
                """实时更新扫描进度到内存状态和数据库。"""
                stats = _running.get("stats", {})
                if stage == "discovery" and discovery:
                    found = stats.get("candidates_found", 0) + 1
                    # 立即写入 DB，保证个股详情可查询
                    db.upsert_candidate(task_id, discovery)
                    discoveries = list(stats.get("discoveries") or [])
                    discoveries.insert(0, {
                        "code": discovery["code"],
                        "name": discovery["name"],
                        "score": discovery["score"],
                        "rating": "强候选" if discovery["score"] >= 80 else "中等候选" if discovery["score"] >= 70 else "弱候选",
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
                        "total_stocks": total,
                        "current_code": code,
                        "current_name": detail[len(code):].strip() if len(detail) > len(code) else detail,
                    })
                    s.setdefault("candidates_found", 0)
                    s.setdefault("skipped", 0)
                    _running["stats"] = s
                db.update_scan_progress(
                    task_id,
                    scanned=_running["stats"].get("scanned", 0),
                    skipped=_running["stats"].get("skipped", 0),
                    candidates_count=_running["stats"].get("candidates_found", 0),
                )

            result = scan_all(config, progress_callback=on_progress)

            # Save candidates to DB
            if result["candidates"]:
                sc = config.get("scoring", {})
                db.save_candidates(
                    task_id, result["candidates"],
                    strong=sc.get("strong_threshold", 80),
                    medium=sc.get("medium_threshold", 70),
                )

            # Update final stats
            s = result["stats"]
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
            import traceback
            logger.error(f"Scan failed: {e}\n{traceback.format_exc()}")
            _running["stats"] = {"error": str(e)}
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

    return {"task_id": task_id, "status": "started"}


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


@app.get("/api/candidates")
async def get_candidates():
    # During scan, return real-time discoveries
    if _running["running"]:
        ds = _running.get("stats", {}).get("discoveries") or []
        return {"candidates": ds, "total": len(ds)}

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
        "lip_deviation_pct": c.get("lip_deviation_pct", 0),
    }


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

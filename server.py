# server.py
import logging
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import yaml

from scanner.engine import scan_all

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: load config, load history, start scheduler if enabled."""
    _load_history()
    config = load_config()
    if config.get("scheduler", {}).get("enabled", False):
        from scheduler.scheduler import start_scheduler
        start_scheduler(config)
        logger.info("Scheduler auto-started on server launch")
    yield
    # Shutdown
    from scheduler.scheduler import stop_scheduler
    stop_scheduler()
    _save_history()
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

_scan_status = {
    "running": False,
    "task_id": None,
    "progress": {},
    "stats": {},
    "candidates": [],
}


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@app.get("/api/scan/start")
async def start_scan():
    global _scan_status
    if _scan_status["running"]:
        return JSONResponse({"error": "Scan already running"}, status_code=409)

    import datetime
    _scan_status["running"] = True
    _scan_status["candidates"] = []
    _scan_status["started_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    config = load_config()

    def run():
        def on_progress(stage, current, total, detail):
            """实时更新扫描进度到全局状态。"""
            code = detail.split()[0] if detail else ""
            _scan_status["stats"] = {
                "scanned": current,
                "total_stocks": total,
                "skipped": _scan_status.get("stats", {}).get("skipped", 0),
                "candidates_found": len(_scan_status["candidates"]),
                "current_code": code,
                "current_name": detail[len(code):].strip() if len(detail) > len(code) else detail,
            }
            _scan_status["task_id"] = _scan_status.get("task_id", "pending")

        result = scan_all(config, progress_callback=on_progress)
        _scan_status["running"] = False
        _scan_status["stats"] = result["stats"]
        _scan_status["candidates"] = result["candidates"]
        _scan_status["task_id"] = result["task_id"]

        # Save to history
        s = result["stats"]
        _scan_history.append({
            "id": result["task_id"],
            "date": _scan_status.get("started_at", ""),
            "scope": f"全市场 · {s.get('total_stocks', '--')}只",
            "running": False,
            "duration": f"{s.get('elapsed_seconds', 0):.0f}s",
            "candidates": s.get("candidates_found", 0),
            "topScore": max((r.score for _, r in result["candidates"]), default=0),
            "avgScore": round(sum(r.score for _, r in result["candidates"]) / max(len(result["candidates"]), 1), 1),
            "aGrade": sum(1 for _, r in result["candidates"] if r.score >= 80),
            "breakout": sum(1 for _, r in result["candidates"] if r.is_breakout),
        })
        _save_history()  # 持久化

    t = threading.Thread(target=run, daemon=True)
    t.start()
    _scan_status["task_id"] = "pending"

    return {"task_id": _scan_status["task_id"], "status": "started"}


@app.get("/api/scan/status")
async def scan_status():
    return {
        "running": _scan_status["running"],
        "task_id": _scan_status["task_id"],
        "stats": _scan_status["stats"],
    }


# Track scan history
HISTORY_FILE = "output_data/scan_history.json"
_scan_history: list = []


def _load_history():
    """从磁盘加载扫描历史。"""
    import os
    global _scan_history
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                import json
                _scan_history = json.load(f)
            logger.info(f"Loaded {len(_scan_history)} scan history records")
        except Exception as e:
            logger.warning(f"Failed to load scan history: {e}")
            _scan_history = []


def _save_history():
    """持久化扫描历史到磁盘。"""
    import os, json
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(_scan_history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save scan history: {e}")


@app.get("/api/scan/tasks")
async def list_tasks():
    tasks = []
    # Include current scan if running
    if _scan_status["running"]:
        s = _scan_status.get("stats", {})
        tasks.append({
            "id": _scan_status.get("task_id", "current"),
            "date": _scan_status.get("started_at", ""),
            "scope": f"全市场 · {s.get('total_stocks', '--')}只",
            "running": True,
            "candidates": s.get("candidates_found", 0),
            "scanned": s.get("scanned", 0),
            "total": s.get("total_stocks", 0),
        })
    # Add completed scans
    for h in reversed(_scan_history):
        tasks.append(h)
    return {"tasks": tasks}


@app.get("/api/candidates")
async def get_candidates():
    cands = _scan_status["candidates"]
    result = []
    for stock, r in cands:
        result.append({
            "code": r.code,
            "name": r.name,
            "score": r.score,
            "rating": "强候选" if r.score >= 80 else "中等候选" if r.score >= 70 else "弱候选",
            "is_breakout": r.is_breakout,
            "is_volume_breakout": r.is_volume_breakout,
            "latest_close": stock.get("latest_close", 0),
            "breakout_price": r.breakout_price,
            "cup_depth_pct": r.cup_depth_pct,
            "handle_depth_pct": r.handle_depth_pct,
            "cup_duration": r.cup_duration,
            "vol_multiplier": r.vol_multiplier,
        })
    return {"candidates": result, "total": len(result)}


@app.get("/api/candidate/{code}")
async def get_candidate(code: str):
    for stock, r in _scan_status["candidates"]:
        if r.code == code:
            return {
                "code": r.code,
                "name": r.name,
                "score": r.score,
                "left_high_price": r.left_high_price,
                "cup_low_price": r.cup_low_price,
                "right_high_price": r.right_high_price,
                "handle_low_price": r.handle_low_price,
                "left_high_date": r.left_high_date,
                "cup_low_date": r.cup_low_date,
                "right_high_date": r.right_high_date,
                "handle_low_date": r.handle_low_date,
                "cup_depth_pct": r.cup_depth_pct,
                "handle_depth_pct": r.handle_depth_pct,
                "cup_duration": r.cup_duration,
                "handle_duration": r.handle_duration,
                "is_breakout": r.is_breakout,
                "is_volume_breakout": r.is_volume_breakout,
                "vol_multiplier": r.vol_multiplier,
                "latest_close": stock.get("latest_close", 0),
                "latest_turnover": stock.get("latest_turnover", 0),
            }
    return JSONResponse({"error": "Not found"}, status_code=404)


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
            await websocket.send_json({
                "running": _scan_status["running"],
                "stats": _scan_status["stats"],
                "candidate_count": len(_scan_status["candidates"]),
            })
    except WebSocketDisconnect:
        pass

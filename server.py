# server.py
import logging
import threading
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
import yaml

from scanner.engine import scan_all

logger = logging.getLogger(__name__)

app = FastAPI(title="CupHandleScan API")

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

    _scan_status["running"] = True
    _scan_status["candidates"] = []

    config = load_config()

    def run():
        result = scan_all(config)
        _scan_status["running"] = False
        _scan_status["stats"] = result["stats"]
        _scan_status["candidates"] = result["candidates"]
        _scan_status["task_id"] = result["task_id"]

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


@app.get("/api/scan/tasks")
async def list_tasks():
    # Phase 3: read from log/database
    return {"tasks": []}


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
            }
    return JSONResponse({"error": "Not found"}, status_code=404)


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

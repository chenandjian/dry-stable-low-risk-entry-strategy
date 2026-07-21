from __future__ import annotations

import copy
import datetime as dt
import math
import threading
import uuid
from pathlib import Path

from scanner import db

from .cli import ADJUSTMENT, atomic_write_json, backup_database, write_report
from .client import TickFlowBatchClient
from .service import TickFlowDailyUpdateService


HISTORY_DAYS = 1100
CHUNK_SIZE = 100
BATCH_SIZE = 100
MAX_WORKERS = 5
OVERLAP_DAYS = 10


class TickFlowTaskConflict(RuntimeError):
    """Raised when a TickFlow full refresh is already running."""


def _launch_daemon(target):
    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread


class TickFlowFullRefreshManager:
    def __init__(
        self,
        *,
        client_factory=TickFlowBatchClient,
        thread_launcher=_launch_daemon,
    ):
        self._client_factory = client_factory
        self._thread_launcher = thread_launcher
        self._lock = threading.Lock()
        self._state = self._idle_state()
        self._thread = None

    @staticmethod
    def _idle_state() -> dict:
        return {
            "running": False,
            "task_id": None,
            "status": "idle",
            "parameters": {
                "history_days": HISTORY_DAYS,
                "chunk_size": CHUNK_SIZE,
                "batch_size": BATCH_SIZE,
                "max_workers": MAX_WORKERS,
                "adjustment": ADJUSTMENT,
            },
            "total_stocks": 0,
            "total_chunks": 0,
            "current_chunk": 0,
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "failures": [],
            "started_at": None,
            "finished_at": None,
            "elapsed_seconds": 0.0,
            "backup_path": None,
            "progress_path": None,
            "report_path": None,
            "error": None,
        }

    def is_running(self) -> bool:
        with self._lock:
            return bool(self._state["running"])

    def status(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._state)

    def start(self, database_path: str | Path, stocks: list[dict]) -> dict:
        if not stocks:
            raise ValueError("stock_pool is empty")
        database = Path(database_path).resolve()
        stock_snapshot = [dict(stock) for stock in stocks]
        task_id = f"tickflow-web-{dt.datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
        started_at = dt.datetime.now().isoformat(timespec="seconds")
        data_dir = database.parent / "tickflow"
        progress_path = data_dir / "progress" / f"{task_id}.json"
        report_path = data_dir / "reports" / f"{task_id}.md"

        with self._lock:
            if self._state["running"]:
                raise TickFlowTaskConflict(self._state["task_id"])
            self._state = {
                **self._idle_state(),
                "running": True,
                "task_id": task_id,
                "status": "running",
                "total_stocks": len(stock_snapshot),
                "total_chunks": math.ceil(len(stock_snapshot) / CHUNK_SIZE),
                "started_at": started_at,
                "progress_path": str(progress_path),
                "report_path": str(report_path),
            }

        def worker():
            self._run_worker(
                database=database,
                stocks=stock_snapshot,
                task_id=task_id,
                progress_path=progress_path,
                report_path=report_path,
            )

        try:
            self._thread = self._thread_launcher(worker)
        except Exception as exc:
            with self._lock:
                self._state.update(
                    running=False,
                    status="failed",
                    finished_at=dt.datetime.now().isoformat(timespec="seconds"),
                    error=str(exc),
                )
            raise
        return self.status()

    def _run_worker(
        self,
        *,
        database: Path,
        stocks: list[dict],
        task_id: str,
        progress_path: Path,
        report_path: Path,
    ) -> None:
        started = dt.datetime.now()
        try:
            backup_path = backup_database(database, database.parent / "tickflow" / "backups")
            with self._lock:
                self._state["backup_path"] = str(backup_path)
            self._persist_progress(progress_path)

            db.init_db(str(database))
            client = self._client_factory(batch_size=BATCH_SIZE, max_workers=MAX_WORKERS)
            service = TickFlowDailyUpdateService(
                client,
                history_days=HISTORY_DAYS,
                overlap_days=OVERLAP_DAYS,
                request_chunk_size=CHUNK_SIZE,
            )

            def record_result(item) -> None:
                with self._lock:
                    self._state["processed"] += 1
                    self._state["current_chunk"] = min(
                        self._state["total_chunks"],
                        math.ceil(self._state["processed"] / CHUNK_SIZE),
                    )
                    if item.status == "success":
                        self._state["succeeded"] += 1
                    else:
                        self._state["failed"] += 1
                        if len(self._state["failures"]) < 100:
                            self._state["failures"].append(
                                {"code": item.code, "error": item.error or item.status}
                            )
                    should_persist = (
                        self._state["processed"] % CHUNK_SIZE == 0
                        or self._state["processed"] == self._state["total_stocks"]
                    )
                if should_persist:
                    self._persist_progress(progress_path)

            result = service.run(
                stocks,
                dry_run=False,
                mode="backfill",
                run_id=task_id,
                on_result=record_result,
            )
            write_report(report_path, result, backup_path)
            terminal_status = (
                "completed_with_errors"
                if any(item.status == "failed" for item in result.results)
                else "completed"
            )
            with self._lock:
                self._state.update(
                    running=False,
                    status=terminal_status,
                    processed=len(result.results),
                    succeeded=sum(item.status == "success" for item in result.results),
                    failed=sum(item.status == "failed" for item in result.results),
                    current_chunk=self._state["total_chunks"],
                    finished_at=result.finished_at,
                    elapsed_seconds=result.elapsed_seconds,
                )
        except Exception as exc:
            with self._lock:
                self._state.update(
                    running=False,
                    status="failed",
                    finished_at=dt.datetime.now().isoformat(timespec="seconds"),
                    elapsed_seconds=max(0.0, (dt.datetime.now() - started).total_seconds()),
                    error=str(exc),
                )
        finally:
            self._persist_progress(progress_path)

    def _persist_progress(self, path: Path) -> None:
        atomic_write_json(path, self.status())

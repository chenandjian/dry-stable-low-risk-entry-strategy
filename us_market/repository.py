from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .daily_data import normalize_bars
from .instruments import provider_symbol


class USRepository:
    """Explicit US diagnostic store; no process-global DB or shared connection."""

    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables - {"us_diagnostic_snapshots"}:
                raise ValueError("refusing a non-US diagnostic database")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""CREATE TABLE IF NOT EXISTS us_diagnostic_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                adjustment TEXT NOT NULL,
                payload TEXT NOT NULL
            )""")

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=30)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def save_snapshot(self, snapshot: dict) -> None:
        if provider_symbol(snapshot["symbol"]) != snapshot["symbol"]:
            raise ValueError("snapshot must use canonical US symbol")
        if snapshot.get("formal_scan_allowed") is not False:
            raise ValueError("diagnostic storage cannot enable formal scanning")
        normalize_bars(snapshot["rows"])
        if not snapshot.get("snapshot_id") or snapshot.get("adjustment") not in {"none", "forward", "forward_additive"}:
            raise ValueError("invalid snapshot identity or adjustment")
        payload = json.dumps(snapshot, allow_nan=False, sort_keys=True)
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute("SELECT payload FROM us_diagnostic_snapshots WHERE snapshot_id=?",
                                    (snapshot["snapshot_id"],)).fetchone()
            if existing:
                if existing[0] != payload:
                    raise ValueError("snapshot is immutable; use a new snapshot_id")
                return
            conn.execute("INSERT INTO us_diagnostic_snapshots VALUES (?, ?, ?, ?)",
                         (snapshot["snapshot_id"], snapshot["symbol"], snapshot["adjustment"], payload))

    def get_snapshot(self, snapshot_id: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute("SELECT payload FROM us_diagnostic_snapshots WHERE snapshot_id=?",
                               (snapshot_id,)).fetchone()
        return json.loads(row[0]) if row else None

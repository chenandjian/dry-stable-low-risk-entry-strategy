from __future__ import annotations

import json
import hashlib
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .daily_data import normalize_bars
from .instruments import provider_symbol


class USRepository:
    """Explicit US store; no process-global DB or shared connection."""

    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables - {"us_diagnostic_snapshots", "us_stock_history", "us_runs"}:
                raise ValueError("refusing a non-US diagnostic database")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""CREATE TABLE IF NOT EXISTS us_diagnostic_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                adjustment TEXT NOT NULL,
                payload TEXT NOT NULL
            )""")
            conn.execute('''CREATE TABLE IF NOT EXISTS us_stock_history (
                symbol TEXT NOT NULL, adjustment TEXT NOT NULL,
                metadata TEXT NOT NULL, rows_json TEXT NOT NULL,
                PRIMARY KEY (symbol, adjustment)
            )''')
            conn.execute('''CREATE TABLE IF NOT EXISTS us_runs (
                task_id TEXT PRIMARY KEY, payload TEXT NOT NULL
            )''')

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

    def save_history(self, symbol: str, rows: list[dict], metadata: dict) -> None:
        symbol = provider_symbol(symbol)
        normalize_bars(rows)
        if metadata.get('adjustment') != 'forward' or metadata.get('source') != 'tickflow_free':
            raise ValueError('US acquisition requires free forward history')
        payload = json.dumps(rows, allow_nan=False)
        metadata = dict(metadata, data_hash=hashlib.sha256(
            json.dumps(rows, sort_keys=True, allow_nan=False).encode()
        ).hexdigest())
        meta = json.dumps(metadata, allow_nan=False)
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            existing = conn.execute('SELECT rows_json FROM us_stock_history WHERE symbol=? AND adjustment=?',
                                    (symbol, 'forward')).fetchone()
            if existing:
                old = json.loads(existing[0])
                if len(rows) < len(old) or rows[-1]['date'] < old[-1]['date']:
                    raise ValueError('history shortened or latest date regressed; previous data preserved')
            conn.execute('INSERT OR REPLACE INTO us_stock_history VALUES (?, ?, ?, ?)',
                         (symbol, 'forward', meta, payload))

    def get_history(self, symbol: str) -> dict | None:
        symbol = provider_symbol(symbol)
        with self.connection() as conn:
            row = conn.execute('SELECT metadata, rows_json FROM us_stock_history WHERE symbol=? AND adjustment=?',
                               (symbol, 'forward')).fetchone()
        return {'metadata': json.loads(row[0]), 'rows': json.loads(row[1])} if row else None

    def save_run(self, result: dict) -> None:
        if result.get('market') != 'US' or not result.get('research_only'):
            raise ValueError('US repository only accepts US research tasks')
        with self.connection() as conn:
            conn.execute('INSERT OR REPLACE INTO us_runs VALUES (?, ?)',
                         (result['task_id'], json.dumps(result, allow_nan=False)))

    def get_run(self, task_id: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute('SELECT payload FROM us_runs WHERE task_id=?', (task_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list_runs(self, limit: int = 20, *, kind=None, status=None, summary=False) -> list[dict]:
        filters, values = [], []
        for key, value in [('kind', kind), ('status', status)]:
            if value is not None:
                filters.append(f"json_extract(payload, '$.{key}') = ?")
                values.append(value)
        expression = "json_remove(payload, '$.stocks')" if summary else 'payload'
        where = ' WHERE ' + ' AND '.join(filters) if filters else ''
        with self.connection() as conn:
            rows = conn.execute(f'SELECT {expression} FROM us_runs{where} ORDER BY rowid DESC LIMIT ?',
                                (*values, limit)).fetchall()
        return [json.loads(row[0]) for row in rows]

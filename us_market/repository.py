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
            if tables - {"us_diagnostic_snapshots", "us_stock_history", "us_runs", "us_universes", "us_job_stocks"}:
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
            conn.execute('''CREATE TABLE IF NOT EXISTS us_universes (
                snapshot_id TEXT PRIMARY KEY, payload TEXT NOT NULL
            )''')
            conn.execute('''CREATE TABLE IF NOT EXISTS us_job_stocks (
                task_id TEXT NOT NULL, symbol TEXT NOT NULL, position INTEGER NOT NULL,
                status TEXT NOT NULL, passed INTEGER NOT NULL DEFAULT 0, payload TEXT NOT NULL,
                PRIMARY KEY (task_id, symbol)
            )''')
            conn.execute('CREATE INDEX IF NOT EXISTS us_job_stocks_page ON us_job_stocks(task_id, position)')
            conn.execute('CREATE INDEX IF NOT EXISTS us_job_stocks_status ON us_job_stocks(task_id, status)')
            conn.execute('CREATE INDEX IF NOT EXISTS us_job_stocks_counts ON us_job_stocks(task_id, status, passed)')

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
        expression = "json_remove(payload, '$.stocks', '$.symbols', '$.config')" if summary else 'payload'
        where = ' WHERE ' + ' AND '.join(filters) if filters else ''
        with self.connection() as conn:
            rows = conn.execute(f'SELECT {expression} FROM us_runs{where} ORDER BY rowid DESC LIMIT ?',
                                (*values, limit)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def save_universe(self, snapshot):
        if not snapshot.get('symbols') or snapshot.get('source') != 'tickflow_free':
            raise ValueError('invalid universe snapshot')
        with self.connection() as conn:
            conn.execute('INSERT INTO us_universes VALUES (?, ?)',
                         (snapshot['snapshot_id'], json.dumps(snapshot, allow_nan=False)))

    def latest_universe(self):
        with self.connection() as conn:
            row = conn.execute('SELECT payload FROM us_universes ORDER BY rowid DESC LIMIT 1').fetchone()
        return json.loads(row[0]) if row else None

    def get_universe(self, snapshot_id):
        with self.connection() as conn:
            row = conn.execute('SELECT payload FROM us_universes WHERE snapshot_id=?', (snapshot_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def initialize_job(self, task, *, resume_of=None):
        symbols = task.pop('symbols')
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('INSERT INTO us_runs VALUES (?, ?)', (task['task_id'], json.dumps(task, allow_nan=False)))
            if resume_of:
                conn.execute('''INSERT INTO us_job_stocks
                    SELECT ?, symbol, position, status, passed, payload FROM us_job_stocks WHERE task_id=?''',
                             (task['task_id'], resume_of))
            else:
                conn.executemany('INSERT INTO us_job_stocks VALUES (?, ?, ?, ?, 0, ?)',
                                 [(task['task_id'], symbol, i, 'PENDING', json.dumps({'symbol': symbol, 'status': 'PENDING'}))
                                  for i, symbol in enumerate(symbols)])
            self._job_counts(conn, task)
            task['progress'].update(processed=task['processed_count'], total=task['total_count'])
            conn.execute('UPDATE us_runs SET payload=? WHERE task_id=?', (json.dumps(task), task['task_id']))

    @staticmethod
    def _job_counts(conn, task):
        total, pending, failed, candidates = conn.execute('''SELECT count(*),
            coalesce(sum(status='PENDING'),0), coalesce(sum(status='FAILED'),0), coalesce(sum(passed),0)
            FROM us_job_stocks WHERE task_id=?''', (task['task_id'],)).fetchone()
        task.update(total_count=total, processed_count=total-pending, pending_count=pending,
                    failed_count=failed, candidates=candidates, evaluated_count=total-pending-failed)

    def complete_job_stocks(self, task, stocks):
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            for stock in stocks:
                if stock.get('status') not in {'FAILED', 'EVALUATED'}:
                    raise ValueError('job stock is not terminal')
                passed = stock.get('candidate', {}).get('candidate_type') in {'READY_CANDIDATE', 'KEY_CANDIDATE', 'WATCH_CANDIDATE'}
                changed = conn.execute('''UPDATE us_job_stocks SET status=?, passed=?, payload=?
                    WHERE task_id=? AND symbol=? AND status='PENDING' ''',
                                      (stock['status'], int(passed), json.dumps(stock, allow_nan=False), task['task_id'], stock['symbol'])).rowcount
                if changed != 1:
                    raise ValueError('unknown or already completed job stock')
            self._job_counts(conn, task)
            conn.execute('UPDATE us_runs SET payload=? WHERE task_id=?', (json.dumps(task, allow_nan=False), task['task_id']))

    def job_symbols(self, task_id, status=None):
        where = 'task_id=?' + (' AND status=?' if status is not None else '')
        values = (task_id, status) if status is not None else (task_id,)
        with self.connection() as conn:
            return [row[0] for row in conn.execute(f'SELECT symbol FROM us_job_stocks WHERE {where} ORDER BY position', values)]

    def job_page(self, task_id, *, page=1, page_size=50, only_passed=False):
        if not 1 <= page <= 50000 or not 1 <= page_size <= 100:
            raise ValueError('invalid page or page size')
        where = 'task_id=?' + (' AND passed=1' if only_passed else '')
        with self.connection() as conn:
            conn.execute('BEGIN')
            record = conn.execute("SELECT payload FROM us_runs WHERE task_id=? AND json_extract(payload, '$.kind')='job'", (task_id,)).fetchone()
            if record is None:
                return None
            task = json.loads(record[0])
            if task.get('stock_storage') == 'rows_v1':
                total = conn.execute(f'SELECT count(*) FROM us_job_stocks WHERE {where}', (task_id,)).fetchone()[0]
                rows = conn.execute(f'SELECT payload FROM us_job_stocks WHERE {where} ORDER BY position LIMIT ? OFFSET ?',
                                    (task_id, page_size, (page-1)*page_size)).fetchall()
                stocks = [json.loads(row[0]) for row in rows]
            else:
                stocks = task['stocks']
                task['failed_count'] = sum(stock['status'] == 'FAILED' for stock in stocks)
                if only_passed:
                    stocks = [stock for stock in stocks if stock.get('candidate', {}).get('candidate_type') in {'READY_CANDIDATE', 'KEY_CANDIDATE', 'WATCH_CANDIDATE'}]
                total = len(stocks)
                stocks = stocks[(page-1)*page_size:page*page_size]
        task.pop('symbols', None)
        task.pop('config', None)
        return dict(task, stocks=stocks, pagination={
            'page': page, 'page_size': page_size, 'total': total, 'pages': max(1, (total+page_size-1)//page_size),
        })

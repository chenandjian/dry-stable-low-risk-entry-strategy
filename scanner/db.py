# scanner/db.py
"""SQLite database layer for CupHandleScan.

Single database file at data/cuphandle.db with tables:
  stock_pool, daily_ohlc, scan_tasks, candidates.
"""

import sqlite3
import os
import threading
from contextlib import contextmanager

DB_PATH = None
_local = threading.local()


def init_db(path: str = "data/cuphandle.db"):
    """Initialize database and create tables if not exist."""
    global DB_PATH
    DB_PATH = path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with get_conn() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS stock_pool (
                code    TEXT PRIMARY KEY,
                name    TEXT NOT NULL,
                market  TEXT,
                updated TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS daily_ohlc (
                code     TEXT NOT NULL,
                date     TEXT NOT NULL,
                open     REAL,
                high     REAL,
                low      REAL,
                close    REAL,
                volume   REAL,
                turnover REAL,
                PRIMARY KEY (code, date)
            );
            CREATE INDEX IF NOT EXISTS idx_ohlc_code ON daily_ohlc(code);
            CREATE INDEX IF NOT EXISTS idx_ohlc_date ON daily_ohlc(date);

            CREATE TABLE IF NOT EXISTS scan_tasks (
                id               TEXT PRIMARY KEY,
                started_at       TEXT,
                finished_at      TEXT,
                status           TEXT DEFAULT 'running',
                total_stocks     INTEGER DEFAULT 0,
                scanned          INTEGER DEFAULT 0,
                skipped          INTEGER DEFAULT 0,
                candidates_count INTEGER DEFAULT 0,
                elapsed_seconds  REAL,
                error            TEXT
            );

            CREATE TABLE IF NOT EXISTS candidates (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id             TEXT NOT NULL,
                code                TEXT NOT NULL,
                name                TEXT NOT NULL,
                score               INTEGER,
                rating              TEXT,
                is_breakout         INTEGER DEFAULT 0,
                is_volume_breakout  INTEGER DEFAULT 0,
                breakout_price      REAL,
                vol_multiplier      REAL,
                cup_depth_pct       REAL,
                cup_duration        INTEGER,
                handle_depth_pct    REAL,
                handle_duration     INTEGER,
                lip_deviation_pct   REAL,
                left_high_price     REAL,
                cup_low_price       REAL,
                right_high_price    REAL,
                handle_low_price    REAL,
                left_high_date      TEXT,
                cup_low_date        TEXT,
                right_high_date     TEXT,
                handle_low_date     TEXT,
                latest_close        REAL,
                latest_turnover     REAL,
                FOREIGN KEY (task_id) REFERENCES scan_tasks(id)
            );
            CREATE INDEX IF NOT EXISTS idx_candidates_task ON candidates(task_id);
            CREATE INDEX IF NOT EXISTS idx_candidates_score ON candidates(score DESC);
        ''')
        conn.commit()


def get_conn() -> sqlite3.Connection:
    """Get thread-local database connection."""
    if DB_PATH is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    if not hasattr(_local, 'conn') or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH)
        _local.conn.execute("PRAGMA journal_mode=WAL")
    return _local.conn


# ====== Stock Pool ======

def save_stock_pool(stocks: list[dict]):
    """Replace stock pool table with new data."""
    conn = get_conn()
    conn.execute("DELETE FROM stock_pool")
    conn.executemany(
        "INSERT INTO stock_pool (code, name, market) VALUES (?, ?, ?)",
        [(s["code"], s["name"], s.get("market", "")) for s in stocks]
    )
    conn.commit()


def get_stock_pool() -> list[dict]:
    """Get all stocks from pool."""
    conn = get_conn()
    rows = conn.execute("SELECT code, name, market FROM stock_pool").fetchall()
    return [{"code": r[0], "name": r[1], "market": r[2]} for r in rows]


def get_stock_pool_count() -> int:
    conn = get_conn()
    return conn.execute("SELECT COUNT(*) FROM stock_pool").fetchone()[0]


# ====== Daily OHLC Cache ======

def save_ohlc(code: str, data: list[dict]):
    """Insert or replace OHLC data for a stock."""
    conn = get_conn()
    conn.execute("DELETE FROM daily_ohlc WHERE code = ?", (code,))
    conn.executemany(
        """INSERT INTO daily_ohlc (code, date, open, high, low, close, volume, turnover)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [(code, d["date"], d.get("open"), d.get("high"), d.get("low"),
          d.get("close"), d.get("volume"), d.get("turnover")) for d in data]
    )
    conn.commit()


def get_ohlc(code: str) -> list[dict] | None:
    """Get cached OHLC data for a stock, sorted by date."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT date, open, high, low, close, volume, turnover "
        "FROM daily_ohlc WHERE code = ? ORDER BY date", (code,)
    ).fetchall()
    if not rows:
        return None
    return [
        {"date": r[0], "open": r[1], "high": r[2], "low": r[3],
         "close": r[4], "volume": r[5], "turnover": r[6]}
        for r in rows
    ]


def get_ohlc_latest_date(code: str) -> str | None:
    """Get the latest date in cached OHLC data."""
    conn = get_conn()
    row = conn.execute(
        "SELECT MAX(date) FROM daily_ohlc WHERE code = ?", (code,)
    ).fetchone()
    return row[0] if row else None


# ====== Scan Tasks ======

def create_scan_task(task_id: str, started_at: str, total_stocks: int = 0) -> int:
    """Insert a new scan task. Returns row id."""
    conn = get_conn()
    conn.execute(
        "INSERT INTO scan_tasks (id, started_at, status, total_stocks) VALUES (?, ?, 'running', ?)",
        (task_id, started_at, total_stocks)
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def update_scan_progress(task_id: str, scanned: int, skipped: int = 0, candidates_count: int = 0):
    """Update scan progress in real-time."""
    conn = get_conn()
    conn.execute(
        "UPDATE scan_tasks SET scanned=?, skipped=?, candidates_count=? WHERE id=?",
        (scanned, skipped, candidates_count, task_id)
    )
    conn.commit()


def finish_scan_task(task_id: str, finished_at: str, candidates_count: int,
                     elapsed_seconds: float, scanned: int = 0, skipped: int = 0):
    """Mark scan task as completed."""
    conn = get_conn()
    conn.execute(
        """UPDATE scan_tasks
           SET status='completed', finished_at=?, candidates_count=?,
               elapsed_seconds=?, scanned=?, skipped=?
           WHERE id=?""",
        (finished_at, candidates_count, elapsed_seconds, scanned, skipped, task_id)
    )
    conn.commit()


def get_scan_tasks() -> list[dict]:
    """Get all scan tasks, most recent first."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, started_at, finished_at, status, total_stocks, scanned, skipped, "
        "candidates_count, elapsed_seconds FROM scan_tasks ORDER BY started_at DESC"
    ).fetchall()
    return [
        {"id": r[0], "date": r[1] or "", "finished_at": r[2],
         "running": r[3] == 'running', "scope": f"全市场 · {r[4]}只",
         "total_stocks": r[4], "scanned": r[5], "total": r[4],
         "candidates": r[7], "elapsed_seconds": r[8]}
        for r in rows
    ]


def get_running_task_id() -> str | None:
    """Get the ID of the currently running scan task, if any."""
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM scan_tasks WHERE status='running' ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else None


# ====== Candidates ======

def save_candidates(task_id: str, candidates: list):
    """Save candidate results for a scan task.

    Args:
        task_id: scan task id
        candidates: list of (stock_dict, CupHandleResult) tuples
    """
    conn = get_conn()
    conn.execute("DELETE FROM candidates WHERE task_id = ?", (task_id,))
    rows = []
    for stock, r in candidates:
        rows.append((
            task_id, r.code, r.name, r.score,
            "强候选" if r.score >= 80 else "中等候选" if r.score >= 70 else "弱候选",
            1 if r.is_breakout else 0,
            1 if r.is_volume_breakout else 0,
            r.breakout_price, r.vol_multiplier,
            r.cup_depth_pct, r.cup_duration,
            r.handle_depth_pct, r.handle_duration,
            r.lip_deviation_pct,
            r.left_high_price, r.cup_low_price,
            r.right_high_price, r.handle_low_price,
            r.left_high_date, r.cup_low_date,
            r.right_high_date, r.handle_low_date,
            stock.get("latest_close", 0),
            stock.get("latest_turnover", 0),
        ))
    conn.executemany(
        """INSERT INTO candidates (
            task_id, code, name, score, rating,
            is_breakout, is_volume_breakout, breakout_price, vol_multiplier,
            cup_depth_pct, cup_duration, handle_depth_pct, handle_duration,
            lip_deviation_pct,
            left_high_price, cup_low_price, right_high_price, handle_low_price,
            left_high_date, cup_low_date, right_high_date, handle_low_date,
            latest_close, latest_turnover
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows
    )
    conn.commit()


def get_candidates(task_id: str = None) -> list[dict]:
    """Get candidates, optionally filtered by task_id. Latest task if not specified."""
    conn = get_conn()
    if task_id:
        rows = conn.execute(
            "SELECT * FROM candidates WHERE task_id = ? ORDER BY score DESC", (task_id,)
        ).fetchall()
    else:
        # Get latest completed task's candidates
        latest = conn.execute(
            "SELECT id FROM scan_tasks WHERE status='completed' ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if not latest:
            return []
        rows = conn.execute(
            "SELECT * FROM candidates WHERE task_id = ? ORDER BY score DESC", (latest[0],)
        ).fetchall()

    col_names = [d[0] for d in conn.execute("PRAGMA table_info(candidates)").fetchall()]
    return [dict(zip(col_names, r)) for r in rows]


def get_candidate(code: str, task_id: str = None) -> dict | None:
    """Get single candidate detail."""
    conn = get_conn()
    if task_id:
        row = conn.execute(
            "SELECT * FROM candidates WHERE code = ? AND task_id = ?", (code, task_id)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM candidates WHERE code = ? ORDER BY id DESC LIMIT 1", (code,)
        ).fetchone()
    if not row:
        return None
    col_names = [d[0] for d in conn.execute("PRAGMA table_info(candidates)").fetchall()]
    return dict(zip(col_names, row))

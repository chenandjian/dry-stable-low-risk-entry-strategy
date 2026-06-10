# scanner/db.py
"""SQLite database layer for CupHandleScan.

Single database file at data/cuphandle.db with tables:
  stock_pool, daily_ohlc, scan_tasks, candidates.
"""

import sqlite3
import os
import threading
import datetime
from contextlib import contextmanager

DB_PATH = None
_local = threading.local()


def init_db(path: str = "data/cuphandle.db"):
    """Initialize database and create tables if not exist."""
    global DB_PATH
    if hasattr(_local, 'conn') and _local.conn is not None:
        try:
            _local.conn.close()
        except sqlite3.Error:
            pass
        _local.conn = None
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
                dry_stable_verdict  TEXT,
                dry_stable_summary  TEXT,
                volume_dry_score    INTEGER,
                price_stable_score  INTEGER,
                pattern_score_20    INTEGER,
                pattern_type        TEXT,
                key_pattern_type    TEXT,
                risk_percent        REAL,
                rr1                 REAL,
                position_advice     TEXT,
                entry_zone_low      REAL,
                entry_zone_high     REAL,
                pivot               REAL,
                stop_loss           REAL,
                target_1            REAL,
                target_2            REAL,
                market_status       TEXT,
                market_position_advice TEXT,
                FOREIGN KEY (task_id) REFERENCES scan_tasks(id)
            );
            CREATE INDEX IF NOT EXISTS idx_candidates_task ON candidates(task_id);
            CREATE INDEX IF NOT EXISTS idx_candidates_score ON candidates(score DESC);
        ''')
        _ensure_candidate_columns(conn)
        _ensure_scan_task_columns(conn)
        _ensure_task_stocks_table(conn)
        _dedupe_candidates_before_unique_index(conn)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_candidates_task_code ON candidates(task_id, code)")
        _ensure_strategy2_candidates_table(conn)
        conn.commit()


def _ensure_candidate_columns(conn: sqlite3.Connection):
    """Add strategy columns for databases created by older versions."""
    existing = {d[1] for d in conn.execute("PRAGMA table_info(candidates)").fetchall()}
    columns = {
        "dry_stable_verdict": "TEXT",
        "dry_stable_summary": "TEXT",
        "volume_dry_score": "INTEGER",
        "price_stable_score": "INTEGER",
        "pattern_score_20": "INTEGER",
        "pattern_type": "TEXT",
        "cup_handle_score": "INTEGER",
        "vcp_score": "INTEGER",
        "vcp_contractions": "INTEGER",
        "key_pattern_type": "TEXT",
        "risk_percent": "REAL",
        "rr1": "REAL",
        "position_advice": "TEXT",
        "entry_zone_low": "REAL",
        "entry_zone_high": "REAL",
        "pivot": "REAL",
        "stop_loss": "REAL",
        "target_1": "REAL",
        "target_2": "REAL",
        "market_status": "TEXT",
        "market_position_advice": "TEXT",
        "verdict_key": "TEXT",
        "positive_factors": "TEXT",
        "warnings": "TEXT",
        "reject_reasons": "TEXT",
        "raw_volume_dry_score": "INTEGER",
        "raw_price_stable_score": "INTEGER",
        "score_caps": "TEXT",
    }
    for name, typ in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE candidates ADD COLUMN {name} {typ}")




def _ensure_scan_task_columns(conn: sqlite3.Connection):
    """Add scan task tracking columns for databases created by older versions."""
    existing = {d[1] for d in conn.execute("PRAGMA table_info(scan_tasks)").fetchall()}
    columns = {
        "success_count": "INTEGER DEFAULT 0",
        "failed_count": "INTEGER DEFAULT 0",
        "stock_pool_source": "TEXT",
        "stock_pool_error": "TEXT",
        "retry_mode": "TEXT DEFAULT 'full'",
        "data_fresh_policy": "TEXT DEFAULT 'force_refresh'",
        "latest_trade_date": "TEXT",
        "strategy_type": "TEXT DEFAULT 'STRATEGY_1_CUP_HANDLE'",
    }
    for name, typ in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE scan_tasks ADD COLUMN {name} {typ}")
    # Ensure strategy2 index exists
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_scan_tasks_strategy_started "
        "ON scan_tasks(strategy_type, started_at DESC)"
    )



def _ensure_task_stocks_table(conn: sqlite3.Connection):
    """Create per-task stock tracking table used by scan progress and retries."""
    conn.execute('''
        CREATE TABLE IF NOT EXISTS task_stocks (
            task_id TEXT NOT NULL,
            idx INTEGER NOT NULL,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            market TEXT,
            status TEXT DEFAULT 'pending',
            status_reason TEXT,
            error_detail TEXT,
            primary_source TEXT,
            fallback_source TEXT,
            primary_attempts INTEGER DEFAULT 0,
            fallback_attempts INTEGER DEFAULT 0,
            primary_error TEXT,
            fallback_error TEXT,
            source_errors TEXT,
            kline_latest_date TEXT,
            quote_status TEXT DEFAULT 'not_requested',
            quote_error TEXT,
            started_at TEXT,
            finished_at TEXT,
            updated_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (task_id, code),
            FOREIGN KEY (task_id) REFERENCES scan_tasks(id)
        )
    ''')
    existing = {d[1] for d in conn.execute("PRAGMA table_info(task_stocks)").fetchall()}
    columns = {
        "market": "TEXT",
        "status": "TEXT DEFAULT 'pending'",
        "status_reason": "TEXT",
        "error_detail": "TEXT",
        "primary_source": "TEXT",
        "fallback_source": "TEXT",
        "primary_attempts": "INTEGER DEFAULT 0",
        "fallback_attempts": "INTEGER DEFAULT 0",
        "primary_error": "TEXT",
        "fallback_error": "TEXT",
        "source_errors": "TEXT",
        "kline_latest_date": "TEXT",
        "quote_status": "TEXT DEFAULT 'not_requested'",
        "quote_error": "TEXT",
        "started_at": "TEXT",
        "finished_at": "TEXT",
        "updated_at": "TEXT",
    }
    for name, typ in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE task_stocks ADD COLUMN {name} {typ}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_stocks_task_status ON task_stocks(task_id, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_stocks_task_idx ON task_stocks(task_id, idx)")



def _dedupe_candidates_before_unique_index(conn: sqlite3.Connection):
    """Keep the newest row for each task/code before adding a unique index."""
    conn.execute('''
        DELETE FROM candidates
        WHERE id NOT IN (
            SELECT MAX(id)
            FROM candidates
            GROUP BY task_id, code
        )
    ''')


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


def get_ohlc(code: str, max_rows: int = 0) -> list[dict] | None:
    """Get cached OHLC data for a stock, sorted by date.

    Args:
        max_rows: if > 0, return only the most recent N rows.
    """
    conn = get_conn()
    query = "SELECT date, open, high, low, close, volume, turnover FROM daily_ohlc WHERE code = ? ORDER BY date"
    rows = conn.execute(query, (code,)).fetchall()
    if not rows:
        return None
    if max_rows and len(rows) > max_rows:
        rows = rows[-max_rows:]
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

def create_scan_task(task_id: str, started_at: str, total_stocks: int = 0,
                     stock_pool_source: str = None, stock_pool_error: str = None,
                     retry_mode: str = "full",
                     strategy_type: str = "STRATEGY_1_CUP_HANDLE") -> int:
    """Insert a new scan task. Returns row id."""
    conn = get_conn()
    conn.execute(
        """INSERT INTO scan_tasks
           (id, started_at, status, total_stocks, stock_pool_source,
            stock_pool_error, retry_mode, data_fresh_policy, strategy_type)
           VALUES (?, ?, 'running', ?, ?, ?, ?, 'force_refresh', ?)""",
        (task_id, started_at, total_stocks, stock_pool_source, stock_pool_error, retry_mode, strategy_type),
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


def update_scan_task_total(task_id: str, total: int, source: str = ""):
    """Update the total stock count and source after pool is ready."""
    conn = get_conn()
    conn.execute(
        "UPDATE scan_tasks SET total_stocks=?, stock_pool_source=? WHERE id=?",
        (total, source, task_id),
    )
    conn.commit()


def finish_scan_task(task_id: str, finished_at: str, candidates_count: int,
                     elapsed_seconds: float, scanned: int = 0, skipped: int = 0):
    """Mark scan task as completed."""
    conn = get_conn()
    conn.execute(
        """UPDATE scan_tasks
           SET status='completed', finished_at=?, candidates_count=?,
               elapsed_seconds=?, scanned=?, skipped=?, error=NULL
           WHERE id=?""",
        (finished_at, candidates_count, elapsed_seconds, scanned, skipped, task_id)
    )
    conn.commit()


def mark_dead_tasks_as_failed():
    """Mark any running tasks as failed — they were interrupted by server restart.
    Also reset fetching stocks to pending so auto-resume can re-process them.
    Also handle crashed tasks (failed without finished_at) by resetting their
    fetching stocks so they can be picked up by get_interrupted_task()."""
    conn = get_conn()
    running_ids = conn.execute(
        "SELECT id FROM scan_tasks WHERE status='running'"
    ).fetchall()
    for (task_id,) in running_ids:
        conn.execute(
            "UPDATE task_stocks SET status='pending', status_reason=NULL, error_detail=NULL "
            "WHERE task_id=? AND status='fetching'",
            (task_id,),
        )
    conn.execute(
        "UPDATE scan_tasks SET status='failed', error='Interrupted by current server startup' WHERE status='running'"
    )
    # Also reset fetching stocks for crashed tasks (status=failed but never finished)
    crashed = conn.execute(
        "SELECT id FROM scan_tasks WHERE status='failed' AND finished_at IS NULL"
    ).fetchall()
    for (task_id,) in crashed:
        conn.execute(
            "UPDATE task_stocks SET status='pending', status_reason=NULL, error_detail=NULL "
            "WHERE task_id=? AND status='fetching'",
            (task_id,),
        )
    conn.commit()
    conn.commit()


def get_interrupted_task() -> dict | None:
    """Get the most recent interrupted task for resume.

    Returns any task that didn't finish all stocks (scanned < total_stocks)
    regardless of the specific error string.  This covers:
    - Server restart (mark_dead_tasks_as_failed)
    - User stop (cancelled)
    - Code bugs caught by the scan thread
    - Unexpected process termination

    Returns dict with id, scanned, total_stocks, strategy_type.
    NULL strategy_type → STRATEGY_1_CUP_HANDLE.
    """
    conn = get_conn()
    row = conn.execute(
        "SELECT id, scanned, total_stocks, strategy_type FROM scan_tasks "
        "WHERE (status='failed' OR status='cancelled') "
        "  AND finished_at IS NULL "
        "ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    if not row or row[1] >= row[2]:
        return None
    return {
        "id": row[0], "scanned": row[1], "total_stocks": row[2],
        "strategy_type": row[3] or "STRATEGY_1_CUP_HANDLE",
    }


def save_task_stocks(task_id: str, stocks: list[dict]):
    """Save the complete stock list for a scan task."""
    conn = get_conn()
    conn.execute("DELETE FROM task_stocks WHERE task_id = ?", (task_id,))
    conn.executemany(
        """INSERT INTO task_stocks (task_id, idx, code, name, market, status)
           VALUES (?, ?, ?, ?, ?, 'pending')""",
        [(task_id, i, s["code"], s.get("name", ""), s.get("market", "")) for i, s in enumerate(stocks)]
    )
    conn.execute("UPDATE scan_tasks SET total_stocks=? WHERE id=?", (len(stocks), task_id))
    conn.commit()


def update_task_stock(task_id: str, code: str, **fields):
    """Update fields for one task stock row."""
    allowed = {
        "status", "status_reason", "error_detail", "primary_source", "fallback_source",
        "primary_attempts", "fallback_attempts", "primary_error", "fallback_error",
        "kline_latest_date", "quote_status", "quote_error", "started_at", "finished_at",
        "source_errors",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    updates["updated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    assignments = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [task_id, code]
    conn = get_conn()
    conn.execute(f"UPDATE task_stocks SET {assignments} WHERE task_id=? AND code=?", values)
    conn.commit()


def get_task_stocks(task_id: str, status: str = None, limit: int = 100, offset: int = 0) -> list[dict]:
    """Return tracked stocks for a task, optionally filtered by status."""
    conn = get_conn()
    if status:
        rows = conn.execute(
            "SELECT * FROM task_stocks WHERE task_id=? AND status=? ORDER BY idx LIMIT ? OFFSET ?",
            (task_id, status, limit, offset),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM task_stocks WHERE task_id=? ORDER BY idx LIMIT ? OFFSET ?",
            (task_id, limit, offset),
        ).fetchall()
    columns = [d[1] for d in conn.execute("PRAGMA table_info(task_stocks)").fetchall()]
    return [dict(zip(columns, row)) for row in rows]


def get_pending_stocks(task_id: str, from_idx: int = 0) -> list[dict]:
    """Get unfinished stocks for a resumed task.

    Resume must not trust scan_tasks.scanned as an idx offset: multi-threaded scans
    and source-busy requeues can leave low-idx rows unfinished while later rows are
    already processed.
    """
    conn = get_conn()
    rows = conn.execute(
        """SELECT code, name, market FROM task_stocks
           WHERE task_id=? AND status IN ('pending', 'fetching')
           ORDER BY idx""",
        (task_id,),
    ).fetchall()
    return [{"code": r[0], "name": r[1], "market": r[2]} for r in rows]


def get_failed_task_stocks(task_id: str) -> list[dict]:
    """Return failed stocks for retry."""
    return get_task_stocks(task_id, status="failed", limit=100000, offset=0)


def reset_failed_task_stocks(task_id: str):
    """Move failed stocks back to pending before a retry run."""
    conn = get_conn()
    conn.execute(
        """UPDATE task_stocks
           SET status='pending', status_reason=NULL, error_detail=NULL,
               primary_attempts=0, fallback_attempts=0,
               primary_error=NULL, fallback_error=NULL,
               quote_status='not_requested', quote_error=NULL,
               updated_at=datetime('now')
           WHERE task_id=? AND status='failed'""",
        (task_id,),
    )
    conn.commit()


def summarize_task_stocks(task_id: str) -> dict:
    """Count task stocks by status."""
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM task_stocks WHERE task_id=?", (task_id,)).fetchone()[0]
    rows = conn.execute(
        "SELECT status, COUNT(*) FROM task_stocks WHERE task_id=? GROUP BY status",
        (task_id,),
    ).fetchall()
    counts = {r[0]: r[1] for r in rows}
    return {
        "total_stocks": total,
        "pending": counts.get("pending", 0),
        "fetching": counts.get("fetching", 0),
        "scanned": counts.get("scanned", 0),
        "skipped": counts.get("skipped", 0),
        "failed": counts.get("failed", 0),
        "candidate": counts.get("candidate", 0),
    }


def refresh_scan_task_counts(task_id: str) -> dict:
    """Persist scan task aggregate counts from task_stocks."""
    s = summarize_task_stocks(task_id)
    processed = s["scanned"] + s["skipped"] + s["failed"] + s["candidate"]
    candidates_count = s["candidate"]
    latest_row = get_conn().execute(
        "SELECT MAX(kline_latest_date) FROM task_stocks WHERE task_id=?",
        (task_id,),
    ).fetchone()
    latest_trade_date = latest_row[0] if latest_row else None
    conn = get_conn()
    conn.execute(
        """UPDATE scan_tasks
           SET total_stocks=?, scanned=?, skipped=?, failed_count=?,
               success_count=?, candidates_count=?, latest_trade_date=?
           WHERE id=?""",
        (
            s["total_stocks"], processed, s["skipped"], s["failed"],
            s["scanned"] + s["candidate"], candidates_count, latest_trade_date, task_id,
        ),
    )
    conn.commit()
    stock_pool_source = get_conn().execute(
        "SELECT stock_pool_source FROM scan_tasks WHERE id=?", (task_id,)
    ).fetchone()
    return {
        **s,
        "processed": processed,
        "success_count": s["scanned"] + s["candidate"],
        "failed_count": s["failed"],
        "candidates_count": candidates_count,
        "latest_trade_date": latest_trade_date,
        "stock_pool_source": stock_pool_source[0] if stock_pool_source else "",
    }


def get_scan_task(task_id: str) -> dict | None:
    """Get a single scan task by ID (RECHECK-S2-003)."""
    conn = get_conn()
    row = conn.execute(
        "SELECT id, started_at, finished_at, status, total_stocks, scanned, skipped, "
        "candidates_count, elapsed_seconds, failed_count, stock_pool_source, "
        "latest_trade_date, strategy_type "
        "FROM scan_tasks WHERE id=?",
        (task_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "id": row[0], "date": row[1] or "", "finished_at": row[2],
        "running": row[3] == 'running', "status": row[3],
        "total_stocks": row[4], "scanned": row[5], "total": row[4],
        "skipped": row[6], "candidates": row[7], "elapsed_seconds": row[8],
        "duration": f"{row[8]:.0f}s" if row[8] is not None else None,
        "failed": row[9], "stock_pool_source": row[10], "latest_trade_date": row[11],
        "strategy_type": row[12] or "STRATEGY_1_CUP_HANDLE",
    }


def get_task_strategy_type(task_id: str) -> str | None:
    """Return the strategy_type for a task, or None if not found (RECHECK-S2-003)."""
    conn = get_conn()
    row = conn.execute(
        "SELECT strategy_type FROM scan_tasks WHERE id=?", (task_id,),
    ).fetchone()
    if not row:
        return None
    return row[0] or "STRATEGY_1_CUP_HANDLE"


def get_scan_tasks(strategy_type: str = None) -> list[dict]:
    """Get scan tasks, optionally filtered by strategy_type (RECHECK-S2-003)."""
    conn = get_conn()
    if strategy_type:
        rows = conn.execute(
            """SELECT id, started_at, finished_at, status, total_stocks, scanned, skipped,
                      candidates_count, elapsed_seconds, failed_count, stock_pool_source,
                      latest_trade_date, strategy_type
               FROM scan_tasks WHERE (strategy_type=? OR (strategy_type IS NULL AND ?='STRATEGY_1_CUP_HANDLE'))
               ORDER BY started_at DESC""",
            (strategy_type, strategy_type),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT id, started_at, finished_at, status, total_stocks, scanned, skipped,
                      candidates_count, elapsed_seconds, failed_count, stock_pool_source,
                      latest_trade_date, strategy_type
               FROM scan_tasks ORDER BY started_at DESC"""
        ).fetchall()
    return [
        {"id": r[0], "date": r[1] or "", "finished_at": r[2],
         "running": r[3] == 'running', "status": r[3], "scope": f"全市场 · {r[4]}只",
         "total_stocks": r[4], "scanned": r[5], "total": r[4],
         "skipped": r[6], "candidates": r[7], "elapsed_seconds": r[8],
         "duration": f"{r[8]:.0f}s" if r[8] is not None else None,
         "failed": r[9], "stock_pool_source": r[10], "latest_trade_date": r[11],
         "strategy_type": r[12] or "STRATEGY_1_CUP_HANDLE"}
        for r in rows
    ]


def get_running_task_id() -> str | None:
    """Get the ID of the currently running scan task, if any."""
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM scan_tasks WHERE status='running' ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else None


def get_running_task() -> dict | None:
    """Get the currently running scan task with strategy type, if any."""
    conn = get_conn()
    row = conn.execute(
        "SELECT id, strategy_type FROM scan_tasks WHERE status='running' ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None
    return {"id": row[0], "strategy_type": row[1] or "STRATEGY_1_CUP_HANDLE"}


# ====== Candidates ======

def _json_list(value):
    """Encode a list as JSON string for TEXT column storage, or return empty string."""
    if not value:
        return ""
    import json
    return json.dumps(list(value), ensure_ascii=False)


def delete_candidates(task_id: str):
    """Delete all candidates for a task (so re-evaluate can replace them)."""
    conn = get_conn()
    conn.execute("DELETE FROM candidates WHERE task_id=?", (task_id,))
    conn.commit()


def upsert_candidate(task_id: str, d: dict):
    """Insert or update a single candidate (for real-time discovery)."""
    conn = get_conn()
    rating = "强候选" if d["score"] >= 80 else "中等候选" if d["score"] >= 70 else "弱候选"
    columns = [
        "task_id", "code", "name", "score", "rating",
        "is_breakout", "is_volume_breakout", "breakout_price", "vol_multiplier",
        "cup_depth_pct", "cup_duration", "handle_depth_pct", "handle_duration",
        "lip_deviation_pct", "left_high_price", "cup_low_price", "right_high_price",
        "handle_low_price", "left_high_date", "cup_low_date", "right_high_date",
        "handle_low_date", "latest_close", "latest_turnover",
        "dry_stable_verdict", "dry_stable_summary",
        "volume_dry_score", "price_stable_score", "pattern_score_20",
        "cup_handle_score", "vcp_score", "vcp_contractions",
        "pattern_type", "key_pattern_type",
        "risk_percent", "rr1", "position_advice",
        "entry_zone_low", "entry_zone_high", "pivot", "stop_loss", "target_1", "target_2",
        "market_status", "market_position_advice",
        "verdict_key", "positive_factors", "warnings", "reject_reasons",
        "raw_volume_dry_score", "raw_price_stable_score", "score_caps",
    ]
    values = (
        task_id, d["code"], d["name"], d["score"], rating,
        d.get("is_breakout", 0), d.get("is_volume_breakout", 0),
        d.get("breakout_price", 0), d.get("vol_multiplier", 0),
        d.get("cup_depth_pct", 0), d.get("cup_duration", 0),
        d.get("handle_depth_pct", 0), d.get("handle_duration", 0),
        d.get("lip_deviation_pct", 0), d.get("left_high_price", 0),
        d.get("cup_low_price", 0), d.get("right_high_price", 0),
        d.get("handle_low_price", 0),
        d.get("left_high_date", ""), d.get("cup_low_date", ""),
        d.get("right_high_date", ""), d.get("handle_low_date", ""),
        d.get("latest_close", 0),
        0,
        d.get("dry_stable_verdict", ""),
        d.get("dry_stable_summary", ""),
        d.get("volume_dry_score", 0),
        d.get("price_stable_score", 0),
        d.get("pattern_score_20", 0),
        d.get("cup_handle_score", 0),
        d.get("vcp_score", 0),
        d.get("vcp_contractions", 0),
        d.get("pattern_type", ""),
        d.get("key_pattern_type", ""),
        d.get("risk_percent", 0),
        d.get("rr1", 0),
        d.get("position_advice", ""),
        d.get("entry_zone_low", 0),
        d.get("entry_zone_high", 0),
        d.get("pivot", 0),
        d.get("stop_loss", 0),
        d.get("target_1", 0),
        d.get("target_2", 0),
        d.get("market_status", ""),
        d.get("market_position_advice", ""),
        d.get("verdict_key", ""),
        _json_list(d.get("positive_factors")),
        _json_list(d.get("warnings")),
        _json_list(d.get("reject_reasons")),
        d.get("raw_volume_dry_score", 0),
        d.get("raw_price_stable_score", 0),
        _json_list(d.get("score_caps")),
    )
    value_marks = ", ".join("?" for _ in columns)
    update_assignments = ", ".join(f"{c}=excluded.{c}" for c in columns if c not in ("task_id", "code"))
    conn.execute(
        f"""INSERT INTO candidates ({', '.join(columns)}) VALUES ({value_marks})
            ON CONFLICT(task_id, code) DO UPDATE SET {update_assignments}""",
        values,
    )
    conn.commit()


def save_candidates(task_id: str, candidates: list, strong: int = 80, medium: int = 70):
    """Save candidate results for a scan task.

    Args:
        task_id: scan task id
        candidates: list of (stock_dict, CupHandleResult) tuples
        strong: threshold for 强候选 (default 80)
        medium: threshold for 中等候选 (default 70)
    """
    conn = get_conn()
    rows = []
    for stock, r in candidates:
        rating = "强候选" if r.score >= strong else "中等候选" if r.score >= medium else "弱候选"
        dry = stock.get("dry_stable", {})
        decision = dry.get("decision", {})
        volume_dry = dry.get("volume_dry", {})
        price_stable = dry.get("price_stable", {})
        pattern = dry.get("pattern_score", {})
        rr = dry.get("risk_reward", {})
        key = dry.get("key_prices", {})
        market = dry.get("market_environment", {})
        rows.append((
            task_id, r.code, r.name, r.score, rating,
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
            decision.get("verdict", ""),
            decision.get("summary", ""),
            volume_dry.get("score", 0),
            price_stable.get("score", 0),
            pattern.get("score", 0),
            pattern.get("cup_handle_score", 0),
            pattern.get("vcp_score", 0),
            pattern.get("vcp_contractions", 0),
            pattern.get("type", ""),
            pattern.get("key_pattern_type", ""),
            rr.get("risk_percent", 0),
            rr.get("rr1", 0),
            rr.get("position_advice", ""),
            key.get("entry_zone_low", 0),
            key.get("entry_zone_high", 0),
            key.get("pivot", 0),
            key.get("stop_loss", 0),
            key.get("target_1", 0),
            key.get("target_2", 0),
            market.get("status", ""),
            market.get("position_advice", ""),
            decision.get("verdict_key", ""),
            _json_list(decision.get("positive_factors")),
            _json_list(decision.get("warnings")),
            _json_list(decision.get("reject_reasons")),
            volume_dry.get("raw_score", 0),
            price_stable.get("raw_score", 0),
            _json_list(volume_dry.get("caps", []) + price_stable.get("caps", [])),
        ))
    columns = [
        "task_id", "code", "name", "score", "rating",
        "is_breakout", "is_volume_breakout", "breakout_price", "vol_multiplier",
        "cup_depth_pct", "cup_duration", "handle_depth_pct", "handle_duration",
        "lip_deviation_pct", "left_high_price", "cup_low_price", "right_high_price",
        "handle_low_price", "left_high_date", "cup_low_date", "right_high_date",
        "handle_low_date", "latest_close", "latest_turnover",
        "dry_stable_verdict", "dry_stable_summary",
        "volume_dry_score", "price_stable_score", "pattern_score_20",
        "cup_handle_score", "vcp_score", "vcp_contractions",
        "pattern_type", "key_pattern_type",
        "risk_percent", "rr1", "position_advice",
        "entry_zone_low", "entry_zone_high", "pivot", "stop_loss", "target_1", "target_2",
        "market_status", "market_position_advice",
        "verdict_key", "positive_factors", "warnings", "reject_reasons",
        "raw_volume_dry_score", "raw_price_stable_score", "score_caps",
    ]
    value_marks = ", ".join("?" for _ in columns)
    update_assignments = ", ".join(f"{c}=excluded.{c}" for c in columns if c not in ("task_id", "code"))
    conn.executemany(
        f"""INSERT INTO candidates ({', '.join(columns)}) VALUES ({value_marks})
            ON CONFLICT(task_id, code) DO UPDATE SET {update_assignments}""",
        rows,
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
        # Get latest completed STRATEGY1 task's candidates (BUG-S2-007)
        latest = conn.execute(
            "SELECT id FROM scan_tasks WHERE status='completed' "
            "AND (strategy_type IS NULL OR strategy_type='STRATEGY_1_CUP_HANDLE') "
            "ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if not latest:
            return []
        rows = conn.execute(
            "SELECT * FROM candidates WHERE task_id = ? ORDER BY score DESC", (latest[0],)
        ).fetchall()

    col_names = [d[1] for d in conn.execute("PRAGMA table_info(candidates)").fetchall()]
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
    col_names = [d[1] for d in conn.execute("PRAGMA table_info(candidates)").fetchall()]
    return dict(zip(col_names, row))


# ====== Strategy2 Candidates ======

def _ensure_strategy2_candidates_table(conn: sqlite3.Connection):
    """Create strategy2_candidates table if not exists (compatible migration)."""
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy2_candidates (
            id                         INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id                    TEXT NOT NULL,
            code                       TEXT NOT NULL,
            name                       TEXT NOT NULL,
            evaluation_date            TEXT NOT NULL,
            total_score                INTEGER NOT NULL,
            level                      TEXT NOT NULL,
            volume_dry_score           INTEGER NOT NULL,
            price_stable_score         INTEGER NOT NULL,
            current_close              REAL NOT NULL,
            v3                         REAL,
            v5                         REAL,
            v10                        REAL,
            v20                        REAL,
            volume_ratio_5_20          REAL,
            volume_percentile          REAL,
            volume_percentile_days     INTEGER,
            range_5                    REAL,
            close_range_5              REAL,
            return_3                   REAL,
            return_5                   REAL,
            key_support                REAL NOT NULL,
            buy_zone_low               REAL NOT NULL,
            buy_zone_high              REAL NOT NULL,
            stop_loss                  REAL NOT NULL,
            risk_ratio                 REAL NOT NULL,
            risk_level                 TEXT NOT NULL,
            score_reasons              TEXT,
            reject_reasons             TEXT,
            data_source                TEXT,
            created_at                 TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (task_id) REFERENCES scan_tasks(id),
            UNIQUE (task_id, code)
        )
    ''')
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy2_candidates_task_score "
        "ON strategy2_candidates(task_id, total_score DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy2_candidates_task_risk "
        "ON strategy2_candidates(task_id, risk_ratio ASC)"
    )


def _json_dumps(value):
    """Encode a list as JSON string, or return empty string."""
    if not value:
        return ""
    import json
    return json.dumps(list(value), ensure_ascii=False)


def upsert_strategy2_candidate(task_id: str, d: dict):
    """Insert or update a single strategy2 candidate."""
    conn = get_conn()
    columns = [
        "task_id", "code", "name", "evaluation_date", "total_score", "level",
        "volume_dry_score", "price_stable_score", "current_close",
        "v3", "v5", "v10", "v20", "volume_ratio_5_20",
        "volume_percentile", "volume_percentile_days",
        "range_5", "close_range_5", "return_3", "return_5",
        "key_support", "buy_zone_low", "buy_zone_high", "stop_loss",
        "risk_ratio", "risk_level", "score_reasons", "reject_reasons", "data_source",
    ]
    values = (
        task_id, d["code"], d["name"], d["evaluation_date"],
        d["total_score"], d["level"],
        d["volume_dry_score"], d["price_stable_score"], d["current_close"],
        d.get("v3"), d.get("v5"), d.get("v10"), d.get("v20"),
        d.get("volume_ratio_5_20"), d.get("volume_percentile"), d.get("volume_percentile_days"),
        d.get("range_5"), d.get("close_range_5"), d.get("return_3"), d.get("return_5"),
        d["key_support"], d["buy_zone_low"], d["buy_zone_high"], d["stop_loss"],
        d["risk_ratio"], d["risk_level"],
        _json_dumps(d.get("score_reasons")),
        _json_dumps(d.get("reject_reasons")),
        d.get("data_source", ""),
    )
    value_marks = ", ".join("?" for _ in columns)
    update_assignments = ", ".join(f"{c}=excluded.{c}" for c in columns if c not in ("task_id", "code"))
    conn.execute(
        f"""INSERT INTO strategy2_candidates ({', '.join(columns)}) VALUES ({value_marks})
            ON CONFLICT(task_id, code) DO UPDATE SET {update_assignments}""",
        values,
    )
    conn.commit()


def get_strategy2_candidates(task_id: str = None) -> list[dict]:
    """Get strategy2 candidates, optionally filtered by task_id.

    Returns JSON array fields as deserialized lists (BUG-S2-011).
    Sorted by total_score DESC, risk_ratio ASC, code ASC (BUG-S2-011).
    """
    conn = get_conn()
    if task_id:
        rows = conn.execute(
            "SELECT * FROM strategy2_candidates WHERE task_id=? "
            "ORDER BY total_score DESC, risk_ratio ASC, code ASC",
            (task_id,),
        ).fetchall()
    else:
        latest = conn.execute(
            "SELECT id FROM scan_tasks WHERE status='completed' AND strategy_type='STRATEGY_2_EXTREME_DRY_STABLE' ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if not latest:
            return []
        rows = conn.execute(
            "SELECT * FROM strategy2_candidates WHERE task_id=? "
            "ORDER BY total_score DESC, risk_ratio ASC, code ASC",
            (latest[0],),
        ).fetchall()
    col_names = [d[1] for d in conn.execute("PRAGMA table_info(strategy2_candidates)").fetchall()]
    return [_deserialize_strategy2_candidate(dict(zip(col_names, r))) for r in rows]


def get_strategy2_candidate(code: str, task_id: str = None) -> dict | None:
    """Get single strategy2 candidate detail.

    Returns JSON array fields as deserialized lists (BUG-S2-011).
    """
    conn = get_conn()
    if task_id:
        row = conn.execute(
            "SELECT * FROM strategy2_candidates WHERE code=? AND task_id=?",
            (code, task_id),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM strategy2_candidates WHERE code=? ORDER BY id DESC LIMIT 1",
            (code,),
        ).fetchone()
    if not row:
        return None
    col_names = [d[1] for d in conn.execute("PRAGMA table_info(strategy2_candidates)").fetchall()]
    return _deserialize_strategy2_candidate(dict(zip(col_names, row)))


def _deserialize_strategy2_candidate(row: dict) -> dict:
    """Convert JSON string fields to Python lists (BUG-S2-011)."""
    json_fields = ("score_reasons", "reject_reasons")
    for field in json_fields:
        value = row.get(field)
        if isinstance(value, str) and value:
            try:
                import json
                row[field] = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                row[field] = []
        elif not value:
            row[field] = []
    return row

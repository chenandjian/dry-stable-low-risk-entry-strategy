# scanner/db.py
"""SQLite database layer for CupHandleScan.

Single database file at data/cuphandle.db with tables:
  stock_pool, daily_ohlc, scan_tasks, candidates.
"""

import json
import sqlite3
import os
import threading
import datetime
from contextlib import contextmanager

DB_PATH = None
_local = threading.local()
STRATEGY2_DATA_REVISION_VERSION = "daily-ohlc-v2"


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
        _ensure_strategy3_candidates_table(conn)
        _ensure_strategy2_backtest_tables(conn)
        _ensure_strategy1_backtest_tables(conn)
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
            kline_fetched_at TEXT,
            kline_target_trade_date TEXT,
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
        "kline_fetched_at": "TEXT",
        "kline_target_trade_date": "TEXT",
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


def get_ohlc_history_page(
    code: str,
    start_date: str | None = None,
    end_date: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Return a paginated slice of cached OHLC history, newest rows first."""
    page = max(1, int(page or 1))
    page_size = min(200, max(1, int(page_size or 50)))
    offset = (page - 1) * page_size

    clauses = ["code = ?"]
    params: list = [code]
    if start_date:
        clauses.append("date >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("date <= ?")
        params.append(end_date)
    where = " AND ".join(clauses)

    conn = get_conn()
    total = conn.execute(
        f"SELECT COUNT(*) FROM daily_ohlc WHERE {where}",
        params,
    ).fetchone()[0]
    rows = conn.execute(
        f"""SELECT date, open, high, low, close, volume, turnover
            FROM daily_ohlc
            WHERE {where}
            ORDER BY date DESC
            LIMIT ? OFFSET ?""",
        [*params, page_size, offset],
    ).fetchall()
    return {
        "rows": [
            {
                "date": r[0],
                "open": r[1],
                "high": r[2],
                "low": r[3],
                "close": r[4],
                "volume": r[5],
                "turnover": r[6],
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_latest_task_stock_kline_metadata(code: str) -> dict | None:
    """Return the newest scan task K-line metadata for one stock."""
    conn = get_conn()
    row = conn.execute(
        """SELECT kline_latest_date, kline_fetched_at,
                  kline_target_trade_date, quote_status
           FROM task_stocks
           WHERE code = ?
             AND (kline_latest_date IS NOT NULL OR kline_fetched_at IS NOT NULL)
           ORDER BY kline_fetched_at DESC, updated_at DESC
           LIMIT 1""",
        (code,),
    ).fetchone()
    if not row:
        return None
    return {
        "kline_latest_date": row[0],
        "kline_fetched_at": row[1],
        "kline_target_trade_date": row[2],
        "quote_status": row[3] or "not_requested",
    }


def get_reusable_task_stock_kline_context(
    code: str,
    target_trade_date: str,
    min_fetch_time: str | None,
    exclude_task_id: str | None = None,
) -> dict | None:
    """Return prior task K-line freshness metadata reusable for a new scan.

    Freshness is tied to the latest completed trade date, not calendar today.
    Suspended/no-trade rows may have latest K-line before target_trade_date,
    but only when a prior scan fetched after the target close time.
    """
    conn = get_conn()
    params: list = [code, target_trade_date]
    min_fetch_clause = ""
    if min_fetch_time:
        min_fetch_clause = "AND ts.kline_fetched_at >= ?"
        params.append(min_fetch_time)
    params.append(target_trade_date)
    exclude_clause = ""
    if exclude_task_id:
        exclude_clause = "AND ts.task_id != ?"
        params.append(exclude_task_id)
    row = conn.execute(
        f"""SELECT ts.kline_latest_date, ts.kline_fetched_at,
                  ts.kline_target_trade_date, ts.quote_status
            FROM task_stocks ts
            WHERE ts.code = ?
              AND ts.kline_target_trade_date = ?
              AND ts.kline_fetched_at IS NOT NULL
              {min_fetch_clause}
              AND ts.kline_latest_date IS NOT NULL
              AND ts.status IN ('scanned', 'skipped', 'candidate')
              AND (
                    ts.kline_latest_date >= ?
                    OR ts.quote_status IN ('suspended', 'no_trade')
                  )
              {exclude_clause}
            ORDER BY ts.kline_fetched_at DESC, ts.updated_at DESC
            LIMIT 1""",
        params,
    ).fetchone()
    if not row:
        return None
    return {
        "kline_latest_date": row[0],
        "kline_fetched_at": row[1],
        "kline_target_trade_date": row[2],
        "quote_status": row[3] or "not_requested",
    }


def get_today_task_stock_latest_date(code: str, today: str, exclude_task_id: str | None = None) -> str | None:
    """Return this stock's latest K-line date recorded by a task started today."""
    conn = get_conn()
    params: list = [code, f"{today}%"]
    exclude_clause = ""
    if exclude_task_id:
        exclude_clause = "AND ts.task_id != ?"
        params.append(exclude_task_id)
    row = conn.execute(
        f"""SELECT ts.kline_latest_date
            FROM task_stocks ts
            JOIN scan_tasks st ON st.id = ts.task_id
            WHERE ts.code = ?
              AND st.started_at LIKE ?
              AND ts.kline_latest_date IS NOT NULL
              AND ts.status IN ('scanned', 'skipped', 'candidate')
              {exclude_clause}
            ORDER BY st.started_at DESC, ts.updated_at DESC
            LIMIT 1""",
        params,
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
        "source_errors", "kline_fetched_at", "kline_target_trade_date",
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
    # 趋势字段兼容式迁移（V2 价格路径+120日长期确认）
    _ensure_column(conn, "strategy2_candidates", "trend_type", "TEXT")
    _ensure_column(conn, "strategy2_candidates", "short_mid_score", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_candidates", "long_score", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_candidates", "total_evidence_score", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_candidates", "necessary_conditions_met", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_candidates", "ma20", "REAL")
    _ensure_column(conn, "strategy2_candidates", "ma60", "REAL")
    _ensure_column(conn, "strategy2_candidates", "ma120", "REAL")
    _ensure_column(conn, "strategy2_candidates", "ma20_slope", "REAL")
    _ensure_column(conn, "strategy2_candidates", "ma60_slope", "REAL")
    _ensure_column(conn, "strategy2_candidates", "drawdown_from_high_60", "REAL")
    _ensure_column(conn, "strategy2_candidates", "center_shift_20", "REAL")
    _ensure_column(conn, "strategy2_candidates", "price_position_60", "REAL")
    _ensure_column(conn, "strategy2_candidates", "linear_trend_60", "REAL")
    _ensure_column(conn, "strategy2_candidates", "drawdown_from_high_120", "REAL")
    _ensure_column(conn, "strategy2_candidates", "center_shift_40", "REAL")
    _ensure_column(conn, "strategy2_candidates", "return_20", "REAL")
    _ensure_column(conn, "strategy2_candidates", "return_60", "REAL")
    _ensure_column(conn, "strategy2_candidates", "downtrend_conditions", "TEXT")
    _ensure_column(conn, "strategy2_candidates", "short_term_time_exit_days", "INTEGER DEFAULT 0")


def _ensure_strategy3_candidates_table(conn: sqlite3.Connection):
    """Create strategy3_candidates table if not exists (compatible migration)."""
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy3_candidates (
            id                         INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id                    TEXT NOT NULL,
            code                       TEXT NOT NULL,
            name                       TEXT NOT NULL,
            evaluation_date            TEXT NOT NULL,
            total_score                INTEGER NOT NULL,
            level                      TEXT NOT NULL,
            trend_score                INTEGER DEFAULT 0,
            pullback_score             INTEGER DEFAULT 0,
            volume_stability_score     INTEGER DEFAULT 0,
            second_breakout_score      INTEGER DEFAULT 0,
            risk_reward_score          INTEGER DEFAULT 0,
            current_close              REAL DEFAULT 0,
            ma5                        REAL,
            ma10                       REAL,
            ma20                       REAL,
            ma60                       REAL,
            ma120                      REAL,
            recent_high                REAL,
            pullback_pct               REAL,
            relative_strength_60       REAL,
            volume_ratio_5_20          REAL,
            range_5                    REAL,
            close_range_5              REAL,
            support_price              REAL,
            stop_loss                  REAL,
            target_1                   REAL,
            risk_ratio                 REAL,
            rr1                        REAL,
            structural_support         REAL,
            structural_stop_loss       REAL,
            structural_risk_ratio      REAL,
            structural_rr1             REAL,
            tactical_support           REAL,
            tactical_stop_loss         REAL,
            tactical_risk_ratio        REAL,
            tactical_rr1               REAL,
            support_quality            TEXT,
            score_reasons              TEXT,
            reject_reasons             TEXT,
            data_source                TEXT,
            created_at                 TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (task_id) REFERENCES scan_tasks(id),
            UNIQUE (task_id, code)
        )
    ''')
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy3_candidates_task_score "
        "ON strategy3_candidates(task_id, total_score DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy3_candidates_task_risk "
        "ON strategy3_candidates(task_id, risk_ratio ASC)"
    )
    _ensure_column(conn, "strategy3_candidates", "structural_support", "REAL")
    _ensure_column(conn, "strategy3_candidates", "structural_stop_loss", "REAL")
    _ensure_column(conn, "strategy3_candidates", "structural_risk_ratio", "REAL")
    _ensure_column(conn, "strategy3_candidates", "structural_rr1", "REAL")
    _ensure_column(conn, "strategy3_candidates", "tactical_support", "REAL")
    _ensure_column(conn, "strategy3_candidates", "tactical_stop_loss", "REAL")
    _ensure_column(conn, "strategy3_candidates", "tactical_risk_ratio", "REAL")
    _ensure_column(conn, "strategy3_candidates", "tactical_rr1", "REAL")
    _ensure_column(conn, "strategy3_candidates", "support_quality", "TEXT")
    _ensure_column(conn, "strategy3_candidates", "v3", "REAL")
    _ensure_column(conn, "strategy3_candidates", "v5", "REAL")
    _ensure_column(conn, "strategy3_candidates", "v10", "REAL")
    _ensure_column(conn, "strategy3_candidates", "v20", "REAL")
    _ensure_column(conn, "strategy3_candidates", "return_5", "REAL")
    _ensure_column(conn, "strategy3_candidates", "min_close_5", "REAL")
    _ensure_column(conn, "strategy3_candidates", "min_close_10", "REAL")
    _ensure_column(conn, "strategy3_candidates", "no_new_low", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy3_candidates", "support_price_10", "REAL")
    _ensure_column(conn, "strategy3_candidates", "support_test_count", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy3_candidates", "support_valid", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy3_candidates", "bear_body_shrink", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy3_candidates", "lower_shadow_count", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy3_candidates", "down_volume_ratio_5", "REAL")
    _ensure_column(conn, "strategy3_candidates", "atr_ratio_5_20", "REAL")
    _ensure_column(conn, "strategy3_candidates", "has_big_down_volume", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy3_candidates", "short_support", "REAL")
    _ensure_column(conn, "strategy3_candidates", "short_support_zone_low", "REAL")
    _ensure_column(conn, "strategy3_candidates", "short_support_zone_high", "REAL")
    _ensure_column(conn, "strategy3_candidates", "key_support", "REAL")
    _ensure_column(conn, "strategy3_candidates", "key_support_zone_low", "REAL")
    _ensure_column(conn, "strategy3_candidates", "key_support_zone_high", "REAL")
    _ensure_column(conn, "strategy3_candidates", "strong_support", "REAL")
    _ensure_column(conn, "strategy3_candidates", "strong_support_zone_low", "REAL")
    _ensure_column(conn, "strategy3_candidates", "strong_support_zone_high", "REAL")
    _ensure_column(conn, "strategy3_candidates", "support_status", "TEXT")
    _ensure_column(conn, "strategy3_candidates", "break_status", "TEXT")
    _ensure_column(conn, "strategy3_candidates", "nearest_support_distance", "REAL")
    _ensure_column(conn, "strategy3_candidates", "support_sources", "TEXT")


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, col_type: str):
    """Compatible add-column-if-not-exists helper."""
    existing = [d[1] for d in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


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
        "trend_type", "short_mid_score", "long_score", "total_evidence_score",
        "necessary_conditions_met", "ma20", "ma60", "ma120",
        "ma20_slope", "ma60_slope",
        "drawdown_from_high_60", "center_shift_20", "price_position_60",
        "linear_trend_60", "drawdown_from_high_120", "center_shift_40",
        "return_20", "return_60", "downtrend_conditions",
        "short_term_time_exit_days",
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
        d.get("trend_type", ""),
        d.get("short_mid_score", 0), d.get("long_score", 0), d.get("total_evidence_score", 0),
        d.get("necessary_conditions_met", 0),
        d.get("ma20", 0.0), d.get("ma60", 0.0), d.get("ma120"),
        d.get("ma20_slope", 0.0), d.get("ma60_slope"),
        d.get("drawdown_from_high_60", 0.0), d.get("center_shift_20", 0.0),
        d.get("price_position_60", 0.5), d.get("linear_trend_60", 0.0),
        d.get("drawdown_from_high_120", 0.0), d.get("center_shift_40", 0.0),
        d.get("return_20", 0.0), d.get("return_60", 0.0),
        d.get("downtrend_conditions", "[]"),
        d.get("short_term_time_exit_days", 0),
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


def upsert_strategy3_candidate(task_id: str, d: dict):
    """Insert or update a single strategy3 candidate."""
    conn = get_conn()
    columns = [
        "task_id", "code", "name", "evaluation_date", "total_score", "level",
        "trend_score", "pullback_score", "volume_stability_score",
        "second_breakout_score", "risk_reward_score", "current_close",
        "ma5", "ma10", "ma20", "ma60", "ma120", "recent_high",
        "pullback_pct", "relative_strength_60", "volume_ratio_5_20",
        "v3", "v5", "v10", "v20", "return_5", "min_close_5", "min_close_10",
        "no_new_low", "support_price_10", "support_test_count", "support_valid",
        "bear_body_shrink", "lower_shadow_count", "down_volume_ratio_5",
        "atr_ratio_5_20", "has_big_down_volume",
        "range_5", "close_range_5", "support_price", "stop_loss",
        "target_1", "risk_ratio", "rr1",
        "structural_support", "structural_stop_loss", "structural_risk_ratio",
        "structural_rr1", "tactical_support", "tactical_stop_loss",
        "tactical_risk_ratio", "tactical_rr1", "support_quality",
        "short_support", "short_support_zone_low", "short_support_zone_high",
        "key_support", "key_support_zone_low", "key_support_zone_high",
        "strong_support", "strong_support_zone_low", "strong_support_zone_high",
        "support_status", "break_status", "nearest_support_distance", "support_sources",
        "score_reasons", "reject_reasons", "data_source",
    ]
    values = (
        task_id,
        d["code"],
        d.get("name", ""),
        d.get("evaluation_date", ""),
        d.get("total_score", 0),
        d.get("level", ""),
        d.get("trend_score", 0),
        d.get("pullback_score", 0),
        d.get("volume_stability_score", 0),
        d.get("second_breakout_score", 0),
        d.get("risk_reward_score", 0),
        d.get("current_close", 0.0),
        d.get("ma5"),
        d.get("ma10"),
        d.get("ma20"),
        d.get("ma60"),
        d.get("ma120"),
        d.get("recent_high"),
        d.get("pullback_pct"),
        d.get("relative_strength_60"),
        d.get("volume_ratio_5_20"),
        d.get("v3"),
        d.get("v5"),
        d.get("v10"),
        d.get("v20"),
        d.get("return_5"),
        d.get("min_close_5"),
        d.get("min_close_10"),
        int(bool(d.get("no_new_low"))),
        d.get("support_price_10"),
        d.get("support_test_count", 0),
        int(bool(d.get("support_valid"))),
        int(bool(d.get("bear_body_shrink"))),
        d.get("lower_shadow_count", 0),
        d.get("down_volume_ratio_5"),
        d.get("atr_ratio_5_20"),
        int(bool(d.get("has_big_down_volume"))),
        d.get("range_5"),
        d.get("close_range_5"),
        d.get("support_price"),
        d.get("stop_loss"),
        d.get("target_1"),
        d.get("risk_ratio"),
        d.get("rr1"),
        d.get("structural_support"),
        d.get("structural_stop_loss"),
        d.get("structural_risk_ratio"),
        d.get("structural_rr1"),
        d.get("tactical_support"),
        d.get("tactical_stop_loss"),
        d.get("tactical_risk_ratio"),
        d.get("tactical_rr1"),
        d.get("support_quality", ""),
        d.get("short_support"),
        d.get("short_support_zone_low"),
        d.get("short_support_zone_high"),
        d.get("key_support"),
        d.get("key_support_zone_low"),
        d.get("key_support_zone_high"),
        d.get("strong_support"),
        d.get("strong_support_zone_low"),
        d.get("strong_support_zone_high"),
        d.get("support_status", ""),
        d.get("break_status", ""),
        d.get("nearest_support_distance"),
        _json_dumps(d.get("support_sources")),
        _json_dumps(d.get("score_reasons")),
        _json_dumps(d.get("reject_reasons")),
        d.get("data_source", ""),
    )
    marks = ", ".join("?" for _ in columns)
    updates = ", ".join(f"{c}=excluded.{c}" for c in columns if c not in ("task_id", "code"))
    conn.execute(
        f"""INSERT INTO strategy3_candidates ({', '.join(columns)}) VALUES ({marks})
            ON CONFLICT(task_id, code) DO UPDATE SET {updates}""",
        values,
    )
    conn.commit()


def get_strategy3_candidates(task_id: str = None) -> list[dict]:
    """Get strategy3 candidates, optionally filtered by task_id."""
    conn = get_conn()
    if task_id:
        rows = conn.execute(
            "SELECT * FROM strategy3_candidates WHERE task_id=? "
            "ORDER BY total_score DESC, risk_ratio ASC, code ASC",
            (task_id,),
        ).fetchall()
    else:
        latest = conn.execute(
            "SELECT id FROM scan_tasks WHERE status='completed' "
            "AND strategy_type='STRATEGY_3_STRONG_PULLBACK_SECOND_BREAKOUT' "
            "ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if not latest:
            return []
        rows = conn.execute(
            "SELECT * FROM strategy3_candidates WHERE task_id=? "
            "ORDER BY total_score DESC, risk_ratio ASC, code ASC",
            (latest[0],),
        ).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy3_candidates)").fetchall()]
    return [_deserialize_strategy3_candidate(dict(zip(cols, row))) for row in rows]


def get_strategy3_candidate(code: str, task_id: str = None) -> dict | None:
    """Get single strategy3 candidate detail."""
    conn = get_conn()
    if task_id:
        row = conn.execute(
            "SELECT * FROM strategy3_candidates WHERE code=? AND task_id=?",
            (code, task_id),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM strategy3_candidates WHERE code=? ORDER BY id DESC LIMIT 1",
            (code,),
        ).fetchone()
    if not row:
        return None
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy3_candidates)").fetchall()]
    return _deserialize_strategy3_candidate(dict(zip(cols, row)))


def _deserialize_strategy3_candidate(row: dict) -> dict:
    """Convert strategy3 JSON string fields to Python lists."""
    for field in ("score_reasons", "reject_reasons", "support_sources"):
        value = row.get(field)
        if isinstance(value, str) and value:
            try:
                row[field] = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                row[field] = []
        elif not value:
            row[field] = []
    return row


# ═══════════════════════════════════════════════════════════════════════════════
# Strategy2 Backtest Tables
# ═══════════════════════════════════════════════════════════════════════════════

def _ensure_strategy2_backtest_tables(conn: sqlite3.Connection):
    """Create strategy2 backtest tables if not exists (Phase 1 compatible migration)."""
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy2_backtest_tasks (
            id                       TEXT PRIMARY KEY,
            status                   TEXT NOT NULL DEFAULT 'running',
            requested_start_date     TEXT,
            requested_end_date       TEXT,
            actual_start_date        TEXT,
            actual_end_date          TEXT,
            actual_evaluation_start_date TEXT,
            actual_evaluation_end_date TEXT,
            observation_data_end_date   TEXT,
            scope_type               TEXT NOT NULL DEFAULT 'market',
            requested_codes          TEXT,
            max_stocks               INTEGER,
            config_snapshot          TEXT NOT NULL,
            total_stocks             INTEGER DEFAULT 0,
            processed_stocks         INTEGER DEFAULT 0,
            stocks_with_opportunities INTEGER DEFAULT 0,
            opportunities_count      INTEGER DEFAULT 0,
            insufficient_stocks_count INTEGER DEFAULT 0,
            failed_stocks_count      INTEGER DEFAULT 0,
            started_at               TEXT,
            finished_at              TEXT,
            elapsed_seconds          REAL,
            current_code             TEXT,
            current_name             TEXT,
            error                    TEXT,
            backtest_engine_version  TEXT,
            strategy_engine_version  TEXT,
            credibility_status       TEXT,
            execution_model          TEXT,
            sampling_method          TEXT,
            sampling_seed            INTEGER,
            data_snapshot_date       TEXT,
            data_revision_version    TEXT,
            estimated_evaluations    INTEGER DEFAULT 0,
            completed_evaluations    INTEGER DEFAULT 0,
            raw_signals_count        INTEGER DEFAULT 0,
            evaluation_error_days    INTEGER DEFAULT 0,
            summary_json             TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy2_backtest_opportunities (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id               TEXT NOT NULL,
            code                  TEXT NOT NULL,
            name                  TEXT,
            first_detected_date   TEXT NOT NULL,
            last_detected_date    TEXT NOT NULL,
            consecutive_hit_days  INTEGER NOT NULL,
            first_score           INTEGER NOT NULL,
            max_score             INTEGER NOT NULL,
            level                 TEXT,
            entry_close           REAL NOT NULL,
            stop_loss             REAL NOT NULL,
            risk_ratio            REAL,
            trend_type            TEXT,
            trend_evidence_score  INTEGER,
            evaluation_snapshot   TEXT,
            horizon_3             TEXT,
            horizon_5             TEXT,
            horizon_10            TEXT,
            horizon_20            TEXT,
            created_at            TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (task_id) REFERENCES strategy2_backtest_tasks(id)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy2_backtest_signals (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id               TEXT NOT NULL,
            code                  TEXT NOT NULL,
            name                  TEXT,
            evaluation_date       TEXT NOT NULL,
            evaluation_index      INTEGER NOT NULL,
            score                 INTEGER NOT NULL,
            level                 TEXT,
            current_close         REAL NOT NULL,
            stop_loss             REAL,
            risk_ratio            REAL,
            volume_dry_score      INTEGER,
            price_stable_score    INTEGER,
            trend_type            TEXT,
            trend_evidence_score  INTEGER,
            evaluation_snapshot   TEXT NOT NULL,
            UNIQUE (task_id, code, evaluation_date)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy2_backtest_insufficient_stocks (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id          TEXT NOT NULL,
            code             TEXT NOT NULL,
            name             TEXT,
            reason_code      TEXT NOT NULL,
            available_days   INTEGER DEFAULT 0,
            required_days    INTEGER DEFAULT 0,
            earliest_date    TEXT,
            latest_date      TEXT,
            actual_start_date    TEXT,
            actual_end_date      TEXT,
            detail               TEXT,
            FOREIGN KEY (task_id) REFERENCES strategy2_backtest_tasks(id)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS strategy2_backtest_task_stocks (
            task_id                  TEXT NOT NULL,
            code                     TEXT NOT NULL,
            name                     TEXT,
            status                   TEXT NOT NULL DEFAULT 'PENDING',
            available_days           INTEGER DEFAULT 0,
            actual_eval_start_date   TEXT,
            actual_eval_end_date     TEXT,
            evaluation_days          INTEGER DEFAULT 0,
            liquidity_filtered_days  INTEGER DEFAULT 0,
            trend_filtered_days      INTEGER DEFAULT 0,
            rejection_failed_days    INTEGER DEFAULT 0,
            score_failed_days        INTEGER DEFAULT 0,
            risk_failed_days         INTEGER DEFAULT 0,
            invalid_data_days        INTEGER DEFAULT 0,
            evaluation_error_days    INTEGER DEFAULT 0,
            raw_signals_count        INTEGER DEFAULT 0,
            opportunities_count      INTEGER DEFAULT 0,
            error_code               TEXT,
            error_detail             TEXT,
            started_at               TEXT,
            finished_at              TEXT,
            PRIMARY KEY (task_id, code)
        )
    ''')
    # Indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s2_bt_task_status ON strategy2_backtest_tasks(status, started_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s2_bt_opp_task ON strategy2_backtest_opportunities(task_id, first_detected_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s2_bt_opp_stock ON strategy2_backtest_opportunities(task_id, code, first_detected_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s2_bt_insuf_task ON strategy2_backtest_insufficient_stocks(task_id, reason_code)")
    # Phase 1 unique indexes
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_s2_bt_signal ON strategy2_backtest_signals(task_id, code, evaluation_date)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_s2_bt_opp ON strategy2_backtest_opportunities(task_id, code, first_detected_date)")

    # Compatible migration: add execution columns to opportunities
    _ensure_column(conn, "strategy2_backtest_opportunities", "first_signal_id", "INTEGER")
    _ensure_column(conn, "strategy2_backtest_opportunities", "last_signal_id", "INTEGER")
    _ensure_column(conn, "strategy2_backtest_opportunities", "signal_count", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_opportunities", "execution_model", "TEXT")
    _ensure_column(conn, "strategy2_backtest_opportunities", "entry_date", "TEXT")
    _ensure_column(conn, "strategy2_backtest_opportunities", "entry_price", "REAL")
    _ensure_column(conn, "strategy2_backtest_opportunities", "exit_date", "TEXT")
    _ensure_column(conn, "strategy2_backtest_opportunities", "exit_price", "REAL")
    _ensure_column(conn, "strategy2_backtest_opportunities", "exit_reason", "TEXT")
    _ensure_column(conn, "strategy2_backtest_opportunities", "realized_return", "REAL")
    _ensure_column(conn, "strategy2_backtest_opportunities", "mark_to_market_end_return", "REAL")
    _ensure_column(conn, "strategy2_backtest_opportunities", "holding_days", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_opportunities", "available_forward_days", "INTEGER DEFAULT 0")

    # Task table migration: add Phase 1 fields
    _ensure_column(conn, "strategy2_backtest_tasks", "backtest_engine_version", "TEXT")
    _ensure_column(conn, "strategy2_backtest_tasks", "strategy_engine_version", "TEXT")
    _ensure_column(conn, "strategy2_backtest_tasks", "credibility_status", "TEXT")
    _ensure_column(conn, "strategy2_backtest_tasks", "execution_model", "TEXT")
    _ensure_column(conn, "strategy2_backtest_tasks", "sampling_method", "TEXT")
    _ensure_column(conn, "strategy2_backtest_tasks", "sampling_seed", "INTEGER")
    _ensure_column(conn, "strategy2_backtest_tasks", "data_snapshot_date", "TEXT")
    _ensure_column(conn, "strategy2_backtest_tasks", "data_revision_id", "TEXT")
    _ensure_column(conn, "strategy2_backtest_tasks", "data_revision_version", "TEXT")
    _ensure_column(conn, "strategy2_backtest_tasks", "actual_evaluation_start_date", "TEXT")
    _ensure_column(conn, "strategy2_backtest_tasks", "actual_evaluation_end_date", "TEXT")
    _ensure_column(conn, "strategy2_backtest_tasks", "observation_data_end_date", "TEXT")
    _ensure_column(conn, "strategy2_backtest_tasks", "estimated_evaluations", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_tasks", "completed_evaluations", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_tasks", "raw_signals_count", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_tasks", "evaluation_error_days", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_tasks", "summary_json", "TEXT")
    _ensure_column(conn, "strategy2_backtest_tasks", "experiment_snapshot", "TEXT")
    _ensure_column(conn, "strategy2_backtest_tasks", "baseline_task_id", "TEXT")
    _ensure_column(conn, "strategy2_backtest_tasks", "comparison_summary_json", "TEXT")
    _ensure_column(conn, "strategy2_backtest_tasks", "experiment_filtered_days", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_tasks", "experiment_volume_filtered_days", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_tasks", "experiment_score_filtered_days", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_tasks", "entry_confirmation_failed_count", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_tasks", "time_exit_count", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_signals", "baseline_passed", "INTEGER DEFAULT 1")
    _ensure_column(conn, "strategy2_backtest_signals", "experiment_passed", "INTEGER DEFAULT 1")
    _ensure_column(conn, "strategy2_backtest_signals", "experiment_filter_reason", "TEXT")
    _ensure_column(conn, "strategy2_backtest_signals", "opportunity_type", "TEXT")
    _ensure_column(conn, "strategy2_backtest_opportunities", "opportunity_type", "TEXT")
    _ensure_column(conn, "strategy2_backtest_opportunities", "volume_dry_score", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_opportunities", "price_stable_score", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_opportunities", "entry_confirmation_type", "TEXT")
    _ensure_column(conn, "strategy2_backtest_opportunities", "entry_confirmation_date", "TEXT")
    _ensure_column(conn, "strategy2_backtest_opportunities", "entry_confirmation_price", "REAL")
    _ensure_column(conn, "strategy2_backtest_opportunities", "entry_confirmation_status", "TEXT")
    _ensure_column(conn, "strategy2_backtest_opportunities", "time_exit_days", "INTEGER")
    _ensure_column(conn, "strategy2_backtest_opportunities", "market_context_json", "TEXT")
    _ensure_column(conn, "strategy2_backtest_task_stocks", "experiment_filtered_days", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_task_stocks", "experiment_volume_filtered_days", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_task_stocks", "experiment_score_filtered_days", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_task_stocks", "entry_confirmation_failed_count", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_task_stocks", "time_exit_count", "INTEGER DEFAULT 0")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s2_bt_task_baseline ON strategy2_backtest_tasks(baseline_task_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s2_bt_signal_experiment ON strategy2_backtest_signals(task_id, experiment_passed, experiment_filter_reason)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s2_bt_opp_type ON strategy2_backtest_opportunities(task_id, opportunity_type)")

    # Mark old tasks as untrusted
    conn.execute(
        "UPDATE strategy2_backtest_tasks SET credibility_status='LEGACY_UNTRUSTED', "
        "backtest_engine_version='legacy-v1' "
        "WHERE credibility_status IS NULL"
    )
    # task_stocks missing columns
    _ensure_column(conn, "strategy2_backtest_task_stocks", "required_days", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_task_stocks", "observation_data_end_date", "TEXT")
    _ensure_column(conn, "strategy2_backtest_task_stocks", "available_days", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy2_backtest_task_stocks", "earliest_date", "TEXT")
    _ensure_column(conn, "strategy2_backtest_task_stocks", "latest_date", "TEXT")

    from strategy2.version import (
        STRATEGY2_BACKTEST_ENGINE_VERSION,
        STRATEGY2_STRATEGY_ENGINE_VERSION,
    )
    # Historical tasks cannot remain trusted if they fail current baseline rules.
    conn.execute(
        "UPDATE strategy2_backtest_tasks "
        "SET credibility_status='LEGACY_UNTRUSTED', "
        "backtest_engine_version=COALESCE(backtest_engine_version, 'legacy-v1') "
        "WHERE credibility_status='TRUSTED_BASELINE' AND ("
        "LOWER(COALESCE(status, '')) <> 'completed' "
        "OR COALESCE(data_revision_id, '') = '' "
        "OR COALESCE(data_revision_version, '') <> ? "
        "OR COALESCE(backtest_engine_version, '') <> ? "
        "OR COALESCE(strategy_engine_version, '') <> ? "
        "OR summary_json IS NULL "
        "OR COALESCE(processed_stocks, 0) <> COALESCE(total_stocks, 0) "
        "OR COALESCE(failed_stocks_count, 0) > 0 "
        "OR COALESCE(evaluation_error_days, 0) > 0 "
        "OR EXISTS (SELECT 1 FROM strategy2_backtest_task_stocks s "
        "           WHERE s.task_id=strategy2_backtest_tasks.id "
        "             AND s.status IN ('PENDING','RUNNING'))"
        ")",
        (
            STRATEGY2_DATA_REVISION_VERSION,
            STRATEGY2_BACKTEST_ENGINE_VERSION,
            STRATEGY2_STRATEGY_ENGINE_VERSION,
        ),
    )


def mark_running_strategy2_backtests_interrupted() -> list[str]:
    """Make backtests left running by a previous process explicitly resumable."""
    conn = get_conn()
    task_ids = [
        row[0] for row in conn.execute(
            "SELECT id FROM strategy2_backtest_tasks WHERE LOWER(status)='running'"
        ).fetchall()
    ]
    if not task_ids:
        return []
    try:
        conn.execute("BEGIN IMMEDIATE")
        for task_id in task_ids:
            conn.execute(
                "UPDATE strategy2_backtest_tasks "
                "SET status='INTERRUPTED', credibility_status='PHASE1_INCOMPLETE', "
                "error='Interrupted by server restart' WHERE id=?",
                (task_id,),
            )
            conn.execute(
                "UPDATE strategy2_backtest_task_stocks SET status='PENDING' "
                "WHERE task_id=? AND status='RUNNING'",
                (task_id,),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return task_ids


def create_strategy2_backtest_task(task_id: str, payload: dict, config_snapshot: str):
    from strategy2.version import (
        STRATEGY2_BACKTEST_ENGINE_VERSION,
        STRATEGY2_STRATEGY_ENGINE_VERSION,
    )
    conn = get_conn()
    conn.execute(
        """INSERT INTO strategy2_backtest_tasks
           (id, status, requested_start_date, requested_end_date,
            scope_type, requested_codes, max_stocks, config_snapshot,
            total_stocks, started_at, backtest_engine_version, strategy_engine_version)
           VALUES (?, 'running', ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)""",
        (task_id, payload.get("startDate", ""), payload.get("endDate", ""),
         "market" if not payload.get("codes") else "single",
         ",".join(payload.get("codes") or []),
         payload.get("maxStocks", 200),
         config_snapshot,
         datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
         STRATEGY2_BACKTEST_ENGINE_VERSION,
         STRATEGY2_STRATEGY_ENGINE_VERSION),
    )
    updates = {}
    experiment_snapshot = payload.get("experiment_snapshot")
    if experiment_snapshot is None and payload.get("experiment") is not None:
        experiment_snapshot = payload.get("experiment")
    if experiment_snapshot is not None:
        updates["experiment_snapshot"] = (
            experiment_snapshot if isinstance(experiment_snapshot, str)
            else json.dumps(experiment_snapshot, ensure_ascii=False)
        )
    if payload.get("baselineTaskId"):
        updates["baseline_task_id"] = payload.get("baselineTaskId")
    if updates:
        sets = ", ".join(f"{key}=?" for key in updates)
        conn.execute(f"UPDATE strategy2_backtest_tasks SET {sets} WHERE id=?", list(updates.values()) + [task_id])
    conn.commit()


def update_strategy2_backtest_task(task_id: str, **kwargs):
    if not kwargs:
        return
    conn = get_conn()
    sets = ", ".join(f"{k}=?" for k in kwargs)
    values = list(kwargs.values()) + [task_id]
    conn.execute(f"UPDATE strategy2_backtest_tasks SET {sets} WHERE id=?", values)
    conn.commit()


def get_strategy2_backtest_task(task_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM strategy2_backtest_tasks WHERE id=?", (task_id,)
    ).fetchone()
    if not row:
        return None
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy2_backtest_tasks)")]
    return dict(zip(cols, row))


def get_strategy2_backtest_tasks(
    page: int = 1, page_size: int = 20, status: str | None = None,
) -> tuple[list[dict], int]:
    conn = get_conn()
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    where = ""
    params = []
    if status:
        where = " WHERE LOWER(status)=LOWER(?)"
        params.append(status)
    total = conn.execute(
        "SELECT COUNT(*) FROM strategy2_backtest_tasks" + where, params
    ).fetchone()[0]
    rows = conn.execute(
        "SELECT * FROM strategy2_backtest_tasks" + where
        + " ORDER BY started_at DESC LIMIT ? OFFSET ?",
        params + [page_size, (page - 1) * page_size],
    ).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy2_backtest_tasks)")]
    return [dict(zip(cols, r)) for r in rows], total


def save_strategy2_backtest_signal(task_id: str, signal):
    """保存原始命中信号（幂等：ON CONFLICT 更新）。"""
    conn = get_conn()
    if hasattr(signal, 'evaluation_date'):
        # BacktestSignal dataclass
        snapshot_json = json.dumps(signal.evaluation_snapshot, ensure_ascii=False) if signal.evaluation_snapshot else "{}"
        conn.execute(
            """INSERT INTO strategy2_backtest_signals
               (task_id, code, name, evaluation_date, evaluation_index,
                score, level, current_close, stop_loss, risk_ratio,
                volume_dry_score, price_stable_score, trend_type, trend_evidence_score,
                evaluation_snapshot, baseline_passed, experiment_passed,
                experiment_filter_reason, opportunity_type)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(task_id, code, evaluation_date) DO UPDATE SET
                score=excluded.score, level=excluded.level,
                current_close=excluded.current_close, stop_loss=excluded.stop_loss,
                risk_ratio=excluded.risk_ratio,
                experiment_passed=excluded.experiment_passed,
                experiment_filter_reason=excluded.experiment_filter_reason,
                opportunity_type=excluded.opportunity_type""",
            (task_id, signal.code, signal.name, signal.evaluation_date,
             signal.evaluation_index, signal.score, signal.level,
             signal.current_close, signal.stop_loss, signal.risk_ratio,
             signal.volume_dry_score, signal.price_stable_score,
             signal.trend_type, signal.trend_evidence_score, snapshot_json,
             1 if getattr(signal, "baseline_passed", True) else 0,
             1 if getattr(signal, "experiment_passed", True) else 0,
             getattr(signal, "experiment_filter_reason", ""),
             getattr(signal, "opportunity_type", "")),
        )
    else:
        # 兼容 dict
        conn.execute(
            """INSERT INTO strategy2_backtest_signals
               (task_id, code, name, evaluation_date, evaluation_index,
                score, level, current_close, stop_loss, risk_ratio,
                volume_dry_score, price_stable_score, trend_type, trend_evidence_score,
                evaluation_snapshot, baseline_passed, experiment_passed,
                experiment_filter_reason, opportunity_type)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(task_id, code, evaluation_date) DO NOTHING""",
            (task_id, signal.get("code"), signal.get("name"),
             signal.get("evaluation_date"), signal.get("evaluation_index", 0),
             signal.get("score", 0), signal.get("level", ""),
             signal.get("current_close", 0.0), signal.get("stop_loss", 0.0),
             signal.get("risk_ratio", 0.0), signal.get("volume_dry_score", 0),
             signal.get("price_stable_score", 0), signal.get("trend_type", ""),
             signal.get("trend_evidence_score", 0),
             json.dumps(signal.get("evaluation_snapshot", {}), ensure_ascii=False),
             1 if signal.get("baseline_passed", True) else 0,
             1 if signal.get("experiment_passed", True) else 0,
             signal.get("experiment_filter_reason", ""),
             signal.get("opportunity_type", "")),
        )
    conn.commit()


def save_strategy2_backtest_opportunity(task_id: str, opp: dict):
    conn = get_conn()
    conn.execute(
        """INSERT INTO strategy2_backtest_opportunities
           (task_id, code, name, first_detected_date, last_detected_date,
            consecutive_hit_days, first_score, max_score, level,
            entry_close, stop_loss, risk_ratio, trend_type, trend_evidence_score,
            evaluation_snapshot, horizon_3, horizon_5, horizon_10, horizon_20,
            signal_count, execution_model, entry_date, entry_price,
            exit_date, exit_price, exit_reason, realized_return,
            mark_to_market_end_return, holding_days, available_forward_days,
            opportunity_type, volume_dry_score, price_stable_score,
            entry_confirmation_type, entry_confirmation_date,
            entry_confirmation_price, entry_confirmation_status, time_exit_days,
            market_context_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (task_id, opp["code"], opp.get("name", ""), opp["first_detected_date"],
         opp["last_detected_date"], opp["consecutive_hit_days"],
         opp["first_score"], opp["max_score"], opp.get("level", ""),
         opp["entry_close"], opp["stop_loss"], opp.get("risk_ratio"),
         opp.get("trend_type", ""), opp.get("trend_evidence_score", 0),
         opp.get("evaluation_snapshot", "{}"),
         opp.get("horizon_3", "{}"), opp.get("horizon_5", "{}"),
         opp.get("horizon_10", "{}"), opp.get("horizon_20", "{}"),
         opp.get("signal_count", 0),
         opp.get("execution_model", ""), opp.get("entry_date", ""),
         opp.get("entry_price", 0), opp.get("exit_date", ""),
         opp.get("exit_price", 0), opp.get("exit_reason", ""),
         opp.get("realized_return", 0), opp.get("mark_to_market_end_return", 0),
         opp.get("holding_days", 0), opp.get("available_forward_days", 0),
         opp.get("opportunity_type", ""),
         opp.get("volume_dry_score", 0),
         opp.get("price_stable_score", 0),
         opp.get("entry_confirmation_type", ""),
         opp.get("entry_confirmation_date", ""),
         opp.get("entry_confirmation_price", 0),
         opp.get("entry_confirmation_status", ""),
         opp.get("time_exit_days"),
         opp.get("market_context_json", "{}")),
    )
    conn.commit()


def save_strategy2_backtest_task_stock(task_id: str, code: str, **kwargs):
    conn = get_conn()
    existing = conn.execute(
        "SELECT 1 FROM strategy2_backtest_task_stocks WHERE task_id=? AND code=?", (task_id, code)
    ).fetchone()
    if existing:
        sets = ", ".join(f"{k}=?" for k in kwargs)
        vals = list(kwargs.values()) + [task_id, code]
        conn.execute(f"UPDATE strategy2_backtest_task_stocks SET {sets} WHERE task_id=? AND code=?", vals)
    else:
        cols = ["task_id", "code"] + list(kwargs.keys())
        placeholders = ", ".join("?" for _ in cols)
        vals = [task_id, code] + list(kwargs.values())
        conn.execute(f"INSERT INTO strategy2_backtest_task_stocks ({', '.join(cols)}) VALUES ({placeholders})", vals)
    conn.commit()


def get_strategy2_backtest_task_stocks(task_id: str, status: str = None) -> list[dict]:
    conn = get_conn()
    if status:
        rows = conn.execute(
            "SELECT * FROM strategy2_backtest_task_stocks WHERE task_id=? AND status=? ORDER BY code",
            (task_id, status)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM strategy2_backtest_task_stocks WHERE task_id=? ORDER BY code",
            (task_id,)).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy2_backtest_task_stocks)")]
    return [dict(zip(cols, r)) for r in rows]


def build_strategy2_backtest_summary(task_id: str) -> dict:
    """从数据库完整明细生成汇总。horizon统计使用 horizon_N JSON 字段。"""
    import statistics as _st
    conn = get_conn()
    opps = conn.execute(
        "SELECT * FROM strategy2_backtest_opportunities WHERE task_id=?", (task_id,)
    ).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy2_backtest_opportunities)")]
    opps = [dict(zip(cols, r)) for r in opps]

    # ── 周期观察统计（使用 horizon_N JSON）──
    horizon_stats = {}
    for h in ["3", "5", "10", "20"]:
        end_returns, max_upsides, max_drawdowns = [], [], []
        days_to_target, days_to_stop = [], []
        observed, success, failed, unresolved, unobserved = 0, 0, 0, 0, 0
        for o in opps:
            try:
                raw = o.get(f"horizon_{h}", "{}")
                d = __import__("json").loads(raw) if raw else {}
            except Exception:
                d = {}
            r = d.get("result", "UNOBSERVED")
            if r == "UNOBSERVED":
                unobserved += 1
            else:
                observed += 1
                end_returns.append(d.get("end_return", 0))
                max_upsides.append(d.get("max_upside", 0))
                max_drawdowns.append(d.get("max_drawdown", 0))
                if r == "SUCCESS":
                    success += 1
                    if d.get("days_to_target") is not None:
                        days_to_target.append(d["days_to_target"])
                elif r == "FAILED":
                    failed += 1
                    if d.get("days_to_stop") is not None:
                        days_to_stop.append(d["days_to_stop"])
                elif r == "UNRESOLVED":
                    unresolved += 1
        decisive = success + failed
        horizon_stats[h] = {
            "observed": observed, "unobserved": unobserved,
            "success": success, "failed": failed, "unresolved": unresolved,
            "success_rate": round(success / observed * 100, 2) if observed else 0,       # 前端兼容
            "failed_rate": round(failed / observed * 100, 2) if observed else 0,          # 前端兼容
            "target_hit_rate": round(success / observed * 100, 2) if observed else 0,
            "stop_hit_rate": round(failed / observed * 100, 2) if observed else 0,
            "unresolved_rate": round(unresolved / observed * 100, 2) if observed else 0,
            "decisive_win_rate": round(success / decisive * 100, 2) if decisive else 0,
            "avg_end_return": round(_st.mean(end_returns), 6) if end_returns else 0,
            "median_end_return": round(_st.median(end_returns), 6) if end_returns else 0,
            "avg_max_upside": round(_st.mean(max_upsides), 6) if max_upsides else 0,
            "median_max_upside": round(_st.median(max_upsides), 6) if max_upsides else 0,
            "avg_max_drawdown": round(_st.mean(max_drawdowns), 6) if max_drawdowns else 0,
            "median_max_drawdown": round(_st.median(max_drawdowns), 6) if max_drawdowns else 0,
            "avg_days_to_target": round(_st.mean(days_to_target), 1) if days_to_target else None,
            "avg_days_to_stop": round(_st.mean(days_to_stop), 1) if days_to_stop else None,
        }

    # ── 整笔交易执行统计（使用机会执行字段）──
    entered_opps = [o for o in opps if o.get("entry_price") and o["entry_price"] > 0]
    entered = len(entered_opps)
    target = sum(1 for o in opps if o.get("exit_reason") == "TARGET")
    stop = sum(1 for o in opps if o.get("exit_reason") == "STOP")
    unresolved = sum(1 for o in opps if o.get("exit_reason") == "UNRESOLVED")
    not_entered = len(opps) - entered
    realized_returns = [o["realized_return"] or 0 for o in entered_opps]
    holding_days = [o.get("holding_days") or 0 for o in entered_opps if o.get("holding_days")]
    positive = sum(1 for rr in realized_returns if rr > 0)

    funnel_columns = [
        "evaluation_days",
        "liquidity_filtered_days",
        "trend_filtered_days",
        "rejection_failed_days",
        "score_failed_days",
        "risk_failed_days",
        "invalid_data_days",
        "evaluation_error_days",
        "raw_signals_count",
        "opportunities_count",
    ]
    funnel_row = conn.execute(
        "SELECT " + ", ".join(f"COALESCE(SUM({column}), 0)" for column in funnel_columns)
        + " FROM strategy2_backtest_task_stocks WHERE task_id=?",
        (task_id,),
    ).fetchone()
    funnel = dict(zip(funnel_columns, funnel_row))
    experiment_columns = [
        "experiment_filtered_days",
        "experiment_volume_filtered_days",
        "experiment_score_filtered_days",
        "entry_confirmation_failed_count",
        "time_exit_count",
    ]
    experiment_row = conn.execute(
        "SELECT " + ", ".join(f"COALESCE(SUM({column}), 0)" for column in experiment_columns)
        + " FROM strategy2_backtest_task_stocks WHERE task_id=?",
        (task_id,),
    ).fetchone()
    experiment_funnel = dict(zip(experiment_columns, experiment_row))

    def _score_band(value) -> str:
        try:
            ivalue = int(value or 0)
        except Exception:
            ivalue = 0
        lower = max(0, min(100, (ivalue // 10) * 10))
        if lower == 100:
            return "100"
        return f"{lower}-{lower + 9}"

    def _group_key(row: dict, kind: str) -> str:
        if kind == "month":
            return str(row.get("first_detected_date") or "")[:7] or "UNKNOWN"
        if kind == "opportunity_type":
            return row.get("opportunity_type") or "UNKNOWN"
        if kind == "volume_dry_score_band":
            return _score_band(row.get("volume_dry_score"))
        if kind == "price_stable_score_band":
            return _score_band(row.get("price_stable_score"))
        if kind == "total_score_band":
            return _score_band(row.get("first_score"))
        if kind == "entry_confirmation_status":
            return row.get("entry_confirmation_status") or "UNKNOWN"
        return "UNKNOWN"

    def _summarize_group(rows: list[dict]) -> dict:
        entered_rows = [row for row in rows if row.get("entry_price") and row["entry_price"] > 0]
        realized_returns = [row.get("realized_return") or 0 for row in entered_rows]
        target = sum(1 for row in rows if row.get("exit_reason") == "TARGET")
        stop = sum(1 for row in rows if row.get("exit_reason") == "STOP")
        entered = len(entered_rows)
        return {
            "opportunities": len(rows),
            "entered": entered,
            "target": target,
            "stop": stop,
            "target_hit_rate": round(target / entered * 100, 2) if entered else 0,
            "stop_hit_rate": round(stop / entered * 100, 2) if entered else 0,
            "average_realized_return": round(_st.mean(realized_returns), 6) if realized_returns else 0,
            "median_realized_return": round(_st.median(realized_returns), 6) if realized_returns else 0,
        }

    def _group_by(kind: str) -> dict:
        grouped = {}
        for row in opps:
            grouped.setdefault(_group_key(row, kind), []).append(row)
        return {key: _summarize_group(rows) for key, rows in sorted(grouped.items())}

    groups = {
        "by_month": _group_by("month"),
        "by_opportunity_type": _group_by("opportunity_type"),
        "by_volume_dry_score_band": _group_by("volume_dry_score_band"),
        "by_price_stable_score_band": _group_by("price_stable_score_band"),
        "by_total_score_band": _group_by("total_score_band"),
        "by_entry_confirmation_status": _group_by("entry_confirmation_status"),
    }

    return {
        "horizon_stats": horizon_stats,
        "execution_stats": {
            "opportunities": len(opps), "entered": entered,
            "target": target, "stop": stop, "unresolved": unresolved,
            "not_entered": not_entered,
            "target_hit_rate": round(target / entered * 100, 2) if entered else 0,
            "avg_realized_return": round(_st.mean(realized_returns), 6) if realized_returns else 0,
            "median_realized_return": round(_st.median(realized_returns), 6) if realized_returns else 0,
            "positive_rate": round(positive / entered * 100, 2) if entered else 0,
            "avg_holding_days": round(_st.mean(holding_days), 1) if holding_days else 0,
        },
        "funnel": funnel,
        "experiment_funnel": experiment_funnel,
        "groups": groups,
        "integrity": {},
    }


def validate_strategy2_backtest_integrity(task_id: str) -> tuple:
    """校验任务完整性。返回 (passed: bool, errors: list[str])。"""
    conn = get_conn()
    errors = []
    task = conn.execute("SELECT * FROM strategy2_backtest_tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        return False, ["task_not_found"]
    tcols = [d[1] for d in conn.execute("PRAGMA table_info(strategy2_backtest_tasks)")]
    t = dict(zip(tcols, task))

    if str(t.get("status", "")).lower() != "completed":
        errors.append(f"task status is {t.get('status')}, expected completed")
    if not t.get("data_revision_id"):
        errors.append("missing data_revision_id")
    if t.get("data_revision_version") != STRATEGY2_DATA_REVISION_VERSION:
        errors.append(f"invalid data_revision_version: {t.get('data_revision_version')}")
    from strategy2.version import (
        STRATEGY2_BACKTEST_ENGINE_VERSION,
        STRATEGY2_STRATEGY_ENGINE_VERSION,
    )
    if t.get("backtest_engine_version") != STRATEGY2_BACKTEST_ENGINE_VERSION:
        errors.append(f"invalid backtest_engine_version: {t.get('backtest_engine_version')}")
    if t.get("strategy_engine_version") != STRATEGY2_STRATEGY_ENGINE_VERSION:
        errors.append(f"invalid strategy_engine_version: {t.get('strategy_engine_version')}")

    total = t.get("total_stocks", 0)
    processed = t.get("processed_stocks", 0)
    stocks_cnt = conn.execute("SELECT COUNT(*) FROM strategy2_backtest_task_stocks WHERE task_id=?", (task_id,)).fetchone()[0]
    if stocks_cnt != total:
        errors.append(f"task_stocks count mismatch: {stocks_cnt} != {total}")
    pending = conn.execute("SELECT COUNT(*) FROM strategy2_backtest_task_stocks WHERE task_id=? AND status IN ('PENDING','RUNNING')", (task_id,)).fetchone()[0]
    if pending > 0:
        errors.append(f"{pending} stocks still PENDING/RUNNING")
    if processed != total:
        errors.append(f"processed {processed} != total {total}")

    sig_cnt = conn.execute("SELECT COUNT(*) FROM strategy2_backtest_signals WHERE task_id=?", (task_id,)).fetchone()[0]
    stock_sig = conn.execute("SELECT COALESCE(SUM(raw_signals_count),0) FROM strategy2_backtest_task_stocks WHERE task_id=?", (task_id,)).fetchone()[0]
    if sig_cnt != stock_sig:
        errors.append(f"signal delta: {sig_cnt} vs {stock_sig}")

    opp_cnt = conn.execute("SELECT COUNT(*) FROM strategy2_backtest_opportunities WHERE task_id=?", (task_id,)).fetchone()[0]
    stock_opp = conn.execute("SELECT COALESCE(SUM(opportunities_count),0) FROM strategy2_backtest_task_stocks WHERE task_id=?", (task_id,)).fetchone()[0]
    if opp_cnt != stock_opp:
        errors.append(f"opportunity delta: {opp_cnt} vs {stock_opp}")

    if not t.get("observation_data_end_date"):
        errors.append("missing observation_data_end_date")
    if not t.get("summary_json"):
        errors.append("missing summary_json")
    else:
        try:
            s = __import__("json").loads(t["summary_json"])
            hs = s.get("horizon_stats", {})
            for h in ["3", "5", "10", "20"]:
                if h not in hs:
                    errors.append(f"missing horizon_stats {h}")
        except Exception:
            errors.append("invalid summary_json")

    if t.get("evaluation_error_days", 0) > 0:
        errors.append(f"evaluation_error_days={t['evaluation_error_days']} > 0")
    failed = t.get("failed_stocks_count", 0)
    if failed > 0:
        errors.append(f"failed_stocks_count={failed} > 0")

    return (len(errors) == 0), errors


def replace_strategy2_stock_backtest_result(
    task_id: str, code: str, name: str, result: dict,
) -> None:
    """原子替换单只股票的回测结果（事务化）。"""
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        # 删除旧结果
        conn.execute("DELETE FROM strategy2_backtest_opportunities WHERE task_id=? AND code=?", (task_id, code))
        conn.execute("DELETE FROM strategy2_backtest_signals WHERE task_id=? AND code=?", (task_id, code))

        # 插入信号，记录日期→ID映射
        signal_id_by_date = {}
        for sig in (result.get("signals") or []):
            if hasattr(sig, 'evaluation_date'):
                edate = sig.evaluation_date
                snapshot = (json.dumps(sig.evaluation_snapshot, ensure_ascii=False)
                            if sig.evaluation_snapshot else "{}")
                c = conn.execute(
                    """INSERT INTO strategy2_backtest_signals
                       (task_id, code, name, evaluation_date, evaluation_index,
                        score, level, current_close, stop_loss, risk_ratio,
                        volume_dry_score, price_stable_score, trend_type, trend_evidence_score,
                        evaluation_snapshot, baseline_passed, experiment_passed,
                        experiment_filter_reason, opportunity_type)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (task_id, code, name, edate, sig.evaluation_index, sig.score,
                     sig.level, sig.current_close, sig.stop_loss, sig.risk_ratio,
                     sig.volume_dry_score, sig.price_stable_score, sig.trend_type,
                     sig.trend_evidence_score, snapshot,
                     1 if getattr(sig, "baseline_passed", True) else 0,
                     1 if getattr(sig, "experiment_passed", True) else 0,
                     getattr(sig, "experiment_filter_reason", ""),
                     getattr(sig, "opportunity_type", "")),
                )
                signal_id_by_date[edate] = c.lastrowid
            else:
                edate = sig.get("evaluation_date", "")
                c = conn.execute(
                    """INSERT INTO strategy2_backtest_signals
                       (task_id, code, name, evaluation_date, evaluation_index, score, level,
                        current_close, stop_loss, risk_ratio, volume_dry_score,
                        price_stable_score, trend_type, trend_evidence_score, evaluation_snapshot,
                        baseline_passed, experiment_passed, experiment_filter_reason, opportunity_type)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (task_id, code, name, edate, sig.get("evaluation_index", 0),
                     sig.get("score", 0), sig.get("level", ""), sig.get("current_close", 0),
                     sig.get("stop_loss", 0), sig.get("risk_ratio", 0), sig.get("volume_dry_score", 0),
                     sig.get("price_stable_score", 0), sig.get("trend_type", ""),
                     sig.get("trend_evidence_score", 0),
                     json.dumps(sig.get("evaluation_snapshot", {}), ensure_ascii=False),
                     1 if sig.get("baseline_passed", True) else 0,
                     1 if sig.get("experiment_passed", True) else 0,
                     sig.get("experiment_filter_reason", ""),
                     sig.get("opportunity_type", "")),
                )
                signal_id_by_date[edate] = c.lastrowid

        # 插入机会，关联信号ID
        for opp in (result.get("opportunities") or []):
            first_sid = signal_id_by_date.get(opp["first_detected_date"])
            last_sid = signal_id_by_date.get(opp["last_detected_date"])
            conn.execute(
                """INSERT INTO strategy2_backtest_opportunities
                   (task_id, code, name, first_detected_date, last_detected_date,
                    consecutive_hit_days, first_score, max_score, level,
                    entry_close, stop_loss, risk_ratio, trend_type, trend_evidence_score,
                    evaluation_snapshot, horizon_3, horizon_5, horizon_10, horizon_20,
                    signal_count, execution_model, entry_date, entry_price,
                    exit_date, exit_price, exit_reason, realized_return,
                    mark_to_market_end_return, holding_days, available_forward_days,
                    first_signal_id, last_signal_id, opportunity_type,
                    volume_dry_score, price_stable_score,
                    entry_confirmation_type, entry_confirmation_date,
                    entry_confirmation_price, entry_confirmation_status,
                    time_exit_days, market_context_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (task_id, code, name, opp["first_detected_date"], opp["last_detected_date"],
                 opp["consecutive_hit_days"], opp["first_score"], opp["max_score"],
                 opp.get("level", ""), opp["entry_close"], opp["stop_loss"],
                 opp.get("risk_ratio"), opp.get("trend_type", ""),
                 opp.get("trend_evidence_score", 0), opp.get("evaluation_snapshot", "{}"),
                 opp.get("horizon_3", "{}"), opp.get("horizon_5", "{}"),
                 opp.get("horizon_10", "{}"), opp.get("horizon_20", "{}"),
                 opp.get("signal_count", 0), opp.get("execution_model", ""),
                 opp.get("entry_date", ""), opp.get("entry_price", 0),
                 opp.get("exit_date", ""), opp.get("exit_price", 0),
                 opp.get("exit_reason", ""), opp.get("realized_return", 0),
                 opp.get("mark_to_market_end_return", 0), opp.get("holding_days", 0),
                 opp.get("available_forward_days", 0), first_sid, last_sid,
                 opp.get("opportunity_type", ""),
                 opp.get("volume_dry_score", 0),
                 opp.get("price_stable_score", 0),
                 opp.get("entry_confirmation_type", ""),
                 opp.get("entry_confirmation_date", ""),
                 opp.get("entry_confirmation_price", 0),
                 opp.get("entry_confirmation_status", ""),
                 opp.get("time_exit_days"),
                 opp.get("market_context_json", "{}")),
            )

        # 更新股票终态
        update_kwargs = {k: v for k, v in {
            "status": "COMPLETED", "name": name,
            "evaluation_days": result.get("eval_days", 0),
            "liquidity_filtered_days": result.get("liquidity_filtered_days", 0),
            "trend_filtered_days": result.get("trend_filtered_days", 0),
            "rejection_failed_days": result.get("rejection_failed_days", 0),
            "score_failed_days": result.get("score_failed_days", 0),
            "risk_failed_days": result.get("risk_failed_days", 0),
            "invalid_data_days": result.get("invalid_data_days", 0),
            "evaluation_error_days": result.get("evaluation_error_days", 0),
            "raw_signals_count": result.get("raw_signals_count", 0),
            "opportunities_count": result.get("opportunities_count", 0),
            "actual_eval_start_date": result.get("actual_eval_start_date"),
            "actual_eval_end_date": result.get("actual_eval_end_date"),
            "observation_data_end_date": result.get("observation_data_end_date"),
            "available_days": result.get("available_days", 0),
            "required_days": result.get("required_days", 250),
            "earliest_date": result.get("earliest_date"),
            "latest_date": result.get("latest_date"),
            "experiment_filtered_days": result.get("experiment_filtered_days", 0),
            "experiment_volume_filtered_days": result.get("experiment_volume_filtered_days", 0),
            "experiment_score_filtered_days": result.get("experiment_score_filtered_days", 0),
            "entry_confirmation_failed_count": result.get("entry_confirmation_failed_count", 0),
            "time_exit_count": result.get("time_exit_count", 0),
            "started_at": result.get("started_at"),
            "finished_at": result.get("finished_at"),
        }.items() if v is not None}
        if update_kwargs:
            sets = ", ".join(f"{k}=?" for k in update_kwargs)
            vals = list(update_kwargs.values()) + [task_id, code]
            conn.execute(f"UPDATE strategy2_backtest_task_stocks SET {sets} WHERE task_id=? AND code=?", vals)

        conn.commit()
    except Exception:
        conn.rollback()
        raise


def get_strategy2_backtest_opportunities(
    task_id: str, code: str = None, limit: int = 500, offset: int = 0,
) -> list[dict]:
    conn = get_conn()
    if code:
        rows = conn.execute(
            "SELECT * FROM strategy2_backtest_opportunities "
            "WHERE task_id=? AND code=? ORDER BY first_detected_date LIMIT ? OFFSET ?",
            (task_id, code, limit, offset),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM strategy2_backtest_opportunities "
            "WHERE task_id=? ORDER BY first_detected_date LIMIT ? OFFSET ?",
            (task_id, limit, offset),
        ).fetchall()
    cols = [d[1] for d in conn.execute(
        "PRAGMA table_info(strategy2_backtest_opportunities)"
    )]
    return [dict(zip(cols, r)) for r in rows]


def summarize_strategy2_backtest_for_comparison(task_id: str) -> dict:
    """Return compact execution metrics for baseline/experiment comparison."""
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*), "
        "SUM(CASE WHEN COALESCE(entry_price,0)>0 THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN exit_reason='TARGET' THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN exit_reason='STOP' THEN 1 ELSE 0 END), "
        "AVG(CASE WHEN COALESCE(entry_price,0)>0 THEN COALESCE(realized_return,0) END) "
        "FROM strategy2_backtest_opportunities WHERE task_id=?",
        (task_id,),
    ).fetchone()
    opportunities, entered, target, stop, avg_return = row
    opportunities = opportunities or 0
    entered = entered or 0
    target = target or 0
    stop = stop or 0
    return {
        "opportunities": opportunities,
        "entered": entered,
        "target": target,
        "stop": stop,
        "successRate": round(target / entered, 6) if entered else 0.0,
        "stopRate": round(stop / entered, 6) if entered else 0.0,
        "averageRealizedReturn": round(avg_return or 0.0, 6),
    }


def compare_strategy2_backtest_tasks(experiment_task_id: str, baseline_task_id: str) -> dict:
    """Compare two completed Strategy2 backtest tasks and explain incompatibility."""
    baseline = get_strategy2_backtest_task(baseline_task_id)
    experiment = get_strategy2_backtest_task(experiment_task_id)
    if not baseline or not experiment:
        return {
            "comparable": False,
            "baselineTaskId": baseline_task_id,
            "experimentTaskId": experiment_task_id,
            "reasons": ["task_not_found"],
        }

    checks = [
        "requested_start_date",
        "requested_end_date",
        "requested_codes",
        "max_stocks",
        "execution_model",
        "backtest_engine_version",
        "strategy_engine_version",
        "data_revision_version",
        "data_revision_id",
    ]
    reasons = [key for key in checks if (baseline.get(key) or "") != (experiment.get(key) or "")]
    if baseline.get("credibility_status") != "TRUSTED_BASELINE":
        reasons.append("baseline_credibility_status")
    if experiment.get("credibility_status") != "EXPERIMENTAL":
        reasons.append("experiment_credibility_status")

    base_summary = summarize_strategy2_backtest_for_comparison(baseline_task_id)
    exp_summary = summarize_strategy2_backtest_for_comparison(experiment_task_id)
    delta = {
        key: round(exp_summary.get(key, 0) - base_summary.get(key, 0), 6)
        for key in {
            "opportunities", "entered", "target", "stop",
            "successRate", "stopRate", "averageRealizedReturn",
        }
    }
    return {
        "comparable": len(reasons) == 0,
        "baselineTaskId": baseline_task_id,
        "experimentTaskId": experiment_task_id,
        "reasons": reasons,
        "baseline": base_summary,
        "experiment": exp_summary,
        "delta": delta,
    }


def save_strategy2_backtest_insufficient_stocks(task_id: str, stocks: list[dict]):
    if not stocks:
        return
    conn = get_conn()
    for s in stocks:
        conn.execute(
            """INSERT INTO strategy2_backtest_insufficient_stocks
               (task_id, code, name, reason_code, available_days, required_days,
                earliest_date, latest_date, actual_start_date, actual_end_date, detail)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (task_id, s["code"], s.get("name", ""), s["reason_code"],
             s.get("available_days", 0), s.get("required_days", 0),
             s.get("earliest_date", ""), s.get("latest_date", ""),
             s.get("actual_start_date", ""), s.get("actual_end_date", ""),
             s.get("detail", "")),
        )
    conn.commit()


def get_strategy2_backtest_insufficient_stocks(task_id: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM strategy2_backtest_insufficient_stocks "
        "WHERE task_id=? ORDER BY reason_code, code",
        (task_id,),
    ).fetchall()
    cols = [d[1] for d in conn.execute(
        "PRAGMA table_info(strategy2_backtest_insufficient_stocks)"
    )]
    return [dict(zip(cols, r)) for r in rows]


# ====== Strategy1 Trusted Backtest ======

STRATEGY1_DATA_REVISION_VERSION = "daily-ohlc-v1"


def _ensure_strategy1_backtest_tables(conn: sqlite3.Connection):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS strategy1_backtest_tasks (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            credibility_status TEXT,
            requested_start_date TEXT,
            requested_end_date TEXT,
            actual_evaluation_start_date TEXT,
            actual_evaluation_end_date TEXT,
            observation_data_end_date TEXT,
            scope_type TEXT,
            requested_codes TEXT,
            max_stocks INTEGER,
            config_snapshot TEXT NOT NULL,
            experiment_snapshot TEXT,
            baseline_task_id TEXT,
            comparison_summary_json TEXT,
            strategy_engine_version TEXT,
            backtest_engine_version TEXT,
            data_revision_version TEXT,
            data_revision_id TEXT,
            execution_model TEXT,
            total_stocks INTEGER DEFAULT 0,
            processed_stocks INTEGER DEFAULT 0,
            failed_stocks_count INTEGER DEFAULT 0,
            insufficient_stocks_count INTEGER DEFAULT 0,
            raw_signals_count INTEGER DEFAULT 0,
            opportunities_count INTEGER DEFAULT 0,
            summary_json TEXT,
            started_at TEXT,
            finished_at TEXT,
            elapsed_seconds REAL,
            error TEXT
        );

        CREATE TABLE IF NOT EXISTS strategy1_backtest_task_stocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT,
            status TEXT NOT NULL,
            available_days INTEGER DEFAULT 0,
            required_days INTEGER DEFAULT 0,
            earliest_date TEXT,
            latest_date TEXT,
            actual_start_date TEXT,
            actual_end_date TEXT,
            raw_signals_count INTEGER DEFAULT 0,
            opportunities_count INTEGER DEFAULT 0,
            evaluation_days INTEGER DEFAULT 0,
            filtered_days INTEGER DEFAULT 0,
            error_code TEXT,
            error_detail TEXT,
            UNIQUE(task_id, code)
        );

        CREATE TABLE IF NOT EXISTS strategy1_backtest_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT,
            evaluation_date TEXT NOT NULL,
            evaluation_index INTEGER DEFAULT 0,
            pattern_kind TEXT,
            score INTEGER DEFAULT 0,
            cup_depth_pct REAL DEFAULT 0,
            cup_duration INTEGER DEFAULT 0,
            handle_depth_pct REAL DEFAULT 0,
            handle_duration INTEGER DEFAULT 0,
            lip_deviation_pct REAL DEFAULT 0,
            is_breakout INTEGER DEFAULT 0,
            is_volume_breakout INTEGER DEFAULT 0,
            breakout_price REAL DEFAULT 0,
            current_close REAL DEFAULT 0,
            volume_dry_score INTEGER DEFAULT 0,
            price_stable_score INTEGER DEFAULT 0,
            pattern_score_20 INTEGER DEFAULT 0,
            verdict_key TEXT,
            risk_percent REAL DEFAULT 0,
            rr1 REAL DEFAULT 0,
            entry_zone_low REAL DEFAULT 0,
            entry_zone_high REAL DEFAULT 0,
            stop_loss REAL DEFAULT 0,
            target_1 REAL DEFAULT 0,
            target_2 REAL DEFAULT 0,
            baseline_passed INTEGER DEFAULT 1,
            experiment_passed INTEGER DEFAULT 1,
            experiment_filter_reason TEXT,
            evaluation_snapshot TEXT,
            UNIQUE(task_id, code, evaluation_date)
        );

        CREATE TABLE IF NOT EXISTS strategy1_backtest_opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT,
            first_detected_date TEXT NOT NULL,
            last_detected_date TEXT,
            pattern_kind TEXT,
            first_score INTEGER DEFAULT 0,
            max_score INTEGER DEFAULT 0,
            signal_count INTEGER DEFAULT 0,
            entry_date TEXT,
            entry_price REAL DEFAULT 0,
            stop_loss REAL DEFAULT 0,
            exit_date TEXT,
            exit_price REAL DEFAULT 0,
            exit_reason TEXT,
            realized_return REAL,
            mark_to_market_end_return REAL,
            holding_days INTEGER DEFAULT 0,
            available_forward_days INTEGER DEFAULT 0,
            horizon_3 TEXT,
            horizon_5 TEXT,
            horizon_10 TEXT,
            horizon_20 TEXT,
            market_context_json TEXT,
            evaluation_snapshot TEXT,
            UNIQUE(task_id, code, first_detected_date)
        );

        CREATE TABLE IF NOT EXISTS strategy1_backtest_insufficient_stocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT,
            reason_code TEXT,
            available_days INTEGER DEFAULT 0,
            required_days INTEGER DEFAULT 0,
            earliest_date TEXT,
            latest_date TEXT,
            detail TEXT
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s1_bt_task_status ON strategy1_backtest_tasks(status, started_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s1_bt_signal_task ON strategy1_backtest_signals(task_id, code, evaluation_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s1_bt_opp_task ON strategy1_backtest_opportunities(task_id, first_detected_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_s1_bt_stock_task ON strategy1_backtest_task_stocks(task_id, status)")
    _ensure_column(conn, "strategy1_backtest_opportunities", "volume_dry_score", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy1_backtest_opportunities", "price_stable_score", "INTEGER DEFAULT 0")
    _ensure_column(conn, "strategy1_backtest_opportunities", "verdict_key", "TEXT")
    _ensure_column(conn, "strategy1_backtest_opportunities", "quality_tags", "TEXT")
    _ensure_column(conn, "strategy1_backtest_opportunities", "quality_layer", "TEXT")
    _ensure_column(conn, "strategy1_backtest_opportunities", "short_term_exit_note", "TEXT")


def create_strategy1_backtest_task(task_id: str, payload: dict, config_snapshot: str):
    conn = get_conn()
    experiment = payload.get("experiment_snapshot")
    if experiment is None:
        experiment = payload.get("experiment")
    experiment_json = (
        experiment if isinstance(experiment, str)
        else json.dumps(experiment, ensure_ascii=False) if experiment is not None else None
    )
    credibility_status = "EXPERIMENTAL" if _strategy1_experiment_enabled(experiment) else "INCOMPLETE"
    execution_model = "NEXT_OPEN"
    if isinstance(experiment, dict):
        execution_model = experiment.get("execution_model") or experiment.get("executionModel") or execution_model

    conn.execute(
        """INSERT INTO strategy1_backtest_tasks
           (id, status, credibility_status, requested_start_date, requested_end_date,
            scope_type, requested_codes, max_stocks, config_snapshot,
            experiment_snapshot, baseline_task_id, execution_model,
            data_revision_version, started_at)
           VALUES (?, 'running', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            task_id,
            credibility_status,
            payload.get("startDate", ""),
            payload.get("endDate", ""),
            "market" if not payload.get("codes") else "single",
            ",".join(payload.get("codes") or []),
            payload.get("maxStocks"),
            config_snapshot,
            experiment_json,
            payload.get("baselineTaskId"),
            execution_model,
            STRATEGY1_DATA_REVISION_VERSION,
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    conn.commit()


def mark_running_strategy1_backtests_interrupted() -> list[str]:
    """Mark Strategy1 backtests left running by a previous process interrupted."""
    conn = get_conn()
    task_ids = [
        row[0] for row in conn.execute(
            "SELECT id FROM strategy1_backtest_tasks WHERE LOWER(status)='running'"
        ).fetchall()
    ]
    if not task_ids:
        return []
    try:
        conn.execute("BEGIN IMMEDIATE")
        for task_id in task_ids:
            conn.execute(
                "UPDATE strategy1_backtest_tasks "
                "SET status='INTERRUPTED', credibility_status='INCOMPLETE', "
                "error='Interrupted by server restart' WHERE id=?",
                (task_id,),
            )
            conn.execute(
                "UPDATE strategy1_backtest_task_stocks SET status='PENDING' "
                "WHERE task_id=? AND status='RUNNING'",
                (task_id,),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return task_ids


def update_strategy1_backtest_task(task_id: str, **kwargs):
    if not kwargs:
        return
    conn = get_conn()
    sets = ", ".join(f"{key}=?" for key in kwargs)
    conn.execute(f"UPDATE strategy1_backtest_tasks SET {sets} WHERE id=?", list(kwargs.values()) + [task_id])
    conn.commit()


def get_strategy1_backtest_task(task_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM strategy1_backtest_tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        return None
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy1_backtest_tasks)")]
    return dict(zip(cols, row))


def get_strategy1_backtest_tasks(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
) -> tuple[list[dict], int]:
    conn = get_conn()
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    where = ""
    params = []
    if status:
        where = " WHERE LOWER(status)=LOWER(?)"
        params.append(status)
    total = conn.execute("SELECT COUNT(*) FROM strategy1_backtest_tasks" + where, params).fetchone()[0]
    rows = conn.execute(
        "SELECT * FROM strategy1_backtest_tasks" + where
        + " ORDER BY started_at DESC LIMIT ? OFFSET ?",
        params + [page_size, (page - 1) * page_size],
    ).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy1_backtest_tasks)")]
    return [dict(zip(cols, row)) for row in rows], total


def save_strategy1_backtest_signal(task_id: str, signal):
    conn = get_conn()
    snapshot_json = json.dumps(getattr(signal, "evaluation_snapshot", None) or {}, ensure_ascii=False)
    conn.execute(
        """INSERT INTO strategy1_backtest_signals
           (task_id, code, name, evaluation_date, evaluation_index, pattern_kind,
            score, cup_depth_pct, cup_duration, handle_depth_pct, handle_duration,
            lip_deviation_pct, is_breakout, is_volume_breakout, breakout_price,
            current_close, volume_dry_score, price_stable_score, pattern_score_20,
            verdict_key, risk_percent, rr1, entry_zone_low, entry_zone_high,
            stop_loss, target_1, target_2, baseline_passed, experiment_passed,
            experiment_filter_reason, evaluation_snapshot)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(task_id, code, evaluation_date) DO UPDATE SET
            score=excluded.score,
            experiment_passed=excluded.experiment_passed,
            experiment_filter_reason=excluded.experiment_filter_reason,
            evaluation_snapshot=excluded.evaluation_snapshot""",
        (
            task_id,
            signal.code,
            signal.name,
            signal.evaluation_date,
            signal.evaluation_index,
            signal.pattern_kind,
            signal.score,
            signal.cup_depth_pct,
            signal.cup_duration,
            signal.handle_depth_pct,
            signal.handle_duration,
            signal.lip_deviation_pct,
            1 if signal.is_breakout else 0,
            1 if signal.is_volume_breakout else 0,
            signal.breakout_price,
            signal.current_close,
            signal.volume_dry_score,
            signal.price_stable_score,
            signal.pattern_score_20,
            signal.verdict_key,
            signal.risk_percent,
            signal.rr1,
            signal.entry_zone_low,
            signal.entry_zone_high,
            signal.stop_loss,
            signal.target_1,
            signal.target_2,
            1 if signal.baseline_passed else 0,
            1 if signal.experiment_passed else 0,
            signal.experiment_filter_reason,
            snapshot_json,
        ),
    )
    conn.commit()


def replace_strategy1_stock_backtest_result(task_id: str, code: str, name: str, result: dict):
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM strategy1_backtest_opportunities WHERE task_id=? AND code=?", (task_id, code))
        conn.execute("DELETE FROM strategy1_backtest_signals WHERE task_id=? AND code=?", (task_id, code))

        for signal in result.get("signals") or []:
            _insert_strategy1_signal(conn, task_id, signal)
        for opportunity in result.get("opportunities") or []:
            _insert_strategy1_opportunity(conn, task_id, opportunity)

        stock_values = {
            "task_id": task_id,
            "code": code,
            "name": name,
            "status": result.get("status", "COMPLETED"),
            "available_days": result.get("available_days", 0),
            "required_days": result.get("required_days", 0),
            "earliest_date": result.get("earliest_date", ""),
            "latest_date": result.get("latest_date", ""),
            "actual_start_date": result.get("actual_start_date", result.get("actual_eval_start_date", "")),
            "actual_end_date": result.get("actual_end_date", result.get("actual_eval_end_date", "")),
            "raw_signals_count": result.get("raw_signals_count", 0),
            "opportunities_count": result.get("opportunities_count", 0),
            "evaluation_days": result.get("evaluation_days", result.get("eval_days", 0)),
            "filtered_days": result.get("filtered_days", 0),
            "error_code": result.get("error_code", ""),
            "error_detail": result.get("error_detail", ""),
        }
        columns = list(stock_values)
        placeholders = ", ".join("?" for _ in columns)
        updates = ", ".join(f"{column}=excluded.{column}" for column in columns if column not in {"task_id", "code"})
        conn.execute(
            f"""INSERT INTO strategy1_backtest_task_stocks ({', '.join(columns)})
                VALUES ({placeholders})
                ON CONFLICT(task_id, code) DO UPDATE SET {updates}""",
            [stock_values[column] for column in columns],
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def get_strategy1_backtest_opportunities(
    task_id: str,
    code: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> list[dict]:
    conn = get_conn()
    params = [task_id]
    where = "WHERE task_id=?"
    if code:
        where += " AND code=?"
        params.append(code)
    rows = conn.execute(
        "SELECT * FROM strategy1_backtest_opportunities "
        + where
        + " ORDER BY first_detected_date LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy1_backtest_opportunities)")]
    result = [dict(zip(cols, row)) for row in rows]
    for item in result:
        raw_tags = item.get("quality_tags")
        if isinstance(raw_tags, str) and raw_tags:
            try:
                parsed = json.loads(raw_tags)
                item["quality_tags"] = parsed if isinstance(parsed, list) else []
            except Exception:
                item["quality_tags"] = []
        elif not raw_tags:
            item["quality_tags"] = []
    return result


def get_strategy1_backtest_signals(
    task_id: str,
    code: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> list[dict]:
    conn = get_conn()
    params = [task_id]
    where = "WHERE task_id=?"
    if code:
        where += " AND code=?"
        params.append(code)
    rows = conn.execute(
        "SELECT * FROM strategy1_backtest_signals "
        + where
        + " ORDER BY evaluation_index LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy1_backtest_signals)")]
    return [dict(zip(cols, row)) for row in rows]


def get_strategy1_backtest_task_stocks(task_id: str, status: str | None = None) -> list[dict]:
    conn = get_conn()
    if status:
        rows = conn.execute(
            "SELECT * FROM strategy1_backtest_task_stocks WHERE task_id=? AND status=? ORDER BY code",
            (task_id, status),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM strategy1_backtest_task_stocks WHERE task_id=? ORDER BY code",
            (task_id,),
        ).fetchall()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy1_backtest_task_stocks)")]
    return [dict(zip(cols, row)) for row in rows]


def build_strategy1_backtest_summary(task_id: str) -> dict:
    import statistics as _st

    conn = get_conn()
    cols = [d[1] for d in conn.execute("PRAGMA table_info(strategy1_backtest_opportunities)")]
    rows = conn.execute(
        "SELECT * FROM strategy1_backtest_opportunities WHERE task_id=?",
        (task_id,),
    ).fetchall()
    opportunities = [dict(zip(cols, row)) for row in rows]
    entered = [row for row in opportunities if (row.get("entry_price") or 0) > 0]
    realized = [row.get("realized_return") or 0 for row in entered]
    target_count = sum(1 for row in opportunities if row.get("exit_reason") == "TARGET")
    stop_count = sum(1 for row in opportunities if row.get("exit_reason") == "STOP")
    raw_signals_count = conn.execute(
        "SELECT COUNT(*) FROM strategy1_backtest_signals WHERE task_id=?",
        (task_id,),
    ).fetchone()[0]

    def _group_by(field: str) -> dict:
        grouped = {}
        for row in opportunities:
            key = row.get(field) or "UNKNOWN"
            grouped.setdefault(key, []).append(row)
        return {
            key: {
                "count": len(items),
                "entered": sum(1 for item in items if (item.get("entry_price") or 0) > 0),
                "target": sum(1 for item in items if item.get("exit_reason") == "TARGET"),
                "stop": sum(1 for item in items if item.get("exit_reason") == "STOP"),
            }
            for key, items in sorted(grouped.items())
        }

    def _group_by_quality_tag() -> dict:
        grouped = {}
        for row in opportunities:
            raw_tags = row.get("quality_tags")
            tags = []
            if isinstance(raw_tags, str) and raw_tags:
                try:
                    parsed = json.loads(raw_tags)
                    tags = parsed if isinstance(parsed, list) else []
                except Exception:
                    tags = []
            elif isinstance(raw_tags, list):
                tags = raw_tags
            if not tags:
                tags = ["UNTAGGED"]
            for tag in tags:
                grouped.setdefault(tag, []).append(row)
        return {
            key: {
                "count": len(items),
                "entered": sum(1 for item in items if (item.get("entry_price") or 0) > 0),
                "target": sum(1 for item in items if item.get("exit_reason") == "TARGET"),
                "stop": sum(1 for item in items if item.get("exit_reason") == "STOP"),
            }
            for key, items in sorted(grouped.items())
        }

    return {
        "total_opportunities": len(opportunities),
        "raw_signals_count": raw_signals_count,
        "entered_count": len(entered),
        "target_count": target_count,
        "stop_count": stop_count,
        "target_rate": round(target_count / len(entered), 6) if entered else 0.0,
        "stop_rate": round(stop_count / len(entered), 6) if entered else 0.0,
        "average_realized_return": round(_st.mean(realized), 6) if realized else 0.0,
        "median_realized_return": round(_st.median(realized), 6) if realized else 0.0,
        "by_pattern_kind": _group_by("pattern_kind"),
        "by_quality_tag": _group_by_quality_tag(),
    }


def validate_strategy1_backtest_integrity(task_id: str) -> tuple[bool, list[str]]:
    """Validate whether a Strategy1 backtest task can be trusted as baseline."""
    conn = get_conn()
    errors: list[str] = []
    task = get_strategy1_backtest_task(task_id)
    if not task:
        return False, ["task_not_found"]

    if str(task.get("status", "")).lower() != "completed":
        errors.append(f"task status is {task.get('status')}, expected completed")
    if not task.get("data_revision_id"):
        errors.append("missing data_revision_id")
    if task.get("data_revision_version") != STRATEGY1_DATA_REVISION_VERSION:
        errors.append(f"invalid data_revision_version: {task.get('data_revision_version')}")
    if not task.get("strategy_engine_version"):
        errors.append("missing strategy_engine_version")
    if not task.get("backtest_engine_version"):
        errors.append("missing backtest_engine_version")

    total = int(task.get("total_stocks") or 0)
    processed = int(task.get("processed_stocks") or 0)
    stocks_count = conn.execute(
        "SELECT COUNT(*) FROM strategy1_backtest_task_stocks WHERE task_id=?",
        (task_id,),
    ).fetchone()[0]
    if stocks_count != total:
        errors.append(f"task_stocks count mismatch: {stocks_count} != {total}")
    if processed != total:
        errors.append(f"processed {processed} != total {total}")

    pending = conn.execute(
        "SELECT COUNT(*) FROM strategy1_backtest_task_stocks "
        "WHERE task_id=? AND status IN ('PENDING','RUNNING')",
        (task_id,),
    ).fetchone()[0]
    if pending:
        errors.append(f"{pending} stocks still PENDING/RUNNING")

    signal_count = conn.execute(
        "SELECT COUNT(*) FROM strategy1_backtest_signals WHERE task_id=?",
        (task_id,),
    ).fetchone()[0]
    stock_signal_count = conn.execute(
        "SELECT COALESCE(SUM(raw_signals_count),0) FROM strategy1_backtest_task_stocks WHERE task_id=?",
        (task_id,),
    ).fetchone()[0]
    if signal_count != stock_signal_count:
        errors.append(f"signal delta: {signal_count} vs {stock_signal_count}")

    opp_count = conn.execute(
        "SELECT COUNT(*) FROM strategy1_backtest_opportunities WHERE task_id=?",
        (task_id,),
    ).fetchone()[0]
    stock_opp_count = conn.execute(
        "SELECT COALESCE(SUM(opportunities_count),0) FROM strategy1_backtest_task_stocks WHERE task_id=?",
        (task_id,),
    ).fetchone()[0]
    if opp_count != stock_opp_count:
        errors.append(f"opportunity delta: {opp_count} vs {stock_opp_count}")

    if int(task.get("failed_stocks_count") or 0) > 0:
        errors.append(f"failed_stocks_count={task.get('failed_stocks_count')} > 0")
    if not task.get("observation_data_end_date"):
        errors.append("missing observation_data_end_date")
    if not task.get("summary_json"):
        errors.append("missing summary_json")
    else:
        try:
            summary = json.loads(task["summary_json"])
            for key in ["total_opportunities", "raw_signals_count", "entered_count"]:
                if key not in summary:
                    errors.append(f"missing summary key {key}")
        except Exception:
            errors.append("invalid summary_json")

    return len(errors) == 0, errors


def compare_strategy1_backtest_tasks(experiment_task_id: str, baseline_task_id: str) -> dict:
    baseline = get_strategy1_backtest_task(baseline_task_id)
    experiment = get_strategy1_backtest_task(experiment_task_id)
    if not baseline or not experiment:
        return {
            "comparable": False,
            "baselineTaskId": baseline_task_id,
            "experimentTaskId": experiment_task_id,
            "reasons": ["TASK_NOT_FOUND"],
        }

    checks = [
        ("requested_start_date", "DATE_RANGE_MISMATCH"),
        ("requested_end_date", "DATE_RANGE_MISMATCH"),
        ("requested_codes", "STOCK_SCOPE_MISMATCH"),
        ("max_stocks", "STOCK_SCOPE_MISMATCH"),
        ("execution_model", "EXECUTION_MODEL_MISMATCH"),
        ("strategy_engine_version", "STRATEGY_VERSION_MISMATCH"),
        ("data_revision_version", "DATA_REVISION_MISMATCH"),
        ("data_revision_id", "DATA_REVISION_MISMATCH"),
    ]
    reasons = []
    for field, reason in checks:
        if (baseline.get(field) or "") != (experiment.get(field) or "") and reason not in reasons:
            reasons.append(reason)
    if baseline.get("credibility_status") != "TRUSTED_BASELINE":
        reasons.append("BASELINE_NOT_TRUSTED")
    if experiment.get("credibility_status") != "EXPERIMENTAL":
        reasons.append("EXPERIMENT_NOT_MARKED")

    baseline_summary = _strategy1_summary_for_comparison(baseline_task_id, baseline)
    experiment_summary = _strategy1_summary_for_comparison(experiment_task_id, experiment)
    delta = {
        key: round((experiment_summary.get(key) or 0) - (baseline_summary.get(key) or 0), 6)
        for key in {"opportunities", "entered", "target", "stop", "targetRate", "stopRate", "averageRealizedReturn"}
    }
    return {
        "comparable": not reasons,
        "baselineTaskId": baseline_task_id,
        "experimentTaskId": experiment_task_id,
        "reasons": reasons,
        "baseline": baseline_summary,
        "experiment": experiment_summary,
        "delta": delta,
    }


def _insert_strategy1_signal(conn: sqlite3.Connection, task_id: str, signal):
    snapshot_json = json.dumps(getattr(signal, "evaluation_snapshot", None) or {}, ensure_ascii=False)
    conn.execute(
        """INSERT INTO strategy1_backtest_signals
           (task_id, code, name, evaluation_date, evaluation_index, pattern_kind,
            score, current_close, volume_dry_score, price_stable_score,
            pattern_score_20, verdict_key, risk_percent, rr1, stop_loss,
            baseline_passed, experiment_passed, experiment_filter_reason,
            evaluation_snapshot)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            task_id,
            signal.code,
            signal.name,
            signal.evaluation_date,
            signal.evaluation_index,
            signal.pattern_kind,
            signal.score,
            signal.current_close,
            signal.volume_dry_score,
            signal.price_stable_score,
            signal.pattern_score_20,
            signal.verdict_key,
            signal.risk_percent,
            signal.rr1,
            signal.stop_loss,
            1 if signal.baseline_passed else 0,
            1 if signal.experiment_passed else 0,
            signal.experiment_filter_reason,
            snapshot_json,
        ),
    )


def _insert_strategy1_opportunity(conn: sqlite3.Connection, task_id: str, opportunity):
    horizons = getattr(opportunity, "horizons", {}) or {}

    def _horizon_json(days: str) -> str:
        hp = horizons.get(days) or horizons.get(int(days))
        return json.dumps(hp.to_dict() if hasattr(hp, "to_dict") else {}, ensure_ascii=False)

    conn.execute(
        """INSERT INTO strategy1_backtest_opportunities
           (task_id, code, name, first_detected_date, last_detected_date,
            pattern_kind, first_score, max_score, signal_count, entry_date,
            entry_price, stop_loss, exit_date, exit_price, exit_reason,
            realized_return, mark_to_market_end_return, holding_days,
            available_forward_days, horizon_3, horizon_5, horizon_10,
            horizon_20, market_context_json, evaluation_snapshot,
            volume_dry_score, price_stable_score, verdict_key, quality_tags,
            quality_layer, short_term_exit_note)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            task_id,
            opportunity.code,
            opportunity.name,
            opportunity.first_detected_date,
            opportunity.last_detected_date,
            opportunity.pattern_kind,
            opportunity.first_score,
            opportunity.max_score,
            opportunity.signal_count,
            opportunity.entry_date,
            opportunity.entry_price,
            opportunity.stop_loss,
            opportunity.exit_date,
            opportunity.exit_price,
            opportunity.exit_reason,
            opportunity.realized_return,
            opportunity.mark_to_market_end_return,
            opportunity.holding_days,
            opportunity.available_forward_days,
            _horizon_json("3"),
            _horizon_json("5"),
            _horizon_json("10"),
            _horizon_json("20"),
            json.dumps(opportunity.market_context or {}, ensure_ascii=False),
            json.dumps(opportunity.evaluation_snapshot or {}, ensure_ascii=False),
            getattr(opportunity, "volume_dry_score", 0),
            getattr(opportunity, "price_stable_score", 0),
            getattr(opportunity, "verdict_key", ""),
            json.dumps(getattr(opportunity, "quality_tags", []) or [], ensure_ascii=False),
            getattr(opportunity, "quality_layer", "normal"),
            getattr(opportunity, "short_term_exit_note", ""),
        ),
    )


def _strategy1_summary_for_comparison(task_id: str, task: dict) -> dict:
    raw = task.get("summary_json")
    if raw:
        try:
            summary = json.loads(raw)
            return {
                "opportunities": summary.get("total_opportunities", summary.get("opportunities", 0)),
                "entered": summary.get("entered_count", summary.get("entered", 0)),
                "target": summary.get("target_count", summary.get("target", 0)),
                "stop": summary.get("stop_count", summary.get("stop", 0)),
                "targetRate": summary.get("target_rate", summary.get("targetRate", 0)),
                "stopRate": summary.get("stop_rate", summary.get("stopRate", 0)),
                "averageRealizedReturn": summary.get(
                    "average_realized_return",
                    summary.get("averageRealizedReturn", 0),
                ),
            }
        except Exception:
            pass
    summary = build_strategy1_backtest_summary(task_id)
    return {
        "opportunities": summary["total_opportunities"],
        "entered": summary["entered_count"],
        "target": summary["target_count"],
        "stop": summary["stop_count"],
        "targetRate": summary["target_rate"],
        "stopRate": summary["stop_rate"],
        "averageRealizedReturn": summary["average_realized_return"],
    }


def _strategy1_experiment_enabled(experiment) -> bool:
    if isinstance(experiment, str):
        try:
            experiment = json.loads(experiment)
        except Exception:
            return False
    return bool(isinstance(experiment, dict) and experiment.get("enabled"))

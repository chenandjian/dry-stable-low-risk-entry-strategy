# Scan Start and Results Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make scan starts use fresh market data by default, track every stock's scan outcome, prevent duplicate candidates, and support retrying failed stocks while allowing only one global scan process at a time.

**Architecture:** Add durable per-task stock status tracking in SQLite, move task ownership to `server.py`, and refactor `scanner/engine.py` so data fetching is fresh-first with explicit retry policies. Expose task-stock and retry APIs, then enhance the Vue scan console/task center to show real totals, failures, and retry controls.

**Tech Stack:** Python 3.10+, SQLite, FastAPI, pytest, Vue 3, Vite.

---

## Scope Check

The approved spec spans database, backend engine, API, and frontend UI, but all changes serve one coherent workflow: reliable scan task execution and recovery. Keep the implementation in one plan, split into small commits that each leave tests passing.

## File Structure

Modify existing files unless a focused test or component needs to be created.

- Modify `scanner/db.py`: schema migration helpers, `task_stocks` CRUD, candidate upsert/delete duplicate helpers, scan task stats helpers.
- Modify `scanner/stock_pool.py`: expose force-refresh stock-pool result metadata for scan starts.
- Modify `scanner/engine.py`: accept server-owned `task_id` and stock list, implement fresh-first fetch with retry metadata, record per-stock statuses, deduplicate candidates, support failed-only retry mode.
- Modify `server.py`: global scan mutex, start-scan preparation, retry-failed endpoint, task-stocks endpoint, enhanced status payload.
- Modify `scheduler/scheduler.py`: use shared scan-start guard or refuse when another scan is running.
- Modify `web/src/composables/useApi.js`: add task-stock and retry-failed API clients.
- Modify `web/src/components/ScanEngine.vue`: display processed/success/skipped/failed/candidate counts and disable controls correctly.
- Modify `web/src/pages/ScannerConsole.vue`: real totals, failure summary, retry button, frontend candidate de-duplication.
- Modify `web/src/pages/TaskCenter.vue`: show failed count/source and link to task detail/failure filtered view.
- Create `tests/test_scan_task_tracking.py`: database task-stock and candidate de-duplication tests.
- Create `tests/test_engine_fresh_fetch.py`: fresh-first data fetch and retry-policy tests.
- Create `tests/test_server_scan_api.py`: global mutex and task-stock API tests.

Do not restructure strategy algorithm files (`pattern_detector`, `scorer`, `analyzer/*`) unless a test reveals a direct integration bug.

---

## Task 1: Database schema and task-stock persistence

**Files:**
- Modify: `scanner/db.py`
- Create: `tests/test_scan_task_tracking.py`

- [ ] **Step 1: Write failing tests for schema, task-stock CRUD, stats, and candidate de-duplication**

Create `tests/test_scan_task_tracking.py` with:

```python
from scanner import db
from scanner.pattern_detector import CupHandleResult


def test_init_db_creates_task_stocks_and_scan_task_columns(tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))

    with db.get_conn() as conn:
        task_columns = {r[1] for r in conn.execute("PRAGMA table_info(scan_tasks)").fetchall()}
        stock_columns = {r[1] for r in conn.execute("PRAGMA table_info(task_stocks)").fetchall()}
        indexes = {r[1] for r in conn.execute("PRAGMA index_list(candidates)").fetchall()}

    assert "success_count" in task_columns
    assert "failed_count" in task_columns
    assert "stock_pool_source" in task_columns
    assert "retry_mode" in task_columns
    assert "latest_trade_date" in task_columns
    assert "status_reason" in stock_columns
    assert "primary_attempts" in stock_columns
    assert "fallback_error" in stock_columns
    assert "quote_status" in stock_columns
    assert "idx_candidates_task_code" in indexes


def test_save_and_update_task_stocks(tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    db.create_scan_task("task-1", "2026-06-04 09:30:00", total_stocks=0)
    stocks = [
        {"code": "600000", "name": "浦发银行", "market": "上证主板"},
        {"code": "000001", "name": "平安银行", "market": "深证主板"},
    ]

    db.save_task_stocks("task-1", stocks)
    db.update_task_stock(
        "task-1",
        "600000",
        status="failed",
        status_reason="数据源全部失败，未使用旧缓存扫描",
        primary_source="sina",
        fallback_source="tencent",
        primary_attempts=2,
        fallback_attempts=2,
        primary_error="timeout",
        fallback_error="empty response",
        kline_latest_date=None,
        quote_status="not_requested",
    )

    all_rows = db.get_task_stocks("task-1")
    failed_rows = db.get_task_stocks("task-1", status="failed")
    stats = db.summarize_task_stocks("task-1")

    assert [r["code"] for r in all_rows] == ["600000", "000001"]
    assert len(failed_rows) == 1
    assert failed_rows[0]["status_reason"] == "数据源全部失败，未使用旧缓存扫描"
    assert failed_rows[0]["primary_attempts"] == 2
    assert stats["total_stocks"] == 2
    assert stats["failed"] == 1
    assert stats["pending"] == 1


def test_update_scan_task_from_task_stock_summary(tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    db.create_scan_task("task-1", "2026-06-04 09:30:00", total_stocks=0)
    db.save_task_stocks("task-1", [
        {"code": "600000", "name": "浦发银行", "market": "上证主板"},
        {"code": "000001", "name": "平安银行", "market": "深证主板"},
        {"code": "300001", "name": "特锐德", "market": "创业板"},
    ])
    db.update_task_stock("task-1", "600000", status="candidate", kline_latest_date="2026-06-04")
    db.update_task_stock("task-1", "000001", status="skipped", status_reason="流动性过滤未通过")
    db.update_task_stock("task-1", "300001", status="failed", status_reason="扫描异常")

    summary = db.refresh_scan_task_counts("task-1")
    tasks = db.get_scan_tasks()
    saved = tasks[0]

    assert summary["processed"] == 3
    assert summary["success_count"] == 1
    assert summary["skipped"] == 1
    assert summary["failed_count"] == 1
    assert summary["candidates_count"] == 1
    assert saved["scanned"] == 3
    assert saved["skipped"] == 1
    assert saved["failed"] == 1
    assert saved["candidates"] == 1


def test_candidates_are_unique_per_task_and_code(tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    db.create_scan_task("task-1", "2026-06-04 09:30:00", total_stocks=1)
    stock = {"code": "600000", "name": "浦发银行", "latest_close": 11.0, "latest_turnover": 100_000_000}
    first = CupHandleResult(found=True, code="600000", name="浦发银行", score=70)
    second = CupHandleResult(found=True, code="600000", name="浦发银行", score=85)

    db.save_candidates("task-1", [(stock, first)])
    db.save_candidates("task-1", [(stock, second)])
    db.upsert_candidate("task-1", {"code": "600000", "name": "浦发银行", "score": 90})

    rows = db.get_candidates("task-1")
    assert len(rows) == 1
    assert rows[0]["code"] == "600000"
    assert rows[0]["score"] == 90
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_scan_task_tracking.py -v
```

Expected: FAIL because `task_stocks` table/schema helpers and new DB functions do not exist yet, or because `candidates` duplicates are not constrained.

- [ ] **Step 3: Implement schema migration helpers in `scanner/db.py`**

Add scan task column and task stock schema helpers below `_ensure_candidate_columns()`:

```python
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
    }
    for name, typ in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE scan_tasks ADD COLUMN {name} {typ}")


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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_stocks_task_status ON task_stocks(task_id, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_stocks_task_idx ON task_stocks(task_id, idx)")
```

In `init_db()`, after `_ensure_candidate_columns(conn)`, call:

```python
        _ensure_scan_task_columns(conn)
        _ensure_task_stocks_table(conn)
        _dedupe_candidates_before_unique_index(conn)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_candidates_task_code ON candidates(task_id, code)")
```

Add the dedupe helper before creating the unique index:

```python
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
```

- [ ] **Step 4: Implement task-stock CRUD and stats helpers in `scanner/db.py`**

Replace existing `save_task_stocks()` and `get_pending_stocks()` with versions that use the real schema, then add the new helpers:

```python
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
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    updates["updated_at"] = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
    """Get pending stocks for a resumed task."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT code, name, market FROM task_stocks
           WHERE task_id=? AND idx>=? AND status IN ('pending', 'fetching')
           ORDER BY idx""",
        (task_id, from_idx),
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
    return {
        **s,
        "processed": processed,
        "success_count": s["scanned"] + s["candidate"],
        "failed_count": s["failed"],
        "candidates_count": candidates_count,
        "latest_trade_date": latest_trade_date,
    }
```

- [ ] **Step 5: Update scan task functions and candidate upserts in `scanner/db.py`**

Change `create_scan_task()` signature and SQL:

```python
def create_scan_task(task_id: str, started_at: str, total_stocks: int = 0,
                     stock_pool_source: str = None, stock_pool_error: str = None,
                     retry_mode: str = "full") -> int:
    """Insert a new scan task. Returns row id."""
    conn = get_conn()
    conn.execute(
        """INSERT INTO scan_tasks
           (id, started_at, status, total_stocks, stock_pool_source,
            stock_pool_error, retry_mode, data_fresh_policy)
           VALUES (?, ?, 'running', ?, ?, ?, ?, 'force_refresh')""",
        (task_id, started_at, total_stocks, stock_pool_source, stock_pool_error, retry_mode),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
```

Update `get_scan_tasks()` returned dict to include failed/source fields:

```python
        {"id": r[0], "date": r[1] or "", "finished_at": r[2],
         "running": r[3] == 'running', "status": r[3], "scope": f"全市场 · {r[4]}只",
         "total_stocks": r[4], "scanned": r[5], "total": r[4],
         "skipped": r[6], "candidates": r[7], "elapsed_seconds": r[8],
         "duration": f"{r[8]:.0f}s" if r[8] is not None else None,
         "failed": r[9], "stock_pool_source": r[10], "latest_trade_date": r[11]}
```

Adjust the query columns accordingly:

```python
        """SELECT id, started_at, finished_at, status, total_stocks, scanned, skipped,
                  candidates_count, elapsed_seconds, failed_count, stock_pool_source,
                  latest_trade_date
           FROM scan_tasks ORDER BY started_at DESC"""
```

Change `save_candidates()` and `upsert_candidate()` insert SQL to use SQLite conflict update:

```python
    update_assignments = ", ".join(f"{c}=excluded.{c}" for c in columns if c not in ("task_id", "code"))
    conn.executemany(
        f"""INSERT INTO candidates ({', '.join(columns)}) VALUES ({value_marks})
            ON CONFLICT(task_id, code) DO UPDATE SET {update_assignments}""",
        rows,
    )
```

For `upsert_candidate()`, use the same `ON CONFLICT(task_id, code) DO UPDATE` SQL with `conn.execute(...)`.

- [ ] **Step 6: Run database tests**

Run:

```bash
python -m pytest tests/test_scan_task_tracking.py -v
```

Expected: PASS.

- [ ] **Step 7: Run existing DB-related regression test**

Run:

```bash
python -m pytest tests/test_db_strategy_fields.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit database tracking changes**

Run:

```bash
git add scanner/db.py tests/test_scan_task_tracking.py
git commit -m "Add scan task stock tracking"
```

Expected: commit succeeds and includes only `scanner/db.py` plus `tests/test_scan_task_tracking.py`.

---

## Task 2: Stock-pool refresh result metadata

**Files:**
- Modify: `scanner/stock_pool.py`
- Test: `tests/test_scan_task_tracking.py`

- [ ] **Step 1: Add failing tests for force-refresh stock-pool metadata**

Append to `tests/test_scan_task_tracking.py`:

```python
def test_get_a_stock_pool_result_uses_akshare_when_available(monkeypatch, tmp_path):
    import types
    from scanner import stock_pool

    db.init_db(str(tmp_path / "cuphandle.db"))

    class FakeDataFrame:
        def iterrows(self):
            return iter([
                (0, {"code": "600000", "name": "浦发银行"}),
                (1, {"code": "000001", "name": "平安银行"}),
            ])

    fake_ak = types.SimpleNamespace(stock_info_a_code_name=lambda: FakeDataFrame())
    monkeypatch.setitem(__import__("sys").modules, "akshare", fake_ak)

    result = stock_pool.get_a_stock_pool_result({"market": {}})

    assert result["source"] == "akshare"
    assert result["error"] is None
    assert [s["code"] for s in result["stocks"]] == ["600000", "000001"]


def test_get_a_stock_pool_result_falls_back_to_cached_pool(monkeypatch, tmp_path):
    import types
    from scanner import stock_pool

    db.init_db(str(tmp_path / "cuphandle.db"))
    db.save_stock_pool([{"code": "600000", "name": "浦发银行", "market": "上证主板"}])

    def fail():
        raise RuntimeError("akshare down")

    fake_ak = types.SimpleNamespace(stock_info_a_code_name=fail)
    monkeypatch.setitem(__import__("sys").modules, "akshare", fake_ak)

    result = stock_pool.get_a_stock_pool_result({"market": {}})

    assert result["source"] == "cached"
    assert "akshare down" in result["error"]
    assert result["stocks"][0]["code"] == "600000"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_scan_task_tracking.py::test_get_a_stock_pool_result_uses_akshare_when_available tests/test_scan_task_tracking.py::test_get_a_stock_pool_result_falls_back_to_cached_pool -v
```

Expected: FAIL because `get_a_stock_pool_result()` does not exist.

- [ ] **Step 3: Implement result metadata in `scanner/stock_pool.py`**

Add this function above `get_a_stock_pool()` and update `get_a_stock_pool()` to delegate:

```python
def get_a_stock_pool_result(config: dict) -> dict:
    """Get A-share stock pool with source/error metadata for scan tasks."""
    error = None
    try:
        import akshare as ak
        df = ak.stock_info_a_code_name()
        stocks = []
        for _, row in df.iterrows():
            code = str(row["code"]).zfill(6)
            name = str(row["name"])
            stocks.append({"code": code, "name": name})
        logger.info(f"AKShare: got {len(stocks)} stocks")
        if stocks:
            save_stock_pool(stocks)
            return {"stocks": _filter_stocks(stocks, config), "source": "akshare", "error": None}
    except Exception as e:
        error = str(e)
        logger.warning(f"AKShare stock pool failed: {e}")

    cached = get_stock_pool()
    if cached:
        logger.info(f"Using cached stock pool: {len(cached)} stocks")
        return {"stocks": _filter_stocks(cached, config), "source": "cached", "error": error}

    logger.error("Cannot get stock pool from any source")
    return {"stocks": [], "source": "none", "error": error or "No stock pool available"}


def get_a_stock_pool(config: dict) -> list[dict]:
    """获取 A 股股票池，过滤 ST/新股/北交所。"""
    return get_a_stock_pool_result(config)["stocks"]
```

- [ ] **Step 4: Run stock-pool tests**

Run:

```bash
python -m pytest tests/test_scan_task_tracking.py::test_get_a_stock_pool_result_uses_akshare_when_available tests/test_scan_task_tracking.py::test_get_a_stock_pool_result_falls_back_to_cached_pool -v
```

Expected: PASS.

- [ ] **Step 5: Run stock-pool related regression tests**

Run:

```bash
python -m pytest tests/test_data_source.py tests/test_scan_task_tracking.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit stock-pool metadata changes**

Run:

```bash
git add scanner/stock_pool.py tests/test_scan_task_tracking.py
git commit -m "Track stock pool source for scans"
```

Expected: commit succeeds.

---

## Task 3: Fresh-first fetch with retry metadata

**Files:**
- Modify: `scanner/engine.py`
- Create: `tests/test_engine_fresh_fetch.py`

- [ ] **Step 1: Write failing fetch tests**

Create `tests/test_engine_fresh_fetch.py` with:

```python
from scanner import db
from scanner import engine


def _row(day, close=10.0):
    return {"date": day, "open": close, "high": close, "low": close, "close": close, "volume": 10_000_000, "turnover": close * 10_000_000}


def test_fetch_with_retry_ignores_fresh_cache_when_source_succeeds(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    db.save_ohlc("600000", [_row("2026-06-03", close=9.0)])
    calls = []

    def fake_sina(code):
        calls.append(code)
        return [_row("2026-06-04", close=10.0)]

    monkeypatch.setattr(engine, "fetch_sina_daily", fake_sina)
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code: None)
    result = engine._fetch_with_retry("600000", "sina", retry_attempts=2, fallback_attempts=2, sleep_fn=lambda _: None)

    assert calls == ["600000"]
    assert result.data[-1]["date"] == "2026-06-04"
    assert result.from_cache is False
    assert result.primary_attempts == 1
    assert result.fallback_attempts == 0
    assert db.get_ohlc("600000")[-1]["date"] == "2026-06-04"


def test_fetch_with_retry_uses_fallback_after_primary_failures(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    primary_calls = []
    fallback_calls = []

    def fake_sina(code):
        primary_calls.append(code)
        return None

    def fake_tencent(code):
        fallback_calls.append(code)
        return [_row("2026-06-04", close=10.0)]

    monkeypatch.setattr(engine, "fetch_sina_daily", fake_sina)
    monkeypatch.setattr(engine, "fetch_tencent_daily", fake_tencent)
    result = engine._fetch_with_retry("600000", "sina", retry_attempts=2, fallback_attempts=2, sleep_fn=lambda _: None)

    assert result.data[-1]["date"] == "2026-06-04"
    assert result.primary_attempts == 2
    assert result.fallback_attempts == 1
    assert result.primary_error == "empty response"
    assert result.fallback_error is None


def test_fetch_with_retry_does_not_return_cache_when_sources_fail(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    db.save_ohlc("600000", [_row("2026-06-03", close=9.0)])

    monkeypatch.setattr(engine, "fetch_sina_daily", lambda code: None)
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code: None)
    result = engine._fetch_with_retry("600000", "sina", retry_attempts=2, fallback_attempts=2, sleep_fn=lambda _: None)

    assert result.data is None
    assert result.primary_attempts == 2
    assert result.fallback_attempts == 2
    assert result.primary_error == "empty response"
    assert result.fallback_error == "empty response"
    assert result.from_cache is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_engine_fresh_fetch.py -v
```

Expected: FAIL because `_fetch_with_retry()` and its return object do not exist.

- [ ] **Step 3: Add fetch result dataclass and retry helper in `scanner/engine.py`**

At the top of `scanner/engine.py`, add:

```python
from dataclasses import dataclass
from typing import Callable
```

Below imports, add:

```python
@dataclass
class FetchResult:
    data: list[dict] | None
    primary_source: str
    fallback_source: str
    primary_attempts: int = 0
    fallback_attempts: int = 0
    primary_error: str | None = None
    fallback_error: str | None = None
    from_cache: bool = False
```

Replace `_fetch_with_fallback()` with fresh-first retry logic:

```python
def _fetch_with_retry(
    code: str,
    primary_ds: str,
    retry_attempts: int = 2,
    fallback_attempts: int = 2,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> FetchResult:
    """Fetch fresh K-line data first; cache is only used to merge history."""
    fallback_ds = "tencent" if primary_ds == "sina" else "sina"
    cached = db.get_ohlc(code)
    result = FetchResult(data=None, primary_source=primary_ds, fallback_source=fallback_ds)

    data, attempts, error = _try_fetch_source(code, primary_ds, retry_attempts, sleep_fn)
    result.primary_attempts = attempts
    result.primary_error = error
    if data:
        merged = _merge_data(cached or [], data)
        db.save_ohlc(code, merged)
        result.data = merged
        return result

    data, attempts, error = _try_fetch_source(code, fallback_ds, fallback_attempts, sleep_fn)
    result.fallback_attempts = attempts
    result.fallback_error = error
    if data:
        merged = _merge_data(cached or [], data)
        db.save_ohlc(code, merged)
        result.data = merged
        return result

    return result


def _try_fetch_source(code: str, ds_name: str, attempts: int, sleep_fn: Callable[[float], None]) -> tuple[list[dict] | None, int, str | None]:
    fetch_fn = fetch_sina_daily if ds_name == "sina" else fetch_tencent_daily
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            data = fetch_fn(code)
            if data:
                return data, attempt, None
            last_error = "empty response"
        except Exception as exc:
            last_error = str(exc)
        if attempt < attempts:
            sleep_fn(min(0.5 * attempt, 2.0))
    return None, attempts, last_error
```

Keep `_merge_data()` and remove `_is_cache_fresh()` if no longer used.

- [ ] **Step 4: Run fetch tests**

Run:

```bash
python -m pytest tests/test_engine_fresh_fetch.py -v
```

Expected: PASS.

- [ ] **Step 5: Run related engine regressions**

Run:

```bash
python -m pytest tests/test_pattern_detector.py tests/test_scorer.py tests/test_liquidity_filter.py tests/test_engine_fresh_fetch.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit fresh-fetch helper changes**

Run:

```bash
git add scanner/engine.py tests/test_engine_fresh_fetch.py
git commit -m "Fetch fresh scan data before cache"
```

Expected: commit succeeds.

---

## Task 4: Engine task ownership, stock status tracking, and failed-only retry

**Files:**
- Modify: `scanner/engine.py`
- Modify: `tests/test_engine_fresh_fetch.py`

- [ ] **Step 1: Add failing scan status tests with monkeypatched strategy functions**

Append to `tests/test_engine_fresh_fetch.py`:

```python
def test_scan_all_records_failed_stock_when_fetch_fails(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    db.create_scan_task("task-1", "2026-06-04 09:30:00", total_stocks=1)
    stocks = [{"code": "600000", "name": "浦发银行", "market": "上证主板"}]
    db.save_task_stocks("task-1", stocks)

    monkeypatch.setattr(engine, "fetch_market_index_daily", lambda: [])
    monkeypatch.setattr(engine, "_fetch_with_retry", lambda *args, **kwargs: engine.FetchResult(
        data=None,
        primary_source="sina",
        fallback_source="tencent",
        primary_attempts=2,
        fallback_attempts=2,
        primary_error="timeout",
        fallback_error="empty response",
    ))

    result = engine.scan_all({"liquidity": {"enabled": False}}, task_id="task-1", stocks=stocks, worker_count=1)
    rows = db.get_task_stocks("task-1", status="failed")

    assert result["stats"]["failed"] == 1
    assert rows[0]["code"] == "600000"
    assert rows[0]["status_reason"] == "数据源全部失败，未使用旧缓存扫描"
    assert rows[0]["primary_error"] == "timeout"


def test_scan_all_marks_skipped_for_insufficient_listing_days(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    db.create_scan_task("task-1", "2026-06-04 09:30:00", total_stocks=1)
    stocks = [{"code": "600000", "name": "浦发银行", "market": "上证主板"}]
    db.save_task_stocks("task-1", stocks)
    data = [_row("2026-06-04")]

    monkeypatch.setattr(engine, "fetch_market_index_daily", lambda: [])
    monkeypatch.setattr(engine, "_fetch_with_retry", lambda *args, **kwargs: engine.FetchResult(
        data=data,
        primary_source="sina",
        fallback_source="tencent",
        primary_attempts=1,
    ))

    result = engine.scan_all({"liquidity": {"enabled": False, "min_listing_days": 250}}, task_id="task-1", stocks=stocks, worker_count=1)
    rows = db.get_task_stocks("task-1", status="skipped")

    assert result["stats"]["skipped"] == 1
    assert rows[0]["status_reason"] == "上市天数不足"


def test_scan_all_deduplicates_candidates(monkeypatch, tmp_path):
    from scanner.pattern_detector import CupHandleResult

    db.init_db(str(tmp_path / "cuphandle.db"))
    db.create_scan_task("task-1", "2026-06-04 09:30:00", total_stocks=2)
    stocks = [
        {"code": "600000", "name": "浦发银行", "market": "上证主板"},
        {"code": "600000", "name": "浦发银行", "market": "上证主板"},
    ]
    db.save_task_stocks("task-1", stocks)
    data = [_row(f"2026-05-{str(i+1).zfill(2)}", close=20.0) for i in range(30)]

    monkeypatch.setattr(engine, "fetch_market_index_daily", lambda: [])
    monkeypatch.setattr(engine, "_fetch_with_retry", lambda *args, **kwargs: engine.FetchResult(
        data=data,
        primary_source="sina",
        fallback_source="tencent",
        primary_attempts=1,
    ))
    monkeypatch.setattr(engine, "passes_liquidity_filter", lambda data, config: True)
    monkeypatch.setattr(engine, "detect_cup_handle", lambda data, config: CupHandleResult(found=True, score=0))
    monkeypatch.setattr(engine, "score_cup_handle_advanced", lambda result, data, scoring_cfg=None: 80)
    monkeypatch.setattr(engine, "analyze_dry_stable", lambda result, data, market_data=None: {
        "decision": {"verdict": "可低吸", "summary": "测试"},
        "volume_dry": {"score": 8},
        "price_stable": {"score": 8},
        "pattern_score": {"score": 16, "type": "杯柄", "key_pattern_type": "cup_handle"},
        "risk_reward": {"risk_percent": 4.0, "rr1": 2.0, "position_advice": "30%"},
        "key_prices": {"entry_zone_low": 19, "entry_zone_high": 20, "pivot": 21, "stop_loss": 18, "target_1": 24, "target_2": 26},
        "market_environment": {"status": "一般", "position_advice": "轻仓"},
    })

    result = engine.scan_all({"liquidity": {"enabled": False}, "scoring": {"medium_threshold": 70}}, task_id="task-1", stocks=stocks, worker_count=1)
    candidates = db.get_candidates("task-1")

    assert result["stats"]["candidates_found"] == 1
    assert len(candidates) == 1
    assert candidates[0]["code"] == "600000"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_engine_fresh_fetch.py -v
```

Expected: FAIL because `scan_all()` does not accept `task_id`, `stocks`, or `worker_count`, and does not update `task_stocks`.

- [ ] **Step 3: Change `scan_all()` signature and task preparation**

Update `scan_all()` signature:

```python
def scan_all(
    config: dict,
    progress_callback=None,
    resume_task_id: str = None,
    task_id: str = None,
    stocks: list[dict] = None,
    retry_policy: str = "normal",
    worker_count: int = 2,
) -> dict:
```

At the beginning after `db.init_db(db_path)`, replace stock loading with:

```python
    from scanner.stock_pool import get_a_stock_pool

    if task_id is None:
        task_id = resume_task_id or time.strftime("%Y%m%d-%H%M%S")

    start_offset = 0
    if stocks is None and resume_task_id:
        info = db.get_interrupted_task()
        if info:
            start_offset = info.get("scanned", 0)
            stocks = db.get_pending_stocks(resume_task_id, from_idx=start_offset)

    if stocks is None:
        stocks = get_a_stock_pool(config)
        if not resume_task_id:
            db.save_task_stocks(task_id, stocks)
```

Set retry attempts:

```python
    if retry_policy == "failed_only":
        primary_attempts = 3
        fallback_attempts = 3
    else:
        primary_attempts = 2
        fallback_attempts = 2
```

Use `worker_count` when creating threads:

```python
    threads = [threading.Thread(target=worker, args=(f"t{i+1}",), daemon=True) for i in range(worker_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
```

- [ ] **Step 4: Add per-stock status updates in the worker**

Inside the worker, after `code = stock["code"]`, set fetching:

```python
                db.update_task_stock(
                    task_id,
                    code,
                    status="fetching",
                    primary_source=ds,
                    fallback_source="tencent" if ds == "sina" else "sina",
                    started_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                )
```

Replace `_fetch_with_fallback(code, ds, mgr)` with:

```python
                fetch_result = _fetch_with_retry(
                    code,
                    ds,
                    retry_attempts=primary_attempts,
                    fallback_attempts=fallback_attempts,
                )
                data = fetch_result.data
                if data is None:
                    db.update_task_stock(
                        task_id,
                        code,
                        status="failed",
                        status_reason="数据源全部失败，未使用旧缓存扫描",
                        primary_source=fetch_result.primary_source,
                        fallback_source=fetch_result.fallback_source,
                        primary_attempts=fetch_result.primary_attempts,
                        fallback_attempts=fetch_result.fallback_attempts,
                        primary_error=fetch_result.primary_error,
                        fallback_error=fetch_result.fallback_error,
                        finished_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                    )
                    with stats_lock:
                        skip_count[0] += 1
                    db.refresh_scan_task_counts(task_id)
                    continue
```

For insufficient listing days:

```python
                    db.update_task_stock(
                        task_id,
                        code,
                        status="skipped",
                        status_reason="上市天数不足",
                        kline_latest_date=data[-1].get("date"),
                        finished_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                    )
                    db.refresh_scan_task_counts(task_id)
```

For liquidity failure:

```python
                    db.update_task_stock(
                        task_id,
                        code,
                        status="skipped",
                        status_reason="流动性过滤未通过",
                        kline_latest_date=data[-1].get("date"),
                        finished_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                    )
                    db.refresh_scan_task_counts(task_id)
```

When not a candidate after normal scan:

```python
                    db.update_task_stock(
                        task_id,
                        code,
                        status="scanned",
                        kline_latest_date=data[-1].get("date"),
                        quote_status="not_requested",
                        finished_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                    )
```

When candidate:

```python
                            candidate_by_code[code] = (stock, result)
                        db.update_task_stock(
                            task_id,
                            code,
                            status="candidate",
                            kline_latest_date=data[-1].get("date"),
                            quote_status="not_requested",
                            finished_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                        )
```

In `except Exception as e`, update task stock:

```python
                db.update_task_stock(
                    task_id,
                    code,
                    status="failed",
                    status_reason="扫描异常",
                    error_detail=str(e),
                    finished_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                )
                db.refresh_scan_task_counts(task_id)
```

- [ ] **Step 5: Replace candidate list append with dictionary de-duplication**

Initialize:

```python
    candidate_by_code = {}
```

Replace `candidates.append((stock, result))` with:

```python
                            candidate_by_code[code] = (stock, result)
```

At the end, build sorted candidates:

```python
    candidates = list(candidate_by_code.values())
    candidates.sort(key=lambda x: x[1].score, reverse=True)
    summary = db.refresh_scan_task_counts(task_id)
```

Return stats from summary:

```python
            "total_stocks": summary["total_stocks"],
            "scanned": summary["processed"],
            "skipped": summary["skipped"],
            "failed": summary["failed"],
            "candidates_found": len(candidates),
            "latest_trade_date": summary.get("latest_trade_date"),
```

Return the server-owned `task_id`:

```python
        "task_id": task_id,
```

- [ ] **Step 6: Run engine tracking tests**

Run:

```bash
python -m pytest tests/test_engine_fresh_fetch.py -v
```

Expected: PASS.

- [ ] **Step 7: Run broader scanner tests**

Run:

```bash
python -m pytest tests/test_pattern_detector.py tests/test_scorer.py tests/test_liquidity_filter.py tests/test_engine_fresh_fetch.py tests/test_scan_task_tracking.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit engine task tracking changes**

Run:

```bash
git add scanner/engine.py tests/test_engine_fresh_fetch.py
git commit -m "Track per-stock scan outcomes"
```

Expected: commit succeeds.

---

## Task 5: Server APIs and global scan mutex

**Files:**
- Modify: `server.py`
- Modify: `scheduler/scheduler.py`
- Create: `tests/test_server_scan_api.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/test_server_scan_api.py` with:

```python
from fastapi.testclient import TestClient

import server
from scanner import db


def test_start_scan_rejects_when_db_task_running(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    db.create_scan_task("running-1", "2026-06-04 09:30:00", total_stocks=1)
    server._running["running"] = False
    server._running["task_id"] = None

    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": {"data": {"database_path": str(tmp_path / "cuphandle.db")}})

    client = TestClient(server.app)
    res = client.get("/api/scan/start")

    assert res.status_code == 409
    assert res.json()["error"] == "Scan already running"
    assert res.json()["running_task_id"] == "running-1"


def test_task_stocks_endpoint_filters_failed_rows(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    db.create_scan_task("task-1", "2026-06-04 09:30:00", total_stocks=2)
    db.save_task_stocks("task-1", [
        {"code": "600000", "name": "浦发银行", "market": "上证主板"},
        {"code": "000001", "name": "平安银行", "market": "深证主板"},
    ])
    db.update_task_stock("task-1", "600000", status="failed", status_reason="数据源全部失败")
    db.update_task_stock("task-1", "000001", status="scanned")

    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": {"data": {"database_path": str(tmp_path / "cuphandle.db")}})

    client = TestClient(server.app)
    res = client.get("/api/scan/tasks/task-1/stocks?status=failed")

    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 1
    assert body["stocks"][0]["code"] == "600000"
    assert body["stocks"][0]["status_reason"] == "数据源全部失败"


def test_retry_failed_returns_zero_when_no_failures(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    db.create_scan_task("task-1", "2026-06-04 09:30:00", total_stocks=1)
    db.save_task_stocks("task-1", [{"code": "600000", "name": "浦发银行", "market": "上证主板"}])
    db.update_task_stock("task-1", "600000", status="scanned")
    server._running["running"] = False
    server._running["task_id"] = None

    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": {"data": {"database_path": str(tmp_path / "cuphandle.db")}})

    client = TestClient(server.app)
    res = client.post("/api/scan/tasks/task-1/retry-failed")

    assert res.status_code == 200
    assert res.json()["retry_count"] == 0
    assert res.json()["status"] == "no_failed_stocks"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_server_scan_api.py -v
```

Expected: FAIL because new endpoints and mutex helper do not exist.

- [ ] **Step 3: Add scan mutex helpers in `server.py`**

Below `_running`, add:

```python
def _get_running_task_id() -> str | None:
    if _running.get("running") and _running.get("task_id"):
        return _running["task_id"]
    return db.get_running_task_id()


def _scan_conflict_response():
    running_id = _get_running_task_id()
    if running_id:
        return JSONResponse(
            {"error": "Scan already running", "running_task_id": running_id},
            status_code=409,
        )
    return None


def _set_running(task_id: str, mode: str):
    _running["running"] = True
    _running["task_id"] = task_id
    _running["mode"] = mode
    _running["stats"] = {}


def _clear_running():
    _running["running"] = False
```

- [ ] **Step 4: Update `/api/scan/start` to prepare task and stock list before launching thread**

In `start_scan()`, replace the initial running check and task setup with:

```python
    conflict = _scan_conflict_response()
    if conflict:
        return conflict

    import datetime
    from scanner.stock_pool import get_a_stock_pool_result

    config = load_config()
    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)

    pool_result = get_a_stock_pool_result(config)
    stocks = pool_result["stocks"]
    if not stocks:
        return JSONResponse({"error": "No stock pool available", "detail": pool_result.get("error")}, status_code=503)

    task_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    started_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.create_scan_task(
        task_id,
        started_at,
        total_stocks=len(stocks),
        stock_pool_source=pool_result["source"],
        stock_pool_error=pool_result.get("error"),
        retry_mode="full",
    )
    db.save_task_stocks(task_id, stocks)
    _set_running(task_id, "full")
    _running["started_at"] = started_at
```

Inside the background `run()` call `scan_all` with server-owned inputs:

```python
            result = scan_all(config, progress_callback=on_progress, task_id=task_id, stocks=stocks, retry_policy="normal")
```

Return:

```python
    return {"task_id": task_id, "status": "started", "total_stocks": len(stocks), "stock_pool_source": pool_result["source"]}
```

In `finally`, call `_clear_running()`.

- [ ] **Step 5: Enhance scan status and task-stock endpoints in `server.py`**

Add endpoint:

```python
@app.get("/api/scan/tasks/{task_id}/stocks")
async def get_task_stocks(task_id: str, status: str = None, page: int = 1, page_size: int = 100):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 500)
    offset = (page - 1) * page_size
    stocks = db.get_task_stocks(task_id, status=status, limit=page_size, offset=offset)
    total = db.summarize_task_stocks(task_id)
    if status:
        count = total.get(status, 0)
    else:
        count = total["total_stocks"]
    return {"task_id": task_id, "stocks": stocks, "total": count, "page": page, "page_size": page_size}
```

Update `/api/scan/status` running response to include mode and DB summary:

```python
        summary = db.refresh_scan_task_counts(_running["task_id"]) if _running.get("task_id") else {}
        return {
            "running": True,
            "task_id": _running["task_id"],
            "mode": _running.get("mode", "full"),
            "stats": {**summary, **_running.get("stats", {})},
        }
```

- [ ] **Step 6: Add retry-failed endpoint in `server.py`**

Add:

```python
@app.post("/api/scan/tasks/{task_id}/retry-failed")
async def retry_failed_stocks(task_id: str):
    conflict = _scan_conflict_response()
    if conflict:
        return conflict

    config = load_config()
    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)
    failed = db.get_failed_task_stocks(task_id)
    if not failed:
        return {"task_id": task_id, "status": "no_failed_stocks", "retry_count": 0}

    db.reset_failed_task_stocks(task_id)
    db.get_conn().execute("UPDATE scan_tasks SET status='running', retry_mode='failed_only' WHERE id=?", (task_id,))
    db.get_conn().commit()
    _set_running(task_id, "failed_only")

    stocks = [{"code": s["code"], "name": s["name"], "market": s.get("market", "")} for s in failed]

    def run_retry():
        import datetime
        try:
            result = scan_all(config, task_id=task_id, stocks=stocks, retry_policy="failed_only")
            s = result["stats"]
            db.finish_scan_task(
                task_id,
                finished_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                candidates_count=s.get("candidates_found", 0),
                elapsed_seconds=s.get("elapsed_seconds", 0),
                scanned=s.get("scanned", 0),
                skipped=s.get("skipped", 0),
            )
            db.refresh_scan_task_counts(task_id)
        except Exception as e:
            import traceback
            logger.error(f"Retry failed stocks failed: {e}\n{traceback.format_exc()}")
            db.get_conn().execute("UPDATE scan_tasks SET status='failed', error=? WHERE id=?", (str(e), task_id))
            db.get_conn().commit()
        finally:
            _clear_running()

    threading.Thread(target=run_retry, daemon=True).start()
    return {"task_id": task_id, "status": "retry_started", "retry_count": len(stocks)}
```

- [ ] **Step 7: Make scheduler respect global running DB state**

In `scheduler/scheduler.py`, before calling `scan_all(config)`, add:

```python
        import scanner.db as db
        db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
        db.init_db(db_path)
        if config.get("scheduler", {}).get("skip_if_running", True) and db.get_running_task_id():
            logger.info("Scheduled scan skipped because another scan is running")
            return
```

- [ ] **Step 8: Run server API tests**

Run:

```bash
python -m pytest tests/test_server_scan_api.py -v
```

Expected: PASS.

- [ ] **Step 9: Run backend integration tests**

Run:

```bash
python -m pytest tests/test_server_scan_api.py tests/test_scan_task_tracking.py tests/test_engine_fresh_fetch.py -v
```

Expected: PASS.

- [ ] **Step 10: Commit server API changes**

Run:

```bash
git add server.py scheduler/scheduler.py tests/test_server_scan_api.py
git commit -m "Add scan retry APIs and mutex"
```

Expected: commit succeeds.

---

## Task 6: Frontend API client and scan console failure visibility

**Files:**
- Modify: `web/src/composables/useApi.js`
- Modify: `web/src/components/ScanEngine.vue`
- Modify: `web/src/pages/ScannerConsole.vue`

- [ ] **Step 1: Update `useApi.js` API client functions**

Modify `web/src/composables/useApi.js`:

```javascript
const API_BASE = '/api'

export function useApi() {
  async function startScan() {
    const res = await fetch(`${API_BASE}/scan/start`)
    const body = await res.json()
    return { ...body, ok: res.ok, statusCode: res.status }
  }

  async function getScanStatus() {
    const res = await fetch(`${API_BASE}/scan/status`)
    return res.json()
  }

  async function getCandidates(params = {}) {
    const qs = new URLSearchParams(params).toString()
    const res = await fetch(`${API_BASE}/candidates?${qs}`)
    return res.json()
  }

  async function getCandidate(code) {
    const res = await fetch(`${API_BASE}/candidate/${code}`)
    if (!res.ok) return null
    return res.json()
  }

  async function getScanTasks() {
    const res = await fetch(`${API_BASE}/scan/tasks`)
    return res.json()
  }

  async function getTaskStocks(taskId, params = {}) {
    const qs = new URLSearchParams(params).toString()
    const res = await fetch(`${API_BASE}/scan/tasks/${taskId}/stocks?${qs}`)
    return res.json()
  }

  async function retryFailedStocks(taskId) {
    const res = await fetch(`${API_BASE}/scan/tasks/${taskId}/retry-failed`, { method: 'POST' })
    const body = await res.json()
    return { ...body, ok: res.ok, statusCode: res.status }
  }

  async function getConfig() {
    try {
      const res = await fetch(`${API_BASE}/config`)
      return res.json()
    } catch { return { config: {} } }
  }

  async function updateConfig(data) {
    try {
      const res = await fetch(`${API_BASE}/config`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })
      return res.json()
    } catch { return { status: 'error', message: '保存失败' } }
  }

  return {
    startScan, getScanStatus, getCandidates, getCandidate, getScanTasks,
    getTaskStocks, retryFailedStocks, getConfig, updateConfig,
  }
}
```

- [ ] **Step 2: Update `ScanEngine.vue` props and display**

Modify props:

```javascript
const props = defineProps({
  running: Boolean,
  scanned: Number,
  total: Number,
  currentCode: String,
  currentName: String,
  skipped: Number,
  failed: Number,
  candidates: Number,
  latestTradeDate: String,
  stockPoolSource: String,
  logLines: { type: Array, default: () => [] },
})
```

Replace `progressText` and `skipText`:

```javascript
const progressText = computed(() => {
  const total = props.total || 0
  const scanned = props.scanned || 0
  return `已处理 ${scanned} / ${total || '--'} · 剩余 ${Math.max(0, total - scanned)}只`
})
const statusText = computed(() => props.running ? '扫描任务进行中' : '')
const skipText = computed(() => `跳过 ${props.skipped || 0} · 失败 ${props.failed || 0} · 候选 ${props.candidates || 0}`)
const sourceText = computed(() => props.stockPoolSource ? `股票池 ${props.stockPoolSource}` : '股票池 --')
```

Inside `.current-stock`, add source/date display:

```vue
<span class="speed">{{ skipText }}</span>
```

Below `.current-stock`, add:

```vue
<div class="scan-meta">
  <span>{{ sourceText }}</span>
  <span>最新交易日 {{ latestTradeDate || '--' }}</span>
</div>
```

Add CSS:

```css
.scan-meta { display: flex; justify-content: space-between; margin-top: 8px; font-size: 11px; color: var(--text-muted); }
```

- [ ] **Step 3: Update `ScannerConsole.vue` state and API usage**

Change API destructuring:

```javascript
const { startScan, getScanStatus, getCandidates, getTaskStocks, retryFailedStocks } = useApi()
```

Change scan progress initial state:

```javascript
const scanProgress = reactive({
  taskId: '', scanned: 0, total: 0, currentCode: '--', currentName: '--',
  skipped: 0, failed: 0, candidates: 0, latestTradeDate: '', stockPoolSource: '',
})
const failures = ref([])
```

Pass new props to `ScanEngine`:

```vue
<ScanEngine
  :running="scanning"
  :scanned="scanProgress.scanned"
  :total="scanProgress.total"
  :currentCode="scanProgress.currentCode"
  :currentName="scanProgress.currentName"
  :skipped="scanProgress.skipped"
  :failed="scanProgress.failed"
  :candidates="scanProgress.candidates"
  :latestTradeDate="scanProgress.latestTradeDate"
  :stockPoolSource="scanProgress.stockPoolSource"
  :logLines="logLines"
  @start="handleStartScan"
  @stop="handleStopScan"
/>
```

In `handleStartScan()`, process status code:

```javascript
    const res = await startScan()
    if (!res.ok || res.error) {
      if (res.statusCode === 409) {
        scanError.value = `扫描已在运行中：${res.running_task_id || '--'}`
      } else {
        scanError.value = res.error || '启动扫描失败'
      }
      return
    }
    scanProgress.taskId = res.task_id
    scanProgress.total = res.total_stocks || 0
    scanProgress.stockPoolSource = res.stock_pool_source || ''
    scanning.value = true
    pollTimer = setInterval(pollStatus, 1000)
```

Add helper to update progress:

```javascript
function applyStats(status) {
  const stats = status.stats || {}
  scanProgress.taskId = status.task_id || scanProgress.taskId
  scanProgress.scanned = stats.processed || stats.scanned || 0
  scanProgress.total = stats.total_stocks || scanProgress.total || 0
  scanProgress.skipped = stats.skipped || 0
  scanProgress.failed = stats.failed || stats.failed_count || 0
  scanProgress.candidates = stats.candidates_found || stats.candidates_count || 0
  scanProgress.currentCode = stats.current_code || '--'
  scanProgress.currentName = stats.current_name || '--'
  scanProgress.latestTradeDate = stats.latest_trade_date || ''
  scanProgress.stockPoolSource = stats.stock_pool_source || scanProgress.stockPoolSource || ''
}
```

Use it in `pollStatus()` and `onMounted()` instead of assigning fields one by one.

- [ ] **Step 4: Add failure list and retry UI to `ScannerConsole.vue`**

Below the two-column panel, add:

```vue
<div class="panel failure-panel" v-if="scanProgress.taskId">
  <div class="panel-header">
    <span>失败股票 · {{ scanProgress.failed || 0 }}</span>
    <button class="retry-btn" :disabled="scanning || !scanProgress.failed" @click="handleRetryFailed">重新拉取失败股票</button>
  </div>
  <div v-if="failures.length === 0" class="empty-state">暂无失败股票</div>
  <div v-for="f in failures" :key="f.code" class="failure-row">
    <span class="code">{{ f.code }}</span>
    <span>{{ f.name }}</span>
    <span class="muted">{{ f.status_reason || f.error_detail || '--' }}</span>
    <span class="muted">主源 {{ f.primary_attempts || 0 }} · 备源 {{ f.fallback_attempts || 0 }}</span>
  </div>
</div>
```

Add functions:

```javascript
async function loadFailures() {
  if (!scanProgress.taskId) return
  try {
    const data = await getTaskStocks(scanProgress.taskId, { status: 'failed', page_size: 20 })
    failures.value = data.stocks || []
  } catch (e) {
    console.error('Load failures failed:', e)
  }
}

async function handleRetryFailed() {
  if (!scanProgress.taskId) return
  const res = await retryFailedStocks(scanProgress.taskId)
  if (!res.ok || res.error) {
    scanError.value = res.statusCode === 409 ? `扫描已在运行中：${res.running_task_id || '--'}` : (res.error || '重拉失败股票失败')
    return
  }
  if (res.retry_count === 0) {
    scanError.value = '没有需要重拉的失败股票'
    return
  }
  scanning.value = true
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = setInterval(pollStatus, 1000)
}
```

Call `loadFailures()` when a scan stops and after applying stats:

```javascript
      await loadFailures()
```

Add CSS:

```css
.failure-panel { margin-top: 12px; }
.retry-btn { background: transparent; color: var(--accent); border: 1px solid var(--accent); border-radius: 4px; padding: 4px 10px; cursor: pointer; }
.retry-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.failure-row { display: grid; grid-template-columns: 90px 120px 1fr 140px; gap: 8px; padding: 8px 16px; border-top: 1px solid var(--border); font-size: 12px; }
.failure-row .code { color: var(--accent); font-family: var(--font-mono); }
.muted { color: var(--text-muted); }
```

- [ ] **Step 5: Make frontend candidate list de-duplicate on load**

Add helper in `ScannerConsole.vue`:

```javascript
function dedupeDiscoveries(list) {
  const byCode = new Map()
  list.forEach(item => byCode.set(item.code, item))
  return Array.from(byCode.values())
}
```

Use in `loadResults()`:

```javascript
    discoveries.value = dedupeDiscoveries((data.candidates || []).map(c => ({
      code: c.code,
      name: c.name,
      score: c.score,
      rating: c.score >= 80 ? 'strong' : c.score >= 70 ? 'medium' : 'weak',
      status: statusFor(c),
      detail: formatDetail(c),
    })))
```

- [ ] **Step 6: Build frontend**

Run:

```bash
cd web && npm run build
```

Expected: Vite build succeeds.

- [ ] **Step 7: Commit frontend scan console changes**

Run:

```bash
git add web/src/composables/useApi.js web/src/components/ScanEngine.vue web/src/pages/ScannerConsole.vue
git commit -m "Show scan failures and retry controls"
```

Expected: commit succeeds.

---

## Task 7: Task center visibility for failed scans

**Files:**
- Modify: `web/src/pages/TaskCenter.vue`

- [ ] **Step 1: Add failure/source columns in `TaskCenter.vue`**

Update header grid to include failed/source/date columns:

```vue
<div class="task-header">
  <span style="width:20px"></span>
  <span>扫描日期</span>
  <span>范围</span>
  <span>状态</span>
  <span>耗时</span>
  <span>候选</span>
  <span>失败</span>
  <span>来源</span>
  <span>最新日</span>
  <span>操作</span>
</div>
```

Update row:

```vue
<div v-for="t in tasks" :key="t.id" class="task-row">
  <span class="task-dot" :class="t.running ? 'running' : 'done'"></span>
  <span class="task-date">{{ t.date }}</span>
  <span>{{ t.scope || '全市场' }}</span>
  <span :class="t.running ? 'st-running' : 'st-done'">{{ t.running ? '扫描中' : statusText(t.status) }}</span>
  <span class="muted">{{ t.duration || '--' }}</span>
  <span class="blue">{{ t.candidates || 0 }}</span>
  <span class="red">{{ t.failed || 0 }}</span>
  <span class="muted">{{ t.stock_pool_source || '--' }}</span>
  <span class="muted">{{ t.latest_trade_date || '--' }}</span>
  <span class="actions">
    <button class="action-btn" @click="viewResults(t.id)" v-if="!t.running">查看结果</button>
    <button class="action-btn" @click="viewFailures(t.id)" v-if="!t.running && t.failed">失败列表</button>
    <span v-if="t.running" class="st-running">实时查看 →</span>
  </span>
</div>
```

Add script helpers:

```javascript
function statusText(status) {
  if (status === 'failed') return '失败'
  if (status === 'cancelled') return '已取消'
  return '已完成'
}
function viewFailures(id) { router.push(`/?task=${id}&status=failed`) }
```

Update grid CSS:

```css
.task-header {
  display: grid; grid-template-columns: 20px 180px 130px 80px 70px 60px 60px 80px 90px 160px;
  align-items: center; padding: 10px 16px; border-bottom: 2px solid var(--border-light);
  font-size: 11px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px;
}
.task-row {
  display: grid; grid-template-columns: 20px 180px 130px 80px 70px 60px 60px 80px 90px 160px;
  align-items: center; padding: 12px 16px; border-bottom: 1px solid var(--border); font-size: 13px;
}
```

- [ ] **Step 2: Build frontend**

Run:

```bash
cd web && npm run build
```

Expected: Vite build succeeds.

- [ ] **Step 3: Commit task center changes**

Run:

```bash
git add web/src/pages/TaskCenter.vue
git commit -m "Surface scan failures in task center"
```

Expected: commit succeeds.

---

## Task 8: Final verification and manual run smoke test

**Files:**
- Verify: full test suite and frontend build
- Optional manual run: backend and frontend dev servers

- [ ] **Step 1: Run all Python tests**

Run:

```bash
python -m pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 2: Run frontend build**

Run:

```bash
cd web && npm run build
```

Expected: build exits 0.

- [ ] **Step 3: Start backend smoke server**

Run:

```bash
python main.py serve --port 8080
```

Expected: server starts and `http://127.0.0.1:8080/docs` returns HTTP 200. If using the Claude Code Bash tool, run this in background and poll with:

```bash
python - <<'PY'
import urllib.request
with urllib.request.urlopen('http://127.0.0.1:8080/docs', timeout=5) as r:
    print(r.status)
PY
```

Expected output:

```text
200
```

- [ ] **Step 4: Start frontend smoke server**

Run:

```bash
npm --prefix web run dev -- --host 127.0.0.1
```

Expected: Vite starts and `http://127.0.0.1:5173/` returns HTTP 200. Poll with:

```bash
python - <<'PY'
import urllib.request
with urllib.request.urlopen('http://127.0.0.1:5173/', timeout=5) as r:
    print(r.status)
PY
```

Expected output:

```text
200
```

- [ ] **Step 5: Manual API verification with a small mocked or controlled scan if available**

If external data sources are available, click “开始扫描” in the UI and verify:

```text
- total is not the old hard-coded 5128 fallback
- running status shows processed/skipped/failed/candidate counts
- candidates do not duplicate by code
- failures appear in the failure panel with source attempt counts
- retry failed is disabled while a scan is running
```

If external data sources are unavailable, use the automated tests from Tasks 1-5 as the verification evidence and report that live external-source validation was skipped because it depends on network data-source availability.

- [ ] **Step 6: Inspect final git state**

Run:

```bash
git status --short
git log --oneline -8
```

Expected: only intentional uncommitted files remain. The existing `CLAUDE.md` local modification may remain if it was not part of this feature branch; do not include it in scan reliability commits unless explicitly instructed.

---

## Self-Review Checklist

- Spec coverage:
  - Fresh-first K-line fetch: Task 3 and Task 4.
  - No old-cache fallback after data-source failure: Task 3.
  - Candidate de-duplication: Task 1 and Task 4.
  - Full stock-pool task coverage: Task 1, Task 2, Task 5.
  - Per-stock status and failure reason: Task 1, Task 4, Task 5.
  - Failed-stock retry: Task 4 and Task 5.
  - Global single running scan: Task 5.
  - Frontend failure visibility and retry controls: Task 6 and Task 7.
- Incomplete-marker scan: the plan was searched for unfinished markers and none remain; code snippets use `value_marks` for SQL parameter markers to avoid ambiguous wording.
- Type consistency:
  - `task_id`, `status_reason`, `primary_attempts`, `fallback_attempts`, `kline_latest_date`, and `quote_status` names match across DB, server, engine, and frontend.
  - `retry_policy` values are `normal` and `failed_only` in engine; persisted task `retry_mode` values are `full` and `failed_only`.
  - API paths match frontend client functions.

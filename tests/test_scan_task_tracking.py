import sqlite3

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


def test_init_db_migrates_legacy_task_stocks_table(tmp_path):
    db_path = tmp_path / "cuphandle.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE task_stocks (
                task_id TEXT NOT NULL,
                idx INTEGER NOT NULL,
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                scanned INTEGER DEFAULT 0
            )
            """
        )
        conn.execute(
            "INSERT INTO task_stocks (task_id, idx, code, name, scanned) VALUES (?, ?, ?, ?, ?)",
            ("task-legacy", 0, "600000", "浦发银行", 1),
        )
        conn.commit()

    db.init_db(str(db_path))

    with db.get_conn() as conn:
        stock_columns = {r[1] for r in conn.execute("PRAGMA table_info(task_stocks)").fetchall()}

    rows = db.get_task_stocks("task-legacy")

    assert "status" in stock_columns
    assert "status_reason" in stock_columns
    assert "primary_attempts" in stock_columns
    assert rows == [
        {
            "task_id": "task-legacy",
            "idx": 0,
            "code": "600000",
            "name": "浦发银行",
            "scanned": 1,
            "market": None,
            "status": "pending",
            "status_reason": None,
            "error_detail": None,
            "primary_source": None,
            "fallback_source": None,
            "primary_attempts": 0,
            "fallback_attempts": 0,
            "primary_error": None,
            "fallback_error": None,
            "kline_latest_date": None,
            "quote_status": "not_requested",
            "quote_error": None,
            "started_at": None,
            "finished_at": None,
            "updated_at": None,
        }
    ]


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



def test_get_pending_stocks_resume_includes_low_idx_unfinished_rows(tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    db.create_scan_task("task-resume", "2026-06-04 09:30:00", total_stocks=4)
    db.save_task_stocks("task-resume", [
        {"code": "000001", "name": "平安银行", "market": "深证主板"},
        {"code": "000002", "name": "万科A", "market": "深证主板"},
        {"code": "600000", "name": "浦发银行", "market": "上证主板"},
        {"code": "600036", "name": "招商银行", "market": "上证主板"},
    ])
    db.update_task_stock("task-resume", "000001", status="fetching")
    db.update_task_stock("task-resume", "000002", status="scanned")
    db.update_task_stock("task-resume", "600000", status="skipped")
    db.update_task_stock("task-resume", "600036", status="pending")

    pending = db.get_pending_stocks("task-resume", from_idx=3)

    assert [row["code"] for row in pending] == ["000001", "600036"]


def test_get_interrupted_task_ignores_stale_server_restarted_history(tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    db.create_scan_task("old-failed", "2026-06-04 09:30:00", total_stocks=2)
    db.save_task_stocks("old-failed", [
        {"code": "000001", "name": "平安银行", "market": "深证主板"},
        {"code": "000002", "name": "万科A", "market": "深证主板"},
    ])
    db.update_task_stock("old-failed", "000001", status="scanned")
    db.refresh_scan_task_counts("old-failed")
    conn = db.get_conn()
    conn.execute("UPDATE scan_tasks SET status='failed', error='Server restarted' WHERE id=?", ("old-failed",))
    conn.commit()

    assert db.get_interrupted_task() is None


def test_mark_dead_tasks_as_failed_makes_current_interrupted_task_resumable(tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    db.create_scan_task("running-now", "2026-06-06 09:30:00", total_stocks=2)
    db.save_task_stocks("running-now", [
        {"code": "000001", "name": "平安银行", "market": "深证主板"},
        {"code": "000002", "name": "万科A", "market": "深证主板"},
    ])
    db.update_task_stock("running-now", "000001", status="scanned")
    db.update_task_stock("running-now", "000002", status="fetching")
    db.refresh_scan_task_counts("running-now")

    db.mark_dead_tasks_as_failed()

    interrupted = db.get_interrupted_task()
    assert interrupted["id"] == "running-now"


def test_get_a_stock_pool_result_uses_akshare_when_available(monkeypatch, tmp_path):
    import types
    from scanner import stock_pool

    db.init_db(str(tmp_path / "cuphandle.db"))

    class FakeDataFrame:
        def iterrows(self):
            return iter([
                (0, {"code": "600000", "name": "浦发银行"}),
                (1, {"code": "830001", "name": "北交测试"}),
                (2, {"code": "000002", "name": "ST样本"}),
            ])

    fake_ak = types.SimpleNamespace(stock_info_a_code_name=lambda: FakeDataFrame())
    monkeypatch.setitem(__import__("sys").modules, "akshare", fake_ak)

    result = stock_pool.get_a_stock_pool_result({"market": {"exclude_st": True, "exclude_bj": True}})
    saved = db.get_stock_pool()

    assert result["source"] == "akshare"
    assert result["error"] is None
    assert result["stocks"] == [{"code": "600000", "name": "浦发银行", "market": "上证主板"}]
    assert saved == [
        {"code": "600000", "name": "浦发银行", "market": ""},
        {"code": "830001", "name": "北交测试", "market": ""},
        {"code": "000002", "name": "ST样本", "market": ""},
    ]



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



def test_get_a_stock_pool_result_returns_none_source_when_all_sources_fail(monkeypatch, tmp_path):
    import types
    from scanner import stock_pool

    db.init_db(str(tmp_path / "cuphandle.db"))

    def fail():
        raise RuntimeError("akshare down")

    fake_ak = types.SimpleNamespace(stock_info_a_code_name=fail)
    monkeypatch.setitem(__import__("sys").modules, "akshare", fake_ak)

    result = stock_pool.get_a_stock_pool_result({"market": {}})

    assert result["source"] == "none"
    assert result["stocks"] == []
    assert result["error"]
    assert "akshare down" in result["error"] or "stock pool" in result["error"].lower()



def test_get_a_stock_pool_delegates_to_result_helper(monkeypatch):
    from scanner import stock_pool

    expected = [{"code": "600000", "name": "浦发银行"}]
    monkeypatch.setattr(
        stock_pool,
        "get_a_stock_pool_result",
        lambda config: {"stocks": expected, "source": "akshare", "error": None},
    )

    assert stock_pool.get_a_stock_pool({"market": {}}) == expected

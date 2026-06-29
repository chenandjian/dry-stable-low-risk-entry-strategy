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
    assert "kline_fetched_at" in stock_columns
    assert "kline_target_trade_date" in stock_columns
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
    assert "source_errors" in stock_columns
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
            "source_errors": None,
            "kline_latest_date": None,
            "quote_status": "not_requested",
            "quote_error": None,
            "kline_fetched_at": None,
            "kline_target_trade_date": None,
            "started_at": None,
            "finished_at": None,
            "updated_at": None,
        }
    ]


def test_init_db_migrates_source_errors_to_legacy_task_stocks(tmp_path):
    """ROUND3-001: Old task_stocks without source_errors column gets it on upgrade."""
    import json
    db_path = tmp_path / "cuphandle.db"
    # Create old-style task_stocks WITHOUT source_errors
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE task_stocks (
                task_id TEXT NOT NULL,
                idx INTEGER NOT NULL,
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                primary_source TEXT,
                fallback_source TEXT,
                primary_attempts INTEGER DEFAULT 0,
                fallback_attempts INTEGER DEFAULT 0,
                primary_error TEXT,
                fallback_error TEXT,
                kline_latest_date TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO task_stocks (task_id, idx, code, name, status) VALUES (?, ?, ?, ?, ?)",
            ("task-1", 0, "600000", "浦发银行", "pending"),
        )
        conn.commit()

    db.init_db(str(db_path))

    with db.get_conn() as conn:
        stock_columns = {r[1] for r in conn.execute("PRAGMA table_info(task_stocks)").fetchall()}

    assert "source_errors" in stock_columns

    # Verify update with source_errors works
    db.update_task_stock("task-1", "600000", status="failed", source_errors='{"sina":"busy"}')
    row = db.get_task_stocks("task-1")[0]
    assert row["source_errors"] == '{"sina":"busy"}'


def test_source_errors_persisted_as_valid_json_by_encode_helper():
    """ROUND3-005: _encode_source_errors outputs valid JSON, not str(dict)."""
    import json
    from scanner.engine import _encode_source_errors

    source_errors = {"sina": "busy", "baidu": "attempts=2 error=timeout"}
    encoded = _encode_source_errors(source_errors)

    assert encoded is not None
    # Must be valid JSON
    parsed = json.loads(encoded)
    assert parsed == source_errors
    # Must NOT use Python repr format (single quotes)
    assert "'" not in encoded


def test_source_errors_persisted_for_all_status_branches(monkeypatch, tmp_path):
    """ROUND3-005: source_errors persisted in skipped/candidate/scanned/failed branches."""
    import json
    db_path = tmp_path / "cuphandle.db"
    from scanner import engine as engine_mod
    from scanner import stock_pool

    config = {
        "data": {"database_path": str(db_path), "worker_count": 1},
        "liquidity": {"enabled": False, "min_listing_days": 250},
        "scoring": {"medium_threshold": 70},
    }
    stocks = [
        {"code": "000001", "name": "StockA", "market": "SZ"},
        {"code": "000002", "name": "StockB", "market": "SZ"},
        {"code": "000003", "name": "StockC", "market": "SZ"},
    ]

    db.init_db(str(db_path))
    db.create_scan_task("task-src", "2026-06-09 09:00:00", total_stocks=len(stocks))
    db.save_task_stocks("task-src", stocks)

    source_errors_seen = []

    class FakeManager:
        def acquire(self, ds_name):
            return True
        def release(self, ds_name):
            pass

    fetch_call = [0]

    def fake_fetch_with_retry(code, ds, *args, mgr=None, source_chain=None, kline_days=None, **kwargs):
        fetch_call[0] += 1
        call_num = fetch_call[0]
        if call_num == 1:
            # StockA: successful fetch but with prior source errors
            return engine_mod.FetchResult(
                data=_rrows(260, close=20.0),
                primary_source="baidu",
                fallback_source="sina",
                primary_attempts=1,
                source_errors={"sina": "busy"},
            )
        elif call_num == 2:
            # StockB: insufficient listing days
            return engine_mod.FetchResult(
                data=[{"date": "2026-06-09", "open": 10, "high": 10, "low": 10, "close": 10, "volume": 1_000_000, "turnover": 10_000_000}],
                primary_source="baidu",
                fallback_source="baidu",
                primary_attempts=1,
                source_errors={"sina": "attempts=2 error=timeout", "tencent": "busy"},
            )
        else:
            # StockC: all sources failed
            return engine_mod.FetchResult(
                data=None,
                primary_source="baidu",
                fallback_source="tencent",
                primary_attempts=2,
                fallback_attempts=2,
                primary_error="timeout",
                fallback_error="empty response",
                source_errors={"baidu": "attempts=2 error=timeout", "sina": "busy", "tencent": "attempts=2 error=empty response"},
            )

    def fake_row(day, close=10.0):
        return {"date": day, "open": close, "high": close, "low": close, "close": close, "volume": 10_000_000, "turnover": close * 10_000_000}

    def _rrows(count, close=10.0):
        rows = []
        for day in range(1, count + 1):
            month = ((day - 1) // 28) + 1
            dom = ((day - 1) % 28) + 1
            rows.append(fake_row(f"2026-{month:02d}-{dom:02d}", close=close))
        return rows

    monkeypatch.setattr(engine_mod, "DataSourceManager", FakeManager)
    monkeypatch.setattr(engine_mod.threading, "Thread", type("ImmediateThread", (), {
        "__init__": lambda self, target=None, args=(), daemon=None: setattr(self, "target", target) or setattr(self, "args", args),
        "start": lambda self: self.target(*self.args) if self.target else None,
        "join": lambda self: None,
    }))
    monkeypatch.setattr(engine_mod, "_fetch_with_retry", fake_fetch_with_retry)
    monkeypatch.setattr(stock_pool, "get_a_stock_pool", lambda config: stocks)
    monkeypatch.setattr(engine_mod, "fetch_market_index_daily", lambda symbol=None: [])

    class FakeStrategyEngine:
        def __init__(self, config):
            pass
        def evaluate_at(self, data, code="", name="", market_data=None):
            result = engine_mod.CupHandleResult(found=False, code=code, name=name)
            dry = {
                "decision": {"verdict": "不建议买入", "verdict_key": "REJECT", "summary": ""},
                "volume_dry": {"score": 5},
                "price_stable": {"score": 5},
                "pattern_score": {"score": 0, "type": "无有效形态", "key_pattern_type": "other"},
                "risk_reward": {"risk_percent": 0, "rr1": 0, "position_advice": ""},
                "key_prices": {"entry_zone_low": 0, "entry_zone_high": 0, "pivot": 0, "stop_loss": 0, "target_1": 0, "target_2": 0},
                "market_environment": {"status": "", "position_advice": ""},
            }
            return type("Eval", (), {"result": result, "dry_stable": dry, "passed": False})()

    monkeypatch.setattr(engine_mod, "CupHandleStrategyEngine", FakeStrategyEngine)
    monkeypatch.setattr(engine_mod, "passes_liquidity_filter", lambda data, cfg: True)

    engine_mod.scan_all(config, task_id="task-src", worker_count=1)

    all_rows = db.get_task_stocks("task-src")
    assert len(all_rows) == 3

    # Find each stock by code
    by_code = {r["code"]: r for r in all_rows}

    # StockA: scanned (successful fetch with prior source busy on sina)
    assert by_code["000001"]["status"] == "scanned"
    assert by_code["000001"]["source_errors"] is not None
    parsed_a = json.loads(by_code["000001"]["source_errors"])
    assert parsed_a == {"sina": "busy"}

    # StockB: skipped (insufficient listing days, but source_errors saved)
    assert by_code["000002"]["status"] == "skipped"
    assert by_code["000002"]["source_errors"] is not None
    parsed_b = json.loads(by_code["000002"]["source_errors"])
    assert "sina" in parsed_b
    assert "tencent" in parsed_b

    # StockC: failed (all sources failed)
    assert by_code["000003"]["status"] == "failed"
    assert by_code["000003"]["source_errors"] is not None
    parsed_c = json.loads(by_code["000003"]["source_errors"])
    assert "baidu" in parsed_c
    assert "sina" in parsed_c
    assert "tencent" in parsed_c


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
        kline_fetched_at="2026-06-15 15:11:00",
        kline_target_trade_date="2026-06-15",
        quote_status="not_requested",
    )

    all_rows = db.get_task_stocks("task-1")
    failed_rows = db.get_task_stocks("task-1", status="failed")
    stats = db.summarize_task_stocks("task-1")

    assert [r["code"] for r in all_rows] == ["600000", "000001"]
    assert len(failed_rows) == 1
    assert failed_rows[0]["status_reason"] == "数据源全部失败，未使用旧缓存扫描"
    assert failed_rows[0]["primary_attempts"] == 2
    assert failed_rows[0]["kline_fetched_at"] == "2026-06-15 15:11:00"
    assert failed_rows[0]["kline_target_trade_date"] == "2026-06-15"
    assert stats["total_stocks"] == 2
    assert stats["failed"] == 1
    assert stats["pending"] == 1


def test_reusable_kline_context_requires_fetch_after_target_close(tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    db.create_scan_task("task-old", "2026-06-15 14:55:00", total_stocks=0)
    db.save_task_stocks("task-old", [{"code": "600000", "name": "浦发银行"}])
    db.update_task_stock(
        "task-old",
        "600000",
        status="scanned",
        kline_latest_date="2026-06-15",
        kline_fetched_at="2026-06-15 14:59:00",
        kline_target_trade_date="2026-06-15",
    )
    db.create_scan_task("task-fresh", "2026-06-15 15:11:00", total_stocks=0)
    db.save_task_stocks("task-fresh", [{"code": "600000", "name": "浦发银行"}])
    db.update_task_stock(
        "task-fresh",
        "600000",
        status="scanned",
        kline_latest_date="2026-06-15",
        kline_fetched_at="2026-06-15 15:11:00",
        kline_target_trade_date="2026-06-15",
    )

    reusable = db.get_reusable_task_stock_kline_context(
        "600000",
        target_trade_date="2026-06-15",
        min_fetch_time="2026-06-15 15:00:00",
    )

    assert reusable["kline_fetched_at"] == "2026-06-15 15:11:00"


def test_reusable_kline_context_rejects_inconclusive_suspended_source_errors(tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    db.create_scan_task("task-polluted", "2026-06-29 15:20:00", total_stocks=0)
    db.save_task_stocks("task-polluted", [{"code": "000921", "name": "海信家电"}])
    db.update_task_stock(
        "task-polluted",
        "000921",
        status="scanned",
        kline_latest_date="2026-06-26",
        kline_fetched_at="2026-06-29 15:21:03",
        kline_target_trade_date="2026-06-29",
        quote_status="suspended",
        source_errors=(
            '{"baidu":"busy",'
            '"sina":"attempts=1 error=missing target trade date 2026-06-29",'
            '"tencent":"busy"}'
        ),
    )

    reusable = db.get_reusable_task_stock_kline_context(
        "000921",
        target_trade_date="2026-06-29",
        min_fetch_time="2026-06-29 15:00:00",
    )

    assert reusable is None


def test_reusable_kline_context_allows_conclusive_suspended_source_errors(tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    db.create_scan_task("task-suspended", "2026-06-29 15:20:00", total_stocks=0)
    db.save_task_stocks("task-suspended", [{"code": "000921", "name": "海信家电"}])
    db.update_task_stock(
        "task-suspended",
        "000921",
        status="scanned",
        kline_latest_date="2026-06-26",
        kline_fetched_at="2026-06-29 15:21:03",
        kline_target_trade_date="2026-06-29",
        quote_status="suspended",
        source_errors=(
            '{"baidu":"attempts=1 error=missing target trade date 2026-06-29",'
            '"sina":"attempts=1 error=missing target trade date 2026-06-29",'
            '"tencent":"attempts=1 error=missing target trade date 2026-06-29"}'
        ),
    )

    reusable = db.get_reusable_task_stock_kline_context(
        "000921",
        target_trade_date="2026-06-29",
        min_fetch_time="2026-06-29 15:00:00",
    )

    assert reusable["kline_latest_date"] == "2026-06-26"
    assert reusable["quote_status"] == "suspended"


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


def test_get_interrupted_task_returns_unfinished_failed_task(tmp_path):
    """Any failed/cancelled task with remaining stocks (finished_at=NULL) is resumable."""
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

    # Unfinished (scanned=1 < total=2, finished_at=NULL) → resumable
    result = db.get_interrupted_task()
    assert result is not None
    assert result["id"] == "old-failed"


def test_get_interrupted_task_ignores_finished_failed_task(tmp_path):
    """A failed task with finished_at set is completed, not resumable."""
    db.init_db(str(tmp_path / "cuphandle.db"))
    db.create_scan_task("done-failed", "2026-06-04 09:30:00", total_stocks=2)
    db.save_task_stocks("done-failed", [
        {"code": "000001", "name": "平安银行", "market": "深证主板"},
        {"code": "000002", "name": "万科A", "market": "深证主板"},
    ])
    db.update_task_stock("done-failed", "000001", status="scanned")
    db.refresh_scan_task_counts("done-failed")
    conn = db.get_conn()
    conn.execute("UPDATE scan_tasks SET status='failed', error='Some error', finished_at='2026-06-04 10:00:00' WHERE id=?", ("done-failed",))
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

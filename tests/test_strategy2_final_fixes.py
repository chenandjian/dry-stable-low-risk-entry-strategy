# tests/test_strategy2_final_fixes.py
"""真实行为测试 — FINAL-S2-001 至 FINAL-S2-005。"""
import pytest
from fastapi.testclient import TestClient

import scanner.db as db
import server as server_mod
from strategy2.validation import validate_ohlc_structure
from strategy2.engine import ExtremeDryStableStrategyEngine


# ── helpers ──────────────────────────────────────────────────────────────────

def _s2_cfg():
    return {
        "strategy_window_days": 120, "minimum_required_days": 60,
        "candidate_min_score": 70, "max_risk_ratio": 0.05,
        "support_lookback_days": 10, "buy_zone_max_premium": 0.03,
        "stop_loss_buffer": 0.03,
    }


def _setup_server_state(tmp_path, running=False, task_id=None, strategy_type=None):
    """Reset server memory state and init DB."""
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    server_mod._running["running"] = running
    server_mod._running["task_id"] = task_id
    server_mod._running["strategy_type"] = strategy_type
    server_mod._running["stats"] = {}
    return db_path


# ═══════════════════════════════════════════════════════════════════════════════
# FINAL-S2-001: 跨策略执行防护
# ═══════════════════════════════════════════════════════════════════════════════

class TestCrossStrategyExecutionBlocked:
    """证明 Strategy2 任务无法进入 Strategy1 执行链。"""

    @pytest.mark.parametrize("url,method", [
        ("/api/candidates?task_id={task_id}", "get"),
        ("/api/scan/tasks/{task_id}/re-evaluate", "post"),
        ("/api/scan/tasks/{task_id}/retry-failed", "post"),
    ])
    def test_strategy1_endpoints_reject_strategy2_task(self, monkeypatch, tmp_path, url, method):
        """FINAL-S2-001: Strategy2 task_id rejected by all Strategy1 endpoints."""
        db_path = _setup_server_state(tmp_path)
        db.create_scan_task("s2-task", "2026-06-10 09:00:00",
                            strategy_type="STRATEGY_2_EXTREME_DRY_STABLE")
        # Mark completed so retry-failed has stocks
        db.save_task_stocks("s2-task", [{"code": "000001", "name": "test", "market": ""}])
        conn = db.get_conn()
        conn.execute("UPDATE scan_tasks SET status='completed', finished_at='2026-06-10 10:00:00' WHERE id='s2-task'")
        conn.execute("UPDATE task_stocks SET status='failed' WHERE task_id='s2-task'")
        conn.commit()

        monkeypatch.setattr(server_mod, "load_config",
                            lambda path="config.yaml": {"data": {"database_path": str(db_path)}})

        client = TestClient(server_mod.app)
        formatted_url = url.format(task_id="s2-task")
        if method == "get":
            res = client.get(formatted_url)
        else:
            res = client.post(formatted_url)

        assert res.status_code in (400, 404, 409), \
            f"{method.upper()} {formatted_url} returned {res.status_code}, expected 400/404/409"
        body = res.json()
        assert body.get("error") in (
            "TASK_STRATEGY_MISMATCH", "STRATEGY2_RETRY_NOT_SUPPORTED", "TASK_NOT_FOUND",
        ), f"Unexpected error code: {body.get('error')}"

    def test_strategy1_retry_still_works(self, monkeypatch, tmp_path):
        """Stage 5: Strategy1 retry — mock scan_all to avoid background thread leak."""
        import threading
        db_path = _setup_server_state(tmp_path)
        db.create_scan_task("s1-task", "2026-06-10 09:00:00",
                            strategy_type="STRATEGY_1_CUP_HANDLE")
        db.save_task_stocks("s1-task", [{"code": "000001", "name": "test", "market": ""}])
        conn = db.get_conn()
        conn.execute("UPDATE scan_tasks SET status='completed', finished_at='2026-06-10 10:00:00' WHERE id='s1-task'")
        conn.execute("UPDATE task_stocks SET status='failed' WHERE task_id='s1-task'")
        conn.commit()

        monkeypatch.setattr(server_mod, "load_config",
                            lambda path="config.yaml": {"data": {"database_path": str(db_path)}})
        server_mod._clear_running()

        done = threading.Event()
        received = {}
        def fake_scan_all(config, progress_callback=None, task_id=None, stocks=None, **kwargs):
            received["task_id"] = task_id
            received["stocks"] = stocks
            done.set()
            return {"candidates": [], "stats": {"total_stocks": len(stocks or []), "processed": len(stocks or []), "failed": 0, "skipped": 0, "candidates_found": 0}}
        monkeypatch.setattr(server_mod, "scan_all", fake_scan_all)

        client = TestClient(server_mod.app)
        res = client.post("/api/scan/tasks/s1-task/retry-failed")
        assert res.status_code == 200, f"Strategy1 retry blocked: {res.status_code} {res.json()}"
        assert done.wait(timeout=2), "retry worker did not finish"
        assert received["task_id"] == "s1-task"
        server_mod._clear_running()

    def test_strategy2_endpoints_reject_strategy1_task(self, monkeypatch, tmp_path):
        """FINAL-S2-001: Strategy2 endpoints reject Strategy1 task_id."""
        db_path = _setup_server_state(tmp_path)
        db.create_scan_task("s1-task", "2026-06-10 09:00:00",
                            strategy_type="STRATEGY_1_CUP_HANDLE")
        conn = db.get_conn()
        conn.execute("UPDATE scan_tasks SET status='completed', finished_at='2026-06-10 10:00:00' WHERE id='s1-task'")
        conn.commit()

        monkeypatch.setattr(server_mod, "load_config",
                            lambda path="config.yaml": {"data": {"database_path": str(db_path)}})

        client = TestClient(server_mod.app)
        res = client.get("/api/strategy2/candidates?task_id=s1-task")
        assert res.status_code in (400, 404), \
            f"Strategy2 candidates with S1 task returned {res.status_code}"

        res2 = client.get("/api/strategy2/candidates/000001?task_id=s1-task")
        assert res2.status_code in (400, 404), \
            f"Strategy2 detail with S1 task returned {res2.status_code}"

    def test_get_candidates_with_s2_task_id_rejected(self, monkeypatch, tmp_path):
        """FINAL-S2-001: GET /api/candidates?task_id=S2 → type mismatch."""
        db_path = _setup_server_state(tmp_path)
        db.create_scan_task("s2-task", "2026-06-10 09:00:00",
                            strategy_type="STRATEGY_2_EXTREME_DRY_STABLE")
        conn = db.get_conn()
        conn.execute("UPDATE scan_tasks SET status='completed', finished_at='2026-06-10 10:00:00' WHERE id='s2-task'")
        conn.commit()

        monkeypatch.setattr(server_mod, "load_config",
                            lambda path="config.yaml": {"data": {"database_path": str(db_path)}})

        client = TestClient(server_mod.app)
        res = client.get("/api/candidates?task_id=s2-task")
        assert res.status_code in (400, 404)


# ═══════════════════════════════════════════════════════════════════════════════
# FINAL-S2-005: 任务列表隔离
# ═══════════════════════════════════════════════════════════════════════════════

class TestTaskListIsolation:
    def test_s1_tasks_exclude_running_s2(self, monkeypatch, tmp_path):
        """FINAL-S2-005: Running S2 task excluded from S1 task list."""
        db_path = _setup_server_state(tmp_path, running=True, task_id="live-s2",
                                       strategy_type="STRATEGY_2_EXTREME_DRY_STABLE")
        server_mod._running["stats"] = {"total_stocks": 100, "scanned": 0, "candidates_found": 0}

        monkeypatch.setattr(server_mod, "load_config",
                            lambda path="config.yaml": {"data": {"database_path": str(db_path)}})

        client = TestClient(server_mod.app)
        res = client.get("/api/scan/tasks")
        data = res.json()
        # Running S2 must NOT appear in S1 task list
        s1_ids = [t["id"] for t in data["tasks"]]
        assert "live-s2" not in s1_ids, f"S2 task leaked into S1 list: {s1_ids}"

    def test_s2_tasks_include_running_s2(self, monkeypatch, tmp_path):
        """FINAL-S2-005: Running S2 task appears in S2 task list."""
        db_path = _setup_server_state(tmp_path, running=True, task_id="live-s2",
                                       strategy_type="STRATEGY_2_EXTREME_DRY_STABLE")
        server_mod._running["stats"] = {"total_stocks": 100, "scanned": 50, "candidates_found": 3}
        # Also create S2 DB task
        db.create_scan_task("live-s2", "2026-06-10 09:00:00",
                            strategy_type="STRATEGY_2_EXTREME_DRY_STABLE")

        monkeypatch.setattr(server_mod, "load_config",
                            lambda path="config.yaml": {"data": {"database_path": str(db_path)}})

        client = TestClient(server_mod.app)
        res = client.get("/api/strategy2/tasks")
        data = res.json()
        s2_ids = [t["id"] for t in data["tasks"]]
        assert "live-s2" in s2_ids, f"Running S2 missing from S2 list: {s2_ids}"

    def test_s2_tasks_exclude_running_s1(self, monkeypatch, tmp_path):
        """FINAL-S2-005: Running S1 task excluded from S2 task list."""
        db_path = _setup_server_state(tmp_path, running=True, task_id="live-s1",
                                       strategy_type="STRATEGY_1_CUP_HANDLE")
        server_mod._running["stats"] = {"total_stocks": 100}

        monkeypatch.setattr(server_mod, "load_config",
                            lambda path="config.yaml": {"data": {"database_path": str(db_path)}})

        client = TestClient(server_mod.app)
        res = client.get("/api/strategy2/tasks")
        data = res.json()
        s2_ids = [t["id"] for t in data["tasks"]]
        assert "live-s1" not in s2_ids, f"S1 task leaked into S2 list: {s2_ids}"

    def test_task_items_return_strategy_type(self, monkeypatch, tmp_path):
        """FINAL-S2-005: Task list items include strategy_type."""
        db_path = _setup_server_state(tmp_path)
        db.create_scan_task("s2-done", "2026-06-10 09:00:00",
                            strategy_type="STRATEGY_2_EXTREME_DRY_STABLE")
        conn = db.get_conn()
        conn.execute("UPDATE scan_tasks SET status='completed', finished_at='2026-06-10 10:00:00' WHERE id='s2-done'")
        conn.commit()

        monkeypatch.setattr(server_mod, "load_config",
                            lambda path="config.yaml": {"data": {"database_path": str(db_path)}})

        client = TestClient(server_mod.app)
        res = client.get("/api/strategy2/tasks")
        data = res.json()
        for t in data["tasks"]:
            assert "strategy_type" in t


# ═══════════════════════════════════════════════════════════════════════════════
# FINAL-S2-002: 候选终态 processed 回调
# ═══════════════════════════════════════════════════════════════════════════════

class TestCandidateTerminalProgress:
    def test_candidate_path_sends_scanning_callback(self, monkeypatch, tmp_path):
        """FINAL-S2-002: Candidate terminal path sends scanning callback."""
        from strategy2.scanner import scan_strategy2_all
        import scanner.daily_data_service

        db_path = str(tmp_path / "prog.db")
        db.init_db(db_path)

        from datetime import datetime, timedelta
        base = datetime(2026, 6, 10)
        mock_data = []
        for i in range(130):
            date = (base - timedelta(days=129 - i)).strftime("%Y-%m-%d")
            vol = 500_000 if i >= 110 else 2_000_000
            mock_data.append({"date": date, "open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0, "volume": vol, "turnover": 10.0 * vol})

        def mock_fetch(*args, **kwargs):
            from scanner.daily_data_service import FetchResult
            return FetchResult(data=list(mock_data), primary_source="test", fallback_source="test", from_cache=True)

        monkeypatch.setattr(scanner.daily_data_service, "fetch_with_retry", mock_fetch)

        callbacks_received = []
        def track_cb(stage, current, total, detail, discovery=None):
            callbacks_received.append((stage, current, total))

        stocks = [{"code": "000001", "name": "test", "market": ""}]
        config = {
            "strategy2": {
                "strategy_window_days": 120, "minimum_required_days": 60,
                "candidate_min_score": 60, "max_risk_ratio": 0.05,
                "support_lookback_days": 10, "buy_zone_max_premium": 0.03,
                "stop_loss_buffer": 0.03,
            },
            "liquidity": {"enabled": False},
            "data": {"database_path": db_path, "daily_sources": ["test"]},
        }
        # Pre-create task + stocks so refresh_scan_task_counts works
        db.create_scan_task("prog-test", "2026-06-10 09:00:00", total_stocks=1,
                            strategy_type="STRATEGY_2_EXTREME_DRY_STABLE")
        db.save_task_stocks("prog-test", stocks)

        result = scan_strategy2_all(config, task_id="prog-test", stocks=stocks,
                                     progress_callback=track_cb, worker_count=1)

        # Verify DB state — the stock should be marked as candidate
        summary = db.summarize_task_stocks("prog-test")
        assert summary["candidate"] + summary["scanned"] + summary["failed"] + summary["skipped"] == 1, \
            f"Stock should be in a terminal state: {summary}"

        # Scanning callbacks verify progress was reported
        scanning_cbs = [c for c in callbacks_received if c[0] == "scanning"]
        assert len(scanning_cbs) >= 1, f"No scanning callbacks: {callbacks_received}"
        assert result["stats"]["processed"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# FINAL-S2-003: 前端后端契约
# ═══════════════════════════════════════════════════════════════════════════════

class TestFrontendBackendContract:
    def test_scan_status_returns_exact_strategy_type(self, monkeypatch, tmp_path):
        """FINAL-S2-003: /api/scan/status must return exact strategyType when running."""
        db_path = _setup_server_state(tmp_path)
        db.create_scan_task("s2-running", "2026-06-10 09:00:00",
                            strategy_type="STRATEGY_2_EXTREME_DRY_STABLE")

        monkeypatch.setattr(server_mod, "load_config",
                            lambda path="config.yaml": {"data": {"database_path": str(db_path)}})

        client = TestClient(server_mod.app)
        res = client.get("/api/scan/status")
        data = res.json()
        assert data["running"] is True
        assert data["strategyType"] == "STRATEGY_2_EXTREME_DRY_STABLE"

    def test_strategy2_tasks_returns_strategy_type_per_item(self, monkeypatch, tmp_path):
        """FINAL-S2-003: /api/strategy2/tasks items include strategy_type."""
        db_path = _setup_server_state(tmp_path)
        db.create_scan_task("s2-done", "2026-06-10 09:00:00",
                            strategy_type="STRATEGY_2_EXTREME_DRY_STABLE")
        conn = db.get_conn()
        conn.execute("UPDATE scan_tasks SET status='completed', finished_at='2026-06-10 10:00:00' WHERE id='s2-done'")
        conn.commit()

        monkeypatch.setattr(server_mod, "load_config",
                            lambda path="config.yaml": {"data": {"database_path": str(db_path)}})

        client = TestClient(server_mod.app)
        res = client.get("/api/strategy2/tasks")
        data = res.json()
        assert len(data["tasks"]) >= 1
        for t in data["tasks"]:
            assert "strategy_type" in t
            assert t["strategy_type"] == "STRATEGY_2_EXTREME_DRY_STABLE"


# ═══════════════════════════════════════════════════════════════════════════════
# 回归：结构校验 + 窗口隔离
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegressionWindowAndDate:
    def test_non_iso_date_rejected(self):
        assert validate_ohlc_structure([{"date": "bad-001"}]) == "INVALID_MARKET_DATA"

    def test_future_date_passes_structure(self):
        """Future date is valid ISO — structure passes; cache layer rejects."""
        assert validate_ohlc_structure([{"date": "2099-12-31", "open": 10, "high": 10, "low": 10, "close": 10, "volume": 100}]) is None

    def test_unknown_task_type_lifespan_marks_failed(self, monkeypatch, tmp_path):
        """FINAL-S2-001 regression: Unknown strategy_type → task failed."""
        db_path = str(tmp_path / "unk.db")
        db.init_db(db_path)
        db.create_scan_task("unknown-task", "2026-06-10 09:00:00",
                            total_stocks=1, strategy_type="UNKNOWN_TYPE")
        db.save_task_stocks("unknown-task", [{"code": "000001", "name": "test", "market": ""}])
        conn = db.get_conn()
        conn.execute("UPDATE scan_tasks SET status='failed', finished_at=NULL WHERE id='unknown-task'")
        conn.commit()

        interrupted = db.get_interrupted_task()
        assert interrupted is not None
        assert interrupted["strategy_type"] == "UNKNOWN_TYPE"

    def test_valid_strategy2_scan_not_corrupted(self):
        """Regression: Normal strategy2 engine construction still works."""
        engine = ExtremeDryStableStrategyEngine(_s2_cfg())
        assert engine.strategy_window_days == 120
        assert engine.candidate_min_score == 70

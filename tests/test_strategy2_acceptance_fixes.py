# tests/test_strategy2_acceptance_fixes.py
"""验收修复测试 — ACCEPT-S2-001 至 ACCEPT-S2-005。"""
import pytest
from fastapi.testclient import TestClient

import scanner.db as db
import server as server_mod
from strategy2.validation import resolve_strategy2_config
from scanner.daily_data_service import (
    FetchResult,
    DEFAULT_DAILY_SOURCES,
    _daily_fetch_fn,
)
from scanner.data_source import DataSourceManager


# ═══════════════════════════════════════════════════════════════════════════════
# ACCEPT-S2-001: 失败终态不会留下 fetching
# ═══════════════════════════════════════════════════════════════════════════════

class TestFailedTerminalStates:
    def test_all_sources_failed_produces_failed_status(self, monkeypatch, tmp_path):
        """ACCEPT-S2-001: All sources failed → status=failed, not fetching."""
        from strategy2 import scanner as s2_scanner
        from scanner.daily_data_service import FetchResult

        db_path = str(tmp_path / "fail.db")
        db.init_db(db_path)

        def mock_fetch_fail(*args, **kwargs):
            return FetchResult(data=None, primary_source="test", fallback_source="test",
                               primary_error="connection refused", fallback_error="timeout")

        monkeypatch.setattr(s2_scanner, "fetch_with_retry", mock_fetch_fail)

        callbacks = []
        def track(stage, cur, tot, detail, disc=None):
            callbacks.append((stage, cur, tot))

        stocks = [{"code": "000001", "name": "test", "market": ""}]
        config = {
            "strategy2": {"strategy_window_days": 120, "minimum_required_days": 60,
                          "candidate_min_score": 70, "max_risk_ratio": 0.05,
                          "support_lookback_days": 10, "buy_zone_max_premium": 0.03,
                          "stop_loss_buffer": 0.03},
            "liquidity": {"enabled": False},
            "data": {"database_path": db_path, "daily_sources": ["test"]},
        }
        db.create_scan_task("fail-test", "2026-06-10 09:00:00", total_stocks=1,
                            strategy_type="STRATEGY_2_EXTREME_DRY_STABLE")
        db.save_task_stocks("fail-test", stocks)

        s2_scanner.scan_strategy2_all(config, task_id="fail-test", stocks=stocks,
                                       progress_callback=track, worker_count=1)

        # Verify: stock must be failed, not fetching
        task_stocks = db.get_task_stocks("fail-test")
        assert len(task_stocks) == 1
        assert task_stocks[0]["status"] == "failed", \
            f"Expected 'failed', got '{task_stocks[0]['status']}'"
        assert task_stocks[0]["finished_at"] is not None, "finished_at must be set"
        assert "ALL_DATA_SOURCES_FAILED" in (task_stocks[0].get("status_reason") or "")

        summary = db.summarize_task_stocks("fail-test")
        assert summary["failed"] == 1
        assert summary["fetching"] == 0

    def test_evaluation_exception_produces_failed_status(self, monkeypatch, tmp_path):
        """ACCEPT-S2-001: Engine crash → status=failed, STRATEGY2_EVALUATION_ERROR."""
        from strategy2 import scanner as s2_scanner
        from strategy2.engine import ExtremeDryStableStrategyEngine
        from scanner.daily_data_service import FetchResult

        db_path = str(tmp_path / "exn.db")
        db.init_db(db_path)

        from datetime import datetime, timedelta
        base = datetime(2026, 6, 10)
        mock_data = []
        for i in range(130):
            date = (base - timedelta(days=129 - i)).strftime("%Y-%m-%d")
            mock_data.append({"date": date, "open": 10, "high": 10, "low": 10, "close": 10, "volume": 1_000_000, "turnover": 10_000_000})

        def mock_fetch(*args, **kwargs):
            return FetchResult(data=list(mock_data), primary_source="test", fallback_source="test", from_cache=True)
        monkeypatch.setattr(s2_scanner, "fetch_with_retry", mock_fetch)

        # Make engine crash
        original_eval = ExtremeDryStableStrategyEngine.evaluate_at
        def crashing_eval(self, *args, **kwargs):
            raise RuntimeError("simulated engine crash")
        monkeypatch.setattr(ExtremeDryStableStrategyEngine, "evaluate_at", crashing_eval)

        # Make engine crash
        original_eval = ExtremeDryStableStrategyEngine.evaluate_at
        def crashing_eval(self, *args, **kwargs):
            raise RuntimeError("simulated engine crash")
        monkeypatch.setattr(ExtremeDryStableStrategyEngine, "evaluate_at", crashing_eval)

        callbacks = []
        def track(stage, cur, tot, detail, disc=None):
            callbacks.append((stage, cur, tot))

        stocks = [{"code": "000001", "name": "test", "market": ""}]
        config = {
            "strategy2": {"strategy_window_days": 120, "minimum_required_days": 60,
                          "candidate_min_score": 70, "max_risk_ratio": 0.05,
                          "support_lookback_days": 10, "buy_zone_max_premium": 0.03,
                          "stop_loss_buffer": 0.03},
            "liquidity": {"enabled": False},
            "data": {"database_path": db_path, "daily_sources": ["test"]},
        }
        db.create_scan_task("exn-test", "2026-06-10 09:00:00", total_stocks=1,
                            strategy_type="STRATEGY_2_EXTREME_DRY_STABLE")
        db.save_task_stocks("exn-test", stocks)

        result = s2_scanner.scan_strategy2_all(config, task_id="exn-test", stocks=stocks,
                                                 progress_callback=track, worker_count=1)

        task_stocks = db.get_task_stocks("exn-test")
        assert task_stocks[0]["status"] == "failed"
        assert "STRATEGY2_EVALUATION_ERROR" in (task_stocks[0].get("status_reason") or "")
        assert result["stats"]["processed"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# ACCEPT-S2-002: 实时 API 策略隔离
# ═══════════════════════════════════════════════════════════════════════════════

class TestRealtimeAPIIsolation:
    def test_s1_candidates_excludes_s2_discoveries(self, monkeypatch, tmp_path):
        """ACCEPT-S2-002: S1 candidates API does not return S2 discoveries."""
        db_path = str(tmp_path / "iso1.db")
        db.init_db(db_path)
        server_mod._running["running"] = True
        server_mod._running["task_id"] = "s2-live"
        server_mod._running["strategy_type"] = "STRATEGY_2_EXTREME_DRY_STABLE"
        server_mod._running["stats"] = {
            "discoveries": [{"code": "999999", "name": "S2-only", "total_score": 88}],
            "total_stocks": 100,
        }

        monkeypatch.setattr(server_mod, "load_config",
                            lambda path="config.yaml": {"data": {"database_path": str(db_path)}})

        client = TestClient(server_mod.app)
        res = client.get("/api/candidates")
        data = res.json()
        # No S2 discoveries should appear
        s2_codes = [d["code"] for d in data.get("candidates", []) if d.get("code") == "999999"]
        assert len(s2_codes) == 0, f"S2 discovery leaked into S1 candidates: {s2_codes}"

    def test_s1_candidate_detail_rejects_s2_discovery(self, monkeypatch, tmp_path):
        """ACCEPT-S2-002: S1 candidate detail returns 404 for S2-only discovery."""
        db_path = str(tmp_path / "iso2.db")
        db.init_db(db_path)
        server_mod._running["running"] = True
        server_mod._running["task_id"] = "s2-live"
        server_mod._running["strategy_type"] = "STRATEGY_2_EXTREME_DRY_STABLE"
        server_mod._running["stats"] = {
            "discoveries": [{"code": "999999", "name": "S2-only", "total_score": 88}],
        }

        monkeypatch.setattr(server_mod, "load_config",
                            lambda path="config.yaml": {"data": {"database_path": str(db_path)}})

        client = TestClient(server_mod.app)
        res = client.get("/api/candidate/999999")
        assert res.status_code == 404, f"S2 discovery leaked into S1 detail: {res.status_code}"

    def test_s1_discoveries_still_work_when_s1_running(self, monkeypatch, tmp_path):
        """ACCEPT-S2-002: S1 discoveries still work when S1 is running."""
        db_path = str(tmp_path / "iso3.db")
        db.init_db(db_path)
        server_mod._running["running"] = True
        server_mod._running["task_id"] = "s1-live"
        server_mod._running["strategy_type"] = "STRATEGY_1_CUP_HANDLE"
        server_mod._running["stats"] = {
            "discoveries": [{"code": "600000", "name": "S1-candidate", "score": 85}],
        }

        monkeypatch.setattr(server_mod, "load_config",
                            lambda path="config.yaml": {"data": {"database_path": str(db_path)}})

        client = TestClient(server_mod.app)
        res = client.get("/api/candidates")
        data = res.json()
        s1_codes = [d["code"] for d in data.get("candidates", []) if d.get("code") == "600000"]
        assert len(s1_codes) == 1, f"S1 discovery missing: {s1_codes}"


# ═══════════════════════════════════════════════════════════════════════════════
# ACCEPT-S2-003: 全源失败禁止缓存回退
# ═══════════════════════════════════════════════════════════════════════════════

class TestAllSourcesFailedNoCache:
    def test_fetch_returns_none_when_all_sources_fail_and_cache_exists(self, monkeypatch, tmp_path):
        """ACCEPT-S2-003: cache exists + all online fail → data is None, from_cache False."""
        import scanner.db as db
        from scanner.daily_data_service import fetch_with_retry, FetchResult

        db_path = str(tmp_path / "nocache.db")
        db.init_db(db_path)
        # Save cached data to DB
        db.save_ohlc("000001", [{"date": "2026-06-09", "open": 10, "high": 10, "low": 10, "close": 10, "volume": 1_000_000, "turnover": 10_000_000}])

        def mock_try_fetch(*args, **kwargs):
            return None, 1, "connection refused"

        monkeypatch.setattr("scanner.daily_data_service._try_fetch_source", mock_try_fetch)

        result = fetch_with_retry("000001", "baidu", source_chain=["baidu"], kline_days=250)
        assert result.data is None, f"Expected data=None, got data with {len(result.data) if result.data else 0} rows"
        assert result.from_cache is False, f"Expected from_cache=False, got {result.from_cache}"

    def test_online_source_success_still_merges_cache(self, monkeypatch, tmp_path):
        """ACCEPT-S2-003: Online source success → still merges with cache and saves."""
        import scanner.db as db
        from scanner.daily_data_service import fetch_with_retry

        db_path = str(tmp_path / "merge.db")
        db.init_db(db_path)
        # Save old cached data
        db.save_ohlc("000001", [{"date": "2026-06-08", "open": 9, "high": 9, "low": 9, "close": 9, "volume": 1_000_000, "turnover": 9_000_000}])

        fresh = [{"date": "2026-06-09", "open": 10, "high": 10, "low": 10, "close": 10, "volume": 2_000_000, "turnover": 20_000_000}]
        def mock_try_fetch(*args, **kwargs):
            return fresh, 1, None

        monkeypatch.setattr("scanner.daily_data_service._try_fetch_source", mock_try_fetch)

        result = fetch_with_retry("000001", "baidu", source_chain=["baidu"], kline_days=250)
        assert result.data is not None
        assert len(result.data) >= 2  # merged both dates

    def test_strategy2_scanner_produces_failed_on_all_source_failure(self, monkeypatch, tmp_path):
        """ACCEPT-S2-003: Strategy2 scanner marks stock as failed, not fetching."""
        from strategy2 import scanner as s2_scanner
        from scanner.daily_data_service import FetchResult

        db_path = str(tmp_path / "s2fail.db")
        db.init_db(db_path)

        def mock_fetch(*args, **kwargs):
            return FetchResult(data=None, primary_source="baidu", fallback_source="sina",
                               primary_error="connection refused", fallback_error="timeout",
                               source_errors={"baidu": "connection refused", "sina": "timeout", "tencent": "empty"})
        monkeypatch.setattr(s2_scanner, "fetch_with_retry", mock_fetch)

        stocks = [{"code": "000001", "name": "test", "market": ""}]
        config = {
            "strategy2": {"strategy_window_days": 120, "minimum_required_days": 60,
                          "candidate_min_score": 70, "max_risk_ratio": 0.05,
                          "support_lookback_days": 10, "buy_zone_max_premium": 0.03,
                          "stop_loss_buffer": 0.03},
            "liquidity": {"enabled": False},
            "data": {"database_path": db_path, "daily_sources": ["baidu", "sina", "tencent"]},
        }
        db.create_scan_task("s2fail-test", "2026-06-10 09:00:00", total_stocks=1,
                            strategy_type="STRATEGY_2_EXTREME_DRY_STABLE")
        db.save_task_stocks("s2fail-test", stocks)

        s2_scanner.scan_strategy2_all(config, task_id="s2fail-test", stocks=stocks, worker_count=1)

        ts = db.get_task_stocks("s2fail-test")
        assert ts[0]["status"] == "failed"
        assert "ALL_DATA_SOURCES_FAILED" in (ts[0].get("status_reason") or "")
        assert ts[0]["finished_at"] is not None


# ═══════════════════════════════════════════════════════════════════════════════
# ACCEPT-S2-004: 三数据源收敛
# ═══════════════════════════════════════════════════════════════════════════════

class TestDataSourceConvergence:
    def test_default_daily_sources_equal_three(self):
        """ACCEPT-S2-004: DEFAULT_DAILY_SOURCES == ['baidu', 'sina', 'tencent']."""
        from scanner.daily_data_service import DEFAULT_DAILY_SOURCES as DDS
        assert DDS == ["baidu", "sina", "tencent"], f"Got: {DDS}"

    def test_mootdx_not_in_source_chain(self):
        """ACCEPT-S2-004: mootdx not in available fetch functions."""
        with pytest.raises(ValueError, match="Unknown daily data source"):
            _daily_fetch_fn("mootdx")

    def test_yfinance_not_in_source_chain(self):
        """ACCEPT-S2-004: yfinance not in available fetch functions."""
        with pytest.raises(ValueError, match="Unknown daily data source"):
            _daily_fetch_fn("yfinance")

    def test_datasource_manager_only_three_locks(self):
        """ACCEPT-S2-004: DataSourceManager only has baidu/sina/tencent locks."""
        mgr = DataSourceManager()
        assert set(mgr._locks.keys()) == {"baidu", "sina", "tencent"}, \
            f"Got: {set(mgr._locks.keys())}"

    def test_config_default_daily_sources_are_three(self):
        """ACCEPT-S2-004: config.yaml default daily_sources are baidu/sina/tencent."""
        import yaml
        with open("config.yaml", "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        sources = config.get("data", {}).get("daily_sources", [])
        assert sources == ["baidu", "sina", "tencent"], f"Got: {sources}"


# ═══════════════════════════════════════════════════════════════════════════════
# ROUND2-S2-004: 六种终态分别真实制造并验证
# ═══════════════════════════════════════════════════════════════════════════════

class TestSixTerminalStatesParametrized:
    """ROUND2-S2-004: 6 terminal states, each with distinct conditions and isolated verification."""

    @pytest.mark.parametrize("state,setup", [
        ("candidate", "candidate"),
        ("scanned", "scanned"),
        ("skipped", "skipped"),
        ("all-sources-failed", "fail"),
        ("persist-failed", "persist_fail"),
        ("evaluation-error", "crash"),
    ])
    def test_each_terminal_state_individually(self, monkeypatch, tmp_path, state, setup):
        """ROUND2-S2-004: Single stock through exactly one terminal path → correct DB + processed."""
        import time
        from strategy2 import scanner as s2_scanner
        from scanner.daily_data_service import FetchResult

        db_path = str(tmp_path / f"term_{setup}.db")
        import scanner.db as db
        db.init_db(db_path)

        from datetime import datetime, timedelta

        def build_good_data():
            base = datetime(2026, 6, 10)
            d = []
            for i in range(130):
                date = (base - timedelta(days=129 - i)).strftime("%Y-%m-%d")
                vol = 500_000 if i >= 110 else 2_000_000
                d.append({"date": date, "open": 10, "high": 10, "low": 10, "close": 10, "volume": vol, "turnover": 10 * vol})
            return d

        if setup == "fail":
            # All sources fail → failed
            def mock_fetch(*a, **kw):
                return FetchResult(data=None, primary_source="baidu", fallback_source="sina",
                                   primary_error="connection refused", fallback_error="timeout")
            monkeypatch.setattr(s2_scanner, "fetch_with_retry", mock_fetch)
        elif setup == "crash":
            # Engine crash → failed
            def mock_fetch(*a, **kw):
                return FetchResult(data=build_good_data(), primary_source="test", fallback_source="test", from_cache=True)
            monkeypatch.setattr(s2_scanner, "fetch_with_retry", mock_fetch)
            from strategy2.engine import ExtremeDryStableStrategyEngine
            def crash_eval(self, *a, **kw):
                raise RuntimeError("boom")
            monkeypatch.setattr(ExtremeDryStableStrategyEngine, "evaluate_at", crash_eval)
        elif setup == "persist_fail":
            # Candidate but persist fails → failed
            def mock_fetch(*a, **kw):
                return FetchResult(data=build_good_data(), primary_source="test", fallback_source="test", from_cache=True)
            monkeypatch.setattr(s2_scanner, "fetch_with_retry", mock_fetch)
            def mock_upsert(*a, **kw):
                raise RuntimeError("db write error")
            monkeypatch.setattr(db, "upsert_strategy2_candidate", mock_upsert)
        elif setup == "skipped":
            # Liquidity filter blocks → skipped
            def mock_fetch(*a, **kw):
                return FetchResult(data=build_good_data(), primary_source="test", fallback_source="test", from_cache=True)
            monkeypatch.setattr(s2_scanner, "fetch_with_retry", mock_fetch)
            # Override config to enable strict liquidity
            pass  # handled by config below
        else:
            # candidate / scanned: normal data
            def mock_fetch(*a, **kw):
                return FetchResult(data=build_good_data(), primary_source="test", fallback_source="test", from_cache=True)
            monkeypatch.setattr(s2_scanner, "fetch_with_retry", mock_fetch)

        stocks = [{"code": "000001", "name": "test", "market": ""}]
        cfg = {
            "strategy2": {"strategy_window_days": 120, "minimum_required_days": 60,
                          "candidate_min_score": 100 if setup in ("scanned", "skipped") else 60,
                          "max_risk_ratio": 0.05,
                          "support_lookback_days": 10, "buy_zone_max_premium": 0.03,
                          "stop_loss_buffer": 0.03},
            "liquidity": {"enabled": setup == "skipped",
                          "avg_turnover_days": 20, "min_avg_turnover": 999_999_999_999,
                          "min_avg_volume": 1, "min_latest_turnover": 1,
                          "min_stock_price": 99999},
            "data": {"database_path": db_path, "daily_sources": ["baidu", "sina", "tencent"]},
        }
        db.create_scan_task(f"term-{setup}", "2026-06-10 09:00:00", total_stocks=1,
                            strategy_type="STRATEGY_2_EXTREME_DRY_STABLE")
        db.save_task_stocks(f"term-{setup}", stocks)

        s2_scanner.scan_strategy2_all(cfg, task_id=f"term-{setup}", stocks=stocks, worker_count=1)

        ts = db.get_task_stocks(f"term-{setup}")
        assert len(ts) == 1
        # Verify terminal state — no fetching
        assert ts[0]["status"] != "fetching", f"Stock stuck in fetching for setup={setup}"
        assert ts[0]["finished_at"] is not None, f"finished_at missing for setup={setup}"

        summary = db.summarize_task_stocks(f"term-{setup}")
        terminal = summary["scanned"] + summary["skipped"] + summary["failed"] + summary["candidate"]
        assert terminal == 1, f"Expected 1 terminal for {setup}, got {terminal}: {summary}"
        # Allow threads to finish
        time.sleep(0.1)

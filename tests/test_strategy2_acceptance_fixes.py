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
    def test_fetch_reuses_fresh_cache_without_calling_sources(self, monkeypatch, tmp_path):
        """Fresh local OHLC for the target date should skip online sources."""
        import scanner.db as db
        from scanner.daily_data_service import fetch_with_retry

        db_path = str(tmp_path / "fresh_cache.db")
        db.init_db(db_path)
        rows = [
            {"date": f"2026-06-{day:02d}", "open": 10, "high": 10, "low": 10,
             "close": 10, "volume": 1_000_000, "turnover": 10_000_000}
            for day in range(1, 11)
        ]
        db.save_ohlc("000001", rows)

        calls = []

        def mock_try_fetch(*args, **kwargs):
            calls.append(args)
            return None, 1, "should not be called"

        monkeypatch.setattr("scanner.daily_data_service._try_fetch_source", mock_try_fetch)

        result = fetch_with_retry(
            "000001",
            "baidu",
            source_chain=["baidu", "sina"],
            kline_days=5,
            cache_fresh_date="2026-06-10",
        )

        assert result.data == rows[-5:]
        assert result.from_cache is True
        assert result.primary_source == "cache"
        assert result.fallback_source == "cache"
        assert calls == []

    def test_fetch_reuses_fresh_cache_even_when_rows_are_less_than_kline_days(self, monkeypatch, tmp_path):
        """Same-day local OHLC should skip online sources even if history is short."""
        import scanner.db as db
        from scanner.daily_data_service import fetch_with_retry

        db_path = str(tmp_path / "fresh_cache_short.db")
        db.init_db(db_path)
        rows = [
            {"date": "2026-06-10", "open": 10, "high": 10, "low": 10,
             "close": 10, "volume": 1_000_000, "turnover": 10_000_000}
        ]
        db.save_ohlc("000001", rows)

        calls = []

        def mock_try_fetch(*args, **kwargs):
            calls.append(args)
            return None, 1, "connection refused"

        monkeypatch.setattr("scanner.daily_data_service._try_fetch_source", mock_try_fetch)

        result = fetch_with_retry(
            "000001",
            "baidu",
            source_chain=["baidu"],
            kline_days=5,
            cache_fresh_date="2026-06-10",
        )

        assert result.data == rows
        assert result.from_cache is True
        assert calls == []

    def test_strategy2_scan_passes_existing_today_stock_latest_trade_date_to_fetch(self, monkeypatch, tmp_path):
        """Strategy2 should reuse a same-stock latest date recorded by today's prior scan."""
        from strategy2 import scanner as s2_scanner
        from scanner.daily_data_service import FetchResult
        import scanner.db as db

        db_path = str(tmp_path / "s2_same_day_reuse.db")
        db.init_db(db_path)
        db.create_scan_task("prior-s1", "2026-06-15 09:30:00", total_stocks=1,
                            strategy_type="STRATEGY_1_CUP_HANDLE")
        db.save_task_stocks("prior-s1", [{"code": "000001", "name": "Prior"}])
        db.update_task_stock(
            "prior-s1",
            "000001",
            status="scanned",
            kline_latest_date="2026-06-15",
            kline_fetched_at="2026-06-15 15:12:00",
            kline_target_trade_date="2026-06-15",
            finished_at="2026-06-15 15:12:00",
        )
        db.refresh_scan_task_counts("prior-s1")
        db.finish_scan_task("prior-s1", "2026-06-15 09:32:00", 0, 2.0, scanned=1, skipped=0)

        seen = []

        def mock_fetch(*args, freshness_context=None, **kwargs):
            seen.append({
                "target": freshness_context.target_trade_date if freshness_context else None,
                "min_fetch_time": freshness_context.min_fetch_time if freshness_context else None,
                "fetched_at": freshness_context.fetched_at if freshness_context else None,
            })
            return FetchResult(data=None, primary_source="baidu", fallback_source="baidu")

        original_strftime = s2_scanner.time.strftime

        def fake_strftime(fmt, *args):
            if args:
                return original_strftime(fmt, *args)
            if fmt == "%Y%m%d-%H%M%S":
                return "20260615-100000"
            if fmt == "%Y-%m-%d %H:%M:%S":
                return "2026-06-15 15:15:00"
            if fmt == "%Y-%m-%d":
                return "2026-06-15"
            return original_strftime(fmt)

        monkeypatch.setattr(s2_scanner, "fetch_with_retry", mock_fetch)
        monkeypatch.setattr(s2_scanner.time, "strftime", fake_strftime)

        stocks = [{"code": "000001", "name": "test", "market": ""}]
        cfg = {"strategy2": {"strategy_window_days": 120, "minimum_required_days": 60,
                             "candidate_min_score": 70, "max_risk_ratio": 0.05,
                             "support_lookback_days": 10, "buy_zone_max_premium": 0.03,
                             "stop_loss_buffer": 0.03},
               "liquidity": {"enabled": False, "min_listing_days": 350},
               "data": {"database_path": db_path, "daily_sources": ["baidu"], "worker_count": 1}}
        db.create_scan_task("current-s2", "2026-06-15 10:00:00", total_stocks=1,
                            strategy_type="STRATEGY_2_EXTREME_DRY_STABLE")
        db.save_task_stocks("current-s2", stocks)

        s2_scanner.scan_strategy2_all(cfg, task_id="current-s2", stocks=stocks, worker_count=1)

        assert seen == [{
            "target": "2026-06-15",
            "min_fetch_time": "2026-06-15 15:00:00",
            "fetched_at": "2026-06-15 15:12:00",
        }]

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
# ACCEPT-S2-004: 四数据源收敛 (baidu/sina/tencent/yfinance)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDataSourceConvergence:
    def test_default_daily_sources_equal_four(self):
        """DEFAULT_DAILY_SOURCES == ['baidu', 'sina', 'tencent', 'yfinance']."""
        from scanner.daily_data_service import DEFAULT_DAILY_SOURCES as DDS
        assert DDS == ["baidu", "sina", "tencent", "yfinance"], f"Got: {DDS}"

    def test_mootdx_not_in_source_chain(self):
        """ACCEPT-S2-004: mootdx not in available fetch functions."""
        with pytest.raises(ValueError, match="Unknown daily data source"):
            _daily_fetch_fn("mootdx")

    def test_yfinance_in_source_chain(self):
        """yfinance is now back in available fetch functions."""
        fn = _daily_fetch_fn("yfinance")
        assert fn is not None

    def test_datasource_manager_has_four_locks(self):
        """DataSourceManager has baidu/sina/tencent/yfinance locks."""
        mgr = DataSourceManager()
        assert set(mgr._locks.keys()) == {"baidu", "sina", "tencent", "yfinance"}, \
            f"Got: {set(mgr._locks.keys())}"

    def test_config_default_daily_sources_are_four(self):
        """config.yaml default daily_sources are baidu/sina/tencent/yfinance."""
        import yaml
        with open("config.yaml", "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        sources = config.get("data", {}).get("daily_sources", [])
        assert sources == ["baidu", "sina", "tencent", "yfinance"], f"Got: {sources}"


# ═══════════════════════════════════════════════════════════════════════════════
# Step 5: 源诊断精确测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestSourceDiagnostics:
    def test_all_sources_failed_persists_full_diagnostics(self, monkeypatch, tmp_path):
        """Step 5: All sources fail → all diagnostic fields persisted."""
        from strategy2 import scanner as s2_scanner
        from scanner.daily_data_service import FetchResult
        db_path = str(tmp_path / "diag1.db")
        import scanner.db as db
        db.init_db(db_path)

        expected_errs = {"baidu": "attempts=2 error=timeout", "sina": "attempts=2 error=456", "tencent": "attempts=2 error=empty"}
        def mock_fetch(*a, **kw):
            return FetchResult(data=None, primary_source="baidu", fallback_source="tencent",
                               primary_attempts=2, fallback_attempts=2,
                               primary_error="timeout", fallback_error="empty",
                               source_errors=expected_errs)
        monkeypatch.setattr(s2_scanner, "fetch_with_retry", mock_fetch)

        stocks = [{"code": "000001", "name": "test", "market": ""}]
        cfg = {"strategy2": {"strategy_window_days": 120, "minimum_required_days": 60, "candidate_min_score": 70, "max_risk_ratio": 0.05, "support_lookback_days": 10, "buy_zone_max_premium": 0.03, "stop_loss_buffer": 0.03}, "liquidity": {"enabled": False}, "data": {"database_path": db_path, "daily_sources": ["baidu", "sina", "tencent"]}}
        db.create_scan_task("diag-test", "2026-06-10 09:00:00", total_stocks=1, strategy_type="STRATEGY_2_EXTREME_DRY_STABLE")
        db.save_task_stocks("diag-test", stocks)

        s2_scanner.scan_strategy2_all(cfg, task_id="diag-test", stocks=stocks, worker_count=1)
        ts = db.get_task_stocks("diag-test")
        row = ts[0]
        assert row["status"] == "failed"
        assert row["status_reason"] == "ALL_DATA_SOURCES_FAILED"
        assert row["primary_source"] == "baidu"
        assert row["fallback_source"] == "tencent"
        assert row["primary_attempts"] == 2
        assert row["fallback_attempts"] == 2
        assert row["primary_error"] == "timeout"
        assert row["fallback_error"] == "empty"
        assert row["source_errors"] is not None
        import json
        parsed = json.loads(row["source_errors"])
        assert parsed == expected_errs

    def test_busy_exceeded_persists_diagnostics(self, monkeypatch, tmp_path):
        """ROUND5-S2-004: Busy exceeded → exact status_reason + all diagnostic fields."""
        from strategy2 import scanner as s2_scanner
        from scanner.daily_data_service import FetchResult
        db_path = str(tmp_path / "diag2.db")
        import scanner.db as db
        db.init_db(db_path)

        expected_src_errs = {"baidu": "busy", "sina": "busy", "tencent": "busy"}
        def mock_fetch(*a, **kw):
            return FetchResult(data=None, primary_source="baidu", fallback_source="sina",
                               primary_error="data source busy", fallback_error="data source busy",
                               source_errors=expected_src_errs)
        monkeypatch.setattr(s2_scanner, "fetch_with_retry", mock_fetch)

        stocks = [{"code": "000001", "name": "test", "market": ""}]
        cfg = {"strategy2": {"strategy_window_days": 120, "minimum_required_days": 60, "candidate_min_score": 70, "max_risk_ratio": 0.05, "support_lookback_days": 10, "buy_zone_max_premium": 0.03, "stop_loss_buffer": 0.03}, "liquidity": {"enabled": False}, "data": {"database_path": db_path, "daily_sources": ["baidu", "sina", "tencent"], "source_busy_max_retries": 0}}
        db.create_scan_task("busy-test", "2026-06-10 09:00:00", total_stocks=1, strategy_type="STRATEGY_2_EXTREME_DRY_STABLE")
        db.save_task_stocks("busy-test", stocks)

        s2_scanner.scan_strategy2_all(cfg, task_id="busy-test", stocks=stocks, worker_count=1)
        ts = db.get_task_stocks("busy-test")
        row = ts[0]
        assert row["status"] == "failed"
        assert row["status_reason"] == "数据源忙，超过重试次数"
        assert row["primary_source"] == "baidu"
        assert row["fallback_source"] == "sina"
        assert row["primary_error"] == "data source busy"
        assert row["fallback_error"] == "data source busy"
        import json
        assert json.loads(row["source_errors"]) == expected_src_errs
        assert row["finished_at"] is not None

    def test_fetch_exception_produces_eval_error(self, monkeypatch, tmp_path):
        """Step 5: fetch_with_retry throws → STRATEGY2_EVALUATION_ERROR, no UnboundLocalError."""
        from strategy2 import scanner as s2_scanner
        db_path = str(tmp_path / "diag3.db")
        import scanner.db as db
        db.init_db(db_path)

        def mock_fetch_crash(*a, **kw):
            raise RuntimeError("network unreachable")
        monkeypatch.setattr(s2_scanner, "fetch_with_retry", mock_fetch_crash)

        stocks = [{"code": "000001", "name": "test", "market": ""}]
        cfg = {"strategy2": {"strategy_window_days": 120, "minimum_required_days": 60, "candidate_min_score": 70, "max_risk_ratio": 0.05, "support_lookback_days": 10, "buy_zone_max_premium": 0.03, "stop_loss_buffer": 0.03}, "liquidity": {"enabled": False}, "data": {"database_path": db_path, "daily_sources": ["baidu", "sina", "tencent"]}}
        db.create_scan_task("crash-fetch", "2026-06-10 09:00:00", total_stocks=1, strategy_type="STRATEGY_2_EXTREME_DRY_STABLE")
        db.save_task_stocks("crash-fetch", stocks)

        s2_scanner.scan_strategy2_all(cfg, task_id="crash-fetch", stocks=stocks, worker_count=1)
        ts = db.get_task_stocks("crash-fetch")
        row = ts[0]
        assert row["status"] == "failed"
        assert row["status_reason"] == "STRATEGY2_EVALUATION_ERROR"
        assert row["finished_at"] is not None

    def test_candidate_status_reason_is_none(self, monkeypatch, tmp_path):
        """Step 5: Candidate explicitly has status_reason is None."""
        from strategy2 import scanner as s2_scanner
        from scanner.daily_data_service import FetchResult
        db_path = str(tmp_path / "diag4.db")
        import scanner.db as db
        db.init_db(db_path)

        from datetime import datetime, timedelta
        base = datetime(2026, 6, 10)
        good = []
        for i in range(130):
            date = (base - timedelta(days=129 - i)).strftime("%Y-%m-%d")
            vol = 500_000 if i >= 110 else 2_000_000
            good.append({"date": date, "open": 10, "high": 10, "low": 10, "close": 10, "volume": vol, "turnover": 10*vol})

        def mock_fetch(*a, **kw):
            return FetchResult(data=list(good), primary_source="test", fallback_source="test", from_cache=True)
        monkeypatch.setattr(s2_scanner, "fetch_with_retry", mock_fetch)

        stocks = [{"code": "000001", "name": "test", "market": ""}]
        cfg = {"strategy2": {"strategy_window_days": 120, "minimum_required_days": 60, "candidate_min_score": 60, "max_risk_ratio": 0.05, "support_lookback_days": 10, "buy_zone_max_premium": 0.03, "stop_loss_buffer": 0.03}, "liquidity": {"enabled": False}, "data": {"database_path": db_path, "daily_sources": ["baidu", "sina", "tencent"]}}
        db.create_scan_task("cand-null", "2026-06-10 09:00:00", total_stocks=1, strategy_type="STRATEGY_2_EXTREME_DRY_STABLE")
        db.save_task_stocks("cand-null", stocks)

        s2_scanner.scan_strategy2_all(cfg, task_id="cand-null", stocks=stocks, worker_count=1)
        ts = db.get_task_stocks("cand-null")
        row = ts[0]
        assert row["status"] == "candidate"
        assert row["status_reason"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# Stage 1: Task stocks API 404 semantics
# ═══════════════════════════════════════════════════════════════════════════════

class TestTaskStocksAPI:
    def test_unknown_task_returns_404(self, monkeypatch, tmp_path):
        """Stage 1: Unknown task → 404 TASK_NOT_FOUND."""
        from fastapi.testclient import TestClient
        import server as server_mod
        db_path = str(tmp_path / "ts1.db")
        import scanner.db as db
        db.init_db(db_path)
        server_mod._running["running"] = False
        monkeypatch.setattr(server_mod, "load_config",
                            lambda path="config.yaml": {"data": {"database_path": db_path}})
        client = TestClient(server_mod.app)
        res = client.get("/api/scan/tasks/not-found/stocks")
        assert res.status_code == 404
        assert res.json()["error"] == "TASK_NOT_FOUND"

    def test_legacy_null_type_returns_s1(self, monkeypatch, tmp_path):
        """Stage 1: NULL strategy_type → STRATEGY_1_CUP_HANDLE."""
        from fastapi.testclient import TestClient
        import server as server_mod
        db_path = str(tmp_path / "ts2.db")
        import scanner.db as db
        db.init_db(db_path)
        db.create_scan_task("null-task", "2026-06-10 09:00:00")
        conn = db.get_conn()
        conn.execute("UPDATE scan_tasks SET strategy_type=NULL WHERE id='null-task'")
        conn.commit()
        monkeypatch.setattr(server_mod, "load_config",
                            lambda path="config.yaml": {"data": {"database_path": db_path}})
        client = TestClient(server_mod.app)
        res = client.get("/api/scan/tasks/null-task/stocks")
        assert res.status_code == 200
        assert res.json()["strategy_type"] == "STRATEGY_1_CUP_HANDLE"

    def test_s2_task_returns_s2(self, monkeypatch, tmp_path):
        """Stage 1: S2 task → STRATEGY_2_EXTREME_DRY_STABLE."""
        from fastapi.testclient import TestClient
        import server as server_mod
        db_path = str(tmp_path / "ts3.db")
        import scanner.db as db
        db.init_db(db_path)
        db.create_scan_task("s2-ts", "2026-06-10 09:00:00",
                            strategy_type="STRATEGY_2_EXTREME_DRY_STABLE")
        monkeypatch.setattr(server_mod, "load_config",
                            lambda path="config.yaml": {"data": {"database_path": db_path}})
        client = TestClient(server_mod.app)
        res = client.get("/api/scan/tasks/s2-ts/stocks")
        assert res.status_code == 200
        assert res.json()["strategy_type"] == "STRATEGY_2_EXTREME_DRY_STABLE"

    def test_empty_failure_list_not_404(self, monkeypatch, tmp_path):
        """Stage 1: Valid task, no failures → 200 + empty + total=0."""
        from fastapi.testclient import TestClient
        import server as server_mod
        db_path = str(tmp_path / "ts4.db")
        import scanner.db as db
        db.init_db(db_path)
        db.create_scan_task("empty-ts", "2026-06-10 09:00:00")
        monkeypatch.setattr(server_mod, "load_config",
                            lambda path="config.yaml": {"data": {"database_path": db_path}})
        client = TestClient(server_mod.app)
        res = client.get("/api/scan/tasks/empty-ts/stocks?status=failed")
        assert res.status_code == 200
        assert res.json()["stocks"] == []
        assert res.json()["total"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# ROUND2-S2-004: 六种终态分别真实制造并验证
# ═══════════════════════════════════════════════════════════════════════════════

class TestSixTerminalStatesParametrized:
    """Stage 4: 6 terminal states with exact expected status and reason."""

    @pytest.mark.parametrize(
        "setup,expected_status,expected_reason",
        [
            ("candidate", "candidate", None),
            ("scanned", "scanned", "SCORE_BELOW_THRESHOLD"),
            ("skipped", "skipped", "LIQUIDITY_FILTER_REJECTED"),
            ("fail", "failed", "ALL_DATA_SOURCES_FAILED"),
            ("persist_fail", "failed", "STRATEGY2_CANDIDATE_PERSIST_FAILED"),
            ("crash", "failed", "STRATEGY2_EVALUATION_ERROR"),
        ],
    )
    def test_each_terminal_state_individually(self, monkeypatch, tmp_path, setup, expected_status, expected_reason):
        """Stage 4: Single stock, distinct terminal path → exact status + reason + callback."""
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

        events = []
        def on_progress(stage, current, total, detail, discovery=None):
            events.append({"stage": stage, "current": current, "total": total, "detail": detail, "discovery": discovery})

        if setup == "fail":
            def mock_fetch(*a, **kw):
                return FetchResult(data=None, primary_source="baidu", fallback_source="tencent",
                                   primary_attempts=2, fallback_attempts=2,
                                   primary_error="baidu failed", fallback_error="tencent failed",
                                   source_errors={"baidu": "a=2 e=baidu failed", "sina": "a=2 e=sina failed", "tencent": "a=2 e=tencent failed"})
            monkeypatch.setattr(s2_scanner, "fetch_with_retry", mock_fetch)
        elif setup == "crash":
            def mock_fetch(*a, **kw):
                return FetchResult(data=build_good_data(), primary_source="test", fallback_source="test", from_cache=True)
            monkeypatch.setattr(s2_scanner, "fetch_with_retry", mock_fetch)
            from strategy2.engine import ExtremeDryStableStrategyEngine
            def crash_eval(self, *a, **kw):
                raise RuntimeError("boom")
            monkeypatch.setattr(ExtremeDryStableStrategyEngine, "evaluate_at", crash_eval)
        elif setup == "persist_fail":
            def mock_fetch(*a, **kw):
                return FetchResult(data=build_good_data(), primary_source="test", fallback_source="test", from_cache=True)
            monkeypatch.setattr(s2_scanner, "fetch_with_retry", mock_fetch)
            def mock_upsert(*a, **kw):
                raise RuntimeError("db write error")
            monkeypatch.setattr(db, "upsert_strategy2_candidate", mock_upsert)
        else:
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

        s2_scanner.scan_strategy2_all(cfg, task_id=f"term-{setup}", stocks=stocks,
                                       progress_callback=on_progress, worker_count=1)

        ts = db.get_task_stocks(f"term-{setup}")
        assert len(ts) == 1
        row = ts[0]
        assert row["status"] == expected_status, f"Expected {expected_status}, got {row['status']}"
        if expected_reason is not None:
            assert row["status_reason"] == expected_reason, \
                f"Expected reason {expected_reason}, got {row['status_reason']}"
        assert row["finished_at"] is not None

        summary = db.summarize_task_stocks(f"term-{setup}")
        assert summary[expected_status] == 1
        for other in {"candidate", "scanned", "skipped", "failed"} - {expected_status}:
            assert summary[other] == 0, f"{other} should be 0 for {setup}"

        scanning_events = [e for e in events if e["stage"] == "scanning"]
        assert len(scanning_events) == 1, f"Expected 1 scanning event, got {len(scanning_events)}"
        assert scanning_events[0]["current"] == 1
        assert scanning_events[0]["total"] == 1

        discovery_events = [e for e in events if e["stage"] == "discovery"]
        if expected_status == "candidate":
            assert len(discovery_events) == 1
        else:
            assert len(discovery_events) == 0, f"No discovery expected for {setup}"

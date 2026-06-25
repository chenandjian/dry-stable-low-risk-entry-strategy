import scanner.db as db
import server as server_mod
import threading
from fastapi.testclient import TestClient
from scanner.daily_data_service import FetchResult
from strategy3.models import Strategy3Evaluation, Strategy3Indicators, Strategy3Risk
from strategy3.scanner import _build_strategy3_discovery, re_evaluate_strategy3_task, scan_strategy3_all
from tests.test_strategy3_engine import make_strategy3_candidate_bars


def test_strategy3_candidate_table_roundtrip(tmp_path):
    db.init_db(str(tmp_path / "test.db"))
    db.create_scan_task(
        "s3-task",
        "2026-06-25 15:30:00",
        strategy_type="STRATEGY_3_STRONG_PULLBACK_SECOND_BREAKOUT",
    )

    db.upsert_strategy3_candidate("s3-task", {
        "code": "000001",
        "name": "平安银行",
        "evaluation_date": "2026-06-25",
        "total_score": 86,
        "level": "核心候选",
        "trend_score": 25,
        "pullback_score": 20,
        "volume_stability_score": 16,
        "second_breakout_score": 12,
        "risk_reward_score": 13,
        "current_close": 10.0,
        "ma5": 10.1,
        "ma10": 10.0,
        "ma20": 9.8,
        "ma60": 9.2,
        "ma120": 8.5,
        "recent_high": 11.5,
        "pullback_pct": 0.13,
        "relative_strength_60": 0.10,
        "volume_ratio_5_20": 0.70,
        "range_5": 0.04,
        "close_range_5": 0.03,
        "support_price": 9.5,
        "stop_loss": 9.31,
        "target_1": 12.0,
        "risk_ratio": 0.04,
        "rr1": 2.2,
        "score_reasons": ["强趋势"],
        "reject_reasons": [],
    })

    rows = db.get_strategy3_candidates(task_id="s3-task")
    assert len(rows) == 1
    assert rows[0]["code"] == "000001"
    assert rows[0]["score_reasons"] == ["强趋势"]
    assert rows[0]["reject_reasons"] == []


def test_strategy3_candidates_do_not_leak_into_strategy1_or_strategy2_tables(tmp_path):
    db.init_db(str(tmp_path / "test.db"))
    db.create_scan_task(
        "s3-task",
        "2026-06-25 15:30:00",
        strategy_type="STRATEGY_3_STRONG_PULLBACK_SECOND_BREAKOUT",
    )
    db.upsert_strategy3_candidate("s3-task", {
        "code": "000001",
        "name": "平安银行",
        "evaluation_date": "2026-06-25",
        "total_score": 80,
        "level": "观察候选",
    })

    assert db.get_candidates(task_id="s3-task") == []
    assert db.get_strategy2_candidates(task_id="s3-task") == []


def test_get_strategy3_candidate_by_code(tmp_path):
    db.init_db(str(tmp_path / "test.db"))
    db.create_scan_task(
        "s3-task",
        "2026-06-25 15:30:00",
        strategy_type="STRATEGY_3_STRONG_PULLBACK_SECOND_BREAKOUT",
    )
    db.upsert_strategy3_candidate("s3-task", {
        "code": "000001",
        "name": "平安银行",
        "evaluation_date": "2026-06-25",
        "total_score": 80,
        "level": "观察候选",
    })

    row = db.get_strategy3_candidate("000001", task_id="s3-task")
    assert row["code"] == "000001"
    assert row["level"] == "观察候选"


def test_build_strategy3_discovery_contains_frontend_fields():
    ev = Strategy3Evaluation(
        passed=True,
        code="000001",
        name="平安银行",
        evaluation_date="2026-06-25",
        total_score=88,
        level="核心候选",
        current_close=10.0,
        trend_score=25,
        pullback_score=20,
        volume_stability_score=18,
        second_breakout_score=12,
        risk_reward_score=13,
        indicators=Strategy3Indicators(
            ma5=10.1,
            ma10=10.0,
            ma20=9.8,
            ma60=9.2,
            ma120=8.5,
            recent_high=11.5,
            pullback_pct=0.15,
            relative_strength_60=0.12,
            volume_ratio_5_20=0.7,
            range_5=0.04,
            close_range_5=0.03,
        ),
        risk=Strategy3Risk(
            support_price=9.5,
            stop_loss=9.31,
            target_1=12.0,
            risk_ratio=0.069,
            rr1=2.9,
            structural_support=8.8,
            structural_stop_loss=8.62,
            structural_risk_ratio=0.138,
            tactical_support=9.5,
            tactical_stop_loss=9.31,
            tactical_risk_ratio=0.069,
            tactical_rr1=2.9,
            support_quality="ma20",
        ),
        score_reasons=["强趋势"],
    )

    d = _build_strategy3_discovery(ev)

    assert d["total_score"] == 88
    assert d["pullback_pct"] == 0.15
    assert d["risk_ratio"] == 0.069
    assert d["rr1"] == 2.9
    assert d["trend_score"] == 25
    assert d["structural_support"] == 8.8
    assert d["tactical_support"] == 9.5
    assert d["tactical_risk_ratio"] == 0.069
    assert d["support_quality"] == "ma20"


def test_strategy3_candidate_table_roundtrip_tactical_and_structural_risk(tmp_path):
    db.init_db(str(tmp_path / "test.db"))
    db.create_scan_task(
        "s3-task",
        "2026-06-25 15:30:00",
        strategy_type="STRATEGY_3_STRONG_PULLBACK_SECOND_BREAKOUT",
    )

    db.upsert_strategy3_candidate("s3-task", {
        "code": "000001",
        "name": "平安银行",
        "evaluation_date": "2026-06-25",
        "total_score": 86,
        "level": "核心候选",
        "support_price": 9.5,
        "stop_loss": 9.31,
        "target_1": 12.0,
        "risk_ratio": 0.069,
        "rr1": 2.9,
        "structural_support": 8.8,
        "structural_stop_loss": 8.62,
        "structural_risk_ratio": 0.138,
        "tactical_support": 9.5,
        "tactical_stop_loss": 9.31,
        "tactical_risk_ratio": 0.069,
        "tactical_rr1": 2.9,
        "support_quality": "ma20",
    })

    row = db.get_strategy3_candidates(task_id="s3-task")[0]

    assert row["structural_support"] == 8.8
    assert row["structural_risk_ratio"] == 0.138
    assert row["tactical_support"] == 9.5
    assert row["tactical_risk_ratio"] == 0.069
    assert row["support_quality"] == "ma20"


def test_re_evaluate_strategy3_task_uses_cached_ohlc(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    monkeypatch.setattr("strategy3.scanner.fetch_market_index_daily", lambda symbol=None: [])
    db.create_scan_task(
        "s3-task",
        "2026-06-25 15:30:00",
        strategy_type="STRATEGY_3_STRONG_PULLBACK_SECOND_BREAKOUT",
    )
    db.save_task_stocks("s3-task", [{"code": "000001", "name": "平安银行", "market": "SZ"}])
    db.save_ohlc("000001", make_strategy3_candidate_bars())

    result = re_evaluate_strategy3_task({
        "data": {"database_path": db_path},
        "liquidity": {
            "enabled": False,
            "min_listing_days": 350,
            "min_avg_turnover": 0,
            "min_avg_volume": 0,
            "min_latest_turnover": 0,
            "min_stock_price": 0,
        },
        "strategy3": {"strategy_window_days": 250, "minimum_required_days": 180},
    }, "s3-task")

    assert result["status"] == "completed"
    assert result["candidates_found"] == 1
    rows = db.get_strategy3_candidates(task_id="s3-task")
    assert rows[0]["code"] == "000001"
    task_stock = db.get_task_stocks("s3-task", limit=1)[0]
    assert task_stock["status"] == "candidate"
    summary = db.refresh_scan_task_counts("s3-task")
    assert summary["candidates_count"] == 1


def test_scan_strategy3_all_passes_truncated_market_data(monkeypatch, tmp_path):
    import strategy3.scanner as s3_scanner

    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    db.create_scan_task(
        "s3-task",
        "2026-06-25 15:30:00",
        strategy_type="STRATEGY_3_STRONG_PULLBACK_SECOND_BREAKOUT",
    )
    stocks = [{"code": "000001", "name": "平安银行", "market": "SZ"}]
    db.save_task_stocks("s3-task", stocks)
    data = make_strategy3_candidate_bars()
    data[-1]["date"] = "2026-06-25"
    market_full = [
        {"date": "2026-06-24", "open": 10, "high": 10, "low": 10, "close": 10, "volume": 1},
        {"date": "2026-06-25", "open": 10, "high": 10, "low": 10, "close": 11, "volume": 1},
        {"date": "2026-06-26", "open": 10, "high": 10, "low": 10, "close": 99, "volume": 1},
    ]
    calls = []

    monkeypatch.setattr(
        s3_scanner,
        "fetch_with_retry",
        lambda *args, **kwargs: FetchResult(
            data=data,
            primary_source="cache",
            fallback_source="cache",
            from_cache=True,
        ),
    )
    monkeypatch.setattr(s3_scanner, "fetch_market_index_daily", lambda symbol=None: list(market_full), raising=False)

    class FakeEngine:
        def __init__(self, config):
            pass

        def evaluate_at(self, rows, *, code="", name="", market_data=None):
            calls.append([row["date"] for row in (market_data or [])])
            return Strategy3Evaluation(
                False,
                code=code,
                name=name,
                evaluation_date=rows[-1]["date"],
                status_reason="SCORE_BELOW_THRESHOLD",
            )

    monkeypatch.setattr(s3_scanner, "StrongPullbackSecondBreakoutEngine", FakeEngine)

    scan_strategy3_all(
        {
            "data": {"database_path": db_path, "daily_sources": ["cache"], "worker_count": 1},
            "liquidity": {"enabled": False, "min_listing_days": 350},
            "market_environment": {"index_symbol": "sh000001"},
            "strategy3": {"strategy_window_days": 250, "minimum_required_days": 180},
        },
        task_id="s3-task",
        stocks=stocks,
        worker_count=1,
    )

    assert calls == [["2026-06-24", "2026-06-25"]]


def test_scan_strategy3_all_marks_fallback_when_market_data_misses_evaluation_date(monkeypatch, tmp_path):
    import json
    import strategy3.scanner as s3_scanner

    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    db.create_scan_task(
        "s3-task",
        "2026-06-25 15:30:00",
        strategy_type="STRATEGY_3_STRONG_PULLBACK_SECOND_BREAKOUT",
    )
    stocks = [{"code": "000001", "name": "平安银行", "market": "SZ"}]
    db.save_task_stocks("s3-task", stocks)
    data = make_strategy3_candidate_bars()
    data[-1]["date"] = "2026-06-25"

    monkeypatch.setattr(
        s3_scanner,
        "fetch_with_retry",
        lambda *args, **kwargs: FetchResult(
            data=data,
            primary_source="cache",
            fallback_source="cache",
            from_cache=True,
        ),
    )
    monkeypatch.setattr(
        s3_scanner,
        "fetch_market_index_daily",
        lambda symbol=None: [
            {"date": "2026-06-24", "open": 10, "high": 10, "low": 10, "close": 10, "volume": 1},
        ],
        raising=False,
    )

    class FakeEngine:
        def __init__(self, config):
            pass

        def evaluate_at(self, rows, *, code="", name="", market_data=None):
            assert market_data == []
            return Strategy3Evaluation(
                False,
                code=code,
                name=name,
                evaluation_date=rows[-1]["date"],
                status_reason="SCORE_BELOW_THRESHOLD",
            )

    monkeypatch.setattr(s3_scanner, "StrongPullbackSecondBreakoutEngine", FakeEngine)

    scan_strategy3_all(
        {
            "data": {"database_path": db_path, "daily_sources": ["cache"], "worker_count": 1},
            "liquidity": {"enabled": False, "min_listing_days": 350},
            "market_environment": {"index_symbol": "sh000001"},
            "strategy3": {"strategy_window_days": 250, "minimum_required_days": 180},
        },
        task_id="s3-task",
        stocks=stocks,
        worker_count=1,
    )

    task_stock = db.get_task_stocks("s3-task", limit=1)[0]
    debug = json.loads(task_stock["error_detail"])
    assert "NO_MARKET_DATA_RELATIVE_STRENGTH_FALLBACK" in debug["scoreReasons"]


def test_strategy3_candidates_api_rejects_strategy1_task(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    monkeypatch.setattr(
        server_mod,
        "load_config",
        lambda: {"data": {"database_path": db_path}, "liquidity": {"min_listing_days": 350}},
    )
    db.create_scan_task("s1-task", "2026-06-25 09:00:00", strategy_type="STRATEGY_1_CUP_HANDLE")

    res = TestClient(server_mod.app).get("/api/strategy3/candidates?task_id=s1-task")

    assert res.status_code == 400
    assert res.json()["error"] == "TASK_STRATEGY_MISMATCH"


def test_strategy3_tasks_api_returns_only_strategy3(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    monkeypatch.setattr(
        server_mod,
        "load_config",
        lambda: {"data": {"database_path": db_path}, "liquidity": {"min_listing_days": 350}},
    )
    server_mod._running.update({"running": False, "task_id": None, "strategy_type": None, "stats": {}})
    db.create_scan_task("s3-task", "2026-06-25 09:00:00", strategy_type="STRATEGY_3_STRONG_PULLBACK_SECOND_BREAKOUT")
    db.create_scan_task("s2-task", "2026-06-25 09:10:00", strategy_type="STRATEGY_2_EXTREME_DRY_STABLE")

    res = TestClient(server_mod.app).get("/api/strategy3/tasks")

    assert res.status_code == 200
    ids = [task["id"] for task in res.json()["tasks"]]
    assert "s3-task" in ids
    assert "s2-task" not in ids


def test_strategy3_candidate_detail_api(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    monkeypatch.setattr(
        server_mod,
        "load_config",
        lambda: {"data": {"database_path": db_path}, "liquidity": {"min_listing_days": 350}},
    )
    db.create_scan_task("s3-task", "2026-06-25 09:00:00", strategy_type="STRATEGY_3_STRONG_PULLBACK_SECOND_BREAKOUT")
    db.upsert_strategy3_candidate("s3-task", {
        "code": "000001",
        "name": "平安银行",
        "evaluation_date": "2026-06-25",
        "total_score": 80,
        "level": "观察候选",
    })

    res = TestClient(server_mod.app).get("/api/strategy3/candidates/000001?task_id=s3-task")

    assert res.status_code == 200
    assert res.json()["code"] == "000001"


def test_strategy3_running_status_includes_live_failed_counts(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    monkeypatch.setattr(
        server_mod,
        "load_config",
        lambda: {
            "data": {"database_path": db_path},
            "liquidity": {"min_listing_days": 350},
            "strategy3": {"strategy_window_days": 250, "minimum_required_days": 180},
        },
    )
    monkeypatch.setattr(
        "scanner.stock_pool.get_a_stock_pool_result",
        lambda config: {"stocks": [{"code": "000001", "name": "平安银行", "market": "SZ"}], "source": "mock"},
    )
    server_mod._running.update({"running": False, "task_id": None, "strategy_type": None, "stats": {}})

    entered = threading.Event()
    release = threading.Event()

    def fake_scan_strategy3_all(config, progress_callback=None, task_id=None, stocks=None, **kwargs):
        db.update_task_stock(
            task_id,
            "000001",
            status="failed",
            status_reason="ALL_DATA_SOURCES_FAILED",
            finished_at="2026-06-25 15:30:00",
        )
        if progress_callback:
            progress_callback("scanning", 1, 1, "000001 平安银行")
        entered.set()
        release.wait(timeout=2)
        return {
            "stats": {
                "total": 1,
                "total_stocks": 1,
                "scanned": 1,
                "processed": 1,
                "skipped": 0,
                "failed": 1,
                "candidates_found": 0,
                "elapsed_seconds": 0.1,
            },
        }

    monkeypatch.setattr(server_mod, "scan_strategy3_all", fake_scan_strategy3_all)

    client = TestClient(server_mod.app)
    try:
        res = client.post("/api/strategy3/scans")
        assert res.status_code == 200
        assert entered.wait(timeout=2)

        status = client.get("/api/strategy3/scans/status").json()

        assert status["running"] is True
        assert status["stats"]["processed"] == 1
        assert status["stats"]["failed"] == 1
    finally:
        release.set()

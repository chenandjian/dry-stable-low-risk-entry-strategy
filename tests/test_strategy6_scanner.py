import scanner.db as db
from datetime import date, timedelta
from scanner.daily_data_service import FetchResult
from strategy6 import STRATEGY6_TYPE
from strategy6.scanner import scan_strategy6_all


def _market_rows(closes, start_date=date(2025, 11, 11)):
    rows = []
    for i, close in enumerate(closes):
        rows.append({
            "date": (start_date + timedelta(days=i)).isoformat(),
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": 1_000_000 + i * 1000,
        })
    return rows


def _empty_market(monkeypatch):
    import strategy6.scanner as scanner_mod

    monkeypatch.setattr(scanner_mod, "fetch_market_index_daily", lambda *args, **kwargs: [])


def test_strategy6_scan_forwards_progress_callback_to_tickflow_prepare(tmp_path, monkeypatch):
    import strategy6.scanner as scanner_mod

    db_path = str(tmp_path / "s6-progress.db")
    callback = lambda *args: None
    captured = {}

    def fake_prepare(config, stocks, *, progress_callback=None):
        captured["callback"] = progress_callback
        raise RuntimeError("stop after preparation boundary")

    monkeypatch.setattr(scanner_mod, "prepare_scan_daily_data", fake_prepare)

    import pytest
    with pytest.raises(RuntimeError, match="preparation boundary"):
        scan_strategy6_all(
            {"data": {"database_path": db_path}, "strategy6": {}},
            task_id="s6-progress",
            stocks=[{"code": "000001", "name": "平安银行", "market": "深证主板"}],
            progress_callback=callback,
        )

    assert captured["callback"] is callback


def test_strategy6_scan_marks_all_source_failure_as_failed_stock(tmp_path, monkeypatch):
    _empty_market(monkeypatch)
    db_path = str(tmp_path / "s6scan.db")
    config = {"data": {"database_path": db_path, "daily_sources": ["baidu", "sina", "tencent"], "worker_count": 1}, "strategy6": {}}
    stocks = [{"code": "000001", "name": "平安银行", "market": "SZ", "sector_name": "银行"}]

    def fake_fetch(*args, **kwargs):
        return FetchResult(
            data=None,
            primary_source="baidu",
            fallback_source="tencent",
            primary_error="baidu down",
            fallback_error="tencent down",
        )

    result = scan_strategy6_all(config, task_id="s6-scan", stocks=stocks, fetch_daily_fn=fake_fetch, worker_count=1)

    assert result["task_id"] == "s6-scan"
    assert result["stats"]["failed"] == 1
    assert result["stats"]["candidates_found"] == 0
    assert db.get_task_strategy_type("s6-scan") == STRATEGY6_TYPE
    failed = db.get_failed_task_stocks("s6-scan")
    assert failed[0]["code"] == "000001"
    assert failed[0]["status_reason"] == "ALL_DATA_SOURCES_FAILED"


def test_strategy6_scan_persists_candidate_from_fetched_data(tmp_path, monkeypatch):
    from tests.test_strategy6_core_rules import build_strategy6_candidate_data

    _empty_market(monkeypatch)
    db_path = str(tmp_path / "s6scan.db")
    config = {"data": {"database_path": db_path, "daily_sources": ["baidu", "sina", "tencent"], "worker_count": 1}, "strategy6": {}}
    stocks = [{"code": "000001", "name": "平安银行", "market": "SZ", "sector_name": "银行"}]

    def fake_fetch(*args, **kwargs):
        return FetchResult(data=build_strategy6_candidate_data(), primary_source="baidu", fallback_source="baidu")

    result = scan_strategy6_all(config, task_id="s6-candidate", stocks=stocks, fetch_daily_fn=fake_fetch, worker_count=1)

    assert result["stats"]["candidates_found"] == 1
    assert db.get_task_strategy_type("s6-candidate") == STRATEGY6_TYPE
    rows = db.get_strategy6_candidates("s6-candidate")
    assert rows[0]["code"] == "000001"
    assert rows[0]["sector_name"] == "银行"
    assert rows[0]["risk_reward_ratio_2"] >= 1.5
    assert db.get_task_stocks("s6-candidate")[0]["status"] == "candidate"


def test_strategy6_scan_persists_observer_only_row_without_counting_trade_candidate(tmp_path, monkeypatch):
    import strategy6.scanner as scanner_mod
    import strategy6.vcp_observer as observer_mod
    from types import SimpleNamespace
    from strategy6.vcp_history import Strategy6VcpCandidateHistory
    from tests.test_strategy6_core_rules import build_strategy6_candidate_data

    _empty_market(monkeypatch)
    db_path = str(tmp_path / "s6-observer-only.db")
    config = {
        "data": {
            "database_path": db_path,
            "daily_sources": ["baidu", "sina", "tencent"],
            "worker_count": 1,
        },
        "strategy6": {
            "rr2_min_watch": 10.0,
            "rr2_min_key": 10.0,
            "rr2_min_ready": 10.0,
        },
    }
    stocks = [{"code": "000001", "name": "平安银行", "market": "SZ"}]
    monkeypatch.setattr(
        scanner_mod,
        "evaluate_vcp_candidate_history",
        lambda **kwargs: Strategy6VcpCandidateHistory(
            qualified=True,
            candidate_date="2026-01-20",
            candidate_type="WATCH_CANDIDATE",
            candidate_score=68,
            source="DAILY_AS_OF_REPLAY",
            origin_start_date="2026-01-10",
        ),
    )
    monkeypatch.setattr(
        observer_mod,
        "find_historical_start_anchor",
        lambda rows, *args, **kwargs: SimpleNamespace(
            start_date=rows[0]["date"],
            failure_reasons=[],
        ),
    )

    def fake_fetch(*args, **kwargs):
        return FetchResult(
            data=build_strategy6_candidate_data(),
            primary_source="baidu",
            fallback_source="baidu",
        )

    result = scan_strategy6_all(
        config,
        task_id="s6-observer-only",
        stocks=stocks,
        fetch_daily_fn=fake_fetch,
        worker_count=1,
    )

    assert result["stats"]["candidates_found"] == 0
    assert result["candidates"] == []
    rows = db.get_strategy6_candidates("s6-observer-only")
    assert len(rows) == 1
    assert rows[0]["candidate_type"] == "REJECTED"
    assert rows[0]["vcp_observation_eligible"] is True
    assert rows[0]["vcp_history_qualified"] is True
    assert rows[0]["vcp_history_candidate_date"] == "2026-01-20"
    assert db.get_task_stocks("s6-observer-only")[0]["status"] == "scanned"
    assert db.get_strategy6_lifecycle("000001") is None


def test_strategy6_scan_does_not_persist_vcp_without_formal_candidate_history(tmp_path, monkeypatch):
    import strategy6.scanner as scanner_mod
    from strategy6.models import Strategy6VcpQuality
    from strategy6.vcp_history import Strategy6VcpCandidateHistory
    from tests.test_strategy6_core_rules import build_strategy6_candidate_data

    _empty_market(monkeypatch)
    db_path = str(tmp_path / "s6-vcp-unqualified.db")
    config = {
        "data": {"database_path": db_path, "daily_sources": ["baidu", "sina", "tencent"], "worker_count": 1},
        "strategy6": {"rr2_min_watch": 10.0, "rr2_min_key": 10.0, "rr2_min_ready": 10.0},
    }
    data = build_strategy6_candidate_data()
    monkeypatch.setattr(
        scanner_mod,
        "evaluate_vcp_candidate_history",
        lambda **kwargs: Strategy6VcpCandidateHistory(
            qualified=False,
            origin_start_date=kwargs["origin_start_date"],
        ),
    )
    quality_calls = []
    monkeypatch.setattr(
        scanner_mod,
        "evaluate_vcp_quality",
        lambda *_args, **_kwargs: quality_calls.append(True) or Strategy6VcpQuality(
            scored=True,
            score=99,
            grade="TOP",
            model_version="VCP_QUALITY_V1",
        ),
    )

    scan_strategy6_all(
        config,
        task_id="s6-vcp-unqualified",
        stocks=[{"code": "000001", "name": "平安银行", "market": "SZ"}],
        fetch_daily_fn=lambda *args, **kwargs: FetchResult(
            data=data, primary_source="baidu", fallback_source="baidu",
        ),
        worker_count=1,
    )

    assert db.get_strategy6_candidates("s6-vcp-unqualified") == []
    assert quality_calls == []


def test_strategy6_scan_persists_history_evidence_on_formal_vcp_candidate(tmp_path, monkeypatch):
    import strategy6.scanner as scanner_mod
    from strategy6.engine import StrongVcpTailEngine
    from strategy6.models import Strategy6VcpObservation, Strategy6VcpQuality
    from strategy6.vcp_history import Strategy6VcpCandidateHistory
    from tests.test_strategy6_core_rules import build_strategy6_candidate_data

    _empty_market(monkeypatch)
    db_path = str(tmp_path / "s6-formal-vcp-history.db")
    config = {
        "data": {"database_path": db_path, "daily_sources": ["baidu", "sina", "tencent"], "worker_count": 1},
        "strategy6": {},
    }
    data = build_strategy6_candidate_data()
    evaluation = StrongVcpTailEngine(config).evaluate_at(data, code="000001", name="平安银行")
    assert evaluation.passed is True
    evaluation.vcp_observation = Strategy6VcpObservation(
        eligible=True,
        lifecycle_status="VCP_NEAR_PIVOT",
        origin_start_date=data[-20]["date"],
        pattern_start_date=data[-10]["date"],
        pattern_end_date=data[-1]["date"],
        contraction_count=2,
    )

    class FakeEngine:
        def __init__(self, _config):
            pass

        def evaluate_at(self, *_args, **_kwargs):
            return evaluation

    monkeypatch.setattr(scanner_mod, "StrongVcpTailEngine", FakeEngine)
    history_calls = []
    monkeypatch.setattr(
        scanner_mod,
        "evaluate_vcp_candidate_history",
        lambda **kwargs: history_calls.append(kwargs) or Strategy6VcpCandidateHistory(
            qualified=True,
            candidate_date=evaluation.indicators.evaluation_date,
            candidate_type=evaluation.candidate_type,
            candidate_score=evaluation.score.total_score,
            source="DAILY_AS_OF_REPLAY",
            origin_start_date=evaluation.vcp_observation.origin_start_date,
        ),
    )
    quality_calls = []
    monkeypatch.setattr(
        scanner_mod,
        "evaluate_vcp_quality",
        lambda rows, observation: quality_calls.append((rows, observation)) or Strategy6VcpQuality(
            scored=True,
            score=85,
            grade="HIGH",
            contraction_score=12,
            range_score=25,
            volume_score=20,
            low_score=13,
            time_score=10,
            pivot_score=5,
            model_version="VCP_QUALITY_V1",
        ),
        raising=False,
    )

    scan_strategy6_all(
        config,
        task_id="s6-formal-vcp-history",
        stocks=[{"code": "000001", "name": "平安银行", "market": "SZ"}],
        fetch_daily_fn=lambda *args, **kwargs: FetchResult(
            data=data, primary_source="baidu", fallback_source="baidu",
        ),
        worker_count=1,
    )

    row = db.get_strategy6_candidates("s6-formal-vcp-history")[0]
    assert row["candidate_type"] != "REJECTED"
    assert row["vcp_observation_eligible"] is True
    assert row["vcp_history_qualified"] is True
    assert row["vcp_history_candidate_date"] == evaluation.indicators.evaluation_date
    assert row["vcp_quality_score"] == 85
    assert row["vcp_quality_grade"] == "HIGH"
    assert row["vcp_quality_model_version"] == "VCP_QUALITY_V1"
    assert len(quality_calls) == 1
    assert history_calls[0]["pattern_start_date"] == evaluation.vcp_observation.pattern_start_date


def test_strategy6_scan_does_not_persist_vcp_exit_without_prior_observation(tmp_path, monkeypatch):
    import strategy6.scanner as scanner_mod
    from strategy6.engine import StrongVcpTailEngine
    from strategy6.models import Strategy6VcpObservation
    from tests.test_strategy6_core_rules import build_strategy6_candidate_data

    _empty_market(monkeypatch)
    db_path = str(tmp_path / "s6-vcp-exit.db")
    config = {
        "data": {
            "database_path": db_path,
            "daily_sources": ["baidu", "sina", "tencent"],
            "worker_count": 1,
        },
        "strategy6": {
            "rr2_min_watch": 10.0,
            "rr2_min_key": 10.0,
            "rr2_min_ready": 10.0,
        },
    }
    data = build_strategy6_candidate_data()
    evaluation = StrongVcpTailEngine(config).evaluate_at(data, code="000001", name="平安银行")
    evaluation.vcp_observation = Strategy6VcpObservation(
        eligible=False,
        lifecycle_status="VCP_INVALID",
        contraction_count=2,
        pivot_price=12.5,
        structure_low=11.8,
        risk_tags=["VCP_STRUCTURE_LOW_BROKEN"],
        invalidation_reason="VCP_STRUCTURE_LOW_BROKEN",
    )

    class FakeEngine:
        def __init__(self, _config):
            pass

        def evaluate_at(self, *_args, **_kwargs):
            return evaluation

    monkeypatch.setattr(scanner_mod, "StrongVcpTailEngine", FakeEngine)
    fake_fetch = lambda *args, **kwargs: FetchResult(
        data=data,
        primary_source="baidu",
        fallback_source="baidu",
    )

    result = scan_strategy6_all(
        config,
        task_id="s6-vcp-exit",
        stocks=[{"code": "000001", "name": "平安银行", "market": "SZ"}],
        fetch_daily_fn=fake_fetch,
        worker_count=1,
    )

    assert result["stats"]["candidates_found"] == 0
    assert db.get_strategy6_candidates("s6-vcp-exit") == []
    assert db.get_strategy6_lifecycle("000001") is None


def test_strategy6_scan_persists_one_vcp_exit_after_prior_eligible_observation(tmp_path, monkeypatch):
    import strategy6.scanner as scanner_mod
    from strategy6.engine import StrongVcpTailEngine
    from strategy6.models import Strategy6VcpObservation
    from tests.test_strategy6_core_rules import build_strategy6_candidate_data

    _empty_market(monkeypatch)
    db_path = str(tmp_path / "s6-vcp-real-exit.db")
    config = {
        "data": {
            "database_path": db_path,
            "daily_sources": ["baidu", "sina", "tencent"],
            "worker_count": 1,
        },
        "strategy6": {
            "rr2_min_watch": 10.0,
            "rr2_min_key": 10.0,
            "rr2_min_ready": 10.0,
        },
    }
    db.init_db(db_path)
    db.create_scan_task("s6-vcp-prior", "2026-07-08 10:00:00", strategy_type=STRATEGY6_TYPE)
    prior = {
        "code": "000001",
        "name": "平安银行",
        "evaluation_date": "2026-07-08",
        "candidate_type": "REJECTED",
        "classification": "observation",
        "vcp_observation_eligible": True,
        "vcp_history_qualified": True,
        "vcp_history_candidate_date": "2026-07-07",
        "vcp_history_candidate_type": "WATCH_CANDIDATE",
        "vcp_history_candidate_score": 66,
        "vcp_history_source": "DAILY_AS_OF_REPLAY",
        "vcp_history_origin_start_date": "2026-06-20",
        "vcp_lifecycle_status": "VCP_NEAR_PIVOT",
    }
    db.upsert_strategy6_candidate("s6-vcp-prior", prior)
    db.finish_scan_task(
        "s6-vcp-prior", "2026-07-08 16:00:00", candidates_count=0, elapsed_seconds=1.0,
    )

    data = build_strategy6_candidate_data()
    evaluation = StrongVcpTailEngine(config).evaluate_at(data, code="000001", name="平安银行")
    evaluation.vcp_observation = Strategy6VcpObservation(
        eligible=False,
        lifecycle_status="VCP_INVALID",
        contraction_count=2,
        pivot_price=12.5,
        structure_low=11.8,
        risk_tags=["VCP_STRUCTURE_LOW_BROKEN"],
        invalidation_reason="VCP_STRUCTURE_LOW_BROKEN",
    )

    class FakeEngine:
        def __init__(self, _config):
            pass

        def evaluate_at(self, *_args, **_kwargs):
            return evaluation

    monkeypatch.setattr(scanner_mod, "StrongVcpTailEngine", FakeEngine)
    monkeypatch.setattr(
        scanner_mod,
        "evaluate_vcp_quality",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("ineligible VCP exit audit must not be scored")
        ),
    )
    fake_fetch = lambda *args, **kwargs: FetchResult(
        data=data,
        primary_source="baidu",
        fallback_source="baidu",
    )

    scan_strategy6_all(
        config,
        task_id="s6-vcp-real-exit",
        stocks=[{"code": "000001", "name": "平安银行", "market": "SZ"}],
        fetch_daily_fn=fake_fetch,
        worker_count=1,
    )
    rows = db.get_strategy6_candidates("s6-vcp-real-exit")
    assert len(rows) == 1
    assert rows[0]["vcp_exit_audit"] is True
    assert rows[0]["vcp_observation_eligible"] is False
    assert rows[0]["vcp_quality_score"] is None
    assert not rows[0]["vcp_quality_model_version"]
    db.finish_scan_task(
        "s6-vcp-real-exit", "2026-07-09 16:00:00", candidates_count=0, elapsed_seconds=1.0,
    )

    scan_strategy6_all(
        config,
        task_id="s6-vcp-still-invalid",
        stocks=[{"code": "000001", "name": "平安银行", "market": "SZ"}],
        fetch_daily_fn=fake_fetch,
        worker_count=1,
    )
    assert db.get_strategy6_candidates("s6-vcp-still-invalid") == []


def test_strategy6_scan_ignores_vcp_state_from_failed_task(tmp_path, monkeypatch):
    import strategy6.scanner as scanner_mod
    from strategy6.engine import StrongVcpTailEngine
    from strategy6.models import Strategy6VcpObservation
    from tests.test_strategy6_core_rules import build_strategy6_candidate_data

    _empty_market(monkeypatch)
    db_path = str(tmp_path / "s6-vcp-failed-state.db")
    config = {
        "data": {
            "database_path": db_path,
            "daily_sources": ["baidu", "sina", "tencent"],
            "worker_count": 1,
        },
        "strategy6": {
            "rr2_min_watch": 10.0,
            "rr2_min_key": 10.0,
            "rr2_min_ready": 10.0,
        },
    }
    db.init_db(db_path)
    db.create_scan_task("s6-vcp-failed-prior", "2026-07-08 10:00:00", strategy_type=STRATEGY6_TYPE)
    db.upsert_strategy6_candidate("s6-vcp-failed-prior", {
        "code": "000001",
        "name": "平安银行",
        "evaluation_date": "2026-07-08",
        "candidate_type": "REJECTED",
        "classification": "observation",
        "vcp_observation_eligible": True,
        "vcp_lifecycle_status": "VCP_NEAR_PIVOT",
    })
    conn = db.get_conn()
    conn.execute("UPDATE scan_tasks SET status='failed', finished_at=? WHERE id=?", (
        "2026-07-08 16:00:00", "s6-vcp-failed-prior",
    ))
    conn.commit()

    data = build_strategy6_candidate_data()
    evaluation = StrongVcpTailEngine(config).evaluate_at(data, code="000001", name="平安银行")
    evaluation.vcp_observation = Strategy6VcpObservation(
        eligible=False,
        lifecycle_status="VCP_INVALID",
        risk_tags=["VCP_STRUCTURE_LOW_BROKEN"],
        invalidation_reason="VCP_STRUCTURE_LOW_BROKEN",
    )

    class FakeEngine:
        def __init__(self, _config):
            pass

        def evaluate_at(self, *_args, **_kwargs):
            return evaluation

    monkeypatch.setattr(scanner_mod, "StrongVcpTailEngine", FakeEngine)
    scan_strategy6_all(
        config,
        task_id="s6-after-failed",
        stocks=[{"code": "000001", "name": "平安银行", "market": "SZ"}],
        fetch_daily_fn=lambda *args, **kwargs: FetchResult(
            data=data, primary_source="baidu", fallback_source="baidu",
        ),
        worker_count=1,
    )

    assert db.get_strategy6_candidates("s6-after-failed") == []


def test_strategy6_scan_persists_failed_lifecycle_audit_without_candidate(tmp_path, monkeypatch):
    from tests.test_strategy6_core_rules import build_strategy6_candidate_data

    _empty_market(monkeypatch)
    db_path = str(tmp_path / "s6-lifecycle-exit.db")
    db.init_db(db_path)
    db.update_strategy6_lifecycle(
        code="000001",
        evaluation_date="2026-01-28",
        candidate_type="KEY_CANDIDATE",
        lifecycle_status="READY",
        event_key="stable-event",
        reject_reasons=[],
        max_watch_days=10,
        expired_cooldown_days=5,
        failed_cooldown_days=10,
    )
    data = build_strategy6_candidate_data()
    data[-1]["open"] = data[-2]["close"]
    data[-1]["close"] = round(data[-2]["close"] * 0.92, 4)
    data[-1]["high"] = round(data[-2]["close"] * 1.01, 4)
    data[-1]["low"] = round(data[-1]["close"] * 0.99, 4)
    data[-1]["volume"] = 3_000_000

    config = {"data": {"database_path": db_path, "daily_sources": ["baidu", "sina", "tencent"], "worker_count": 1}, "strategy6": {}}
    stocks = [{"code": "000001", "name": "平安银行", "market": "SZ"}]
    fake_fetch = lambda *args, **kwargs: FetchResult(data=data, primary_source="baidu", fallback_source="baidu")

    scan_strategy6_all(config, task_id="s6-exit", stocks=stocks, fetch_daily_fn=fake_fetch, worker_count=1)

    assert db.get_strategy6_candidates("s6-exit") == []
    audit = db.get_strategy6_task_lifecycle("s6-exit")
    assert audit[0]["lifecycle_status"] == "FAILED"
    assert audit[0]["blocked"] is True
    assert "BIG_DOWN_VOLUME" in audit[0]["reject_reasons"]


def test_strategy6_scan_passes_market_context_when_market_filter_enabled(tmp_path, monkeypatch):
    from tests.test_strategy6_core_rules import build_strategy6_candidate_data
    import strategy6.scanner as scanner_mod

    db_path = str(tmp_path / "s6market.db")
    config = {
        "data": {"database_path": db_path, "daily_sources": ["baidu", "sina", "tencent"], "worker_count": 1},
        "strategy6": {"enable_market_filter": True, "market_filter_mode": "downgrade"},
    }
    stocks = [{"code": "000001", "name": "平安银行", "market": "SZ", "sector_name": "银行"}]
    fetched_symbols = []

    def fake_fetch_market(symbol=None, days=250):
        fetched_symbols.append(symbol)
        return _market_rows([120 - i * 0.2 for i in range(80)])

    def fake_fetch(*args, **kwargs):
        return FetchResult(data=build_strategy6_candidate_data(), primary_source="baidu", fallback_source="baidu")

    monkeypatch.setattr(scanner_mod, "fetch_market_index_daily", fake_fetch_market)
    monkeypatch.setattr(scanner_mod, "_now", lambda: "2026-01-29 16:00:00")

    scan_strategy6_all(config, task_id="s6-market", stocks=stocks, fetch_daily_fn=fake_fetch, worker_count=1)

    row = db.get_strategy6_candidates("s6-market")[0]
    assert {"sh000001", "sz399001", "sz399006"}.issubset(set(fetched_symbols))
    assert row["enable_market_filter"] is True
    assert row["market_status"] in {"MARKET_WEAK", "MARKET_RISK", "MARKET_NEUTRAL", "MARKET_STRONG"}


def test_strategy6_scan_persists_market_snapshot_for_frontend_audit(tmp_path, monkeypatch):
    from tests.test_strategy6_core_rules import build_strategy6_candidate_data
    import strategy6.scanner as scanner_mod

    db_path = str(tmp_path / "s6marketsnapshot.db")
    config = {
        "data": {"database_path": db_path, "daily_sources": ["baidu", "sina", "tencent"], "worker_count": 1},
        "strategy6": {"enable_market_filter": True, "market_filter_mode": "downgrade"},
    }
    stocks = [{"code": "000001", "name": "平安银行", "market": "SZ", "sector_name": "银行"}]

    def fake_fetch_market(symbol=None, days=250):
        if symbol == "sh000001":
            return _market_rows([100 + i * 0.2 for i in range(80)])
        if symbol == "sz399001":
            return _market_rows([120 + i * 0.1 for i in range(80)])
        if symbol == "sz399006":
            return _market_rows([140 - i * 0.05 for i in range(80)])
        return _market_rows([110 + i * 0.15 for i in range(80)])

    def fake_fetch(*args, **kwargs):
        return FetchResult(data=build_strategy6_candidate_data(), primary_source="baidu", fallback_source="baidu")

    monkeypatch.setattr(scanner_mod, "fetch_market_index_daily", fake_fetch_market)
    monkeypatch.setattr(scanner_mod, "_now", lambda: "2026-01-29 16:00:00")

    scan_strategy6_all(config, task_id="s6-market-snapshot", stocks=stocks, fetch_daily_fn=fake_fetch, worker_count=1)

    snapshot = db.get_strategy6_market_snapshot("s6-market-snapshot")
    assert snapshot["task_id"] == "s6-market-snapshot"
    assert snapshot["market_status"] in {"MARKET_STRONG", "MARKET_NEUTRAL", "MARKET_WEAK", "MARKET_RISK"}
    symbols = {row["symbol"] for row in snapshot["indexes"]}
    assert {"sh000001", "sz399001", "sz399006", "hs300"} <= symbols
    sh = next(row for row in snapshot["indexes"] if row["symbol"] == "sh000001")
    assert sh["name"] == "上证指数"
    assert sh["latest_date"]
    assert sh["latest_close"] > 0
    assert sh["ma20"] > 0
    assert sh["ma50"] > 0
    assert isinstance(sh["above_ma20"], bool)
    assert sh["data_status"] == "FRESH"
    assert db.get_market_index_coverage("sh000300")["rows"] == 80


def test_strategy6_scan_reports_market_status_when_market_filter_disabled(tmp_path, monkeypatch):
    from tests.test_strategy6_core_rules import build_strategy6_candidate_data
    import strategy6.scanner as scanner_mod

    db_path = str(tmp_path / "s6marketoff.db")
    config = {
        "data": {"database_path": db_path, "daily_sources": ["baidu", "sina", "tencent"], "worker_count": 1},
        "strategy6": {"enable_market_filter": False, "market_filter_mode": "downgrade"},
    }
    stocks = [{"code": "000001", "name": "平安银行", "market": "SZ", "sector_name": "银行"}]

    def fake_fetch_market(symbol=None, days=250):
        return _market_rows([120 - i * 0.2 for i in range(80)])

    def fake_fetch(*args, **kwargs):
        return FetchResult(data=build_strategy6_candidate_data(), primary_source="baidu", fallback_source="baidu")

    monkeypatch.setattr(scanner_mod, "fetch_market_index_daily", fake_fetch_market)

    scan_strategy6_all(config, task_id="s6-market-off", stocks=stocks, fetch_daily_fn=fake_fetch, worker_count=1)

    row = db.get_strategy6_candidates("s6-market-off")[0]
    assert row["enable_market_filter"] is False
    assert row["market_status"] == "MARKET_WEAK"
    assert "MARKET_WEAK_DOWNGRADED" not in row["warn_tags"]
    assert "MARKET_WEAK_STRICT" not in row["warn_tags"]


def test_strategy6_scan_truncates_market_context_to_stock_evaluation_date(tmp_path, monkeypatch):
    from tests.test_strategy6_core_rules import build_strategy6_candidate_data
    import strategy6.scanner as scanner_mod

    db_path = str(tmp_path / "s6marketfuture.db")
    config = {
        "data": {"database_path": db_path, "daily_sources": ["baidu", "sina", "tencent"], "worker_count": 1},
        "strategy6": {"enable_market_filter": False},
    }
    stocks = [{"code": "000001", "name": "平安银行", "market": "SZ", "sector_name": "银行"}]

    def fake_fetch_market(symbol=None, days=250):
        rows = []
        start_date = date(2025, 11, 11)
        for i in range(120):
            close = 100 + i * 0.01
            if i >= 80:
                close = 200 + i
            rows.append({
                "date": (start_date + timedelta(days=i)).isoformat(),
                "open": close,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": 1_000_000,
            })
        return rows

    def fake_fetch(*args, **kwargs):
        return FetchResult(data=build_strategy6_candidate_data(), primary_source="baidu", fallback_source="baidu")

    monkeypatch.setattr(scanner_mod, "fetch_market_index_daily", fake_fetch_market)

    scan_strategy6_all(config, task_id="s6-market-truncate", stocks=stocks, fetch_daily_fn=fake_fetch, worker_count=1)

    row = db.get_strategy6_candidates("s6-market-truncate")[0]
    assert row["relative_strength_20_observed"] is True
    assert row["relative_strength_20"] > 0.10
    assert row["kline_latest_date"] == "2026-01-29"

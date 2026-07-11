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

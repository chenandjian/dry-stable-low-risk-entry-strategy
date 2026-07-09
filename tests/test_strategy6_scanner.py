import scanner.db as db
from scanner.daily_data_service import FetchResult
from strategy6 import STRATEGY6_TYPE
from strategy6.scanner import scan_strategy6_all


def test_strategy6_scan_marks_all_source_failure_as_failed_stock(tmp_path):
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


def test_strategy6_scan_persists_candidate_from_fetched_data(tmp_path):
    from tests.test_strategy6_core_rules import build_strategy6_candidate_data

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
        return [
            {"date": f"2026-01-{i+1:02d}", "open": 100 - i, "high": 101 - i, "low": 99 - i, "close": 100 - i, "volume": 1_000_000 + i * 1000}
            for i in range(80)
        ]

    def fake_fetch(*args, **kwargs):
        return FetchResult(data=build_strategy6_candidate_data(), primary_source="baidu", fallback_source="baidu")

    monkeypatch.setattr(scanner_mod, "fetch_market_index_daily", fake_fetch_market)

    scan_strategy6_all(config, task_id="s6-market", stocks=stocks, fetch_daily_fn=fake_fetch, worker_count=1)

    row = db.get_strategy6_candidates("s6-market")[0]
    assert {"sh000001", "sz399001", "sz399006"}.issubset(set(fetched_symbols))
    assert row["enable_market_filter"] is True
    assert row["market_status"] in {"MARKET_WEAK", "MARKET_RISK", "MARKET_NEUTRAL", "MARKET_STRONG"}

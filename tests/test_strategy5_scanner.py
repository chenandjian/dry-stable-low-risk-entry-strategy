import scanner.db as db
from scanner.daily_data_service import FetchResult
from strategy5.scanner import STRATEGY5_TYPE, scan_strategy5_all


def test_strategy5_scan_marks_all_source_failure_as_failed_stock(tmp_path):
    db_path = str(tmp_path / "s5scan.db")
    config = {"data": {"database_path": db_path, "daily_sources": ["baidu", "sina", "tencent"], "worker_count": 1}}
    stocks = [{"code": "000001", "name": "平安银行", "market": "SZ"}]

    def fake_fetch(*args, **kwargs):
        return FetchResult(
            data=None,
            primary_source="baidu",
            fallback_source="tencent",
            primary_error="baidu down",
            fallback_error="tencent down",
        )

    result = scan_strategy5_all(config, task_id="s5-scan", stocks=stocks, fetch_daily_fn=fake_fetch, worker_count=1)

    assert result["task_id"] == "s5-scan"
    assert result["stats"]["failed"] == 1
    assert result["stats"]["candidates_found"] == 0
    assert db.get_task_strategy_type("s5-scan") == STRATEGY5_TYPE
    failed = db.get_failed_task_stocks("s5-scan")
    assert failed[0]["code"] == "000001"
    assert failed[0]["status_reason"] == "ALL_DATA_SOURCES_FAILED"


def test_strategy5_scan_persists_candidate_from_fetched_data(tmp_path):
    from tests.test_strategy5_core_rules import build_strong_data

    db_path = str(tmp_path / "s5scan.db")
    config = {"data": {"database_path": db_path, "daily_sources": ["baidu", "sina", "tencent"], "worker_count": 1}}
    stocks = [{"code": "000001", "name": "平安银行", "market": "SZ"}]

    def fake_fetch(*args, **kwargs):
        return FetchResult(data=build_strong_data(), primary_source="baidu", fallback_source="baidu")

    result = scan_strategy5_all(config, task_id="s5-candidate", stocks=stocks, fetch_daily_fn=fake_fetch, worker_count=1)

    assert result["stats"]["candidates_found"] == 1
    assert db.get_task_strategy_type("s5-candidate") == STRATEGY5_TYPE
    rows = db.get_strategy5_candidates("s5-candidate")
    assert rows[0]["code"] == "000001"
    assert rows[0]["high_trigger"]
    assert rows[0]["strength_trigger"]
    assert db.get_task_stocks("s5-candidate")[0]["status"] == "candidate"

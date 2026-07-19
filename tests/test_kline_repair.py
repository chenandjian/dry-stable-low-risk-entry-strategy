import json
import threading
from concurrent.futures import ThreadPoolExecutor

from scanner import db
from scanner import kline_repair
from scanner.data_source import DataSourceManager


def _row(day: int, close: float = 10.0):
    date = f"2026-05-{day:02d}"
    return {
        "date": date,
        "open": close,
        "high": close + 0.2,
        "low": close - 0.2,
        "close": close,
        "volume": 1000.0,
        "turnover": close * 1000,
    }


def test_replace_ohlc_with_metadata_replaces_old_rows_atomically(tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    db.save_ohlc("002396", [_row(19, 33.0), _row(20, 33.22)])

    db.replace_ohlc_with_metadata(
        "002396",
        [_row(20, 25.38), _row(21, 23.46)],
        source="sina",
        fetched_at="2026-07-19 12:00:00",
        repair_run_id="repair-1",
    )

    assert db.get_ohlc("002396") == [_row(20, 25.38), _row(21, 23.46)]
    assert db.get_ohlc_metadata("002396") == {
        "code": "002396",
        "source": "sina",
        "price_basis": "FORWARD_ADJUSTED",
        "row_count": 2,
        "first_date": "2026-05-20",
        "latest_date": "2026-05-21",
        "fetched_at": "2026-07-19 12:00:00",
        "repair_run_id": "repair-1",
    }


def test_infer_legacy_selected_source_uses_first_source_without_error():
    assert kline_repair.infer_legacy_selected_source(None) == "baidu"
    assert kline_repair.infer_legacy_selected_source(json.dumps({"baidu": "busy"})) == "sina"
    assert kline_repair.infer_legacy_selected_source(
        json.dumps({"baidu": "busy", "sina": "busy"})
    ) == "tencent"
    assert kline_repair.infer_legacy_selected_source(
        json.dumps({"baidu": "busy", "sina": "busy", "tencent": "busy"})
    ) is None


def test_repair_stock_uses_tencent_sina_baidu_order_and_skips_short_source(tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    existing = [_row(day, 30.0) for day in range(1, 6)]
    db.save_ohlc("002396", existing)
    calls = []

    def tencent(code, days):
        calls.append("tencent")
        return [_row(day, 25.0) for day in range(2, 6)]

    def sina(code, days):
        calls.append("sina")
        return [_row(day, 20.0 + day) for day in range(1, 6)]

    def baidu(code, days):
        calls.append("baidu")
        raise AssertionError("baidu should not be reached")

    result = kline_repair.repair_stock(
        "002396",
        requested_days=5,
        fetchers={"tencent": tencent, "sina": sina, "baidu": baidu},
        repair_run_id="repair-1",
    )

    assert calls == ["tencent", "sina"]
    assert result.status == "repaired"
    assert result.source == "sina"
    assert "insufficient rows" in result.source_errors["tencent"]
    assert db.get_ohlc("002396")[0]["close"] == 21.0
    assert db.get_ohlc_metadata("002396")["source"] == "sina"


def test_repair_stock_rejects_older_latest_date_and_dry_run_does_not_write(tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    existing = [_row(day, 30.0) for day in range(1, 6)]
    db.save_ohlc("002396", existing)

    old = [
        dict(_row(1, 20.0), date="2026-04-30"),
        _row(1, 20.0),
        _row(2, 20.0),
        _row(3, 20.0),
        _row(4, 20.0),
    ]
    good = [_row(day, 20.0) for day in range(1, 6)]
    result = kline_repair.repair_stock(
        "002396",
        requested_days=5,
        fetchers={"tencent": lambda *_args, **_kwargs: old, "sina": lambda *_args, **_kwargs: good},
        dry_run=True,
    )

    assert result.status == "would_repair"
    assert result.source == "sina"
    assert "latest date regressed" in result.source_errors["tencent"]
    assert db.get_ohlc("002396") == existing
    assert db.get_ohlc_metadata("002396") is None


def test_repair_stock_never_shortens_existing_history_when_requested_days_is_lower(tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    existing = [_row(day, 30.0) for day in range(1, 7)]
    db.save_ohlc("002396", existing)
    requested = []

    def tencent(code, days):
        requested.append(days)
        return [_row(day, 20.0) for day in range(1, 7)]

    result = kline_repair.repair_stock(
        "002396",
        requested_days=5,
        fetchers={
            "tencent": tencent,
            "sina": lambda *_args, **_kwargs: None,
            "baidu": lambda *_args, **_kwargs: None,
        },
    )

    assert requested == [6]
    assert result.status == "repaired"
    assert result.row_count == 6
    assert len(db.get_ohlc("002396")) == 6


def test_find_legacy_sina_candidates_uses_latest_non_cache_task(tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    db.save_ohlc("002396", [_row(20, 33.22)])
    stocks = [
        {"code": "002396", "name": "A", "market": "SZ"},
        {"code": "000001", "name": "B", "market": "SZ"},
    ]
    for task_id, fetched_at, errors in [
        ("old", "2026-07-16 15:30:00", None),
        ("new", "2026-07-17 15:30:00", '{"baidu":"busy"}'),
    ]:
        db.create_scan_task(task_id, fetched_at, total_stocks=2)
        db.save_task_stocks(task_id, stocks)
        db.update_task_stock(
            task_id,
            "002396",
            status="scanned",
            primary_source="baidu",
            fallback_source="tencent",
            source_errors=errors,
            kline_fetched_at=fetched_at,
        )
    db.update_task_stock(
        "new",
        "000001",
        status="scanned",
        primary_source="baidu",
        fallback_source="tencent",
        source_errors='{"baidu":"busy","sina":"busy"}',
        kline_fetched_at="2026-07-17 15:30:00",
    )

    candidates, unknown = kline_repair.find_legacy_sina_candidates()

    assert [row["code"] for row in candidates] == ["002396"]
    assert unknown == []


def test_three_repair_workers_use_three_source_locks_concurrently(tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    codes = ["000001", "000002", "000003"]
    for code in codes:
        db.save_ohlc(code, [_row(day, 30.0) for day in range(1, 6)])

    barrier = threading.Barrier(3)
    calls = []
    calls_lock = threading.Lock()

    def fetch_from(source):
        def fetch(code, days):
            with calls_lock:
                calls.append((source, code))
            barrier.wait(timeout=5)
            return [_row(day, 20.0) for day in range(1, 6)]
        return fetch

    fetchers = {source: fetch_from(source) for source in kline_repair.REPAIR_SOURCE_CHAIN}
    source_manager = DataSourceManager()
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(
            executor.map(
                lambda code: kline_repair.repair_stock(
                    code,
                    requested_days=5,
                    fetchers=fetchers,
                    source_manager=source_manager,
                ),
                codes,
            )
        )

    assert {result.source for result in results} == {"tencent", "sina", "baidu"}
    assert {source for source, _code in calls} == {"tencent", "sina", "baidu"}

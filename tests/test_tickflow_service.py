import pandas as pd

from scanner import db
from tickflow_data.models import BatchFetchResult
from tickflow_data.service import TickFlowDailyUpdateService


def _rows(start_day=1, count=3, *, close_offset=0.0):
    rows = []
    for day in range(start_day, start_day + count):
        close = 10.0 + day / 10 + close_offset
        rows.append(
            {
                "date": f"2026-07-{day:02d}",
                "open": close - 0.1,
                "high": close + 0.2,
                "low": close - 0.2,
                "close": close,
                "volume": 100_000.0 + day,
                "turnover": 1_000_000.0 + day,
            }
        )
    return rows


def _frame(rows):
    return pd.DataFrame(
        [
            {
                "trade_date": row["date"],
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"] / 100,
                "amount": row["turnover"],
            }
            for row in rows
        ]
    )


class _Client:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def fetch(self, symbols, *, count):
        self.calls.append((list(symbols), count))
        return self.responses.pop(0)


def _setup_db(tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))


def _save_existing(code, rows, *, source):
    db.replace_ohlc_with_metadata(
        code,
        rows,
        source=source,
        repair_run_id="before",
    )


def test_full_backfill_replaces_non_tickflow_history(tmp_path):
    _setup_db(tmp_path)
    _save_existing("600519", _rows(1, 2), source="tencent")
    fresh = _rows(1, 4, close_offset=1.0)
    client = _Client(
        [BatchFetchResult(frames={"600519.SH": _frame(fresh)})]
    )
    service = TickFlowDailyUpdateService(client, history_days=1100, overlap_days=10)

    result = service.run([{"code": "600519", "market": "SH"}], dry_run=False)

    assert client.calls == [(["600519.SH"], 1100)]
    assert result.results[0].status == "success"
    assert result.results[0].request_mode == "full"
    assert db.get_ohlc("600519") == fresh
    metadata = db.get_ohlc_metadata("600519")
    assert metadata["source"] == "tickflow"
    assert metadata["price_basis"] == "FORWARD_ADJUSTED"
    assert metadata["repair_run_id"] == result.run_id


def test_incremental_update_merges_overlap_and_preserves_history(tmp_path):
    _setup_db(tmp_path)
    existing = _rows(1, 4)
    _save_existing("600519", existing, source="tickflow")
    overlap = [existing[-1], *_rows(5, 2)]
    client = _Client(
        [BatchFetchResult(frames={"600519.SH": _frame(overlap)})]
    )
    service = TickFlowDailyUpdateService(client, history_days=1100, overlap_days=10)

    result = service.run([{"code": "600519", "market": "SH"}], dry_run=False)

    assert client.calls == [(["600519.SH"], 10)]
    assert result.results[0].request_mode == "incremental"
    assert db.get_ohlc("600519") == [*existing, *_rows(5, 2)]


def test_adjustment_change_upgrades_incremental_stock_to_full_refresh(tmp_path):
    _setup_db(tmp_path)
    existing = _rows(1, 4)
    _save_existing("600519", existing, source="tickflow")
    changed_overlap = _rows(4, 2, close_offset=1.0)
    full = _rows(1, 6, close_offset=1.0)
    client = _Client(
        [
            BatchFetchResult(frames={"600519.SH": _frame(changed_overlap)}),
            BatchFetchResult(frames={"600519.SH": _frame(full)}),
        ]
    )
    service = TickFlowDailyUpdateService(client, history_days=1100, overlap_days=10)

    result = service.run([{"code": "600519", "market": "SH"}], dry_run=False)

    assert client.calls == [(["600519.SH"], 10), (["600519.SH"], 1100)]
    assert result.results[0].request_mode == "full_adjustment_refresh"
    assert db.get_ohlc("600519") == full


def test_missing_or_invalid_stock_does_not_modify_existing_data(tmp_path):
    _setup_db(tmp_path)
    old_a = _rows(1, 2)
    old_b = _rows(1, 2)
    _save_existing("600519", old_a, source="tencent")
    _save_existing("000001", old_b, source="tencent")
    invalid = _frame(_rows(1, 2))
    invalid.loc[0, "high"] = 1.0
    client = _Client(
        [
            BatchFetchResult(
                frames={"600519.SH": invalid},
                missing_symbols=["000001.SZ"],
            )
        ]
    )
    service = TickFlowDailyUpdateService(client)

    result = service.run(
        [
            {"code": "600519", "market": "SH"},
            {"code": "000001", "market": "SZ"},
        ],
        dry_run=False,
    )

    assert [item.status for item in result.results] == ["failed", "failed"]
    assert db.get_ohlc("600519") == old_a
    assert db.get_ohlc("000001") == old_b
    assert db.get_ohlc_metadata("600519")["source"] == "tencent"
    assert db.get_ohlc_metadata("000001")["source"] == "tencent"


def test_dry_run_validates_without_writing_database(tmp_path):
    _setup_db(tmp_path)
    old = _rows(1, 2)
    _save_existing("600519", old, source="tencent")
    client = _Client(
        [BatchFetchResult(frames={"600519.SH": _frame(_rows(1, 4))})]
    )
    service = TickFlowDailyUpdateService(client)

    result = service.run([{"code": "600519", "market": "SH"}], dry_run=True)

    assert result.results[0].status == "validated"
    assert db.get_ohlc("600519") == old
    assert db.get_ohlc_metadata("600519")["source"] == "tencent"


def test_full_refresh_never_shortens_or_regresses_existing_history(tmp_path):
    _setup_db(tmp_path)
    old = _rows(1, 4)
    _save_existing("600519", old, source="tickflow")
    shorter = _rows(1, 2)
    client = _Client(
        [BatchFetchResult(frames={"600519.SH": _frame(shorter)})]
    )
    service = TickFlowDailyUpdateService(client)

    result = service.run(
        [{"code": "600519", "market": "SH"}],
        dry_run=False,
        mode="backfill",
    )

    assert result.results[0].status == "failed"
    assert "shortened" in result.results[0].error
    assert db.get_ohlc("600519") == old


def test_full_refresh_ignores_zero_volume_placeholder_in_history_guards(tmp_path):
    _setup_db(tmp_path)
    real = _rows(1, 3)
    placeholder = {
        **real[-1],
        "date": "2026-07-04",
        "volume": 0.0,
        "turnover": 0.0,
    }
    _save_existing("688693", [*real, placeholder], source="sina")
    client = _Client(
        [BatchFetchResult(frames={"688693.SH": _frame(real)})]
    )
    service = TickFlowDailyUpdateService(client)

    result = service.run(
        [{"code": "688693", "market": "SH"}],
        dry_run=False,
        mode="backfill",
    )

    assert result.results[0].status == "success"
    assert db.get_ohlc("688693") == real
    assert db.get_ohlc_metadata("688693")["source"] == "tickflow"


def test_full_refresh_trims_non_positive_adjusted_prefix_when_valid_suffix_is_long_enough(tmp_path):
    _setup_db(tmp_path)
    existing = _rows(3, 2)
    _save_existing("600066", existing, source="sina")
    fetched = _rows(1, 4)
    fetched[1]["low"] = -0.1
    client = _Client(
        [BatchFetchResult(frames={"600066.SH": _frame(fetched)})]
    )
    service = TickFlowDailyUpdateService(client)

    result = service.run(
        [{"code": "600066", "market": "SH"}],
        dry_run=False,
        mode="backfill",
    )

    assert result.results[0].status == "success"
    assert db.get_ohlc("600066") == fetched[2:]
    assert result.results[0].first_date == "2026-07-03"


def test_full_market_backfill_requests_stocks_in_bounded_chunks(tmp_path):
    _setup_db(tmp_path)
    stocks = [
        {"code": "600519", "market": "SH"},
        {"code": "601318", "market": "SH"},
        {"code": "000001", "market": "SZ"},
        {"code": "002396", "market": "SZ"},
        {"code": "300750", "market": "SZ"},
    ]
    client = _Client(
        [
            BatchFetchResult(
                frames={stock["code"] + "." + stock["market"]: _frame(_rows(1, 3)) for stock in stocks[:2]}
            ),
            BatchFetchResult(
                frames={stock["code"] + "." + stock["market"]: _frame(_rows(1, 3)) for stock in stocks[2:4]}
            ),
            BatchFetchResult(
                frames={stocks[4]["code"] + ".SZ": _frame(_rows(1, 3))}
            ),
        ]
    )
    service = TickFlowDailyUpdateService(
        client,
        history_days=1100,
        request_chunk_size=2,
    )

    result = service.run(stocks, dry_run=False, mode="backfill")

    assert [len(symbols) for symbols, _ in client.calls] == [2, 2, 1]
    assert [item.code for item in result.results] == [stock["code"] for stock in stocks]
    assert all(item.status == "success" for item in result.results)

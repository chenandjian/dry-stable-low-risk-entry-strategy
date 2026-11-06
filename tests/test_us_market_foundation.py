import sqlite3
import os
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from us_market.daily_data import diagnose, normalize_bars
from us_market.instruments import parse_directory, provider_symbol
from us_market.repository import USRepository


def bar(**changes):
    return dict(trade_date="2026-11-05", open=10, high=12, low=9,
                close=11, volume=1234, amount=0, **changes)


def test_symbols_preserve_share_classes_and_reject_foreign_suffixes():
    assert provider_symbol("brk.b") == "BRK.B.US"
    assert provider_symbol("BRK.B.US") == "BRK.B.US"
    for value in ["600000.SH", "AAPL.US.US", "", "AAPL,MSFT", "../AAPL"]:
        with pytest.raises(ValueError):
            provider_symbol(value)


def test_directory_excludes_footer_and_conservatively_classifies():
    text = ("ACT Symbol|Security Name|Exchange|ETF|Test Issue\n"
            "BRK.B|Berkshire Hathaway Inc. New Common Stock|N|N|N\n"
            "SPY|SPDR ETF Trust|P|Y|N\n"
            "ABC|Ambiguous security|N|N|N\n"
            "PREF|Example Preferred Stock|N|N|N\n"
            "TEST|Example Common Stock|N|N|Y\n"
            "File Creation Time: 1106202609:46||||\n")
    result = parse_directory(text, kind="otherlisted")
    assert result["file_created_raw"] == "1106202609:46"
    assert len(result["instruments"]) == 5
    a, b, c, d, e = result["instruments"]
    assert (a["symbol"], a["exchange"], a["eligible"]) == ("BRK.B.US", "NYSE", True)
    assert b["security_type"] == "ETF" and not b["eligible"]
    assert c["security_type"] == "UNKNOWN" and not c["eligible"]
    assert not d["eligible"] and not e["eligible"]
    with pytest.raises(ValueError):
        parse_directory("Symbol|Security Name\nAAPL|Apple", kind="nasdaqlisted")


def test_unsupported_directory_symbols_are_retained_for_mapping_audit():
    text = ("ACT Symbol|Security Name|Exchange|ETF|Test Issue\n"
            "ABC$A|Example Preferred Stock|N|N|N\n"
            "ABC|Example Common Stock|N|N|N\n")
    result = parse_directory(text, kind="otherlisted")["instruments"]
    assert result[0]["symbol"] is None
    assert result[0]["mapping_status"] == "UNSUPPORTED_SYMBOL"
    assert result[0]["raw"]["ACT Symbol"] == "ABC$A"
    assert not result[0]["eligible"]
    assert result[1]["eligible"]


def test_warrants_mentioning_common_stock_are_not_eligible():
    text = ("Symbol|Security Name|ETF|Test Issue\n"
            "ABCW|Example Warrants to purchase Common Stock|N|N\n")
    result = parse_directory(text, kind="nasdaqlisted")["instruments"][0]
    assert result["security_type"] == "UNKNOWN"
    assert result["eligible"] is False


def test_normalize_keeps_volume_and_missing_amount_unknown():
    rows = normalize_bars([bar()])
    assert rows[0]["volume"] == 1234
    assert rows[0]["turnover"] is None
    assert "estimated_turnover" not in rows[0]
    positive = bar()
    positive["amount"] = 13574
    assert normalize_bars([positive])[0]["turnover"] == 13574


@pytest.mark.parametrize("changes", [
    {"close": float("nan")}, {"volume": -1}, {"high": 10},
    {"low": 0}, {"trade_date": "2026-02-30"}, {"amount": -1},
    {"volume": True},
])
def test_invalid_bars_rejected(changes):
    value = bar()
    value.update(changes)
    with pytest.raises(ValueError):
        normalize_bars([value])


def test_empty_and_duplicate_dates_rejected():
    for rows in [[], [bar(), bar()]]:
        with pytest.raises(ValueError):
            normalize_bars(rows)


def test_diagnostic_uses_free_and_blocks_formal_scan(tmp_path, monkeypatch):
    calls = []
    import tickflow

    class SDK:
        _client = SimpleNamespace(api_key="must-not-be-used")
        klines = SimpleNamespace(get=lambda symbol, **kw: calls.append((symbol, kw)) or [bar()])
        def close(self):
            calls.append("closed")

    monkeypatch.setenv("TICKFLOW_API_KEY", "must-not-be-used")
    monkeypatch.setattr(tickflow.TickFlow, "free", lambda **kw: SDK())
    repo = USRepository(tmp_path / "us.db")
    result = diagnose(repo, "brk.b", count=10, adjustment="forward")
    assert calls[0][0] == "BRK.B.US"
    assert calls[0][1]["adjust"] == "forward"
    assert calls[-1] == "closed"
    assert result["formal_scan_allowed"] is False
    assert "VOLUME_BASIS_UNVERIFIED" in result["blocking_reasons"]
    assert result["volume_basis"] == "UNKNOWN"
    assert result["price_basis"] == "PROVIDER_FORWARD_UNVERIFIED"
    assert result["missing_turnover_rows"] == 1
    assert repo.get_snapshot(result["snapshot_id"]) == result
    assert SDK._client.api_key is None


def test_real_sdk_never_sends_environment_key_or_uses_paid_url(monkeypatch):
    from us_market.daily_data import _create_free_sdk
    monkeypatch.setenv("TICKFLOW_API_KEY", "must-not-be-sent")
    monkeypatch.setenv("TICKFLOW_FREE_BASE_URL", "https://api.tickflow.org")
    sdk = _create_free_sdk()
    try:
        assert sdk._client.base_url == "https://free-api.tickflow.org"
        assert "x-api-key" not in sdk._client._build_headers()
        assert os.environ["TICKFLOW_API_KEY"] == "must-not-be-sent"
    finally:
        sdk.close()


def test_failed_or_mismatched_response_closes_sdk_and_does_not_write(tmp_path, monkeypatch):
    import tickflow
    repo = USRepository(tmp_path / "us.db")
    closed = []

    class SDK:
        _client = SimpleNamespace(api_key=None)
        klines = SimpleNamespace(get=lambda *a, **k: [dict(bar(), symbol="MSFT.US")])
        def close(self):
            closed.append(True)

    monkeypatch.setattr(tickflow.TickFlow, "free", lambda **kw: SDK())
    with pytest.raises(ValueError, match="symbol"):
        diagnose(repo, "AAPL")
    assert closed == [True]
    with sqlite3.connect(repo.path) as conn:
        assert conn.execute("SELECT count(*) FROM us_diagnostic_snapshots").fetchone()[0] == 0


def test_us_operations_do_not_change_cn_global_connection(tmp_path, monkeypatch):
    from scanner import db
    sentinel = object()
    monkeypatch.setattr(db, "DB_PATH", "cn-original.db")
    monkeypatch.setattr(db._local, "conn", sentinel, raising=False)
    repo = USRepository(tmp_path / "us.db")
    assert repo.get_snapshot("missing") is None
    assert db.DB_PATH == "cn-original.db"
    assert db._local.conn is sentinel


def test_repository_isolation_idempotency_and_basis(tmp_path):
    first = USRepository(tmp_path / "one.db")
    second = USRepository(tmp_path / "two.db")
    snapshot = dict(snapshot_id="one", symbol="AAPL.US", adjustment="none",
                    price_basis="PROVIDER_NONE_UNVERIFIED", volume_basis="UNKNOWN",
                    source="tickflow_free", fetched_at="2026-11-06T00:00:00+00:00",
                    formal_scan_allowed=False, rows=normalize_bars([bar()]))
    first.save_snapshot(snapshot)
    first.save_snapshot(snapshot)
    assert first.get_snapshot("one") == snapshot
    assert second.get_snapshot("one") is None
    changed = dict(snapshot, snapshot_id="two", adjustment="forward")
    first.save_snapshot(changed)
    assert first.get_snapshot("one")["adjustment"] == "none"
    assert first.get_snapshot("two")["adjustment"] == "forward"
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda n: first.save_snapshot(dict(snapshot, snapshot_id=str(n))), range(12)))
        list(pool.map(lambda _: first.save_snapshot(dict(snapshot, snapshot_id="shared")), range(12)))
    assert first.get_snapshot("shared") == dict(snapshot, snapshot_id="shared")
    assert first.get_snapshot("11")["rows"][0]["volume"] == 1234
    with pytest.raises(ValueError):
        first.save_snapshot(dict(snapshot, rows=[dict(snapshot["rows"][0], close=float("nan"))]))
    assert first.get_snapshot("one") == snapshot


def test_snapshot_identity_is_immutable(tmp_path):
    repo = USRepository(tmp_path / "us.db")
    snapshot = dict(snapshot_id="same", symbol="AAPL.US", adjustment="none",
                    formal_scan_allowed=False, rows=normalize_bars([bar()]))
    repo.save_snapshot(snapshot)
    with pytest.raises(ValueError, match="immutable"):
        repo.save_snapshot(dict(snapshot, adjustment="forward"))
    assert repo.get_snapshot("same") == snapshot


def test_cli_continues_after_failure_and_returns_nonzero(tmp_path, monkeypatch, capsys):
    import us_market.__main__ as cli

    def fake(repo, symbol, **kwargs):
        if symbol == "BAD":
            raise ValueError("missing data")
        return {"symbol": symbol, "rows": [bar()], "formal_scan_allowed": False}

    monkeypatch.setattr(cli, "diagnose", fake)
    assert cli.main(["BAD", "AAPL", "--db", str(tmp_path / "us.db")]) == 1
    output = capsys.readouterr()
    assert "FAILED" in output.err and "AAPL" in output.out
    assert '"rows"' not in output.out


def test_repository_refuses_cn_database_without_modifying_it(tmp_path):
    path = tmp_path / "cn.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE daily_ohlc(code TEXT)")
        conn.execute("INSERT INTO daily_ohlc VALUES ('600000')")
    with pytest.raises(ValueError, match="non-US"):
        USRepository(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT * FROM daily_ohlc").fetchall() == [("600000",)]
        assert conn.execute("SELECT count(*) FROM sqlite_master WHERE name LIKE 'us_%'").fetchone()[0] == 0


def test_repository_cannot_store_non_us_or_formal_snapshot(tmp_path):
    repo = USRepository(tmp_path / "us.db")
    for snapshot in [dict(symbol="600000.SH"), dict(symbol="AAPL.US", formal_scan_allowed=True)]:
        with pytest.raises(ValueError):
            repo.save_snapshot(snapshot)

import pytest

from strategy6.backtest.data import audit_ohlc_rows, build_data_fingerprint, slice_visible_rows


ROWS = [
    {"date": "2025-01-02", "open": 10.0, "high": 10.5, "low": 9.8, "close": 10.2, "volume": 100},
    {"date": "2025-01-03", "open": 10.2, "high": 10.6, "low": 10.0, "close": 10.4, "volume": 120},
]


def test_data_audit_and_fingerprint_are_deterministic():
    audit = audit_ohlc_rows(ROWS)
    assert audit["valid"] is True
    assert audit["rows"] == 2
    assert audit["min_date"] == "2025-01-02"
    assert build_data_fingerprint({"000001": ROWS}) == build_data_fingerprint({"000001": list(ROWS)})


def test_data_audit_rejects_duplicate_date_and_illegal_ohlc():
    duplicate = ROWS + [dict(ROWS[-1])]
    assert "DUPLICATE_DATE" in audit_ohlc_rows(duplicate)["errors"]
    broken = [dict(ROWS[0], high=9.0)]
    assert "ILLEGAL_OHLC" in audit_ohlc_rows(broken)["errors"]


def test_visible_slice_never_returns_future_rows():
    assert [row["date"] for row in slice_visible_rows(ROWS, "2025-01-02")] == ["2025-01-02"]


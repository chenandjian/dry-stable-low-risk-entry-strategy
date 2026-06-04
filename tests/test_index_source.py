from scanner.index_source import normalize_index_ohlc


def test_normalize_index_ohlc_sorts_and_keeps_required_fields():
    raw = [
        {"date": "2026-06-02", "open": 101, "high": 103, "low": 100, "close": 102, "volume": 20},
        {"date": "2026-06-01", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 10},
    ]

    result = normalize_index_ohlc(raw)

    assert [d["date"] for d in result] == ["2026-06-01", "2026-06-02"]
    assert result[0]["close"] == 101
    assert result[1]["volume"] == 20


def test_normalize_index_ohlc_skips_incomplete_rows():
    raw = [
        {"date": "2026-06-01", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 10},
        {"date": "2026-06-02", "open": 101, "high": 103, "close": 102, "volume": 20},
    ]

    result = normalize_index_ohlc(raw)

    assert len(result) == 1
    assert result[0]["date"] == "2026-06-01"

import pytest

from strategy4.topic_index_source import TopicIndexSourceError, normalize_topic_index_rows


def test_normalize_ths_topic_index_rows_accepts_realistic_columns():
    rows = normalize_topic_index_rows(
        [
            {
                "日期": "2026-06-26",
                "开盘价": "100.0",
                "最高价": "108.0",
                "最低价": "99.5",
                "收盘价": "106.0",
                "成交量": "123456",
                "成交额": "987654321",
                "涨跌幅": "3.5%",
            },
        ],
        source="akshare_ths",
    )

    assert rows == [{
        "date": "2026-06-26",
        "open": 100.0,
        "high": 108.0,
        "low": 99.5,
        "close": 106.0,
        "volume": 123456.0,
        "amount": 987654321.0,
        "turnover": 987654321.0,
        "change_pct": 0.035,
        "raw_snapshot": {
            "日期": "2026-06-26",
            "开盘价": "100.0",
            "最高价": "108.0",
            "最低价": "99.5",
            "收盘价": "106.0",
            "成交量": "123456",
            "成交额": "987654321",
            "涨跌幅": "3.5%",
        },
    }]


def test_normalize_eastmoney_topic_index_rows_accepts_realistic_columns():
    rows = normalize_topic_index_rows(
        [
            {
                "日期": "2026-06-26",
                "开盘": 100,
                "最高": 110,
                "最低": 99,
                "收盘": 108,
                "成交量": 1000,
                "成交额": 2000,
                "换手率": "1.2%",
                "涨跌幅": 4.2,
            },
        ],
        source="akshare_eastmoney",
    )

    assert rows[0]["date"] == "2026-06-26"
    assert rows[0]["open"] == 100.0
    assert rows[0]["high"] == 110.0
    assert rows[0]["low"] == 99.0
    assert rows[0]["close"] == 108.0
    assert rows[0]["turnover"] == 0.012
    assert rows[0]["change_pct"] == 0.042


def test_normalize_topic_index_rows_rejects_invalid_ohlc():
    with pytest.raises(TopicIndexSourceError, match="INVALID_OHLC"):
        normalize_topic_index_rows(
            [{"日期": "2026-06-26", "开盘": 10, "最高": 9, "最低": 8, "收盘": 10}],
            source="akshare_eastmoney",
        )

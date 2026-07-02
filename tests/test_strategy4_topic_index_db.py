from datetime import date, datetime

import scanner.db as db


def test_strategy4_topic_index_ohlc_roundtrip_and_end_date_truncation(tmp_path):
    db.init_db(str(tmp_path / "test.db"))

    db.save_strategy4_topic_index_ohlc(
        topic_id="concept-ai",
        topic_name="AI算力",
        topic_type="concept",
        source="akshare_ths",
        rows=[
            {"date": "2026-06-20", "open": 100, "high": 105, "low": 99, "close": 104, "amount": 1000},
            {"date": "2026-06-21", "open": 104, "high": 110, "low": 103, "close": 109, "amount": 2000},
            {"date": "2026-06-22", "open": 109, "high": 111, "low": 108, "close": 110, "amount": 3000},
        ],
        source_topic_code="BK001",
        source_topic_name="AI算力",
    )

    rows = db.get_strategy4_topic_index_ohlc("concept-ai", end_date="2026-06-21", max_rows=10)

    assert [r["date"] for r in rows] == ["2026-06-20", "2026-06-21"]
    assert rows[-1]["source"] == "akshare_ths"
    assert rows[-1]["source_topic_code"] == "BK001"


def test_strategy4_topic_index_ohlc_is_idempotent_per_topic_source_date(tmp_path):
    db.init_db(str(tmp_path / "test.db"))

    db.save_strategy4_topic_index_ohlc(
        topic_id="concept-ai",
        topic_name="AI算力",
        topic_type="concept",
        source="akshare_ths",
        rows=[{"date": "2026-06-20", "open": 100, "high": 105, "low": 99, "close": 104}],
    )
    db.save_strategy4_topic_index_ohlc(
        topic_id="concept-ai",
        topic_name="AI算力",
        topic_type="concept",
        source="akshare_ths",
        rows=[{"date": "2026-06-20", "open": 100, "high": 106, "low": 99, "close": 105}],
    )

    rows = db.get_strategy4_topic_index_ohlc("concept-ai")

    assert len(rows) == 1
    assert rows[0]["close"] == 105


def test_strategy4_topic_index_ohlc_serializes_date_values_in_raw_snapshot(tmp_path):
    db.init_db(str(tmp_path / "test.db"))

    db.save_strategy4_topic_index_ohlc(
        topic_id="industry-component",
        topic_name="元件",
        topic_type="industry",
        source="akshare_ths",
        rows=[{
            "date": "2026-07-01",
            "open": 100,
            "high": 105,
            "low": 99,
            "close": 104,
            "raw_snapshot": {
                "日期": date(2026, 7, 1),
                "更新时间": datetime(2026, 7, 1, 15, 0, 1),
            },
        }],
    )

    rows = db.get_strategy4_topic_index_ohlc("industry-component")

    assert rows[0]["raw_snapshot"]["日期"] == "2026-07-01"
    assert rows[0]["raw_snapshot"]["更新时间"] == "2026-07-01T15:00:01"


def test_strategy4_topic_index_fetch_status_records_failures(tmp_path):
    db.init_db(str(tmp_path / "test.db"))

    db.save_strategy4_topic_index_fetch_status(
        topic_id="concept-ai",
        topic_name="AI算力",
        topic_type="concept",
        source="akshare_ths",
        status="source_failed",
        error_code="SOURCE_FAILED",
        error_message="timeout",
        rows_count=0,
    )

    status = db.get_latest_strategy4_topic_index_fetch_status("concept-ai")

    assert status["status"] == "source_failed"
    assert status["error_code"] == "SOURCE_FAILED"
    assert status["error_message"] == "timeout"

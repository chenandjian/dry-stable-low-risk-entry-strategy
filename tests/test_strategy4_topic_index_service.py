from datetime import datetime

import scanner.db as db
import strategy4.topic_index_service as service_mod
from strategy4.topic_index_service import TopicIndexService, _target_trade_date


def test_target_trade_date_uses_latest_complete_weekday_after_close_confirm():
    assert _target_trade_date(datetime(2026, 7, 2, 15, 11)) == "2026-07-02"
    assert _target_trade_date(datetime(2026, 7, 2, 9, 0)) == "2026-07-01"
    assert _target_trade_date(datetime(2026, 7, 6, 9, 0)) == "2026-07-03"


def test_topic_index_service_refetches_stale_cache(tmp_path, monkeypatch):
    db.init_db(str(tmp_path / "test.db"))
    db.save_strategy4_topic_index_ohlc(
        topic_id="concept:AI算力",
        topic_name="AI算力",
        topic_type="concept",
        source="fixture",
        rows=[
            {"date": f"2000-01-{idx + 1:02d}", "open": 100, "high": 101, "low": 99, "close": 100 + idx * 0.1}
            for idx in range(10)
        ],
    )
    called = {"fetch": False}

    def fake_fetch_topic_index_ohlc(**kwargs):
        called["fetch"] = True
        return [
            {"date": f"2099-01-{idx + 1:02d}", "open": 100, "high": 101 + idx, "low": 99, "close": 100 + idx, "amount": 1000 + idx}
            for idx in range(10)
        ], {"source": "fixture", "source_topic_name": "AI算力"}

    monkeypatch.setattr(service_mod, "fetch_topic_index_ohlc", fake_fetch_topic_index_ohlc)

    ctx = TopicIndexService({"topic_index": {"min_required_rows": 10, "history_days": 10}}).ensure_topic_index_context({
        "topic_id": "concept:AI算力",
        "topic_name": "AI算力",
        "topic_type": "concept",
    })

    assert called["fetch"] is True
    assert ctx["observed"] is True
    assert ctx["latest_date"] == "2099-01-10"

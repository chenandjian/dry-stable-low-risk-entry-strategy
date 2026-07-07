import scanner.db as db

from strategy4.derived_topic_detector import derive_hot_topics_for_date


def test_derived_hot_topics_use_topic_index_only_until_evaluation_date(tmp_path):
    db.init_db(str(tmp_path / "test.db"))
    db.save_strategy4_topic_index_ohlc(
        topic_id="concept:AI算力",
        topic_name="AI算力",
        topic_type="concept",
        source="fixture",
        rows=_topic_rows_with_future_spike(),
    )
    db.save_strategy4_topic_members(
        topic_id="concept:AI算力",
        topic_name="AI算力",
        topic_type="concept",
        source="fixture",
        membership_snapshot_date="2026-07-02",
        membership_mode="current_members_proxy",
        members=[
            {"code": "300750", "name": "宁德时代"},
            {"code": "688981", "name": "中芯国际"},
        ],
    )
    db.save_ohlc("300750", _member_rows("2026-04-01", base=10.0, step=0.12, future_step=5.0))
    db.save_ohlc("688981", _member_rows("2026-04-01", base=20.0, step=-0.02, future_step=8.0))

    topics = derive_hot_topics_for_date(
        "2026-06-20",
        {
            "derived_source": {
                "topic_top_n": 5,
                "max_topics_per_day": 5,
                "min_confirmed_topic_hot_score": 60,
                "min_topic_hot_score": 50,
                "min_topic_index_rows": 20,
                "min_breadth_ratio": 0.1,
            }
        },
    )

    assert len(topics) == 1
    topic = topics[0]
    assert topic["source"] == "historical_kline_derived"
    assert topic["snapshot_source"] == "historical_kline_derived"
    assert topic["source_modes"] == ["historical_kline_derived"]
    assert topic["topic_index_latest_date"] == "2026-06-20"
    assert topic["raw_snapshot"]["topic_index_context"]["latest_date"] == "2026-06-20"
    assert topic["raw_snapshot"]["topic_index_context"]["topic_return_1d"] < 0.10
    assert topic["membership_mode"] == "current_members_proxy"
    assert topic["derived_hot_score"] >= 60
    assert topic["status"] == "CONFIRMED_HOT"


def _topic_rows_with_future_spike():
    rows = []
    for idx in range(82):
        close = 100 + idx * 0.35
        date = f"2026-04-{idx + 1:02d}" if idx < 30 else f"2026-05-{idx - 29:02d}" if idx < 61 else f"2026-06-{idx - 60:02d}"
        rows.append({
            "date": date,
            "open": close - 0.2,
            "high": close + 0.8,
            "low": close - 0.8,
            "close": close,
            "amount": 1_000_000 + idx * 20_000,
        })
    rows.append({"date": "2026-06-23", "open": 130, "high": 210, "low": 128, "close": 205, "amount": 99_000_000})
    return rows


def _member_rows(start_date, *, base, step, future_step):
    rows = []
    for idx in range(82):
        close = base + idx * step
        date = f"2026-04-{idx + 1:02d}" if idx < 30 else f"2026-05-{idx - 29:02d}" if idx < 61 else f"2026-06-{idx - 60:02d}"
        rows.append({
            "date": date,
            "open": close * 0.99,
            "high": close * 1.02,
            "low": close * 0.98,
            "close": close,
            "volume": 1_000_000 + idx * 1000,
            "turnover": close * (1_000_000 + idx * 1000),
        })
    rows.append({
        "date": "2026-06-23",
        "open": base + 82 * future_step,
        "high": base + 83 * future_step,
        "low": base + 81 * future_step,
        "close": base + 83 * future_step,
        "volume": 9_000_000,
        "turnover": (base + 83 * future_step) * 9_000_000,
    })
    return rows

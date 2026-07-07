import scanner.db as db

from strategy4.derived_leader_detector import derive_leaders_for_topic


def test_derived_leaders_rank_by_history_before_evaluation_date_and_mark_membership_proxy(tmp_path):
    db.init_db(str(tmp_path / "test.db"))
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
    db.save_ohlc("300750", _stock_rows(strong=True))
    db.save_ohlc("688981", _stock_rows(strong=False, future_spike=True))

    leaders = derive_leaders_for_topic(
        {
            "topic_id": "concept:AI算力",
            "topic_name": "AI算力",
            "topic_type": "concept",
            "raw_snapshot": {
                "topic_index_context": {
                    "topic_return_5d": 0.03,
                    "topic_return_10d": 0.08,
                    "topic_return_20d": 0.12,
                }
            },
        },
        evaluation_date="2026-06-20",
        config={"derived_source": {"max_leaders_per_topic": 2, "min_member_count": 1}},
    )

    assert leaders[0]["code"] == "300750"
    assert leaders[0]["source"] == "historical_kline_derived"
    assert leaders[0]["membership_mode"] == "current_members_proxy"
    assert leaders[0]["raw_snapshot"]["leader_rs_10d"] > 0
    assert leaders[0]["raw_snapshot"]["latest_date"] == "2026-06-20"
    assert leaders[1]["code"] == "688981"
    assert leaders[1]["raw_snapshot"]["latest_date"] == "2026-06-20"
    assert leaders[1]["return_20d"] < leaders[0]["return_20d"]


def test_derived_leaders_return_unobserved_when_members_missing(tmp_path):
    db.init_db(str(tmp_path / "test.db"))

    leaders = derive_leaders_for_topic(
        {"topic_id": "concept:AI算力", "topic_name": "AI算力", "topic_type": "concept"},
        evaluation_date="2026-06-20",
        config={"derived_source": {"min_member_count": 1}},
    )

    assert leaders == []


def _stock_rows(*, strong, future_spike=False):
    rows = []
    for idx in range(82):
        date = f"2026-04-{idx + 1:02d}" if idx < 30 else f"2026-05-{idx - 29:02d}" if idx < 61 else f"2026-06-{idx - 60:02d}"
        close = 10 + idx * (0.2 if strong else 0.01)
        rows.append({
            "date": date,
            "open": close * 0.99,
            "high": close * 1.03,
            "low": close * 0.98,
            "close": close,
            "volume": 2_000_000 + idx * (10_000 if strong else 1000),
            "turnover": close * (2_000_000 + idx * (10_000 if strong else 1000)),
        })
    if future_spike:
        rows.append({
            "date": "2026-06-23",
            "open": 50,
            "high": 60,
            "low": 49,
            "close": 58,
            "volume": 20_000_000,
            "turnover": 58 * 20_000_000,
        })
    return rows

import scanner.db as db

from strategy4.backtester import (
    run_strategy4_parameter_experiments,
    run_strategy4_snapshot_backtest,
)


def test_strategy4_backtest_marks_missing_snapshot_unobserved(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    db.save_ohlc("300750", _bars_for_buyable_second_wave())

    result = run_strategy4_snapshot_backtest(
        db_path=db_path,
        start_date="2026-06-20",
        end_date="2026-06-20",
        config_snapshot={"strategy4": {}},
    )

    assert result.summary.unobserved_snapshot_days == 1
    assert result.signals == []
    assert result.unobserved[0].reason_code == "UNOBSERVED_TOPIC_SNAPSHOT"


def test_strategy4_execution_rejects_one_word_limit_up_entry(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    rows = _bars_for_buyable_second_wave()
    previous_close = rows[-1]["close"]
    limit_price = round(previous_close * 1.20, 2)
    rows.append({
        "date": "2026-06-23",
        "open": limit_price,
        "high": limit_price,
        "low": limit_price,
        "close": limit_price,
        "volume": 500_000,
        "turnover": limit_price * 500_000,
    })
    db.save_ohlc("300750", rows)
    _seed_strategy4_snapshot(db_path, task_id="s4-snap", date="2026-06-20", code="300750")

    result = run_strategy4_snapshot_backtest(
        db_path=db_path,
        start_date="2026-06-20",
        end_date="2026-06-20",
        config_snapshot={"strategy4": {"min_leader_strength_score": 60}},
    )

    assert len(result.opportunities) == 1
    opp = result.opportunities[0]
    assert opp.execution_model == "NEXT_OPEN"
    assert opp.exit_reason == "NO_ENTRY_LIMIT_UP_UNBUYABLE"
    assert opp.entry_price == 0


def test_strategy4_execution_rejects_t_limit_up_open_entry(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    rows = _bars_for_buyable_second_wave()
    previous_close = rows[-1]["close"]
    limit_price = round(previous_close * 1.20, 2)
    rows.append({
        "date": "2026-06-23",
        "open": limit_price,
        "high": limit_price,
        "low": round(limit_price * 0.96, 2),
        "close": limit_price,
        "volume": 2_000_000,
        "turnover": limit_price * 2_000_000,
    })
    db.save_ohlc("300750", rows)
    _seed_strategy4_snapshot(db_path, task_id="s4-snap", date="2026-06-20", code="300750")

    result = run_strategy4_snapshot_backtest(
        db_path=db_path,
        start_date="2026-06-20",
        end_date="2026-06-20",
        config_snapshot={"strategy4": {"min_leader_strength_score": 60}},
    )

    opp = result.opportunities[0]
    assert opp.exit_reason == "NO_ENTRY_OPEN_LIMIT_UNOBSERVED"
    assert opp.entry_price == 0


def test_strategy4_parameter_experiments_filter_observed_snapshots_only(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    rows = _bars_for_buyable_second_wave()
    rows.append({
        "date": "2026-06-23",
        "open": 16.5,
        "high": 17.2,
        "low": 16.2,
        "close": 17.0,
        "volume": 4_500_000,
        "turnover": 16.8 * 4_500_000,
    })
    db.save_ohlc("300750", rows)
    db.save_market_index_ohlc("sh000001", [
        {"date": "2026-06-20", "open": 1000, "high": 1010, "low": 990, "close": 1005},
        {"date": "2026-06-21", "open": 1005, "high": 1015, "low": 1000, "close": 1010},
    ])
    _seed_strategy4_snapshot(
        db_path,
        task_id="s4-snap",
        date="2026-06-20",
        code="300750",
        hot_score=92,
        leader_score=91,
    )

    experiments = run_strategy4_parameter_experiments(
        db_path=db_path,
        start_date="2026-06-20",
        end_date="2026-06-21",
        base_config={"strategy4": {}},
        experiment_grid=[
            {"name": "strict", "min_hot_topic_score": 95, "min_leader_strength_score": 95},
            {"name": "baseline", "min_hot_topic_score": 85, "min_leader_strength_score": 88},
        ],
    )

    assert experiments["strict"].summary.total_opportunities == 0
    assert experiments["baseline"].summary.total_opportunities == 1
    assert experiments["baseline"].summary.unobserved_snapshot_days == 1


def test_strategy4_backtest_market_index_metadata_is_truncated_at_evaluation_date(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    rows = _bars_for_buyable_second_wave()
    rows.append({
        "date": "2026-06-23",
        "open": 16.5,
        "high": 17.2,
        "low": 16.2,
        "close": 17.0,
        "volume": 4_500_000,
        "turnover": 16.8 * 4_500_000,
    })
    db.save_ohlc("300750", rows)
    db.save_market_index_ohlc("sz399006", [
        {"date": "2026-06-18", "open": 1000, "high": 1010, "low": 990, "close": 1005},
        {"date": "2026-06-20", "open": 1005, "high": 1020, "low": 1000, "close": 1018},
        {"date": "2026-06-23", "open": 1018, "high": 1200, "low": 1010, "close": 1190},
    ])
    _seed_strategy4_snapshot(db_path, task_id="s4-snap", date="2026-06-20", code="300750")

    result = run_strategy4_snapshot_backtest(
        db_path=db_path,
        start_date="2026-06-20",
        end_date="2026-06-20",
        config_snapshot={"strategy4": {"min_leader_strength_score": 60}},
    )

    snapshot = result.signals[0].evaluation_snapshot
    assert snapshot["market_index_symbol"] == "sz399006"
    assert snapshot["market_index_latest_date"] == "2026-06-20"
    assert snapshot["market_index_rows"] == 2


def _seed_strategy4_snapshot(
    db_path,
    *,
    task_id,
    date,
    code,
    hot_score=92,
    leader_score=91,
):
    db.init_db(db_path)
    db.create_scan_task(task_id, f"{date} 15:30:00", strategy_type="STRATEGY_4_HOT_LEADER_SECOND_WAVE")
    db.finish_scan_task(task_id, finished_at=f"{date} 15:31:00", candidates_count=0, elapsed_seconds=1.0)
    db.replace_strategy4_hot_topics(task_id, [{
        "topic_id": "concept-ai",
        "topic_name": "AI算力",
        "topic_type": "concept",
        "source": "fixture",
        "snapshot_time": f"{date} 15:30:00",
        "status": "CONFIRMED_HOT",
        "hot_topic_score": hot_score,
        "price_strength_score": 30,
        "amount_strength_score": 18,
        "fund_flow_score": 14,
        "breadth_score": 13,
        "leader_limit_score": 9,
        "breakout_score": 8,
        "signal_count": 5,
        "leading_stock_code": code,
        "leading_stock_name": "宁德时代",
    }])
    db.replace_strategy4_leaders(task_id, [{
        "topic_id": "concept-ai",
        "topic_name": "AI算力",
        "code": code,
        "name": "宁德时代",
        "leader_type": "SPACE_LEADER",
        "leader_strength_score": leader_score,
        "tradability_score": 80,
        "price_limit_rule": "PRICE_LIMIT_20CM",
        "limit_shape": "LIMIT_UP_CLOSE",
        "limit_pct": 0.20,
        "return_1d": 0.08,
        "return_5d": 0.20,
        "return_10d": 0.35,
        "return_20d": 0.50,
        "amount_1d": 500_000_000,
        "avg_amount_5d": 450_000_000,
        "avg_amount_10d": 400_000_000,
        "first_wave_max_amount": 800_000_000,
        "last_non_limit_amount": 600_000_000,
        "consecutive_limit_count": 1,
        "relative_strength_vs_topic": 0.08,
        "membership_source": "fixture",
        "status": "LEADER_CONFIRMED",
    }])


def _bars_for_buyable_second_wave():
    closes = [
        10.0, 10.2, 10.4, 10.6, 10.8,
        11.2, 12.4, 13.8, 15.2, 17.0,
        16.5, 15.8, 15.3, 15.2, 15.6,
        15.9, 16.1, 16.0, 16.2, 16.4,
    ]
    rows = []
    for idx, close in enumerate(closes):
        previous = closes[idx - 1] if idx else close
        open_ = previous * 0.995
        rows.append({
            "date": f"2026-06-{idx + 1:02d}",
            "open": round(open_, 2),
            "high": round(max(open_, close) * 1.02, 2),
            "low": round(min(open_, close) * 0.98, 2),
            "close": round(close, 2),
            "volume": 6_000_000 if idx < 10 else 3_000_000,
            "turnover": close * (6_000_000 if idx < 10 else 3_000_000),
        })
    rows[-1]["volume"] = 4_000_000
    rows[-1]["open"] = 15.9
    rows[-1]["low"] = 15.6
    rows[-1]["high"] = 16.6
    rows[9]["high"] = 24.0
    return rows

import scanner.db as db

from strategy4.backtester import (
    generate_strategy4_optimization_report,
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


def test_strategy4_backtest_derives_snapshot_when_live_snapshot_missing(tmp_path):
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
    db.save_strategy4_topic_index_ohlc(
        topic_id="concept-ai",
        topic_name="AI算力",
        topic_type="concept",
        source="fixture",
        rows=_derived_topic_rows(),
    )
    db.save_strategy4_topic_members(
        topic_id="concept-ai",
        topic_name="AI算力",
        topic_type="concept",
        source="fixture",
        membership_snapshot_date="2026-07-02",
        membership_mode="current_members_proxy",
        members=[{"code": "300750", "name": "宁德时代"}],
    )

    result = run_strategy4_snapshot_backtest(
        db_path=db_path,
        start_date="2026-06-20",
        end_date="2026-06-20",
        config_snapshot={
            "strategy4": {
                "min_hot_topic_score": 40,
                "min_hot_topic_signal_count": 1,
                "min_leader_strength_score": 40,
                "topic_index": {"min_required_rows": 20, "history_days": 60},
                "derived_source": {
                    "topic_top_n": 5,
                    "max_topics_per_day": 5,
                    "max_leaders_per_topic": 3,
                    "min_topic_index_rows": 20,
                    "min_member_count": 1,
                    "min_topic_hot_score": 40,
                    "min_confirmed_topic_hot_score": 40,
                    "min_breadth_ratio": 0.0,
                },
            }
        },
    )

    assert result.summary.unobserved_snapshot_days == 0
    assert result.summary.derived_snapshot_days == 1
    assert len(result.signals) == 1
    snapshot = result.signals[0].evaluation_snapshot
    assert snapshot["snapshot_source"] == "historical_kline_derived"
    assert snapshot["source_modes"] == ["historical_kline_derived"]
    assert snapshot["membership_mode"] == "current_members_proxy"
    assert snapshot["topic_index_latest_date"] == "2026-06-20"


def test_strategy4_backtest_marks_missing_derived_members_unobserved(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    db.save_strategy4_topic_index_ohlc(
        topic_id="concept-ai",
        topic_name="AI算力",
        topic_type="concept",
        source="fixture",
        rows=_derived_topic_rows(),
    )

    result = run_strategy4_snapshot_backtest(
        db_path=db_path,
        start_date="2026-06-20",
        end_date="2026-06-20",
        config_snapshot={
            "strategy4": {
                "min_hot_topic_score": 40,
                "min_hot_topic_signal_count": 1,
                "topic_index": {"min_required_rows": 20, "history_days": 60},
                "derived_source": {
                    "topic_top_n": 5,
                    "max_topics_per_day": 5,
                    "min_topic_index_rows": 20,
                    "min_member_count": 1,
                    "min_topic_hot_score": 40,
                    "min_confirmed_topic_hot_score": 40,
                    "min_breadth_ratio": 0.0,
                },
            }
        },
    )

    assert result.signals == []
    assert result.summary.unobserved_members_days == 1
    assert result.unobserved[0].reason_code == "UNOBSERVED_DERIVED_MEMBERS"


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


def test_strategy4_parameter_experiments_re_evaluate_no_buy_point_leaders(tmp_path):
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
    _seed_strategy4_snapshot(
        db_path,
        task_id="s4-snap",
        date="2026-06-20",
        code="300750",
        hot_score=92,
        leader_score=81,
        leader_status="HOT_TOPIC_NO_BUY_POINT",
    )

    experiments = run_strategy4_parameter_experiments(
        db_path=db_path,
        start_date="2026-06-20",
        end_date="2026-06-20",
        base_config={"strategy4": {}},
        experiment_grid=[
            {"name": "relaxed_leader", "min_hot_topic_score": 85, "min_leader_strength_score": 60},
        ],
    )

    assert experiments["relaxed_leader"].summary.total_opportunities == 1


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


def test_strategy4_backtest_marks_missing_topic_index_unobserved(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    db.save_ohlc("300750", _bars_for_buyable_second_wave())
    _seed_strategy4_snapshot(db_path, task_id="s4-snap", date="2026-06-20", code="300750", include_topic_index=False)

    result = run_strategy4_snapshot_backtest(
        db_path=db_path,
        start_date="2026-06-20",
        end_date="2026-06-20",
        config_snapshot={"strategy4": {"min_leader_strength_score": 60}},
    )

    assert result.signals == []
    assert result.opportunities == []
    assert result.unobserved[0].reason_code == "UNOBSERVED_TOPIC_INDEX"


def test_strategy4_backtest_topic_index_metadata_is_truncated_at_evaluation_date(tmp_path):
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
    db.save_strategy4_topic_index_ohlc(
        topic_id="concept-ai",
        topic_name="AI算力",
        topic_type="concept",
        source="fixture",
        rows=[
            {"date": "2026-06-18", "open": 100, "high": 101, "low": 99, "close": 100, "amount": 1000},
            {"date": "2026-06-20", "open": 100, "high": 105, "low": 99, "close": 104, "amount": 2000},
            {"date": "2026-06-23", "open": 104, "high": 130, "low": 104, "close": 128, "amount": 9000},
        ],
    )
    _seed_strategy4_snapshot(db_path, task_id="s4-snap", date="2026-06-20", code="300750", include_topic_index=False)

    result = run_strategy4_snapshot_backtest(
        db_path=db_path,
        start_date="2026-06-20",
        end_date="2026-06-20",
        config_snapshot={"strategy4": {"min_leader_strength_score": 60, "topic_index": {"min_required_rows": 2}}},
    )

    snapshot = result.signals[0].evaluation_snapshot
    assert snapshot["topic_index_latest_date"] == "2026-06-20"
    assert snapshot["topic_index_rows"] == 2
    assert snapshot["topic_return_1d"] == 0.04


def test_strategy4_optimization_report_reflects_nonzero_opportunities(tmp_path):
    db_path = str(tmp_path / "test.db")
    report_path = str(tmp_path / "report.md")
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
    _seed_strategy4_snapshot(db_path, task_id="s4-snap", date="2026-06-20", code="300750")

    generate_strategy4_optimization_report(
        db_path=db_path,
        start_date="2026-06-20",
        end_date="2026-06-20",
        base_config={"strategy4": {}},
        experiment_grid=[{"name": "baseline", "min_leader_strength_score": 60}],
        report_path=report_path,
    )

    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "所有实验组均为 0 信号、0 机会、0 入场" not in report
    assert "不可观察率" in report
    assert "平均盈利" in report
    assert "月度分布" in report
    assert "## 机会明细" in report
    assert "板块K线日期" in report


def _seed_strategy4_snapshot(
    db_path,
    *,
    task_id,
    date,
    code,
    hot_score=92,
    leader_score=91,
    include_topic_index=True,
    leader_status="LEADER_CONFIRMED",
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
        "status": leader_status,
    }])
    if include_topic_index:
        db.save_strategy4_topic_index_ohlc(
            topic_id="concept-ai",
            topic_name="AI算力",
            topic_type="concept",
            source="fixture",
            rows=[
                {
                    "date": f"2026-04-{idx + 1:02d}" if idx < 30 else f"2026-05-{idx - 29:02d}",
                    "open": 100 + idx * 0.1,
                    "high": 101 + idx * 0.1,
                    "low": 99 + idx * 0.1,
                    "close": 100 + idx * 0.1,
                    "amount": 1000 + idx * 10,
                }
                for idx in range(60)
            ],
        )


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


def _derived_topic_rows():
    rows = []
    for idx in range(20):
        close = 100 + idx * 0.8
        rows.append({
            "date": f"2026-06-{idx + 1:02d}",
            "open": close - 0.2,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "amount": 1_000_000_000 + idx * 30_000_000,
        })
    rows.append({
        "date": "2026-06-23",
        "open": 130,
        "high": 180,
        "low": 128,
        "close": 175,
        "amount": 30_000_000_000,
    })
    return rows

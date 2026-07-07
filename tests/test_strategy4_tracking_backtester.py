from strategy4.backtest_models import Strategy4BacktestSignal
from strategy4.backtester import run_strategy4_snapshot_backtest


def test_strategy4_backtest_replays_tracking_pool_after_original_hot_day(tmp_path, monkeypatch):
    import scanner.db as db

    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)

    dates = ["2026-06-01", "2026-06-20"]
    monkeypatch.setattr("strategy4.backtester._evaluation_dates", lambda start, end: dates)
    monkeypatch.setattr("strategy4.backtester._snapshot_task_for_exact_date", lambda evaluation_date: None)

    def fake_derived(evaluation_date, cfg):
        if evaluation_date == "2026-06-01":
            return ([{
                "topic_id": "concept-ai",
                "topic_name": "AI算力",
                "topic_type": "concept",
                "status": "CONFIRMED_HOT",
                "hot_topic_score": 80,
                "signal_count": 3,
                "topic_index_phase": "MAIN_TREND",
                "source_modes": ["historical_kline_derived"],
                "membership_mode": "current_members_proxy",
            }], [{
                "topic_id": "concept-ai",
                "topic_name": "AI算力",
                "code": "300750",
                "name": "宁德时代",
                "status": "LEADER_CONFIRMED",
                "leader_type": "SPACE_LEADER",
                "leader_strength_score": 72,
                "tradability_score": 80,
                "source_modes": ["historical_kline_derived"],
                "membership_mode": "current_members_proxy",
            }])
        return ([], [])

    monkeypatch.setattr("strategy4.backtester._derived_snapshots_for_date", fake_derived)
    monkeypatch.setattr("strategy4.backtester._topic_index_context_for_backtest", lambda topic, cfg, evaluation_date: {
        "observed": True,
        "source": "fixture",
        "latest_date": evaluation_date,
        "rows": 60,
        "status": "observed",
        "phase": "PULLBACK_REPAIR",
        "topic_index_trend_score": 12,
        "topic_index_breakout_score": 5,
        "topic_index_volume_score": 5,
        "amount_ratio_5_20": 1.2,
        "drawdown_from_high_20": -0.06,
    })

    def fake_evaluate(topic, leader, engine, cfg, evaluation_date, topic_index_context=None, ohlc_cache=None):
        if evaluation_date != "2026-06-20":
            return None
        return Strategy4BacktestSignal(
            code=leader["code"],
            name=leader["name"],
            topic_id=topic["topic_id"],
            topic_name=topic["topic_name"],
            evaluation_date=evaluation_date,
            hot_topic_score=topic.get("hot_topic_score", 0),
            leader_strength_score=leader.get("leader_strength_score", 0),
            tradability_score=leader.get("tradability_score", 0),
            reward_risk_ratio=2.5,
            risk_ratio=0.08,
            evaluation_snapshot={
                "snapshot_date": evaluation_date,
                "candidate_origin": "tracking_pool",
            },
        )

    monkeypatch.setattr("strategy4.backtester._evaluate_leader_snapshot", fake_evaluate)

    result = run_strategy4_snapshot_backtest(
        db_path=db_path,
        start_date="2026-06-01",
        end_date="2026-06-20",
        config_snapshot={
            "strategy4": {
                "min_hot_topic_score": 60,
                "min_hot_topic_signal_count": 1,
                "min_leader_strength_score": 40,
                "tracking": {"enabled": True, "max_calendar_days": 120},
            }
        },
    )

    assert result.summary.tracking_pool_topics == 1
    assert result.summary.tracking_pool_leaders == 1
    assert result.summary.tracking_pool_opportunities == 1
    assert result.signals[0].evaluation_snapshot["candidate_origin"] == "tracking_pool"
    assert result.signals[0].evaluation_snapshot["topic_first_detected_date"] == "2026-06-01"
    assert result.signals[0].evaluation_snapshot["tracking_age_days"] == 19

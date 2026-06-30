"""策略3本地 DB 回测持久化测试。"""
from __future__ import annotations

import json

from scanner import db
from strategy3.backtest_models import Strategy3BacktestSignal


def _init_tmp_db(tmp_path):
    path = tmp_path / "strategy3_backtest.db"
    db.init_db(str(path))
    return db.get_conn()


def _signal(code="000001", date="2026-01-05", score=88):
    return Strategy3BacktestSignal(
        code=code,
        name="样本",
        evaluation_date=date,
        evaluation_index=10,
        total_score=score,
        level="核心候选",
        current_close=10.0,
        trend_score=22,
        pullback_score=21,
        volume_stability_score=18,
        second_breakout_score=13,
        risk_reward_score=14,
        trade_state="LOW_ABSORB",
        trade_state_label="低吸",
        trade_quality_score=82,
        volume_dry_score=17,
        price_stability_score=16,
        cannot_fall_score=15,
        balance_powerless_score=13,
        support_price=9.7,
        stop_loss=9.5,
        target_price=11.5,
        risk_ratio=0.05,
        rr1=3.0,
        pullback_pct=0.15,
        volume_ratio_5_20=0.55,
        evaluation_snapshot={"date": date, "score": score},
    )


def _opportunity(
    code="000001",
    first_date="2026-01-05",
    score=88,
    exit_reason="TARGET",
    realized_return=None,
    market_index_symbol="sz399001",
    market_return_20=0.02,
    market_return_60=0.03,
    market_above_ma20=True,
    market_above_ma60=True,
):
    entered = not exit_reason.startswith("NO_ENTRY")
    if realized_return is None:
        realized_return = 0.127451 if exit_reason == "TARGET" else 0
    return {
        "code": code,
        "name": "样本",
        "first_detected_date": first_date,
        "last_detected_date": first_date,
        "consecutive_hit_days": 1,
        "first_score": score,
        "max_score": score,
        "level": "核心候选",
        "trade_state": "LOW_ABSORB",
        "trade_state_label": "低吸",
        "trade_quality_score": 82,
        "entry_close": 10.0,
        "support_price": 9.7,
        "stop_loss": 9.5,
        "target_price": 11.5,
        "risk_ratio": 0.05,
        "rr1": 3.0,
        "trend_score": 22,
        "pullback_score": 21,
        "volume_stability_score": 18,
        "second_breakout_score": 13,
        "risk_reward_score": 14,
        "volume_dry_score": 17,
        "price_stability_score": 16,
        "cannot_fall_score": 15,
        "balance_powerless_score": 13,
        "pullback_pct": 0.15,
        "volume_ratio_5_20": 0.55,
        "evaluation_snapshot": json.dumps({
            "score": score,
            "market_index_symbol": market_index_symbol,
            "market_index_name": "深证成指" if market_index_symbol == "sz399001" else "创业板指",
            "market_return_20": market_return_20,
            "market_return_60": market_return_60,
            "market_above_ma20": market_above_ma20,
            "market_above_ma60": market_above_ma60,
            "market_data_mode": "local_equal_weight_proxy",
        }, ensure_ascii=False),
        "horizon_5": json.dumps({"result": "SUCCESS", "end_return": 0.08}),
        "horizon_10": json.dumps({"result": "SUCCESS", "end_return": 0.12}),
        "horizon_20": json.dumps({"result": "SUCCESS", "end_return": 0.15}),
        "signal_count": 1,
        "execution_model": "NEXT_OPEN",
        "entry_date": "2026-01-06" if entered else "",
        "entry_price": 10.2 if entered else 0,
        "exit_date": "2026-01-10" if exit_reason != "NO_ENTRY_GAP_TOO_HIGH" else "",
        "exit_price": 11.5 if exit_reason == "TARGET" else 9.5 if exit_reason == "STOP" else 0,
        "exit_reason": exit_reason,
        "realized_return": realized_return,
        "mark_to_market_end_return": 0.10,
        "holding_days": 4 if exit_reason in {"TARGET", "STOP"} else 0,
        "available_forward_days": 20,
    }


def test_strategy3_backtest_tables_are_created(tmp_path):
    conn = _init_tmp_db(tmp_path)

    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }

    assert {
        "strategy3_backtest_tasks",
        "strategy3_backtest_task_stocks",
        "strategy3_backtest_signals",
        "strategy3_backtest_opportunities",
        "strategy3_backtest_insufficient_stocks",
    }.issubset(tables)


def test_replace_strategy3_stock_backtest_result_is_atomic_and_idempotent(tmp_path):
    _init_tmp_db(tmp_path)
    task_id = "s3bt-test"
    db.create_strategy3_backtest_task(
        task_id,
        {"startDate": "2026-01-01", "endDate": "2026-02-01", "codes": ["000001"]},
        "{}",
    )
    db.save_strategy3_backtest_task_stock(task_id, "000001", name="样本", status="PENDING")

    result = {
        "signals": [_signal()],
        "opportunities": [_opportunity()],
        "eval_days": 12,
        "liquidity_filtered_days": 2,
        "raw_signals_count": 1,
        "opportunities_count": 1,
        "actual_eval_start_date": "2026-01-05",
        "actual_eval_end_date": "2026-01-20",
        "observation_data_end_date": "2026-02-01",
        "available_days": 250,
        "required_days": 180,
        "earliest_date": "2025-01-01",
        "latest_date": "2026-02-01",
    }

    db.replace_strategy3_stock_backtest_result(task_id, "000001", "样本", result)
    db.replace_strategy3_stock_backtest_result(
        task_id,
        "000001",
        "样本",
        {**result, "signals": [], "opportunities": [], "raw_signals_count": 0, "opportunities_count": 0},
    )

    conn = db.get_conn()
    assert conn.execute(
        "SELECT COUNT(*) FROM strategy3_backtest_signals WHERE task_id=? AND code=?",
        (task_id, "000001"),
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM strategy3_backtest_opportunities WHERE task_id=? AND code=?",
        (task_id, "000001"),
    ).fetchone()[0] == 0
    stock = db.get_strategy3_backtest_task_stocks(task_id)[0]
    assert stock["status"] == "COMPLETED"
    assert stock["raw_signals_count"] == 0
    assert stock["opportunities_count"] == 0


def test_build_strategy3_backtest_summary_uses_database_details(tmp_path):
    _init_tmp_db(tmp_path)
    task_id = "s3bt-summary"
    db.create_strategy3_backtest_task(
        task_id,
        {"startDate": "2026-01-01", "endDate": "2026-02-01"},
        "{}",
    )
    for code, score, reason in [
        ("000001", 88, "TARGET"),
        ("000002", 76, "NO_ENTRY_GAP_TOO_HIGH"),
    ]:
        db.save_strategy3_backtest_task_stock(task_id, code, name=f"样本{code}", status="PENDING")
        db.replace_strategy3_stock_backtest_result(
            task_id,
            code,
            f"样本{code}",
            {
                "signals": [_signal(code=code, score=score)],
                "opportunities": [_opportunity(code=code, score=score, exit_reason=reason)],
                "eval_days": 10,
                "raw_signals_count": 1,
                "opportunities_count": 1,
            },
        )

    summary = db.build_strategy3_backtest_summary(task_id)

    assert summary["execution_stats"]["opportunities"] == 2
    assert summary["execution_stats"]["entered"] == 1
    assert summary["execution_stats"]["target"] == 1
    assert summary["execution_stats"]["not_entered"] == 1
    assert summary["funnel"]["raw_signals_count"] == 2
    assert summary["groups"]["by_total_score_band"]["80-89"]["opportunities"] == 1
    assert summary["groups"]["by_total_score_band"]["70-79"]["opportunities"] == 1


def test_build_strategy3_backtest_summary_includes_payoff_and_market_groups(tmp_path):
    _init_tmp_db(tmp_path)
    task_id = "s3bt-payoff-summary"
    db.create_strategy3_backtest_task(
        task_id,
        {"startDate": "2026-01-01", "endDate": "2026-02-01"},
        "{}",
    )
    cases = [
        ("000001", "2026-01-05", "TARGET", 0.20, "sz399001", 0.03, 0.04, True, True),
        ("000002", "2026-01-06", "STOP", -0.05, "sz399001", -0.02, 0.01, False, True),
        ("300001", "2026-01-07", "STOP", -0.04, "sz399006", 0.01, -0.03, True, False),
    ]
    for code, date, reason, ret, symbol, ret20, ret60, above20, above60 in cases:
        db.save_strategy3_backtest_task_stock(task_id, code, name=f"样本{code}", status="PENDING")
        db.replace_strategy3_stock_backtest_result(
            task_id,
            code,
            f"样本{code}",
            {
                "signals": [_signal(code=code, date=date, score=88)],
                "opportunities": [
                    _opportunity(
                        code=code,
                        first_date=date,
                        score=88,
                        exit_reason=reason,
                        realized_return=ret,
                        market_index_symbol=symbol,
                        market_return_20=ret20,
                        market_return_60=ret60,
                        market_above_ma20=above20,
                        market_above_ma60=above60,
                    )
                ],
                "eval_days": 10,
                "raw_signals_count": 1,
                "opportunities_count": 1,
            },
        )

    summary = db.build_strategy3_backtest_summary(task_id)
    execution = summary["execution_stats"]

    assert execution["avg_win"] == 0.2
    assert execution["avg_loss"] == -0.045
    assert execution["payoff_ratio"] == round(0.2 / 0.045, 4)
    assert execution["profit_factor"] == round(0.2 / 0.09, 4)
    assert execution["expectancy"] == round((0.20 - 0.09) / 3, 6)
    assert execution["max_consecutive_losses"] == 2
    assert summary["groups"]["by_market_index"]["sz399001"]["opportunities"] == 2
    assert summary["groups"]["by_market_index"]["sz399006"]["opportunities"] == 1
    assert summary["groups"]["by_market_return_20"]["negative"]["opportunities"] == 1
    assert summary["groups"]["by_market_return_60"]["negative"]["opportunities"] == 1
    assert summary["groups"]["by_market_ma_state"]["above_ma20_above_ma60"]["opportunities"] == 1
    assert summary["marketDataMode"] == "local_equal_weight_proxy"


def test_build_strategy3_backtest_summary_marks_legacy_market_snapshot_unknown(tmp_path):
    _init_tmp_db(tmp_path)
    task_id = "s3bt-legacy-market-summary"
    db.create_strategy3_backtest_task(
        task_id,
        {"startDate": "2026-01-01", "endDate": "2026-02-01"},
        "{}",
    )
    legacy_opp = _opportunity(code="000001", first_date="2026-01-05")
    legacy_opp["evaluation_snapshot"] = json.dumps({"score": 88}, ensure_ascii=False)

    db.save_strategy3_backtest_task_stock(task_id, "000001", name="样本", status="PENDING")
    db.replace_strategy3_stock_backtest_result(
        task_id,
        "000001",
        "样本",
        {
            "signals": [_signal(code="000001", date="2026-01-05", score=88)],
            "opportunities": [legacy_opp],
            "eval_days": 10,
            "raw_signals_count": 1,
            "opportunities_count": 1,
        },
    )

    summary = db.build_strategy3_backtest_summary(task_id)

    assert summary["groups"]["by_market_index"]["UNKNOWN"]["opportunities"] == 1
    assert summary["groups"]["by_market_ma_state"]["UNKNOWN"]["opportunities"] == 1

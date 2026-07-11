import json

from strategy6.backtest.report import write_backtest_report


def test_report_writes_summary_daily_candidates_and_trades(tmp_path):
    result = {
        "run": {"run_id": "s6bt-test", "confidence_label": "RESEARCH_ONLY_CURRENT_UNIVERSE"},
        "data_audit": {"stocks": 2, "survivorship_bias": True},
        "oos_lock": {"status": "OOS_LOCKED", "start_date": "2026-01-01"},
        "summary": {"trades": 1, "expectancy_r": 0.2, "profit_factor": 1.5},
        "experiments": {"E0": {"trades": 1}, "E1": {"trades": 2}},
        "signals": [{"evaluation_date": "2025-01-02", "code": "000001", "name": "样本", "tail_path": "BOX", "candidate_type": "KEY_CANDIDATE"}],
        "orders": [{"order_id": "o1", "code": "000001", "status": "FILLED"}],
        "trades": [{"trade_id": "t1", "code": "000001", "net_return": 0.1}],
        "parameter_trials": [{"parameter_set_id": "p1", "robust_score": 80}],
    }
    paths = write_backtest_report(result, tmp_path)
    assert set(paths) >= {"markdown", "summary_json", "signals_csv", "orders_csv", "trades_csv", "trials_csv"}
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "RESEARCH_ONLY_CURRENT_UNIVERSE" in markdown
    assert "OOS_LOCKED" in markdown
    assert "幸存者偏差" in markdown
    summary = json.loads(paths["summary_json"].read_text(encoding="utf-8"))
    assert summary["summary"]["trades"] == 1

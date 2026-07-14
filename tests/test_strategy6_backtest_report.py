import csv
import json

from strategy6.backtest.report import write_backtest_report


def test_report_writes_summary_daily_candidates_and_trades(tmp_path):
    result = {
        "run": {"run_id": "s6bt-test", "confidence_label": "RESEARCH_ONLY_CURRENT_UNIVERSE"},
        "data_audit": {"stocks": 2, "survivorship_bias": True},
        "oos_lock": {"status": "OOS_LOCKED", "start_date": "2026-01-01"},
        "summary": {"trades": 1, "expectancy_r": 0.2, "profit_factor": 1.5},
        "experiments": {"E0": {"trades": 1}, "E1": {"trades": 2}},
        "path_metrics": {"NONE": {"trades": 1}},
        "authoritative_path_metrics": {"BROOKS": {"trades": 1}},
        "tail_primary_path_metrics": {"BROOKS": {"trades": 1}},
        "tail_path_summary_metrics": {"BROOKS": {"trades": 1}},
        "brooks_status_metrics": {"SECOND_ENTRY_LONG_READY": {"trades": 1}},
        "brooks_structure_metrics": {"MICRO_DOUBLE_BOTTOM": {"trades": 1}},
        "entry_archetype_metrics": {"SUPPORT_PULLBACK": {"trades": 1}},
        "setup_quality_metrics": {"20-24": {"trades": 1}},
        "support_reaction_metrics": {"05-09": {"trades": 1}},
        "start_quality_metrics": {"15-19": {"trades": 1}},
        "path_evidence_metrics": {"10-14": {"trades": 1}},
        "signals": [{
            "evaluation_date": "2025-01-02", "code": "000001", "name": "样本",
            "tail_path": "NONE", "tail_paths": ["BROOKS"], "tail_primary_path": "BROOKS",
            "tail_path_summary": "BROOKS", "brooks_status": "SECOND_ENTRY_LONG_READY",
            "brooks_result": {"structure": {"setup_types": ["MICRO_DOUBLE_BOTTOM"]}},
            "candidate_type": "KEY_CANDIDATE",
        }],
        "orders": [{"order_id": "o1", "code": "000001", "status": "FILLED"}],
        "trades": [{
            "trade_id": "t1", "code": "000001", "net_return": 0.1,
            "tail_path": "NONE", "tail_paths": ["BROOKS"],
            "tail_primary_path": "BROOKS", "tail_path_summary": "BROOKS",
            "brooks_status": "SECOND_ENTRY_LONG_READY",
        }],
        "parameter_trials": [{"parameter_set_id": "p1", "robust_score": 80}],
        "phase_metrics": {"TRAIN": {"trades": 1}, "VALIDATION": {"trades": 1}},
        "stress_tests": {"HIGH_COST": {"status": "COMPLETED"}},
        "walk_forward": {"status": "INSUFFICIENT_DATA"},
        "optimization": {"recommendation": "KEEP_DEFAULT"},
        "recommendation": {"decision": "KEEP_DEFAULT", "production_config_modified": False},
    }
    paths = write_backtest_report(result, tmp_path)
    assert set(paths) >= {"markdown", "summary_json", "signals_csv", "orders_csv", "trades_csv", "trials_csv"}
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "RESEARCH_ONLY_CURRENT_UNIVERSE" in markdown
    assert "OOS_LOCKED" in markdown
    assert "幸存者偏差" in markdown
    assert "压力测试" in markdown
    assert "INSUFFICIENT_DATA" in markdown
    assert "KEEP_DEFAULT" in markdown
    assert "旧双路径归因" in markdown
    assert "权威三路径归因" in markdown
    assert "Brooks状态" in markdown
    assert "入场类型与质量归因" in markdown
    assert "SUPPORT_PULLBACK" in markdown
    assert "setup_quality" in markdown
    summary = json.loads(paths["summary_json"].read_text(encoding="utf-8"))
    assert summary["summary"]["trades"] == 1

    with paths["signals_csv"].open(encoding="utf-8-sig", newline="") as handle:
        signal = next(csv.DictReader(handle))
    assert json.loads(signal["tail_paths"]) == ["BROOKS"]
    assert json.loads(signal["brooks_result"])["structure"]["setup_types"] == ["MICRO_DOUBLE_BOTTOM"]

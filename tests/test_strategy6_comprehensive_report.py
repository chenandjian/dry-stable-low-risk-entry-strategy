import copy
import json

from scanner import db
from strategy6.backtest.comprehensive_report import write_comprehensive_report
from strategy6.backtest.comprehensive_runner import initialize_campaign
from strategy6.validation import DEFAULT_STRATEGY6_CONFIG


def test_comprehensive_report_writes_complete_empty_safe_artifacts_without_mutating_config(tmp_path):
    db.init_db(str(tmp_path / "report.db"))
    production = copy.deepcopy(DEFAULT_STRATEGY6_CONFIG)
    initialize_campaign(
        campaign_id="c1", base_config=production,
        strategy_git_commit="abc", data_version="v1",
        random_seed=7, max_joint_trials=2,
    )
    before = copy.deepcopy(production)

    result = write_comprehensive_report("c1", tmp_path / "output", production)

    assert production == before
    assert result["recommendation"] == "INCOMPLETE"
    expected = {
        "report.md", "campaign.json", "parameter_dictionary.csv",
        "stage_trials.csv", "daily_candidates.csv", "orders.csv", "trades.csv",
    }
    assert expected <= {path.name for path in (tmp_path / "output").iterdir()}
    report = (tmp_path / "output" / "report.md").read_text(encoding="utf-8")
    assert "七阶段状态" in report
    assert "生产配置未自动修改" in report
    assert "OOS" in report
    payload = json.loads((tmp_path / "output" / "campaign.json").read_text(encoding="utf-8"))
    assert payload["campaign"]["campaign_id"] == "c1"
    assert len(payload["stages"]) == 7


def test_report_records_keep_previous_stage_and_parameter_dictionary_reasons(tmp_path):
    db.init_db(str(tmp_path / "keep.db"))
    initialize_campaign(
        campaign_id="c1", base_config=DEFAULT_STRATEGY6_CONFIG,
        strategy_git_commit="abc", data_version="v1",
        random_seed=7, max_joint_trials=2,
    )
    first = db.get_strategy6_optimization_stages("c1")[0]
    db.save_strategy6_optimization_stage({
        **first,
        "status": "FROZEN",
        "decision": "KEEP_PREVIOUS_STAGE",
        "selected_parameter_set_id": first["parent_parameter_set_id"],
        "detail": {"selected_config": DEFAULT_STRATEGY6_CONFIG, "confirmed_count": 0},
    })

    result = write_comprehensive_report("c1", tmp_path / "output", DEFAULT_STRATEGY6_CONFIG)

    assert result["recommendation"] == "INCOMPLETE"
    report = (tmp_path / "output" / "report.md").read_text(encoding="utf-8")
    assert "KEEP_PREVIOUS_STAGE" in report
    dictionary = (tmp_path / "output" / "parameter_dictionary.csv").read_text(encoding="utf-8-sig")
    assert "minimum_trading_days" in dictionary
    assert "固定参数" in dictionary
    assert "min_relative_strength_20" in dictionary
    assert "consolidation_min_days" in dictionary
    assert "本轮设计未列入搜索空间" in dictionary
    assert "max_amp_5d_s" in dictionary
    assert "grade_risk_profile" in dictionary

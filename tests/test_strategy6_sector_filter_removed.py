from pathlib import Path

from strategy6.engine import StrongVcpTailEngine
from strategy6.report import build_strategy6_report_xlsx
from strategy6.validation import resolve_strategy6_config
from tests.test_strategy6_core_rules import build_strategy6_candidate_data


FORBIDDEN_FIELDS = {
    "enable_sector_filter",
    "sector_filter_mode",
    "sector_strength_status",
    "sector_strength_score",
    "relative_strength_10_sector",
    "sector_member_new_high_count",
}


def test_strategy6_config_and_candidate_output_have_no_sector_filter_fields():
    cfg = resolve_strategy6_config({
        "strategy6": {
            "enable_sector_filter": True,
            "sector_filter_mode": "strict",
            "sector_min_member_new_high_count": 9,
        }
    })
    assert FORBIDDEN_FIELDS.isdisjoint(cfg)
    assert "sector_min_member_new_high_count" not in cfg

    evaluation = StrongVcpTailEngine({"strategy6": cfg}).evaluate_at(
        build_strategy6_candidate_data(),
        code="000001",
        name="平安银行",
        sector_name="银行",
    )
    candidate = evaluation.to_candidate_dict()
    assert candidate["sector_name"] == "银行"
    assert FORBIDDEN_FIELDS.isdisjoint(candidate)


def test_strategy6_report_and_package_have_no_sector_filter_module_or_headers():
    assert not Path("strategy6/sector.py").exists()

    content = build_strategy6_report_xlsx([{
        "code": "000001",
        "name": "平安银行",
        "sector_name": "银行",
        "candidate_type": "WATCH_CANDIDATE",
    }])
    for field in FORBIDDEN_FIELDS:
        assert field.encode() not in content

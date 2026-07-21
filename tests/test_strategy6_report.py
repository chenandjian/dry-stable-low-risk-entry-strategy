from io import BytesIO
import zipfile

from strategy6.report import build_strategy6_report_xlsx, is_strategy6_observation_record


def test_strategy6_vcp_observation_requires_historical_formal_candidate():
    structural_only = {
        "candidate_type": "REJECTED",
        "classification": "observation",
        "vcp_observation_eligible": True,
        "vcp_history_qualified": False,
    }

    assert is_strategy6_observation_record(structural_only) is False
    assert is_strategy6_observation_record({
        **structural_only,
        "vcp_history_qualified": True,
    }) is True


def test_strategy6_report_xlsx_handles_empty_candidates():
    content = build_strategy6_report_xlsx([])

    workbook = zipfile.ZipFile(BytesIO(content))
    shared = workbook.read("xl/sharedStrings.xml").decode("utf-8")
    sheet = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")

    assert "stock_code" in shared
    assert "enable_market_filter" in shared
    assert "relative_strength_10_sector" not in shared
    assert "strategy_version" in shared
    assert "decision_profile" in shared
    assert "pattern_type" in shared
    assert "objective_target_2" in shared
    assert "execution_target_2r" in shared
    assert "objective_rr_2" in shared
    assert "valid_from_date" in shared
    assert "price_basis" in shared
    assert "start_day_self_amount_percentile" in shared
    for header in (
        "original_tail_pass", "box_tail_enabled", "box_tail_pass", "box_status",
        "tail_path", "box_start_date", "box_high", "box_low", "box_width",
        "box_low_test_count", "box_volume_contraction_ratio", "box_center_shift",
        "compact_kline_enabled", "compact_kline_pass", "compact_kline_score",
        "box_quality_score", "box_quality_tag", "avg_body_ratio_5",
        "compact_close_range_5", "kline_overlap_pair_count", "atr_contraction_ratio",
        "compact_kline_reasons", "compact_kline_risk_tags",
        "brooks_tail_enabled", "brooks_tail_pass", "brooks_tail_score",
        "brooks_tail_premium", "brooks_status", "brooks_trade_ready",
        "brooks_trade_trigger_type", "brooks_trigger_price", "brooks_trigger_valid_until", "tail_paths",
        "tail_path_summary", "tail_primary_path", "passed_path_count",
        "multi_path_confirmed", "brooks_result",
    ):
        assert header in shared
    assert '<row r="1">' in sheet
    assert '<row r="2">' not in sheet


def test_strategy6_report_has_separate_lifecycle_audit_sheet():
    content = build_strategy6_report_xlsx([], [{
        "code": "000001",
        "name": "平安银行",
        "lifecycle_status": "FAILED",
        "exit_reason": "SUPPORT_FAILED",
        "cooldown_until_date": "2026-08-05",
    }])

    workbook = zipfile.ZipFile(BytesIO(content))
    workbook_xml = workbook.read("xl/workbook.xml").decode("utf-8")
    lifecycle_sheet = workbook.read("xl/worksheets/sheet2.xml").decode("utf-8")
    shared = workbook.read("xl/sharedStrings.xml").decode("utf-8")

    assert "lifecycle_audit" in workbook_xml
    assert "SUPPORT_FAILED" in shared
    assert '<row r="2">' in lifecycle_sheet


def test_strategy6_report_serializes_brooks_details_as_stable_json():
    content = build_strategy6_report_xlsx([{
        "code": "000001",
        "tail_path": "NONE",
        "tail_paths": ["BROOKS"],
        "tail_path_summary": "BROOKS",
        "tail_primary_path": "BROOKS",
        "passed_path_count": 1,
        "multi_path_confirmed": False,
        "brooks_tail_enabled": True,
        "brooks_tail_pass": True,
        "brooks_tail_score": 18,
        "brooks_tail_premium": False,
        "brooks_status": "MICRO_DOUBLE_BOTTOM",
        "brooks_trade_ready": False,
        "brooks_trade_trigger_type": "",
        "brooks_trigger_price": 10.18,
        "brooks_trigger_valid_until": "2026-07-14",
        "brooks_result": {
            "status": "MICRO_DOUBLE_BOTTOM",
            "context": {"passed": True, "context_type": "TRADING_RANGE"},
        },
    }])

    workbook = zipfile.ZipFile(BytesIO(content))
    shared = workbook.read("xl/sharedStrings.xml").decode("utf-8")
    sheet = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")

    assert "BROOKS" in shared
    assert "MICRO_DOUBLE_BOTTOM" in shared
    assert "<v>10.18</v>" in sheet
    assert '{"context":{"context_type":"TRADING_RANGE","passed":true},"status":"MICRO_DOUBLE_BOTTOM"}' in shared


def test_strategy6_formal_report_excludes_observation_and_exit_audit_rows():
    content = build_strategy6_report_xlsx([
        {
            "code": "000001",
            "name": "正式候选",
            "candidate_type": "KEY_CANDIDATE",
        },
        {
            "code": "000002",
            "name": "VCP观察审计",
            "candidate_type": "REJECTED",
            "classification": "observation",
            "vcp_lifecycle_status": "VCP_INVALID",
        },
    ])

    workbook = zipfile.ZipFile(BytesIO(content))
    shared = workbook.read("xl/sharedStrings.xml").decode("utf-8")
    sheet = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")

    assert "正式候选" in shared
    assert "VCP观察审计" not in shared
    assert '<row r="2">' in sheet
    assert '<row r="3">' not in sheet

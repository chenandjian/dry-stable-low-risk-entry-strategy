from io import BytesIO
import zipfile

from strategy6.report import build_strategy6_report_xlsx


def test_strategy6_report_xlsx_handles_empty_candidates():
    content = build_strategy6_report_xlsx([])

    workbook = zipfile.ZipFile(BytesIO(content))
    shared = workbook.read("xl/sharedStrings.xml").decode("utf-8")
    sheet = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")

    assert "stock_code" in shared
    assert "enable_market_filter" in shared
    assert "relative_strength_10_sector" not in shared
    assert "strategy_version" in shared
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

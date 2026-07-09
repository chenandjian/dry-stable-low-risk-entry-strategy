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
    assert "relative_strength_10_sector" in shared
    assert '<row r="1">' in sheet
    assert '<row r="2">' not in sheet

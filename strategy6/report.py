"""Strategy6 daily report export."""
from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile
from xml.sax.saxutils import escape


STRATEGY6_REPORT_COLUMNS = [
    ("stock_code", "code"),
    ("stock_name", "name"),
    ("sector_name", "sector_name"),
    ("candidate_type", "candidate_type"),
    ("lifecycle_status", "lifecycle_status"),
    ("total_score", "total_score"),
    ("enable_market_filter", "enable_market_filter"),
    ("enable_sector_filter", "enable_sector_filter"),
    ("market_filter_mode", "market_filter_mode"),
    ("sector_filter_mode", "sector_filter_mode"),
    ("current_price", "current_price"),
    ("daily_return", "daily_return"),
    ("ma5", "ma5"),
    ("ma10", "ma10"),
    ("ma20", "ma20"),
    ("ma50", "ma50"),
    ("ma120", "ma120"),
    ("ma250", "ma250"),
    ("return_5", "return_5"),
    ("return_10", "return_10"),
    ("return_20", "return_20"),
    ("relative_strength_20", "relative_strength_20"),
    ("relative_strength_20_observed", "relative_strength_20_observed"),
    ("relative_strength_10_sector", "relative_strength_10_sector"),
    ("sector_member_new_high_count", "sector_member_new_high_count"),
    ("amount_avg_10", "amount_avg_10"),
    ("amount_avg_30", "amount_avg_30"),
    ("amount_avg_60", "amount_avg_60"),
    ("market_status", "market_status"),
    ("sector_strength_status", "sector_strength_status"),
    ("start_date", "start_date"),
    ("start_type", "start_type"),
    ("start_grade", "start_grade"),
    ("start_day_return", "start_day_return"),
    ("start_day_volume_ratio", "start_day_volume_ratio"),
    ("start_day_amount", "start_day_amount"),
    ("start_day_close_position", "start_day_close_position"),
    ("is_limit_up", "is_limit_up"),
    ("is_one_word_limit_up", "is_one_word_limit_up"),
    ("limit_up_pct", "limit_up_pct"),
    ("highest_close_20", "highest_close_20"),
    ("highest_close_120", "highest_close_120"),
    ("pullback_from_20d_high", "pullback_from_20d_high"),
    ("range_5", "range_5"),
    ("range_10", "range_10"),
    ("close_range_5", "close_range_5"),
    ("v3", "v3"),
    ("v5", "v5"),
    ("v10", "v10"),
    ("v20", "v20"),
    ("volume_ratio_5_20", "volume_ratio_5_20"),
    ("key_support_price", "key_support_price"),
    ("support_zone_low", "support_zone_low"),
    ("support_zone_high", "support_zone_high"),
    ("defense_support_price", "defense_support_price"),
    ("main_support_ma", "main_support_ma"),
    ("support_status", "support_status"),
    ("support_test_count", "support_test_count"),
    ("pivot_price", "pivot_price"),
    ("box_height", "box_height"),
    ("suggested_buy_price", "suggested_buy_price"),
    ("buy_zone_low", "buy_zone_low"),
    ("buy_zone_high", "buy_zone_high"),
    ("stop_loss_price", "stop_loss_price"),
    ("target_price_1", "target_price_1"),
    ("target_price_2", "target_price_2"),
    ("target_price_3", "target_price_3"),
    ("risk_amount", "risk_amount"),
    ("reward_amount_1", "reward_amount_1"),
    ("reward_amount_2", "reward_amount_2"),
    ("reward_amount_3", "reward_amount_3"),
    ("risk_reward_ratio_1", "risk_reward_ratio_1"),
    ("risk_reward_ratio_2", "risk_reward_ratio_2"),
    ("risk_reward_ratio_3", "risk_reward_ratio_3"),
    ("strong_start_score", "strong_start_score"),
    ("support_score", "support_score"),
    ("dry_stable_score", "dry_stable_score"),
    ("risk_reward_score", "risk_reward_score"),
    ("risk_control_score", "risk_control_score"),
    ("risk_tags", "risk_tags"),
    ("warn_tags", "warn_tags"),
    ("reject_reason", "reject_reasons"),
    ("suggestion", "suggestion"),
]


def build_strategy6_report_xlsx(candidates: list[dict]) -> bytes:
    rows = [[header for header, _ in STRATEGY6_REPORT_COLUMNS]]
    for candidate in candidates:
        rows.append([_cell_value(candidate.get(key)) for _, key in STRATEGY6_REPORT_COLUMNS])

    shared_strings: list[str] = []
    shared_index: dict[str, int] = {}
    sheet_rows = []
    for row_idx, row in enumerate(rows, start=1):
        cells = []
        for col_idx, value in enumerate(row, start=1):
            ref = f"{_column_name(col_idx)}{row_idx}"
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                text = str(value)
                idx = shared_index.get(text)
                if idx is None:
                    idx = len(shared_strings)
                    shared_index[text] = idx
                    shared_strings.append(text)
                cells.append(f'<c r="{ref}" t="s"><v>{idx}</v></c>')
        sheet_rows.append(f'<row r="{row_idx}">{"".join(cells)}</row>')

    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _content_types_xml())
        zf.writestr("_rels/.rels", _rels_xml())
        zf.writestr("xl/workbook.xml", _workbook_xml())
        zf.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml())
        zf.writestr("xl/worksheets/sheet1.xml", _sheet_xml(sheet_rows))
        zf.writestr("xl/sharedStrings.xml", _shared_strings_xml(shared_strings))
    return output.getvalue()


def _cell_value(value):
    if isinstance(value, list):
        return "|".join(str(v) for v in value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return value


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _content_types_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>"""


def _rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""


def _workbook_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="strategy6_report" sheetId="1" r:id="rId1"/></sheets>
</workbook>"""


def _workbook_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>
</Relationships>"""


def _sheet_xml(rows: list[str]) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<sheetData>{''.join(rows)}</sheetData>
</worksheet>"""


def _shared_strings_xml(strings: list[str]) -> str:
    items = "".join(f"<si><t>{escape(text)}</t></si>" for text in strings)
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{len(strings)}" uniqueCount="{len(strings)}">{items}</sst>"""

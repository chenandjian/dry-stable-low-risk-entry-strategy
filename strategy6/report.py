"""Strategy6 daily report export."""
from __future__ import annotations

import json
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile
from xml.sax.saxutils import escape


STRATEGY6_REPORT_COLUMNS = [
    ("stock_code", "code"),
    ("stock_name", "name"),
    ("sector_name", "sector_name"),
    ("candidate_type", "candidate_type"),
    ("lifecycle_status", "lifecycle_status"),
    ("first_seen_date", "first_seen_date"),
    ("last_seen_date", "last_seen_date"),
    ("days_in_pool", "days_in_pool"),
    ("exit_date", "exit_date"),
    ("exit_reason", "exit_reason"),
    ("cooldown_until_date", "cooldown_until_date"),
    ("reentry_count", "reentry_count"),
    ("strategy_version", "strategy_version"),
    ("config_hash", "config_hash"),
    ("price_basis", "price_basis"),
    ("current_price_adj", "current_price_adj"),
    ("current_price_raw", "current_price_raw"),
    ("total_score", "total_score"),
    ("enable_market_filter", "enable_market_filter"),
    ("market_filter_mode", "market_filter_mode"),
    ("current_price", "current_price"),
    ("daily_return", "daily_return"),
    ("current_close_position", "current_close_position"),
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
    ("amount_avg_10", "amount_avg_10"),
    ("amount_avg_30", "amount_avg_30"),
    ("amount_avg_60", "amount_avg_60"),
    ("market_status", "market_status"),
    ("start_date", "start_date"),
    ("start_type", "start_type"),
    ("start_grade", "start_grade"),
    ("start_day_return", "start_day_return"),
    ("start_day_volume_ratio", "start_day_volume_ratio"),
    ("start_day_amount", "start_day_amount"),
    ("start_day_close_position", "start_day_close_position"),
    ("start_day_self_amount_percentile", "start_day_self_amount_percentile"),
    ("start_low", "start_low"),
    ("is_limit_up", "is_limit_up"),
    ("is_one_word_limit_up", "is_one_word_limit_up"),
    ("limit_up_pct", "limit_up_pct"),
    ("days_since_start", "days_since_start"),
    ("phase_status", "phase_status"),
    ("consolidation_start_date", "consolidation_start_date"),
    ("tail_start_date", "tail_start_date"),
    ("signal_date", "signal_date"),
    ("start_age_days", "start_age_days"),
    ("consolidation_days", "consolidation_days"),
    ("tail_days", "tail_days"),
    ("pattern_type", "pattern_type"),
    ("pattern_score", "pattern_score"),
    ("pattern_start_date", "pattern_start_date"),
    ("pattern_end_date", "pattern_end_date"),
    ("pivot_source", "pivot_source"),
    ("pattern_low", "pattern_low"),
    ("pattern_height", "pattern_height"),
    ("pattern_depth_pct", "pattern_depth_pct"),
    ("contraction_count", "contraction_count"),
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
    ("tactical_support_price", "tactical_support_price"),
    ("prior_key_support_price", "prior_key_support_price"),
    ("support_zone_low", "support_zone_low"),
    ("support_zone_high", "support_zone_high"),
    ("defense_support_price", "defense_support_price"),
    ("main_support_ma", "main_support_ma"),
    ("support_status", "support_status"),
    ("support_test_count", "support_test_count"),
    ("support_cluster_sources", "support_cluster_sources"),
    ("support_cluster_score", "support_cluster_score"),
    ("pivot_price", "pivot_price"),
    ("box_height", "box_height"),
    ("suggested_buy_price", "suggested_buy_price"),
    ("buy_zone_low", "buy_zone_low"),
    ("buy_zone_high", "buy_zone_high"),
    ("stop_loss_price", "stop_loss_price"),
    ("target_price_1", "target_price_1"),
    ("target_price_2", "target_price_2"),
    ("target_price_3", "target_price_3"),
    ("objective_target_1", "objective_target_1"),
    ("objective_target_2", "objective_target_2"),
    ("execution_target_1_5r", "execution_target_1_5r"),
    ("execution_target_2r", "execution_target_2r"),
    ("execution_target_2_5r", "execution_target_2_5r"),
    ("execution_target_3_5r", "execution_target_3_5r"),
    ("risk_amount", "risk_amount"),
    ("reward_amount_1", "reward_amount_1"),
    ("reward_amount_2", "reward_amount_2"),
    ("reward_amount_3", "reward_amount_3"),
    ("risk_reward_ratio_1", "risk_reward_ratio_1"),
    ("risk_reward_ratio_2", "risk_reward_ratio_2"),
    ("risk_reward_ratio_3", "risk_reward_ratio_3"),
    ("objective_rr_1", "objective_rr_1"),
    ("objective_rr_2", "objective_rr_2"),
    ("valid_from_date", "valid_from_date"),
    ("valid_until_date", "valid_until_date"),
    ("suggested_limit_price", "suggested_limit_price"),
    ("execution_notes", "execution_notes"),
    ("strong_start_score", "strong_start_score"),
    ("support_score", "support_score"),
    ("dry_stable_score", "dry_stable_score"),
    ("risk_reward_score", "risk_reward_score"),
    ("risk_control_score", "risk_control_score"),
    ("pattern_score_component", "pattern_score_component"),
    ("tail_score", "tail_score"),
    ("objective_rr_score", "objective_rr_score"),
    ("relative_strength_risk_score", "relative_strength_risk_score"),
    ("tail_avg_volume", "tail_avg_volume"),
    ("pre_tail_avg_volume_20", "pre_tail_avg_volume_20"),
    ("tail_volume_ratio", "tail_volume_ratio"),
    ("volume_slope_10", "volume_slope_10"),
    ("original_tail_pass", "original_tail_pass"),
    ("original_tail_score", "original_tail_score"),
    ("box_tail_enabled", "box_tail_enabled"),
    ("box_tail_pass", "box_tail_pass"),
    ("box_tail_score", "box_tail_score"),
    ("box_status", "box_status"),
    ("tail_pass", "tail_pass"),
    ("tail_path", "tail_path"),
    ("box_start_date", "box_start_date"),
    ("box_end_date", "box_end_date"),
    ("box_days", "box_days"),
    ("box_high", "box_high"),
    ("box_low", "box_low"),
    ("box_width", "box_width"),
    ("box_position", "box_position"),
    ("box_position_raw", "box_position_raw"),
    ("box_low_test_count", "box_low_test_count"),
    ("box_high_test_count", "box_high_test_count"),
    ("box_first_half_volume", "box_first_half_volume"),
    ("box_second_half_volume", "box_second_half_volume"),
    ("box_volume_contraction_ratio", "box_volume_contraction_ratio"),
    ("first_half_median_close", "first_half_median_close"),
    ("second_half_median_close", "second_half_median_close"),
    ("box_center_shift", "box_center_shift"),
    ("box_break_reason", "box_break_reason"),
    ("box_selection_reason", "box_selection_reason"),
    ("compact_kline_enabled", "compact_kline_enabled"),
    ("compact_kline_pass", "compact_kline_pass"),
    ("compact_kline_score", "compact_kline_score"),
    ("box_quality_score", "box_quality_score"),
    ("box_quality_tag", "box_quality_tag"),
    ("avg_body_ratio_5", "avg_body_ratio_5"),
    ("max_body_ratio_5", "max_body_ratio_5"),
    ("compact_close_range_5", "compact_close_range_5"),
    ("kline_overlap_pair_count", "kline_overlap_pair_count"),
    ("avg_kline_overlap_ratio", "avg_kline_overlap_ratio"),
    ("gap_count_5", "gap_count_5"),
    ("max_gap_ratio_5", "max_gap_ratio_5"),
    ("atr5", "atr5"),
    ("atr20", "atr20"),
    ("atr_contraction_ratio", "atr_contraction_ratio"),
    ("compact_kline_reasons", "compact_kline_reasons"),
    ("compact_kline_risk_tags", "compact_kline_risk_tags"),
    ("brooks_tail_enabled", "brooks_tail_enabled"),
    ("brooks_tail_pass", "brooks_tail_pass"),
    ("brooks_tail_score", "brooks_tail_score"),
    ("brooks_tail_premium", "brooks_tail_premium"),
    ("brooks_status", "brooks_status"),
    ("brooks_trade_ready", "brooks_trade_ready"),
    ("brooks_trade_trigger_type", "brooks_trade_trigger_type"),
    ("brooks_trigger_price", "brooks_trigger_price"),
    ("brooks_trigger_valid_until", "brooks_trigger_valid_until"),
    ("tail_paths", "tail_paths"),
    ("tail_path_summary", "tail_path_summary"),
    ("tail_primary_path", "tail_primary_path"),
    ("passed_path_count", "passed_path_count"),
    ("multi_path_confirmed", "multi_path_confirmed"),
    ("brooks_result", "brooks_result"),
    ("risk_tags", "risk_tags"),
    ("warn_tags", "warn_tags"),
    ("reject_reason", "reject_reasons"),
    ("suggestion", "suggestion"),
]

LIFECYCLE_REPORT_COLUMNS = [
    ("stock_code", "code"),
    ("stock_name", "name"),
    ("evaluation_date", "evaluation_date"),
    ("candidate_type", "candidate_type"),
    ("lifecycle_status", "lifecycle_status"),
    ("first_seen_date", "first_seen_date"),
    ("last_seen_date", "last_seen_date"),
    ("days_in_pool", "days_in_pool"),
    ("exit_date", "exit_date"),
    ("exit_reason", "exit_reason"),
    ("cooldown_until_date", "cooldown_until_date"),
    ("reentry_count", "reentry_count"),
    ("blocked", "blocked"),
    ("reject_reasons", "reject_reasons"),
]


def is_strategy6_trading_candidate(candidate: dict) -> bool:
    return candidate.get("candidate_type") != "REJECTED"


def is_strategy6_observation_record(candidate: dict) -> bool:
    return (
        candidate.get("candidate_type") == "REJECTED"
        and candidate.get("classification") == "observation"
        and candidate.get("vcp_observation_eligible") is True
        and candidate.get("vcp_history_qualified") is True
    )


def is_strategy6_vcp_eligible(candidate: dict) -> bool:
    return (
        candidate.get("vcp_observation_eligible") is True
        and candidate.get("vcp_history_qualified") is True
    )


def is_strategy6_exit_audit_record(candidate: dict) -> bool:
    return bool(candidate.get("vcp_exit_audit"))


def is_strategy6_visible_record(candidate: dict) -> bool:
    return (
        is_strategy6_trading_candidate(candidate)
        or is_strategy6_observation_record(candidate)
        or is_strategy6_exit_audit_record(candidate)
    )


def build_strategy6_report_xlsx(
    candidates: list[dict],
    lifecycle_rows: list[dict] | None = None,
) -> bytes:
    shared_strings: list[str] = []
    shared_index: dict[str, int] = {}
    trading_candidates = [item for item in candidates if is_strategy6_trading_candidate(item)]
    candidate_rows = _report_rows(trading_candidates, STRATEGY6_REPORT_COLUMNS)
    lifecycle_report_rows = _report_rows(lifecycle_rows or [], LIFECYCLE_REPORT_COLUMNS)
    sheet_rows = _encode_sheet_rows(candidate_rows, shared_strings, shared_index)
    lifecycle_sheet_rows = _encode_sheet_rows(lifecycle_report_rows, shared_strings, shared_index)

    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _content_types_xml())
        zf.writestr("_rels/.rels", _rels_xml())
        zf.writestr("xl/workbook.xml", _workbook_xml())
        zf.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml())
        zf.writestr("xl/worksheets/sheet1.xml", _sheet_xml(sheet_rows))
        zf.writestr("xl/worksheets/sheet2.xml", _sheet_xml(lifecycle_sheet_rows))
        zf.writestr("xl/sharedStrings.xml", _shared_strings_xml(shared_strings))
    return output.getvalue()


def _report_rows(items: list[dict], columns: list[tuple[str, str]]) -> list[list]:
    rows = [[header for header, _ in columns]]
    rows.extend([_cell_value(item.get(key)) for _, key in columns] for item in items)
    return rows


def _encode_sheet_rows(
    rows: list[list],
    shared_strings: list[str],
    shared_index: dict[str, int],
) -> list[str]:
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
    return sheet_rows


def _cell_value(value):
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
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
<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
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
<sheets>
<sheet name="strategy6_report" sheetId="1" r:id="rId1"/>
<sheet name="lifecycle_audit" sheetId="2" r:id="rId2"/>
</sheets>
</workbook>"""


def _workbook_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>
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

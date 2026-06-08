from __future__ import annotations

import inspect
import json
import os
from datetime import datetime, timedelta

from scanner import db
from scanner.engine import _merge_data
from scanner.baidu_source import fetch_baidu_daily
from scanner.sina_source import fetch_sina_daily
from scanner.strategy_engine import CupHandleStrategyEngine, serialize_pattern_for_backtest
from scanner.tencent_source import fetch_tencent_daily


class DataCoverageError(Exception):
    def __init__(self, code: str, required_start_date: str, required_end_date: str, available_range: dict | None):
        self.code = code
        self.required_start_date = required_start_date
        self.required_end_date = required_end_date
        self.available_range = available_range
        self.missing_ranges = _missing_ranges(required_start_date, required_end_date, available_range)
        super().__init__(f"Insufficient data coverage for {code}: {required_start_date} to {required_end_date}")

    def to_dict(self) -> dict:
        return {
            "error": "Insufficient data coverage",
            "message": "历史数据覆盖不足，无法完成所需区间的回测。",
            "code": self.code,
            "requiredRange": {
                "startDate": self.required_start_date,
                "endDate": self.required_end_date,
            },
            "availableRange": self.available_range,
            "missingRanges": self.missing_ranges,
        }


def _range_for(data: list[dict] | None) -> dict | None:
    if not data:
        return None
    dates = sorted(row["date"] for row in data if row.get("date"))
    if not dates:
        return None
    return {"startDate": dates[0], "endDate": dates[-1]}


def _covers(data: list[dict] | None, start_date: str, end_date: str) -> bool:
    available_range = _range_for(data)
    if not available_range:
        return False
    return available_range["startDate"] <= start_date and available_range["endDate"] >= end_date


def _prev_date(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=1)
    return dt.strftime("%Y-%m-%d")


def _next_date(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)
    return dt.strftime("%Y-%m-%d")


def _missing_ranges(start_date: str, end_date: str, available_range: dict | None) -> list[dict]:
    if not available_range:
        return [{"startDate": start_date, "endDate": end_date}]

    missing = []
    available_start = available_range["startDate"]
    available_end = available_range["endDate"]

    if available_start > start_date:
        missing.append({
            "startDate": start_date,
            "endDate": min(_prev_date(available_start), end_date),
        })

    if available_end < end_date:
        missing.append({
            "startDate": max(_next_date(available_end), start_date),
            "endDate": end_date,
        })

    return [r for r in missing if r["startDate"] <= r["endDate"]]


def _estimate_fetch_days(required_start_date: str, required_end_date: str) -> int:
    start = datetime.strptime(required_start_date, "%Y-%m-%d")
    end = datetime.strptime(required_end_date, "%Y-%m-%d")
    calendar_span_days = max(1, (end - start).days + 1)
    return max(250, calendar_span_days * 2 + 60)


def default_fresh_fetch(
    code: str,
    required_start_date: str | None = None,
    required_end_date: str | None = None,
) -> list[dict] | None:
    days = 250
    if required_start_date and required_end_date:
        days = _estimate_fetch_days(required_start_date, required_end_date)

    for fetch_fn in (fetch_baidu_daily, fetch_sina_daily, fetch_tencent_daily):
        data = fetch_fn(code, days=days)
        if data:
            return data
    return None


def _call_fetch_fn(fetch_fn, code: str, required_start_date: str, required_end_date: str) -> list[dict] | None:
    if fetch_fn is default_fresh_fetch:
        return fetch_fn(code, required_start_date, required_end_date)

    try:
        signature = inspect.signature(fetch_fn)
    except (TypeError, ValueError):
        return fetch_fn(code)

    parameters = list(signature.parameters.values())
    parameter_names = {parameter.name for parameter in parameters}
    positional_parameters = [
        parameter
        for parameter in parameters
        if parameter.kind in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD)
    ]
    has_varargs = any(parameter.kind == parameter.VAR_POSITIONAL for parameter in parameters)

    if has_varargs or len(positional_parameters) >= 3:
        return fetch_fn(code, required_start_date, required_end_date)

    if {"required_start_date", "required_end_date"}.issubset(parameter_names):
        return fetch_fn(
            code,
            required_start_date=required_start_date,
            required_end_date=required_end_date,
        )

    if "days" in parameter_names:
        estimated_days = _estimate_fetch_days(required_start_date, required_end_date)
        return fetch_fn(code, days=estimated_days)

    return fetch_fn(code)


def ensure_backtest_data(
    code: str,
    required_start_date: str,
    required_end_date: str,
    fetch_fn=default_fresh_fetch,
) -> tuple[list[dict], dict]:
    cached = db.get_ohlc(code) or []
    if _covers(cached, required_start_date, required_end_date):
        return cached, {
            "source": "cache",
            "availableRange": _range_for(cached),
        }

    fresh = _call_fetch_fn(fetch_fn, code, required_start_date, required_end_date) or []
    merged = _merge_data(cached, fresh)
    if merged:
        db.save_ohlc(code, merged)

    if _covers(merged, required_start_date, required_end_date):
        return merged, {
            "source": "fresh_merged",
            "availableRange": _range_for(merged),
        }

    raise DataCoverageError(
        code=code,
        required_start_date=required_start_date,
        required_end_date=required_end_date,
        available_range=_range_for(merged),
    )


def _parse_date(date_str: str) -> datetime:
    return datetime.strptime(date_str, "%Y-%m-%d")


def _subtract_days(date_str: str, days: int) -> str:
    return (_parse_date(date_str) - timedelta(days=days)).strftime("%Y-%m-%d")


def _derive_context_days(config: dict) -> int:
    cup_max = int(config.get("cup", {}).get("max_duration", 180) or 0)
    handle_max = int(config.get("handle", {}).get("max_duration", 30) or 0)
    return max(120, cup_max + handle_max)


def _validate_request(start_date: str, end_date: str, handle_start_date: str | None, handle_end_date: str | None):
    if _parse_date(start_date) > _parse_date(end_date):
        raise ValueError("start_date must be on or before end_date")
    if (handle_start_date is None) != (handle_end_date is None):
        raise ValueError("handle_start_date and handle_end_date must both be provided")
    if handle_start_date is None:
        return
    if _parse_date(handle_start_date) > _parse_date(handle_end_date):
        raise ValueError("handle_start_date must be on or before handle_end_date")
    if handle_start_date < start_date or handle_end_date > end_date:
        raise ValueError("specified handle range must be within backtest range")



def _rows_between(data: list[dict], start_date: str, end_date: str) -> list[dict]:
    return [row for row in data if start_date <= row.get("date", "") <= end_date]


def _rows_until(data: list[dict], end_date: str) -> list[dict]:
    return [row for row in data if row.get("date", "") <= end_date]


def _lookup_stock_name(code: str) -> str:
    try:
        for stock in db.get_stock_pool() or []:
            if stock.get("code") == code:
                return stock.get("name", "")
    except Exception:
        return ""
    return ""


def _canonical_handle_end_date(result, data: list[dict]) -> str:
    if not data:
        return ""
    start_idx = getattr(result, "right_high_idx", -1) + 1
    low_idx = getattr(result, "handle_low_idx", -1)
    duration = int(getattr(result, "handle_duration", 0) or 0)
    end_idx = max(start_idx + max(duration - 1, 0), low_idx)
    end_idx = min(max(end_idx, 0), len(data) - 1)
    return data[end_idx]["date"]


def _pattern_identity(pattern: dict) -> tuple[str, str, str]:
    return (
        pattern.get("handleStartDate", ""),
        pattern.get("handleEndDate", ""),
        pattern.get("handleLowDate", ""),
    )


def _pattern_id(code: str, pattern: dict) -> str:
    return "{}-{}-{}-{}".format(
        code,
        pattern.get("handleStartDate", ""),
        pattern.get("handleEndDate", ""),
        pattern.get("handleLowDate", ""),
    )



def _serialize_rules(rules) -> list[dict]:
    serialized = []
    for rule in rules or []:
        if hasattr(rule, "to_dict"):
            serialized.append(rule.to_dict())
        elif isinstance(rule, dict):
            serialized.append(rule)
        else:
            serialized.append(dict(getattr(rule, "__dict__", {})))
    return serialized


def _build_pattern_entry(code: str, evaluation, window: list[dict]) -> dict:
    pattern = serialize_pattern_for_backtest(evaluation.result, window)
    pattern["handleEndDate"] = _canonical_handle_end_date(evaluation.result, window)
    detected_date = window[-1]["date"]
    return {
        "patternId": _pattern_id(code, pattern),
        "detectedDate": detected_date,
        "firstDetectedDate": detected_date,
        "score": getattr(evaluation.result, "score", 0),
        "passed": bool(getattr(evaluation, "passed", False)),
        "passedRules": _serialize_rules(getattr(evaluation, "passed_rules", [])),
        "failedRules": _serialize_rules(getattr(evaluation, "failed_rules", [])),
        "dryStable": getattr(evaluation, "dry_stable", None),
        **pattern,
    }


def _merge_pattern(existing: dict, candidate: dict) -> dict:
    merged = dict(existing)
    merged["firstDetectedDate"] = min(existing["firstDetectedDate"], candidate["firstDetectedDate"])
    if candidate.get("score", 0) > existing.get("score", 0):
        merged = dict(candidate)
        merged["firstDetectedDate"] = min(existing["firstDetectedDate"], candidate["firstDetectedDate"])
    return merged


def _write_backtest_json(result: dict, output_dir: str) -> str:
    backtest_dir = os.path.abspath(os.path.join(output_dir, "backtests"))
    os.makedirs(backtest_dir, exist_ok=True)
    filename = "single_stock_backtest_{}_{}_{}.json".format(
        result["code"],
        result["request"]["startDate"],
        result["request"]["endDate"],
    )
    filepath = os.path.join(backtest_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return filepath


def run_single_stock_cuphandle_backtest(
    code,
    start_date,
    end_date,
    config,
    handle_start_date=None,
    handle_end_date=None,
    context_days=None,
    fetch_fn=default_fresh_fetch,
):
    _validate_request(start_date, end_date, handle_start_date, handle_end_date)

    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)

    context_days_used = _derive_context_days(config) if context_days is None else max(0, int(context_days))
    required_start_date = _subtract_days(start_date, context_days_used) if context_days_used else start_date
    data, coverage = ensure_backtest_data(
        code,
        required_start_date=required_start_date,
        required_end_date=end_date,
        fetch_fn=fetch_fn,
    )

    working_data = _rows_between(data, required_start_date, end_date)

    name = _lookup_stock_name(code)
    engine = CupHandleStrategyEngine(config)
    backtest_rows = _rows_between(working_data, start_date, end_date)
    deduped_patterns: dict[tuple[str, str, str], dict] = {}

    for row in backtest_rows:
        window = _rows_until(working_data, row["date"])
        if not window:
            continue
        evaluation = engine.evaluate_at(window, code=code, name=name)
        if not getattr(evaluation.result, "found", False) or not getattr(evaluation, "passed", False):
            continue
        entry = _build_pattern_entry(code, evaluation, window)
        identity = _pattern_identity(entry)
        if identity in deduped_patterns:
            deduped_patterns[identity] = _merge_pattern(deduped_patterns[identity], entry)
        else:
            deduped_patterns[identity] = entry

    patterns = list(deduped_patterns.values())
    patterns.sort(key=lambda item: (item.get("firstDetectedDate", ""), item.get("detectedDate", ""), item.get("patternId", "")))

    specified_diagnosis = None
    if handle_start_date and handle_end_date:
        diagnosis_window = _rows_until(working_data, handle_end_date)
        diagnosis = engine.diagnose_handle(
            diagnosis_window,
            handle_start_date,
            handle_end_date,
            code=code,
            name=name,
        )
        specified_diagnosis = diagnosis.to_dict() if hasattr(diagnosis, "to_dict") else diagnosis

    result = {
        "code": code,
        "name": name,
        "strategyVersion": engine.strategy_version,
        "configHash": engine.config_hash,
        "request": {
            "startDate": start_date,
            "endDate": end_date,
            "handleStartDate": handle_start_date,
            "handleEndDate": handle_end_date,
            "contextDays": context_days_used,
        },
        "dataCoverage": {
            "source": coverage.get("source"),
            "requiredRange": {
                "startDate": required_start_date,
                "endDate": end_date,
            },
            "availableRange": coverage.get("availableRange"),
        },
        "summary": {
            "tradingDays": len(backtest_rows),
            "totalPatterns": len(patterns),
        },
        "patterns": patterns,
        "specifiedDiagnosis": specified_diagnosis,
        "ohlc": backtest_rows,
    }

    output_dir = config.get("output", {}).get("output_dir", "./output_data")
    result["outputFile"] = _write_backtest_json(result, output_dir)
    return result

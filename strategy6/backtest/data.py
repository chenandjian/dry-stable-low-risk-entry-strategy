"""Local OHLC audit and as-of slicing for Strategy6 research."""
from __future__ import annotations

import hashlib
import json


def audit_ohlc_rows(rows: list[dict]) -> dict:
    errors: list[str] = []
    dates = [str(row.get("date") or "") for row in rows]
    if len(set(dates)) != len(dates):
        errors.append("DUPLICATE_DATE")
    if dates != sorted(dates):
        errors.append("UNSORTED_DATE")
    for row in rows:
        try:
            open_price = float(row["open"])
            high = float(row["high"])
            low = float(row["low"])
            close = float(row["close"])
        except (KeyError, TypeError, ValueError):
            errors.append("INVALID_NUMERIC_FIELD")
            continue
        if min(open_price, high, low, close) <= 0 or high < max(open_price, close, low) or low > min(open_price, close, high):
            errors.append("ILLEGAL_OHLC")
    errors = list(dict.fromkeys(errors))
    return {
        "valid": not errors,
        "rows": len(rows),
        "min_date": min(dates) if dates else "",
        "max_date": max(dates) if dates else "",
        "errors": errors,
    }


def build_data_fingerprint(data_by_code: dict[str, list[dict]]) -> str:
    summary = []
    for code in sorted(data_by_code):
        rows = data_by_code[code]
        audit = audit_ohlc_rows(rows)
        row_digest = hashlib.sha256(
            json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        summary.append({"code": code, **audit, "row_digest": row_digest})
    payload = json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def slice_visible_rows(rows: list[dict], as_of_date: str) -> list[dict]:
    return [row for row in rows if str(row.get("date") or "") <= as_of_date]


def market_calendar_from_indexes(data_by_symbol: dict[str, list[dict]]) -> list[str]:
    dates: set[str] = set()
    for rows in data_by_symbol.values():
        dates.update(str(row.get("date") or "") for row in rows if row.get("date"))
    return sorted(dates)


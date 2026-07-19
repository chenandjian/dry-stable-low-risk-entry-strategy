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


def build_database_fingerprint(conn, *, batch_size: int = 10_000) -> str:
    """Hash the actual local universe and OHLC contents without loading them all."""
    digest = hashlib.sha256()
    queries = (
        (
            "stock_pool",
            "SELECT code, name, market FROM stock_pool ORDER BY code",
        ),
        (
            "daily_ohlc",
            """SELECT code, date, open, high, low, close, volume, turnover
               FROM daily_ohlc ORDER BY code, date""",
        ),
        (
            "market_index_ohlc",
            """SELECT symbol, date, open, high, low, close, volume, turnover, source
               FROM market_index_ohlc ORDER BY symbol, date""",
        ),
    )
    for table, query in queries:
        digest.update(f"table:{table}\n".encode("utf-8"))
        cursor = conn.execute(query)
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            for row in rows:
                payload = json.dumps(row, ensure_ascii=False, separators=(",", ":"), default=str)
                digest.update(payload.encode("utf-8"))
                digest.update(b"\n")
    return digest.hexdigest()


def slice_visible_rows(rows: list[dict], as_of_date: str) -> list[dict]:
    return [row for row in rows if str(row.get("date") or "") <= as_of_date]


def market_calendar_from_indexes(data_by_symbol: dict[str, list[dict]]) -> list[str]:
    dates: set[str] = set()
    for rows in data_by_symbol.values():
        dates.update(str(row.get("date") or "") for row in rows if row.get("date"))
    return sorted(dates)

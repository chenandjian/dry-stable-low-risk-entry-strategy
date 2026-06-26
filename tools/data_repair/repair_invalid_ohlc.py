"""Repair invalid daily_ohlc rows by replacing them with trusted source rows.

Default mode is dry-run. Use --apply to update SQLite.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scanner.baidu_source import fetch_baidu_daily
from scanner.sina_source import fetch_sina_daily
from scanner.tencent_source import fetch_tencent_daily


FetchFn = Callable[[str, int], list[dict] | None]


@dataclass
class RepairResult:
    scanned: int = 0
    repaired: int = 0
    missing_replacement: int = 0
    invalid_replacement: int = 0
    failed_fetch: int = 0
    skipped: int = 0


def is_valid_ohlc(row: dict) -> bool:
    try:
        open_ = float(row["open"])
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        volume = float(row.get("volume", 0))
    except (KeyError, TypeError, ValueError):
        return False
    if min(open_, high, low, close) <= 0 or volume < 0:
        return False
    return high >= max(open_, close, low) and low <= min(open_, close, high)


def find_invalid_rows(conn: sqlite3.Connection, task_id: str | None = None) -> list[dict]:
    conn.row_factory = sqlite3.Row
    if task_id:
        sql = """
            SELECT DISTINCT o.code, o.date, o.open, o.high, o.low, o.close, o.volume, o.turnover
            FROM task_stocks ts
            JOIN daily_ohlc o ON o.code = ts.code AND o.date = ts.kline_latest_date
            WHERE ts.task_id = ?
              AND ts.fallback_source = 'yfinance'
              AND (o.high < max(o.open, o.close, o.low) OR o.low > min(o.open, o.close, o.high))
            ORDER BY o.code, o.date
        """
        rows = conn.execute(sql, (task_id,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT code, date, open, high, low, close, volume, turnover
            FROM daily_ohlc
            WHERE high < max(open, close, low) OR low > min(open, close, high)
            ORDER BY code, date
        """).fetchall()
    return [dict(row) for row in rows]


def find_yfinance_sourced_codes(conn: sqlite3.Connection, task_id: str | None = None) -> list[str]:
    """Return distinct stock codes whose task metadata says yfinance produced data."""
    existing = {d[1] for d in conn.execute("PRAGMA table_info(task_stocks)").fetchall()}
    source_clauses = []
    if "primary_source" in existing:
        source_clauses.append("primary_source = 'yfinance'")
    if "fallback_source" in existing:
        source_clauses.append("fallback_source = 'yfinance'")
    if not source_clauses:
        return []

    params: list[str] = []
    where = f"({' OR '.join(source_clauses)})"
    if task_id:
        where = f"task_id = ? AND {where}"
        params.append(task_id)
    rows = conn.execute(
        f"SELECT DISTINCT code FROM task_stocks WHERE {where} ORDER BY code",
        params,
    ).fetchall()
    return [row[0] for row in rows]


def select_replacement(
    code: str,
    target_date: str,
    fetchers: list[tuple[str, FetchFn]],
    *,
    days: int = 10,
) -> tuple[str | None, dict | None]:
    invalid_source = None
    for source_name, fetch_fn in fetchers:
        data = fetch_fn(code, days)
        if not data:
            continue
        row = next((item for item in data if item.get("date") == target_date), None)
        if row is None:
            continue
        if not is_valid_ohlc(row):
            invalid_source = source_name
            continue
        return source_name, row
    return invalid_source, None


def update_daily_ohlc_row(conn: sqlite3.Connection, code: str, row: dict) -> None:
    conn.execute(
        """
        UPDATE daily_ohlc
           SET open = ?, high = ?, low = ?, close = ?, volume = ?, turnover = ?
         WHERE code = ? AND date = ?
        """,
        (
            float(row["open"]),
            float(row["high"]),
            float(row["low"]),
            float(row["close"]),
            float(row.get("volume", 0) or 0),
            float(row.get("turnover", 0) or 0),
            code,
            row["date"],
        ),
    )


def replace_daily_ohlc_series(conn: sqlite3.Connection, code: str, rows: list[dict]) -> None:
    conn.execute("DELETE FROM daily_ohlc WHERE code = ?", (code,))
    conn.executemany(
        """
        INSERT INTO daily_ohlc (code, date, open, high, low, close, volume, turnover)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                code,
                row["date"],
                float(row["open"]),
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
                float(row.get("volume", 0) or 0),
                float(row.get("turnover", 0) or 0),
            )
            for row in rows
        ],
    )


def repair_invalid_rows(
    db_path: str,
    *,
    task_id: str | None = None,
    apply: bool = False,
    fetchers: list[tuple[str, FetchFn]] | None = None,
    sleep_seconds: float = 0.0,
) -> RepairResult:
    fetchers = fetchers or [("baidu", fetch_baidu_daily), ("sina", fetch_sina_daily), ("tencent", fetch_tencent_daily)]
    conn = sqlite3.connect(db_path)
    try:
        rows = find_invalid_rows(conn, task_id=task_id)
        result = RepairResult(scanned=len(rows))
        for row in rows:
            source_name, replacement = select_replacement(
                row["code"], row["date"], fetchers, days=10,
            )
            if replacement is None:
                if source_name is None:
                    result.missing_replacement += 1
                else:
                    result.invalid_replacement += 1
                continue
            if apply:
                update_daily_ohlc_row(conn, row["code"], replacement)
            result.repaired += 1
            if sleep_seconds:
                time.sleep(sleep_seconds)
        if apply:
            conn.commit()
        return result
    finally:
        conn.close()


def refetch_yfinance_sourced_stocks(
    db_path: str,
    *,
    task_id: str | None = None,
    apply: bool = False,
    fetchers: list[tuple[str, FetchFn]] | None = None,
    days: int = 500,
    sleep_seconds: float = 0.0,
) -> RepairResult:
    """Re-fetch whole OHLC series for stocks previously populated by yfinance.

    The historical task metadata remains intact as an audit trail; only
    daily_ohlc is replaced when --apply is used.
    """
    fetchers = fetchers or [("baidu", fetch_baidu_daily), ("sina", fetch_sina_daily), ("tencent", fetch_tencent_daily)]
    conn = sqlite3.connect(db_path)
    try:
        codes = find_yfinance_sourced_codes(conn, task_id=task_id)
        result = RepairResult(scanned=len(codes))
        for code in codes:
            replacement = None
            invalid_seen = False
            for candidate_source, fetch_fn in fetchers:
                data = fetch_fn(code, days)
                if not data:
                    continue
                if not all(is_valid_ohlc(row) for row in data):
                    invalid_seen = True
                    continue
                replacement = data
                break
            if not replacement:
                if invalid_seen:
                    result.invalid_replacement += 1
                else:
                    result.failed_fetch += 1
                continue
            if apply:
                replace_daily_ohlc_series(conn, code, replacement)
            result.repaired += 1
            if sleep_seconds:
                time.sleep(sleep_seconds)
        if apply:
            conn.commit()
        return result
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--task-id")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--refetch-yfinance-sourced", action="store_true")
    parser.add_argument("--days", type=int, default=500)
    parser.add_argument("--sleep", type=float, default=0.0)
    args = parser.parse_args()

    if args.refetch_yfinance_sourced:
        result = refetch_yfinance_sourced_stocks(
            args.db,
            task_id=args.task_id,
            apply=args.apply,
            days=args.days,
            sleep_seconds=args.sleep,
        )
    else:
        result = repair_invalid_rows(
            args.db,
            task_id=args.task_id,
            apply=args.apply,
            sleep_seconds=args.sleep,
        )
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Repair legacy mixed-adjustment OHLC using one complete forward-adjusted source."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from scanner import db
from scanner.baidu_source import fetch_baidu_daily
from scanner.data_source import DataSourceManager
from scanner.sina_source import fetch_sina_daily
from scanner.tencent_source import fetch_tencent_daily

LEGACY_SOURCE_CHAIN = ("baidu", "sina", "tencent")
REPAIR_SOURCE_CHAIN = ("tencent", "sina", "baidu")


@dataclass
class RepairResult:
    code: str
    status: str
    source: str | None = None
    row_count: int = 0
    first_date: str | None = None
    latest_date: str | None = None
    source_errors: dict[str, str] = field(default_factory=dict)


def infer_legacy_selected_source(source_errors_json: str | None) -> str | None:
    if not source_errors_json:
        errors = {}
    else:
        try:
            errors = json.loads(source_errors_json)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        if not isinstance(errors, dict):
            return None
    for source in LEGACY_SOURCE_CHAIN:
        if source not in errors:
            return source
    return None


def find_legacy_sina_candidates() -> tuple[list[dict], list[dict]]:
    """Return stocks whose latest non-cache fetch can be inferred as legacy Sina."""
    conn = db.get_conn()
    rows = conn.execute(
        """
        WITH ranked AS (
            SELECT ts.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY code
                       ORDER BY datetime(COALESCE(kline_fetched_at, updated_at)) DESC,
                                rowid DESC
                   ) AS rn
            FROM task_stocks ts
            WHERE primary_source IS NOT NULL
              AND primary_source <> 'cache'
              AND kline_fetched_at IS NOT NULL
        )
        SELECT code, task_id, source_errors, kline_fetched_at
        FROM ranked
        WHERE rn=1
        ORDER BY code
        """
    ).fetchall()
    candidates: list[dict] = []
    unknown: list[dict] = []
    for code, task_id, source_errors, fetched_at in rows:
        selected = infer_legacy_selected_source(source_errors)
        item = {
            "code": code,
            "task_id": task_id,
            "source_errors": source_errors,
            "kline_fetched_at": fetched_at,
            "inferred_source": selected,
        }
        if selected == "sina" and db.get_ohlc(code):
            candidates.append(item)
        elif selected is None:
            unknown.append(item)
    return candidates, unknown


def repair_stock(
    code: str,
    *,
    requested_days: int,
    fetchers: dict[str, Callable] | None = None,
    source_manager: DataSourceManager | None = None,
    dry_run: bool = False,
    repair_run_id: str | None = None,
) -> RepairResult:
    existing = db.get_ohlc(code) or []
    if not existing:
        return RepairResult(code=code, status="skipped", source_errors={"database": "no existing OHLC"})

    requested_days = max(1, int(requested_days), len(existing))
    required_rows = len(existing)
    existing_latest = existing[-1]["date"]
    fetchers = fetchers or {
        "tencent": fetch_tencent_daily,
        "sina": fetch_sina_daily,
        "baidu": fetch_baidu_daily,
    }
    source_errors: dict[str, str] = {}

    for source in REPAIR_SOURCE_CHAIN:
        fetcher = fetchers[source]
        locked = False
        if source_manager is not None:
            if not source_manager.acquire(source):
                source_errors[source] = "busy"
                continue
            locked = True
        try:
            fetched = fetcher(code, days=requested_days)
        except Exception as exc:
            source_errors[source] = str(exc)
            continue
        finally:
            if locked:
                source_manager.release(source)
        rows, error = _normalize_and_validate(fetched)
        if error:
            source_errors[source] = error
            continue
        if len(rows) < required_rows:
            source_errors[source] = f"insufficient rows: required {required_rows}, got {len(rows)}"
            continue
        replacement = rows[-requested_days:]
        if replacement[-1]["date"] < existing_latest:
            source_errors[source] = (
                f"latest date regressed: existing {existing_latest}, got {replacement[-1]['date']}"
            )
            continue
        status = "would_repair" if dry_run else "repaired"
        if not dry_run:
            db.replace_ohlc_with_metadata(
                code,
                replacement,
                source=source,
                fetched_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                repair_run_id=repair_run_id,
            )
        return RepairResult(
            code=code,
            status=status,
            source=source,
            row_count=len(replacement),
            first_date=replacement[0]["date"],
            latest_date=replacement[-1]["date"],
            source_errors=source_errors,
        )
    return RepairResult(code=code, status="failed", source_errors=source_errors)


def _normalize_and_validate(data: list[dict] | None) -> tuple[list[dict], str | None]:
    if not data:
        return [], "empty response"
    rows_by_date: dict[str, dict] = {}
    try:
        for raw in data:
            row = {
                "date": str(raw["date"])[:10],
                "open": float(raw["open"]),
                "high": float(raw["high"]),
                "low": float(raw["low"]),
                "close": float(raw["close"]),
                "volume": float(raw["volume"]),
                "turnover": float(raw.get("turnover") or 0),
            }
            numbers = tuple(row[key] for key in ("open", "high", "low", "close", "volume", "turnover"))
            if not all(math.isfinite(value) for value in numbers):
                return [], "non-finite OHLC"
            if min(row["open"], row["high"], row["low"], row["close"]) <= 0:
                return [], "non-positive OHLC"
            if row["volume"] < 0 or row["turnover"] < 0:
                return [], "negative volume or turnover"
            if row["high"] < max(row["open"], row["close"], row["low"]):
                return [], "invalid OHLC high"
            if row["low"] > min(row["open"], row["close"], row["high"]):
                return [], "invalid OHLC low"
            rows_by_date[row["date"]] = row
    except (KeyError, TypeError, ValueError):
        return [], "invalid row schema"
    rows = sorted(rows_by_date.values(), key=lambda row: row["date"])
    return rows, None

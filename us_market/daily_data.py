from __future__ import annotations

import math
from datetime import date, datetime, timezone
from numbers import Real
from uuid import uuid4

from .instruments import provider_symbol


def _number(value, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"invalid {field}: {value!r}")
    return float(value)


def normalize_bars(raw: list[dict]) -> list[dict]:
    """Keep provider units; zero/missing amount is unknown, not zero liquidity."""
    if not raw:
        raise ValueError("empty daily bars")
    result, dates = [], set()
    for item in raw:
        day = str(item.get("trade_date", item.get("date", "")))
        if date.fromisoformat(day).isoformat() != day:
            raise ValueError(f"invalid daily date: {day}")
        if day in dates:
            raise ValueError(f"duplicate trade date: {day}")
        dates.add(day)
        row = {field: _number(item.get(field), field) for field in ("open", "high", "low", "close", "volume")}
        if min(row[k] for k in ("open", "high", "low", "close")) <= 0:
            raise ValueError(f"non-positive OHLC on {day}")
        if not row["low"] <= min(row["open"], row["close"]) <= max(row["open"], row["close"]) <= row["high"]:
            raise ValueError(f"invalid OHLC ordering on {day}")
        if row["volume"] < 0:
            raise ValueError(f"negative volume on {day}")
        amount = item.get("amount", item.get("turnover"))
        if amount is not None:
            amount = _number(amount, "amount")
            if amount < 0:
                raise ValueError(f"negative amount on {day}")
        result.append(dict(date=day, **row, turnover=amount if amount else None))
    return sorted(result, key=lambda row: row["date"])


def _create_free_sdk():
    from tickflow import TickFlow

    sdk = TickFlow.free(base_url="https://free-api.tickflow.org", timeout=20, max_retries=0)
    # SDK 0.1.26 free() passes None, but BaseClient then reads the environment key.
    # Clear only this private client's key; never mutate the process environment.
    transport = getattr(sdk, "_client", None)
    if transport is None or not hasattr(transport, "api_key"):
        sdk.close()
        raise RuntimeError("unsupported TickFlow SDK: cannot guarantee unauthenticated requests")
    transport.api_key = None
    return sdk


def diagnose(repository, symbol: str, *, count: int = 1100, adjustment: str = "forward") -> dict:
    """Explicit free-only diagnostic query. Never feeds the production engine."""
    symbol = provider_symbol(symbol)
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 5000:
        raise ValueError("count must be between 1 and 5000")
    if adjustment not in {"none", "forward", "forward_additive"}:
        raise ValueError("unsupported adjustment")
    rows = _fetch_daily(symbol, count, adjustment)
    snapshot = {
        "snapshot_id": uuid4().hex, "symbol": symbol, "source": "tickflow_free",
        "currency": "USD", "adjustment": adjustment,
        "price_basis": f"PROVIDER_{adjustment.upper()}_UNVERIFIED", "volume_basis": "UNKNOWN",
        "fetched_at": datetime.now(timezone.utc).isoformat(), "requested_count": count,
        "row_count": len(rows), "first_date": rows[0]["date"], "latest_date": rows[-1]["date"],
        "missing_turnover_rows": sum(row["turnover"] is None for row in rows),
        "formal_scan_allowed": False,
        "blocking_reasons": ["PRICE_BASIS_UNVERIFIED", "VOLUME_BASIS_UNVERIFIED",
                             "REAL_INDEX_HISTORY_UNVERIFIED", "US_CALENDAR_UNVERIFIED"],
        "rows": rows,
    }
    repository.save_snapshot(snapshot)
    return snapshot


def _fetch_daily(symbol, count, adjustment, *, allow_empty=False):
    sdk = _create_free_sdk()
    try:
        frame = sdk.klines.get(symbol, period="1d", count=count, adjust=adjustment, as_dataframe=True)
        raw = frame.to_dict("records") if hasattr(frame, "to_dict") else frame
        if not isinstance(raw, list):
            raise ValueError("unexpected daily response")
        for item in raw:
            if "symbol" in item and item["symbol"] != symbol:
                raise ValueError("response symbol does not match request")
        return [] if allow_empty and not raw else normalize_bars(raw)
    finally:
        sdk.close()


def probe_provider_daily(symbol: str, *, now: datetime | None = None) -> dict:
    """Read the free provider directly without touching a local repository."""
    from .calendar import target_session

    symbol = provider_symbol(symbol)
    rows = _fetch_daily(symbol, 5, "forward", allow_empty=True)
    checked_at = now or datetime.now(timezone.utc)
    target = target_session(checked_at)["target_trade_date"]
    target_bar = next((row for row in rows if row["date"] == target), None)
    latest_completed = next((row for row in reversed(rows) if row["date"] <= target), None)
    return {
        "symbol": symbol, "source": "tickflow_free", "checked_at": checked_at.isoformat(),
        "target_trade_date": target, "latest_date": rows[-1]["date"] if rows else None,
        "latest_completed_date": latest_completed["date"] if latest_completed else None,
        "target_bar": target_bar,
        "status": "UPDATED" if target_bar else "TARGET_MISSING" if rows else "NO_DATA",
    }

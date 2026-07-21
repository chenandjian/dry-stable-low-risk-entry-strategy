from __future__ import annotations

import datetime as dt
import math
from typing import Any

from .models import TickFlowDataError


REQUIRED_COLUMNS = {"trade_date", "open", "high", "low", "close", "volume", "amount"}


def _to_date(value: Any) -> str:
    if hasattr(value, "date") and not isinstance(value, (str, dt.date)):
        value = value.date()
    text = str(value).strip()[:10]
    try:
        return dt.date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise TickFlowDataError(f"invalid trade date {value!r}") from exc


def _finite_number(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise TickFlowDataError(f"invalid {field}: {value!r}") from exc
    if not math.isfinite(number):
        raise TickFlowDataError(f"non-finite {field}: {value!r}")
    return number


def normalize_frame(frame, *, trim_non_positive_prefix: bool = False) -> list[dict]:
    if frame is None or getattr(frame, "empty", True):
        raise TickFlowDataError("empty TickFlow daily frame")

    columns = set(getattr(frame, "columns", ()))
    missing = sorted(REQUIRED_COLUMNS - columns)
    if missing:
        raise TickFlowDataError(f"missing columns: {', '.join(missing)}")

    prepared: list[tuple[str, dict]] = []
    seen_dates: set[str] = set()
    for raw in frame.to_dict(orient="records"):
        trade_date = _to_date(raw["trade_date"])
        if trade_date in seen_dates:
            raise TickFlowDataError(f"duplicate trade date: {trade_date}")
        seen_dates.add(trade_date)
        prepared.append((trade_date, raw))

    if trim_non_positive_prefix:
        non_positive_dates = []
        for trade_date, raw in prepared:
            prices = tuple(
                _finite_number(raw[field], field)
                for field in ("open", "high", "low", "close")
            )
            if min(prices) <= 0:
                non_positive_dates.append(trade_date)
        if non_positive_dates:
            cutoff = max(non_positive_dates)
            prepared = [(date, raw) for date, raw in prepared if date > cutoff]
            if not prepared:
                raise TickFlowDataError(
                    f"no positive OHLC after adjusted-price cutoff {cutoff}"
                )

    normalized: list[dict] = []
    for trade_date, raw in prepared:
        open_price = _finite_number(raw["open"], "open")
        high = _finite_number(raw["high"], "high")
        low = _finite_number(raw["low"], "low")
        close = _finite_number(raw["close"], "close")
        volume_lots = _finite_number(raw["volume"], "volume")
        turnover = _finite_number(raw["amount"], "amount")

        if min(open_price, high, low, close) <= 0:
            raise TickFlowDataError(f"non-positive OHLC on {trade_date}")
        if high < max(open_price, low, close) or low > min(open_price, high, close):
            raise TickFlowDataError(f"invalid OHLC relationship on {trade_date}")
        if volume_lots < 0 or turnover < 0:
            raise TickFlowDataError(f"negative volume or amount on {trade_date}")

        normalized.append(
            {
                "date": trade_date,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume_lots * 100.0,
                "turnover": turnover,
            }
        )

    normalized.sort(key=lambda row: row["date"])
    return normalized


__all__ = ["TickFlowDataError", "normalize_frame"]

"""Strategy4 real topic/industry index K-line source adapters."""
from __future__ import annotations

from datetime import date, datetime


class TopicIndexSourceError(RuntimeError):
    """Raised when topic index K-line fetch or normalization fails."""


def fetch_topic_index_ohlc(
    *,
    topic_name: str,
    topic_type: str,
    start_date: str,
    end_date: str,
    preferred_sources: list[str] | None = None,
) -> tuple[list[dict], dict]:
    """Fetch real topic index OHLC from THS/Eastmoney through AkShare."""
    preferred_sources = preferred_sources or ["akshare_ths", "akshare_eastmoney"]
    errors: list[str] = []
    for source in preferred_sources:
        try:
            rows = _fetch_from_source(source, topic_name, topic_type, start_date, end_date)
            normalized = normalize_topic_index_rows(rows, source=source)
            if normalized:
                return normalized, {
                    "source": source,
                    "source_topic_name": topic_name,
                    "source_topic_code": "",
                }
            errors.append(f"{source}: empty")
        except TopicIndexSourceError as exc:
            errors.append(f"{source}: {exc}")
        except Exception as exc:  # pragma: no cover - external source variability
            errors.append(f"{source}: {exc}")
    raise TopicIndexSourceError("; ".join(errors) or "TOPIC_INDEX_SOURCE_FAILED")


def normalize_topic_index_rows(rows, *, source: str) -> list[dict]:
    """Normalize THS/Eastmoney board K-lines into the local OHLC shape."""
    normalized: list[dict] = []
    for row in _rows_from_frame(rows):
        item = {
            "date": _date_text(_pick(row, "日期", "date", "时间")),
            "open": _to_float(_pick(row, "开盘价", "开盘", "open")),
            "high": _to_float(_pick(row, "最高价", "最高", "high")),
            "low": _to_float(_pick(row, "最低价", "最低", "low")),
            "close": _to_float(_pick(row, "收盘价", "收盘", "close")),
            "volume": _to_float(_pick(row, "成交量", "volume", default=0)),
            "amount": _to_float(_pick(row, "成交额", "amount", "turnover", default=0)),
            "turnover": _pct_or_amount(_pick(row, "换手率", "turnover_rate", default=None), _pick(row, "成交额", default=0)),
            "change_pct": _pct(_pick(row, "涨跌幅", "change_pct", "涨幅", default=0)),
            "raw_snapshot": dict(row),
        }
        if not item["date"]:
            raise TopicIndexSourceError("INVALID_DATE")
        _validate_ohlc(item)
        normalized.append(item)
    normalized.sort(key=lambda r: r["date"])
    return normalized


def _fetch_from_source(source: str, topic_name: str, topic_type: str, start_date: str, end_date: str):
    try:
        import akshare as ak
    except Exception as exc:  # pragma: no cover - optional runtime dependency
        raise TopicIndexSourceError(f"AKSHARE_IMPORT_FAILED: {exc}") from exc

    start = _compact_date(start_date)
    end = _compact_date(end_date)
    if source == "akshare_ths":
        if topic_type == "industry":
            func_name = "stock_board_industry_index_ths"
        else:
            func_name = "stock_board_concept_index_ths"
        func = getattr(ak, func_name, None)
        if func is None:
            raise TopicIndexSourceError(f"{func_name}: missing")
        return func(symbol=topic_name, start_date=start, end_date=end)

    if source == "akshare_eastmoney":
        if topic_type == "industry":
            func_name = "stock_board_industry_hist_em"
        else:
            func_name = "stock_board_concept_hist_em"
        func = getattr(ak, func_name, None)
        if func is None:
            raise TopicIndexSourceError(f"{func_name}: missing")
        if topic_type == "industry":
            return func(symbol=topic_name, start_date=start, end_date=end, period="日k", adjust="")
        return func(symbol=topic_name, period="daily", start_date=start, end_date=end, adjust="")

    raise TopicIndexSourceError(f"UNSUPPORTED_TOPIC_INDEX_SOURCE: {source}")


def _validate_ohlc(row: dict) -> None:
    o, h, l, c = row["open"], row["high"], row["low"], row["close"]
    if min(o, h, l, c) <= 0:
        raise TopicIndexSourceError("INVALID_OHLC: non-positive price")
    if h < max(o, l, c) or l > min(o, h, c):
        raise TopicIndexSourceError("INVALID_OHLC: high/low inconsistent")


def _rows_from_frame(frame) -> list[dict]:
    if hasattr(frame, "to_dict"):
        return frame.to_dict("records")
    return list(frame or [])


def _pick(row: dict, *keys, default=None):
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return default


def _date_text(value) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text[:10]


def _compact_date(value: str) -> str:
    return str(value or "").replace("-", "")[:8]


def _to_float(value) -> float:
    try:
        if isinstance(value, str):
            value = value.replace("%", "").replace(",", "").strip()
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _pct(value) -> float:
    number = _to_float(value)
    return number / 100 if abs(number) > 1 else number


def _pct_or_amount(value, amount_value) -> float:
    if value not in (None, ""):
        return _pct(value)
    return _to_float(amount_value)

import logging
import math
from datetime import date, datetime

logger = logging.getLogger(__name__)


def fetch_sina_daily(code: str, days: int = 250) -> list[dict] | None:
    """Fetch forward-adjusted A-share daily bars from Sina through AkShare."""
    try:
        ak = _load_akshare()
        frame = ak.stock_zh_a_daily(
            symbol=_to_sina_symbol(code),
            start_date="19900101",
            end_date=date.today().strftime("%Y%m%d"),
            adjust="qfq",
        )
        if frame is None or frame.empty:
            logger.warning("AkShare Sina returned empty data for %s", code)
            return None

        required = {"date", "open", "high", "low", "close", "volume"}
        if not required.issubset(set(frame.columns)):
            logger.warning("AkShare Sina returned missing columns for %s", code)
            return None

        rows_by_date: dict[str, dict] = {}
        for item in frame.to_dict("records"):
            row = _normalize_row(item)
            if row is not None:
                rows_by_date[row["date"]] = row
        rows = sorted(rows_by_date.values(), key=lambda row: row["date"])
        if not rows:
            return None
        return rows[-int(days):] if days else rows
    except Exception as exc:
        if _is_rate_limited(exc):
            raise RuntimeError(str(exc)) from exc
        logger.warning("AkShare Sina fetch/parse error for %s: %s", code, exc)
        return None


def _load_akshare():
    import akshare as ak

    return ak


def _to_sina_symbol(code: str) -> str:
    normalized = str(code).strip().lower()
    if normalized.startswith(("sh", "sz", "bj")):
        return normalized
    if "." in normalized:
        normalized = normalized.split(".", 1)[0]
    if normalized.startswith("6"):
        return f"sh{normalized}"
    if normalized.startswith(("4", "8")):
        return f"bj{normalized}"
    return f"sz{normalized}"


def _normalize_row(item: dict) -> dict | None:
    try:
        raw_date = item["date"]
        if isinstance(raw_date, datetime):
            trade_date = raw_date.date().isoformat()
        elif isinstance(raw_date, date):
            trade_date = raw_date.isoformat()
        else:
            trade_date = str(raw_date)[:10]
        open_ = float(item["open"])
        high = float(item["high"])
        low = float(item["low"])
        close = float(item["close"])
        volume = float(item["volume"])
        amount = item.get("amount")
        turnover = float(amount) if amount is not None else volume * close
        values = (open_, high, low, close, volume, turnover)
        if not trade_date or not all(math.isfinite(value) for value in values):
            return None
        if min(open_, high, low, close) <= 0 or volume < 0 or turnover < 0:
            return None
        if high < max(open_, close, low) or low > min(open_, close, high):
            return None
        return {
            "date": trade_date,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "turnover": turnover,
        }
    except (KeyError, TypeError, ValueError):
        return None


def _is_rate_limited(exc: Exception) -> bool:
    text = str(exc)
    return "456" in text or "429" in text

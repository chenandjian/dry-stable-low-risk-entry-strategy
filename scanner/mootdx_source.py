# scanner/mootdx_source.py
import logging

logger = logging.getLogger(__name__)

try:
    from mootdx.quotes import Quotes
except Exception:  # pragma: no cover - dependency may be absent before install
    Quotes = None


def fetch_mootdx_daily(code: str, days: int = 250) -> list[dict] | None:
    """从 mootdx 通达信 TCP 源获取单只股票日线数据。"""
    if Quotes is None:
        logger.warning("mootdx is not installed; cannot fetch %s", code)
        return None

    try:
        client = Quotes.factory(market="std")
        bars = client.bars(
            symbol=_normalize_code(code),
            category=4,
            market=_market_id(code),
            offset=days,
        )
        rows = [_normalize_row(row) for row in _to_records(bars)]
        rows = [row for row in rows if row is not None]
        if not rows:
            return None
        return sorted(rows, key=lambda row: row["date"])
    except Exception as exc:
        logger.warning("mootdx fetch error for %s: %s", code, exc)
        return None


def _normalize_code(code: str) -> str:
    code = code.strip().lower()
    if code.startswith(("sh", "sz", "bj")):
        return code[2:]
    if "." in code:
        return code.split(".", 1)[0]
    return code


def _market_id(code: str) -> int:
    normalized = _normalize_code(code)
    return 1 if normalized.startswith(("6", "9")) else 0


def _to_records(bars) -> list[dict]:
    if bars is None:
        return []
    if hasattr(bars, "to_dict"):
        return bars.to_dict("records")
    if isinstance(bars, list):
        return bars
    return []


def _normalize_row(row: dict) -> dict | None:
    try:
        date = str(row.get("datetime") or row.get("date") or "")[:10]
        if not date:
            return None
        close = float(row["close"])
        volume = float(row.get("vol", row.get("volume", 0)) or 0)
        turnover = float(row.get("amount", row.get("turnover", close * volume)) or 0)
        return {
            "date": date,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": close,
            "volume": volume,
            "turnover": turnover,
        }
    except (KeyError, TypeError, ValueError):
        return None

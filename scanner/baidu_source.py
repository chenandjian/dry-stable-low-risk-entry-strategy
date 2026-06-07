# scanner/baidu_source.py
import logging

import requests

logger = logging.getLogger(__name__)

BAIDU_KLINE_URL = "https://finance.pae.baidu.com/selfselect/getstockquotation"


def fetch_baidu_daily(code: str, days: int = 250) -> list[dict] | None:
    """从百度股市通 K 线接口获取单只股票日线数据。"""
    params = {
        "all": "1",
        "isIndex": "false",
        "isBk": "false",
        "isBlock": "false",
        "isFutures": "false",
        "isStock": "true",
        "newFormat": "1",
        "group": "quotation_kline_ab",
        "finClientType": "pc",
        "code": _normalize_code(code),
        "ktype": "1",
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/vnd.finance-web.v1+json",
        "Origin": "https://gushitong.baidu.com",
        "Referer": "https://gushitong.baidu.com/",
    }
    try:
        resp = requests.get(BAIDU_KLINE_URL, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        rows = _parse_payload(resp.json())
        if not rows:
            return None
        return rows[-days:]
    except Exception as exc:
        logger.warning("Baidu kline fetch/parse error for %s: %s", code, exc)
        return None


def _normalize_code(code: str) -> str:
    code = code.strip().lower()
    if code.startswith(("sh", "sz", "bj")):
        return code[2:]
    if "." in code:
        return code.split(".", 1)[0]
    return code


def _parse_payload(payload: dict) -> list[dict]:
    market_data = payload.get("Result", {}).get("newMarketData", {})
    keys = market_data.get("keys") or []
    raw_rows = market_data.get("marketData") or ""
    required = {"time", "open", "close", "high", "low", "volume", "amount"}
    if not raw_rows or not required.issubset(set(keys)):
        return []

    rows = []
    for raw_row in raw_rows.split(";"):
        if not raw_row.strip():
            continue
        values = raw_row.split(",")
        if len(values) < len(keys):
            continue
        row = _normalize_row(dict(zip(keys, values)))
        if row:
            rows.append(row)
    return sorted(rows, key=lambda row: row["date"])


def _normalize_row(item: dict) -> dict | None:
    try:
        return {
            "date": str(item["time"])[:10],
            "open": float(item["open"]),
            "high": float(item["high"]),
            "low": float(item["low"]),
            "close": float(item["close"]),
            "volume": float(item["volume"]),
            "turnover": float(item["amount"]),
        }
    except (KeyError, TypeError, ValueError):
        return None

# scanner/tencent_source.py
import requests
import json
import logging
import time

logger = logging.getLogger(__name__)


def fetch_tencent_daily(code: str, days: int = 250) -> list[dict] | None:
    """从腾讯财经获取单只股票的日线数据（内部回退到新浪API）。

    Args:
        code: 股票代码，如 '600036' 或 '000001'
        days: 获取最近 N 个交易日数据

    Returns:
        list[dict]: [{date, open, high, low, close, volume, turnover}, ...]
        按日期升序排列。失败返回 None。
    """
    if code.startswith("6"):
        symbol = f"sh{code}"
    else:
        symbol = f"sz{code}"

    # Try Tencent K-line API (may be unavailable)
    data = _try_tencent_kline(symbol, days)
    if data:
        return data

    # Fallback: use Sina API (same as sina_source but accessed here)
    logger.debug(f"Tencent API unavailable for {code}, falling back to Sina")
    data = _try_sina_kline(symbol, days)
    if data:
        return data

    return None


def _try_tencent_kline(symbol: str, days: int) -> list[dict] | None:
    """Attempt Tencent K-line API."""
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    params = {
        "param": f"{symbol},day,,,{days}",
        "_var": "kline_day",
    }

    try:
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        text = resp.text

        json_str = text.split("=", 1)[1].strip() if "=" in text else text
        data = json.loads(json_str)

        if data.get("code") != 0:
            return None

        stock_data = data.get("data", {}).get(symbol, {})
        klines = stock_data.get("qfqday") or stock_data.get("day", [])

        if not klines:
            return None

        result = []
        for item in klines:
            result.append({
                "date": item[0],
                "open": float(item[1]),
                "close": float(item[2]),
                "high": float(item[3]),
                "low": float(item[4]),
                "volume": float(item[5]),
                "turnover": float(item[2]) * float(item[5]),
            })
        return result

    except Exception:
        return None


def _try_sina_kline(symbol: str, days: int) -> list[dict] | None:
    """Use Sina API as fallback."""
    url = "https://quotes.sina.cn/cn/api/jsonp_v2.php/data/CN_MarketDataService.getKLineData"
    params = {
        "symbol": symbol,
        "scale": "240",
        "datalen": str(days),
    }

    try:
        resp = requests.get(url, params=params, timeout=5, headers={
            "Referer": "https://finance.sina.com.cn",
        })
        resp.raise_for_status()
        text = resp.text

        # Parse JSONP: data([...]);
        if text.startswith("data(") and text.endswith(");"):
            text = text[5:-2]
        elif "(" in text:
            start = text.index("(") + 1
            end = text.rindex(")")
            text = text[start:end]

        raw_data = json.loads(text)

        if not raw_data or not isinstance(raw_data, list):
            return None

        result = []
        for item in raw_data:
            close_price = float(item["close"])
            volume = float(item["volume"])
            result.append({
                "date": item["day"],
                "open": float(item["open"]),
                "high": float(item["high"]),
                "low": float(item["low"]),
                "close": close_price,
                "volume": volume,
                "turnover": volume * close_price,
            })
        return result

    except Exception:
        return None

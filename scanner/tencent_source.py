# scanner/tencent_source.py
import requests
import json
import logging

logger = logging.getLogger(__name__)


def fetch_tencent_daily(code: str, days: int = 250) -> list[dict] | None:
    """从腾讯财经获取单只股票的日线数据。

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

    return _try_tencent_kline(symbol, days)


def _try_tencent_kline(symbol: str, days: int) -> list[dict] | None:
    """Attempt Tencent K-line API."""
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    params = {
        "param": f"{symbol},day,,,{days},qfq",
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
                "volume": float(item[5]) * 100,
                "turnover": float(item[2]) * float(item[5]) * 100,
            })
        return result

    except Exception:
        return None

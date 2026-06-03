# scanner/sina_source.py
import requests
import logging

logger = logging.getLogger(__name__)


def fetch_sina_daily(code: str, days: int = 250) -> list[dict] | None:
    """从新浪获取单只股票的日线数据。

    Args:
        code: 股票代码，如 '600036' 或 '000001'
        days: 获取最近 N 个交易日数据

    Returns:
        list[dict]: [{date, open, high, low, close, volume, turnover}, ...]
        按日期升序排列。失败返回 None。
    """
    # 判断交易所前缀
    if code.startswith("6"):
        symbol = f"sh{code}"
    else:
        symbol = f"sz{code}"

    url = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData/getKLineData"
    params = {
        "symbol": symbol,
        "scale": "240",  # 日线
        "ma": "no",
        "datalen": str(days),
    }

    try:
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        raw_data = resp.json()

        if not raw_data or not isinstance(raw_data, list):
            logger.warning(f"Sina returned empty/invalid data for {code}")
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
                "turnover": volume * close_price / 10000,
            })
        return result

    except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as e:
        logger.warning(f"Sina fetch failed for {code}: {e}")
        return None
    except (ValueError, KeyError, TypeError) as e:
        logger.warning(f"Sina parse error for {code}: {e}")
        return None

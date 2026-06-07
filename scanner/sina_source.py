# scanner/sina_source.py
import requests
import logging
import time
import json

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

    url = "https://quotes.sina.cn/cn/api/jsonp_v2.php/data/CN_MarketDataService.getKLineData"
    params = {
        "symbol": symbol,
        "scale": "240",  # 日线
        "datalen": str(days),
    }

    max_retries = 2
    last_error = None
    for attempt in range(max_retries + 1):
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
                # Handle other JSONP variations
                start = text.index("(") + 1
                end = text.rindex(")")
                text = text[start:end]

            raw_data = json.loads(text)

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
                    "turnover": volume * close_price,
                })
            return result

        except (requests.Timeout, requests.ConnectionError) as e:
            last_error = e
            if attempt < max_retries:
                delay = 2 ** attempt  # 1s, 2s
                logger.debug(f"Sina retry {attempt + 1}/{max_retries} for {code} after {delay}s")
                time.sleep(delay)
            else:
                logger.warning(f"Sina fetch failed for {code} after {max_retries} retries: {e}")
                return None
        except requests.HTTPError as e:
            if _is_rate_limited(e):
                raise RuntimeError(str(e)) from e
            logger.warning(f"Sina fetch/parse error for {code}: {e}")
            return None
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
            logger.warning(f"Sina fetch/parse error for {code}: {e}")
            return None


def _is_rate_limited(exc: Exception) -> bool:
    text = str(exc)
    return "456" in text or "429" in text

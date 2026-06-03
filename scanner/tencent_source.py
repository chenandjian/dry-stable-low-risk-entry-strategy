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

    Note:
        腾讯日线数据格式: ["2026-06-03", "42.000(open)", "43.000(close)", "41.500(high)", "42.850(low)", "123456.00(volume)"]
        注意字段顺序: date, open, close, high, low, volume
    """
    if code.startswith("6"):
        symbol = f"sh{code}"
    else:
        symbol = f"sz{code}"

    url = "http://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    params = {
        "param": f"{symbol},day,,,{days}",
        "_var": "kline_day",
    }

    try:
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        text = resp.text

        # 响应格式: kline_day={...json...}
        json_str = text.split("=", 1)[1].strip() if "=" in text else text
        data = json.loads(json_str)

        stock_data = data.get("data", {}).get(symbol, {})
        # 优先使用前复权数据
        klines = stock_data.get("qfqday") or stock_data.get("day", [])

        if not klines:
            logger.warning(f"Tencent returned empty data for {code}")
            return None

        result = []
        for item in klines:
            # 腾讯格式: [date, open, close, high, low, volume]
            result.append({
                "date": item[0],
                "open": float(item[1]),
                "close": float(item[2]),
                "high": float(item[3]),
                "low": float(item[4]),
                "volume": float(item[5]),
                "turnover": None,  # 腾讯日线不直接给成交额
            })
        return result

    except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as e:
        logger.warning(f"Tencent fetch failed for {code}: {e}")
        return None
    except (ValueError, KeyError, IndexError, json.JSONDecodeError) as e:
        logger.warning(f"Tencent parse error for {code}: {e}")
        return None

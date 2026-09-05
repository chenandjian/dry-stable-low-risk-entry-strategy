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
    """Attempt Tencent K-line API.

    K-line array format: [date, open, close, high, low, volume]. Tencent
    returns lots for most A shares but shares for some instruments. The unit
    is inferred from the same-day exact quote amount before normalization.
    The response also includes ``qt`` real-time quote data which contains
    the actual turnover (amount) for the latest trading day.  We use that
    exact amount for the last row and fall back to ``close * volume(股)``
    for historical rows where no per-row amount is available.
    """
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

        # Extract exact amount (万元) from real-time quote for the latest day
        qt_amount = None
        qt = stock_data.get("qt", {}).get(symbol, [])
        if len(qt) > 57 and qt[57]:
            try:
                qt_amount = float(qt[57]) * 10000  # 万元 → 元
            except (ValueError, TypeError):
                pass

        volume_multiplier = _infer_volume_multiplier(klines, qt, qt_amount)
        if volume_multiplier is None:
            logger.warning("%s cannot infer Tencent K-line volume unit", symbol)
            return None

        result = []
        for i, item in enumerate(klines):
            open_ = float(item[1])
            close = float(item[2])
            high = float(item[3])
            low = float(item[4])
            vol_shares = float(item[5]) * volume_multiplier

            is_last = (i == len(klines) - 1)
            if is_last and qt_amount is not None:
                turnover = qt_amount
            else:
                turnover = close * vol_shares

            result.append({
                "date": item[0],
                "open": open_,
                "close": close,
                "high": high,
                "low": low,
                "volume": vol_shares,
                "turnover": turnover,
            })
        return result

    except Exception:
        return None


def _infer_volume_multiplier(
    klines: list[list],
    quote: list,
    quote_amount: float | None,
) -> int | None:
    """Infer whether Tencent K-line volume is already shares or is lots."""
    if not klines or quote_amount is None or quote_amount <= 0 or len(quote) <= 30:
        return None

    latest = klines[-1]
    quote_date = str(quote[30])[:8]
    kline_date = str(latest[0]).replace("-", "")
    if quote_date != kline_date:
        return None

    close = float(latest[2])
    raw_volume = float(latest[5])
    if close <= 0 or raw_volume <= 0:
        return None

    amount_scale = quote_amount / (close * raw_volume)
    if 0.2 <= amount_scale <= 5:
        return 1
    if 20 <= amount_scale <= 500:
        return 100
    return None

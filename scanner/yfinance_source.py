# scanner/yfinance_source.py
"""Yahoo Finance 日线数据源 — 获取 A 股 OHLC 并归一化为项目统一格式。"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ── 代码映射 ────────────────────────────────────────────────────────

def _to_yahoo_symbol(code: str) -> str | None:
    """将 A 股代码转换为 Yahoo Finance 符号。

    沪市主板/科创板 → .SS，深市主板/创业板 → .SZ。
    不支持北交所。
    """
    code = code.strip()
    if not code or len(code) < 6:
        return None
    prefix = code[:3]
    if prefix in ("600", "601", "603", "605", "688"):
        return f"{code}.SS"
    if prefix in ("000", "001", "002", "003", "300", "301"):
        return f"{code}.SZ"
    logger.debug("Unsupported A-share code for yfinance: %s", code)
    return None


# ── 公共接口 ─────────────────────────────────────────────────────────

def fetch_yfinance_daily(code: str, days: int = 250) -> list[dict] | None:
    """从 Yahoo Finance 获取 A 股日线数据并归一化。

    Args:
        code: 6 位 A 股代码。
        days: 需要保留的最近交易日数量。

    Returns:
        统一 OHLC 格式 list[dict]，失败或数据不足返回 None。
        限流异常向调用方抛出，不被吞掉。
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance not installed, skipping")
        return None

    symbol = _to_yahoo_symbol(code)
    if symbol is None:
        return None

    try:
        ticker = yf.Ticker(symbol)
        # 显式指定参数，禁止依赖库默认值
        history = ticker.history(
            period="max",
            auto_adjust=True,
            actions=False,
        )
    except Exception as exc:
        _raise_if_rate_limited(exc)
        logger.debug("yfinance fetch failed for %s: %s", code, exc)
        return None

    if history is None or history.empty:
        return None

    return _normalize_history(history, days)


# ── 数据归一化 ───────────────────────────────────────────────────────

def _normalize_history(history, days: int) -> list[dict] | None:
    """将 yfinance DataFrame 转换为项目统一 OHLC 格式。"""
    import math

    rows = []
    for idx, row in history.iterrows():
        normalized = _normalize_row(idx, row)
        if normalized is None:
            continue
        # 过滤无效价格
        if not _is_valid_ohlc(normalized):
            continue
        rows.append(normalized)

    if not rows:
        return None

    # 按日期升序，保留最近 days 条
    rows.sort(key=lambda r: r["date"])
    return rows[-days:]


def _normalize_row(index, row) -> dict | None:
    """将单行 DataFrame 行转换为项目 dict。"""
    # 检查所有必需字段存在
    required = ("Open", "High", "Low", "Close", "Volume")
    for key in required:
        if key not in row:
            return None

    try:
        date_str = str(index.date()) if hasattr(index, "date") else str(index)[:10]
        if not date_str or len(date_str) < 10:
            return None
        date_str = date_str[:10]
    except Exception:
        return None

    try:
        open_ = float(row["Open"])
        high = float(row["High"])
        low = float(row["Low"])
        close = float(row["Close"])
        volume = float(row["Volume"])
    except (ValueError, TypeError):
        return None

    return {
        "date": date_str,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "turnover": close * volume,
    }


def _is_valid_ohlc(row: dict) -> bool:
    """检查 OHLC 字段均为有限正数。"""
    import math

    for key in ("open", "high", "low", "close"):
        val = row.get(key)
        if val is None or not math.isfinite(val) or val <= 0:
            return False
    vol = row.get("volume")
    if vol is None or not math.isfinite(vol) or vol < 0:
        return False
    turnover = row.get("turnover")
    if turnover is None or not math.isfinite(turnover):
        return False
    return True


# ── 限流处理 ─────────────────────────────────────────────────────────

def _raise_if_rate_limited(exc: Exception) -> None:
    """如果异常包含限流信息，重新抛出供引擎层归类为 data source busy。"""
    text = str(exc).lower()
    if "429" in text or "too many requests" in text:
        raise ValueError("data source busy") from exc
    # yfinance 限流异常类型检查
    exc_type_name = type(exc).__name__.lower()
    if "rate" in exc_type_name or "limit" in exc_type_name:
        raise ValueError("data source busy") from exc

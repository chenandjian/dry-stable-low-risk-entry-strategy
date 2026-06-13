# strategy2/validation.py
"""策略2共享校验与辅助函数 — 配置解析、行情验证、最近N日涨跌序列。

校验分为两级（RECHECK-S2-004）：
  - validate_ohlc_structure: 只检查日期格式/排序/字段存在，用于完整输入。
  - validate_ohlc_values: 检查 OHLC 数值和关系，仅用于截取后的策略窗口。
"""
import logging
import math
from datetime import date, datetime
from typing import Any

logger = logging.getLogger(__name__)


# ── 配置校验 ────────────────────────────────────────────────────────────────

def resolve_strategy2_config(full_config: dict) -> dict:
    """严格解析并校验策略2配置。"""
    if not isinstance(full_config, dict):
        raise ValueError("strategy2 config must be a dict")

    if "strategy2" in full_config:
        s2 = full_config.get("strategy2", {})
        liquidity = full_config.get("liquidity", {})
    elif "liquidity" in full_config:
        s2 = full_config.get("strategy2", {})
        liquidity = full_config.get("liquidity", {})
    elif "strategy_window_days" in full_config:
        s2 = full_config
        liquidity = {}
    else:
        s2 = full_config
        liquidity = {}

    min_listing_days = liquidity.get("min_listing_days", 350) if isinstance(liquidity, dict) else 350

    def _strict_int(value: Any, key: str, min_val: int | None = None, max_val: int | None = None) -> int:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"strategy2.{key} must be an integer, got {type(value).__name__} ({value!r})")
        ival = int(value)
        if ival != value:
            raise ValueError(f"strategy2.{key} must be an integer, got {value!r}")
        if min_val is not None and ival < min_val:
            raise ValueError(f"strategy2.{key} ({ival}) must be >= {min_val}")
        if max_val is not None and ival > max_val:
            raise ValueError(f"strategy2.{key} ({ival}) must be <= {max_val}")
        return ival

    def _strict_float(value: Any, key: str, min_val: float | None = None, max_val: float | None = None) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"strategy2.{key} must be a number, got {type(value).__name__} ({value!r})")
        fval = float(value)
        if min_val is not None and fval <= min_val:
            raise ValueError(f"strategy2.{key} ({fval}) must be > {min_val}")
        if max_val is not None and fval > max_val:
            raise ValueError(f"strategy2.{key} ({fval}) must be <= {max_val}")
        return fval

    strategy_window_days = _strict_int(s2.get("strategy_window_days", 120), "strategy_window_days", min_val=60)
    minimum_required_days = _strict_int(s2.get("minimum_required_days", 60), "minimum_required_days", min_val=60)
    candidate_min_score = _strict_int(s2.get("candidate_min_score", 70), "candidate_min_score", min_val=0, max_val=100)
    minimum_volume_dry_score = _strict_int(s2.get("minimum_volume_dry_score", 0), "minimum_volume_dry_score", min_val=0, max_val=100)
    short_term_time_exit_days = _strict_int(s2.get("short_term_time_exit_days", 0), "short_term_time_exit_days", min_val=0, max_val=20)
    support_lookback_days = _strict_int(s2.get("support_lookback_days", 10), "support_lookback_days", min_val=2)

    max_risk_ratio = _strict_float(s2.get("max_risk_ratio", 0.05), "max_risk_ratio", min_val=0.0, max_val=1.0)
    buy_zone_max_premium = _strict_float(s2.get("buy_zone_max_premium", 0.03), "buy_zone_max_premium", min_val=0.0, max_val=0.20)
    stop_loss_buffer = _strict_float(s2.get("stop_loss_buffer", 0.03), "stop_loss_buffer", min_val=0.0, max_val=0.20)

    if strategy_window_days < minimum_required_days:
        raise ValueError(f"strategy2.strategy_window_days ({strategy_window_days}) must be >= strategy2.minimum_required_days ({minimum_required_days})")
    if strategy_window_days > min_listing_days:
        raise ValueError(f"strategy2.strategy_window_days ({strategy_window_days}) must be <= liquidity.min_listing_days ({min_listing_days})")
    if support_lookback_days >= strategy_window_days:
        raise ValueError(f"strategy2.support_lookback_days ({support_lookback_days}) must be < strategy2.strategy_window_days ({strategy_window_days})")

    return {
        "strategy_window_days": strategy_window_days,
        "minimum_required_days": minimum_required_days,
        "candidate_min_score": candidate_min_score,
        "minimum_volume_dry_score": minimum_volume_dry_score,
        "short_term_time_exit_days": short_term_time_exit_days,
        "max_risk_ratio": max_risk_ratio,
        "support_lookback_days": support_lookback_days,
        "buy_zone_max_premium": buy_zone_max_premium,
        "stop_loss_buffer": stop_loss_buffer,
    }


# ── 行情数据结构校验（完整输入用） ──────────────────────────────────────────

def validate_ohlc_structure(data: list[dict]) -> str | None:
    """校验日线数据结构：日期格式/排序/字段存在（RECHECK-S2-004 + 007）。

    仅检查确保可以安全截取尾部窗口所需的结构属性。
    不检查 OHLC 数值（由 validate_ohlc_values 在截取后检查）。

    Returns:
        None 表示结构有效，否则返回 "INVALID_MARKET_DATA"。
    """
    if not data or not isinstance(data, list):
        return "INVALID_MARKET_DATA"

    prev_date = None
    for row in data:
        if not isinstance(row, dict):
            return "INVALID_MARKET_DATA"

        # RECHECK-S2-004: 字段存在性不在结构检查中验证
        # （窗口外行的字段缺失不应阻断窗口内评估）
        # 字段检查在 validate_ohlc_values 中仅在截取后的窗口上执行

        # 日期格式与排序 (RECHECK-S2-007)
        date_str = row.get("date")
        if not isinstance(date_str, str) or not date_str:
            return "INVALID_MARKET_DATA"
        try:
            parsed = date.fromisoformat(date_str)
        except (ValueError, TypeError):
            return "INVALID_MARKET_DATA"
        if prev_date is not None:
            if parsed <= prev_date:
                return "INVALID_MARKET_DATA"
        prev_date = parsed

    return None


# ── 行情数据值校验（截取后窗口用） ──────────────────────────────────────────

def validate_ohlc_values(data: list[dict]) -> str | None:
    """校验 OHLC 数值和关系（RECHECK-S2-004）。

    在截取后的策略窗口上执行，确保窗口内数据有效。
    拒绝 NaN、Inf、零或负价格、bool 冒充数字、无效 OHLC 关系。

    Returns:
        None 表示数据有效，否则返回 "INVALID_MARKET_DATA"。
    """
    if not data:
        return "INVALID_MARKET_DATA"

    for row in data:
        # OHLC 数值校验
        for field in ("open", "high", "low", "close"):
            value = row.get(field)
            if isinstance(value, bool):
                return "INVALID_MARKET_DATA"
            if not isinstance(value, (int, float)):
                return "INVALID_MARKET_DATA"
            if math.isnan(value) or math.isinf(value):
                return "INVALID_MARKET_DATA"
            if value <= 0:
                return "INVALID_MARKET_DATA"

        # volume 校验
        volume = row.get("volume")
        if isinstance(volume, bool):
            return "INVALID_MARKET_DATA"
        if not isinstance(volume, (int, float)):
            return "INVALID_MARKET_DATA"
        if math.isnan(volume) or math.isinf(volume):
            return "INVALID_MARKET_DATA"
        if volume < 0:
            return "INVALID_MARKET_DATA"

        # OHLC 关系校验
        o, h, l, c = row["open"], row["high"], row["low"], row["close"]
        if h < max(o, c, l):
            return "INVALID_MARKET_DATA"
        if l > min(o, c, h):
            return "INVALID_MARKET_DATA"

    return None


# ── 兼容别名 ────────────────────────────────────────────────────────────────

def validate_ohlc_data(data: list[dict]) -> str | None:
    """完整校验（兼容旧接口）：先结构后值。"""
    err = validate_ohlc_structure(data)
    if err:
        return err
    return validate_ohlc_values(data)


# ── 最近 N 日涨跌序列（共享） ────────────────────────────────────────────────

def recent_daily_changes(data: list[dict], days: int = 5) -> list[dict]:
    """计算最近 N 个交易日各自相对于前一日的涨跌幅。"""
    if len(data) < days + 1:
        return []
    window = data[-(days + 1):]
    result = []
    for i in range(1, len(window)):
        prev_close = window[i - 1]["close"]
        curr_row = window[i]
        if prev_close > 0:
            change = curr_row["close"] / prev_close - 1
        else:
            change = 0.0
        result.append({"row": curr_row, "change": change})
    return result

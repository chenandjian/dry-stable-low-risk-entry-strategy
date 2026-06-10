# strategy2/validation.py
"""策略2共享校验与辅助函数 — 配置解析、行情验证、最近N日涨跌序列。

所有策略2模块应通过此模块的共享函数执行数据校验和窗口处理，
避免引擎、scanner、indicators 中各自实现边界逻辑。
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


# ── 配置校验 ────────────────────────────────────────────────────────────────

def resolve_strategy2_config(full_config: dict) -> dict:
    """严格解析并校验策略2配置。

    接受两种形式的输入：
    1. 完整 config.yaml（含 strategy2、liquidity 段）。
    2. 直接策略2配置字典（如从 engine 构造传入）。

    Args:
        full_config: 配置字典。

    Returns:
        规范化并校验后的策略2配置字典。

    Raises:
        ValueError: 配置参数非法。
    """
    if not isinstance(full_config, dict):
        raise ValueError("strategy2 config must be a dict")

    # 检测输入形式：有 strategy2 子段 → 完整配置；否则 → 直接配置
    if "strategy2" in full_config:
        s2 = full_config.get("strategy2", {})
        liquidity = full_config.get("liquidity", {})
    elif "liquidity" in full_config or "strategy_window_days" in full_config:
        # 可能是完整配置无 strategy2 段，或直接配置
        if "liquidity" in full_config:
            s2 = full_config.get("strategy2", {})
            liquidity = full_config.get("liquidity", {})
        else:
            # 直接策略2配置 — 用默认 liquidity
            s2 = full_config
            liquidity = {}
    else:
        s2 = full_config
        liquidity = {}

    min_listing_days = liquidity.get("min_listing_days", 350) if isinstance(liquidity, dict) else 350

    # 严格类型校验 — 拒绝 bool、字符串、浮点（整数参数）
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
    support_lookback_days = _strict_int(s2.get("support_lookback_days", 10), "support_lookback_days", min_val=2)

    max_risk_ratio = _strict_float(s2.get("max_risk_ratio", 0.05), "max_risk_ratio", min_val=0.0, max_val=1.0)
    buy_zone_max_premium = _strict_float(s2.get("buy_zone_max_premium", 0.03), "buy_zone_max_premium", min_val=0.0, max_val=0.20)
    stop_loss_buffer = _strict_float(s2.get("stop_loss_buffer", 0.03), "stop_loss_buffer", min_val=0.0, max_val=0.20)

    # 窗口关系校验
    if strategy_window_days < minimum_required_days:
        raise ValueError(
            f"strategy2.strategy_window_days ({strategy_window_days}) must be >= "
            f"strategy2.minimum_required_days ({minimum_required_days})"
        )
    if strategy_window_days > min_listing_days:
        raise ValueError(
            f"strategy2.strategy_window_days ({strategy_window_days}) must be <= "
            f"liquidity.min_listing_days ({min_listing_days})"
        )
    if support_lookback_days >= strategy_window_days:
        raise ValueError(
            f"strategy2.support_lookback_days ({support_lookback_days}) must be < "
            f"strategy2.strategy_window_days ({strategy_window_days})"
        )

    return {
        "strategy_window_days": strategy_window_days,
        "minimum_required_days": minimum_required_days,
        "candidate_min_score": candidate_min_score,
        "max_risk_ratio": max_risk_ratio,
        "support_lookback_days": support_lookback_days,
        "buy_zone_max_premium": buy_zone_max_premium,
        "stop_loss_buffer": stop_loss_buffer,
    }


# ── 行情数据校验 ────────────────────────────────────────────────────────────

def validate_ohlc_data(data: list[dict]) -> str | None:
    """完整校验日线数据格式和内容。

    校验内容:
    - 非空列表。
    - 每行必须包含 date/open/high/low/close/volume。
    - 日期严格升序、不重复、可比较。
    - OHLC 为有限正数，volume 为有限非负数。
    - high >= max(open, close, low), low <= min(open, close, high)。
    - 拒绝 bool 冒充数字。

    Returns:
        None 表示数据有效，否则返回稳定错误码字符串。
    """
    if not data or not isinstance(data, list):
        return "INVALID_MARKET_DATA"

    required_fields = ("date", "open", "high", "low", "close", "volume")
    prev_date = None

    for i, row in enumerate(data):
        if not isinstance(row, dict):
            return "INVALID_MARKET_DATA"

        # 必需字段存在
        for field in required_fields:
            if field not in row:
                return "INVALID_MARKET_DATA"

        # 日期校验
        date = row["date"]
        if not isinstance(date, str) or not date:
            return "INVALID_MARKET_DATA"
        if prev_date is not None:
            if date <= prev_date:
                return "INVALID_MARKET_DATA"
        prev_date = date

        # OHLC 校验
        for field in ("open", "high", "low", "close"):
            value = row[field]
            if isinstance(value, bool):
                return "INVALID_MARKET_DATA"
            if not isinstance(value, (int, float)):
                return "INVALID_MARKET_DATA"
            import math
            if math.isnan(value) or math.isinf(value):
                return "INVALID_MARKET_DATA"
            if value <= 0:
                return "INVALID_MARKET_DATA"

        # volume 校验（允许为 0，但后续 V20=0 由引擎排除）
        volume = row["volume"]
        if isinstance(volume, bool):
            return "INVALID_MARKET_DATA"
        if not isinstance(volume, (int, float)):
            return "INVALID_MARKET_DATA"
        import math
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


# ── 最近 N 日涨跌序列（共享） ────────────────────────────────────────────────

def recent_daily_changes(data: list[dict], days: int = 5) -> list[dict]:
    """计算最近 N 个交易日各自相对于前一日的涨跌幅。

    要计算最近 5 日的每日涨跌，需要 6 个收盘价（data[-(days+1):]）。
    返回 N 个元素的列表，每个元素为 {"row": row_dict, "change": float}。
    数据不足时返回空列表。
    """
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

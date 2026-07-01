"""A-share price-limit rule and limit-shape classification."""
from __future__ import annotations

from dataclasses import dataclass


PRICE_LIMIT_RULE_10CM = "PRICE_LIMIT_10CM"
PRICE_LIMIT_RULE_20CM = "PRICE_LIMIT_20CM"
PRICE_LIMIT_RULE_30CM = "PRICE_LIMIT_30CM"
PRICE_LIMIT_RULE_5CM_ST = "PRICE_LIMIT_5CM_ST"
PRICE_LIMIT_RULE_NO_LIMIT = "NO_PRICE_LIMIT_RULE"
PRICE_LIMIT_RULE_UNKNOWN = "UNKNOWN_PRICE_LIMIT_RULE"

LIMIT_SHAPE_LIMIT_UP_CLOSE = "LIMIT_UP_CLOSE"
LIMIT_SHAPE_NEAR_LIMIT_UP = "NEAR_LIMIT_UP"
LIMIT_SHAPE_ONE_WORD_LIMIT_UP = "ONE_WORD_LIMIT_UP"
LIMIT_SHAPE_T_LIMIT_UP = "T_LIMIT_UP"
LIMIT_SHAPE_BROKEN_LIMIT_UP = "BROKEN_LIMIT_UP"
LIMIT_SHAPE_NO_PRICE_LIMIT_DAY = "NO_PRICE_LIMIT_DAY"
LIMIT_SHAPE_NOT_LIMIT_UP = "NOT_LIMIT_UP"


@dataclass(frozen=True)
class PriceLimitInfo:
    code: str
    rule: str
    limit_pct: float | None
    reason: str = ""


class PriceLimitResolver:
    """Resolve daily price-limit rules without assuming all A-shares are 10cm."""

    def __init__(self, tolerance: float = 0.003):
        self.tolerance = tolerance

    def resolve(
        self,
        code: str,
        name: str = "",
        *,
        is_st: bool | None = None,
        no_price_limit: bool = False,
    ) -> PriceLimitInfo:
        normalized = (code or "").strip()
        upper_name = name.upper()
        st_flag = bool(is_st) if is_st is not None else ("ST" in upper_name)

        if no_price_limit:
            return PriceLimitInfo(normalized, PRICE_LIMIT_RULE_NO_LIMIT, None, "no_price_limit_phase")
        if st_flag:
            return PriceLimitInfo(normalized, PRICE_LIMIT_RULE_5CM_ST, 0.05, "st_stock")
        if normalized.startswith(("300", "301", "688")):
            return PriceLimitInfo(normalized, PRICE_LIMIT_RULE_20CM, 0.20, "20cm_board")
        if normalized.startswith(("8", "4")):
            return PriceLimitInfo(normalized, PRICE_LIMIT_RULE_30CM, 0.30, "bse_board")
        if normalized.startswith(("600", "601", "603", "605", "000", "001", "002", "003")):
            return PriceLimitInfo(normalized, PRICE_LIMIT_RULE_10CM, 0.10, "main_board")
        return PriceLimitInfo(normalized, PRICE_LIMIT_RULE_UNKNOWN, None, "unknown_code_prefix")

    def classify_shape(self, info: PriceLimitInfo, row: dict, *, prev_close: float) -> str:
        """Classify the evaluated bar's limit-up shape."""
        if info.rule == PRICE_LIMIT_RULE_NO_LIMIT:
            return LIMIT_SHAPE_NO_PRICE_LIMIT_DAY
        if info.limit_pct is None or prev_close <= 0:
            return LIMIT_SHAPE_NOT_LIMIT_UP

        open_ = float(row["open"])
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        limit_price = round(float(prev_close) * (1 + info.limit_pct), 2)
        near_price = limit_price * (1 - max(self.tolerance, 0.01))

        high_touched = high >= limit_price * (1 - self.tolerance)
        close_limit = close >= limit_price * (1 - self.tolerance)
        open_limit = open_ >= limit_price * (1 - self.tolerance)
        open_near_limit = open_ >= limit_price * 0.98
        low_limit = low >= limit_price * (1 - self.tolerance)

        if open_limit and high_touched and low_limit and close_limit:
            return LIMIT_SHAPE_ONE_WORD_LIMIT_UP
        if open_near_limit and high_touched and close_limit and not low_limit:
            return LIMIT_SHAPE_T_LIMIT_UP
        if close_limit:
            return LIMIT_SHAPE_LIMIT_UP_CLOSE
        if high_touched and not close_limit:
            return LIMIT_SHAPE_BROKEN_LIMIT_UP
        if close >= near_price or high >= near_price:
            return LIMIT_SHAPE_NEAR_LIMIT_UP
        return LIMIT_SHAPE_NOT_LIMIT_UP

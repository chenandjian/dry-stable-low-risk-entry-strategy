from __future__ import annotations

import re


_SYMBOL_RE = re.compile(r"^(\d{6})\.(SH|SZ|BJ)$", re.IGNORECASE)
_MARKET_ALIASES = {
    "SH": "SH",
    "SSE": "SH",
    "上海": "SH",
    "沪市": "SH",
    "SZ": "SZ",
    "SZSE": "SZ",
    "深圳": "SZ",
    "深市": "SZ",
    "BJ": "BJ",
    "BSE": "BJ",
    "北京": "BJ",
    "北交所": "BJ",
}


def _infer_market(code: str) -> str:
    if code.startswith("92"):
        return "BJ"
    if code.startswith(("5", "6", "9")):
        return "SH"
    if code.startswith(("0", "2", "3")):
        return "SZ"
    if code.startswith(("4", "8")):
        return "BJ"
    raise ValueError(f"cannot infer A-share market for code {code!r}")


def to_tickflow_symbol(code: str, market: str | None = None) -> str:
    normalized_code = str(code).strip()
    if not re.fullmatch(r"\d{6}", normalized_code):
        raise ValueError(f"invalid A-share code {code!r}")

    if market is None or not str(market).strip():
        normalized_market = _infer_market(normalized_code)
    else:
        market_key = str(market).strip().upper()
        normalized_market = _MARKET_ALIASES.get(market_key)
        if normalized_market is None:
            raise ValueError(f"unsupported A-share market {market!r}")

    inferred_market = _infer_market(normalized_code)
    if normalized_market != inferred_market:
        raise ValueError(
            f"stock code {normalized_code} does not belong to market {normalized_market}"
        )
    return f"{normalized_code}.{normalized_market}"


def from_tickflow_symbol(symbol: str) -> str:
    match = _SYMBOL_RE.fullmatch(str(symbol).strip())
    if match is None:
        raise ValueError(f"invalid TickFlow A-share symbol {symbol!r}")
    code, market = match.groups()
    if _infer_market(code) != market.upper():
        raise ValueError(f"symbol market does not match stock code: {symbol!r}")
    return code

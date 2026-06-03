# scanner/stock_pool.py
import logging
import json
import os

logger = logging.getLogger(__name__)

CACHE_FILE = "cache/stock_pool.json"


def get_a_stock_pool(config: dict) -> list[dict]:
    """获取 A 股股票池，过滤 ST/新股/北交所。

    Returns:
        list[dict]: [{code, name, market, listing_date}, ...]
    """
    # 1. 尝试 AKShare
    try:
        import akshare as ak
        df = ak.stock_info_a_code_name()
        stocks = []
        for _, row in df.iterrows():
            code = str(row["code"]).zfill(6)
            name = str(row["name"])
            stocks.append({"code": code, "name": name})
        logger.info(f"AKShare: got {len(stocks)} stocks")
        if stocks:
            _save_cache(stocks)
            return _filter_stocks(stocks, config)
    except Exception as e:
        logger.warning(f"AKShare stock pool failed: {e}")

    # 2. 回退本地缓存
    cached = _load_cache()
    if cached:
        logger.info(f"Using cached stock pool: {len(cached)} stocks")
        return _filter_stocks(cached, config)

    # 3. Last resort
    logger.error("Cannot get stock pool from any source")
    return []


def _filter_stocks(stocks: list[dict], config: dict) -> list[dict]:
    """过滤 ST/*ST/北交所/新股。"""
    market_cfg = config.get("market", {})
    result = []

    for s in stocks:
        code = s["code"]
        name = s["name"]

        # 排除 ST
        if market_cfg.get("exclude_st", True) and ("ST" in name or "*ST" in name):
            continue

        # 排除北交所（8 开头、4 开头）
        if market_cfg.get("exclude_bj", True) and (code.startswith("8") or code.startswith("4")):
            continue

        # 判断市场
        if code.startswith("688"):
            if not market_cfg.get("include_kcb", True):
                continue
            s["market"] = "科创板"
        elif code.startswith("300") or code.startswith("301"):
            if not market_cfg.get("include_cyb", True):
                continue
            s["market"] = "创业板"
        elif code.startswith("6"):
            if not market_cfg.get("include_sh", True):
                continue
            s["market"] = "上证主板"
        elif code.startswith("0") or code.startswith("002") or code.startswith("003"):
            if not market_cfg.get("include_sz", True):
                continue
            s["market"] = "深证主板"
        else:
            continue  # 不认识的代码，跳过

        result.append(s)

    logger.info(f"Stock pool after filter: {len(result)} (from {len(stocks)})")
    return result


def _save_cache(stocks: list[dict]):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(stocks, f, ensure_ascii=False)


def _load_cache() -> list[dict] | None:
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

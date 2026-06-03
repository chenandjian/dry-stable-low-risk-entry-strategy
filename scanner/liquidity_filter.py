# scanner/liquidity_filter.py
import logging

logger = logging.getLogger(__name__)


def passes_liquidity_filter(data: list[dict], config: dict) -> bool:
    """检查股票是否通过流动性过滤。

    Args:
        data: 日线数据列表，按日期升序
        config: liquidity 配置段

    Returns:
        True 如果通过或过滤已关闭
    """
    if not config.get("enabled", True):
        return True

    if not data or len(data) < config.get("avg_turnover_days", 20):
        return False

    n = config["avg_turnover_days"]
    recent = data[-n:]  # 最近 N 日
    latest = data[-1]

    # 1. 最近 N 日平均成交额
    turnovers = [d.get("turnover") or (d["volume"] * d["close"]) for d in recent]
    avg_turnover = _avg(turnovers)
    if avg_turnover < config.get("min_avg_turnover", 100_000_000):
        logger.debug(f"  liquidity fail: avg_turnover={avg_turnover:,.0f} < {config['min_avg_turnover']:,.0f}")
        return False

    # 2. 最近 N 日平均成交量
    volumes = [d["volume"] for d in recent]
    avg_volume = _avg(volumes)
    if avg_volume < config.get("min_avg_volume", 5_000_000):
        logger.debug(f"  liquidity fail: avg_volume={avg_volume:,.0f} < {config['min_avg_volume']:,.0f}")
        return False

    # 3. 最近 1 日成交额
    latest_turnover = latest.get("turnover") or (latest["volume"] * latest["close"])
    if latest_turnover < config.get("min_latest_turnover", 80_000_000):
        logger.debug(f"  liquidity fail: latest_turnover={latest_turnover:,.0f} < {config['min_latest_turnover']:,.0f}")
        return False

    return True


def _avg(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)

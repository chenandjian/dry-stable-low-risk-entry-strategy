"""Market environment filter for dry-stable strategy."""

from dataclasses import dataclass, field


@dataclass
class MarketEnvironmentResult:
    status: str = "一般"
    position_advice: str = "轻仓"
    score: int = 1
    reasons: list[str] = field(default_factory=list)


def assess_market_environment(index_data: list[dict] | None = None) -> MarketEnvironmentResult:
    """Assess broad market state from index OHLC data.

    Returns 良好 / 一般 / 较差. Missing index data defaults to 一般 so it
    reduces aggressiveness without blocking scans before index feeds exist.
    """
    result = MarketEnvironmentResult()
    if not index_data or len(index_data) < 50:
        result.reasons.append("未接入足够的大盘指数数据，默认按一般环境处理")
        return result

    closes = [d["close"] for d in index_data]
    volumes = [d.get("volume", 0) for d in index_data]
    latest = closes[-1]
    ma20 = _avg(closes[-20:])
    ma50 = _avg(closes[-50:])
    prev_ma50 = _avg(closes[-60:-10]) if len(closes) >= 60 else ma50
    vol20 = _avg(volumes[-20:])
    last3_down = all(closes[-i] < closes[-i - 1] for i in range(1, 4))
    last3_vol = _avg(volumes[-3:])

    if latest > ma20 and latest > ma50 and ma50 >= prev_ma50:
        result.status = "良好"
        result.position_advice = "正常"
        result.score = 2
        result.reasons.append("指数位于20日线和50日线上方，50日线未下行")
        if volumes[-1] >= vol20 * 1.1:
            result.reasons.append("指数上涨阶段量能较活跃")
        return result

    if latest < ma50 and (last3_down or (vol20 > 0 and last3_vol >= vol20 * 1.3)):
        result.status = "较差"
        result.position_advice = "暂不参与"
        result.score = 0
        result.reasons.append("指数跌破50日线且近期下跌或放量")
        return result

    result.status = "一般"
    result.position_advice = "轻仓"
    result.score = 1
    result.reasons.append("指数处于震荡或趋势确认不足状态")
    return result


def _avg(seq):
    return sum(seq) / len(seq) if seq else 0.0

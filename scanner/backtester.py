# scanner/backtester.py
"""Historical backtesting for Cup & Handle pattern detection.

Core approach:
  1. For each stock, load 500+ trading days of historical OHLC data
  2. Slide a detection window: at each index i from window_min to n - forward_days:
     - Use data[0:i] as the "known" data at time i
     - Run pattern detection on this window
     - If a pattern is found, record forward returns at 5/10/20/60 days
     - Track false breakouts (price falls below breakout_price within N days)
  3. Aggregate statistics across all stocks
"""

import logging
from dataclasses import dataclass, field
from scanner.pattern_detector import detect_cup_handle
from scanner.scorer import score_cup_handle

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Single pattern backtest result."""
    code: str = ""
    name: str = ""
    detect_date: str = ""         # 检测到形态的日期
    score: int = 0
    cup_depth_pct: float = 0.0
    cup_duration: int = 0
    handle_depth_pct: float = 0.0
    handle_duration: int = 0
    breakout_price: float = 0.0
    detect_close: float = 0.0     # 检测时收盘价

    # Forward returns (%)
    ret_5d: float | None = None
    ret_10d: float | None = None
    ret_20d: float | None = None
    ret_60d: float | None = None

    # Success flags
    hit_5d: bool = False     # ret > 0
    hit_10d: bool = False
    hit_20d: bool = False
    hit_60d: bool = False

    # False breakout: price drops below breakout_price within N days
    false_breakout_5d: bool = False
    false_breakout_10d: bool = False
    false_breakout_20d: bool = False
    false_breakout_60d: bool = False

    # Stop loss hit: price drops below (breakout_price * 0.95)
    stop_loss_hit_5d: bool = False
    stop_loss_hit_10d: bool = False
    stop_loss_hit_20d: bool = False
    stop_loss_hit_60d: bool = False


@dataclass
class BacktestReport:
    """Aggregated backtest statistics."""
    total_patterns: int = 0
    total_stocks_tested: int = 0
    stocks_with_patterns: int = 0

    # Hit rates (% of patterns that had positive return)
    hit_rate_5d: float = 0.0
    hit_rate_10d: float = 0.0
    hit_rate_20d: float = 0.0
    hit_rate_60d: float = 0.0

    # Average returns (%)
    avg_return_5d: float = 0.0
    avg_return_10d: float = 0.0
    avg_return_20d: float = 0.0
    avg_return_60d: float = 0.0

    # Median returns (%)
    median_return_5d: float = 0.0
    median_return_10d: float = 0.0
    median_return_20d: float = 0.0
    median_return_60d: float = 0.0

    # Max drawdown per pattern (worst return)
    worst_return_5d: float = 0.0
    worst_return_10d: float = 0.0
    worst_return_20d: float = 0.0

    # False breakout rate
    false_breakout_rate_5d: float = 0.0
    false_breakout_rate_10d: float = 0.0
    false_breakout_rate_20d: float = 0.0

    # Stop loss hit rate
    stop_loss_hit_rate_5d: float = 0.0
    stop_loss_hit_rate_10d: float = 0.0
    stop_loss_hit_rate_20d: float = 0.0

    # Score-stratified results
    by_score_range: list = field(default_factory=list)  # [{range, count, hit_rate_10d, avg_ret_10d}, ...]

    # Individual results
    results: list = field(default_factory=list)  # list of BacktestResult

    # Parameter suggestions
    parameter_suggestions: dict = field(default_factory=dict)


def run_backtest(
    stocks: list[dict],
    fetch_fn,
    config: dict,
    window_min: int = 250,
    min_score: int = 60,
    max_stocks: int | None = None,  # Limit for testing
) -> BacktestReport:
    """Run historical backtest across a stock universe.

    Args:
        stocks: list of {code, name} stock dicts
        fetch_fn: function(code) -> list[dict] OHLC data
        config: full config dict
        window_min: minimum data points before starting detection
        min_score: minimum pattern score to include
        max_stocks: limit number of stocks (for speed)

    Returns:
        BacktestReport with aggregated statistics
    """
    report = BacktestReport()

    # Build pattern config
    cup_cfg = config.get("cup", {})
    handle_cfg = config.get("handle", {})
    breakout_cfg = config.get("breakout", {})
    handle_prefixed = {f"handle_{k}": v for k, v in handle_cfg.items()}
    pattern_cfg = {**cup_cfg, **handle_prefixed, **breakout_cfg}

    all_results = []
    stocks_tested = 0
    stocks_with_patterns = 0

    stock_list = stocks[:max_stocks] if max_stocks else stocks

    for stock in stock_list:
        stocks_tested += 1
        code = stock["code"]
        name = stock.get("name", "")

        try:
            data = fetch_fn(code)
        except Exception:
            continue

        if not data or len(data) < window_min + 60:
            continue

        n = len(data)
        stock_has_pattern = False

        # Slide window: detect at each position from window_min to n-60
        for i in range(window_min, n - 60):
            window_data = data[:i]
            future_data = data[i:]

            # Detect pattern using only data available at time i
            result = detect_cup_handle(window_data, pattern_cfg)
            if not result.found:
                continue

            result.score = score_cup_handle(result)
            if result.score < min_score:
                continue

            stock_has_pattern = True

            br = BacktestResult(
                code=code,
                name=name,
                detect_date=window_data[-1]["date"],
                score=result.score,
                cup_depth_pct=result.cup_depth_pct,
                cup_duration=result.cup_duration,
                handle_depth_pct=result.handle_depth_pct,
                handle_duration=result.handle_duration,
                breakout_price=result.breakout_price,
                detect_close=window_data[-1]["close"],
            )

            # Calculate forward returns
            detect_close = window_data[-1]["close"]

            _calc_forward(br, detect_close, result.breakout_price, future_data)
            all_results.append(br)

        if stock_has_pattern:
            stocks_with_patterns += 1

        if stocks_tested % 100 == 0:
            logger.info(f"Backtest progress: {stocks_tested}/{len(stock_list)} stocks, "
                        f"{len(all_results)} patterns found")

    # Aggregate
    report.total_stocks_tested = stocks_tested
    report.stocks_with_patterns = stocks_with_patterns
    report.total_patterns = len(all_results)
    report.results = all_results

    if all_results:
        _aggregate(report, all_results)
        _score_stratify(report, all_results)
        _suggest_parameters(report, all_results)

    logger.info(f"Backtest complete: {stocks_tested} stocks, {len(all_results)} patterns")
    return report


def _calc_forward(br: BacktestResult, detect_close: float, breakout_price: float, future: list[dict]):
    """Calculate forward returns and false breakout flags."""
    horizons = {"5d": 5, "10d": 10, "20d": 20, "60d": 60}

    for label, days in horizons.items():
        if len(future) < days:
            continue

        future_close = future[days - 1]["close"]

        # Return
        ret = (future_close - detect_close) / detect_close * 100
        setattr(br, f"ret_{label}", round(ret, 2))
        setattr(br, f"hit_{label}", ret > 0)

        # False breakout: price dropped below breakout_price * 0.97
        # (within the 3% buffer, meaning the breakout failed)
        future_lows = [d["low"] for d in future[:days]]
        min_low = min(future_lows)
        setattr(br, f"false_breakout_{label}", min_low < breakout_price * 0.97)

        # Stop loss hit: 5% below breakout
        sl_price = breakout_price * 0.95
        setattr(br, f"stop_loss_hit_{label}", min_low < sl_price)


def _aggregate(report: BacktestReport, results: list[BacktestResult]):
    """Calculate aggregate statistics."""
    n = len(results)

    def _calc_metrics(prefix):
        rets = [getattr(r, f"ret_{prefix}", None) for r in results]
        rets = [v for v in rets if v is not None]
        hits = [getattr(r, f"hit_{prefix}", None) for r in results]
        hits = [v for v in hits if v is not None]
        fbs = [getattr(r, f"false_breakout_{prefix}", None) for r in results]
        fbs = [v for v in fbs if v is not None]
        sls = [getattr(r, f"stop_loss_hit_{prefix}", None) for r in results]
        sls = [v for v in sls if v is not None]

        if rets:
            setattr(report, f"avg_return_{prefix}", round(sum(rets) / len(rets), 2))
            sorted_rets = sorted(rets)
            setattr(report, f"median_return_{prefix}", round(sorted_rets[len(sorted_rets) // 2], 2))
            setattr(report, f"worst_return_{prefix}", round(min(rets), 2))
        if hits:
            setattr(report, f"hit_rate_{prefix}", round(sum(hits) / len(hits) * 100, 1))
        if fbs:
            setattr(report, f"false_breakout_rate_{prefix}", round(sum(fbs) / len(fbs) * 100, 1))
        if sls:
            setattr(report, f"stop_loss_hit_rate_{prefix}", round(sum(sls) / len(sls) * 100, 1))

    for h in ["5d", "10d", "20d", "60d"]:
        _calc_metrics(h)


def _score_stratify(report: BacktestReport, results: list[BacktestResult]):
    """Break down results by score range."""
    ranges = [(60, 69, "60-69"), (70, 79, "70-79"), (80, 89, "80-89"), (90, 100, "90-100")]
    for low, high, label in ranges:
        subset = [r for r in results if low <= r.score <= high]
        if not subset:
            continue
        rets_10 = [r.ret_10d for r in subset if r.ret_10d is not None]
        hits_10 = [r.hit_10d for r in subset if r.hit_10d is not None]
        report.by_score_range.append({
            "range": label,
            "count": len(subset),
            "hit_rate_10d": round(sum(hits_10) / len(hits_10) * 100, 1) if hits_10 else 0,
            "avg_return_10d": round(sum(rets_10) / len(rets_10), 2) if rets_10 else 0,
        })


def _suggest_parameters(report: BacktestReport, results: list[BacktestResult]):
    """Suggest optimal parameters based on backtest results."""
    suggestions = {}

    # Find best depth range
    depth_ranges = [(12, 25), (25, 33), (12, 33)]
    best_depth = None
    best_hit = 0
    for lo, hi in depth_ranges:
        subset = [r for r in results if lo <= r.cup_depth_pct <= hi]
        if subset:
            hits = [r.hit_10d for r in subset if r.hit_10d is not None]
            hit_rate = sum(hits) / len(hits) * 100 if hits else 0
            if hit_rate > best_hit:
                best_hit = hit_rate
                best_depth = (lo, hi, hit_rate)
    if best_depth:
        suggestions["optimal_cup_depth"] = f"{best_depth[0]}-{best_depth[1]}% (hit rate: {best_depth[2]:.1f}%)"

    # Find best score threshold
    for thresh in [60, 70, 80]:
        subset = [r for r in results if r.score >= thresh]
        if subset:
            hits = [r.hit_10d for r in subset if r.hit_10d is not None]
            hit_rate = sum(hits) / len(hits) * 100 if hits else 0
            suggestions[f"at_score_{thresh}"] = f"hit_rate_10d={hit_rate:.1f}%, count={len(subset)}"

    report.parameter_suggestions = suggestions


def backtest_report_to_dict(report: BacktestReport) -> dict:
    """Convert report to JSON-serializable dict."""
    return {
        "total_patterns": report.total_patterns,
        "total_stocks_tested": report.total_stocks_tested,
        "stocks_with_patterns": report.stocks_with_patterns,
        "hit_rates": {
            "5d": report.hit_rate_5d,
            "10d": report.hit_rate_10d,
            "20d": report.hit_rate_20d,
            "60d": report.hit_rate_60d,
        },
        "avg_returns": {
            "5d": report.avg_return_5d,
            "10d": report.avg_return_10d,
            "20d": report.avg_return_20d,
            "60d": report.avg_return_60d,
        },
        "median_returns": {
            "5d": report.median_return_5d,
            "10d": report.median_return_10d,
            "20d": report.median_return_20d,
            "60d": report.median_return_60d,
        },
        "false_breakout_rate": {
            "5d": report.false_breakout_rate_5d,
            "10d": report.false_breakout_rate_10d,
            "20d": report.false_breakout_rate_20d,
        },
        "stop_loss_hit_rate": {
            "5d": report.stop_loss_hit_rate_5d,
            "10d": report.stop_loss_hit_rate_10d,
            "20d": report.stop_loss_hit_rate_20d,
        },
        "by_score_range": report.by_score_range,
        "parameter_suggestions": report.parameter_suggestions,
    }

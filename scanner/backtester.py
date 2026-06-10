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
from scanner.strategy_engine import CupHandleStrategyEngine, select_strategy_window
from scanner.index_source import fetch_market_index_daily

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
    verdict: str = ""
    volume_dry_score: int = 0
    price_stable_score: int = 0
    pattern_score_20: int = 0
    risk_percent: float = 0.0
    rr1: float = 0.0

    # Forward returns (%)
    ret_5d: float | None = None
    ret_10d: float | None = None
    ret_20d: float | None = None
    ret_60d: float | None = None

    # Success flags: None = insufficient future data (not observed)
    hit_5d: bool | None = None
    hit_10d: bool | None = None
    hit_20d: bool | None = None
    hit_60d: bool | None = None

    # False breakout: None = insufficient future data / not applicable
    false_breakout_5d: bool | None = None
    false_breakout_10d: bool | None = None
    false_breakout_20d: bool | None = None
    false_breakout_60d: bool | None = None

    # Strategy actual stop-loss (from unified engine, not breakout_price * 0.95)
    actual_stop_loss: float = 0.0
    entry_zone_low: float = 0.0
    entry_zone_high: float = 0.0
    pattern_kind: str = ""

    # Stop loss hit: None = not computable (no valid stop), False = valid stop not hit, True = hit
    stop_loss_hit_5d: bool | None = None
    stop_loss_hit_10d: bool | None = None
    stop_loss_hit_20d: bool | None = None
    stop_loss_hit_60d: bool | None = None


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
    by_dry_stable_verdict: dict = field(default_factory=dict)

    # Individual results
    results: list = field(default_factory=list)  # list of BacktestResult

    # Parameter suggestions
    parameter_suggestions: dict = field(default_factory=dict)


def run_backtest(
    stocks: list[dict],
    fetch_fn,
    config: dict,
    window_min: int = None,
    min_score: int = None,
    max_stocks: int | None = None,  # Limit for testing
    market_data: list[dict] | None = None,  # Inject fixed market data (None = auto-fetch)
) -> BacktestReport:
    """Run historical backtest across a stock universe.

    Args:
        stocks: list of {code, name} stock dicts
        fetch_fn: function(code) -> list[dict] OHLC data
        config: full config dict
        window_min: [deprecated] use backtest_window_days from config instead
        min_score: [deprecated] only used for report display filtering
        max_stocks: limit number of stocks (for speed)
        market_data: optional pre-fetched market index data for reproducibility.
                     When None (default), fetches live via fetch_market_index_daily.

    Returns:
        BacktestReport with aggregated statistics
    """
    if window_min is not None:
        logger.warning("window_min 参数已废弃，使用 config.data.backtest_window_days 替代")
    if min_score is not None:
        logger.warning(
            "WARNING: --min-score 已废弃，仅用于回测报告展示过滤，"
            "不参与策略候选判断；下一版本将删除。"
        )

    report = BacktestReport()

    all_results = []
    stocks_tested = 0
    stocks_with_patterns = 0

    stock_list = stocks[:max_stocks] if max_stocks else stocks

    # Read backtest window config
    data_cfg = config.get("data", {})
    backtest_window_days = data_cfg.get("backtest_window_days") or 250
    min_forward_days = 60

    # Use the unified strategy engine (per plan-review: same config, same entry point)
    engine = CupHandleStrategyEngine(config)
    # Per-date market data: use injected data if provided, else fetch live
    if market_data is not None:
        market_data_full = market_data
    else:
        market_cfg = config.get("market_environment", {})
        market_data_full = fetch_market_index_daily(market_cfg.get("index_symbol")) or []

    for stock in stock_list:
        stocks_tested += 1
        code = stock["code"]
        name = stock.get("name", "")

        try:
            data = fetch_fn(code)
        except Exception:
            continue

        if not data or len(data) < backtest_window_days + min_forward_days:
            continue

        n = len(data)
        stock_has_pattern = False

        # Slide window: detect at each position from backtest_window_days to n-min_forward_days
        for i in range(backtest_window_days, n - min_forward_days):
            history_data = data[:i]
            future_data = data[i:]
            detect_date = history_data[-1]["date"]

            # Truncate to fixed backtest window
            window_data = select_strategy_window(history_data, backtest_window_days)
            if window_data is None:
                continue

            # Per-date market data (no future leakage)
            market_window = [r for r in market_data_full if r["date"] <= detect_date]

            # Unified strategy evaluation (handles cup_handle AND VCP)
            evaluation = engine.evaluate_at(
                window_data, code=code, name=name, market_data=market_window,
            )
            if not evaluation.passed:
                continue

            r = evaluation.result
            # Deprecated min_score: used only as report display filter
            if min_score is not None and r.score < min_score:
                continue
            dry = evaluation.dry_stable
            stock_has_pattern = True

            br = BacktestResult(
                code=code,
                name=name,
                detect_date=detect_date,
                score=r.score,
                cup_depth_pct=r.cup_depth_pct,
                cup_duration=r.cup_duration,
                handle_depth_pct=r.handle_depth_pct,
                handle_duration=r.handle_duration,
                breakout_price=r.breakout_price,
                detect_close=window_data[-1]["close"],
                verdict=dry["decision"]["verdict"],
                volume_dry_score=dry["volume_dry"]["score"],
                price_stable_score=dry["price_stable"]["score"],
                pattern_score_20=dry["pattern_score"]["score"],
                risk_percent=dry["risk_reward"]["risk_percent"],
                rr1=dry["risk_reward"]["rr1"],
                actual_stop_loss=dry["key_prices"]["stop_loss"],
                entry_zone_low=dry["key_prices"].get("entry_zone_low", 0),
                entry_zone_high=dry["key_prices"].get("entry_zone_high", 0),
                pattern_kind=getattr(r, "pattern_kind", "cup_handle"),
            )

            # Calculate forward returns
            detect_close = window_data[-1]["close"]

            _calc_forward(br, detect_close, r.breakout_price, future_data)
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
        report.by_dry_stable_verdict = summarize_by_verdict(all_results)
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

        # False breakout: only for cup_handle with valid breakout_price
        future_lows = [d["low"] for d in future[:days]]
        min_low = min(future_lows)
        if br.pattern_kind == "cup_handle" and breakout_price > 0:
            setattr(br, f"false_breakout_{label}", min_low < breakout_price * 0.97)
        else:
            setattr(br, f"false_breakout_{label}", None)

        # Stop loss hit: use strategy's actual stop_loss only
        if br.actual_stop_loss > 0:
            setattr(br, f"stop_loss_hit_{label}", min_low < br.actual_stop_loss)


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


def summarize_by_verdict(rows: list) -> dict:
    """Group backtest rows by dry-stable verdict.

    Returns per-verdict dict with:
      - count: total samples (including unobservable)
      - observed_10d_count: samples with valid 10-day forward data
      - avg_ret_10d: average of observed returns, or None if none observable
    """
    grouped = {}
    for row in rows:
        verdict = row.get("verdict", "未知") if isinstance(row, dict) else getattr(row, "verdict", "未知")
        ret_10d = row.get("ret_10d") if isinstance(row, dict) else getattr(row, "ret_10d", None)
        key = verdict or "未知"

        group = grouped.setdefault(
            key,
            {"count": 0, "observed_10d_count": 0, "returns": []},
        )
        group["count"] += 1
        if ret_10d is not None:
            group["observed_10d_count"] += 1
            group["returns"].append(ret_10d)

    return {
        k: {
            "count": v["count"],
            "observed_10d_count": v["observed_10d_count"],
            "avg_ret_10d": (
                round(sum(v["returns"]) / len(v["returns"]), 2)
                if v["returns"]
                else None
            ),
        }
        for k, v in grouped.items()
    }


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
        "by_dry_stable_verdict": report.by_dry_stable_verdict,
        "results": [_backtest_result_to_dict(r) for r in report.results],
        "parameter_suggestions": report.parameter_suggestions,
    }


def _backtest_result_to_dict(result: BacktestResult) -> dict:
    """Convert one result to a JSON-serializable dict."""
    return result.__dict__.copy()

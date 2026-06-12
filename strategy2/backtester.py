# strategy2/backtester.py
"""策略2本地数据库短线回测 — 核心计算模块。

禁止导入数据源模块、策略1判断模块。
只使用 db.get_ohlc() 读取本地日线数据。
"""
import json
import logging
import statistics
from strategy2.backtest_models import (
    HorizonPerformance,
    BacktestOpportunity,
    BacktestSignal,
    InsufficientStock,
    BacktestSummary,
)

logger = logging.getLogger(__name__)

HORIZONS = [3, 5, 10, 20]
TARGET_RETURN = 0.05  # +5%

# 计入冷却期的评估结果类型
_COOLING_COUNTED = {
    "LIQUIDITY_FILTERED", "DOWNTREND_FILTERED",
    "REJECTION_FAILED", "SCORE_BELOW_THRESHOLD", "RISK_RATIO_TOO_HIGH",
}
# 不计入冷却期（数据不足、数据异常、引擎异常）
_COOLING_NOT_COUNTED = {
    "INSUFFICIENT_DATA", "INVALID_DATA", "EVALUATION_ERROR",
}


# ═══════════════════════════════════════════════════════════════════════════════
# 纯计算函数（无 DB、无网络）
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_horizon_performance(
    future_data: list[dict],
    entry_close: float,
    stop_loss: float,
    horizon_days: int,
) -> HorizonPerformance:
    """计算一个机会在指定观察周期内的表现。

    Args:
        future_data: 入选日之后的 OHLC 数据（按日期升序，不含入选日）。
        entry_close: 入选日收盘价。
        stop_loss: 策略2止损价。
        horizon_days: 观察交易日数。

    Returns:
        HorizonPerformance with result (SUCCESS/FAILED/UNRESOLVED/UNOBSERVED).
    """
    target_price = entry_close * (1.0 + TARGET_RETURN)

    if not future_data or len(future_data) == 0:
        return HorizonPerformance(horizon_days=horizon_days, result="UNOBSERVED")

    # 截取观察周期
    observed = future_data[:horizon_days]
    if len(observed) < horizon_days:
        return HorizonPerformance(horizon_days=horizon_days, result="UNOBSERVED")

    max_upside = max(d["high"] for d in observed) / entry_close - 1.0
    max_drawdown = min(d["low"] for d in observed) / entry_close - 1.0
    end_return = observed[-1]["close"] / entry_close - 1.0

    target_hit_day = None
    stop_hit_day = None

    for day_idx, d in enumerate(observed):
        if d["high"] >= target_price and target_hit_day is None:
            target_hit_day = day_idx + 1  # 1-based
        if d["low"] <= stop_loss and stop_hit_day is None:
            stop_hit_day = day_idx + 1

    if target_hit_day is None and stop_hit_day is None:
        return HorizonPerformance(
            horizon_days=horizon_days,
            end_return=end_return,
            max_upside=max_upside,
            max_drawdown=max_drawdown,
            result="UNRESOLVED",
        )

    # 同日同时触发 → FAILED
    if target_hit_day is not None and stop_hit_day is not None:
        if stop_hit_day <= target_hit_day:
            return HorizonPerformance(
                horizon_days=horizon_days,
                end_return=end_return,
                max_upside=max_upside,
                max_drawdown=max_drawdown,
                result="FAILED",
                days_to_stop=stop_hit_day,
            )
        else:
            return HorizonPerformance(
                horizon_days=horizon_days,
                end_return=end_return,
                max_upside=max_upside,
                max_drawdown=max_drawdown,
                result="SUCCESS",
                days_to_target=target_hit_day,
            )

    if stop_hit_day is not None:
        return HorizonPerformance(
            horizon_days=horizon_days,
            end_return=end_return,
            max_upside=max_upside,
            max_drawdown=max_drawdown,
            result="FAILED",
            days_to_stop=stop_hit_day,
        )

    return HorizonPerformance(
        horizon_days=horizon_days,
        end_return=end_return,
        max_upside=max_upside,
        max_drawdown=max_drawdown,
        result="SUCCESS",
        days_to_target=target_hit_day,
    )


def merge_consecutive_signals(
    hits: list[BacktestSignal],
    eval_results: dict[int, str],
) -> list[BacktestOpportunity]:
    """使用完整评估日序列合并连续命中信号（10交易日冷却规则）。

    两个命中之间的"有效未命中日" = 中间已评估且计入冷却期的交易日数。
    冷却期计数使用 evaluation_index，不使用命中列表下标或自然日差。

    Args:
        hits: 原始命中信号列表（BacktestSignal，含 evaluation_index）。
        eval_results: {evaluation_index: result_type} 完整评估结果。

    Returns:
        去重后的 BacktestOpportunity 列表。
    """
    if not hits:
        return []

    # 按股票分组
    by_code: dict[str, list[BacktestSignal]] = {}
    for h in hits:
        by_code.setdefault(h.code, []).append(h)

    opportunities = []

    for code, stock_hits in by_code.items():
        stock_hits.sort(key=lambda s: s.evaluation_index)

        current_cluster = [stock_hits[0]]
        prev_idx = stock_hits[0].evaluation_index

        for i in range(1, len(stock_hits)):
            current_idx = stock_hits[i].evaluation_index
            # 计算两个命中之间计入冷却期的未命中交易日数
            missed = 0
            for idx in range(prev_idx + 1, current_idx):
                result = eval_results.get(idx, "")
                if result in _COOLING_COUNTED:
                    missed += 1

            if missed < 10:
                current_cluster.append(stock_hits[i])
            else:
                opportunities.append(_build_opportunity(current_cluster))
                current_cluster = [stock_hits[i]]

            prev_idx = current_idx

        opportunities.append(_build_opportunity(current_cluster))

    return opportunities


def _build_opportunity(cluster) -> BacktestOpportunity:
    """将一组连续命中构建为一次机会。接受 BacktestSignal 或旧格式 dict。"""
    first = cluster[0]
    last = cluster[-1]
    if isinstance(first, BacktestSignal):
        scores = [s.score for s in cluster]
        return BacktestOpportunity(
            code=first.code, name=first.name,
            first_detected_date=first.evaluation_date,
            last_detected_date=last.evaluation_date,
            consecutive_hit_days=len(cluster),
            first_score=scores[0], max_score=max(scores),
            level=first.level,
            entry_close=first.current_close,
            stop_loss=first.stop_loss, risk_ratio=first.risk_ratio,
            trend_type=first.trend_type,
            trend_evidence_score=first.trend_evidence_score,
            evaluation_snapshot=first.evaluation_snapshot,
            signal_count=len(cluster),
        )
    else:
        # 兼容旧格式 dict
        scores = [h["score"] for h in cluster]
        return BacktestOpportunity(
            code=first["code"], name=first.get("name", ""),
            first_detected_date=first["date"], last_detected_date=last["date"],
            consecutive_hit_days=len(cluster),
            first_score=scores[0], max_score=max(scores),
            level=first.get("level", ""),
            entry_close=first["close"],
            stop_loss=first.get("stop_loss", 0.0),
            risk_ratio=first.get("risk_ratio", 0.0),
            trend_type=first.get("trend_type", ""),
            trend_evidence_score=first.get("trend_evidence_score", 0),
            evaluation_snapshot=first.get("snapshot"),
        )


def aggregate_backtest_summary(
    opportunities: list[BacktestOpportunity],
    total_stocks: int = 0,
    total_eval_days: int = 0,
    liquidity_filtered: int = 0,
    trend_skipped: int = 0,
) -> BacktestSummary:
    """汇总回测统计数据。

    UNOBSERVED 不计入成功率和失败率。
    """
    codes_with_opps = set()
    complete_observed = 0
    unobserved = 0
    horizon_data: dict[int, dict] = {}

    for h in HORIZONS:
        horizon_data[h] = {
            "observed": 0, "unobserved": 0,
            "success": 0, "failed": 0, "unresolved": 0,
            "end_returns": [], "max_upsides": [], "max_drawdowns": [],
            "days_to_target_list": [], "days_to_stop_list": [],
        }

    for opp in opportunities:
        codes_with_opps.add(opp.code)
        for h in HORIZONS:
            hp = opp.horizons.get(str(h))
            if hp is None:
                continue
            if hp.result == "UNOBSERVED":
                horizon_data[h]["unobserved"] += 1
                unobserved += 1
            else:
                horizon_data[h]["observed"] += 1
                horizon_data[h]["end_returns"].append(hp.end_return)
                horizon_data[h]["max_upsides"].append(hp.max_upside)
                horizon_data[h]["max_drawdowns"].append(hp.max_drawdown)
                if hp.result == "SUCCESS":
                    horizon_data[h]["success"] += 1
                    if hp.days_to_target is not None:
                        horizon_data[h]["days_to_target_list"].append(hp.days_to_target)
                    if h == 3:  # count complete observed only once across all horizons
                        complete_observed += 1
                elif hp.result == "FAILED":
                    horizon_data[h]["failed"] += 1
                    if hp.days_to_stop is not None:
                        horizon_data[h]["days_to_stop_list"].append(hp.days_to_stop)
                    if h == 3:
                        complete_observed += 1
                elif hp.result == "UNRESOLVED":
                    horizon_data[h]["unresolved"] += 1
                    if h == 3:
                        complete_observed += 1

    # Build stats per horizon
    horizon_stats = {}
    for h in HORIZONS:
        d = horizon_data[h]
        obs = d["observed"]
        stats = {
            "horizon_days": h,
            "observed": obs,
            "unobserved": d["unobserved"],
            "success": d["success"],
            "failed": d["failed"],
            "unresolved": d["unresolved"],
            "success_rate": round(d["success"] / obs * 100, 2) if obs > 0 else 0.0,
            "failed_rate": round(d["failed"] / obs * 100, 2) if obs > 0 else 0.0,
            "avg_end_return": round(statistics.mean(d["end_returns"]), 6) if d["end_returns"] else 0.0,
            "median_end_return": round(statistics.median(d["end_returns"]), 6) if d["end_returns"] else 0.0,
            "avg_max_upside": round(statistics.mean(d["max_upsides"]), 6) if d["max_upsides"] else 0.0,
            "median_max_upside": round(statistics.median(d["max_upsides"]), 6) if d["max_upsides"] else 0.0,
            "avg_max_drawdown": round(statistics.mean(d["max_drawdowns"]), 6) if d["max_drawdowns"] else 0.0,
            "median_max_drawdown": round(statistics.median(d["max_drawdowns"]), 6) if d["max_drawdowns"] else 0.0,
            "avg_days_to_target": round(statistics.mean(d["days_to_target_list"]), 1) if d["days_to_target_list"] else None,
            "avg_days_to_stop": round(statistics.mean(d["days_to_stop_list"]), 1) if d["days_to_stop_list"] else None,
        }
        horizon_stats[str(h)] = stats

    avg_opp_per_day = len(opportunities) / total_eval_days if total_eval_days > 0 else 0.0

    return BacktestSummary(
        total_stocks=total_stocks,
        stocks_with_opportunities=len(codes_with_opps),
        total_opportunities=len(opportunities),
        avg_opportunities_per_eval_day=round(avg_opp_per_day, 4),
        complete_observed_count=complete_observed,
        unobserved_count=unobserved,
        horizon_stats=horizon_stats,
        total_eval_days=total_eval_days,
        liquidity_filtered_days=liquidity_filtered,
        trend_skipped_days=trend_skipped,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# NEXT_OPEN 执行模型（Phase 1 可信基线）
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_execution_outcome(
    opp: BacktestOpportunity,
    ohlc_data: list[dict],
    date_to_index: dict[str, int],
    buy_zone_high: float = float("inf"),
) -> BacktestOpportunity:
    """使用 NEXT_OPEN 执行模型计算实际入场和退出。"""
    opp.execution_model = "NEXT_OPEN"
    signal_date = opp.first_detected_date
    signal_idx = date_to_index.get(signal_date)
    if signal_idx is None or signal_idx + 1 >= len(ohlc_data):
        opp.exit_reason = "UNOBSERVED_ENTRY"
        return opp

    entry_day = ohlc_data[signal_idx + 1]
    entry_price = entry_day["open"]
    if entry_price <= opp.stop_loss:
        opp.exit_reason = "NO_ENTRY_GAP_BELOW_STOP"
        return opp
    if buy_zone_high != float("inf") and entry_price > buy_zone_high:
        opp.exit_reason = "NO_ENTRY_ABOVE_BUY_ZONE"
        return opp

    opp.entry_date = entry_day["date"]
    opp.entry_price = entry_price
    target_price = entry_price * (1.0 + TARGET_RETURN)
    stop_loss = opp.stop_loss

    future_from_entry = ohlc_data[signal_idx + 1:]
    opp.available_forward_days = len(future_from_entry)

    target_day = stop_day = None
    for i, d in enumerate(future_from_entry):
        if d["high"] >= target_price and target_day is None:
            target_day = i + 1
        if d["low"] <= stop_loss and stop_day is None:
            stop_day = i + 1

    if target_day and stop_day:
        if stop_day <= target_day:
            opp.exit_reason, opp.holding_days = "STOP", stop_day
        else:
            opp.exit_reason, opp.holding_days = "TARGET", target_day
    elif stop_day:
        opp.exit_reason, opp.holding_days = "STOP", stop_day
    elif target_day:
        opp.exit_reason, opp.holding_days = "TARGET", target_day
    else:
        opp.exit_reason = "UNRESOLVED"
        opp.holding_days = len(future_from_entry)

    if opp.exit_reason in ("TARGET", "STOP") and opp.entry_price > 0:
        opp.realized_return = (target_price if opp.exit_reason == "TARGET" else stop_loss) / opp.entry_price - 1.0

    if len(future_from_entry) > 0:
        opp.mark_to_market_end_return = future_from_entry[-1]["close"] / opp.entry_price - 1.0

    return opp


# ═══════════════════════════════════════════════════════════════════════════════
# 历史回放（读取本地 DB、禁止外部数据源）
# ═══════════════════════════════════════════════════════════════════════════════

def run_strategy2_stock_backtest(
    code: str,
    name: str,
    ohlc_data: list[dict],
    config_snapshot: dict,
    start_date: str,
    end_date: str,
) -> dict:
    """对单只股票执行历史逐日回放。

    使用本地 DB 日线数据，不请求外部数据源。

    Args:
        code: 股票代码。
        name: 股票名称。
        ohlc_data: 完整本地日线数据（按日期升序）。
        config_snapshot: 回测任务启动时的配置快照。
        start_date: 用户请求的开始日期。
        end_date: 用户请求的结束日期。

    Returns:
        {"hits": [...], "opportunities": [...], "eval_days": N,
         "liquidity_filtered": N, "trend_skipped": N, "insufficient": dict|None}
    """
    from strategy2.engine import ExtremeDryStableStrategyEngine
    from strategy2.scanner import _build_strategy2_discovery
    from scanner.liquidity_filter import passes_liquidity_filter

    strategy2_cfg = config_snapshot.get("strategy2", {})
    liquidity_cfg = config_snapshot.get("liquidity", {})
    min_required = strategy2_cfg.get("minimum_required_days", 250)
    max_window = strategy2_cfg.get("strategy_window_days", 350)

    engine = ExtremeDryStableStrategyEngine(config_snapshot)

    if not ohlc_data or len(ohlc_data) < min_required:
        return {
            "hits": [], "opportunities": [], "eval_days": 0,
            "liquidity_filtered": 0, "trend_skipped": 0,
            "insufficient": {
                "code": code, "name": name,
                "reason_code": "INSUFFICIENT_HISTORY_DATA",
                "available_days": len(ohlc_data) if ohlc_data else 0,
                "required_days": min_required,
                "earliest_date": ohlc_data[0]["date"] if ohlc_data else "",
                "latest_date": ohlc_data[-1]["date"] if ohlc_data else "",
            },
        }

    # 构建日期→索引映射（一次遍历）
    date_to_index = {d["date"]: i for i, d in enumerate(ohlc_data)}

    signals: list[BacktestSignal] = []
    eval_results: dict[int, str] = {}
    eval_days = 0
    liquidity_filtered = 0
    trend_skipped = 0

    for i in range(min_required, len(ohlc_data) + 1):
        eval_day = ohlc_data[i - 1]["date"]
        if eval_day < start_date or eval_day > end_date:
            continue

        evaluation_index = i - 1  # 判断日在 ohlc_data 中的位置
        eval_days += 1
        history = ohlc_data[:i]
        if len(history) > max_window:
            history = history[-max_window:]

        if not passes_liquidity_filter(history, liquidity_cfg):
            liquidity_filtered += 1
            eval_results[evaluation_index] = "LIQUIDITY_FILTERED"
            continue

        try:
            evaluation = engine.evaluate_at(history, code=code, name=name)
        except Exception as exc:
            eval_results[evaluation_index] = "EVALUATION_ERROR"
            continue

        if evaluation.passed:
            signal = BacktestSignal(
                code=code, name=name,
                evaluation_date=eval_day,
                evaluation_index=evaluation_index,
                score=evaluation.total_score,
                level=evaluation.level,
                current_close=evaluation.current_close,
                stop_loss=evaluation.risk.stop_loss if evaluation.risk else 0.0,
                risk_ratio=evaluation.risk.risk_ratio if evaluation.risk else 0.0,
                volume_dry_score=evaluation.volume_dry_score,
                price_stable_score=evaluation.price_stable_score,
                trend_type=evaluation.trend.trend_type if evaluation.trend else "",
                trend_evidence_score=evaluation.trend.total_evidence_score if evaluation.trend else 0,
                evaluation_snapshot=_build_strategy2_discovery(evaluation),
            )
            signals.append(signal)
            eval_results[evaluation_index] = "PASSED"
        elif evaluation.status_reason == "DOWNTREND_FILTERED":
            trend_skipped += 1
            eval_results[evaluation_index] = "DOWNTREND_FILTERED"
        elif evaluation.status_reason and "REJECT" in str(evaluation.status_reason):
            eval_results[evaluation_index] = "REJECTION_FAILED"
        elif evaluation.status_reason == "SCORE_BELOW_THRESHOLD":
            eval_results[evaluation_index] = "SCORE_BELOW_THRESHOLD"
        elif evaluation.status_reason == "RISK_RATIO_TOO_HIGH":
            eval_results[evaluation_index] = "RISK_RATIO_TOO_HIGH"
        elif evaluation.status_reason in ("INVALID_MARKET_DATA",):
            eval_results[evaluation_index] = "INVALID_DATA"
        elif evaluation.status_reason in ("INSUFFICIENT_STRATEGY_DATA", "INSUFFICIENT_TREND_DATA"):
            eval_results[evaluation_index] = "INSUFFICIENT_DATA"
        else:
            eval_results[evaluation_index] = "RISK_RATIO_TOO_HIGH"  # 其他非通过原因

    # 合并连续信号 + 执行模型 + 未来表现
    opportunities = merge_consecutive_signals(signals, eval_results)
    for opp in opportunities:
        buy_zone_high = float("inf")
        if opp.evaluation_snapshot:
            buy_zone_high = opp.evaluation_snapshot.get("buy_zone_high", float("inf"))
        calculate_execution_outcome(opp, ohlc_data, date_to_index, buy_zone_high)

        # 计算各周期 horizon（基于实际入场价）
        signal_idx = date_to_index.get(opp.first_detected_date)
        if signal_idx is not None:
            future = ohlc_data[signal_idx + 1:]
            for h in HORIZONS:
                entry_price = opp.entry_price if opp.entry_price > 0 else opp.entry_close
                opp.horizons[str(h)] = calculate_horizon_performance(
                    future, entry_price, opp.stop_loss, h,
                )

    return {
        "signals": signals,
        "opportunities": opps_to_dicts(opportunities),
        "eval_days": eval_days,
        "eval_results": eval_results,
        "liquidity_filtered": liquidity_filtered,
        "trend_skipped": trend_skipped,
        "insufficient": None,
    }


def opps_to_dicts(opportunities: list[BacktestOpportunity]) -> list[dict]:
    """将机会列表转换为 dict 列表，用于持久化和 API。"""
    result = []
    for o in opportunities:
        d = {
            "code": o.code, "name": o.name,
            "first_detected_date": o.first_detected_date,
            "last_detected_date": o.last_detected_date,
            "consecutive_hit_days": o.consecutive_hit_days,
            "first_score": o.first_score, "max_score": o.max_score,
            "level": o.level,
            "entry_close": o.entry_close,
            "stop_loss": o.stop_loss,
            "risk_ratio": o.risk_ratio,
            "trend_type": o.trend_type,
            "trend_evidence_score": o.trend_evidence_score,
            "signal_count": o.signal_count,
            "execution_model": o.execution_model,
            "entry_date": o.entry_date, "entry_price": o.entry_price,
            "exit_date": o.exit_date, "exit_price": o.exit_price,
            "exit_reason": o.exit_reason,
            "realized_return": o.realized_return,
            "mark_to_market_end_return": o.mark_to_market_end_return,
            "holding_days": o.holding_days,
            "available_forward_days": o.available_forward_days,
            "evaluation_snapshot": json.dumps(o.evaluation_snapshot) if o.evaluation_snapshot else "{}",
            "horizon_3": json.dumps(o.horizons.get("3", HorizonPerformance(horizon_days=3)).to_dict()) if "3" in o.horizons else "{}",
            "horizon_5": json.dumps(o.horizons.get("5", HorizonPerformance(horizon_days=5)).to_dict()) if "5" in o.horizons else "{}",
            "horizon_10": json.dumps(o.horizons.get("10", HorizonPerformance(horizon_days=10)).to_dict()) if "10" in o.horizons else "{}",
            "horizon_20": json.dumps(o.horizons.get("20", HorizonPerformance(horizon_days=20)).to_dict()) if "20" in o.horizons else "{}",
        }
        result.append(d)
    return result

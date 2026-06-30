"""策略3本地数据库回测核心计算。

本模块只做纯历史回放和执行模型计算，不拉取外部行情源。
"""
from __future__ import annotations

import json
from dataclasses import asdict
from statistics import mean, median

from scanner.liquidity_filter import passes_liquidity_filter
from strategy3.backtest_models import (
    Strategy3BacktestOpportunity,
    Strategy3BacktestSignal,
    Strategy3HorizonPerformance,
    Strategy3BacktestSummary,
)
from strategy3.engine import StrongPullbackSecondBreakoutEngine
from strategy3.market_index import resolve_strategy3_market_index

HORIZONS = [5, 10, 20]

_COOLING_COUNTED = {
    "LIQUIDITY_FILTERED",
    "TREND_REJECTED",
    "SETUP_REJECTED",
    "VOLUME_REJECTED",
    "SECOND_BREAKOUT_REJECTED",
    "RISK_REJECTED",
    "SCORE_BELOW_THRESHOLD",
    "TRADE_QUALITY_REJECTED",
}


def calculate_strategy3_execution_outcome(
    opp: Strategy3BacktestOpportunity,
    ohlc_data: list[dict],
    date_to_index: dict[str, int],
) -> Strategy3BacktestOpportunity:
    """使用 NEXT_OPEN 模型计算策略3机会入场与退出。"""
    opp.execution_model = "NEXT_OPEN"
    signal_idx = date_to_index.get(opp.first_detected_date)
    if signal_idx is None or signal_idx + 1 >= len(ohlc_data):
        opp.exit_reason = "UNOBSERVED_ENTRY"
        return opp

    entry_day = ohlc_data[signal_idx + 1]
    entry_price = float(entry_day["open"])
    if entry_price <= opp.stop_loss:
        opp.exit_reason = "NO_ENTRY_GAP_BELOW_STOP"
        return opp
    if opp.target_price > 0 and entry_price >= opp.target_price:
        opp.exit_reason = "NO_ENTRY_GAP_TOO_HIGH"
        return opp

    opp.entry_date = entry_day["date"]
    opp.entry_price = entry_price
    future_from_entry = ohlc_data[signal_idx + 1:]
    opp.available_forward_days = len(future_from_entry)

    stop_hit = None
    target_hit = None
    for i, row in enumerate(future_from_entry):
        holding_days = i + 1
        if stop_hit is None and float(row["low"]) <= opp.stop_loss:
            stop_hit = {
                "holding_days": holding_days,
                "date": row["date"],
                "price": opp.stop_loss,
            }
        if target_hit is None and opp.target_price > 0 and float(row["high"]) >= opp.target_price:
            target_hit = {
                "holding_days": holding_days,
                "date": row["date"],
                "price": opp.target_price,
            }

    if stop_hit and target_hit:
        selected = stop_hit if stop_hit["holding_days"] <= target_hit["holding_days"] else target_hit
        opp.exit_reason = "STOP" if selected is stop_hit else "TARGET"
    elif stop_hit:
        selected = stop_hit
        opp.exit_reason = "STOP"
    elif target_hit:
        selected = target_hit
        opp.exit_reason = "TARGET"
    else:
        selected = None
        opp.exit_reason = "UNRESOLVED"
        opp.holding_days = len(future_from_entry)

    if selected:
        opp.holding_days = selected["holding_days"]
        opp.exit_date = selected["date"]
        opp.exit_price = selected["price"]
        opp.realized_return = opp.exit_price / opp.entry_price - 1.0

    if future_from_entry:
        opp.mark_to_market_end_return = float(future_from_entry[-1]["close"]) / opp.entry_price - 1.0

    return opp


def calculate_strategy3_horizon_performance(
    future_data: list[dict],
    entry_price: float,
    stop_loss: float,
    target_price: float,
    horizon_days: int,
) -> Strategy3HorizonPerformance:
    """计算指定观察周期的收益、最大回撤和触发结果。"""
    if not future_data or entry_price <= 0 or len(future_data) < horizon_days:
        return Strategy3HorizonPerformance(horizon_days=horizon_days, result="UNOBSERVED")

    observed = future_data[:horizon_days]
    max_upside = max(float(row["high"]) for row in observed) / entry_price - 1.0
    max_drawdown = min(float(row["low"]) for row in observed) / entry_price - 1.0
    end_return = float(observed[-1]["close"]) / entry_price - 1.0
    stop_day = None
    target_day = None
    for i, row in enumerate(observed):
        day = i + 1
        if stop_day is None and float(row["low"]) <= stop_loss:
            stop_day = day
        if target_day is None and target_price > 0 and float(row["high"]) >= target_price:
            target_day = day
    if stop_day is not None and (target_day is None or stop_day <= target_day):
        result = "FAILED"
    elif target_day is not None:
        result = "SUCCESS"
    else:
        result = "UNRESOLVED"
    return Strategy3HorizonPerformance(
        horizon_days=horizon_days,
        end_return=end_return,
        max_upside=max_upside,
        max_drawdown=max_drawdown,
        result=result,
        days_to_target=target_day if result == "SUCCESS" else None,
        days_to_stop=stop_day if result == "FAILED" else None,
    )


def merge_strategy3_signals(
    hits: list[Strategy3BacktestSignal],
    eval_results: dict[int, str],
) -> list[Strategy3BacktestOpportunity]:
    """按 10 个有效未命中交易日规则合并策略3原始信号。"""
    if not hits:
        return []
    grouped: dict[str, list[Strategy3BacktestSignal]] = {}
    for signal in hits:
        grouped.setdefault(signal.code, []).append(signal)

    opportunities: list[Strategy3BacktestOpportunity] = []
    for signals in grouped.values():
        signals.sort(key=lambda item: item.evaluation_index)
        cluster = [signals[0]]
        prev_idx = signals[0].evaluation_index
        for signal in signals[1:]:
            missed = sum(
                1
                for idx in range(prev_idx + 1, signal.evaluation_index)
                if eval_results.get(idx) in _COOLING_COUNTED
            )
            if missed < 10:
                cluster.append(signal)
            else:
                opportunities.append(_build_opportunity(cluster))
                cluster = [signal]
            prev_idx = signal.evaluation_index
        opportunities.append(_build_opportunity(cluster))
    return opportunities


def run_strategy3_stock_backtest(
    code: str,
    name: str,
    ohlc_data: list[dict],
    config_snapshot: dict,
    start_date: str,
    end_date: str,
    *,
    engine_factory=None,
    market_data: list[dict] | None = None,
    market_data_by_symbol: dict[str, list[dict]] | None = None,
    market_data_mode: str = "",
) -> dict:
    """对单只股票执行策略3本地历史逐日回放。"""
    strategy_cfg = config_snapshot.get("strategy3", {})
    liquidity_cfg = config_snapshot.get("liquidity", {})
    min_required = int(strategy_cfg.get("minimum_required_days", 180))
    max_window = int(strategy_cfg.get("strategy_window_days", 250))
    if not ohlc_data or len(ohlc_data) < min_required:
        return {
            "signals": [],
            "opportunities": [],
            "eval_days": 0,
            "raw_signals_count": 0,
            "opportunities_count": 0,
            "insufficient": {
                "code": code,
                "name": name,
                "reason_code": "INSUFFICIENT_HISTORY_DATA",
                "available_days": len(ohlc_data) if ohlc_data else 0,
                "required_days": min_required,
                "earliest_date": ohlc_data[0]["date"] if ohlc_data else "",
                "latest_date": ohlc_data[-1]["date"] if ohlc_data else "",
            },
        }

    engine_cls = engine_factory or StrongPullbackSecondBreakoutEngine
    engine = engine_cls(config_snapshot)
    market_data_mode = market_data_mode or ("local_equal_weight_proxy" if market_data_by_symbol else "")
    market_selection = _resolve_backtest_market_selection(code, market_data_by_symbol)
    market_metadata = market_selection.to_metadata(market_data_mode)
    date_to_index = {row["date"]: i for i, row in enumerate(ohlc_data)}
    signals: list[Strategy3BacktestSignal] = []
    eval_results: dict[int, str] = {}
    eval_days = 0
    liquidity_filtered = 0
    evaluation_errors: list[dict] = []
    actual_eval_start = None
    actual_eval_end = None
    observation_data_end = None

    for i in range(min_required, len(ohlc_data) + 1):
        eval_day = ohlc_data[i - 1]["date"]
        if eval_day < start_date or eval_day > end_date:
            continue
        eval_days += 1
        actual_eval_start = actual_eval_start or eval_day
        actual_eval_end = eval_day
        if i < len(ohlc_data):
            observation_data_end = ohlc_data[-1]["date"]

        history = ohlc_data[:i]
        if len(history) > max_window:
            history = history[-max_window:]
        if not passes_liquidity_filter(history, liquidity_cfg):
            liquidity_filtered += 1
            eval_results[i - 1] = "LIQUIDITY_FILTERED"
            continue
        try:
            full_market_data = _market_data_for_selection(market_selection.symbol, market_data_by_symbol, market_data)
            market_window = _select_market_window(full_market_data, eval_day)
            current_market_metadata = dict(market_metadata)
            if not market_window:
                current_market_metadata["market_index_fallback"] = True
                current_market_metadata["market_index_fallback_reason"] = (
                    current_market_metadata.get("market_index_fallback_reason")
                    or "NO_MARKET_DATA_RELATIVE_STRENGTH_FALLBACK"
                )
            evaluation = engine.evaluate_at(
                history,
                code=code,
                name=name,
                market_data=market_window,
                market_metadata=current_market_metadata,
            )
        except Exception as exc:
            eval_results[i - 1] = "EVALUATION_ERROR"
            evaluation_errors.append({
                "code": code,
                "date": eval_day,
                "type": type(exc).__name__,
                "detail": str(exc)[:200],
            })
            continue

        if evaluation.passed:
            signal = _signal_from_evaluation(evaluation, i - 1)
            signals.append(signal)
            eval_results[i - 1] = "PASSED"
        else:
            eval_results[i - 1] = _classify_failed_evaluation(evaluation.status_reason, evaluation.reject_reasons)

    opportunities = merge_strategy3_signals(signals, eval_results)
    for opp in opportunities:
        calculate_strategy3_execution_outcome(opp, ohlc_data, date_to_index)
        if opp.entry_price > 0:
            entry_idx = date_to_index.get(opp.entry_date)
            if entry_idx is not None:
                future = ohlc_data[entry_idx:]
                for horizon in HORIZONS:
                    opp.horizons[str(horizon)] = calculate_strategy3_horizon_performance(
                        future,
                        opp.entry_price,
                        opp.stop_loss,
                        opp.target_price,
                        horizon,
                    )
        else:
            for horizon in HORIZONS:
                opp.horizons[str(horizon)] = Strategy3HorizonPerformance(
                    horizon_days=horizon,
                    result="UNOBSERVED",
                )

    return {
        "signals": signals,
        "opportunities": strategy3_opportunities_to_dicts(opportunities),
        "eval_days": eval_days,
        "eval_results": eval_results,
        "actual_eval_start_date": actual_eval_start,
        "actual_eval_end_date": actual_eval_end,
        "observation_data_end_date": observation_data_end,
        "liquidity_filtered_days": liquidity_filtered,
        "evaluation_error_days": len(evaluation_errors),
        "evaluation_errors": evaluation_errors,
        "raw_signals_count": len(signals),
        "opportunities_count": len(opportunities),
        "available_days": len(ohlc_data),
        "required_days": min_required,
        "earliest_date": ohlc_data[0]["date"] if ohlc_data else "",
        "latest_date": ohlc_data[-1]["date"] if ohlc_data else "",
        "insufficient": None,
    }


def _resolve_backtest_market_selection(code: str, market_data_by_symbol: dict[str, list[dict]] | None):
    available_symbols = None
    if market_data_by_symbol is not None:
        available_symbols = {
            symbol
            for symbol, rows in market_data_by_symbol.items()
            if rows
        }
    return resolve_strategy3_market_index(code, available_symbols=available_symbols)


def _market_data_for_selection(
    symbol: str,
    market_data_by_symbol: dict[str, list[dict]] | None,
    fallback_market_data: list[dict] | None,
) -> list[dict]:
    if market_data_by_symbol is not None:
        return market_data_by_symbol.get(symbol) or []
    return fallback_market_data or []


def aggregate_strategy3_backtest_summary(
    opportunities: list[dict | Strategy3BacktestOpportunity],
    *,
    total_stocks: int = 0,
    total_signals: int = 0,
    total_eval_days: int = 0,
) -> Strategy3BacktestSummary:
    """聚合策略3回测机会，包含基础结果和分组统计。"""
    normalized = [
        asdict(opp) if isinstance(opp, Strategy3BacktestOpportunity) else opp
        for opp in opportunities
    ]
    entered = [opp for opp in normalized if opp.get("entry_price", 0) > 0]
    stop_count = sum(1 for opp in normalized if opp.get("exit_reason") == "STOP")
    target_count = sum(1 for opp in normalized if opp.get("exit_reason") == "TARGET")
    unresolved_count = sum(1 for opp in normalized if opp.get("exit_reason") == "UNRESOLVED")
    return Strategy3BacktestSummary(
        total_stocks=total_stocks,
        stocks_with_opportunities=len({opp.get("code") for opp in normalized}),
        total_signals=total_signals,
        total_opportunities=len(normalized),
        entered_opportunities=len(entered),
        no_entry_count=len(normalized) - len(entered),
        stop_count=stop_count,
        target_count=target_count,
        unresolved_count=unresolved_count,
        total_eval_days=total_eval_days,
        group_stats=_build_group_stats(normalized),
    )


def strategy3_opportunities_to_dicts(opportunities: list[Strategy3BacktestOpportunity]) -> list[dict]:
    """将策略3机会转换为可持久化 dict。"""
    rows = []
    for opp in opportunities:
        row = asdict(opp)
        row["evaluation_snapshot"] = json.dumps(opp.evaluation_snapshot, ensure_ascii=False)
        row["horizon_5"] = json.dumps(opp.horizons.get("5", Strategy3HorizonPerformance(5)).to_dict())
        row["horizon_10"] = json.dumps(opp.horizons.get("10", Strategy3HorizonPerformance(10)).to_dict())
        row["horizon_20"] = json.dumps(opp.horizons.get("20", Strategy3HorizonPerformance(20)).to_dict())
        row.pop("horizons", None)
        rows.append(row)
    return rows


def _build_opportunity(cluster: list[Strategy3BacktestSignal]) -> Strategy3BacktestOpportunity:
    first = cluster[0]
    last = cluster[-1]
    scores = [signal.total_score for signal in cluster]
    return Strategy3BacktestOpportunity(
        code=first.code,
        name=first.name,
        first_detected_date=first.evaluation_date,
        last_detected_date=last.evaluation_date,
        consecutive_hit_days=len(cluster),
        first_score=scores[0],
        max_score=max(scores),
        level=first.level,
        trade_state=first.trade_state,
        trade_state_label=first.trade_state_label,
        trade_quality_score=first.trade_quality_score,
        entry_close=first.current_close,
        support_price=first.support_price,
        stop_loss=first.stop_loss,
        target_price=first.target_price,
        risk_ratio=first.risk_ratio,
        rr1=first.rr1,
        trend_score=first.trend_score,
        pullback_score=first.pullback_score,
        volume_stability_score=first.volume_stability_score,
        second_breakout_score=first.second_breakout_score,
        risk_reward_score=first.risk_reward_score,
        volume_dry_score=first.volume_dry_score,
        price_stability_score=first.price_stability_score,
        cannot_fall_score=first.cannot_fall_score,
        balance_powerless_score=first.balance_powerless_score,
        pullback_pct=first.pullback_pct,
        volume_ratio_5_20=first.volume_ratio_5_20,
        evaluation_snapshot=first.evaluation_snapshot,
        signal_ids=[signal.evaluation_index for signal in cluster],
        signal_count=len(cluster),
    )


def _signal_from_evaluation(evaluation, evaluation_index: int) -> Strategy3BacktestSignal:
    risk = evaluation.risk
    quality = evaluation.trade_quality
    ind = evaluation.indicators
    snapshot = {
        "code": evaluation.code,
        "name": evaluation.name,
        "evaluation_date": evaluation.evaluation_date,
        "total_score": evaluation.total_score,
        "level": evaluation.level,
        "trend_score": evaluation.trend_score,
        "pullback_score": evaluation.pullback_score,
        "volume_stability_score": evaluation.volume_stability_score,
        "second_breakout_score": evaluation.second_breakout_score,
        "risk_reward_score": evaluation.risk_reward_score,
        "trade_state": quality.trade_state,
        "trade_state_label": quality.trade_state_label,
        "trade_quality_score": quality.trade_quality_score,
        "support_price": risk.support_price,
        "stop_loss": risk.stop_loss,
        "target_price": quality.target_price or risk.target_1,
        "risk_ratio": risk.risk_ratio,
        "rr1": risk.rr1,
        "market_index_symbol": ind.market_index_symbol,
        "market_index_name": ind.market_index_name,
        "market_return_20": ind.market_return_20,
        "market_return_60": ind.market_return_60,
        "market_above_ma20": ind.market_above_ma20,
        "market_above_ma60": ind.market_above_ma60,
        "market_volatility_20": ind.market_volatility_20,
        "market_drawdown_60": ind.market_drawdown_60,
        "market_data_mode": ind.market_data_mode,
        "market_index_fallback": ind.market_index_fallback,
        "market_index_fallback_reason": ind.market_index_fallback_reason,
        "has_market_data": ind.has_market_data,
        "score_reasons": evaluation.score_reasons,
        "reject_reasons": evaluation.reject_reasons,
        "trigger_reasons": quality.trigger_reasons,
        "risk_warnings": quality.risk_warnings,
        "invalid_conditions": quality.invalid_conditions,
    }
    return Strategy3BacktestSignal(
        code=evaluation.code,
        name=evaluation.name,
        evaluation_date=evaluation.evaluation_date,
        evaluation_index=evaluation_index,
        total_score=evaluation.total_score,
        level=evaluation.level,
        current_close=evaluation.current_close,
        trend_score=evaluation.trend_score,
        pullback_score=evaluation.pullback_score,
        volume_stability_score=evaluation.volume_stability_score,
        second_breakout_score=evaluation.second_breakout_score,
        risk_reward_score=evaluation.risk_reward_score,
        trade_state=quality.trade_state,
        trade_state_label=quality.trade_state_label,
        trade_quality_score=quality.trade_quality_score,
        volume_dry_score=quality.volume_dry_score,
        price_stability_score=quality.price_stability_score,
        cannot_fall_score=quality.cannot_fall_score,
        balance_powerless_score=quality.balance_powerless_score,
        support_price=risk.support_price,
        stop_loss=risk.stop_loss,
        target_price=quality.target_price or risk.target_1,
        risk_ratio=risk.risk_ratio,
        rr1=risk.rr1,
        pullback_pct=ind.pullback_pct,
        volume_ratio_5_20=ind.volume_ratio_5_20,
        evaluation_snapshot=snapshot,
    )


def _classify_failed_evaluation(status_reason: str | None, reject_reasons: list[str]) -> str:
    if status_reason in {"INSUFFICIENT_STRATEGY_DATA", "INVALID_MARKET_DATA"}:
        return "INSUFFICIENT_DATA"
    reasons = set(reject_reasons or [])
    if reasons & {
        "BELOW_MA60_AND_WEAK_TREND",
        "DEEP_DRAWDOWN_FROM_HIGH",
        "RELATIVE_STRENGTH_WEAK",
        "MA60_SLOPE_WEAK",
        "TRADE_MARKET_REGIME_NOT_FAVORABLE",
    }:
        return "TREND_REJECTED"
    if reasons & {
        "PULLBACK_TOO_SHALLOW", "PULLBACK_TOO_DEEP", "RECENT_RANGE_TOO_WIDE",
        "MA60_BREAKDOWN", "TRADE_PULLBACK_ABOVE_DATA_FILTER",
    }:
        return "SETUP_REJECTED"
    if reasons & {"VOLUME_NOT_STABLE", "CLOSE_RANGE_TOO_WIDE", "SHRINKING_BEAR_DRIFT", "DRY_HEAVY_DOWNSIDE_VOLUME"}:
        return "VOLUME_REJECTED"
    if reasons & {"MA5_NOT_RECOVERED", "RECENT_OVERHEATED", "CHASE_NEAR_HIGH"}:
        return "SECOND_BREAKOUT_REJECTED"
    if reasons & {
        "RISK_RATIO_TOO_HIGH", "RR_TOO_LOW", "KEY_SUPPORT_FAILED",
        "KEY_SUPPORT_BROKEN", "TRADE_RISK_ABOVE_DATA_FILTER",
    }:
        return "RISK_REJECTED"
    if reasons & {
        "PRICE_NOT_STABLE", "CONTINUOUS_NEW_LOW", "BEAR_BODY_EXPANDING",
        "TARGET_ROOM_TOO_SMALL", "TRADE_SCORE_BELOW_DATA_FILTER",
        "WAIT_BREAKOUT_NOT_ACTIONABLE",
    }:
        return "TRADE_QUALITY_REJECTED"
    if status_reason:
        return status_reason
    return "SCORE_BELOW_THRESHOLD"


def _build_group_stats(opportunities: list[dict]) -> dict:
    return {
        "by_score": _group_by(opportunities, lambda opp: _score_bucket(opp.get("max_score", 0))),
        "by_trade_state": _group_by(opportunities, lambda opp: opp.get("trade_state") or "UNKNOWN"),
        "by_risk_ratio": _group_by(opportunities, lambda opp: _risk_bucket(opp.get("risk_ratio", 0))),
        "by_rr1": _group_by(opportunities, lambda opp: _rr_bucket(opp.get("rr1", 0))),
        "by_pullback": _group_by(opportunities, lambda opp: _pullback_bucket(opp.get("pullback_pct", 0))),
        "by_month": _group_by(opportunities, lambda opp: (opp.get("first_detected_date") or "")[:7] or "UNKNOWN"),
    }


def _group_by(opportunities: list[dict], key_fn) -> dict:
    groups: dict[str, list[dict]] = {}
    for opp in opportunities:
        groups.setdefault(key_fn(opp), []).append(opp)
    result = {}
    for key, rows in groups.items():
        returns = [float(row.get("realized_return") or 0) for row in rows if row.get("entry_price", 0) > 0]
        result[key] = {
            "count": len(rows),
            "entered": sum(1 for row in rows if row.get("entry_price", 0) > 0),
            "target": sum(1 for row in rows if row.get("exit_reason") == "TARGET"),
            "stop": sum(1 for row in rows if row.get("exit_reason") == "STOP"),
            "avg_return": round(mean(returns), 6) if returns else 0.0,
            "median_return": round(median(returns), 6) if returns else 0.0,
        }
    return result


def _score_bucket(score: int) -> str:
    if score >= 90:
        return "90+"
    if score >= 85:
        return "85-89"
    if score >= 80:
        return "80-84"
    if score >= 75:
        return "75-79"
    return "<75"


def _risk_bucket(risk_ratio: float) -> str:
    if risk_ratio <= 0.04:
        return "<=4%"
    if risk_ratio <= 0.06:
        return "4-6%"
    if risk_ratio <= 0.08:
        return "6-8%"
    return ">8%"


def _rr_bucket(rr1: float) -> str:
    if rr1 < 1.5:
        return "<1.5"
    if rr1 < 2.0:
        return "1.5-2"
    if rr1 < 3.0:
        return "2-3"
    return ">=3"


def _pullback_bucket(pullback_pct: float) -> str:
    if pullback_pct < 0.10:
        return "<10%"
    if pullback_pct < 0.15:
        return "10-15%"
    if pullback_pct <= 0.22:
        return "15-22%"
    if pullback_pct <= 0.30:
        return "22-30%"
    return ">30%"


def _select_market_window(market_data: list[dict] | None, decision_date: str) -> list[dict]:
    if not market_data or not decision_date:
        return []
    return [row for row in market_data if str(row.get("date", "")) <= decision_date]

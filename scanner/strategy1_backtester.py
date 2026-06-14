"""Strategy1 trusted backtest replay helpers.

This module keeps strategy judgement delegated to
CupHandleStrategyEngine.evaluate_at(). It only prepares historical windows,
persists traceable signal objects in memory, and calculates future outcomes.
"""

from __future__ import annotations

from collections.abc import Mapping

from scanner.strategy1_backtest_experiments import (
    apply_signal_experiment_filter,
    normalize_experiment_config,
)
from scanner.strategy1_backtest_models import (
    Strategy1BacktestOpportunity,
    Strategy1BacktestSignal,
    Strategy1HorizonPerformance,
)
from scanner.strategy_engine import (
    CupHandleStrategyEngine,
    resolve_strategy_windows,
    select_market_window,
    select_strategy_window,
)


COUNTED_MISS_REASONS = {
    "LIQUIDITY",
    "SCORE_BELOW_THRESHOLD",
    "CANDIDATE_RULE_FAILED",
    "EXPERIMENT_FILTERED",
    "PATTERN_NOT_FOUND",
    "DECISION_REJECTED",
}


def calculate_horizon_performance(
    future_rows: list[dict],
    *,
    entry_price: float,
    stop_loss: float,
    horizon_days: int,
    target_return: float = 0.05,
) -> Strategy1HorizonPerformance:
    """Calculate short-horizon performance from actual entry price."""
    hp = Strategy1HorizonPerformance(horizon_days=horizon_days)
    if entry_price <= 0 or len(future_rows) < horizon_days:
        return hp

    rows = future_rows[:horizon_days]
    end_close = float(rows[-1].get("close") or 0)
    highs = [float(row.get("high") or 0) for row in rows]
    lows = [float(row.get("low") or 0) for row in rows]
    hp.end_return = round(end_close / entry_price - 1, 6) if end_close > 0 else None
    hp.max_upside = round(max(highs) / entry_price - 1, 6) if highs else None
    hp.max_drawdown = round(min(lows) / entry_price - 1, 6) if lows else None

    target_price = entry_price * (1 + target_return)
    for offset, row in enumerate(rows, start=1):
        high = float(row.get("high") or 0)
        low = float(row.get("low") or 0)
        stop_hit = stop_loss > 0 and low <= stop_loss
        target_hit = high >= target_price
        if stop_hit and target_hit:
            hp.result = "STOP"
            hp.days_to_stop = offset
            return hp
        if stop_hit:
            hp.result = "STOP"
            hp.days_to_stop = offset
            return hp
        if target_hit:
            hp.result = "TARGET"
            hp.days_to_target = offset
            return hp

    hp.result = "UNRESOLVED"
    return hp


def calculate_strategy1_execution_outcome(
    opportunity: Strategy1BacktestOpportunity,
    ohlc_rows: list[dict],
    date_to_index: dict[str, int],
    *,
    horizons: tuple[int, ...] = (3, 5, 10, 20),
) -> Strategy1BacktestOpportunity:
    """Apply the default NEXT_OPEN execution model to an opportunity."""
    signal_idx = date_to_index.get(opportunity.first_detected_date)
    if signal_idx is None:
        opportunity.exit_reason = "UNOBSERVED_ENTRY"
        return opportunity

    entry_idx = signal_idx + 1
    if entry_idx >= len(ohlc_rows):
        opportunity.exit_reason = "UNOBSERVED_ENTRY"
        opportunity.available_forward_days = 0
        return opportunity

    entry_row = ohlc_rows[entry_idx]
    entry_open = float(entry_row.get("open") or 0)
    if opportunity.stop_loss > 0 and entry_open <= opportunity.stop_loss:
        opportunity.exit_reason = "NO_ENTRY_GAP_BELOW_STOP"
        opportunity.entry_date = ""
        opportunity.entry_price = 0.0
        opportunity.available_forward_days = len(ohlc_rows) - entry_idx
        return opportunity

    opportunity.entry_date = str(entry_row.get("date") or "")
    opportunity.entry_price = entry_open
    future_rows = ohlc_rows[entry_idx:]
    opportunity.available_forward_days = len(future_rows)
    opportunity.horizons = {
        str(horizon): calculate_horizon_performance(
            future_rows,
            entry_price=entry_open,
            stop_loss=opportunity.stop_loss,
            horizon_days=horizon,
        )
        for horizon in horizons
    }

    resolved = [
        hp for hp in opportunity.horizons.values()
        if hp.result in {"TARGET", "STOP"} and (hp.days_to_target or hp.days_to_stop)
    ]
    if resolved:
        first = min(resolved, key=lambda hp: hp.days_to_target or hp.days_to_stop or 9999)
        days = first.days_to_target or first.days_to_stop or 1
        exit_idx = min(entry_idx + days - 1, len(ohlc_rows) - 1)
        exit_row = ohlc_rows[exit_idx]
        opportunity.exit_reason = first.result
        opportunity.exit_date = str(exit_row.get("date") or "")
        opportunity.exit_price = (
            entry_open * 1.05 if first.result == "TARGET" else opportunity.stop_loss
        )
        opportunity.holding_days = days
    else:
        last_row = future_rows[-1]
        opportunity.exit_reason = "UNRESOLVED"
        opportunity.exit_date = str(last_row.get("date") or "")
        opportunity.exit_price = float(last_row.get("close") or 0)
        opportunity.holding_days = len(future_rows)

    if opportunity.entry_price > 0 and opportunity.exit_price > 0:
        opportunity.realized_return = round(opportunity.exit_price / opportunity.entry_price - 1, 6)
    return opportunity


def apply_strategy1_time_exit(
    opportunity: Strategy1BacktestOpportunity,
    ohlc_rows: list[dict],
    date_to_index: dict[str, int],
    experiment: Mapping | None,
) -> bool:
    """Apply optional time exit without overriding earlier target/stop exits."""
    time_exit_days = (experiment or {}).get("time_exit_days")
    if not time_exit_days or not opportunity.entry_date:
        return False

    entry_idx = date_to_index.get(opportunity.entry_date)
    if entry_idx is None:
        return False
    exit_idx = entry_idx + int(time_exit_days) - 1
    if exit_idx >= len(ohlc_rows):
        return False
    if opportunity.holding_days and opportunity.holding_days <= int(time_exit_days):
        return False

    exit_row = ohlc_rows[exit_idx]
    opportunity.exit_reason = "TIME_EXIT"
    opportunity.exit_date = str(exit_row.get("date") or "")
    opportunity.exit_price = float(exit_row.get("close") or 0)
    opportunity.holding_days = int(time_exit_days)
    if opportunity.entry_price > 0 and opportunity.exit_price > 0:
        opportunity.realized_return = round(opportunity.exit_price / opportunity.entry_price - 1, 6)
    return True


def merge_strategy1_signals(
    signals: list[Strategy1BacktestSignal],
    eval_results: Mapping[int, str] | None = None,
    *,
    split_after_counted_misses: int = 10,
) -> list[Strategy1BacktestOpportunity]:
    """Merge consecutive hits until 10 counted non-hit trading days split them."""
    if not signals:
        return []

    eval_results = eval_results or {}
    sorted_signals = sorted(signals, key=lambda s: (s.code, s.evaluation_index, s.evaluation_date))
    opportunities: list[Strategy1BacktestOpportunity] = []
    current: Strategy1BacktestOpportunity | None = None
    last_signal: Strategy1BacktestSignal | None = None

    for signal in sorted_signals:
        should_split = current is None or (last_signal is not None and signal.code != last_signal.code)
        if current is not None and last_signal is not None and not should_split:
            counted = sum(
                1
                for idx in range(last_signal.evaluation_index + 1, signal.evaluation_index)
                if eval_results.get(idx) in COUNTED_MISS_REASONS
            )
            should_split = counted >= split_after_counted_misses

        if should_split:
            current = _opportunity_from_signal(signal)
            opportunities.append(current)
        else:
            _extend_opportunity(current, signal)
        last_signal = signal

    return opportunities


def run_strategy1_stock_backtest(
    code: str,
    name: str,
    ohlc_rows: list[dict],
    config: dict,
    start_date: str,
    end_date: str,
    *,
    experiment: Mapping | None = None,
    market_data: list[dict] | None = None,
) -> dict:
    """Replay one stock with local OHLC rows and the unified Strategy1 engine."""
    normalized_experiment = normalize_experiment_config(experiment)
    windows = resolve_strategy_windows(config)
    engine = CupHandleStrategyEngine(config)
    date_to_index = {str(row.get("date") or ""): idx for idx, row in enumerate(ohlc_rows)}
    signals: list[Strategy1BacktestSignal] = []
    eval_results: dict[int, str] = {}

    for idx, row in enumerate(ohlc_rows):
        evaluation_date = str(row.get("date") or "")
        if evaluation_date < start_date or evaluation_date > end_date:
            continue
        if idx + 1 < windows.backtest_window_days:
            eval_results[idx] = "INSUFFICIENT_BACKTEST_WINDOW"
            continue

        known_rows = ohlc_rows[: idx + 1]
        strategy_rows = select_strategy_window(known_rows, windows.backtest_window_days)
        decision_date = str(strategy_rows[-1].get("date") or "")
        market_window = select_market_window(market_data or [], decision_date)
        evaluation = engine.evaluate_at(
            strategy_rows,
            code=code,
            name=name,
            market_data=market_window,
        )
        if not evaluation.passed:
            eval_results[idx] = "CANDIDATE_RULE_FAILED"
            continue

        signal = _signal_from_evaluation(code, name, idx, evaluation_date, row, evaluation)
        passed, reason = apply_signal_experiment_filter(signal, normalized_experiment)
        signals.append(signal)
        eval_results[idx] = "PASSED" if passed else reason or "EXPERIMENT_FILTERED"

    passed_signals = [signal for signal in signals if signal.experiment_passed]
    opportunities = merge_strategy1_signals(passed_signals, eval_results)
    for opportunity in opportunities:
        calculate_strategy1_execution_outcome(opportunity, ohlc_rows, date_to_index)
        apply_strategy1_time_exit(opportunity, ohlc_rows, date_to_index, normalized_experiment)

    return {
        "code": code,
        "name": name,
        "signals": signals,
        "opportunities": opportunities,
        "eval_results": eval_results,
        "raw_signals_count": len(signals),
        "opportunities_count": len(opportunities),
        "strategy_version": getattr(engine, "strategy_version", ""),
        "config_hash": getattr(engine, "config_hash", ""),
    }


def _opportunity_from_signal(signal: Strategy1BacktestSignal) -> Strategy1BacktestOpportunity:
    return Strategy1BacktestOpportunity(
        code=signal.code,
        name=signal.name,
        first_detected_date=signal.evaluation_date,
        last_detected_date=signal.evaluation_date,
        pattern_kind=signal.pattern_kind,
        first_score=signal.score,
        max_score=signal.score,
        signal_count=1,
        stop_loss=signal.stop_loss,
        signal_ids=[],
        evaluation_snapshot=signal.evaluation_snapshot,
    )


def _extend_opportunity(opportunity: Strategy1BacktestOpportunity, signal: Strategy1BacktestSignal) -> None:
    opportunity.last_detected_date = signal.evaluation_date
    opportunity.signal_count += 1
    opportunity.max_score = max(opportunity.max_score, signal.score)
    if signal.stop_loss:
        opportunity.stop_loss = signal.stop_loss
    if signal.evaluation_snapshot:
        opportunity.evaluation_snapshot = signal.evaluation_snapshot


def _signal_from_evaluation(
    code: str,
    name: str,
    evaluation_index: int,
    evaluation_date: str,
    row: dict,
    evaluation,
) -> Strategy1BacktestSignal:
    result = evaluation.result
    dry = evaluation.dry_stable or {}
    key_prices = dry.get("key_prices") or {}
    risk_reward = dry.get("risk_reward") or {}
    return Strategy1BacktestSignal(
        code=code,
        name=name,
        evaluation_date=evaluation_date,
        evaluation_index=evaluation_index,
        pattern_kind=getattr(result, "pattern_kind", ""),
        score=int(getattr(result, "score", 0) or 0),
        cup_depth_pct=float(getattr(result, "cup_depth_pct", 0) or 0),
        cup_duration=int(getattr(result, "cup_duration", 0) or 0),
        handle_depth_pct=float(getattr(result, "handle_depth_pct", 0) or 0),
        handle_duration=int(getattr(result, "handle_duration", 0) or 0),
        lip_deviation_pct=float(getattr(result, "lip_deviation_pct", 0) or 0),
        is_breakout=bool(getattr(result, "is_breakout", False)),
        is_volume_breakout=bool(getattr(result, "is_volume_breakout", False)),
        breakout_price=float(getattr(result, "breakout_price", 0) or 0),
        current_close=float(row.get("close") or 0),
        volume_dry_score=int((dry.get("volume_dry") or {}).get("score") or 0),
        price_stable_score=int((dry.get("price_stable") or {}).get("score") or 0),
        pattern_score_20=int((dry.get("pattern_score") or {}).get("score") or 0),
        verdict_key=str((dry.get("decision") or {}).get("verdict_key") or ""),
        risk_percent=float(risk_reward.get("risk_percent") or 0),
        rr1=float(risk_reward.get("rr1") or 0),
        entry_zone_low=float(key_prices.get("entry_zone_low") or 0),
        entry_zone_high=float(key_prices.get("entry_zone_high") or 0),
        stop_loss=float(key_prices.get("stop_loss") or 0),
        target_1=float(key_prices.get("target_1") or 0),
        target_2=float(key_prices.get("target_2") or 0),
        evaluation_snapshot=evaluation.to_dict() if hasattr(evaluation, "to_dict") else None,
    )

"""Strategy5 local DB validation/backtest utilities.

This module only reads local stock_pool and daily_ohlc. It never fetches
external market data.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Sequence

import scanner.db as db
from strategy5.engine import ShortSprintSupportEngine
from strategy5.indicators import normalize_rows

DEFAULT_FORWARD_WINDOWS = (5, 10, 20)
DEFAULT_HISTORICAL_INDICATOR_WINDOW_DAYS = 260


def run_strategy5_local_backtest(
    config: dict | None = None,
    *,
    evaluation_dates: list[str] | None = None,
    limit: int | None = None,
) -> dict:
    config = config or {}
    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)
    engine = ShortSprintSupportEngine(config)
    stocks = db.get_stock_pool()
    if limit:
        stocks = stocks[:limit]

    evaluated = 0
    insufficient = 0
    candidates: list[dict] = []
    rejected_reasons = Counter()
    dates = evaluation_dates or [None]

    for stock in stocks:
        data = db.get_ohlc(stock["code"], max_rows=int(engine.config["kline_days"]))
        if not data:
            insufficient += 1
            rejected_reasons["NO_DAILY_OHLC"] += 1
            continue
        for evaluation_date in dates:
            window = _truncate_to_date(data, evaluation_date) if evaluation_date else data
            if not window:
                insufficient += 1
                rejected_reasons["NO_WINDOW_DATA"] += 1
                continue
            evaluated += 1
            result = engine.evaluate_at(window, code=stock["code"], name=stock.get("name", ""))
            if result.passed:
                candidates.append(result.to_candidate_dict())
            else:
                rejected_reasons[result.status_reason or "REJECTED"] += 1

    key_count = sum(1 for c in candidates if c.get("candidate_type") == "KEY_CANDIDATE")
    watch_count = sum(1 for c in candidates if c.get("candidate_type") == "WATCH_CANDIDATE")
    return {
        "data_source": "daily_ohlc",
        "stocks": len(stocks),
        "evaluated": evaluated,
        "insufficient": insufficient,
        "candidates": len(candidates),
        "key_candidates": key_count,
        "watch_candidates": watch_count,
        "top_candidates": sorted(candidates, key=lambda c: c.get("total_score") or 0, reverse=True)[:20],
        "reject_reasons": dict(rejected_reasons.most_common(20)),
    }


def _truncate_to_date(data: list[dict], evaluation_date: str | None) -> list[dict]:
    if not evaluation_date:
        return data
    return [row for row in data if str(row.get("date") or "") <= evaluation_date]


def run_strategy5_historical_performance_backtest(
    config: dict | None = None,
    *,
    forward_windows: Sequence[int] = DEFAULT_FORWARD_WINDOWS,
    evaluation_step: int = 5,
    cooldown_days: int = 10,
    limit: int | None = None,
    top_events: int = 50,
    trade_only: bool = False,
) -> dict:
    """Evaluate historical Strategy5 signals and their forward returns.

    Uses only local daily_ohlc. A signal is evaluated at close, entered at the
    next trading day's open, then measured over the requested forward windows.
    """
    config = config or {}
    db_path = config.get("data", {}).get("database_path", "data/cuphandle.db")
    db.init_db(db_path)
    engine = ShortSprintSupportEngine(config)
    windows = tuple(sorted({int(w) for w in forward_windows if int(w) > 0}))
    if not windows:
        raise ValueError("forward_windows must contain positive integers")
    if evaluation_step < 1:
        raise ValueError("evaluation_step must be >= 1")
    if cooldown_days < 0:
        raise ValueError("cooldown_days must be >= 0")

    stocks = db.get_stock_pool()
    if limit:
        stocks = stocks[:limit]

    max_forward = max(windows)
    min_history = int(engine.config["minimum_trading_days"])
    min_eval_idx = min_history - 1
    history_window_days = DEFAULT_HISTORICAL_INDICATOR_WINDOW_DAYS
    historical_evaluation_points = 0
    insufficient_stocks = 0
    no_observable_window_stocks = 0
    skipped_duplicate_events = 0
    reject_reasons = Counter()
    events: list[dict] = []

    for stock in stocks:
        data = db.get_ohlc(stock["code"], max_rows=int(engine.config["kline_days"]))
        if not data:
            insufficient_stocks += 1
            reject_reasons["NO_DAILY_OHLC"] += 1
            continue
        normalized_data = normalize_rows(data)
        last_eval_idx = len(data) - 1 - max_forward
        if last_eval_idx < min_eval_idx:
            no_observable_window_stocks += 1
            continue

        last_event_idx: int | None = None
        for eval_idx in range(min_eval_idx, last_eval_idx + 1, evaluation_step):
            historical_evaluation_points += 1
            strategy_window = _select_historical_strategy_window(normalized_data, eval_idx, history_window_days)
            result = engine.evaluate_at(
                strategy_window,
                code=stock["code"],
                name=stock.get("name", ""),
                trading_days_override=eval_idx + 1,
                rows_normalized=True,
            )
            if not result.passed:
                reject_reasons[result.status_reason or "REJECTED"] += 1
                continue
            if trade_only and not result.is_trade_candidate:
                reject_reasons["NON_TRADE_CANDIDATE"] += 1
                continue
            if last_event_idx is not None and eval_idx - last_event_idx <= cooldown_days:
                skipped_duplicate_events += 1
                continue
            event = _build_performance_event(result.to_candidate_dict(), data, eval_idx, windows)
            if event is None:
                reject_reasons["UNOBSERVABLE_FORWARD_RETURN"] += 1
                continue
            events.append(event)
            last_event_idx = eval_idx

    summary = _summarize_performance_events(events, windows)
    summary.update({
        "data_source": "daily_ohlc",
        "entry_model": "NEXT_OPEN",
        "stocks": len(stocks),
        "historical_evaluation_points": historical_evaluation_points,
        "events": len(events),
        "trade_events": sum(1 for event in events if event.get("candidate_type") == "BUY_CANDIDATE"),
        "key_events": sum(1 for event in events if event.get("candidate_type") == "KEY_CANDIDATE"),
        "watch_events": sum(1 for event in events if event.get("candidate_type") == "WATCH_CANDIDATE"),
        "trade_only": trade_only,
        "insufficient_stocks": insufficient_stocks,
        "no_observable_window_stocks": no_observable_window_stocks,
        "skipped_duplicate_events": skipped_duplicate_events,
        "minimum_trading_days": min_history,
        "historical_indicator_window_days": history_window_days,
        "max_forward_days": max_forward,
        "forward_windows": list(windows),
        "reject_reasons": dict(reject_reasons.most_common(20)),
        "events_detail": sorted(events, key=lambda event: event.get("total_score") or 0, reverse=True)[:top_events],
    })
    if not events and historical_evaluation_points == 0 and no_observable_window_stocks:
        summary["limitation"] = "INSUFFICIENT_HISTORY_PLUS_FORWARD_WINDOW"
    else:
        summary["limitation"] = ""
    return summary


def _select_historical_strategy_window(data: list[dict], eval_idx: int, history_window_days: int) -> list[dict]:
    start = max(0, eval_idx + 1 - history_window_days)
    return data[start: eval_idx + 1]


def _build_performance_event(candidate: dict, data: list[dict], eval_idx: int, windows: Sequence[int]) -> dict | None:
    entry_idx = eval_idx + 1
    if entry_idx >= len(data):
        return None
    entry_row = data[entry_idx]
    entry_price = _price(entry_row, "open") or _price(entry_row, "close")
    if entry_price <= 0:
        return None

    event = {
        "code": candidate.get("code"),
        "name": candidate.get("name"),
        "candidate_type": candidate.get("candidate_type"),
        "classification": candidate.get("classification"),
        "signal_date": candidate.get("evaluation_date"),
        "entry_date": entry_row.get("date"),
        "entry_model": "NEXT_OPEN",
        "signal_close": candidate.get("close"),
        "entry_price": round(entry_price, 6),
        "total_score": candidate.get("total_score"),
        "support_status": candidate.get("support_status"),
        "main_support_ma": candidate.get("main_support_ma"),
        "main_support_distance": candidate.get("main_support_distance"),
        "strength_trigger": candidate.get("strength_trigger"),
        "high_trigger": candidate.get("high_trigger"),
        "risk_tags": candidate.get("risk_tags") or [],
        "warn_tags": candidate.get("warn_tags") or [],
    }

    hold_end_idx = entry_idx + max(windows) - 1
    lows = [_price(row, "low") or _price(row, "close") for row in data[entry_idx: hold_end_idx + 1]]
    event["max_drawdown"] = round(min(low / entry_price - 1 for low in lows if low > 0), 6)
    for window in windows:
        exit_idx = entry_idx + window - 1
        exit_price = _price(data[exit_idx], "close")
        event[f"exit_date_{window}d"] = data[exit_idx].get("date")
        event[f"return_{window}d"] = round(exit_price / entry_price - 1, 6)
    return event


def _summarize_performance_events(events: list[dict], windows: Sequence[int]) -> dict:
    summary: dict[str, float | int | None] = {}
    for window in windows:
        key = f"return_{window}d"
        values = [float(event[key]) for event in events if event.get(key) is not None]
        summary[f"avg_return_{window}d"] = _avg(values)
        summary[f"win_rate_{window}d"] = _win_rate(values)
    drawdowns = [float(event["max_drawdown"]) for event in events if event.get("max_drawdown") is not None]
    summary["avg_max_drawdown"] = _avg(drawdowns)
    summary["worst_max_drawdown"] = round(min(drawdowns), 6) if drawdowns else None
    if windows:
        last_key = f"return_{max(windows)}d"
        returns = [float(event[last_key]) for event in events if event.get(last_key) is not None]
        summary[f"profit_factor_{max(windows)}d"] = _profit_factor(returns)
        summary[f"avg_win_{max(windows)}d"] = _avg([value for value in returns if value > 0])
        summary[f"avg_loss_{max(windows)}d"] = _avg([value for value in returns if value < 0])
    return summary


def _price(row: dict, key: str) -> float:
    try:
        value = float(row.get(key) or 0)
    except (TypeError, ValueError):
        return 0.0
    return value


def _avg(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 6)


def _win_rate(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return round(sum(1 for value in values if value > 0) / len(values), 6)


def _profit_factor(values: Sequence[float]) -> float | None:
    gains = sum(value for value in values if value > 0)
    losses = abs(sum(value for value in values if value < 0))
    if losses == 0:
        return None
    return round(gains / losses, 6)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Strategy5 local DB validation.")
    parser.add_argument("--db", default="data/cuphandle.db")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--evaluation-date", action="append", default=None)
    parser.add_argument("--historical-performance", action="store_true")
    parser.add_argument("--forward-days", nargs="+", type=int, default=list(DEFAULT_FORWARD_WINDOWS))
    parser.add_argument("--evaluation-step", type=int, default=5)
    parser.add_argument("--cooldown-days", type=int, default=10)
    args = parser.parse_args()
    if args.historical_performance:
        summary = run_strategy5_historical_performance_backtest(
            {"data": {"database_path": args.db}},
            forward_windows=args.forward_days,
            evaluation_step=args.evaluation_step,
            cooldown_days=args.cooldown_days,
            limit=args.limit,
        )
    else:
        summary = run_strategy5_local_backtest(
            {"data": {"database_path": args.db}},
            evaluation_dates=args.evaluation_date,
            limit=args.limit,
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

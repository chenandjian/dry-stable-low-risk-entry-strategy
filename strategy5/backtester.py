"""Strategy5 local DB validation/backtest utilities.

This module only reads local stock_pool and daily_ohlc. It never fetches
external market data.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter

import scanner.db as db
from strategy5.engine import ShortSprintSupportEngine


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Strategy5 local DB validation.")
    parser.add_argument("--db", default="data/cuphandle.db")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--evaluation-date", action="append", default=None)
    args = parser.parse_args()
    summary = run_strategy5_local_backtest(
        {"data": {"database_path": args.db}},
        evaluation_dates=args.evaluation_date,
        limit=args.limit,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

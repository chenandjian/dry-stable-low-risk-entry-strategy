"""As-of Strategy6 signal reconstruction through the frozen public engine."""
from __future__ import annotations

import hashlib
import json

from strategy6.backtest.data import slice_visible_rows
from strategy6.backtest.models import BacktestSignal


def build_setup_id(snapshot: dict) -> str:
    identity = {
        "code": snapshot.get("code", ""),
        "start_date": snapshot.get("start_date", ""),
        "pattern_type": snapshot.get("pattern_type", ""),
        "pivot_price": round(float(snapshot.get("pivot_price") or 0), 4),
        "box_start_date": snapshot.get("box_start_date", ""),
    }
    digest = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"s6setup-{digest[:20]}"


def rebuild_stock_signals(
    *,
    code: str,
    name: str,
    rows: list[dict],
    evaluation_dates: list[str],
    market_data_by_symbol: dict[str, list[dict]],
    parameter_set_id: str,
    engine,
    minimum_history: int = 260,
) -> list[BacktestSignal]:
    signals: list[BacktestSignal] = []
    for evaluation_date in sorted(set(evaluation_dates)):
        visible_rows = slice_visible_rows(rows, evaluation_date)
        if len(visible_rows) < minimum_history or not visible_rows:
            continue
        visible_market = {
            symbol: slice_visible_rows(values, evaluation_date)
            for symbol, values in market_data_by_symbol.items()
        }
        evaluation = engine.evaluate_at(
            visible_rows,
            code=code,
            name=name,
            trading_days_override=len(visible_rows),
            market_data_by_symbol=visible_market,
        )
        snapshot = evaluation.to_candidate_dict()
        if snapshot.get("candidate_type") == "REJECTED" or snapshot.get("tail_path") == "NONE":
            continue
        signals.append(BacktestSignal(
            parameter_set_id=parameter_set_id,
            code=code,
            name=name,
            evaluation_date=evaluation_date,
            setup_id=build_setup_id(snapshot),
            tail_path=str(snapshot.get("tail_path") or "NONE"),
            candidate_type=str(snapshot.get("candidate_type") or "REJECTED"),
            snapshot=snapshot,
        ))
    return signals


def signal_to_record(signal: BacktestSignal) -> dict:
    return {
        "code": signal.code,
        "name": signal.name,
        "evaluation_date": signal.evaluation_date,
        "setup_id": signal.setup_id,
        "tail_path": signal.tail_path,
        "candidate_type": signal.candidate_type,
        "snapshot": signal.snapshot,
    }

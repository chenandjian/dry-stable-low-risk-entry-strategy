"""As-of Strategy6 signal reconstruction through the frozen public engine."""
from __future__ import annotations

import hashlib
import json

from strategy6.backtest.data import slice_visible_rows
from strategy6.backtest.models import BacktestSignal


_PATH_ORDER = ("ORIGINAL", "BOX", "BROOKS")


def authoritative_tail_paths(snapshot: dict) -> list[str]:
    """Return three-path attribution while preserving legacy snapshot fallback."""
    if "tail_paths" in snapshot:
        raw_paths = snapshot.get("tail_paths")
        if isinstance(raw_paths, str):
            try:
                raw_paths = json.loads(raw_paths)
            except (TypeError, ValueError):
                raw_paths = []
        if isinstance(raw_paths, (list, tuple, set)):
            selected = {str(value).upper() for value in raw_paths}
            paths = [path for path in _PATH_ORDER if path in selected]
            if paths:
                return paths
    flag_by_path = {
        "ORIGINAL": "original_tail_pass",
        "BOX": "box_tail_pass",
        "BROOKS": "brooks_tail_pass",
    }
    if any(key in snapshot for key in flag_by_path.values()):
        return [
            path for path in _PATH_ORDER
            if _pass_flag(snapshot.get(flag_by_path[path]))
        ]
    legacy_path = str(snapshot.get("tail_path") or "NONE").upper()
    return {
        "ORIGINAL": ["ORIGINAL"],
        "BOX": ["BOX"],
        "BOTH": ["ORIGINAL", "BOX"],
    }.get(legacy_path, [])


def _pass_flag(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def brooks_setup_types(snapshot: dict) -> list[str]:
    direct = snapshot.get("brooks_setup_types")
    if isinstance(direct, list):
        return [str(value) for value in direct if value]
    brooks_result = snapshot.get("brooks_result")
    if not isinstance(brooks_result, dict):
        return []
    structure = brooks_result.get("structure")
    if not isinstance(structure, dict) or not isinstance(structure.get("setup_types"), list):
        return []
    return [str(value) for value in structure["setup_types"] if value]


def path_metadata(snapshot: dict) -> dict:
    paths = authoritative_tail_paths(snapshot)
    if len(paths) > 1:
        summary = "MULTI"
    else:
        summary = paths[0] if paths else "NONE"
    primary = str(snapshot.get("tail_primary_path") or "").upper()
    if primary not in paths:
        scores = {
            "ORIGINAL": float(snapshot.get("original_tail_score") or 0),
            "BOX": float(snapshot.get("box_tail_score") or 0),
            "BROOKS": float(snapshot.get("brooks_tail_score") or 0),
        }
        priority = {"ORIGINAL": 0, "BOX": 1, "BROOKS": 2}
        primary = max(paths, key=lambda path: (scores[path], priority[path])) if paths else "NONE"
    return {
        "tail_paths": paths,
        "tail_path_summary": summary,
        "tail_primary_path": primary,
        "passed_path_count": len(paths),
        "multi_path_confirmed": len(paths) >= 2,
        "brooks_status": str(snapshot.get("brooks_status") or "BROOKS_DISABLED"),
        "brooks_setup_types": brooks_setup_types(snapshot),
    }


def is_trade_ready_snapshot(snapshot: dict) -> bool:
    paths = authoritative_tail_paths(snapshot)
    if paths == ["BROOKS"]:
        return bool(snapshot.get("brooks_trade_ready"))
    return bool(paths)


def build_setup_id(snapshot: dict) -> str:
    identity = {
        "code": snapshot.get("code", ""),
        "start_date": snapshot.get("start_date", ""),
        "pattern_type": snapshot.get("pattern_type", ""),
        "pivot_price": round(float(snapshot.get("pivot_price") or 0), 4),
        "box_start_date": snapshot.get("box_start_date", ""),
    }
    if "BROOKS" in authoritative_tail_paths(snapshot):
        brooks_result = snapshot.get("brooks_result")
        structure = brooks_result.get("structure") if isinstance(brooks_result, dict) else {}
        structure = structure if isinstance(structure, dict) else {}
        identity["brooks_structure"] = {
            "setup_types": sorted(brooks_setup_types(snapshot)),
            "first_recent_low_date": structure.get("first_recent_low_date", ""),
            "second_recent_low_date": structure.get("second_recent_low_date", ""),
            "second_entry_signal_date": structure.get("second_entry_signal_date", ""),
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
        if str(visible_rows[-1].get("date") or "") != evaluation_date:
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
        if snapshot.get("candidate_type") == "REJECTED" or not authoritative_tail_paths(snapshot):
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

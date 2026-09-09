"""Extensible multi-bar price-pattern diagnostics for Strategy6 batch scoring."""
from __future__ import annotations

from strategy6.slow_rounded_base import evaluate_slow_rounded_base


def evaluate_collection_patterns(rows: list[dict]) -> list[dict]:
    try:
        result = evaluate_slow_rounded_base(rows)
    except Exception as exc:
        return [{
            "code": "SLOW_ROUNDED_BASE", "name": "缓跌圆底", "matched": False,
            "strongMatched": False, "status": "EVALUATION_FAILED", "score": 0.0,
            "grade": "UNQUALIFIED", "startDate": "", "endDate": "", "windowDays": 0,
            "features": {}, "componentScores": {}, "invariants": {}, "reasons": [],
            "warnings": ["PATTERN_EVALUATION_FAILED"], "error": str(exc),
            "modelVersion": "SLOW_ROUNDED_BASE_V2",
        }]
    return [_to_api(result)]


def _to_api(result: dict) -> dict:
    return {
        "code": result["code"],
        "name": result["name"],
        "matched": result["matched"],
        "strongMatched": result["strong_matched"],
        "status": result["status"],
        "score": result["score"],
        "grade": result["grade"],
        "startDate": result["start_date"],
        "endDate": result["end_date"],
        "windowDays": result["window_days"],
        "features": _camel_keys(result["features"]),
        "componentScores": _camel_keys(result["component_scores"]),
        "invariants": _camel_keys(result["invariants"]),
        "reasons": result["reasons"],
        "warnings": result["warnings"],
        "modelVersion": result["model_version"],
    }


def _camel_keys(values: dict) -> dict:
    return {_camel(key): value for key, value in values.items()}


def _camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)

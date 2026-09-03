"""Read-only batch evaluation for user-supplied Strategy6 stocks."""
from __future__ import annotations

from scanner import db
from strategy6.engine import StrongVcpTailEngine


MARKET_SYMBOLS = ("sh000001", "sz399001", "sz399006", "hs300")


def evaluate_strategy6_batch(codes: list[str], config: dict) -> dict:
    """Evaluate local daily data without fetching data or mutating scan state."""
    engine = StrongVcpTailEngine(config)
    pool = {item["code"]: item for item in db.get_stock_pool()}
    market_data = {
        symbol: db.get_market_index_ohlc(symbol)
        for symbol in MARKET_SYMBOLS
    }
    results: list[dict] = []
    errors: list[dict] = []

    for code in codes:
        stock = pool.get(code, {})
        name = stock.get("name", "")
        rows = db.get_ohlc(code)
        if not rows:
            errors.append(_error(code, name, "KLINE_NOT_FOUND", "本地没有K线数据"))
            continue
        metadata = db.get_ohlc_metadata(code) or {}
        try:
            evaluation = engine.evaluate_at(
                rows,
                code=code,
                name=name,
                data_source=metadata.get("source", ""),
                kline_fetched_at=metadata.get("fetched_at", ""),
                market_data_by_symbol=market_data,
            )
        except Exception as exc:
            errors.append(_error(code, name, "EVALUATION_FAILED", str(exc)))
            continue
        results.append(_summarize(evaluation, metadata))

    results.sort(
        key=lambda item: (
            -item["tailQualityScore"],
            -int(item["tailPass"]),
            -item["totalScore"],
            item["code"],
        )
    )
    return {
        "results": results,
        "errors": errors,
        "evaluatedCount": len(results),
        "errorCount": len(errors),
        "sort": "TAIL_QUALITY_DESC_TAIL_PASS_DESC_TOTAL_SCORE_DESC",
        "dataMode": "LOCAL_ONLY",
    }


def _summarize(evaluation, metadata: dict) -> dict:
    row = evaluation.to_candidate_dict()
    dry_tail = evaluation.dry_tail
    score = evaluation.score
    return {
        "code": row["code"],
        "name": row.get("name", ""),
        "evaluationDate": row.get("evaluation_date", ""),
        "currentPrice": row.get("current_price", 0.0),
        "candidateType": row.get("candidate_type", "REJECTED"),
        "classification": row.get("classification", "rejected"),
        "totalScore": score.total_score,
        "tailScore": score.tail_score,
        "tailQualityScore": dry_tail.dry_stable_score,
        "tailPass": dry_tail.dry_tail_pass,
        "originalTailScore": row.get("original_tail_score", 0),
        "tailVolumeRatio": dry_tail.tail_volume_ratio,
        "volumeSlope10": dry_tail.volume_slope_10,
        "closeRange5": row.get("close_range_5", 0.0),
        "range5": row.get("range_5", 0.0),
        "return5": row.get("return_5", 0.0),
        "bigDownVolume": bool(evaluation.indicators.has_big_down_volume),
        "tailReasons": list(dry_tail.reasons),
        "tailRejects": list(dry_tail.rejects),
        "rejectReasons": list(evaluation.reject_reasons),
        "scoreReasons": list(score.score_reasons),
        "scoreBreakdown": {
            "strongStart": score.strong_start_score,
            "pattern": score.pattern_score_component,
            "support": score.support_score,
            "tail": score.tail_score,
            "objectiveRiskReward": score.objective_rr_score,
            "relativeStrengthRisk": score.relative_strength_risk_score,
        },
        "patternType": row.get("pattern_type", "UNKNOWN"),
        "phaseStatus": row.get("phase_status", ""),
        "tailDays": row.get("tail_days", 0),
        "supportStatus": row.get("support_status", ""),
        "marketStatus": row.get("market_status", "UNKNOWN"),
        "objectiveRiskReward2": row.get("objective_rr_2", 0.0),
        "dataSource": metadata.get("source", ""),
        "klineFetchedAt": metadata.get("fetched_at", ""),
        "decisionProfile": row.get("decision_profile", ""),
        "scoreModelVersion": row.get("score_model_version", ""),
        "strongTrendSqueezePass": row.get("strong_trend_squeeze_pass"),
        "strongTrendSqueezeStatus": row.get("strong_trend_squeeze_status", ""),
        "trendClose": row.get("trend_close"),
        "trendLow250": row.get("trend_low_250"),
        "trendHigh250": row.get("trend_high_250"),
        "trendCloseToLowRatio": row.get("trend_close_to_low_ratio"),
        "trendCloseToHighRatio": row.get("trend_close_to_high_ratio"),
        "trendEma150": row.get("trend_ema150"),
        "trendEma200": row.get("trend_ema200"),
        "trendSqueezeOn": row.get("trend_squeeze_on"),
        "trendBbUpper": row.get("trend_bb_upper"),
        "trendBbLower": row.get("trend_bb_lower"),
        "trendKcUpper": row.get("trend_kc_upper"),
        "trendKcLower": row.get("trend_kc_lower"),
        "strongTrendSqueezeReasons": row.get("strong_trend_squeeze_reasons", []),
        "strongTrendSqueezeModelVersion": row.get("strong_trend_squeeze_model_version", ""),
    }


def _error(code: str, name: str, error: str, message: str) -> dict:
    return {"code": code, "name": name, "error": error, "message": message}

"""Strategy5 four-dimension scoring."""
from __future__ import annotations

import math

from strategy5.models import Strategy5Indicators, Strategy5Score, Strategy5Support


def score_strategy5(ind: Strategy5Indicators, support: Strategy5Support) -> Strategy5Score:
    technical = _technical_score(ind, support)
    capital = _capital_score(ind)
    trend = _trend_score(ind)
    support_quality = _support_quality_score(ind, support)
    total = min(100.0, technical + capital + trend + support_quality)
    reasons = [
        f"technical={technical:.1f}",
        f"capital={capital:.1f}",
        f"trend={trend:.1f}",
        f"support={support_quality:.1f}",
    ]
    return Strategy5Score(
        technical_score=round(technical, 2),
        capital_score=round(capital, 2),
        trend_score=round(trend, 2),
        support_quality_score=round(support_quality, 2),
        total_score=round(total, 2),
        score_reasons=reasons,
    )


def _technical_score(ind: Strategy5Indicators, support: Strategy5Support) -> float:
    pairs = [
        ind.ma5 > ind.ma10,
        ind.ma10 > ind.ma20,
        ind.ma20 > ind.ma50,
        ind.ma50 > ind.ma100,
        ind.ma100 > ind.ma250,
    ]
    alignment = sum(1 for ok in pairs if ok) / len(pairs) * 10
    state = {
        "SPRINT_MA5_SUPPORT": 12,
        "SPRINT_MA10_SUPPORT": 10,
        "SPRINT_MA20_SUPPORT": 7,
        "SPRINT_MA50_TESTING": 4,
    }.get(support.support_status, 0)
    proximity = max(0.0, 5 - support.main_support_distance * 100)
    if ind.ma20_slope_5d >= 0 and ind.ma50_slope_10d >= 0:
        slope = min(8.0, (ind.ma20_slope_5d / 5 + ind.ma50_slope_10d / 10) * 2)
    else:
        slope = max(0.0, (ind.ma20_slope_5d + ind.ma50_slope_10d) * 2)
    return min(35.0, alignment + state + proximity + slope)


def _capital_score(ind: Strategy5Indicators) -> float:
    turnover = min(15.0, math.log10(max(ind.avg_turnover_60d, 1)) * 5)
    trend = min(8.0, max(0.0, (ind.avg_turnover_10d / ind.avg_turnover_60d - 0.8) * 10)) if ind.avg_turnover_60d > 0 else 0.0
    consistency = min(7.0, ind.avg_turnover_30d / ind.avg_turnover_60d * 5) if ind.avg_turnover_60d > 0 else 0.0
    return min(30.0, turnover + trend + consistency)


def _trend_score(ind: Strategy5Indicators) -> float:
    distance_year = (ind.close - ind.ma250) / ind.ma250 * 100 if ind.ma250 > 0 else 0.0
    if distance_year > 100:
        year_score = 5
    elif distance_year > 50:
        year_score = 10
    elif distance_year > 20:
        year_score = 8
    else:
        year_score = 6 if distance_year > 0 else 0
    long_gap = min(5.0, ((ind.ma120 - ind.ma250) / ind.ma250 * 100) / 5) if ind.ma250 > 0 else 0.0
    ma50_room = min(5.0, max(0.0, ((ind.close - ind.ma50) / ind.ma50 * 100) / 3)) if ind.ma50 > 0 else 0.0
    return min(20.0, year_score + max(0.0, long_gap) + ma50_room)


def _support_quality_score(ind: Strategy5Indicators, support: Strategy5Support) -> float:
    sq = min(12.0, support.support_score)
    ma20 = min(4.0, ind.ma20_slope_5d / 2) if ind.ma20_slope_5d > 0 else 0.0
    ma50 = min(3.0, ind.ma50_slope_10d / 2) if ind.ma50_slope_10d > 0 else 0.0
    return min(15.0, sq + ma20 + ma50)

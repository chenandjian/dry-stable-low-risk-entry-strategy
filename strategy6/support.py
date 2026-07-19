"""Strategy6 support clusters and ATR-adaptive support zones."""
from __future__ import annotations

from strategy6.models import (
    Strategy6Indicators,
    Strategy6Pattern,
    Strategy6Start,
    Strategy6Support,
)


SOURCE_WEIGHTS = {
    "PATTERN_LOW": 1.5,
    "PLATFORM_LOW": 1.5,
    "MA20": 1.3,
    "RECENT_10_CLOSE_LOW": 1.2,
    "RECENT_10_LOW": 1.2,
    "RECENT_20_CLOSE_LOW": 1.2,
    "START_LOW": 1.2,
    "MA10": 1.0,
    "MA5": 0.8,
}
STRUCTURAL_SOURCES = {
    "PATTERN_LOW", "PLATFORM_LOW", "MA20", "RECENT_10_CLOSE_LOW",
    "RECENT_10_LOW", "RECENT_20_CLOSE_LOW", "START_LOW",
}


def evaluate_support(
    rows: list[dict],
    ind: Strategy6Indicators,
    start: Strategy6Start,
    pattern: Strategy6Pattern,
    config: dict,
) -> Strategy6Support:
    if ind.current_price <= 0:
        return Strategy6Support()
    candidates = _support_candidates(rows, ind, start, pattern)
    tolerance = max(
        ind.current_price * float(config["support_cluster_price_pct"]),
        ind.atr14 * float(config["support_cluster_atr_multiplier"]),
    )
    clusters = _cluster_candidates(candidates, tolerance)
    key_cluster = _select_key_cluster(clusters, rows, ind, config)
    if not key_cluster:
        return Strategy6Support()

    key_support = key_cluster["price"]
    zone_width = max(
        ind.current_price * float(config["support_zone_price_pct"]),
        ind.atr14 * float(config["support_zone_atr_multiplier"]),
    )
    zone_low = key_support - zone_width
    zone_high = key_support + zone_width
    tests = _support_test_count(
        rows,
        key_support,
        zone_width,
        int(config["support_test_lookback"]),
    )
    sources = sorted(key_cluster["sources"])
    status = _support_status(sources, ind, key_support)
    tactical = _tactical_support(ind)
    defense = _defense_support(ind, start, key_support)
    cluster_score = _cluster_score(key_cluster, rows, ind, config)
    support_score = min(25, cluster_score + (4 if tests >= 2 else 2 if tests >= 1 else 0))
    reaction_score, reaction_reasons, reaction_risks = evaluate_support_reaction(
        rows,
        key_support,
        zone_width,
        int(config["support_test_lookback"]),
    )
    return Strategy6Support(
        support_status=status,
        main_support_ma=_main_support_ma(sources),
        tactical_support_price=round(tactical, 4),
        key_support_price=round(key_support, 4),
        prior_key_support_price=round(_prior_key_support(rows, ind), 4),
        support_zone_low=round(zone_low, 4),
        support_zone_high=round(zone_high, 4),
        defense_support_price=round(defense, 4),
        support_test_count=tests,
        pivot_price=round(pattern.pivot_price, 4),
        box_height=round(pattern.pattern_height, 4),
        support_score=support_score,
        support_cluster_sources=sources,
        support_cluster_score=cluster_score,
        support_reaction_score=reaction_score,
        support_reaction_reasons=reaction_reasons,
        support_reaction_risk_tags=reaction_risks,
    )


def evaluate_support_reaction(
    rows: list[dict],
    support: float,
    width: float,
    lookback: int,
) -> tuple[int, list[str], list[str]]:
    if support <= 0 or not rows:
        return 0, [], []
    start = max(0, len(rows) - lookback)
    raw_tests = [
        index for index in range(start, len(rows))
        if float(rows[index]["low"]) <= support + width
    ]
    tests = _first_index_per_episode(raw_tests)
    if not tests:
        return 0, [], []

    reactions: list[dict] = []
    for index in tests:
        prior = rows[max(0, index - 20):index]
        baseline_volume = sum(float(row["volume"]) for row in prior) / len(prior) if prior else 0.0
        volume_ratio = float(rows[index]["volume"]) / baseline_volume if baseline_volume > 0 else 0.0
        follow = rows[index + 1:min(len(rows), index + 4)]
        best_follow_close = max((float(row["close"]) for row in follow), default=float(rows[index]["close"]))
        recovery = best_follow_close / support - 1.0
        close_broken = float(rows[index]["close"]) < support - width
        recovered_floor = any(float(row["close"]) >= support - width for row in follow)
        reactions.append({
            "index": index,
            "volume_ratio": volume_ratio,
            "recovery": recovery,
            "unrecovered_volume_break": close_broken and volume_ratio >= 1.2 and not recovered_floor,
        })

    reasons: list[str] = []
    risks: list[str] = []
    score = 0
    if any(0 < item["volume_ratio"] <= 0.80 for item in reactions):
        score += 3
        reasons.append("SUPPORT_TEST_LOW_VOLUME")
    best_recovery = max(item["recovery"] for item in reactions)
    if best_recovery >= 0.02:
        score += 3
        reasons.append("SUPPORT_TEST_RECOVERED")
    elif best_recovery >= 0:
        score += 1
    if len(reactions) >= 2:
        score += 2
        reasons.append("SUPPORT_TEST_REPEATED")
    has_unrecovered_break = any(item["unrecovered_volume_break"] for item in reactions)
    if has_unrecovered_break:
        risks.append("SUPPORT_VOLUME_BREAK_UNRECOVERED")
    else:
        score += 2
    if (
        len(reactions) >= 2
        and reactions[-2]["recovery"] >= 0.01
        and reactions[-1]["recovery"] < reactions[-2]["recovery"] * 0.5
    ):
        risks.append("SUPPORT_REACTION_WEAKENING")
        score = max(0, score - 2)
    return min(10, score), reasons, risks


def _first_index_per_episode(indexes: list[int]) -> list[int]:
    result: list[int] = []
    for index in indexes:
        if not result or index > result[-1] + 1:
            result.append(index)
    return result


def _support_candidates(
    rows: list[dict],
    ind: Strategy6Indicators,
    start: Strategy6Start,
    pattern: Strategy6Pattern,
) -> list[tuple[str, float, float]]:
    history = rows[:-1] if len(rows) > 1 else rows
    values = [
        ("MA5", ind.ma5),
        ("MA10", ind.ma10),
        ("MA20", ind.ma20),
        ("PATTERN_LOW", pattern.pattern_low),
        ("START_LOW", start.start_low),
    ]
    if history[-10:]:
        values.extend([
            ("RECENT_10_CLOSE_LOW", min(row["close"] for row in history[-10:])),
            ("RECENT_10_LOW", min(row["low"] for row in history[-10:])),
        ])
    if history[-20:]:
        values.append(("RECENT_20_CLOSE_LOW", min(row["close"] for row in history[-20:])))
    return [
        (source, float(price), SOURCE_WEIGHTS[source])
        for source, price in values
        if price and price > 0 and price <= ind.current_price * 1.03
    ]


def _cluster_candidates(
    candidates: list[tuple[str, float, float]],
    tolerance: float,
) -> list[dict]:
    clusters: list[dict] = []
    for source, price, weight in sorted(candidates, key=lambda item: item[1]):
        target = next(
            (cluster for cluster in clusters if abs(price - cluster["price"]) <= tolerance),
            None,
        )
        if target is None:
            clusters.append({
                "price": price,
                "weighted_sum": price * weight,
                "weight": weight,
                "sources": {source},
            })
            continue
        target["weighted_sum"] += price * weight
        target["weight"] += weight
        target["sources"].add(source)
        target["price"] = target["weighted_sum"] / target["weight"]
    return clusters


def _select_key_cluster(clusters: list[dict], rows: list[dict], ind: Strategy6Indicators, config: dict) -> dict | None:
    structural = [
        cluster for cluster in clusters
        if cluster["sources"] & STRUCTURAL_SOURCES and cluster["price"] <= ind.current_price * 1.03
    ]
    if not structural:
        return None
    return max(structural, key=lambda cluster: _cluster_score(cluster, rows, ind, config))


def _cluster_score(cluster: dict, rows: list[dict], ind: Strategy6Indicators, config: dict) -> int:
    distance = abs(ind.current_price - cluster["price"]) / ind.current_price
    source_score = min(12, int(round(cluster["weight"] * 3)))
    overlap_score = min(5, max(0, len(cluster["sources"]) - 1) * 2)
    distance_score = 5 if distance <= 0.03 else 3 if distance <= 0.06 else 1
    width = max(
        ind.current_price * float(config["support_zone_price_pct"]),
        ind.atr14 * float(config["support_zone_atr_multiplier"]),
    )
    tests = _support_test_count(rows, cluster["price"], width, int(config["support_test_lookback"]))
    test_score = 3 if tests >= 2 else 2 if tests == 1 else 0
    return min(20, source_score + overlap_score + distance_score + test_score)


def _support_test_count(rows: list[dict], support: float, width: float, lookback: int) -> int:
    return sum(
        1 for row in rows[-lookback:]
        if row["low"] <= support + width and row["close"] >= support - width
    )


def _support_status(sources: list[str], ind: Strategy6Indicators, support: float) -> str:
    if "PATTERN_LOW" in sources:
        return "PATTERN_SUPPORT"
    if "MA20" in sources:
        return "MA20_SUPPORT"
    if support >= ind.ma50 * 0.92 if ind.ma50 > 0 else True:
        return "KEY_SUPPORT_VALID"
    return "SUPPORT_FAILED"


def _tactical_support(ind: Strategy6Indicators) -> float:
    if ind.ma5 > 0 and abs(ind.current_price - ind.ma5) / ind.current_price <= 0.04:
        return ind.ma5
    if ind.ma10 > 0 and abs(ind.current_price - ind.ma10) / ind.current_price <= 0.05:
        return ind.ma10
    return 0.0


def _defense_support(ind: Strategy6Indicators, start: Strategy6Start, key_support: float) -> float:
    values = [value for value in (ind.ma50, start.start_low, key_support) if value > 0]
    return min(values) if values else key_support


def _prior_key_support(rows: list[dict], ind: Strategy6Indicators) -> float:
    history = rows[:-1] if len(rows) > 1 else rows
    values = [ind.ma20]
    if history[-20:]:
        values.append(min(row["close"] for row in history[-20:]))
    return max((value for value in values if value > 0), default=0.0)


def _main_support_ma(sources: list[str]) -> str:
    for source in ("MA20", "MA10", "MA5"):
        if source in sources:
            return source
    return ""

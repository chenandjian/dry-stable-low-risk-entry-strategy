"""Historical formal-candidate qualification for the Strategy6 VCP pool."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Strategy6VcpCandidateHistory:
    qualified: bool = False
    candidate_date: str = ""
    candidate_type: str = ""
    candidate_score: int = 0
    source: str = ""
    origin_start_date: str = ""


def evaluate_vcp_candidate_history(
    *,
    rows: list[dict],
    market_data_by_symbol: dict[str, list[dict]],
    strategy_config: dict,
    code: str,
    name: str,
    origin_start_date: str,
    evaluation_date: str,
    engine_factory: Callable[[dict], object] | None = None,
) -> Strategy6VcpCandidateHistory:
    """Find the latest formal candidate in the current VCP lifecycle."""
    origin = str(origin_start_date or "")
    current = str(evaluation_date or "")
    empty = Strategy6VcpCandidateHistory(origin_start_date=origin)
    if not origin or not current or origin > current:
        return empty

    config = copy.deepcopy(strategy_config)
    config["vcp_observer_enabled"] = False
    if engine_factory is None:
        from strategy6.engine import StrongVcpTailEngine

        engine_factory = lambda resolved: StrongVcpTailEngine({"strategy6": resolved})
    engine = engine_factory(config)
    minimum_history = int(config.get("minimum_trading_days", 1))

    eligible_indexes = [
        index
        for index, row in enumerate(rows)
        if origin <= str(row.get("date") or "") <= current
        and index + 1 >= minimum_history
    ]
    for index in reversed(eligible_indexes):
        visible_rows = rows[:index + 1]
        date = str(visible_rows[-1].get("date") or "")
        visible_market = {
            symbol: [
                item for item in values
                if str(item.get("date") or "") <= date
            ]
            for symbol, values in market_data_by_symbol.items()
        }
        evaluation = engine.evaluate_at(
            visible_rows,
            code=code,
            name=name,
            trading_days_override=len(visible_rows),
            market_data_by_symbol=visible_market,
        )
        if evaluation.candidate_type == "REJECTED":
            continue
        return Strategy6VcpCandidateHistory(
            qualified=True,
            candidate_date=date,
            candidate_type=str(evaluation.candidate_type),
            candidate_score=int(evaluation.score.total_score),
            source="DAILY_AS_OF_REPLAY",
            origin_start_date=origin,
        )
    return empty

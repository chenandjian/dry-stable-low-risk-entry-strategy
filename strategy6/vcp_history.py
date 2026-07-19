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
    pattern_start_date: str = "",
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
    pattern_index = _date_index(rows, pattern_start_date)

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
        if (
            pattern_index is not None
            and index < pattern_index
            and not _history_continuity_valid(
                rows,
                candidate_index=index,
                pattern_index=pattern_index,
                config=config,
            )
        ):
            return empty
        return Strategy6VcpCandidateHistory(
            qualified=True,
            candidate_date=date,
            candidate_type=str(evaluation.candidate_type),
            candidate_score=int(evaluation.score.total_score),
            source="DAILY_AS_OF_REPLAY",
            origin_start_date=origin,
        )
    return empty


def _history_continuity_valid(
    rows: list[dict],
    *,
    candidate_index: int,
    pattern_index: int,
    config: dict,
) -> bool:
    if candidate_index >= pattern_index:
        return True
    candidate_close = _close(rows[candidate_index])
    pattern_close = _close(rows[pattern_index])
    if candidate_close <= 0 or pattern_close <= 0:
        return False

    max_start_loss = float(config.get("vcp_history_max_start_loss_pct", 0.15))
    if pattern_close / candidate_close - 1.0 < -max_start_loss:
        return False

    max_drawdown_limit = float(config.get("vcp_history_max_drawdown_pct", 0.20))
    peak = candidate_close
    max_drawdown = 0.0
    for row in rows[candidate_index:pattern_index + 1]:
        close = _close(row)
        if close <= 0:
            return False
        peak = max(peak, close)
        max_drawdown = min(max_drawdown, close / peak - 1.0)
    if max_drawdown < -max_drawdown_limit:
        return False

    bearish_days = int(config.get("vcp_history_bearish_trend_days", 5))
    if _ending_bearish_alignment_days(rows, pattern_index) >= bearish_days:
        return False
    return True


def _ending_bearish_alignment_days(rows: list[dict], end_index: int) -> int:
    count = 0
    for index in range(end_index, -1, -1):
        ma20 = _moving_average(rows, index, 20)
        ma50 = _moving_average(rows, index, 50)
        close = _close(rows[index])
        if ma20 is None or ma50 is None or not (close < ma20 < ma50):
            break
        count += 1
    return count


def _moving_average(rows: list[dict], end_index: int, days: int) -> float | None:
    start = end_index - days + 1
    if start < 0:
        return None
    closes = [_close(row) for row in rows[start:end_index + 1]]
    if any(close <= 0 for close in closes):
        return None
    return sum(closes) / days


def _date_index(rows: list[dict], target_date: str) -> int | None:
    target = str(target_date or "")
    if not target:
        return None
    return next(
        (index for index, row in enumerate(rows) if str(row.get("date") or "") == target),
        None,
    )


def _close(row: dict) -> float:
    try:
        return float(row.get("close") or 0.0)
    except (TypeError, ValueError):
        return 0.0

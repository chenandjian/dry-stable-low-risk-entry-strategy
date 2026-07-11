"""Deterministic portfolio candidate allocation."""
from __future__ import annotations

from dataclasses import dataclass, field
import math


TIER_PRIORITY = {"READY_CANDIDATE": 0, "KEY_CANDIDATE": 1, "WATCH_CANDIDATE": 2}


@dataclass
class AllocationResult:
    allocations: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)


def allocate_candidates(
    candidates: list[dict],
    *,
    equity: float,
    cash: float,
    mode: str,
    max_positions: int,
    max_position_pct: float,
    risk_per_trade: float,
) -> AllocationResult:
    result = AllocationResult()
    sorted_candidates = sorted(
        candidates,
        key=lambda item: (
            TIER_PRIORITY.get(str(item.get("candidate_type")), 99),
            -float(item.get("total_score") or 0),
            str(item.get("code") or ""),
        ),
    )
    available_cash = float(cash)
    for item in sorted_candidates:
        if len(result.allocations) >= max_positions:
            result.rejected.append({**item, "reason": "MAX_CONCURRENT_POSITIONS"})
            continue
        entry = float(item.get("entry_price") or 0)
        stop = float(item.get("stop_loss_price") or 0)
        if entry <= 0:
            result.rejected.append({**item, "reason": "INVALID_ENTRY_PRICE"})
            continue
        cap = equity * max_position_pct
        if mode == "FIXED_RISK":
            unit_risk = entry - stop
            if unit_risk <= 0:
                result.rejected.append({**item, "reason": "INVALID_RISK_DISTANCE"})
                continue
            raw_shares = min(equity * risk_per_trade / unit_risk, cap / entry)
        else:
            raw_shares = cap / entry
        shares = int(math.floor(raw_shares / 100) * 100)
        notional = round(shares * entry, 6)
        if shares <= 0:
            result.rejected.append({**item, "reason": "BELOW_BOARD_LOT"})
            continue
        if notional > available_cash:
            result.rejected.append({**item, "reason": "INSUFFICIENT_CASH"})
            continue
        available_cash -= notional
        result.allocations.append({**item, "shares": shares, "notional": notional})
    return result


def simulate_portfolio(
    trades: list[dict],
    *,
    initial_equity: float,
    mode: str,
    risk_per_trade: float,
    max_position_pct: float,
    max_concurrent_positions: int,
) -> dict:
    from strategy6.backtest.metrics import calculate_max_drawdown, calculate_trade_metrics

    equity = float(initial_equity)
    cash = float(initial_equity)
    active: list[dict] = []
    accepted: list[dict] = []
    rejected: list[dict] = []
    equity_curve = [equity]
    maximum_active = 0
    ordered = sorted(
        trades,
        key=lambda item: (
            str(item.get("entry_date") or ""),
            TIER_PRIORITY.get(str(item.get("candidate_type")), 99),
            -float(item.get("total_score") or 0),
            str(item.get("code") or ""),
        ),
    )
    for trade in ordered:
        entry_date = str(trade.get("entry_date") or "")
        still_active = []
        for position in active:
            if str(position.get("exit_date") or "9999-12-31") < entry_date:
                cash += float(position["allocated_notional"]) + float(position["allocated_net_profit"])
                equity += float(position["allocated_net_profit"])
                equity_curve.append(equity)
            else:
                still_active.append(position)
        active = still_active
        if any(position.get("code") == trade.get("code") for position in active):
            rejected.append({**trade, "portfolio_reject_reason": "SAME_STOCK_ALREADY_HELD"})
            continue
        capacity = max_concurrent_positions - len(active)
        if capacity <= 0:
            rejected.append({**trade, "portfolio_reject_reason": "MAX_CONCURRENT_POSITIONS"})
            continue
        allocation = allocate_candidates(
            [{
                "code": trade.get("code"),
                "candidate_type": trade.get("candidate_type"),
                "total_score": trade.get("total_score", 0),
                "entry_price": trade.get("entry_price", 0),
                "stop_loss_price": trade.get("stop_loss_price", 0),
            }],
            equity=equity,
            cash=cash,
            mode=mode,
            max_positions=capacity,
            max_position_pct=max_position_pct,
            risk_per_trade=risk_per_trade,
        )
        if not allocation.allocations:
            reason = allocation.rejected[0]["reason"] if allocation.rejected else "CAPITAL_REJECTED"
            rejected.append({**trade, "portfolio_reject_reason": reason})
            continue
        selected = allocation.allocations[0]
        shares = int(selected["shares"])
        notional = float(selected["notional"])
        scale = shares / 100.0
        accepted_trade = {
            **trade,
            "allocated_shares": shares,
            "allocated_notional": notional,
            "allocated_net_profit": round(float(trade.get("net_profit") or 0) * scale, 6),
        }
        cash -= notional
        active.append(accepted_trade)
        accepted.append(accepted_trade)
        maximum_active = max(maximum_active, len(active))
    for position in sorted(active, key=lambda item: str(item.get("exit_date") or "")):
        cash += float(position["allocated_notional"]) + float(position["allocated_net_profit"])
        equity += float(position["allocated_net_profit"])
        equity_curve.append(equity)
    portfolio_trades = [
        {**item, "net_profit": item["allocated_net_profit"]}
        for item in accepted
    ]
    metrics = calculate_trade_metrics(portfolio_trades)
    metrics.update({
        "initial_equity": initial_equity,
        "final_equity": equity,
        "net_return": equity / initial_equity - 1 if initial_equity > 0 else 0.0,
        "max_drawdown": calculate_max_drawdown(equity_curve),
    })
    return {
        "accepted_trades": accepted,
        "rejected_trades": rejected,
        "rejected_count": len(rejected),
        "max_concurrent_positions": maximum_active,
        "equity_curve": equity_curve,
        "metrics": metrics,
    }

"""Signal, trade, portfolio and concentration metrics."""
from __future__ import annotations

from collections import defaultdict
import math
from statistics import mean, median


def calculate_trade_metrics(trades: list[dict]) -> dict:
    if not trades:
        return {
            "trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
            "avg_win_r": 0.0, "avg_loss_r": 0.0, "expectancy_r": 0.0,
            "profit_factor": 0.0, "avg_net_return": 0.0,
            "median_net_return": 0.0, "net_profit": 0.0,
        }
    r_values = [float(item.get("r_multiple") or 0) for item in trades]
    returns = [float(item.get("net_return") or 0) for item in trades]
    profits = [float(item.get("net_profit") or 0) for item in trades]
    wins = [value for value in r_values if value > 0]
    losses = [value for value in r_values if value < 0]
    gross_profit = sum(value for value in profits if value > 0)
    gross_loss = abs(sum(value for value in profits if value < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (math.inf if gross_profit > 0 else 0.0)
    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(trades),
        "avg_win_r": mean(wins) if wins else 0.0,
        "avg_loss_r": abs(mean(losses)) if losses else 0.0,
        "expectancy_r": mean(r_values),
        "profit_factor": profit_factor,
        "avg_net_return": mean(returns),
        "median_net_return": median(returns),
        "net_profit": sum(profits),
    }


def calculate_max_drawdown(equity_curve: list[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = float(equity_curve[0])
    max_drawdown = 0.0
    for value in equity_curve:
        value = float(value)
        peak = max(peak, value)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - value) / peak)
    return max_drawdown


def group_trade_metrics(trades: list[dict], field: str) -> dict[str, dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for trade in trades:
        grouped[str(trade.get(field) or "UNKNOWN")].append(trade)
    return {key: calculate_trade_metrics(values) for key, values in grouped.items()}


def calculate_concentration(
    trades: list[dict],
    *,
    single_stock_limit: float = 0.10,
    top_five_limit: float = 0.35,
    single_year_limit: float = 0.40,
    single_month_limit: float = 0.20,
) -> dict:
    by_stock: dict[str, float] = defaultdict(float)
    by_year: dict[str, float] = defaultdict(float)
    by_month: dict[str, float] = defaultdict(float)
    for trade in trades:
        profit = float(trade.get("net_profit") or 0)
        by_stock[str(trade.get("code") or "UNKNOWN")] += profit
        date = str(trade.get("exit_date") or "")
        if len(date) >= 4:
            by_year[date[:4]] += profit
        if len(date) >= 7:
            by_month[date[:7]] += profit
    total = sum(float(item.get("net_profit") or 0) for item in trades)
    denominator = total if total > 0 else sum(max(0.0, value) for value in by_stock.values())
    stock_sorted = sorted(by_stock.items(), key=lambda item: item[1], reverse=True)

    def share(mapping: dict[str, float]) -> tuple[str, float]:
        if not mapping or denominator <= 0:
            return "", 0.0
        key, value = max(mapping.items(), key=lambda item: item[1])
        return key, value / denominator

    top_stock, stock_share = share(by_stock)
    top_year, year_share = share(by_year)
    top_month, month_share = share(by_month)
    top_five_share = sum(max(0.0, value) for _, value in stock_sorted[:5]) / denominator if denominator > 0 else 0.0
    tags = []
    if stock_share > single_stock_limit:
        tags.append("SINGLE_STOCK_PROFIT_CONCENTRATION")
    if top_five_share > top_five_limit:
        tags.append("TOP_FIVE_PROFIT_CONCENTRATION")
    if year_share > single_year_limit:
        tags.append("SINGLE_YEAR_PROFIT_CONCENTRATION")
    if month_share > single_month_limit:
        tags.append("SINGLE_MONTH_PROFIT_CONCENTRATION")
    return {
        "top_stock": top_stock,
        "single_stock_profit_share": stock_share,
        "top_five_profit_share": top_five_share,
        "top_year": top_year,
        "single_year_profit_share": year_share,
        "top_month": top_month,
        "single_month_profit_share": month_share,
        "risk_tags": tags,
    }

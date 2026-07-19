"""Conservative frozen-plan execution simulator for A-share daily bars."""
from __future__ import annotations

from dataclasses import dataclass, field

from strategy6.backtest.models import BacktestOrder, BacktestSignal, BacktestTrade, stable_hash
from strategy6.limit_up import calc_limit_up_price, get_limit_up_pct, is_one_word_limit_up


@dataclass
class ExecutionOutcome:
    order: BacktestOrder
    trade: BacktestTrade | None = None
    audit_tags: list[str] = field(default_factory=list)


def calculate_transaction_costs(*, entry_price: float, exit_price: float, shares: int, costs: dict) -> dict:
    buy_value = entry_price * shares
    sell_value = exit_price * shares
    buy_commission = max(float(costs["minimum_commission"]), buy_value * float(costs["commission_bps"]) / 10_000)
    sell_commission = max(float(costs["minimum_commission"]), sell_value * float(costs["commission_bps"]) / 10_000)
    sell_tax = sell_value * float(costs["sell_tax_bps"]) / 10_000
    transfer_fee = (buy_value + sell_value) * float(costs["transfer_fee_bps"]) / 10_000
    total = buy_commission + sell_commission + sell_tax + transfer_fee
    return {
        "buy_commission": round(buy_commission, 6),
        "sell_commission": round(sell_commission, 6),
        "sell_tax": round(sell_tax, 6),
        "transfer_fee": round(transfer_fee, 6),
        "total": round(total, 6),
    }


def simulate_frozen_trade(
    signal: BacktestSignal,
    stock_rows: list[dict],
    market_dates: list[str],
    config: dict,
) -> ExecutionOutcome:
    execution = config["execution"]
    costs = config["costs"]
    dates = sorted(date for date in set(market_dates) if date > signal.evaluation_date)
    entry_delay_days = max(0, int(execution.get("entry_delay_days", 0)))
    valid_dates = dates[entry_delay_days:entry_delay_days + int(execution["buy_zone_valid_days"])]
    order = BacktestOrder(
        order_id=f"s6order-{stable_hash([signal.parameter_set_id, signal.setup_id, signal.evaluation_date])[:20]}",
        signal=signal,
        created_date=signal.evaluation_date,
        expire_date=valid_dates[-1] if valid_dates else signal.evaluation_date,
    )
    outcome = ExecutionOutcome(order=order)
    fill_rate = max(0.0, min(1.0, float(execution.get("fill_rate_multiplier", 1.0))))
    fill_bucket = int(stable_hash([signal.parameter_set_id, signal.setup_id, signal.evaluation_date])[:8], 16) / 0xFFFFFFFF
    if fill_rate < 1.0 and fill_bucket >= fill_rate:
        order.status = "EXPIRED_NO_FILL"
        order.fill_reason = "STRESS_FILL_RATE_REJECTED"
        outcome.audit_tags.append("STRESS_FILL_RATE_REJECTED")
        return outcome
    row_by_date = {str(row.get("date") or ""): row for row in stock_rows}
    snapshot = signal.snapshot
    buy_low = float(snapshot.get("buy_zone_low") or 0)
    buy_high = float(snapshot.get("buy_zone_high") or 0)
    limit_price = float(snapshot.get("suggested_limit_price") or buy_high or buy_low)
    stop_price = float(snapshot.get("stop_loss_price") or 0)
    target_price = float(snapshot.get("objective_target_2") or 0)
    if min(buy_low, buy_high, limit_price, stop_price) <= 0 or buy_low > buy_high:
        order.status = "CANCELLED"
        order.fill_reason = "CANCEL_INVALID_FROZEN_PLAN"
        return outcome

    entry_row = None
    entry_price = 0.0
    previous_close = _previous_close(stock_rows, signal.evaluation_date)
    for trade_date in valid_dates:
        row = row_by_date.get(trade_date)
        if not row:
            outcome.audit_tags.append("UNKNOWN_NO_BAR")
            continue
        if float(row.get("volume") or 0) <= 0:
            outcome.audit_tags.append("ZERO_VOLUME")
            continue
        if previous_close > 0 and is_one_word_limit_up(
            signal.code, previous_close,
            float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]),
        ):
            outcome.audit_tags.append("ONE_WORD_LIMIT_UP_UNBUYABLE")
            previous_close = float(row["close"])
            continue
        open_price = float(row["open"])
        if open_price > buy_high:
            order.status = "CANCELLED"
            order.fill_reason = "CANCEL_OPEN_ABOVE_BUY_ZONE"
            return outcome
        if open_price < buy_low:
            order.status = "CANCELLED"
            order.fill_reason = "CANCEL_OPEN_BELOW_BUY_ZONE"
            return outcome
        if open_price <= stop_price:
            order.status = "CANCELLED"
            order.fill_reason = "CANCEL_STRUCTURE_FAILED_BEFORE_ENTRY"
            return outcome
        entry_row = row
        if buy_low <= open_price <= buy_high:
            entry_price = _buy_with_slippage(open_price, costs)
        elif float(row["low"]) <= limit_price <= float(row["high"]):
            entry_price = _buy_with_slippage(limit_price, costs)
        if entry_price > 0:
            break
        previous_close = float(row["close"])

    if not entry_row or entry_price <= 0:
        order.status = "EXPIRED_NO_FILL"
        order.fill_reason = "EXPIRED_NO_FILL"
        return outcome

    order.status = "FILLED"
    order.fill_reason = "FILLED_FROZEN_PLAN"
    shares = 100
    trade = BacktestTrade(
        trade_id=f"s6trade-{stable_hash(order.order_id)[:20]}",
        code=signal.code,
        signal_date=signal.evaluation_date,
        entry_date=str(entry_row["date"]),
        entry_price=round(entry_price, 6),
        intraday_stop_breach=float(entry_row["low"]) <= stop_price,
    )
    entry_index = dates.index(trade.entry_date)
    max_holding_days = int(execution["max_holding_days"])
    holding_dates = dates[entry_index + 1: entry_index + 1 + max_holding_days]
    holding_window_complete = len(holding_dates) >= max_holding_days
    last_observed = None
    exit_previous_close = float(entry_row["close"])
    for trade_date in holding_dates:
        row = row_by_date.get(trade_date)
        if not row:
            outcome.audit_tags.append("UNKNOWN_NO_BAR_EXIT_DELAY")
            continue
        if float(row.get("volume") or 0) <= 0:
            outcome.audit_tags.append("ZERO_VOLUME_EXIT_DELAY")
            continue
        last_observed = row
        if _is_one_word_limit_down(signal.code, exit_previous_close, row):
            outcome.audit_tags.append("ONE_WORD_LIMIT_DOWN_EXIT_DELAY")
            exit_previous_close = float(row["close"])
            continue
        open_price = float(row["open"])
        if open_price <= stop_price:
            _finish_trade(trade, row, _sell_with_slippage(open_price, costs), "STOP_GAP", shares, costs, stop_price)
            break
        stop_hit = float(row["low"]) <= stop_price
        target_hit = target_price > 0 and float(row["high"]) >= target_price
        if stop_hit:
            _finish_trade(trade, row, _sell_with_slippage(stop_price, costs), "STOP", shares, costs, stop_price)
            break
        if target_hit:
            _finish_trade(trade, row, _sell_with_slippage(target_price, costs), "TARGET", shares, costs, stop_price)
            break
        exit_previous_close = float(row["close"])
    if not trade.exit_date and last_observed and holding_window_complete:
        _finish_trade(
            trade, last_observed,
            _sell_with_slippage(float(last_observed["close"]), costs),
            "MAX_HOLDING", shares, costs, stop_price,
        )
    if not trade.exit_date:
        trade.exit_reason = "UNRESOLVED_NO_EXIT_BAR"
    outcome.trade = trade
    return outcome


def _previous_close(rows: list[dict], date: str) -> float:
    previous = [row for row in rows if str(row.get("date") or "") <= date]
    return float(previous[-1]["close"]) if previous else 0.0


def _is_one_word_limit_down(code: str, previous_close: float, row: dict) -> bool:
    if previous_close <= 0:
        return False
    limit_down = calc_limit_up_price(previous_close, -get_limit_up_pct(code))
    prices = [float(row[key]) for key in ("open", "high", "low", "close")]
    return max(prices) - min(prices) <= 0.001 and abs(prices[0] - limit_down) <= 0.01


def _buy_with_slippage(price: float, costs: dict) -> float:
    return price * (1 + float(costs["buy_slippage_bps"]) / 10_000)


def _sell_with_slippage(price: float, costs: dict) -> float:
    return price * (1 - float(costs["sell_slippage_bps"]) / 10_000)


def _finish_trade(
    trade: BacktestTrade,
    row: dict,
    exit_price: float,
    reason: str,
    shares: int,
    costs: dict,
    stop_price: float,
) -> None:
    trade.exit_date = str(row["date"])
    trade.exit_price = round(exit_price, 6)
    trade.exit_reason = reason
    transaction = calculate_transaction_costs(
        entry_price=trade.entry_price, exit_price=trade.exit_price, shares=shares, costs=costs,
    )
    trade.commission = transaction["buy_commission"] + transaction["sell_commission"]
    trade.tax = transaction["sell_tax"] + transaction["transfer_fee"]
    trade.slippage = round(
        trade.entry_price * float(costs["buy_slippage_bps"]) / 10_000
        + trade.exit_price * float(costs["sell_slippage_bps"]) / 10_000,
        6,
    )
    net_profit = (trade.exit_price - trade.entry_price) * shares - transaction["total"]
    trade.net_return = round(net_profit / (trade.entry_price * shares), 8)
    risk = trade.entry_price - stop_price
    trade.r_multiple = round((trade.exit_price - trade.entry_price) / risk, 6) if risk > 0 else 0.0

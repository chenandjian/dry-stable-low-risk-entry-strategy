"""策略3本地 DB 回测任务服务。

读取本地 stock_pool / daily_ohlc，并使用真实指数本地缓存。
"""
from __future__ import annotations

import datetime
import hashlib
import json
import logging
import time

import scanner.db as db
from scanner.index_source import fetch_market_index_daily
from strategy3.backtester import run_strategy3_stock_backtest
from strategy3.market_index import DEFAULT_INDEX_SYMBOLS, resolve_strategy3_market_index

logger = logging.getLogger(__name__)
MARKET_DATA_MODE_LOCAL_PROXY = "local_equal_weight_proxy"
MARKET_DATA_MODE_REAL_INDEX_CACHE = "real_index_cache"
REQUIRED_REAL_INDEX_SYMBOLS = ("sh000001", "sz399001", "sz399006")


def _now_local() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def calculate_daily_ohlc_revision(snapshot_date: str, codes: list[str] | None = None) -> str:
    """计算本地 OHLC 在指定快照日之前的稳定内容指纹。"""
    params = [snapshot_date[:10]]
    query = (
        "SELECT code,date,open,high,low,close,volume,turnover FROM daily_ohlc "
        "WHERE date<=?"
    )
    if codes:
        placeholders = ",".join("?" for _ in codes)
        query += f" AND code IN ({placeholders})"
        params.extend(codes)
    query += " ORDER BY code,date"
    digest = hashlib.sha256()
    for row in db.get_conn().execute(query, params):
        digest.update(json.dumps(row, ensure_ascii=True, separators=(",", ":")).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def build_local_equal_weight_market_data(snapshot_date: str) -> list[dict]:
    """Build a local equal-weight market proxy from daily_ohlc only."""
    rows = db.get_conn().execute(
        "SELECT code,date,close FROM daily_ohlc WHERE date<=? ORDER BY code,date",
        (snapshot_date[:10],),
    )
    return _build_equal_weight_proxy(rows)


def build_local_equal_weight_market_data_by_symbol(snapshot_date: str) -> dict[str, list[dict]]:
    """Build per-index local equal-weight proxies from daily_ohlc only."""
    rows = db.get_conn().execute(
        "SELECT code,date,close FROM daily_ohlc WHERE date<=? ORDER BY code,date",
        (snapshot_date[:10],),
    )
    grouped_rows: dict[str, list[tuple[str, str, float]]] = {}
    for code, date, close in rows:
        selection = resolve_strategy3_market_index(code)
        grouped_rows.setdefault(selection.symbol, []).append((code, date, close))
    return {
        symbol: _build_equal_weight_proxy(symbol_rows)
        for symbol, symbol_rows in grouped_rows.items()
    }


def _build_equal_weight_proxy(rows) -> list[dict]:
    previous_close_by_code = {}
    returns_by_date: dict[str, list[float]] = {}
    for code, date, close in rows:
        previous = previous_close_by_code.get(code)
        if previous and previous > 0 and close and close > 0:
            daily_return = close / previous - 1.0
            if -0.3 < daily_return < 0.3:
                returns_by_date.setdefault(date, []).append(daily_return)
        previous_close_by_code[code] = close

    level = 1000.0
    market_data: list[dict] = []
    for date in sorted(returns_by_date):
        values = returns_by_date[date]
        if not values:
            continue
        open_ = level
        level = level * (1.0 + sum(values) / len(values))
        high = max(open_, level)
        low = min(open_, level)
        market_data.append({
            "date": date,
            "open": open_,
            "high": high,
            "low": low,
            "close": level,
            "volume": len(values),
            "turnover": 0.0,
        })
    return market_data


def refresh_strategy3_market_index_cache(snapshot_date: str, days: int = 900) -> dict[str, dict]:
    """Fetch and cache real market indices for Strategy3 analysis."""
    refreshed: dict[str, dict] = {}
    fetched_at = _now_local()
    for symbol in DEFAULT_INDEX_SYMBOLS:
        try:
            rows = fetch_market_index_daily(symbol, days=days) or []
        except Exception as exc:
            logger.warning("Strategy3 market index refresh failed for %s: %s", symbol, exc)
            rows = []
        rows = [row for row in rows if row.get("date") and row["date"] <= snapshot_date[:10]]
        if rows:
            db.save_market_index_ohlc(symbol, rows, source="sina", fetched_at=fetched_at)
        refreshed[symbol] = db.get_market_index_coverage(symbol)
    return refreshed


def build_real_market_index_data_by_symbol(snapshot_date: str) -> dict[str, list[dict]]:
    """Load cached real market indices; no proxy fallback."""
    market_data_by_symbol = {
        symbol: db.get_market_index_ohlc(symbol, end_date=snapshot_date[:10])
        for symbol in DEFAULT_INDEX_SYMBOLS
    }
    missing = [
        symbol
        for symbol in REQUIRED_REAL_INDEX_SYMBOLS
        if not market_data_by_symbol.get(symbol)
    ]
    if missing:
        raise RuntimeError(f"MISSING_REAL_MARKET_INDEX_CACHE: {','.join(missing)}")
    return {
        symbol: rows
        for symbol, rows in market_data_by_symbol.items()
        if rows
    }


def run_strategy3_backtest_task(
    task_id: str,
    target_stocks: list[dict],
    config_snapshot: dict,
    payload_snapshot: dict,
    data_snapshot_date: str,
    cancel_event=None,
    running_state: dict | None = None,
) -> None:
    """同步执行策略3本地 DB 回测任务。"""
    started = time.monotonic()
    running_state = running_state if running_state is not None else {}
    stats = running_state.setdefault("stats", {})
    stats["total_stocks"] = len(target_stocks)
    db.update_strategy3_backtest_task(
        task_id,
        total_stocks=len(target_stocks),
        data_snapshot_date=data_snapshot_date,
        data_revision_id=calculate_daily_ohlc_revision(
            data_snapshot_date,
            [stock["code"] for stock in target_stocks],
        ),
    )

    snap_date = data_snapshot_date[:10]
    try:
        market_data_by_symbol = None
        for stock in target_stocks:
            if cancel_event is not None and cancel_event.is_set():
                break
            code = stock["code"]
            name = stock.get("name", "")
            stock_started_at = _now_local()
            stats["current_code"] = code
            stats["current_name"] = name
            db.save_strategy3_backtest_task_stock(
                task_id,
                code,
                name=name,
                status="RUNNING",
                started_at=stock_started_at,
                finished_at=None,
                error_code=None,
                error_detail=None,
            )
            try:
                ohlc = db.get_ohlc(code)
                if snap_date and ohlc:
                    ohlc = [row for row in ohlc if row["date"] <= snap_date]
                if not ohlc:
                    required_days = config_snapshot.get("strategy3", {}).get("minimum_required_days", 180)
                    db.save_strategy3_backtest_task_stock(
                        task_id,
                        code,
                        name=name,
                        status="INSUFFICIENT",
                        error_code="NO_LOCAL_DATA",
                        available_days=0,
                        required_days=required_days,
                        earliest_date="",
                        latest_date="",
                        started_at=stock_started_at,
                        finished_at=_now_local(),
                    )
                    continue

                if market_data_by_symbol is None:
                    refresh_strategy3_market_index_cache(data_snapshot_date)
                    market_data_by_symbol = build_real_market_index_data_by_symbol(data_snapshot_date)

                result = run_strategy3_stock_backtest(
                    code,
                    name,
                    ohlc,
                    config_snapshot,
                    payload_snapshot.get("startDate", ""),
                    payload_snapshot.get("endDate", ""),
                    market_data_by_symbol=market_data_by_symbol,
                    market_data_mode=MARKET_DATA_MODE_REAL_INDEX_CACHE,
                )
                if result.get("insufficient"):
                    insufficient = result["insufficient"]
                    db.save_strategy3_backtest_task_stock(
                        task_id,
                        code,
                        name=name,
                        status="INSUFFICIENT",
                        error_code=insufficient.get("reason_code", "INSUFFICIENT_HISTORY_DATA"),
                        available_days=insufficient.get("available_days", 0),
                        required_days=insufficient.get("required_days", 0),
                        earliest_date=insufficient.get("earliest_date", ""),
                        latest_date=insufficient.get("latest_date", ""),
                        started_at=stock_started_at,
                        finished_at=_now_local(),
                    )
                    continue

                result["started_at"] = stock_started_at
                result["finished_at"] = _now_local()
                db.replace_strategy3_stock_backtest_result(task_id, code, name, result)
            except Exception as exc:
                db.save_strategy3_backtest_task_stock(
                    task_id,
                    code,
                    name=name,
                    status="FAILED",
                    error_code=type(exc).__name__,
                    error_detail=str(exc)[:500],
                    started_at=stock_started_at,
                    finished_at=_now_local(),
                )
                logger.warning("Strategy3 backtest stock %s failed: %s", code, exc)
            finally:
                stats["processed_stocks"] = db.get_conn().execute(
                    "SELECT COUNT(*) FROM strategy3_backtest_task_stocks "
                    "WHERE task_id=? AND status IN ('COMPLETED','INSUFFICIENT','FAILED')",
                    (task_id,),
                ).fetchone()[0]
                stats["opportunities_count"] = db.get_conn().execute(
                    "SELECT COUNT(*) FROM strategy3_backtest_opportunities WHERE task_id=?",
                    (task_id,),
                ).fetchone()[0]

        _finalize_strategy3_backtest_task(
            task_id,
            time.monotonic() - started,
            cancel_event,
            market_data_mode=MARKET_DATA_MODE_REAL_INDEX_CACHE,
        )
    except Exception as exc:
        db.update_strategy3_backtest_task(
            task_id,
            status="failed",
            credibility_status="PHASE1_INCOMPLETE",
            error=str(exc),
            finished_at=_now_local(),
        )
        raise


def _finalize_strategy3_backtest_task(
    task_id: str,
    elapsed: float,
    cancel_event=None,
    *,
    market_data_mode: str = "",
) -> None:
    conn = db.get_conn()
    counts = conn.execute(
        "SELECT "
        "SUM(CASE WHEN status IN ('COMPLETED','INSUFFICIENT','FAILED') THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN status='INSUFFICIENT' THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN status IN ('PENDING','RUNNING') THEN 1 ELSE 0 END), "
        "SUM(evaluation_days), SUM(evaluation_error_days), SUM(raw_signals_count), "
        "MIN(actual_eval_start_date), MAX(actual_eval_end_date), MAX(observation_data_end_date) "
        "FROM strategy3_backtest_task_stocks WHERE task_id=?",
        (task_id,),
    ).fetchone()
    processed, failed, insufficient, unfinished = (value or 0 for value in counts[:4])
    evaluations, evaluation_errors, raw_signals = (value or 0 for value in counts[4:7])
    actual_start, actual_end, observation_end = counts[7:10]
    opportunities = conn.execute(
        "SELECT COUNT(*) FROM strategy3_backtest_opportunities WHERE task_id=?",
        (task_id,),
    ).fetchone()[0]
    stocks_with_opportunities = conn.execute(
        "SELECT COUNT(DISTINCT code) FROM strategy3_backtest_opportunities WHERE task_id=?",
        (task_id,),
    ).fetchone()[0]

    if cancel_event is not None and cancel_event.is_set():
        status = "CANCELED"
    elif unfinished:
        status = "INTERRUPTED"
    elif failed:
        status = "completed_with_errors"
    else:
        status = "completed"

    summary = db.build_strategy3_backtest_summary(task_id)
    summary["marketDataMode"] = summary.get("marketDataMode") or market_data_mode
    summary["dateRange"] = {
        "actual_evaluation_start_date": actual_start,
        "actual_evaluation_end_date": actual_end,
        "observation_data_end_date": observation_end,
    }
    db.update_strategy3_backtest_task(
        task_id,
        status=status,
        credibility_status="TRUSTED_BASELINE" if status == "completed" and evaluation_errors == 0 else "PHASE1_INCOMPLETE",
        processed_stocks=processed,
        stocks_with_opportunities=stocks_with_opportunities,
        opportunities_count=opportunities,
        insufficient_stocks_count=insufficient,
        failed_stocks_count=failed,
        finished_at=_now_local(),
        elapsed_seconds=round(elapsed, 1),
        actual_evaluation_start_date=actual_start,
        actual_evaluation_end_date=actual_end,
        observation_data_end_date=observation_end,
        completed_evaluations=evaluations,
        raw_signals_count=raw_signals,
        evaluation_error_days=evaluation_errors,
        summary_json=json.dumps(summary, ensure_ascii=False),
    )

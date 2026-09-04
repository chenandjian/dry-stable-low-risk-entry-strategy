"""Read-only market breadth reconstruction for research and frontend audit.

Breadth is computed from the current local stock universe. A stock is valid on a
date only when it has bars on that exact market date and the immediately prior
market date. This avoids treating a multi-day suspension gap as a one-day move.
The result is research-only and never feeds a strategy engine.
"""

from __future__ import annotations

from bisect import bisect_right
from datetime import date
import threading

from scanner import db


INDEX_NAMES = {
    "sh000001": "上证指数",
    "sz399001": "深证成指",
    "sz399006": "创业板指",
    "hs300": "沪深300",
}
TRADING_CANDIDATE_TYPES = {"READY_CANDIDATE", "KEY_CANDIDATE", "WATCH_CANDIDATE"}
_CACHE_BUILD_LOCK = threading.Lock()


class MarketBreadthDataChanging(RuntimeError):
    """Raised when OHLC changes while a breadth snapshot is being built."""


def _validate_date(value: str | None, field: str) -> str | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc


def _breadth_state(down_ratio: float) -> str:
    if down_ratio >= 0.90:
        return "EXTREME_DECLINE"
    if down_ratio >= 0.80:
        return "PANIC_DECLINE"
    if down_ratio >= 0.70:
        return "BROAD_DECLINE"
    if down_ratio >= 0.60:
        return "WEAK"
    return "NORMAL"


def _eligible_count(first_dates: list[str], previous_trade_date: str) -> int:
    return bisect_right(first_dates, previous_trade_date)


def _load_first_dates(conn) -> list[str]:
    dates = [
        row[0]
        for row in conn.execute(
            "SELECT first_date FROM daily_ohlc_metadata WHERE first_date IS NOT NULL ORDER BY first_date"
        ).fetchall()
    ]
    if dates:
        return dates
    return sorted(
        row[0]
        for row in conn.execute(
            "SELECT MIN(date) FROM daily_ohlc GROUP BY code HAVING MIN(date) IS NOT NULL"
        ).fetchall()
    )


def _source_revision(conn) -> str:
    metadata = conn.execute(
        """SELECT COUNT(*), COALESCE(SUM(row_count),0), COALESCE(MIN(first_date),''),
                  COALESCE(MAX(latest_date),''), COALESCE(MAX(fetched_at),'')
           FROM daily_ohlc_metadata"""
    ).fetchone()
    stock_pool_count = int(conn.execute("SELECT COUNT(*) FROM stock_pool").fetchone()[0] or 0)
    return ":".join(str(value or "") for value in (*metadata, stock_pool_count))


def _invalidate_stale_cache(conn) -> str:
    revision = _source_revision(conn)
    state = conn.execute(
        "SELECT source_revision FROM market_breadth_cache_state WHERE id=1"
    ).fetchone()
    cached_count = int(conn.execute("SELECT COUNT(*) FROM market_breadth_daily").fetchone()[0] or 0)
    if state is None and cached_count:
        # One-time migration for caches produced before revision tracking existed.
        conn.execute(
            "INSERT INTO market_breadth_cache_state(id, source_revision) VALUES(1, ?)",
            (revision,),
        )
        conn.commit()
    elif state is not None and state[0] != revision:
        with conn:
            conn.execute("DELETE FROM market_breadth_daily")
            conn.execute(
                "UPDATE market_breadth_cache_state SET source_revision=?, updated_at=datetime('now') WHERE id=1",
                (revision,),
            )
    elif state is None:
        conn.execute(
            "INSERT INTO market_breadth_cache_state(id, source_revision) VALUES(1, ?)",
            (revision,),
        )
        conn.commit()
    return revision


def _load_strategy6_signals(conn, start_date: str, end_date: str) -> dict[str, dict]:
    tasks = conn.execute(
        """SELECT id, latest_trade_date, started_at
           FROM scan_tasks
           WHERE strategy_type='STRATEGY_6_STRONG_VCP_TAIL'
             AND LOWER(COALESCE(status, ''))='completed'
             AND latest_trade_date BETWEEN ? AND ?
           ORDER BY started_at DESC, id DESC""",
        (start_date, end_date),
    ).fetchall()
    latest_by_date: dict[str, str] = {}
    for task_id, trade_date, _ in tasks:
        latest_by_date.setdefault(trade_date, task_id)
    if not latest_by_date:
        return {}

    task_ids = list(latest_by_date.values())
    placeholders = ",".join("?" for _ in task_ids)
    rows = conn.execute(
        f"""SELECT task_id, code, name, candidate_type
            FROM strategy6_candidates
            WHERE task_id IN ({placeholders})
              AND candidate_type IN ('READY_CANDIDATE', 'KEY_CANDIDATE', 'WATCH_CANDIDATE')
            ORDER BY total_score DESC, code""",
        task_ids,
    ).fetchall()
    by_task: dict[str, list[dict]] = {task_id: [] for task_id in task_ids}
    for task_id, code, name, candidate_type in rows:
        if candidate_type not in TRADING_CANDIDATE_TYPES:
            continue
        by_task[task_id].append({
            "code": code,
            "name": name or "",
            "candidate_type": candidate_type,
        })

    signals: dict[str, dict] = {}
    for trade_date, task_id in latest_by_date.items():
        stocks = by_task.get(task_id, [])
        signals[trade_date] = {
            "task_id": task_id,
            "total": len(stocks),
            "ready_count": sum(s["candidate_type"] == "READY_CANDIDATE" for s in stocks),
            "key_count": sum(s["candidate_type"] == "KEY_CANDIDATE" for s in stocks),
            "watch_count": sum(s["candidate_type"] == "WATCH_CANDIDATE" for s in stocks),
            "stocks": stocks,
            "source": "RECORDED_COMPLETED_TASK",
        }
    return signals


def _ensure_breadth_cache(conn, calendar: list[tuple[str, str]]) -> dict[str, tuple[int, int, int]]:
    """Build missing breadth days and refresh the latest day from real bars."""
    if not calendar:
        return {}
    dates = [item[0] for item in calendar]
    placeholders = ",".join("?" for _ in dates)
    cached_rows = conn.execute(
        f"SELECT trade_date, up_count, down_count, flat_count FROM market_breadth_daily WHERE trade_date IN ({placeholders})",
        dates,
    ).fetchall()
    cached = {row[0]: (int(row[1]), int(row[2]), int(row[3])) for row in cached_rows}
    # The latest day may still be receiving corrected bars, so it is always rebuilt.
    rebuild_dates = [trade_date for trade_date, _ in calendar if trade_date not in cached]
    if dates[-1] not in rebuild_dates:
        rebuild_dates.append(dates[-1])
    if rebuild_dates:
        pair_map = dict(calendar)
        query_start = min(pair_map[trade_date] for trade_date in rebuild_dates)
        query_end = max(rebuild_dates)
        conn.execute(
            """CREATE TEMP TABLE IF NOT EXISTS temp_market_breadth_calendar (
                   trade_date TEXT PRIMARY KEY,
                   previous_trade_date TEXT NOT NULL
               )"""
        )
        conn.execute("DELETE FROM temp_market_breadth_calendar")
        conn.executemany(
            "INSERT INTO temp_market_breadth_calendar(trade_date, previous_trade_date) VALUES (?, ?)",
            [(trade_date, pair_map[trade_date]) for trade_date in rebuild_dates],
        )
        rebuilt = conn.execute(
            """WITH moves AS (
                    SELECT code, date, close,
                           LAG(date) OVER (PARTITION BY code ORDER BY date) AS previous_date,
                           LAG(close) OVER (PARTITION BY code ORDER BY date) AS previous_close
                    FROM daily_ohlc
                    WHERE date BETWEEN ? AND ?
                )
                SELECT moves.date,
                       SUM(CASE WHEN moves.close > moves.previous_close THEN 1 ELSE 0 END),
                       SUM(CASE WHEN moves.close < moves.previous_close THEN 1 ELSE 0 END),
                       SUM(CASE WHEN moves.close = moves.previous_close THEN 1 ELSE 0 END)
                FROM moves
                JOIN temp_market_breadth_calendar calendar
                  ON calendar.trade_date=moves.date
                 AND calendar.previous_trade_date=moves.previous_date
                GROUP BY moves.date""",
            (query_start, query_end),
        ).fetchall()
        rebuilt_map = {row[0]: (int(row[1] or 0), int(row[2] or 0), int(row[3] or 0)) for row in rebuilt}
        with conn:
            for trade_date in rebuild_dates:
                if trade_date not in rebuilt_map:
                    cached.pop(trade_date, None)
                    conn.execute("DELETE FROM market_breadth_daily WHERE trade_date=?", (trade_date,))
                    continue
                up_count, down_count, flat_count = rebuilt_map[trade_date]
                conn.execute(
                    """INSERT INTO market_breadth_daily
                           (trade_date, previous_trade_date, up_count, down_count, flat_count, calculated_at)
                       VALUES (?, ?, ?, ?, ?, datetime('now'))
                       ON CONFLICT(trade_date) DO UPDATE SET
                           previous_trade_date=excluded.previous_trade_date,
                           up_count=excluded.up_count,
                           down_count=excluded.down_count,
                           flat_count=excluded.flat_count,
                           calculated_at=datetime('now')""",
                    (trade_date, pair_map[trade_date], up_count, down_count, flat_count),
                )
                cached[trade_date] = (up_count, down_count, flat_count)
    return cached


def build_market_breadth_history(
    *, start_date: str | None = None, end_date: str | None = None, limit: int = 1500,
) -> dict:
    """Build auditable breadth/index history from local real bars."""
    start_date = _validate_date(start_date, "start_date")
    end_date = _validate_date(end_date, "end_date")
    if start_date and end_date and start_date > end_date:
        raise ValueError("start_date must not be after end_date")
    limit = max(1, min(int(limit), 2000))

    conn = db.get_conn()
    bounds = conn.execute(
        """SELECT MIN(date), MAX(date) FROM market_index_ohlc
           WHERE symbol IN ('sh000001','sz399001','sz399006','hs300')
           GROUP BY symbol"""
    ).fetchall()
    if len(bounds) < 4:
        return {
            "meta": _meta(None, None, 0),
            "summary": None,
            "rows": [],
        }
    common_start = max(row[0] for row in bounds)
    common_end = min(row[1] for row in bounds)
    effective_start = max(start_date or common_start, common_start)
    effective_end = min(end_date or common_end, common_end)
    if effective_start > effective_end:
        return {"meta": _meta(common_start, common_end, 0), "summary": None, "rows": []}

    calendar_dates = [
        row[0]
        for row in conn.execute(
            "SELECT date FROM market_index_ohlc WHERE symbol='sh000001' AND date<=? ORDER BY date",
            (effective_end,),
        ).fetchall()
    ]
    calendar = [
        (calendar_dates[index], calendar_dates[index - 1])
        for index in range(1, len(calendar_dates))
        if calendar_dates[index] >= effective_start
    ][-limit:]
    if not calendar:
        return {"meta": _meta(common_start, common_end, 0), "summary": None, "rows": []}

    with _CACHE_BUILD_LOCK:
        revision = _invalidate_stale_cache(conn)
        cached = _ensure_breadth_cache(conn, calendar)
        # A concurrent data refresh changes the revision and forces a clean
        # rebuild on the next request instead of blessing a mixed snapshot.
        if _source_revision(conn) != revision:
            conn.execute("DELETE FROM market_breadth_daily")
            conn.execute("DELETE FROM market_breadth_cache_state WHERE id=1")
            conn.commit()
            raise MarketBreadthDataChanging("行情数据正在更新，请稍后重新加载市场宽度")
    aggregates = [
        (trade_date, previous_trade_date, *cached[trade_date])
        for trade_date, previous_trade_date in calendar
        if trade_date in cached
    ]
    if not aggregates:
        return {"meta": _meta(common_start, common_end, 0), "summary": None, "rows": []}

    first_date = aggregates[0][1]
    last_date = aggregates[-1][0]
    index_rows = conn.execute(
        """SELECT symbol, date, close, source
           FROM market_index_ohlc
           WHERE symbol IN ('sh000001','sz399001','sz399006','hs300')
             AND date BETWEEN ? AND ?
           ORDER BY symbol, date""",
        (first_date, last_date),
    ).fetchall()
    index_map = {(symbol, trade_date): (float(close), source or "") for symbol, trade_date, close, source in index_rows}
    first_dates = _load_first_dates(conn)
    stock_pool_count = int(conn.execute("SELECT COUNT(*) FROM stock_pool").fetchone()[0] or 0)
    signals = _load_strategy6_signals(conn, aggregates[0][0], last_date)

    result_rows = []
    for trade_date, previous_trade_date, up_count, down_count, flat_count in aggregates:
        up_count = int(up_count or 0)
        down_count = int(down_count or 0)
        flat_count = int(flat_count or 0)
        valid_count = up_count + down_count + flat_count
        eligible_count = _eligible_count(first_dates, previous_trade_date)
        unavailable_count = max(eligible_count - valid_count, 0)
        down_ratio = down_count / valid_count if valid_count else 0.0
        breadth = (up_count - down_count) / valid_count if valid_count else 0.0
        indexes = {}
        for symbol, name in INDEX_NAMES.items():
            current = index_map.get((symbol, trade_date))
            previous = index_map.get((symbol, previous_trade_date))
            close = current[0] if current else None
            daily_return = (
                close / previous[0] - 1.0
                if close is not None and previous and previous[0] > 0
                else None
            )
            indexes[symbol] = {
                "symbol": symbol,
                "name": name,
                "close": close,
                "daily_return": daily_return,
                "source": current[1] if current else "",
            }
        coverage_rate = valid_count / eligible_count if eligible_count else 0.0
        data_quality = "RELIABLE" if coverage_rate >= 0.90 and valid_count >= 1000 else "LOW_COVERAGE"
        result_rows.append({
            "date": trade_date,
            "previous_trade_date": previous_trade_date,
            "up_count": up_count,
            "down_count": down_count,
            "flat_count": flat_count,
            "valid_count": valid_count,
            "eligible_count": eligible_count,
            "unavailable_count": unavailable_count,
            "coverage_rate": coverage_rate,
            "data_quality": data_quality,
            "up_ratio": up_count / valid_count if valid_count else 0.0,
            "down_ratio": down_ratio,
            "advance_decline_ratio": up_count / down_count if down_count else None,
            "net_advancers": up_count - down_count,
            "breadth": breadth,
            "breadth_state": _breadth_state(down_ratio),
            "indexes": indexes,
            "strategy6_signal": signals.get(trade_date),
        })

    meta = _meta(common_start, common_end, len(result_rows))
    reliable_rows = [row for row in result_rows if row["data_quality"] == "RELIABLE"]
    meta["reliable_start_date"] = reliable_rows[0]["date"] if reliable_rows else None
    meta["reliable_row_count"] = len(reliable_rows)
    meta["stock_pool_count"] = stock_pool_count
    meta["tracked_history_count"] = len(first_dates)
    meta["untracked_stock_count"] = max(stock_pool_count - len(first_dates), 0)
    return {
        "meta": meta,
        "summary": result_rows[-1],
        "rows": result_rows,
    }


def _meta(common_start: str | None, common_end: str | None, row_count: int) -> dict:
    return {
        "data_mode": "CURRENT_UNIVERSE_RECONSTRUCTION",
        "price_basis": "FORWARD_ADJUSTED",
        "index_start_date": common_start,
        "index_end_date": common_end,
        "row_count": row_count,
        "affects_strategy6": False,
        "signal_source": "RECORDED_COMPLETED_TASK_ONLY",
        "warning": "当前股票池历史重建，存在幸存者偏差；策略6信号仅来自实际已完成任务，不代表每日完整回测。",
    }

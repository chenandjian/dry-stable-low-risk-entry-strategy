"""Read-only local K-line view; never initializes scan state."""
import json
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

from .calendar import freshness, target_session
from .instruments import provider_symbol


def read_local_history(path: Path, symbol: str) -> dict | None:
    if not path.is_file():
        return None
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=5)) as conn:
        stored = conn.execute(
            "SELECT metadata, rows_json FROM us_stock_history WHERE symbol=? AND adjustment='forward'",
            (symbol,),
        ).fetchone()
    return {'metadata': json.loads(stored[0]), 'rows': json.loads(stored[1])} if stored else None


def history_page(path: Path, code: str, *, start_date: str = '', end_date: str = '',
                 page: int = 1, page_size: int = 50) -> dict:
    symbol = provider_symbol(code)
    for value in (start_date, end_date):
        if value and date.fromisoformat(value).isoformat() != value:
            raise ValueError('dates must use YYYY-MM-DD')
    if start_date and end_date and start_date > end_date:
        raise ValueError('start_date must not be after end_date')
    if not 1 <= page <= 50000 or not 1 <= page_size <= 100:
        raise ValueError('invalid page or page size')

    history = read_local_history(path, symbol)
    metadata, rows = (history['metadata'], history['rows']) if history else ({}, [])
    rows.sort(key=lambda row: row['date'], reverse=True)
    context = target_session()
    target = context['target_trade_date']
    latest = rows[0]['date'] if rows else None
    covers_target = any(row['date'] == target for row in rows)
    filtered = [row for row in rows
                if (not start_date or row['date'] >= start_date) and (not end_date or row['date'] <= end_date)]
    offset = (page - 1) * page_size
    return {
        'symbol': symbol, 'metadata': metadata, 'rows': filtered[offset:offset + page_size],
        'page': page, 'page_size': page_size, 'total': len(filtered),
        'summary': {
            'row_count': len(rows), 'first_kline_date': rows[-1]['date'] if rows else None,
            'latest_kline_date': latest, 'target_trade_date': target,
            'covers_target': covers_target,
            'is_fresh': covers_target and freshness(latest, metadata.get('fetched_at'), context),
        },
    }

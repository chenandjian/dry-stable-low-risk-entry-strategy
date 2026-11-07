"""Offline NYSE/Nasdaq regular-session calendar, with explicit confirmation lag."""
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib.metadata import version
from zoneinfo import ZoneInfo


@lru_cache(maxsize=8)
def _calendar(year):
    import exchange_calendars as xc
    return xc.get_calendar('XNYS', start=f'{year - 1}-01-01', end=f'{year + 1}-12-31')


def target_session(now: datetime | None = None, *, confirmation_minutes: int = 10) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('US clock must be timezone-aware')
    if not 0 <= confirmation_minutes <= 1440:
        raise ValueError('invalid confirmation delay')
    local = now.astimezone(ZoneInfo('America/New_York'))
    cal = _calendar(local.year)
    sessions = cal.sessions_in_range((local.date() - timedelta(days=20)).isoformat(), local.date().isoformat())
    for session in reversed(sessions):
        close = cal.session_close(session).to_pydatetime()
        if close + timedelta(minutes=confirmation_minutes) <= now:
            return {'target_trade_date': session.strftime('%Y-%m-%d'),
                    'target_close_at': close.isoformat(), 'timezone': 'America/New_York',
                    'calendar': 'XNYS', 'calendar_version': version('exchange-calendars'),
                    'confirmation_minutes': confirmation_minutes,
                    'publication_status': 'PROVIDER_PUBLICATION_TIME_UNVERIFIED'}
    raise ValueError('calendar has no completed session within lookback')


def freshness(latest_date: str, fetched_at: str, context: dict) -> bool:
    try:
        fetched = datetime.fromisoformat(fetched_at)
        close = datetime.fromisoformat(context['target_close_at'])
        return bool(fetched.tzinfo and latest_date >= context['target_trade_date'] and fetched >= close)
    except (TypeError, ValueError):
        return False


def evaluation_context(now: datetime, as_of: str | None = None) -> dict:
    context = target_session(now)
    context['live_target_trade_date'] = context['target_trade_date']
    context['historical_evaluation'] = False
    if as_of:
        from datetime import date
        day = date.fromisoformat(as_of)
        cal = _calendar(day.year)
        if day.isoformat() != as_of or as_of > context['target_trade_date'] or not cal.is_session(as_of):
            raise ValueError('as_of must be a completed US trading session')
        context.update(target_trade_date=as_of, target_close_at=cal.session_close(as_of).isoformat(),
                       historical_evaluation=as_of < context['live_target_trade_date'])
    return context

"""Opt-in real local-data verification; never fetch or modify market data."""
import os
import sqlite3
from pathlib import Path

import pytest

from strategy6.selling_exhaustion import evaluate_selling_exhaustion


DB = os.environ.get('SELLING_EXHAUSTION_REAL_DB')
pytestmark = pytest.mark.skipif(not DB, reason='Set SELLING_EXHAUSTION_REAL_DB for local real-data verification')


def evaluate(code, end):
    with sqlite3.connect(Path(DB).resolve().as_uri() + '?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute(
            'SELECT * FROM daily_ohlc WHERE code=? AND date<=? ORDER BY date', (code, end))]
    assert rows and rows[-1]['date'] == end
    return evaluate_selling_exhaustion(rows)


@pytest.mark.parametrize('day', ['2026-09-14', '2026-09-15'])
def test_000811_still_near_bottom(day):
    result = evaluate('000811', day)
    assert result['matched']
    assert result['status'] == 'STRONG'
    assert result['phase'] == 'PULLBACK'
    assert result['phaseMetrics']['floorDistanceAtr'] < .5


@pytest.mark.parametrize('code', ['002774', '688112', '000811', '001339', '688052'])
def test_september_18_is_rebound_not_current_exhaustion(code):
    result = evaluate(code, '2026-09-18')
    assert result['score'] >= 90
    assert not result['matched']
    assert result['status'] == 'REBOUNDED'
    assert result['confirmationDays'] == 0

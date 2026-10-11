from datetime import date, timedelta

import pytest

from strategy6 import rising_support as detector


def bars(closes):
    return [dict(date=str(date(2026, 1, 1) + timedelta(days=i)),
                 open=p, close=p, high=p + .2, low=p - .2)
            for i, p in enumerate(closes)]


def test_confirmed_support_rises_without_modifying_rows(monkeypatch):
    monkeypatch.setattr(detector, '_wilder_atr_series', lambda rows, period: [1.] * len(rows))
    rows = bars([100.] * 60 + [110, 108, 105, 101, 103, 106, 110, 109, 106, 104, 106, 109])
    before = [dict(r) for r in rows]
    result = detector.evaluate_rising_support(rows)
    assert result['matched'] is True
    assert result['supportPrice'] == pytest.approx(103.8)
    assert result['zones'][-1]['confirmedDate'] > result['zones'][-1]['lowDate']
    assert rows == before
    early = detector.evaluate_rising_support(rows[:-2])
    assert early['matched'] is False
    assert early['pendingLow']['price'] == pytest.approx(103.8)


def test_lower_support_and_later_break_are_rejected(monkeypatch):
    monkeypatch.setattr(detector, '_wilder_atr_series', lambda rows, period: [1.] * len(rows))
    rows = bars([100.] * 60 + [110, 108, 105, 101, 103, 106, 110, 108, 105, 98, 100, 103])
    assert detector.evaluate_rising_support(rows)['matched'] is False
    rising = bars([100.] * 60 + [110, 108, 105, 101, 103, 106, 110, 109, 106, 104, 106, 109, 102])
    assert detector.evaluate_rising_support(rising)['reason'] == 'SUPPORT_BROKEN'


def test_cluster_preserves_real_floor_and_fixed_width():
    rows = bars([100, 99.2, 98.4, 97.6])
    pivots = [dict(index=i, date=r['date'], low=r['low'], confirmedDate=r['date'], atr=2.)
              for i, r in enumerate(rows)]
    zones = detector._merge_zones(rows, pivots)
    assert len(zones) > 1
    assert zones[0]['low'] == pytest.approx(99.)
    assert detector._check_chain(rows, zones, 2)['matched'] is False


def test_merge_uses_all_intervening_lows():
    rows = bars([100, 98.9, 100.1])
    pivots = [dict(index=i, date=rows[i]['date'], low=rows[i]['low'],
                   confirmedDate=rows[i]['date'], atr=4.) for i in [0, 2]]
    zone = detector._merge_zones(rows, pivots)[0]
    assert zone['low'] == pytest.approx(98.7)
    assert zone['lowDate'] == rows[1]['date']


def test_insufficient_invalid_and_duplicate_dates_are_unknown():
    assert detector.evaluate_rising_support([])['matched'] is None
    rows = bars([100.] * 60)
    rows[-1]['low'] = float('nan')
    assert detector.evaluate_rising_support(rows)['status'] == 'DATA_INVALID'
    rows = bars([100.] * 60)
    rows[-1]['date'] = rows[-2]['date']
    assert detector.evaluate_rising_support(rows)['matched'] is None


def test_flat_prices_do_not_create_supports():
    assert detector.evaluate_rising_support(bars([100.] * 80))['matched'] is False


def test_zone_tolerance_does_not_roll_down_and_equality_is_allowed():
    rows = bars([100, 102, 101.1])
    zones = [dict(low=value, lastIndex=i) for i, value in enumerate([100., 102., 100.9])]
    assert detector._check_chain(rows, zones, 3)['reason'] == 'LOWER_SUPPORT'
    # A wick exactly on the tolerance boundary is allowed only with a close reclaim.
    rows = bars([100, 102, 102])
    rows[-1]['low'] = 102 * .99
    assert detector._check_chain(rows, zones[:2], 2)['matched'] is True
    rows[-1]['close'] = 101.9
    assert detector._check_chain(rows, zones[:2], 2)['reason'] == 'SUPPORT_BROKEN'

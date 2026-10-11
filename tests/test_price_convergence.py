from datetime import date, timedelta

import pytest

from strategy6 import price_convergence as detector


def rows(count=60):
    return [dict(date=str(date(2026, 1, 1) + timedelta(days=i)),
                 open=110., close=110., low=109., high=111.) for i in range(count)]


def zones(data):
    lows = [dict(firstIndex=i, lastIndex=i, lowDate=data[i]['date'], low=p)
            for i, p in [(20, 100.), (40, 105.)]]
    highs = [dict(firstIndex=i, lastIndex=i, highDate=data[i]['date'], high=p)
             for i, p in [(30, 120.), (50, 115.)]]
    return lows, highs


def test_alternating_rising_support_and_lower_pressure_contract():
    data = rows(); lows, highs = zones(data)
    result = detector._evaluate_pair(data, lows, highs)
    assert result['reason'] == 'MATCHED'
    assert result['contractionPct'] == pytest.approx(50.)
    assert result['supportPrice'] == 105.
    assert result['pressurePrice'] == 115.


def test_separate_phases_cannot_be_spliced():
    data = rows(); lows, highs = zones(data)
    lows[-1].update(firstIndex=25, lastIndex=25, lowDate=data[25]['date'])
    assert detector._evaluate_pair(data, lows, highs)['reason'] == 'TIME_NOT_PAIRED'


def test_wick_above_tolerance_is_not_a_confirmed_breakout_and_does_not_auto_recover():
    data = rows(); lows, highs = zones(data)
    data[55]['high'] = 117.
    result = detector._evaluate_pair(data, lows, highs)
    assert result['reason'] == 'UPPER_BREACH'
    assert result['breachType'] == 'WICK'
    assert result['breachDate'] == data[55]['date']
    data[55]['high'] = 115.
    data[55]['close'] = 115.1
    data[55]['high'] = 115.2
    assert detector._evaluate_pair(data, lows, highs)['breachType'] == 'CLOSE'


def test_pressure_tolerance_cannot_roll_up():
    highs = [dict(high=p) for p in [120., 118., 119.3]]
    assert detector._pressure_shape(highs) is None
    assert detector._pressure_shape([dict(high=p) for p in [120., 119.4]]) is None


def test_unknown_data_and_input_immutability():
    assert detector.evaluate_price_convergence([])['matched'] is None
    data = rows(); before = [dict(r) for r in data]
    result = detector.evaluate_price_convergence(data)
    assert result['matched'] is False
    assert data == before
    data[-1]['low'] = float('nan')
    assert detector.evaluate_price_convergence(data)['status'] == 'DATA_INVALID'


def test_support_break_and_crossed_boundaries_are_rejected():
    data = rows(); lows, highs = zones(data)
    data[55]['low'] = 103.
    assert detector._evaluate_pair(data, lows, highs)['reason'] == 'SUPPORT_BROKEN'
    data = rows()
    highs[-1]['high'] = 104.
    assert detector._evaluate_pair(data, lows, highs)['reason'] == 'NO_RANGE_CONTRACTION'


def test_symmetric_high_confirmation_is_causal_and_keeps_real_maximum(monkeypatch):
    from strategy6 import rising_support
    monkeypatch.setattr(rising_support, '_wilder_atr_series', lambda bars, period: [1.] * len(bars))
    data = rows(80)
    for i, p in enumerate([105, 110, 115, 119, 117, 114], start=74):
        data[i].update(open=p, close=p, low=p-.2, high=p+.2)
    early = detector.evaluate_price_convergence(data[:-2])
    complete = detector.evaluate_price_convergence(data)
    assert early['highZones'] == []
    assert complete['highZones'][-1]['high'] == pytest.approx(119.2)
    assert complete['highZones'][-1]['confirmedDate'] == data[-1]['date']

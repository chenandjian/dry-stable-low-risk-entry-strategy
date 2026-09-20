from datetime import date, timedelta

import pytest

from strategy6.selling_exhaustion import evaluate_selling_exhaustion


def bars():
    rows = []
    for i in range(80):
        close = 100 if i % 2 == 0 else 99
        rows.append(dict(date=str(date(2025, 1, 1) + timedelta(days=i)),
                         open=100, high=102, low=98, close=close, volume=1000))
    for i, row in enumerate(rows[-5:]):
        row.update(open=100, high=101, low=99, close=100.2 if i % 2 == 0 else 100,
                   volume=400)
    return rows


def test_confirms_with_independent_score_and_streak():
    result = evaluate_selling_exhaustion(bars())
    assert result['status'] == 'STRONG'
    assert result['matched'] is True
    assert 0 <= result['score'] <= 100
    assert result['confirmationDays'] >= 1
    assert result['metrics']['recentDownDays5'] == 2


def test_ultra_requires_higher_close_position():
    rows = bars()
    for row in rows[-5:]:
        row['high'] = 100.5
    assert evaluate_selling_exhaustion(rows)['status'] == 'ULTRA'


@pytest.mark.parametrize('field,value', [('volume', 0), ('close', float('nan')), ('low', 103)])
def test_invalid_latest_data_not_zero_score(field, value):
    rows = bars()
    rows[-1][field] = value
    result = evaluate_selling_exhaustion(rows)
    assert result['status'] == 'DATA_INVALID'
    assert result['score'] is None
    assert not result['matched']


def test_insufficient_history_and_down_samples():
    assert evaluate_selling_exhaustion(bars()[:59])['status'] == 'DATA_INSUFFICIENT'
    rows = bars()
    for i, row in enumerate(rows[-5:]):
        row['close'] = 100 + i * .1
    assert evaluate_selling_exhaustion(rows)['status'] == 'SAMPLE_INSUFFICIENT'


def test_high_score_cannot_override_repeated_new_lows():
    rows = bars()
    for i, row in enumerate(rows[-5:]):
        row['low'] = 97.99 - i * .01
    result = evaluate_selling_exhaustion(rows)
    assert result['score'] >= 70
    assert not result['matched']
    assert result['metrics']['newLowCount5'] == 5
    assert any('新低次数' in reason for reason in result['failReasons'])


def test_equal_lows_are_not_new_lows():
    rows = bars()
    for row in rows[-5:]:
        row['low'] = 98
    assert evaluate_selling_exhaustion(rows)['metrics']['newLowCount5'] == 0


def test_configuration_and_flat_bar_fail_closed():
    assert evaluate_selling_exhaustion(bars(), {'normal': [-1, 0, 0, 0]})['status'] == 'CONFIG_INVALID'
    rows = bars()
    rows[-1].update(open=100, high=100, low=100, close=100)
    assert evaluate_selling_exhaustion(rows)['status'] == 'DATA_INVALID'


def test_streak_equals_historical_prefix_confirmations():
    rows = bars()
    expected = 0
    for end in range(len(rows), 59, -1):
        if not evaluate_selling_exhaustion(rows[:end])['matched']:
            break
        expected += 1
    assert evaluate_selling_exhaustion(rows)['confirmationDays'] == expected


def test_wilder_atr_ratios_and_score_are_reproducible():
    result = evaluate_selling_exhaustion(bars())
    metrics = result['metrics']
    # All prior ranges are 4; the last five ranges are 2 without a gap.
    expected_atr = 4
    for _ in range(5):
        expected_atr = (13 * expected_atr + 2) / 14
    assert metrics['atr14'] == pytest.approx(expected_atr)
    assert metrics['lowShiftAtr'] == pytest.approx(1 / expected_atr)
    assert metrics['downVolumeDecay'] == pytest.approx(.4)
    assert metrics['downMoveDecay'] == pytest.approx((1 - 100 / 100.2) / .01)
    assert metrics['closePositionMean5'] == pytest.approx(.56)
    assert result['score'] == 94  # 30 volume + 28 low + 25 move + 11 close


def test_normal_and_strict_configuration_leave_score_independent():
    rows = bars()
    for row in rows[-5:]:
        row['volume'] = 750
    normal = evaluate_selling_exhaustion(rows)
    assert normal['status'] == 'NORMAL'
    strict = evaluate_selling_exhaustion(rows, {'normal': [.7, -.3, .8, .45]})
    assert strict['status'] == 'NOT_CONFIRMED'
    assert strict['score'] == normal['score']


def test_large_single_break_and_unsorted_dates_are_rejected():
    rows = bars()
    rows[-1]['low'] = 90
    result = evaluate_selling_exhaustion(rows)
    assert result['metrics']['newLowCount5'] == 1
    assert result['metrics']['newLowDepthAtr'] > .3
    assert not result['matched']
    rows[-1]['date'] = rows[-2]['date']
    assert evaluate_selling_exhaustion(rows)['status'] == 'DATA_INVALID'

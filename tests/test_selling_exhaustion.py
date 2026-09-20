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


def pullback_bars():
    rows = bars()
    for i in range(60, 75):
        price = 108 - (i-60) * .6
        rows[i].update(open=price+.2, high=price+1, low=price-1, close=price)
    for i, row in enumerate(rows[-5:]):
        price = 99.3 if i % 2 == 0 else 99.1
        row.update(open=price, high=99.8, low=98.7, close=price, volume=400)
    return rows


def test_confirms_with_independent_score_and_streak():
    result = evaluate_selling_exhaustion(pullback_bars())
    assert result['status'] in ('NORMAL', 'STRONG', 'ULTRA')
    assert result['matched'] is True
    assert 0 <= result['score'] <= 100
    assert result['confirmationDays'] >= 1
    assert result['metrics']['recentDownDays5'] == 3


def test_ultra_requires_higher_close_position():
    rows = pullback_bars()
    for row in rows[-5:]:
        row['high'] = 99.4
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
    rows = pullback_bars()
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
    rows = pullback_bars()
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


def test_high_score_without_pullback_is_not_exhaustion():
    result = evaluate_selling_exhaustion(bars())
    assert result['score'] == 94
    assert not result['matched']
    assert result['phase'] == 'NO_PULLBACK'


def test_rebound_retains_floor_when_it_leaves_five_day_window():
    rows = pullback_bars()
    initial = evaluate_selling_exhaustion(rows)
    assert initial['matched']
    for i in range(8):
        price = 102 + i
        rows.append(dict(date=str(date(2025, 1, 1)+timedelta(days=len(rows))),
                         open=price-.1, close=price, high=price+.5, low=price-.5, volume=1000))
    result = evaluate_selling_exhaustion(rows)
    assert result['status'] == 'REBOUNDED'
    assert result['phaseMetrics']['floorPrice'] == initial['phaseMetrics']['floorPrice']
    assert not result['matched']
    assert result['confirmationDays'] == 0


def test_config_validates_phase_parameters():
    for config in [{'phase_max_floor_distance_atr': -1}, {'phase_lookback': 1},
                   {'phase_max_rise_3_atr': float('nan')}]:
        assert evaluate_selling_exhaustion(bars(), config)['status'] == 'CONFIG_INVALID'


def test_one_small_down_day_is_not_enough_even_with_high_score():
    rows = pullback_bars()
    for row, price in zip(rows[-5:], [99.8, 99.7, 99.71, 99.72, 99.73]):
        row.update(open=price, close=price, high=100, low=99.2)
    result = evaluate_selling_exhaustion(rows)
    assert result['metrics']['recentDownDays5'] == 1
    assert result['score'] is not None
    assert not result['matched']


def test_phase_prefixes_do_not_depend_on_future_bars():
    from strategy6.selling_exhaustion import _config, _phases
    rows = pullback_bars()
    atrs = [4] * len(rows)
    full = _phases(rows, atrs, _config(None))
    for end in range(60, len(rows)+1):
        assert _phases(rows[:end], atrs[:end], _config(None))[-1] == full[end-1]


def test_new_pullback_can_reset_anchor_but_window_roll_cannot():
    rows = pullback_bars()
    original = evaluate_selling_exhaustion(rows)
    for price in [103, 105, 108, 111, 109, 106, 104]:
        rows.append(dict(date=str(date(2025, 1, 1)+timedelta(days=len(rows))),
                         open=price, high=price+.3, low=price-.3, close=price, volume=1000))
    result = evaluate_selling_exhaustion(rows)
    assert result['phase'] == 'PULLBACK'
    assert result['phaseMetrics']['pullbackStartDate'] > original['phaseMetrics']['pullbackStartDate']
    assert result['phaseMetrics']['floorPrice'] > original['phaseMetrics']['floorPrice']


def test_prior_break_is_not_current_break():
    rows = pullback_bars()
    rows[-5]['low'] = 97
    result = evaluate_selling_exhaustion(rows)
    assert result['metrics']['newLowDepthAtr'] > .3
    assert result['metrics']['newLowDepthAtr3'] == 0
    assert not any('最近3日最大刺破' in reason for reason in result['failReasons'])


def test_old_large_atr_does_not_widen_current_bottom_zone():
    from strategy6.selling_exhaustion import _config, _phases
    rows = pullback_bars()
    rows[-1].update(open=100.4, close=100.4, high=100.6)
    atrs = [4] * len(rows)
    atrs[-2] = 1
    result = _phases(rows, atrs, _config(None))[-1]
    assert result['phase'] == 'REBOUNDED'
    assert result['phaseMetrics']['positionAtr'] == 1


def test_retest_can_reenter_without_raising_original_floor():
    from strategy6.selling_exhaustion import _config, _phases
    rows = pullback_bars()
    rows[-1].update(open=100.4, close=100.4, high=100.6)
    for price in (100.1, 99.5):
        rows.append(dict(date=str(date(2025, 1, 1)+timedelta(days=len(rows))),
                         open=price, close=price, high=price+.2, low=price-.2, volume=400))
    atrs = [4] * len(rows)
    atrs[-4:] = [1]*4
    phases = _phases(rows, atrs, _config(None))
    assert phases[-3]['phase'] == 'REBOUNDED'
    assert phases[-1]['phase'] == 'PULLBACK'
    assert phases[-1]['phaseMetrics']['floorPrice'] == phases[-3]['phaseMetrics']['floorPrice']


def test_large_daily_bounce_is_excluded_even_when_three_day_return_is_small():
    from strategy6.selling_exhaustion import _config, _phases
    rows = pullback_bars()
    rows[-2].update(open=97.5, close=97.5, low=97.4, high=97.8)
    rows[-1].update(open=97.7, close=99.7, low=97.6, high=99.8)
    phase = _phases(rows, [4]*len(rows), _config(None))[-1]
    assert phase['phaseMetrics']['rise3Atr'] <= .5
    assert phase['phaseMetrics']['rise1Atr'] > .5
    assert phase['phase'] == 'REBOUNDED'

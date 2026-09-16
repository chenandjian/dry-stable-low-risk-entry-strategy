from datetime import date, timedelta
import math
import pytest
from strategy6.ema_compression import evaluate_ema_compression


def bars(values):
    return [{"date": str(date(2024, 1, 1) + timedelta(days=i)), "close": value}
            for i, value in enumerate(values)]


def test_tight_tail_is_confirmed_after_variable_history():
    rows = bars([100 + 8 * math.sin(i / 7) for i in range(250)] + [100] * 90)
    result = evaluate_ema_compression(rows)
    assert result['ultraExtreme']
    assert result['score'] >= 90
    assert result['metrics']['historicalPercentile'] <= 10
    assert result['metrics']['compressionStreak'] >= 5


def test_constant_history_is_not_historically_rare_and_zero_ratio_is_missing():
    result = evaluate_ema_compression(bars([100] * 300))
    assert result['metrics']['historicalPercentile'] == 100
    assert result['metrics']['compressionChange'] is None
    assert not result['extreme']
    assert result['score'] is not None


@pytest.mark.parametrize('values,status', [([100]*224, 'DATA_INSUFFICIENT'), ([100]*225+[float('nan')], 'DATA_INVALID')])
def test_missing_or_invalid_data_is_not_zero_score(values, status):
    result = evaluate_ema_compression(bars(values))
    assert result['status'] == status
    assert result['score'] is None


def test_single_day_release_and_fast_trend_are_not_confirmed():
    history = [100 + 8 * math.sin(i / 7) for i in range(250)] + [100] * 90
    assert not evaluate_ema_compression(bars(history + [115]))['extreme']
    assert not evaluate_ema_compression(bars([100 * .99**i for i in range(300)]))['extreme']


def test_configuration_changes_diagnosis_only():
    rows = bars([100 + 8 * math.sin(i / 7) for i in range(250)] + [100] * 90)
    result = evaluate_ema_compression(rows, {'extreme': [0]*7})
    assert not result['extreme']
    assert result['score'] == evaluate_ema_compression(rows)['score']


def test_invalid_configuration_cannot_silently_confirm_every_stock():
    assert evaluate_ema_compression(bars([100]*300), {'extreme': []})['status'] == 'CONFIG_INVALID'

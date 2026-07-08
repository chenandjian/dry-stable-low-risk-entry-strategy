from strategy5.indicators import calculate_indicators
from strategy5.volume_dry import evaluate_strategy5_volume_dry
from strategy5.validation import resolve_strategy5_config
from tests.test_strategy5_core_rules import _row


def build_healthy_dry_data(length=320):
    data = []
    for i in range(length):
        close = 10 + i * 0.02
        data.append(_row(i, close=close, volume=2_000_000, turnover=40))

    base = data[-21]["close"]
    for j in range(20):
        progress = (j + 1) / 20
        close = base * (1 + 0.28 * progress)
        data[-20 + j].update({
            "open": round(close * 0.995, 4),
            "high": round(close * 1.012, 4),
            "low": round(close * 0.99, 4),
            "close": round(close, 4),
            "volume": 2_400_000,
            "turnover": 45,
        })

    support = data[-6]["close"]
    dry_volumes = [1_450_000, 1_280_000, 1_100_000, 920_000, 780_000]
    for j, volume in enumerate(dry_volumes):
        idx = -5 + j
        close = support * (1 + 0.003 * j)
        data[idx].update({
            "open": round(close * (1.002 if j in {1, 3} else 0.998), 4),
            "high": round(close * 1.012, 4),
            "low": round(close * 0.992, 4),
            "close": round(close, 4),
            "volume": volume,
            "turnover": 30,
        })
    return data


def build_big_down_volume_data():
    data = build_healthy_dry_data()
    data[-1]["open"] = data[-2]["close"]
    data[-1]["close"] = round(data[-2]["close"] * 0.94, 4)
    data[-1]["high"] = round(data[-2]["close"] * 1.005, 4)
    data[-1]["low"] = round(data[-1]["close"] * 0.99, 4)
    data[-1]["volume"] = 4_500_000
    return data


def build_shrinking_bear_drift_data():
    data = build_healthy_dry_data()
    start = data[-6]["close"]
    volumes = [1_300_000, 1_100_000, 950_000, 820_000, 700_000]
    for j, volume in enumerate(volumes):
        close = start * (1 - 0.015 * (j + 1))
        data[-5 + j].update({
            "open": round(close * 1.006, 4),
            "high": round(close * 1.008, 4),
            "low": round(close * 0.99, 4),
            "close": round(close, 4),
            "volume": volume,
            "turnover": 28,
        })
    return data


def test_healthy_sprint_pullback_volume_dry_scores_high():
    cfg = resolve_strategy5_config({})
    ind = calculate_indicators(build_healthy_dry_data(), cfg)

    result = evaluate_strategy5_volume_dry(ind, cfg)

    assert result.volume_dry_score >= 14
    assert result.volume_dry_level in {"HEALTHY_DRY", "EXTREME_DRY"}
    assert "volume:dry" in result.volume_dry_reasons
    assert "volume:down_volume_exhausted" in result.volume_dry_reasons
    assert result.volume_dry_rejects == []


def test_big_down_volume_is_bad_dry_even_when_prior_volume_shrank():
    cfg = resolve_strategy5_config({})
    ind = calculate_indicators(build_big_down_volume_data(), cfg)

    result = evaluate_strategy5_volume_dry(ind, cfg)

    assert result.volume_dry_level == "BAD_DRY"
    assert "DRY_BIG_DOWN_VOLUME" in result.volume_dry_rejects


def test_shrinking_bear_drift_is_rejected_as_bad_dry():
    cfg = resolve_strategy5_config({})
    ind = calculate_indicators(build_shrinking_bear_drift_data(), cfg)

    result = evaluate_strategy5_volume_dry(ind, cfg)

    assert result.volume_dry_level == "BAD_DRY"
    assert "DRY_SHRINKING_BEAR_DRIFT" in result.volume_dry_rejects


def test_zero_volume_does_not_receive_high_dry_score():
    cfg = resolve_strategy5_config({})
    data = build_healthy_dry_data()
    for row in data[-60:]:
        row["volume"] = 0
    ind = calculate_indicators(data, cfg)

    result = evaluate_strategy5_volume_dry(ind, cfg)

    assert result.volume_dry_score < 10
    assert "DRY_INVALID_VOLUME" in result.volume_dry_rejects

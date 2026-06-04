from analyzer.market_env import assess_market_environment


def test_market_environment_good_when_index_above_ma_and_rising():
    data = _index_data(start=100, step=0.5, last_drop=False)

    result = assess_market_environment(data)

    assert result.status == "良好"
    assert result.position_advice == "正常"


def test_market_environment_bad_when_index_breaks_ma50_on_volume():
    data = _index_data(start=120, step=-0.25, last_drop=True)

    result = assess_market_environment(data)

    assert result.status == "较差"
    assert result.position_advice == "暂不参与"


def test_market_environment_unknown_defaults_to_general():
    result = assess_market_environment([])

    assert result.status == "一般"
    assert result.position_advice == "轻仓"


def _index_data(start, step, last_drop):
    data = []
    volume = 10_000_000
    for i in range(80):
        close = start + i * step
        if last_drop and i >= 75:
            close -= (i - 74) * 2
            volume = 18_000_000
        data.append({
            "date": f"2025-{i // 20 + 1:02d}-{i % 20 + 1:02d}",
            "open": close * 0.995,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": volume,
        })
    return data

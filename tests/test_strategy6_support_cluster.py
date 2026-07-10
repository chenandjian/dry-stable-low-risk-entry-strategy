from datetime import date, timedelta

from strategy6.models import Strategy6Indicators, Strategy6Pattern, Strategy6Start
from strategy6.support import evaluate_support
from strategy6.validation import resolve_strategy6_config


def _rows():
    rows = []
    for i in range(30):
        close = 100.0 + (i % 4) * 0.4
        rows.append({
            "date": (date(2026, 1, 1) + timedelta(days=i)).isoformat(),
            "open": close,
            "high": close + 1.0,
            "low": close - 0.8,
            "close": close,
            "volume": 1_000_000 - i * 10_000,
            "amount": 600_000_000,
        })
    return rows


def test_key_support_uses_structural_cluster_instead_of_nearest_ma5():
    rows = _rows()
    ind = Strategy6Indicators(
        current_price=103.0,
        ma5=104.0,
        ma10=102.5,
        ma20=100.0,
        ma50=96.0,
        atr14=2.0,
    )
    start = Strategy6Start(start_date=rows[0]["date"], start_low=99.2)
    pattern = Strategy6Pattern(
        pattern_type="VCP",
        pivot_price=110.0,
        pattern_low=99.5,
        pattern_height=10.5,
    )

    support = evaluate_support(rows, ind, start, pattern, resolve_strategy6_config({}))

    assert support.tactical_support_price == 104.0
    assert support.key_support_price < 101.0
    assert "PATTERN_LOW" in support.support_cluster_sources
    assert "MA20" in support.support_cluster_sources
    assert support.pivot_price == 110.0
    assert support.box_height == 10.5


def test_support_zone_width_uses_larger_of_price_pct_and_atr():
    rows = _rows()
    ind = Strategy6Indicators(
        current_price=103.0,
        ma5=103.5,
        ma10=102.0,
        ma20=100.0,
        ma50=96.0,
        atr14=10.0,
    )
    pattern = Strategy6Pattern(pattern_type="PLATFORM", pivot_price=112.0, pattern_low=100.0, pattern_height=12.0)

    support = evaluate_support(
        rows,
        ind,
        Strategy6Start(start_date=rows[0]["date"], start_low=99.0),
        pattern,
        resolve_strategy6_config({}),
    )

    assert round(support.support_zone_high - support.key_support_price, 2) == 3.0
    assert round(support.key_support_price - support.support_zone_low, 2) == 3.0

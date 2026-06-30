"""Strategy3 market index mapping and context tests."""
from __future__ import annotations

from strategy3.market_index import (
    compute_strategy3_market_context,
    resolve_strategy3_market_index,
)


def _market_rows(days=70, start=100.0, step=1.0):
    rows = []
    for i in range(days):
        close = start + i * step
        rows.append({
            "date": f"2026-01-{i + 1:02d}",
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": 1_000_000,
        })
    return rows


def test_strategy3_market_index_mapping_by_stock_prefix():
    assert resolve_strategy3_market_index("600000").symbol == "sh000001"
    assert resolve_strategy3_market_index("002230").symbol == "sz399001"
    assert resolve_strategy3_market_index("300750").symbol == "sz399006"
    assert resolve_strategy3_market_index("688981").symbol == "sh000688"


def test_strategy3_science_board_falls_back_when_star_index_unavailable():
    selection = resolve_strategy3_market_index(
        "688981",
        available_symbols={"sh000001", "sz399001", "sz399006"},
    )

    assert selection.symbol == "sh000001"
    assert selection.fallback is True
    assert selection.fallback_reason == "STAR_INDEX_UNAVAILABLE_FALLBACK_TO_SH000001"


def test_strategy3_market_context_calculates_payoff_relevant_environment_fields():
    rows = _market_rows()
    selection = resolve_strategy3_market_index("300750")

    context = compute_strategy3_market_context(
        rows,
        selection=selection,
        market_data_mode="injected_test_index",
    )

    assert context["market_index_symbol"] == "sz399006"
    assert context["market_index_name"] == "创业板指"
    assert context["market_data_mode"] == "injected_test_index"
    assert context["has_market_data"] is True
    assert context["market_return_20"] > 0
    assert context["market_return_60"] > 0
    assert context["market_above_ma20"] is True
    assert context["market_above_ma60"] is True
    assert context["market_volatility_20"] >= 0
    assert context["market_drawdown_60"] == 0

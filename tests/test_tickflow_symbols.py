import pytest

from tickflow_data.symbols import from_tickflow_symbol, to_tickflow_symbol


@pytest.mark.parametrize(
    ("code", "market", "expected"),
    [
        ("600519", "SH", "600519.SH"),
        ("000001", "SZ", "000001.SZ"),
        ("920001", "BJ", "920001.BJ"),
        ("688981", None, "688981.SH"),
        ("300750", None, "300750.SZ"),
        ("830799", None, "830799.BJ"),
    ],
)
def test_to_tickflow_symbol(code, market, expected):
    assert to_tickflow_symbol(code, market) == expected


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        ("600519.SH", "600519"),
        ("000001.sz", "000001"),
        ("920001.BJ", "920001"),
    ],
)
def test_from_tickflow_symbol(symbol, expected):
    assert from_tickflow_symbol(symbol) == expected


@pytest.mark.parametrize(
    ("code", "market"),
    [
        ("12345", None),
        ("ABC001", "SH"),
        ("100001", None),
        ("600519", "UNKNOWN"),
    ],
)
def test_to_tickflow_symbol_rejects_unknown_stock(code, market):
    with pytest.raises(ValueError):
        to_tickflow_symbol(code, market)


@pytest.mark.parametrize("symbol", ["600519", "ABC001.SH", "600519.US"])
def test_from_tickflow_symbol_rejects_invalid_symbol(symbol):
    with pytest.raises(ValueError):
        from_tickflow_symbol(symbol)

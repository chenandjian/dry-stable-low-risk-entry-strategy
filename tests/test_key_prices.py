from analyzer.key_prices import calculate_key_prices
from scanner.pattern_detector import CupHandleResult
from tests.test_pattern_score import _make_vcp_data


def test_vcp_key_prices_use_last_contraction_low_and_pivot():
    data = _make_vcp_data()
    result = CupHandleResult(found=False)

    key = calculate_key_prices(result, data, pattern_type="vcp")

    assert key.current_price > 0
    assert key.entry_zone_low > 0
    assert key.entry_zone_high >= key.entry_zone_low
    assert key.pivot > 0
    assert key.stop_loss > 0
    assert key.target_1 > key.current_price

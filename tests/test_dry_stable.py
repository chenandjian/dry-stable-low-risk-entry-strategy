from analyzer.dry_stable import analyze_dry_stable
from scanner.pattern_detector import CupHandleResult
from tests.test_pattern_score import _make_vcp_data


def test_dry_stable_analyzes_vcp_without_cup_handle():
    data = _make_vcp_data()
    result = CupHandleResult(found=False)

    analysis = analyze_dry_stable(result, data)

    assert analysis["pattern_score"]["vcp_score"] >= 13
    assert analysis["pattern_score"]["key_pattern_type"] == "vcp"
    assert analysis["key_prices"]["pivot"] > 0
    assert analysis["key_prices"]["entry_zone_low"] > 0

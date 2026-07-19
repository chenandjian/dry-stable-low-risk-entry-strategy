from strategy6.limit_up import (
    calc_limit_up_price,
    get_limit_up_pct,
    is_limit_up_day,
    is_one_word_limit_up,
    is_touched_limit_up_failed,
)


def test_limit_up_pct_uses_a_share_board_rules():
    assert get_limit_up_pct("000001") == 0.10
    assert get_limit_up_pct("002888") == 0.10
    assert get_limit_up_pct("600036") == 0.10
    assert get_limit_up_pct("300750") == 0.20
    assert get_limit_up_pct("301310") == 0.20
    assert get_limit_up_pct("688981") == 0.20


def test_limit_up_price_rounds_to_two_decimals():
    assert calc_limit_up_price(10.01, 0.10) == 11.01
    assert calc_limit_up_price(10.01, 0.20) == 12.01


def test_limit_up_day_allows_one_cent_tolerance():
    assert is_limit_up_day("000001", prev_close=10.0, close=10.99)
    assert not is_limit_up_day("000001", prev_close=10.0, close=10.98)
    assert is_limit_up_day("300750", prev_close=10.0, close=11.99)
    assert not is_limit_up_day("300750", prev_close=10.0, close=11.98)


def test_one_word_limit_up_is_not_rejected_by_low_volume():
    assert is_one_word_limit_up(
        "688981",
        prev_close=10.0,
        open_price=11.99,
        high=12.0,
        low=11.99,
        close=12.0,
    )


def test_touched_limit_up_failed_is_not_sealed_limit_up():
    assert is_touched_limit_up_failed("000001", prev_close=10.0, high=11.0, close=10.85)
    assert not is_touched_limit_up_failed("000001", prev_close=10.0, high=11.0, close=10.99)


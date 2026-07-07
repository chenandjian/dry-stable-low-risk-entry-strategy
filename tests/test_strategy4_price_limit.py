from strategy4.price_limit import (
    LIMIT_SHAPE_BROKEN_LIMIT_UP,
    LIMIT_SHAPE_LIMIT_UP_CLOSE,
    LIMIT_SHAPE_NEAR_LIMIT_UP,
    LIMIT_SHAPE_NO_PRICE_LIMIT_DAY,
    LIMIT_SHAPE_NOT_LIMIT_UP,
    LIMIT_SHAPE_ONE_WORD_LIMIT_UP,
    LIMIT_SHAPE_T_LIMIT_UP,
    PRICE_LIMIT_RULE_10CM,
    PRICE_LIMIT_RULE_20CM,
    PRICE_LIMIT_RULE_30CM,
    PRICE_LIMIT_RULE_5CM_ST,
    PRICE_LIMIT_RULE_NO_LIMIT,
    PriceLimitResolver,
)


def test_resolves_a_share_price_limit_rules_by_code_and_status():
    resolver = PriceLimitResolver()

    assert resolver.resolve("600000", "浦发银行").rule == PRICE_LIMIT_RULE_10CM
    assert resolver.resolve("002230", "科大讯飞").limit_pct == 0.10
    assert resolver.resolve("300750", "宁德时代").rule == PRICE_LIMIT_RULE_20CM
    assert resolver.resolve("301310", "鑫宏业").rule == PRICE_LIMIT_RULE_20CM
    assert resolver.resolve("688981", "中芯国际").rule == PRICE_LIMIT_RULE_20CM
    assert resolver.resolve("830799", "北交样本").rule == PRICE_LIMIT_RULE_30CM
    assert resolver.resolve("430047", "北交样本").rule == PRICE_LIMIT_RULE_30CM
    assert resolver.resolve("600000", "ST样本", is_st=True).rule == PRICE_LIMIT_RULE_5CM_ST
    assert resolver.resolve("300750", "*ST样本").rule == PRICE_LIMIT_RULE_5CM_ST
    assert resolver.resolve("600001", "新股样本", no_price_limit=True).rule == PRICE_LIMIT_RULE_NO_LIMIT


def test_classifies_limit_shapes_without_hardcoding_10_percent():
    resolver = PriceLimitResolver()
    mainboard = resolver.resolve("600000", "主板")
    cyb = resolver.resolve("300750", "创业板")

    assert resolver.classify_shape(mainboard, _row(10.50, 11.00, 10.50, 11.00), prev_close=10.00) == LIMIT_SHAPE_LIMIT_UP_CLOSE
    assert resolver.classify_shape(cyb, _row(10.00, 12.00, 10.00, 12.00), prev_close=10.00) == LIMIT_SHAPE_LIMIT_UP_CLOSE
    assert resolver.classify_shape(cyb, _row(12.00, 12.00, 12.00, 12.00), prev_close=10.00) == LIMIT_SHAPE_ONE_WORD_LIMIT_UP
    assert resolver.classify_shape(cyb, _row(11.80, 12.00, 11.20, 12.00), prev_close=10.00) == LIMIT_SHAPE_T_LIMIT_UP
    assert resolver.classify_shape(cyb, _row(10.50, 12.00, 10.20, 11.20), prev_close=10.00) == LIMIT_SHAPE_BROKEN_LIMIT_UP
    assert resolver.classify_shape(cyb, _row(10.50, 11.90, 10.20, 11.85), prev_close=10.00) == LIMIT_SHAPE_NEAR_LIMIT_UP
    assert resolver.classify_shape(cyb, _row(10.50, 11.00, 10.20, 11.00), prev_close=10.00) == LIMIT_SHAPE_NOT_LIMIT_UP


def test_no_price_limit_day_does_not_force_limit_up_shape():
    resolver = PriceLimitResolver()
    info = resolver.resolve("301001", "新股", no_price_limit=True)

    assert resolver.classify_shape(info, _row(10, 15, 9, 14), prev_close=10) == LIMIT_SHAPE_NO_PRICE_LIMIT_DAY


def _row(open_, high, low, close):
    return {"open": open_, "high": high, "low": low, "close": close}

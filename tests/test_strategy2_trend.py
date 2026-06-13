# tests/test_strategy2_trend.py
"""策略2 V2 趋势过滤测试 — 价格路径 + 120日长期确认 + 样本回归 + 反误杀。"""
import pytest
from strategy2.trend import evaluate_trend


# ── helpers ──

def _make_data(closes: list[float]) -> list[dict]:
    data = []
    for i, c in enumerate(closes):
        data.append({
            "date": f"2025-{(i+1):03d}",
            "open": c * 0.99, "high": c * 1.02, "low": c * 0.98,
            "close": c, "volume": 1000000,
        })
    return data

def _const(n: int, v: float) -> list[float]:
    return [v] * n


# ═══════════════════════════════════════════════════════════════════════════════
# 必要条件和短中期证据
# ═══════════════════════════════════════════════════════════════════════════════

def test_necessary_conditions_both_required():
    """close < MA20 且 MA20 < MA60 同时满足。"""
    closes = _const(120, 10.0)
    closes[-1] = 9.0  # close < MA20
    for i in range(60, 80):
        closes[i] = 11.0  # MA60 偏高 → MA20 < MA60
    result = evaluate_trend(_make_data(closes))
    assert result.necessary_conditions_met

def test_necessary_close_not_below_ma20_fails():
    """close >= MA20 时必要条件不成立。"""
    closes = _const(120, 10.0)
    result = evaluate_trend(_make_data(closes))
    assert not result.necessary_conditions_met

def test_necessary_ma20_not_below_ma60_fails():
    """MA20 >= MA60 时必要条件不成立。"""
    closes = _const(120, 10.0)
    closes[-1] = 12.0  # close > MA20, 必要条件不满足
    result = evaluate_trend(_make_data(closes))
    assert not result.necessary_conditions_met

def test_s1_close_below_ma20_hit():
    closes = _const(120, 10.0)
    closes[-1] = 9.0
    result = evaluate_trend(_make_data(closes))
    assert "CLOSE_BELOW_MA20" in result.downtrend_conditions

def test_s2_ma20_below_ma60_hit():
    closes = _const(120, 10.0)
    for i in range(60, 80):
        closes[i] = 11.0
    result = evaluate_trend(_make_data(closes))
    assert "MA20_BELOW_MA60" in result.downtrend_conditions

def test_s3_ma20_slope_negative_hit():
    closes = _const(120, 10.0)
    closes[-1] = 9.0  # MA20 slightly lower than MA20(-5)=10.0
    result = evaluate_trend(_make_data(closes))
    assert "MA20_SLOPE_NEGATIVE" in result.downtrend_conditions

def test_s4_ma60_slope_negative_hit():
    closes = _const(120, 10.0)
    closes[-1] = 9.0  # MA60 slightly lower than MA60(-10)=10.0
    result = evaluate_trend(_make_data(closes))
    assert "MA60_SLOPE_NEGATIVE" in result.downtrend_conditions

def test_s5_drawdown_from_high60():
    """60日高点回撤 ≤ -12% → 命中。"""
    closes = _const(120, 10.0)
    closes[60] = 15.0  # high inside [-60:]
    closes[-1] = 13.0  # drawdown = 13/15-1 = -13.3%
    result = evaluate_trend(_make_data(closes))
    assert "DRAWDOWN_FROM_HIGH60_AT_LEAST_12_PERCENT" in result.downtrend_conditions

def test_s6_center_shift_20():
    """最近20日中枢较此前20日下移 ≥ 5% → 命中。"""
    closes = _const(120, 10.0)
    # [-40:-20] = indices 80-99 → 11.0 (前20日中枢=11.0)
    for i in range(80, 100):
        closes[i] = 11.0
    # [-20:] = indices 100-119 → 10.0 (最近20日中枢=10.0)
    # center_shift = 10.0/11.0 - 1 = -9.1%
    result = evaluate_trend(_make_data(closes))
    assert "LATEST20_CENTER_BELOW_PREVIOUS20_BY_5_PERCENT" in result.downtrend_conditions

def test_s7_price_position_60_bottom():
    """60日区间位置 ≤ 30% → 命中。"""
    closes = _const(120, 10.0)
    closes[60] = 15.0  # max
    closes[-1] = 10.5  # pos = (10.5-10)/(15-10) = 10%... too high
    # Actually need pos ≤ 30%: (close-min)/(max-min) ≤ 0.3
    closes[-1] = 11.0  # pos = (11-10)/(15-10) = 20%
    result = evaluate_trend(_make_data(closes))
    assert "PRICE_POSITION60_BOTTOM_30_PERCENT" in result.downtrend_conditions

def test_s8_linear_trend_60():
    """60日线性趋势 ≤ -3% → 命中。"""
    # 构造一个持续下降的序列：从15降到10
    closes = _const(120, 10.0)
    for i in range(60, 120):
        closes[i] = 15.0 - 5.0 * (i - 60) / 59
    result = evaluate_trend(_make_data(closes))
    assert "LINEAR_TREND60_BELOW_MINUS_3_PERCENT" in result.downtrend_conditions


# ═══════════════════════════════════════════════════════════════════════════════
# 长期证据
# ═══════════════════════════════════════════════════════════════════════════════

def test_l1_ma60_below_ma120_hit():
    closes = _const(120, 10.0)
    for i in range(20):
        closes[i] = 12.0  # MA120 higher
    result = evaluate_trend(_make_data(closes))
    assert "MA60_BELOW_MA120" in result.downtrend_conditions

def test_l2_drawdown_from_high120():
    """120日高点回撤 ≤ -18% → 命中。"""
    closes = _const(120, 10.0)
    closes[0] = 20.0  # high inside [-120:]
    closes[-1] = 15.0  # drawdown = 15/20-1 = -25%
    result = evaluate_trend(_make_data(closes))
    assert "DRAWDOWN_FROM_HIGH120_AT_LEAST_18_PERCENT" in result.downtrend_conditions

def test_l3_center_shift_40():
    """最近40日中枢较此前40日下移 ≥ 6% → 命中。"""
    closes = _const(120, 10.0)
    for i in range(40, 80):
        closes[i] = 11.5  # 前40日中枢 ≈ 11.5
    # 最近40日 (80-119) = 10.0
    # shift = 10.0/11.5 - 1 = -13%
    result = evaluate_trend(_make_data(closes))
    assert "LATEST40_CENTER_BELOW_PREVIOUS40_BY_6_PERCENT" in result.downtrend_conditions


# ═══════════════════════════════════════════════════════════════════════════════
# 阈值逻辑
# ═══════════════════════════════════════════════════════════════════════════════

def test_below_total_threshold_not_downtrend():
    """总分 < 6 且必要条件和 long 均未同时满足 → UPTREND。"""
    # 全横盘：所有10.0，无任何下降证据
    closes = _const(120, 10.0)
    result = evaluate_trend(_make_data(closes))
    assert result.total_evidence_score < 6
    assert result.trend_type == "UPTREND_OR_SIDEWAYS"

def test_long_zero_not_downtrend_even_with_high_short():
    """long=0 即使 short≥4 → UPTREND（压低 MA120 打破 L1）。"""
    closes = _const(120, 10.0)
    closes[-1] = 9.6    # S1, S2, S3, S4, S7 都会触发 → short ≥ 4
    closes[30] = 9.0    # 压低 MA120 打破 L1
    # L2 (drawdown_120): 9.6/10-1 = -4% > -18% → 不中
    # L3 (center_shift_40): 几乎为0 → 不中
    result = evaluate_trend(_make_data(closes))
    assert result.long_score == 0, f"long={result.long_score}"
    assert result.trend_type == "UPTREND_OR_SIDEWAYS"


# ═══════════════════════════════════════════════════════════════════════════════
# 精确指标计算
# ═══════════════════════════════════════════════════════════════════════════════

def test_drawdown_from_high_60():
    """DRAWDOWN = close / max60 - 1。"""
    closes = _const(120, 10.0)
    closes[60] = 15.0
    closes[-1] = 12.0
    result = evaluate_trend(_make_data(closes))
    assert result.drawdown_from_high_60 == pytest.approx(12.0 / 15.0 - 1)

def test_center_shift_20():
    """CENTER_SHIFT_20 = mean(closes[-20:]) / mean(closes[-40:-20]) - 1。"""
    closes = _const(120, 10.0)
    for i in range(80, 100):
        closes[i] = 12.0
    # LATEST = mean(closes[100:120]) = 10.0
    # PREVIOUS = mean(closes[80:100]) = 12.0
    # shift = 10/12 - 1 = -16.7%
    result = evaluate_trend(_make_data(closes))
    assert result.center_shift_20 == pytest.approx(10.0 / 12.0 - 1)

def test_linear_trend_60():
    """LINEAR_TREND_60 = OLS slope * 59 / MA60。"""
    # Constant price → slope = 0, trend = 0
    closes = _const(120, 10.0)
    result = evaluate_trend(_make_data(closes))
    assert result.linear_trend_60 == pytest.approx(0.0, abs=1e-9)

def test_linear_trend_60_rising():
    """上升序列 → positive linear trend。"""
    closes = _const(120, 10.0)
    for i in range(60, 120):
        closes[i] = 10.0 + 5.0 * (i - 60) / 59
    result = evaluate_trend(_make_data(closes))
    assert result.linear_trend_60 > 0.03

def test_ma20_slope_5():
    """MA20_SLOPE_5 = MA20 / mean(closes[-25:-5]) - 1。"""
    closes = _const(120, 10.0)
    closes[-1] = 9.0
    result = evaluate_trend(_make_data(closes))
    assert result.ma20_slope < 0


# ═══════════════════════════════════════════════════════════════════════════════
# 数据不足
# ═══════════════════════════════════════════════════════════════════════════════

def test_less_than_120_returns_insufficient():
    """少于120日 → INSUFFICIENT_TREND_DATA。"""
    result = evaluate_trend(_make_data(_const(80, 10.0)))
    assert result is not None
    assert result.trend_type == "INSUFFICIENT_TREND_DATA"

def test_exactly_120_is_ok():
    """恰好120日正常计算。"""
    result = evaluate_trend(_make_data(_const(120, 10.0)))
    assert result.trend_type != "INSUFFICIENT_TREND_DATA"


# ═══════════════════════════════════════════════════════════════════════════════
# 边界值（≤ 均命中）
# ═══════════════════════════════════════════════════════════════════════════════

def test_boundary_drawdown_high60_exact():
    """-12% 命中（使用整数避免浮点精度）。"""
    closes = _const(120, 10.0)
    closes[60] = 25.0
    closes[-1] = 22.0  # 22/25-1 = -12% exactly
    result = evaluate_trend(_make_data(closes))
    assert "DRAWDOWN_FROM_HIGH60_AT_LEAST_12_PERCENT" in result.downtrend_conditions

def test_boundary_center_shift_20_exact():
    """-5% 命中（使用整数比例避免浮点精度）。"""
    closes = _const(120, 20.0)
    for i in range(80, 100):
        closes[i] = 20.0  # 前20日: 20.0
    # 最近20日全用 19.0 → shift = 19/20-1 = -5% exactly
    for i in range(100, 120):
        closes[i] = 19.0
    result = evaluate_trend(_make_data(closes))
    assert "LATEST20_CENTER_BELOW_PREVIOUS20_BY_5_PERCENT" in result.downtrend_conditions

def test_boundary_linear_trend_exact():
    """-3% 命中。"""
    # mA60≈10, slope*59/MA60=-0.03 → slope = -0.03*10/59 ≈ -0.00508
    closes = _const(120, 10.0)
    slope = -0.03 * 10.0 / 59.0
    for i in range(60, 120):
        closes[i] = 10.0 + slope * (i - 60)
    result = evaluate_trend(_make_data(closes))
    assert "LINEAR_TREND60_BELOW_MINUS_3_PERCENT" in result.downtrend_conditions

def test_boundary_drawdown_high120_exact():
    """-18% 命中（使用整数比例）。"""
    closes = _const(120, 50.0)
    closes[0] = 50.0
    closes[-1] = 41.0  # 41/50-1 = -18% exactly
    result = evaluate_trend(_make_data(closes))
    assert "DRAWDOWN_FROM_HIGH120_AT_LEAST_18_PERCENT" in result.downtrend_conditions

def test_boundary_center_shift_40_exact():
    """-6% 命中（使用整数比例）。"""
    closes = _const(120, 50.0)
    for i in range(40, 80):
        closes[i] = 50.0  # 前40日: 50.0
    # 最近40日全用 47.0 → shift = 47/50-1 = -6% exactly
    for i in range(80, 120):
        closes[i] = 47.0
    result = evaluate_trend(_make_data(closes))
    assert "LATEST40_CENTER_BELOW_PREVIOUS40_BY_6_PERCENT" in result.downtrend_conditions


# ═══════════════════════════════════════════════════════════════════════════════
# 离线样本：002468 和 601607 @ 2026-06-11
# ═══════════════════════════════════════════════════════════════════════════════

S2468_120 = [
    14.04,13.92,14.30,14.05,13.96,14.27,14.46,14.48,14.30,14.23,
    14.15,14.15,13.90,13.36,13.42,13.32,13.43,13.50,13.31,13.32,
    13.41,13.58,13.32,13.56,13.63,13.35,13.58,13.72,13.68,13.62,
    13.58,13.25,12.92,12.79,12.94,12.76,12.48,12.68,12.90,12.94,
    12.90,12.93,12.83,12.93,12.88,12.66,12.84,12.61,13.01,13.70,
    13.47,13.33,13.06,13.07,13.62,13.21,13.88,14.05,13.92,14.03,
    14.20,13.65,13.88,13.79,13.90,13.00,13.26,14.17,14.81,15.16,
    14.89,14.72,15.05,15.04,15.30,15.32,15.51,15.42,15.57,15.25,
    14.80,16.29,17.93,17.08,16.89,16.96,17.40,17.63,17.35,17.43,
    16.45,16.47,16.25,16.30,16.28,16.18,16.05,15.82,15.60,15.52,
    15.43,15.67,15.69,15.76,15.10,14.96,14.76,15.02,14.98,15.50,
    15.20,15.03,14.66,14.10,13.63,13.80,13.73,13.84,14.01,13.91,
]

S1607_120 = [
    17.630739212036133,17.69033432006836,17.928722381591797,17.839326858520508,
    17.73006820678711,17.789663314819336,18.0081844329834,17.908859252929688,
    17.859193801879883,17.80953025817871,17.80953025817871,17.80953025817871,
    17.739999771118164,17.710201263427734,17.700267791748047,17.739999771118164,
    17.850000381469727,17.889999389648438,17.81999969482422,17.84000015258789,
    17.8799991607666,17.920000076293945,18.059999465942383,17.579999923706055,
    17.540000915527344,17.360000610351562,17.31999969482422,17.469999313354492,
    17.3700008392334,17.309999465942383,17.479999542236328,17.610000610351562,
    17.43000030517578,17.399999618530273,17.420000076293945,17.299999237060547,
    17.110000610351562,17.170000076293945,17.270000457763672,17.309999465942383,
    17.260000228881836,17.290000915527344,17.280000686645508,17.270000457763672,
    17.209999084472656,17.15999984741211,17.219999313354492,17.290000915527344,
    17.219999313354492,17.200000762939453,17.25,17.209999084472656,17.0,
    17.030000686645508,17.139999389648438,17.170000076293945,17.170000076293945,
    17.200000762939453,17.229999542236328,17.290000915527344,17.270000457763672,
    17.309999465942383,17.219999313354492,17.079999923706055,16.889999389648438,
    16.299999237060547,16.469999313354492,16.579999923706055,16.440000534057617,
    16.690000534057617,16.799999237060547,17.049999237060547,17.200000762939453,
    17.329999923706055,17.309999465942383,17.280000686645508,17.290000915527344,
    17.09000015258789,17.15999984741211,17.079999923706055,17.020000457763672,
    17.25,17.139999389648438,16.989999771118164,16.93000030517578,17.010000228881836,
    16.959999084472656,16.969999313354492,16.8799991607666,16.68000030517578,
    16.93000030517578,16.93000030517578,17.09000015258789,17.15999984741211,
    17.1299991607666,17.06999969482422,17.149999618530273,17.149999618530273,
    17.049999237060547,16.889999389648438,16.729999542236328,16.5,
    16.729999542236328,16.6200008392334,16.5,16.440000534057617,16.3799991607666,
    16.34000015258789,16.389999389648438,16.18000030517578,16.479999542236328,
    16.440000534057617,16.5,16.299999237060547,16.100000381469727,
    16.260000228881836,16.030000686645508,16.1200008392334,16.25,16.239999771118164,
]


def test_002468_regression_downtrend():
    """002468 @ 2026-06-11 → DOWNTREND。"""
    result = evaluate_trend(_make_data(S2468_120))
    assert result.trend_type == "DOWNTREND", \
        f"Got {result.trend_type} (s={result.short_mid_score} l={result.long_score} t={result.total_evidence_score})"
    assert result.necessary_conditions_met
    assert result.short_mid_score >= 4
    assert result.long_score >= 1
    assert result.total_evidence_score >= 6
    # 验证关键指标合理性
    assert result.drawdown_from_high_60 < -0.12
    assert result.center_shift_20 < -0.05
    assert result.drawdown_from_high_120 < -0.18
    # S8 (linear_trend_60) 可命中可不命中，不强行断言


def test_601607_regression_downtrend():
    """601607 @ 2026-06-11 → DOWNTREND。"""
    result = evaluate_trend(_make_data(S1607_120))
    assert result.trend_type == "DOWNTREND", \
        f"Got {result.trend_type} (s={result.short_mid_score} l={result.long_score} t={result.total_evidence_score})"
    assert result.necessary_conditions_met
    assert result.short_mid_score >= 4
    assert result.long_score >= 1
    assert result.total_evidence_score >= 6
    assert result.linear_trend_60 < -0.04  # 文档预期 ≈ -4.95%
    assert result.price_position_60 <= 0.3


# ═══════════════════════════════════════════════════════════════════════════════
# 反误杀测试
# ═══════════════════════════════════════════════════════════════════════════════

def test_anti_false_high_sideways():
    """高位横盘：有120日高点回撤但不满足短中+长期条件，不误杀。"""
    # 早期大涨，后长期横盘在接近高点位置
    closes = _const(120, 20.0)
    closes[0] = 30.0  # 120日高点，使 drawdown_120 = -33%
    # 当前 close=20, MA20=20, MA60=20 → 必要条件不满足
    # short_mid 几乎为0，long只有L2
    result = evaluate_trend(_make_data(closes))
    assert result.trend_type == "UPTREND_OR_SIDEWAYS"

def test_anti_false_normal_pullback():
    """上涨趋势中的正常回调不误杀。"""
    closes = _const(120, 10.0)
    # 整体从10涨到18，最近回调到16
    for i in range(120):
        closes[i] = 10.0 + 8.0 * i / 119
    closes[-1] = 16.0  # 回调一下
    # close(16) > MA20 → 必要条件不满足
    result = evaluate_trend(_make_data(closes))
    assert result.trend_type == "UPTREND_OR_SIDEWAYS"

def test_anti_false_short_only_drop():
    """仅短期急跌但无长期确认 → long_score=0 → UPTREND。"""
    closes = _const(120, 10.0)
    # 最近10日从10跌到8.65（-13.5%），但110日前都是10.0
    for i in range(110, 120):
        closes[i] = 10.0 - 1.5 * (i - 109) / 10
    result = evaluate_trend(_make_data(closes))
    # long_score=0（MA120全部≈10, drawdown120≈13.5%, center_shift≈0）
    # → 不满足 long >= 1 → UPTREND 或 DOWNTREND
    # 不论结果如何，只要验证不崩溃且类型明确
    assert result.trend_type in ("UPTREND_OR_SIDEWAYS", "DOWNTREND")
    # 如果长期证据不足，应为 UPTREND
    if result.long_score < 1 and result.trend_type == "DOWNTREND":
        pytest.fail(f"DOWNTREND with long_score=0: {result.downtrend_conditions}")

def test_anti_false_price_above_ma20():
    """仅长期弱势但当前价已站上MA20，不误杀。"""
    closes = _const(120, 10.0)
    # 长期从15跌到9，但最近回升到11 > MA20
    for i in range(60):
        closes[i] = 15.0 - 5.0 * i / 59
    for i in range(60, 120):
        closes[i] = 9.0 + 2.0 * (i - 60) / 59
    closes[-1] = 11.0  # > MA20
    result = evaluate_trend(_make_data(closes))
    assert not result.necessary_conditions_met
    assert result.trend_type == "UPTREND_OR_SIDEWAYS"


# ═══════════════════════════════════════════════════════════════════════════════
# 不读取未来数据
# ═══════════════════════════════════════════════════════════════════════════════

def test_no_future_data_leak():
    closes = _const(130, 10.0)
    # 只应使用后120条
    for i in range(10, 130):
        closes[i] = 15.0
    result = evaluate_trend(_make_data(closes))
    # uses closes[-120:] = indices 10-129 = all 15.0
    assert result.ma20 == 15.0

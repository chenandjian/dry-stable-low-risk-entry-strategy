# 量干到跌不动选股策略开发文档

## 1. 策略目标

本策略用于识别一种更高级的极致量干状态：

> 成交量已经极度萎缩，并且股价已经跌不动。

也就是说，不只是成交量小，而是要进一步判断：

```text
卖压越来越少
下跌越来越浅
低点不再降低
支撑反复不破
继续砸盘也砸不动价格
```

本策略输出的是 **候选观察信号**，不是直接买入信号。最终买入还需要结合价稳、突破、回踩确认和盈亏比。

---

## 2. 核心思想

普通量干只判断：

```text
成交量是否减少
```

进阶量干要判断：

```text
成交量减少之后，价格是否已经不再有效下跌
```

真正优秀的形态是：

```text
量越来越小
跌幅越来越小
低点不再降低
阴线越来越弱
下影线开始增多
关键支撑多次测试不破
```

一句话：

> 不是量小就好，而是量小之后，价格已经不愿意再往下走。

---

## 3. 适用场景

本策略适合用于以下位置：

| 场景 | 说明 |
|---|---|
| Cup and Handle 柄部后半段 | 柄部缩量，价格不再下跌 |
| VCP 最后一轮收缩末端 | 波动和成交量同时收缩 |
| 强势上涨后的横盘末端 | 回调后卖压枯竭 |
| 突破前蓄力区 | 临近突破但还未放量 |

不适合以下股票：

| 类型 | 原因 |
|---|---|
| 长期下跌股 | 缩量可能只是没人买 |
| 缩量阴跌股 | 不是跌不动，而是无人承接 |
| 流动性太差的股票 | 容易失真 |
| 放量下跌股 | 疑似资金出逃 |
| 频繁破支撑的股票 | 结构不稳定 |

---

## 4. 数据要求

### 4.1 必须字段

每只股票需要日线数据：

| 字段 | 说明 |
|---|---|
| trade_date | 交易日期 |
| open | 开盘价 |
| high | 最高价 |
| low | 最低价 |
| close | 收盘价 |
| volume | 成交量 |
| amount | 成交额，建议保留 |

### 4.2 数据周期

最低要求：

```text
最近 60 个交易日
```

建议要求：

```text
最近 120 个交易日
```

如果少于 60 个交易日：

```text
直接跳过，不参与计算
```

---

## 5. 核心指标

### 5.1 成交量均值

```text
V3  = 最近3日平均成交量
V5  = 最近5日平均成交量
V10 = 最近10日平均成交量
V20 = 最近20日平均成交量
```

### 5.2 量能压缩比

```text
volume_ratio_5_20 = V5 / V20
```

判断标准：

| 状态 | 条件 |
|---|---|
| 初步量干 | V5 / V20 <= 0.70 |
| 明显量干 | V5 / V20 <= 0.60 |
| 极致量干 | V5 / V20 <= 0.50 |
| 终极量干 | V5 / V20 <= 0.40 |

### 5.3 逐级缩量

理想结构：

```text
V3 < V5 < V10 < V20
```

含义：

> 越接近当前，成交量越低，说明卖压持续减少。

### 5.4 最近 5 日涨跌幅

```text
return_5 = 当前收盘价 / 5日前收盘价 - 1
```

判断标准：

| 状态 | 条件 |
|---|---|
| 合格 | return_5 >= -3% |
| 更强 | return_5 >= -2% |
| 极强 | return_5 >= 0% |

核心要求：

```text
成交量缩小，但股价不能明显下跌
```

### 5.5 最近 5 日是否创新低

```text
min_close_5 = 最近5日最低收盘价
min_close_10 = 最近10日最低收盘价

no_new_low = min_close_5 >= min_close_10
```

判断：

```text
no_new_low = true
```

说明：

> 最近 5 日成交量变小，但收盘价没有继续创新低，说明价格开始跌不动。

### 5.6 支撑测试次数

定义关键支撑：

```text
key_support = 最近10日最低收盘价
```

如果能识别形态，则优先使用：

```text
VCP 最后一轮收缩低点
Cup and Handle 柄部低点
平台下沿
```

统计最近 10 日靠近支撑的次数：

```text
support_test_count = 最近10日内 low <= key_support * 1.02 的次数
```

合格条件：

```text
support_test_count >= 2
且
当前收盘价 >= key_support
```

更强条件：

```text
support_test_count >= 3
且
所有收盘价都没有有效跌破 key_support
```

有效跌破定义：

```text
close < key_support * 0.98
```

### 5.7 阴线实体收缩

只统计阴线：

```text
close < open
```

阴线实体：

```text
bear_body = open - close
```

判断：

```text
最近3根阴线实体均值 < 最近10根阴线实体均值
```

更强：

```text
最近3根阴线实体均值 <= 最近10根阴线实体均值 * 0.6
```

说明：

> 阴线越来越小，说明卖方攻击力度下降。

### 5.8 下影线承接

计算下影线比例：

```text
lower_shadow = min(open, close) - low
full_range = high - low
lower_shadow_ratio = lower_shadow / full_range
```

明显下影线定义：

```text
lower_shadow_ratio >= 0.4
```

判断：

```text
最近5日内明显下影线数量 >= 2
```

更强：

```text
最近5日内明显下影线数量 >= 3
```

说明：

> 盘中下杀后被买回，说明下方承接增强。

### 5.9 阴线成交量占比

```text
down_volume_5 = 最近5日内阴线成交量总和
total_volume_5 = 最近5日总成交量

down_volume_ratio = down_volume_5 / total_volume_5
```

判断：

| 状态 | 条件 |
|---|---|
| 合格 | down_volume_ratio <= 60% |
| 更强 | down_volume_ratio <= 50% |

说明：

> 如果缩量过程中主要都是阴线量，说明卖压仍然存在，质量不高。

### 5.10 ATR 波动收缩

```text
ATR5 = 最近5日平均真实波幅
ATR20 = 最近20日平均真实波幅

atr_ratio_5_20 = ATR5 / ATR20
```

判断：

| 状态 | 条件 |
|---|---|
| 波动收缩 | atr_ratio_5_20 <= 0.75 |
| 极致收缩 | atr_ratio_5_20 <= 0.60 |

说明：

> 股价整体波动正在降低，杀跌力度减弱。

---

## 6. 量干到跌不动评分规则

总分：

```text
100 分
```

### 6.1 量干基础分：30 分

| 条件 | 分数 |
|---|---:|
| V5 / V20 <= 0.70 | 10 |
| V5 / V20 <= 0.60 | 10 |
| V5 / V20 <= 0.50 | 10 |

### 6.2 跌不动分：40 分

| 条件 | 分数 |
|---|---:|
| 最近5日跌幅 >= -3% | 10 |
| 最近5日最低收盘价没有创新低 | 10 |
| 最近10日内至少2次测试支撑不破 | 10 |
| 最近3日无单日跌幅超过 -2% | 10 |

### 6.3 卖压衰竭分：20 分

| 条件 | 分数 |
|---|---:|
| 最近3根阴线实体小于最近10根阴线实体均值 | 5 |
| 最近5日内至少2根明显下影线 | 5 |
| 最近5日阴线成交量占比 <= 60% | 5 |
| 最近5日无放量阴线 | 5 |

放量阴线定义：

```text
当日收跌
且
当日成交量 >= V20 * 1.2
```

### 6.4 波动收缩分：10 分

| 条件 | 分数 |
|---|---:|
| ATR5 / ATR20 <= 0.75 | 5 |
| 最近5日振幅 <= 最近20日平均振幅 | 5 |

---

## 7. 等级划分

```text
dry_cannot_fall_score =
量干基础分
+ 跌不动分
+ 卖压衰竭分
+ 波动收缩分
```

| 分数 | 等级 | 含义 |
|---:|---|---|
| < 60 | NOT_READY | 还没到跌不动 |
| 60 - 74 | DRY_BUT_WEAK | 有量干，但跌不动不明显 |
| 75 - 84 | DRY_AND_STABLE | 量干并且价格开始稳定 |
| 85 - 94 | DRY_CANNOT_FALL | 量干到跌不动 |
| >= 95 | EXTREME_DRY_CANNOT_FALL | 极致量干，几乎跌不动 |

---

## 8. 最终入选条件

进入“量干到跌不动”候选池，必须同时满足：

```text
dry_cannot_fall_score >= 85
V5 / V20 <= 0.60
return_5 >= -3%
最近5日最低收盘价没有创新低
当前收盘价 >= key_support
最近10日内至少2次测试支撑不破
无放量下跌
无缩量阴跌
```

极致条件：

```text
dry_cannot_fall_score >= 95
V5 / V20 <= 0.50
return_5 >= -2%
最近3日无单日跌幅超过 -2%
最近5日内至少2根明显下影线
ATR5 / ATR20 <= 0.60
当前收盘价 >= key_support
```

---

## 9. 一票否决规则

### 9.1 缩量破位

```text
V5 / V20 <= 0.60
且
当前收盘价 < 最近10日最低收盘价
```

排除原因：

```text
缩量破位，不是跌不动
```

### 9.2 缩量阴跌

```text
V5 / V20 <= 0.60
且
return_5 <= -5%
```

排除原因：

```text
缩量阴跌，说明无人接盘
```

### 9.3 支撑测试失败

```text
最近10日内测试支撑后
收盘价跌破 key_support * 0.98
```

排除原因：

```text
支撑测试失败
```

### 9.4 放量下跌

```text
单日跌幅 <= -4%
且
当日成交量 >= V20 * 1.3
```

排除原因：

```text
放量下跌，疑似资金出逃
```

### 9.5 下跌波动重新放大

```text
ATR5 / ATR20 >= 1.2
且
return_5 < 0
```

排除原因：

```text
下跌波动重新放大
```

### 9.6 流动性不足

A股默认条件：

```text
最近20日平均成交额 < 5000万
```

美股默认条件：

```text
最近20日平均成交额 < 1000万美元
```

排除原因：

```text
流动性不足
```

该参数需要支持配置。

---

## 10. 输出字段设计

| 字段 | 类型 | 说明 |
|---|---|---|
| stock_code | string | 股票代码 |
| stock_name | string | 股票名称 |
| dry_cannot_fall_score | number | 量干到跌不动评分 |
| dry_cannot_fall_level | string | 等级 |
| status | string | 状态 |
| volume_ratio_5_20 | number | V5 / V20 |
| volume_ratio_3_20 | number | V3 / V20 |
| is_step_contracting | boolean | 是否逐级缩量 |
| return_5 | number | 最近5日涨跌幅 |
| min_close_5 | number | 最近5日最低收盘价 |
| min_close_10 | number | 最近10日最低收盘价 |
| no_new_low | boolean | 最近5日是否没有创新低 |
| key_support | number | 关键支撑 |
| support_test_count | number | 支撑测试次数 |
| support_valid | boolean | 支撑是否有效 |
| bear_body_shrink | boolean | 阴线实体是否缩小 |
| lower_shadow_count | number | 明显下影线数量 |
| down_volume_ratio | number | 阴线成交量占比 |
| atr_ratio_5_20 | number | ATR5 / ATR20 |
| has_big_down_volume | boolean | 是否放量下跌 |
| reject_reason | list | 排除原因 |
| trade_date | string | 最新交易日 |

---

## 11. 输出示例

```json
{
  "stock_code": "603155",
  "stock_name": "示例股票",
  "dry_cannot_fall_score": 90,
  "dry_cannot_fall_level": "DRY_CANNOT_FALL",
  "status": "DRY_CANNOT_FALL",
  "volume_ratio_5_20": 0.52,
  "volume_ratio_3_20": 0.46,
  "is_step_contracting": true,
  "return_5": -0.012,
  "min_close_5": 28.80,
  "min_close_10": 28.50,
  "no_new_low": true,
  "key_support": 28.50,
  "support_test_count": 3,
  "support_valid": true,
  "bear_body_shrink": true,
  "lower_shadow_count": 2,
  "down_volume_ratio": 0.42,
  "atr_ratio_5_20": 0.68,
  "has_big_down_volume": false,
  "reject_reason": [],
  "trade_date": "2026-06-26"
}
```

---

## 12. 模块设计建议

建议拆分为以下模块：

```text
analyzer/
  dry_cannot_fall.py      # 主策略入口
  volume_metrics.py       # 成交量指标
  price_weakness.py       # 跌不动判断
  support.py              # 支撑识别
  candle_strength.py      # K线承接和阴线衰竭
  volatility.py           # ATR和振幅收缩
  reject_rules.py         # 一票否决
  decision.py             # 综合决策
  output.py               # 输出格式化
```

---

## 13. 函数设计

### 13.1 calculate_volume_metrics

```python
def calculate_volume_metrics(data) -> dict:
    """
    计算 V3、V5、V10、V20、V5/V20、是否逐级缩量。
    """
```

返回：

```json
{
  "V3": 1000000,
  "V5": 1200000,
  "V10": 1800000,
  "V20": 2400000,
  "volume_ratio_5_20": 0.50,
  "volume_ratio_3_20": 0.42,
  "is_step_contracting": true
}
```

### 13.2 calculate_key_support

```python
def calculate_key_support(data, pattern_type=None) -> float:
    """
    计算关键支撑位。
    优先使用形态低点；无法识别时使用最近10日最低收盘价。
    """
```

### 13.3 count_support_tests

```python
def count_support_tests(data, key_support, days=10, tolerance=0.02) -> int:
    """
    统计最近 N 日内靠近支撑位的次数。
    默认 low <= key_support * 1.02 视为测试支撑。
    """
```

### 13.4 is_bear_body_shrinking

```python
def is_bear_body_shrinking(data) -> bool:
    """
    判断最近阴线实体是否明显缩小。
    最近3根阴线实体均值 < 最近10根阴线实体均值。
    """
```

### 13.5 count_lower_shadow

```python
def count_lower_shadow(data, days=5, threshold=0.4) -> int:
    """
    统计最近 N 日内明显下影线数量。
    lower_shadow_ratio >= threshold 视为明显下影线。
    """
```

### 13.6 calculate_down_volume_ratio

```python
def calculate_down_volume_ratio(data, days=5) -> float:
    """
    计算最近 N 日阴线成交量占比。
    """
```

### 13.7 calculate_atr_ratio

```python
def calculate_atr_ratio(data, short_days=5, long_days=20) -> float:
    """
    计算 ATR5 / ATR20。
    """
```

### 13.8 check_reject_rules

```python
def check_reject_rules(data, indicators, key_support, config) -> list:
    """
    检查一票否决规则。
    返回排除原因列表。
    """
```

### 13.9 calculate_dry_cannot_fall_score

```python
def calculate_dry_cannot_fall_score(data, indicators, key_support) -> dict:
    """
    计算量干到跌不动评分。
    """
```

返回：

```json
{
  "dry_cannot_fall_score": 90,
  "dry_cannot_fall_level": "DRY_CANNOT_FALL",
  "score_detail": {
    "dry_base_score": 30,
    "cannot_fall_score": 40,
    "selling_pressure_exhaustion_score": 15,
    "volatility_contraction_score": 5
  }
}
```

### 13.10 analyze_dry_cannot_fall

```python
def analyze_dry_cannot_fall(stock, data, config) -> dict:
    """
    量干到跌不动策略完整入口。
    """
```

---

## 14. 核心伪代码

```python
def analyze_dry_cannot_fall(stock, data, config):
    if len(data) < config["min_data_days"]:
        return reject(stock, "数据不足")

    indicators = calculate_volume_metrics(data)

    key_support = calculate_key_support(data)

    reject_reason = check_reject_rules(
        data=data,
        indicators=indicators,
        key_support=key_support,
        config=config
    )

    if reject_reason:
        return {
            "stock_code": stock.code,
            "stock_name": stock.name,
            "status": "FAILED",
            "reject_reason": reject_reason
        }

    score_result = calculate_dry_cannot_fall_score(
        data=data,
        indicators=indicators,
        key_support=key_support
    )

    current_close = data[-1]["close"]

    return {
        "stock_code": stock.code,
        "stock_name": stock.name,
        "dry_cannot_fall_score": score_result["dry_cannot_fall_score"],
        "dry_cannot_fall_level": score_result["dry_cannot_fall_level"],
        "status": score_result["dry_cannot_fall_level"],
        "volume_ratio_5_20": indicators["volume_ratio_5_20"],
        "volume_ratio_3_20": indicators["volume_ratio_3_20"],
        "is_step_contracting": indicators["is_step_contracting"],
        "return_5": calculate_return(data, 5),
        "min_close_5": min_close(data, 5),
        "min_close_10": min_close(data, 10),
        "no_new_low": min_close(data, 5) >= min_close(data, 10),
        "key_support": key_support,
        "support_test_count": count_support_tests(data, key_support),
        "support_valid": current_close >= key_support,
        "bear_body_shrink": is_bear_body_shrinking(data),
        "lower_shadow_count": count_lower_shadow(data),
        "down_volume_ratio": calculate_down_volume_ratio(data),
        "atr_ratio_5_20": calculate_atr_ratio(data),
        "has_big_down_volume": has_big_down_volume(data, indicators["V20"]),
        "reject_reason": [],
        "trade_date": data[-1]["trade_date"]
    }
```

---

## 15. 配置项建议

```json
{
  "min_data_days": 60,
  "v5_v20_dry_threshold": 0.60,
  "v5_v20_extreme_threshold": 0.50,
  "return_5_min": -0.03,
  "return_5_reject": -0.05,
  "max_single_day_drop_3": -0.02,
  "support_test_days": 10,
  "support_test_tolerance": 0.02,
  "support_break_tolerance": 0.98,
  "lower_shadow_threshold": 0.40,
  "lower_shadow_min_count": 2,
  "down_volume_ratio_max": 0.60,
  "big_down_return": -0.04,
  "big_down_volume_ratio": 1.30,
  "big_bear_volume_ratio": 1.20,
  "atr_contract_threshold": 0.75,
  "atr_extreme_contract_threshold": 0.60,
  "a_share_min_avg_amount_20": 50000000,
  "us_stock_min_avg_amount_20": 10000000
}
```

---

## 16. 排序规则

候选股票排序优先级：

```text
1. dry_cannot_fall_score 从高到低
2. volume_ratio_5_20 从低到高
3. support_test_count 从高到低
4. return_5 从高到低
5. atr_ratio_5_20 从低到高
6. down_volume_ratio 从低到高
```

解释：

> 优先选择量更干、支撑测试更有效、价格更跌不动、波动更收缩、阴线量更少的股票。

---

## 17. 前端展示建议

列表展示字段：

| 展示项 | 字段 |
|---|---|
| 股票代码 | stock_code |
| 股票名称 | stock_name |
| 总分 | dry_cannot_fall_score |
| 等级 | dry_cannot_fall_level |
| V5/V20 | volume_ratio_5_20 |
| 5日涨跌幅 | return_5 |
| 是否创新低 | no_new_low |
| 支撑测试次数 | support_test_count |
| 阴线实体收缩 | bear_body_shrink |
| 下影线数量 | lower_shadow_count |
| 阴线量占比 | down_volume_ratio |
| ATR收缩 | atr_ratio_5_20 |
| 排除原因 | reject_reason |

状态颜色建议：

| 状态 | 颜色 |
|---|---|
| NOT_READY | 灰色 |
| DRY_BUT_WEAK | 蓝色 |
| DRY_AND_STABLE | 黄色 |
| DRY_CANNOT_FALL | 橙色 |
| EXTREME_DRY_CANNOT_FALL | 绿色 |
| FAILED | 深灰色 |

---

## 18. 单元测试要求

### 18.1 正常“量干到跌不动”

输入条件：

```text
V5 / V20 = 0.55
return_5 = -1.2%
最近5日最低收盘价没有创新低
最近10日内3次测试支撑不破
最近5日有2根明显下影线
ATR5 / ATR20 = 0.68
无放量下跌
```

预期结果：

```text
status = DRY_CANNOT_FALL
dry_cannot_fall_score >= 85
reject_reason = []
```

### 18.2 极致“量干到跌不动”

输入条件：

```text
V5 / V20 = 0.45
return_5 = -0.5%
最近5日最低收盘价没有创新低
最近10日内3次测试支撑不破
最近3日无单日跌幅超过 -2%
最近5日有3根明显下影线
ATR5 / ATR20 = 0.55
无放量下跌
```

预期结果：

```text
status = EXTREME_DRY_CANNOT_FALL
dry_cannot_fall_score >= 95
reject_reason = []
```

### 18.3 缩量破位排除

输入条件：

```text
V5 / V20 = 0.55
current_close < 最近10日最低收盘价
```

预期结果：

```text
status = FAILED
reject_reason 包含 "缩量破位"
```

### 18.4 缩量阴跌排除

输入条件：

```text
V5 / V20 = 0.55
return_5 = -6%
```

预期结果：

```text
status = FAILED
reject_reason 包含 "缩量阴跌"
```

### 18.5 支撑测试失败排除

输入条件：

```text
close < key_support * 0.98
```

预期结果：

```text
status = FAILED
reject_reason 包含 "支撑测试失败"
```

### 18.6 放量下跌排除

输入条件：

```text
单日跌幅 = -5%
当日成交量 = V20 * 1.5
```

预期结果：

```text
status = FAILED
reject_reason 包含 "放量下跌"
```

---

## 19. 开发注意事项

### 19.1 不要只看成交量小

错误逻辑：

```text
成交量小 = 量干
```

正确逻辑：

```text
成交量小
+
价格不再有效下跌
+
支撑不破
+
卖压衰竭
=
量干到跌不动
```

### 19.2 不要把弱势缩量选出来

长期下跌、缩量阴跌、破支撑的股票必须排除。

### 19.3 量干到跌不动不是最终买点

该策略输出的是：

```text
高质量观察候选
```

真正买点需要继续确认：

```text
价稳
突破
回踩
止损
盈亏比
```

---

## 20. 最终总结

本策略的核心判断标准：

```text
成交量越来越小
股价跌幅越来越浅
低点不再降低
支撑多次测试不破
阴线实体越来越小
下影线开始增多
ATR波动收缩
没有放量出逃
```

最终目标：

> 找出卖压接近枯竭，并且继续卖也砸不动价格的股票。

一句话：

> 干到不能再干，跌到不愿再跌。

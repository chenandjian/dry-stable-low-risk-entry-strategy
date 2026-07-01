# 价稳到跌不动 / 涨跌都无力选股策略开发文档

## 1. 策略名称

```text
Extreme Balance Stability Strategy
```

中文名称：

```text
极致价稳：涨跌都无力策略
```

---

## 2. 策略目标

本策略用于识别一种比普通“价稳”更高级的状态：

> 股价已经被压缩到极小区间内，上涨推不动，下跌也砸不动。

这类股票通常处于：

```text
VCP 最后一轮收缩末端
Cup and Handle 柄部末端
平台整理末端
突破前蓄力区
量干价稳后期
```

策略目标不是寻找已经大涨的股票，而是寻找：

```text
不乱涨
不乱跌
波动极窄
支撑不破
方向效率很低
多空都暂时打不动
```

最终输出的是 **观察候选信号**，不是直接买入信号。

---

## 3. 核心定义

普通价稳：

```text
价格波动变小
收盘价集中
支撑不破
```

进阶价稳：

```text
价格波动变小
上涨推不动
下跌砸不动
高点压不出去
低点打不穿
成交量同步萎缩
```

一句话：

> 稳到涨不动，也跌不动，才是真正的极致价稳。

---

## 4. 适用场景

| 场景 | 说明 |
|---|---|
| VCP 最后一轮收缩 | 高点降低、低点抬高、波动压缩 |
| Cup and Handle 柄部末端 | 柄部缩量，价格横住 |
| 强势上涨后的横盘整理 | 上涨后休息，价格不再大幅波动 |
| 突破前蓄力区 | 临近突破，但尚未放量启动 |
| 量干价稳后期 | 成交量已干，价格进入静止状态 |

---

## 5. 不适用场景

| 类型 | 原因 |
|---|---|
| 长期下跌股 | 可能只是弱势横盘 |
| 暴跌后的弱反弹 | 不是稳定，而是修复不足 |
| 放量下跌股 | 有资金出逃 |
| 频繁破支撑股 | 结构不稳定 |
| 突然大涨后的高位追涨 | 已脱离低风险区域 |
| 流动性太差股票 | 指标容易失真 |

---

## 6. 数据要求

### 6.1 必须字段

| 字段 | 说明 |
|---|---|
| trade_date | 交易日期 |
| open | 开盘价 |
| high | 最高价 |
| low | 最低价 |
| close | 收盘价 |
| volume | 成交量 |
| amount | 成交额，建议保留 |

### 6.2 数据周期

最低要求：

```text
最近 60 个交易日
```

建议要求：

```text
最近 120 个交易日
```

数据少于 60 个交易日时：

```text
直接跳过，不参与评分
```

---

## 7. 核心指标

### 7.1 振幅压缩

计算：

```text
range_5 = 最近5日最高价 / 最近5日最低价 - 1
range_10 = 最近10日最高价 / 最近10日最低价 - 1
range_20 = 最近20日最高价 / 最近20日最低价 - 1
```

判断标准：

| 状态 | 条件 |
|---|---|
| 普通压缩 | range_5 <= 5% |
| 极致压缩 | range_5 <= 3% |
| 10日明显收敛 | range_10 <= 8% |
| 10日极致收敛 | range_10 <= 5% |

更理想结构：

```text
range_5 < range_10 < range_20
```

含义：

> 时间越靠近当前，价格波动越小，说明价格被持续压缩。

---

### 7.2 收盘价集中

计算：

```text
close_range_5 = 最近5日最高收盘价 / 最近5日最低收盘价 - 1
```

判断标准：

| 状态 | 条件 |
|---|---|
| 收盘稳定 | close_range_5 <= 3% |
| 极致稳定 | close_range_5 <= 2% |

含义：

> 盘中可以有波动，但收盘价必须集中，说明最终多空分歧很小。

---

### 7.3 跌不动判断

核心不是“不跌”，而是：

```text
往下试探，但收盘不破
```

计算：

```text
min_close_5 = 最近5日最低收盘价
min_close_10 = 最近10日最低收盘价
```

判断：

```text
min_close_5 >= min_close_10
```

关键支撑：

```text
key_support = 最近10日最低收盘价
```

如果系统能识别形态，则优先使用：

```text
VCP 最后一轮收缩低点
Cup and Handle 柄部低点
平台下沿
MA20 / MA50 重合区
```

支撑测试次数：

```text
support_test_count = 最近10日内 low <= key_support * 1.02 的次数
```

合格条件：

```text
support_test_count >= 2
current_close >= key_support
```

极强条件：

```text
support_test_count >= 3
且
没有 close < key_support * 0.98
```

---

### 7.4 涨不动判断

价格不能提前大涨，否则不是低风险压缩区。

计算：

```text
return_5 = 当前收盘价 / 5日前收盘价 - 1
return_3 = 当前收盘价 / 3日前收盘价 - 1
```

判断：

```text
return_5 <= 5%
return_3 <= 3%
```

更严格：

```text
最近5日最高收盘价没有明显突破平台上沿
```

含义：

> 股价没有提前拉开空间，还在窄区间内蓄力。

---

### 7.5 上下都无力：方向效率

这是识别“涨跌都无力”的核心指标。

计算：

```text
net_change_5 = abs(当前收盘价 - 5日前收盘价) / 5日前收盘价

total_move_5 = 最近5日每日涨跌幅绝对值之和

direction_efficiency = net_change_5 / total_move_5
```

判断标准：

| 状态 | 条件 |
|---|---|
| 方向效率低 | direction_efficiency <= 0.35 |
| 极致无方向 | direction_efficiency <= 0.25 |

解释：

> 最近几天虽然有波动，但最终没有走出方向，说明上涨和下跌都缺乏持续力量。

注意：

```text
如果 total_move_5 = 0，则 direction_efficiency = 0
```

---

### 7.6 最大上涨日和最大下跌日

计算：

```text
max_up_5 = 最近5日最大单日涨幅
max_down_5 = 最近5日最大单日跌幅
```

判断：

```text
max_up_5 <= 3%
max_down_5 >= -3%
```

更极致：

```text
max_up_5 <= 2%
max_down_5 >= -2%
```

含义：

> 没有强拉，也没有强砸，价格进入极窄平衡。

---

### 7.7 收盘位置居中

计算：

```text
close_position = (close - low) / (high - low)
```

当 high == low 时：

```text
close_position = 0.5
```

最近 5 日平均值：

```text
avg_close_position_5
```

理想区间：

```text
0.35 <= avg_close_position_5 <= 0.65
```

含义：

> 收盘既不极弱，也没有提前爆发，处于均衡压缩状态。

---

### 7.8 ATR 波动收缩

计算：

```text
ATR5 = 最近5日平均真实波幅
ATR20 = 最近20日平均真实波幅

atr_ratio_5_20 = ATR5 / ATR20
```

判断标准：

| 状态 | 条件 |
|---|---|
| 波动收缩 | ATR5 / ATR20 <= 0.75 |
| 极致收缩 | ATR5 / ATR20 <= 0.60 |

含义：

> 整体波动明显降低，价格进入静止状态。

---

### 7.9 成交量配合

虽然本策略重点是价稳，但最好要求成交量同步降低。

计算：

```text
V5 = 最近5日平均成交量
V20 = 最近20日平均成交量

volume_ratio_5_20 = V5 / V20
```

判断：

```text
volume_ratio_5_20 <= 0.80
```

更强：

```text
volume_ratio_5_20 <= 0.60
```

说明：

> 如果价格极稳，但成交量仍然很大，说明分歧还没有真正消失。

---

## 8. 评分规则

总分：

```text
100 分
```

### 8.1 价格压缩分：30 分

| 条件 | 分数 |
|---|---:|
| range_5 <= 5% | 10 |
| range_5 <= 3% | 10 |
| close_range_5 <= 3% | 10 |

---

### 8.2 跌不动分：25 分

| 条件 | 分数 |
|---|---:|
| 当前价 >= key_support | 10 |
| 最近5日没有收盘创新低 | 5 |
| 最近10日测试支撑 >= 2 次 | 5 |
| 没有有效跌破 key_support | 5 |

---

### 8.3 涨不动分：20 分

| 条件 | 分数 |
|---|---:|
| 最近5日涨幅 <= 5% | 5 |
| 最近3日涨幅 <= 3% | 5 |
| max_up_5 <= 3% | 5 |
| 最近5日最高收盘价没有明显突破平台上沿 | 5 |

---

### 8.4 涨跌都无力分：25 分

| 条件 | 分数 |
|---|---:|
| direction_efficiency <= 0.35 | 10 |
| max_up_5 <= 3% 且 max_down_5 >= -3% | 5 |
| ATR5 / ATR20 <= 0.75 | 5 |
| 0.35 <= avg_close_position_5 <= 0.65 | 5 |

---

## 9. 等级划分

```text
balance_stable_score =
价格压缩分
+ 跌不动分
+ 涨不动分
+ 涨跌都无力分
```

| 分数 | 等级 | 含义 |
|---:|---|---|
| < 60 | NOT_BALANCED | 还不稳定 |
| 60 - 74 | BALANCE_FORMING | 正在进入平衡 |
| 75 - 84 | BALANCE_CONFIRMED | 价格平衡成立 |
| 85 - 94 | EXTREME_BALANCE | 极致价稳，涨跌都无力 |
| >= 95 | SUPER_BALANCE | 稳到不能再稳，方向高度压缩 |

---

## 10. 最终入选条件

进入候选池必须同时满足：

```text
balance_stable_score >= 85
range_5 <= 5%
close_range_5 <= 3%
current_close >= key_support
最近5日没有收盘创新低
最近5日涨幅 <= 5%
direction_efficiency <= 0.35
ATR5 / ATR20 <= 0.75
无放量下跌
无有效破位
```

极致条件：

```text
balance_stable_score >= 95
range_5 <= 3%
close_range_5 <= 2%
最近3日涨幅 <= 3%
最近3日最大跌幅 >= -2%
direction_efficiency <= 0.25
ATR5 / ATR20 <= 0.60
支撑测试 >= 3 次且不破
```

---

## 11. 一票否决规则

### 11.1 跌破关键支撑

```text
current_close < key_support * 0.98
```

排除原因：

```text
跌破关键支撑
```

---

### 11.2 放量下跌

```text
单日跌幅 <= -4%
且
volume >= V20 * 1.3
```

排除原因：

```text
放量下跌
```

---

### 11.3 波动重新放大

```text
range_5 > 10%
```

排除原因：

```text
波动重新放大
```

---

### 11.4 提前大涨

```text
最近3日涨幅 >= 8%
```

标记：

```text
EXTENDED
```

说明：

> 已脱离低风险价稳区域，不作为新买点候选。

---

### 11.5 长期下降趋势

```text
MA20 < MA50
且
MA50 向下
```

排除原因：

```text
长期趋势向下
```

---

### 11.6 流动性不足

A股默认：

```text
最近20日平均成交额 < 5000万
```

美股默认：

```text
最近20日平均成交额 < 1000万美元
```

排除原因：

```text
流动性不足
```

---

## 12. 输出字段设计

| 字段 | 类型 | 说明 |
|---|---|---|
| stock_code | string | 股票代码 |
| stock_name | string | 股票名称 |
| balance_stable_score | number | 涨跌无力价稳评分 |
| balance_stable_level | string | 等级 |
| status | string | 状态 |
| range_5 | number | 最近5日振幅 |
| range_10 | number | 最近10日振幅 |
| range_20 | number | 最近20日振幅 |
| close_range_5 | number | 最近5日收盘波动 |
| return_5 | number | 最近5日涨跌幅 |
| return_3 | number | 最近3日涨跌幅 |
| max_up_5 | number | 最近5日最大单日涨幅 |
| max_down_5 | number | 最近5日最大单日跌幅 |
| direction_efficiency | number | 方向效率 |
| key_support | number | 关键支撑 |
| support_test_count | number | 支撑测试次数 |
| support_valid | boolean | 支撑是否有效 |
| atr_ratio_5_20 | number | ATR5 / ATR20 |
| avg_close_position_5 | number | 最近5日平均收盘位置 |
| volume_ratio_5_20 | number | V5 / V20 |
| reject_reason | list | 排除原因 |
| trade_date | string | 最新交易日 |

---

## 13. 输出示例

```json
{
  "stock_code": "000921",
  "stock_name": "示例股票",
  "balance_stable_score": 90,
  "balance_stable_level": "EXTREME_BALANCE",
  "status": "EXTREME_BALANCE",
  "range_5": 0.028,
  "range_10": 0.065,
  "range_20": 0.118,
  "close_range_5": 0.018,
  "return_5": 0.012,
  "return_3": 0.006,
  "max_up_5": 0.021,
  "max_down_5": -0.018,
  "direction_efficiency": 0.22,
  "key_support": 26.20,
  "support_test_count": 3,
  "support_valid": true,
  "atr_ratio_5_20": 0.58,
  "avg_close_position_5": 0.52,
  "volume_ratio_5_20": 0.56,
  "reject_reason": [],
  "trade_date": "2026-06-26"
}
```

---

## 14. 模块设计建议

```text
analyzer/
  balance_stability/
    balance_stability.py       # 主策略入口
    range_metrics.py           # 振幅和收盘波动
    direction_efficiency.py    # 方向效率
    support_check.py           # 支撑测试与破位
    atr_metrics.py             # ATR波动收缩
    price_power.py             # 涨不动 / 跌不动判断
    reject_rules.py            # 一票否决规则
    decision.py                # 综合决策
    output.py                  # 输出格式化
```

---

## 15. 函数设计

### 15.1 calc_range

```python
def calc_range(data, days: int) -> float:
    """
    计算最近 N 日高低价振幅。
    range_n = max(high) / min(low) - 1
    """
```

---

### 15.2 calc_close_range

```python
def calc_close_range(data, days: int) -> float:
    """
    计算最近 N 日收盘价波动。
    close_range_n = max(close) / min(close) - 1
    """
```

---

### 15.3 calc_direction_efficiency

```python
def calc_direction_efficiency(data, days: int = 5) -> float:
    """
    计算方向效率。
    direction_efficiency = net_change / total_move
    """
```

实现要点：

```text
net_change = abs(close_today - close_n_days_ago) / close_n_days_ago
total_move = sum(abs(daily_return_i))

if total_move == 0:
    return 0
```

---

### 15.4 calculate_key_support

```python
def calculate_key_support(data, pattern_type=None) -> float:
    """
    计算关键支撑。
    优先使用形态低点，否则使用最近10日最低收盘价。
    """
```

---

### 15.5 count_support_tests

```python
def count_support_tests(data, key_support, days=10, tolerance=0.02) -> int:
    """
    统计最近 N 日靠近支撑的次数。
    low <= key_support * (1 + tolerance)
    """
```

---

### 15.6 calc_avg_close_position

```python
def calc_avg_close_position(data, days=5) -> float:
    """
    计算最近 N 日平均收盘位置。
    close_position = (close - low) / (high - low)
    当 high == low 时，close_position = 0.5
    """
```

---

### 15.7 check_balance_reject_rules

```python
def check_balance_reject_rules(data, indicators, key_support, config) -> list:
    """
    检查一票否决规则。
    返回排除原因列表。
    """
```

---

### 15.8 calculate_balance_stable_score

```python
def calculate_balance_stable_score(data, indicators, key_support) -> dict:
    """
    计算涨跌都无力价稳评分。
    """
```

返回：

```json
{
  "balance_stable_score": 90,
  "balance_stable_level": "EXTREME_BALANCE",
  "score_detail": {
    "price_compression_score": 30,
    "cannot_fall_score": 25,
    "cannot_rise_score": 20,
    "balance_score": 15
  }
}
```

---

## 16. 核心伪代码

```python
def analyze_extreme_balance_stable(stock, data, config):
    if len(data) < config["min_data_days"]:
        return reject(stock, "数据不足")

    indicators = {}

    indicators["range_5"] = calc_range(data, 5)
    indicators["range_10"] = calc_range(data, 10)
    indicators["range_20"] = calc_range(data, 20)

    indicators["close_range_5"] = calc_close_range(data, 5)

    indicators["return_5"] = calc_return(data, 5)
    indicators["return_3"] = calc_return(data, 3)

    indicators["max_up_5"] = calc_max_daily_return(data, 5)
    indicators["max_down_5"] = calc_min_daily_return(data, 5)

    indicators["direction_efficiency"] = calc_direction_efficiency(data, 5)

    indicators["atr_ratio_5_20"] = calc_atr(data, 5) / calc_atr(data, 20)

    indicators["avg_close_position_5"] = calc_avg_close_position(data, 5)

    indicators["volume_ratio_5_20"] = calc_avg_volume(data, 5) / calc_avg_volume(data, 20)

    key_support = calculate_key_support(data)

    indicators["support_test_count"] = count_support_tests(
        data=data,
        key_support=key_support,
        days=10,
        tolerance=config["support_test_tolerance"]
    )

    reject_reason = check_balance_reject_rules(
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

    score_result = calculate_balance_stable_score(
        data=data,
        indicators=indicators,
        key_support=key_support
    )

    return {
        "stock_code": stock.code,
        "stock_name": stock.name,
        "balance_stable_score": score_result["balance_stable_score"],
        "balance_stable_level": score_result["balance_stable_level"],
        "status": score_result["balance_stable_level"],
        "range_5": indicators["range_5"],
        "range_10": indicators["range_10"],
        "range_20": indicators["range_20"],
        "close_range_5": indicators["close_range_5"],
        "return_5": indicators["return_5"],
        "return_3": indicators["return_3"],
        "max_up_5": indicators["max_up_5"],
        "max_down_5": indicators["max_down_5"],
        "direction_efficiency": indicators["direction_efficiency"],
        "key_support": key_support,
        "support_test_count": indicators["support_test_count"],
        "support_valid": current_close(data) >= key_support,
        "atr_ratio_5_20": indicators["atr_ratio_5_20"],
        "avg_close_position_5": indicators["avg_close_position_5"],
        "volume_ratio_5_20": indicators["volume_ratio_5_20"],
        "reject_reason": [],
        "trade_date": data[-1]["trade_date"]
    }
```

---

## 17. 配置项建议

```json
{
  "min_data_days": 60,
  "range_5_threshold": 0.05,
  "range_5_extreme_threshold": 0.03,
  "range_10_threshold": 0.08,
  "close_range_5_threshold": 0.03,
  "close_range_5_extreme_threshold": 0.02,
  "return_5_max": 0.05,
  "return_3_max": 0.03,
  "return_3_extended": 0.08,
  "max_up_5_threshold": 0.03,
  "max_down_5_threshold": -0.03,
  "direction_efficiency_threshold": 0.35,
  "direction_efficiency_extreme_threshold": 0.25,
  "atr_ratio_threshold": 0.75,
  "atr_ratio_extreme_threshold": 0.60,
  "close_position_min": 0.35,
  "close_position_max": 0.65,
  "support_test_days": 10,
  "support_test_tolerance": 0.02,
  "support_break_tolerance": 0.98,
  "big_down_return": -0.04,
  "big_down_volume_ratio": 1.30,
  "volume_ratio_5_20_threshold": 0.80,
  "a_share_min_avg_amount_20": 50000000,
  "us_stock_min_avg_amount_20": 10000000
}
```

---

## 18. 排序规则

候选股票排序优先级：

```text
1. balance_stable_score 从高到低
2. range_5 从低到高
3. close_range_5 从低到高
4. direction_efficiency 从低到高
5. atr_ratio_5_20 从低到高
6. support_test_count 从高到低
7. volume_ratio_5_20 从低到高
```

含义：

> 优先选择波动更窄、收盘更集中、方向效率更低、支撑更可靠、成交量更低的股票。

---

## 19. 前端展示建议

| 展示项 | 字段 |
|---|---|
| 股票代码 | stock_code |
| 股票名称 | stock_name |
| 总分 | balance_stable_score |
| 等级 | balance_stable_level |
| 5日振幅 | range_5 |
| 收盘波动 | close_range_5 |
| 方向效率 | direction_efficiency |
| 5日涨跌幅 | return_5 |
| 最大上涨日 | max_up_5 |
| 最大下跌日 | max_down_5 |
| 关键支撑 | key_support |
| 支撑测试次数 | support_test_count |
| ATR收缩 | atr_ratio_5_20 |
| 成交量压缩 | volume_ratio_5_20 |
| 排除原因 | reject_reason |

状态颜色建议：

| 状态 | 颜色 |
|---|---|
| NOT_BALANCED | 灰色 |
| BALANCE_FORMING | 蓝色 |
| BALANCE_CONFIRMED | 黄色 |
| EXTREME_BALANCE | 橙色 |
| SUPER_BALANCE | 绿色 |
| FAILED | 深灰色 |

---

## 20. 单元测试要求

### 20.1 正常极致价稳

输入：

```text
range_5 = 2.8%
close_range_5 = 1.8%
return_5 = 1.2%
return_3 = 0.6%
max_up_5 = 2.1%
max_down_5 = -1.8%
direction_efficiency = 0.22
ATR5 / ATR20 = 0.58
support_test_count = 3
current_close >= key_support
```

预期：

```text
status = EXTREME_BALANCE 或 SUPER_BALANCE
balance_stable_score >= 85
reject_reason = []
```

---

### 20.2 跌破支撑排除

输入：

```text
current_close < key_support * 0.98
```

预期：

```text
status = FAILED
reject_reason 包含 "跌破关键支撑"
```

---

### 20.3 放量下跌排除

输入：

```text
单日跌幅 = -5%
volume >= V20 * 1.5
```

预期：

```text
status = FAILED
reject_reason 包含 "放量下跌"
```

---

### 20.4 波动重新放大排除

输入：

```text
range_5 = 12%
```

预期：

```text
status = FAILED
reject_reason 包含 "波动重新放大"
```

---

### 20.5 提前大涨标记

输入：

```text
return_3 = 9%
```

预期：

```text
status = EXTENDED 或 FAILED
reject_reason 包含 "提前大涨"
```

---

### 20.6 长期下降趋势排除

输入：

```text
MA20 < MA50
且
MA50 向下
```

预期：

```text
status = FAILED
reject_reason 包含 "长期趋势向下"
```

---

## 21. 开发注意事项

### 21.1 不要把弱势横盘当作极致价稳

必须结合：

```text
趋势过滤
支撑有效
流动性过滤
放量下跌过滤
```

否则会选出长期弱势股票。

---

### 21.2 不要把提前突破的股票当作价稳

如果最近 3 日涨幅过大，说明已经脱离低风险区域。

应该标记为：

```text
EXTENDED
```

---

### 21.3 方向效率是核心

“涨跌都无力”的核心是：

```text
direction_efficiency 很低
```

也就是：

```text
有波动，但没有方向
```

---

### 21.4 极致价稳不是买点

本策略只输出：

```text
高质量观察候选
```

后续买点还需要结合：

```text
放量突破
突破后回踩
止损距离
盈亏比
```

---

## 22. 最终总结

本策略识别的不是普通横盘，而是：

```text
波动越来越小
收盘越来越集中
下跌打不穿
上涨推不动
方向效率很低
ATR明显收缩
成交量同步萎缩
```

最终目标：

> 找出价格被压缩到极小区间，多空都暂时打不动，正在等待方向选择的股票。

一句话：

> 稳到涨不动，也跌不动，才是真正的极致价稳。

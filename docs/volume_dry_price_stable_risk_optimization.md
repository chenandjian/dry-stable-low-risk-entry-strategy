# 量干 + 价稳 + 风险最小策略优化开发文档

## 1. 背景

当前系统已经具备以下评分模块：

```text
analyzer/volume_dry.py
analyzer/price_stable.py
analyzer/decision.py
```

现有目标是判断股票是否处于：

```text
量干：卖压衰竭
价稳：价格停止下跌并进入稳定区间
风险最小：入场价接近支撑，止损空间小，盈亏比合理
```

本次优化目标不是简单增加指标，而是提升系统的稳定性、可解释性和实战可靠性，避免误把以下股票选为低吸标的：

```text
1. 缩量阴跌股
2. 破位后缩量股
3. 无买盘承接的弱势股
4. 盈亏比虚高的股票
5. 止损过近或过远的股票
6. 形态未成熟但短期缩量的股票
```

---

# 2. 本次优化目标

## 2.1 核心目标

将当前评分系统升级为：

```text
评分系统 + 风险控制系统 + 拒因解释系统
```

系统最终不只返回买入或不买入，而是返回明确状态：

```text
BUY_LOW         可低吸
WATCH_BREAKOUT 等突破确认
WAIT_VOLUME    等量能进一步萎缩
WAIT_STABLE    等价格进一步稳定
WAIT_ENTRY     等回调到合理入场区
WAIT_RR        盈亏比不足，继续等待
REJECT         不建议买入
```

---

# 3. 模块改造范围

## 3.1 涉及文件

```text
analyzer/
├── volume_dry.py
├── price_stable.py
├── decision.py
├── risk_reward.py
├── pattern_score.py
└── data_cleaner.py
```

如果当前没有以下文件，需要新增：

```text
analyzer/risk_reward.py
analyzer/data_cleaner.py
```

---

# 4. 数据口径统一

## 4.1 价格口径

所有价格相关指标统一使用前复权数据：

```text
open
high
low
close
```

要求：

```text
价格指标使用前复权 OHLC
成交量 volume 使用原始成交量
成交额 amount 使用原始成交额
```

不得使用未复权价格计算形态、支撑、阻力、止损、ATR。

---

## 4.2 成交量口径

成交量均线统一命名，避免和价格均线混淆：

```text
volume_ma20 = 最近20个交易日成交量平均值
volume_ma50 = 最近50个交易日成交量平均值
```

价格均线命名为：

```text
price_ma20
price_ma50
price_ma120
price_ma250
```

---

# 5. 数据清洗规则

新增文件：

```text
analyzer/data_cleaner.py
```

## 5.1 停牌日处理

如果出现：

```text
volume == 0
或 high == low == close
```

则标记为异常交易日。

停牌日不得参与以下计算：

```text
成交量均线
Range
ATR
局部低点
低点上移判断
```

---

## 5.2 涨跌停处理

A股涨跌停日容易扭曲波动率和成交量，需要标记。

建议字段：

```json
{
	"is_limit_up": true,
	"is_limit_down": false,
	"is_one_word_limit": false
}
```

一字涨停 / 一字跌停定义：

```text
high == low
且涨跌幅接近涨停 / 跌停幅度
```

一字板不参与正常 Range 和 ATR 收缩评分。

---

## 5.3 上市时间不足过滤

如果有效交易日数量不足：

```text
小于80个交易日
```

则不参与完整评分。

返回：

```text
REJECT
拒因：上市时间不足，样本不足
```

---

# 6. 量干评分优化

对应文件：

```text
analyzer/volume_dry.py
```

---

## 6.1 保留原有量干评分

原有 5 个维度继续保留：

```text
A. 近期量 vs MA20
B. 近期量 vs MA50
C. 量递减序列
D. 下跌无量
E. 极端低量
```

总分仍为：

```text
0 ~ 10 分
```

---

## 6.2 明确 V1 / V2 / V3 计算窗口

```text
V1 = 第 -15 到 -11 个交易日的平均成交量
V2 = 第 -10 到 -6 个交易日的平均成交量
V3 = 第 -5 到 -1 个交易日的平均成交量
```

评分：

```text
如果 V1 > V2 > V3，得 2 分
如果 V2 > V3，得 1 分
否则 0 分
```

---

## 6.3 新增：好缩量 / 坏缩量识别

缩量不能单独视为健康信号。

新增逻辑：

```text
如果近10日价格重心持续下移，则量干最高6分。
```

价格重心持续下移定义：

```text
近10日 close 做线性回归
如果回归斜率对应的累计跌幅 < -3%
且当前 close < price_ma20
则视为缩量阴跌
```

处理结果：

```text
volume_dry_score = min(volume_dry_score, 6)
warnings 添加：缩量但价格重心下移，疑似弱势阴跌
```

---

## 6.4 新增：缩量位置过滤

同样是缩量，位置不同意义不同。

新增计算：

```text
position_60d = (close - low_60d) / (high_60d - low_60d)
```

处理规则：

```text
position_60d >= 0.5：
    正常评分

0.3 <= position_60d < 0.5：
    volume_dry_score = min(volume_dry_score, 6)
    warnings 添加：缩量位置偏低，弱势缩量风险

position_60d < 0.3：
    volume_dry_score = min(volume_dry_score, 5)
    reject_reasons 添加：股价处于近60日低位区，缩量不代表卖压衰竭
```

---

## 6.5 新增：放量滞涨封顶

如果出现放量但价格没有有效上涨，说明上方抛压仍在。

定义：

```text
近5天任一天 volume >= 1.5 * volume_ma20
且当天涨幅 < 1%
且 close_position < 0.5
```

其中：

```text
close_position = (close - low) / (high - low)
```

处理：

```text
volume_dry_score = min(volume_dry_score, 6)
warnings 添加：近5日存在放量滞涨，上方抛压仍在
```

---

## 6.6 原有大阴线封顶保留

原规则继续保留：

```text
近3天内有放量 >= 1.5 * volume_ma20
且单日跌幅 >= 3%
```

处理：

```text
volume_dry_score = min(volume_dry_score, 5)
reject_reasons 添加：近3日存在放量大阴线，卖压未释放完毕
```

---

# 7. 价稳评分优化

对应文件：

```text
analyzer/price_stable.py
```

---

## 7.1 保留原有价稳评分

原有 5 个维度继续保留：

```text
A. 振幅收缩
B. 无新低
C. 低点上移
D. 站上 MA20
E. ATR 收缩
```

总分仍为：

```text
0 ~ 10 分
```

---

## 7.2 Range 计算口径

统一使用百分比振幅：

```text
range_pct = (high - low) / close
```

计算：

```text
Range5 = 最近5个交易日 range_pct 平均值
Range20 = 最近20个交易日 range_pct 平均值
```

不得直接使用：

```text
high - low
```

避免不同价格区间股票不可比。

---

## 7.3 新增：收盘价紧致度

只看日内振幅不够，需要增加收盘价稳定性。

新增指标：

```text
close_tightness_5d = close_5d_max / close_5d_min - 1
```

评分建议：

```text
close_tightness_5d <= 3%：+2
close_tightness_5d <= 5%：+1
否则：+0
```

该指标可作为价稳评分的辅助项。

如果不想改变总分 10 分结构，可以将它作为 warning / positive_factor 输出。

推荐方式：

```text
不改变原有10分结构
新增字段 price_tightness_score，作为辅助解释
```

---

## 7.4 优化低点上移算法

当前 LocalLow 容易被单日异常下影线影响。

建议改为分位数口径：

```text
LocalLow1 = 最近20天中前10天 low 的 20% 分位数
LocalLow2 = 最近20天中后10天 low 的 20% 分位数
```

评分：

```text
LocalLow2 > LocalLow1：+2
LocalLow2 >= LocalLow1 * 0.98：+1
否则：+0
```

如果开发分位数不方便，可以先采用简单版本：

```text
LocalLow1 = 前10天最低价
LocalLow2 = 后10天最低价
```

但需要忽略异常针：

```text
如果某日 low 比前后两天 low 均低超过 5%，视为异常针，不参与 LocalLow 计算
```

---

## 7.5 优化 MA20 站上规则

原规则过硬：

```text
近5天全部站上 MA20：+2
1次跌破后恢复：+1
≥2次跌破：+0
```

改为：

```text
近5天 close 在 price_ma20 上方的天数
```

评分：

```text
>= 4 天在 MA20 上方：+2
>= 3 天在 MA20 上方，且最后一天 close > price_ma20：+1
否则：+0
```

---

## 7.6 新增：收盘位置评分

如果股票每天收在日内下半区，说明抛压仍在。

新增指标：

```text
close_position = (close - low) / (high - low)
```

计算：

```text
close_position_5d_avg = 最近5天 close_position 平均值
```

评分建议：

```text
>= 0.6：+2
>= 0.45：+1
< 0.45：+0
```

该指标不强制加入 10 分总分，但需要作为辅助输出：

```json
{
	"close_position_5d_avg": 0.62,
	"close_position_status": "收盘位置偏强"
}
```

---

## 7.7 新增：跌破关键支撑封顶

如果跌破柄底、平台下沿或 MA50，价稳不能高分。

触发条件：

```text
close < handle_low
或 close < support_low * 0.98
或 close < price_ma50
```

处理：

```text
price_stable_score = min(price_stable_score, 5)
reject_reasons 添加：跌破关键支撑，价格尚未稳定
```

---

## 7.8 原有价稳封顶保留

继续保留：

```text
近5天出现20日新低：
    price_stable_score = min(price_stable_score, 5)

连续下跌且跌幅放大：
    price_stable_score = min(price_stable_score, 5)
```

连续下跌且跌幅放大定义：

```text
近5天中至少4天收跌
且最近3天累计跌幅 <= -5%
且最近3天平均跌幅绝对值 > 前2天平均跌幅绝对值
```

---

# 8. 风险收益模块优化

对应文件：

```text
analyzer/risk_reward.py
```

如果当前没有该文件，需要新增。

---

## 8.1 明确入场区

新增低吸入场区计算。

优先级：

```text
1. 柄底低点 handle_low
2. 近10日支撑 support_10d
3. price_ma20 或 price_ma50 附近支撑
```

建议计算：

```text
entry_base = max(handle_low, support_10d)
entry_low = entry_base
entry_high = entry_base * 1.03
```

如果当前价格在：

```text
entry_low <= close <= entry_high
```

则认为：

```text
价格在低吸入场区内
```

如果：

```text
close > entry_high
且尚未突破 pivot
```

则返回：

```text
WAIT_ENTRY
拒因/提示：价格高于低吸区，等待回调
```

---

## 8.2 止损价计算

止损价不能只用固定百分比。

建议使用结构止损：

```text
stop_loss = min(handle_low, support_10d) * 0.98
```

如果有明确平台下沿：

```text
stop_loss = platform_low * 0.98
```

---

## 8.3 止损空间校验

计算：

```text
risk_pct = (entry_price - stop_loss) / entry_price * 100
```

硬性规则：

```text
risk_pct <= max_risk_percent
```

低吸规则：

```text
risk_pct <= low_buy_max_risk_percent
```

---

## 8.4 新增 ATR 止损合理性校验

固定止损百分比不适合所有股票。

计算：

```text
atr14_pct = ATR14 / close * 100
```

止损空间必须满足：

```text
risk_pct >= atr14_pct * 1.2
```

原因：

```text
如果止损距离小于正常波动，很容易被洗出去
```

如果不满足：

```text
decision = WAIT_ENTRY
warnings 添加：止损过近，容易被正常波动触发
```

---

## 8.5 RR1 目标位来源优化

RR1 必须基于真实压力位，而不是随意理论目标。

目标位优先级：

```text
1. 前高
2. 杯沿 / pivot
3. 平台上沿
4. 近期明显压力位
```

计算：

```text
target1 = 最近明确压力位
rr1 = (target1 - entry_price) / (entry_price - stop_loss)
```

不得直接使用过远的理论目标作为 RR1。

---

## 8.6 RR2 / RR3 可选

可以额外输出：

```text
target2 = 杯深等幅目标
target3 = 趋势延伸目标
```

但决策只使用：

```text
RR1
```

防止盈亏比虚高。

---

# 9. 决策流程优化

对应文件：

```text
analyzer/decision.py
```

---

## 9.1 新决策状态

新增枚举：

```python
class DecisionType:
    BUY_LOW = "BUY_LOW"
    WATCH_BREAKOUT = "WATCH_BREAKOUT"
    WAIT_VOLUME = "WAIT_VOLUME"
    WAIT_STABLE = "WAIT_STABLE"
    WAIT_ENTRY = "WAIT_ENTRY"
    WAIT_RR = "WAIT_RR"
    REJECT = "REJECT"
```

---

## 9.2 决策优先级

### 9.2.1 硬拒绝

满足以下任一条件，直接 REJECT：

```text
有效交易日不足80天
形态评分 < min_pattern_score
跌破关键支撑
近3日存在放量大阴线
近5日出现20日新低且未收复
risk_pct > max_risk_percent
```

---

### 9.2.2 等量能

```text
形态评分 >= min_pattern_score
但 volume_dry_score < min_volume_dry_score
```

返回：

```text
WAIT_VOLUME
```

---

### 9.2.3 等价格稳定

```text
形态评分 >= min_pattern_score
volume_dry_score >= min_volume_dry_score
但 price_stable_score < min_price_stable_score
```

返回：

```text
WAIT_STABLE
```

---

### 9.2.4 等入场区

```text
形态评分 >= low_buy_min_pattern_score
volume_dry_score >= min_volume_dry_score
price_stable_score >= min_price_stable_score
但 close > entry_high
且 close < pivot
```

返回：

```text
WAIT_ENTRY
```

---

### 9.2.5 盈亏比不足

```text
rr1 < min_rr1
```

返回：

```text
WAIT_RR
```

---

### 9.2.6 可低吸

满足：

```text
pattern_score >= low_buy_min_pattern_score
volume_dry_score >= low_buy_min_volume_dry
price_stable_score >= low_buy_min_price_stable
risk_pct <= low_buy_max_risk_percent
rr1 >= min_rr1
entry_low <= close <= entry_high
```

返回：

```text
BUY_LOW
```

---

### 9.2.7 等突破确认

满足：

```text
pattern_score >= low_buy_min_pattern_score
volume_dry_score >= min_volume_dry_score
price_stable_score >= min_price_stable_score
risk_pct <= max_risk_percent
rr1 >= min_rr1
但价格不在低吸区
且未明显追涨
```

返回：

```text
WATCH_BREAKOUT
```

---

# 10. 配置项优化

对应文件：

```text
config.yaml
```

新增或调整：

```yaml
decision:
  min_pattern_score: 8
  min_volume_dry_score: 6
  min_price_stable_score: 6

  max_risk_percent: 10
  min_rr1: 2.0

  chase_threshold_pct: 5

  low_buy_min_pattern_score: 13
  low_buy_min_volume_dry: 7
  low_buy_min_price_stable: 7
  low_buy_max_risk_percent: 6

volume_dry:
  bad_shrink_enabled: true
  bad_shrink_max_score: 6
  bad_shrink_slope_threshold_pct: -3

  min_position_60d_normal: 0.5
  min_position_60d_warning: 0.3
  low_position_max_score: 6
  very_low_position_max_score: 5

  volume_stall_multiplier: 1.5
  volume_stall_max_score: 6

  big_bear_volume_multiplier: 1.5
  big_bear_drop_pct: 3
  big_bear_max_score: 5

price_stable:
  range_shrink_strong: 0.6
  range_shrink_normal: 0.8

  atr_shrink_strong: 0.75
  atr_shrink_normal: 0.9

  close_tightness_strong_pct: 3
  close_tightness_normal_pct: 5

  ma20_days_strong: 4
  ma20_days_normal: 3

  support_break_buffer_pct: 2
  support_break_max_score: 5

risk_reward:
  entry_zone_pct: 3
  stop_loss_buffer_pct: 2

  atr_stop_multiplier: 1.2

  target1_source_priority:
    - previous_high
    - pivot
    - platform_high
    - resistance
```

---

# 11. 输出字段要求

每只股票最终输出结构建议如下：

```json
{
	"symbol": "300820",
	"name": "英杰电气",

	"decision": "BUY_LOW",
	"decision_label": "可低吸",

	"pattern_score": 14,
	"volume_dry_score": 7,
	"price_stable_score": 8,

	"price_tightness_score": 2,
	"close_position_5d_avg": 0.62,

	"entry_zone": {
		"entry_low": 42.5,
		"entry_high": 43.78,
		"current_price": 43.1,
		"in_entry_zone": true
	},

	"risk_reward": {
		"entry_price": 43.1,
		"stop_loss": 40.8,
		"risk_pct": 5.34,
		"atr14_pct": 3.1,
		"target1": 48.5,
		"rr1": 2.35
	},

	"positive_factors": [
		"近5日成交量低于MA50的65%",
		"近10日未创新低",
		"近5日收盘价波动小于3%",
		"止损空间小于6%",
		"RR1大于2"
	],

	"warnings": ["价格接近入场区上沿"],

	"reject_reasons": []
}
```

---

# 12. 前端展示建议

前端不要只展示一个分数，应展示：

```text
1. 最终状态
2. 形态分
3. 量干分
4. 价稳分
5. 入场区
6. 止损价
7. 目标价
8. 盈亏比
9. 拒因
10. 风险提示
```

建议颜色：

```text
BUY_LOW：绿色
WATCH_BREAKOUT：蓝色
WAIT_VOLUME / WAIT_STABLE / WAIT_ENTRY / WAIT_RR：黄色
REJECT：灰色或红色
```

---

# 13. 验收标准

## 13.1 量干验收

需要覆盖以下场景：

```text
1. 正常缩量横盘：量干分应较高
2. 缩量阴跌：量干分最高不超过6
3. 近3日放量大阴线：量干分最高不超过5
4. 放量滞涨：量干分最高不超过6
5. 股价处于60日极低位：不能直接判定为健康量干
```

---

## 13.2 价稳验收

需要覆盖以下场景：

```text
1. 振幅收缩且低点上移：价稳分较高
2. 近5日出现20日新低：价稳分最高不超过5
3. 跌破柄底 / 平台下沿：价稳分最高不超过5
4. 收盘价持续下移：不能给高价稳分
5. 围绕MA20轻微震荡但最后收复：不应过度扣分
```

---

## 13.3 风险收益验收

需要覆盖以下场景：

```text
1. 当前价格在低吸区内，风险小，RR达标：BUY_LOW
2. 当前价格高于低吸区但未突破：WAIT_ENTRY
3. 当前价格接近突破位，量价达标：WATCH_BREAKOUT
4. 止损空间过大：REJECT 或 WAIT_ENTRY
5. 止损空间过小，小于 ATR 正常波动：WAIT_ENTRY
6. RR1 不足 2：WAIT_RR
```

---

## 13.4 决策验收

最终结果必须能解释：

```text
为什么可低吸
为什么等突破
为什么继续观察
为什么拒绝
```

不得只返回：

```text
true / false
```

必须返回：

```text
decision
positive_factors
warnings
reject_reasons
```

---

# 14. 开发注意事项

## 14.1 不要让指标过度复杂

本次优化重点是：

```text
减少误判
提升解释能力
明确风险边界
```

不要引入过多新指标导致系统难以维护。

---

## 14.2 所有封顶规则必须可解释

例如：

```text
量干原始分 8 分
但因为出现放量滞涨
最终分被封顶到 6 分
```

需要输出：

```json
{
	"raw_volume_dry_score": 8,
	"volume_dry_score": 6,
	"score_caps": ["放量滞涨，量干最高6分"]
}
```

---

## 14.3 不要删除原始评分细节

每个评分维度都要保留明细：

```json
{
	"volume_dry_detail": {
		"v5_vs_ma20": {
			"value": 0.76,
			"score": 2
		},
		"v5_vs_ma50": {
			"value": 0.63,
			"score": 2
		},
		"volume_decline_sequence": {
			"v1": 1200000,
			"v2": 880000,
			"v3": 620000,
			"score": 2
		}
	}
}
```

方便前端展示和排查。

---

# 15. 最终效果

优化后系统应具备以下能力：

```text
1. 能识别真正健康的缩量
2. 能过滤缩量阴跌
3. 能过滤破位后缩量
4. 能判断价格是否真正稳定
5. 能判断低吸位置是否安全
6. 能判断止损是否合理
7. 能判断盈亏比是否真实
8. 能输出清晰拒因
9. 能给前端展示完整解释
10. 能区分可低吸、等突破、等回调、继续观察和拒绝
```

最终策略原则：

```text
只在形态成熟、量能干净、价格稳定、风险极小、盈亏比真实的位置出手。
```

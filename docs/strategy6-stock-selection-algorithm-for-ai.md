# 策略6选股算法执行说明（供 AI 实现与选股）

> 文档口径：以当前策略6生产代码为准，采用“快速理解层 + 精确执行附录”。
> 适用目标：让另一个已经具备个股日线和宽基指数日线的 AI，能够独立复现策略6的判断、评分、分层和 VCP 确认候选池。
> 不在范围：行情获取、复权实现、数据库、任务调度、API、前端。
> 价格口径：所有个股价格使用同一套前复权日线；不得混用不同复权口径。策略输出是收盘后研究信号，不等同于真实成交回报。

---

## 第一部分：快速理解层

## 1. 策略目标

策略6用于寻找以下类型的股票：

1. 最近出现过可信的强势启动，而不是长期无趋势横盘。
2. 启动后形成独立整理，涨幅没有被完全回吐，抛压逐步衰减。
3. 当前价格靠近有效支撑或处于可确认的支点突破位置。
4. 尾部呈量干、价稳、紧密排列或 Brooks 卖压衰竭结构。
5. 客观上方空间相对止损风险足够大。
6. 没有放量破位、连续跌破支撑、趋势明显失效等硬伤。

策略6不是“看到 VCP 就买”。VCP 只是主链的形态证据之一；正式候选还必须经过流动性、强势启动、支撑、尾部、盈亏比和风险过滤。

## 2. 两条独立输出链

### 2.1 正式候选主链

主链输出四种结果：

| 类型 | 中文含义 | 核心语义 |
| --- | --- | --- |
| `READY_CANDIDATE` | 低吸候选 | 已在支撑区内，质量、量价和盈亏比均达到最高门槛 |
| `KEY_CANDIDATE` | 重点候选 | 结构质量较高，等待支撑低吸或突破确认 |
| `WATCH_CANDIDATE` | 观察候选 | 部分条件已满足，仍缺交易触发、明确形态或多路径确认 |
| `REJECTED` | 排除 | 存在硬性风险、盈亏比不足或评分不足 |

### 2.2 VCP 持续观察池

这是独立于正式候选主链的观察层：

- **VCP 早期观察**：当前形成 1 个完整收缩轮次，并满足历史正式候选资格；下一轮可以处于形成中，但不是准入必需条件。
- **VCP 确认候选**：当前形成至少 2 个完整且递进收缩的轮次，并满足历史正式候选资格。
- VCP 质量分只负责该观察池内部排序和解释。
- VCP 质量分不得加入主链总分，不得绕过主链硬过滤，不得直接生成买入结论。

## 3. 总体执行顺序

必须按以下顺序执行，不能先评分再补过滤：

```text
准备截至 evaluation_date 的可见日线
  -> 基础指标与流动性
  -> 独立 VCP 观察识别
  -> 宽基市场环境与相对强度
  -> 强势启动识别
  -> 启动/整理/尾段严格分段
  -> 杯柄/VCP/平台形态识别
  -> 支撑簇与支撑反应
  -> 整理质量
  -> 原始量干价稳尾部
  -> 稳定箱体尾部
  -> Brooks 尾部
  -> 三路径合并
  -> 入场原型与客观交易计划
  -> 七维总评分
  -> 硬过滤
  -> VCP 基础过滤
  -> 正式候选分层
  -> 市场偏弱时记录降级前等级
  -> VCP 历史正式候选逐日回放与观察池分层
```

## 4. 最小输入约定

另一个 AI 已有数据时，只需满足以下契约：

### 4.1 个股日线

- 按交易日升序。
- 截止 `evaluation_date`，严禁包含未来交易日。
- 每行至少包含：`date/open/high/low/close/volume/amount`。
- OHLC 必须为正且满足 `low <= open,close <= high`。
- `amount` 单位必须可统一换算为亿元。
- 全部股票价格字段使用同一种前复权口径。

### 4.2 指数日线

至少提供上证指数、深证成指、创业板指和沪深300，并同样截断到 `evaluation_date`。市场状态使用前三个宽基指数；个股 RS20 使用沪深300。

### 4.3 无未来数据原则

对历史日期 T 选股时，所有均线、支撑、形态、启动、市场环境和历史候选资格只能使用 `date <= T` 的数据。信号在 T 日收盘后形成，最早只能从下一交易日执行。

## 5. 主链快速判定伪代码

```python
def evaluate_strategy6(stock_rows, index_rows, evaluation_date, cfg):
    rows = rows_up_to(stock_rows, evaluation_date)
    market = index_rows_up_to(index_rows, evaluation_date)

    ind = calculate_indicators(rows)
    vcp_obs = evaluate_vcp_observation(rows, cfg)
    market_ctx = evaluate_market_context(market, evaluation_date)
    ind.rs20 = stock_return_20(rows) - hs300_return_20(market)

    start = evaluate_strong_start(rows, ind, cfg)
    phase = segment_phases(rows, start, cfg)
    pattern = detect_pattern(rows, phase, cfg)
    support = evaluate_support(rows, ind, start, pattern, cfg)
    quality = evaluate_setup_quality(rows, start, phase, market)

    original_tail = evaluate_dry_tail(rows, ind, phase, cfg)
    box_tail = evaluate_box_tail(rows, phase, support, original_tail, cfg)
    brooks_tail = analyze_brooks_tail(rows, ind, start, phase, support, original_tail, cfg)
    paths = combine_tail_paths(original_tail, box_tail, brooks_tail)

    entry_type = identify_entry_archetype(rows, ind, support, brooks_tail, cfg)
    plan = calculate_trade_plan(ind, support, cfg, entry_type)
    score = score_strategy6(ind, start, phase, pattern, support, paths, quality, plan)

    rejects = hard_filter_reasons(rows, ind, start, phase, pattern,
                                  support, original_tail, box_tail,
                                  brooks_tail, quality, plan, cfg)
    vcp_obs = apply_vcp_base_filters(vcp_obs, rejects)
    result = classify_candidate(ind, start, phase, pattern, support,
                                original_tail, box_tail, brooks_tail,
                                quality, plan, score, rejects, cfg)
    return result, vcp_obs
```

---

## 第二部分：精确执行附录

## 6. 基础门槛与市场环境

### 6.1 默认基础门槛

| 项目 | 默认值 |
| --- | ---: |
| 最低交易日数 | 500 |
| 60日平均成交额 | >= 3亿元 |
| 30日平均成交额 | >= 5亿元 |
| 10日平均成交额 | >= 5亿元 |
| 10日/30日平均成交额 | >= 0.80 |
| 个股20日相对沪深300强度 | >= 10%（指数可观测时） |
| 收盘相对MA250 | 必须 `close > MA250` |
| MA120相对MA250 | 必须 `MA120 > MA250` |
| 收盘相对MA50 | 必须 `close >= MA50 * 0.92` |

### 6.2 市场状态

上证、深证、创业板三个指数中，至少两个指数必须拥有不少于50根且最新日期等于评估日的数据，否则市场状态为 `UNKNOWN`。

对每个指数计算：

- `close >= MA20`
- `MA20 >= MA50`
- 弱势：`close < MA20` 且当前 MA20 低于5日前的 MA20
- 放量下跌风险：最近5日中至少3日跌幅 `<= -1.5%`，且成交量 `>=` 之前20日均量的1.2倍

聚合状态：

1. 任一可观测指数出现放量下跌风险：`MARKET_RISK`。
2. 过半可观测指数为弱势：`MARKET_WEAK`。
3. 至少2个指数站上MA20，且至少1个指数MA20站上MA50：`MARKET_STRONG`。
4. 其他：`MARKET_NEUTRAL`。

生产默认 `market_filter_mode=downgrade`。市场为弱势/风险、市场未知或沪深300缺失时，不改变主链总分，但禁止升级为重点/低吸，只能保留为观察候选。只有 `MARKET_WEAK` 或 `MARKET_RISK` 导致的降级会额外记录降级前真实等级；市场未知或沪深300缺失只记录数据不可用警告。

## 7. 强势启动

在最近60个交易日中选择“质量优先、质量接近时较新优先”的启动事件。有效启动类型：

1. `NORMAL_STRONG_BREAKOUT`
   - 当日涨幅 `>= 7%`
   - 当日量 / 前20日均量 `>= 2.0`
   - 收盘位置 `(close-low)/(high-low) >= 0.65`
   - 成交额 `>= 2亿元`
   - 当日成交额在此前60日中的分位 `>= 90%`
2. `VOLUME_LIMIT_UP`：涨停且量比 `>= 1.5`。
3. `LOW_VOLUME_LIMIT_UP`：涨停且量比在 `[0.6, 1.5)`。
4. `ONE_WORD_LIMIT_UP`：一字涨停。
5. 若以上均无有效事件，可用 B 级动量启动：5日涨幅 `>=8%`、或10日 `>=12%`、或20日 `>=20%`。

启动事件的后续5日质量分满分20，考虑启动类型、涨幅、量比、收盘位置、成交额分位、涨幅保留和跟随上涨。以下情况会使事件失效或显著降分：

- 后续跌破启动日低点。
- 3日以上观察后，涨幅几乎完全回吐到启动前收盘的0.5%以内。
- 后续出现跌幅 `<= -4%` 且成交量 `>=` 前一日1.2倍的派发日。

事件质量：S `>=16`，A `>=11`，B `>=8`。正式重点和低吸候选不接受 B 级启动。

此外必须出现高位确认：最近20日最高收盘达到120日最高收盘，或至少达到其98%。

## 8. 严格分段

启动日、整理区和尾段不能重叠：

```text
启动日 = start_index
整理区 = start_index + 1 ... tail_start_index - 1
尾段   = tail_start_index ... evaluation_date
```

默认约束：

- 启动距评估日5至60个交易日。
- 整理区5至40个交易日。
- 固定尾段为最近5日。
- 动态尾段可在3至10日中选择；与此前20日相比，振幅、ATR、均量、平均实体四项中至少3项收缩，阈值分别为0.75、0.80、0.80、0.80，且尾段无放量大跌。
- 动态条件不成立时回退到固定5日尾段。

当前原始量干价稳路径仍要求至少5根尾段K线。因此动态分段若选出3至4日，只能提供分段证据，原始尾部会因基准不足而不通过，仍需箱体或 Brooks 路径提供辅助证据。复现当前代码时不得悄悄取消这项限制。

启动不足5日时属于 `START_CONFIRMED` 观察状态，不应伪造完整整理和交易计划。

## 9. 形态识别

形态只使用整理区，评估日K线不进入形态边界，避免用信号日反向抬高支点。识别优先级为：杯柄 -> VCP -> 平台。

生产默认 `pattern_filter_mode=score_only`：未识别形态不会单独硬性排除，但得不到形态分；若改为 `downgrade` 则只能观察，改为 `strict` 才硬排除。

### 9.1 VCP 完整轮次

一轮必须是完整的“下跌 + 修复”：

```text
起始峰值 -> 最终低点 -> 已确认反弹峰值
```

弱反抽后继续创新低时仍属于同一轮，不能人为切成新一轮。反弹峰值须满足以下任一确认方式：

- 直接突破本轮起始峰值，且当日涨幅 `>=5%` 或量比 `>=1.2`；或
- 从低点反弹 `>=3%`，形成局部峰值，低点后至少连续2日收盘不低于该低点，并且反弹峰值后至少已有一个交易日用于确认。

第一轮振幅必须在8%至32%之间。第二轮及以后必须同时满足：

- 振幅 `<` 上一轮振幅的90%。
- 下跌段平均成交量 `<` 上一轮的90%。
- 本轮最低收盘 `>=` 上一轮最低收盘的97%。

主链确认 VCP 还要求：

- 至少2个完整轮次。
- 当前收盘距最后反弹支点不超过下方5%，即 `close >= pivot * 0.95`。

VCP 原始形态分为 `min(20, 16 + 完整轮数)`。

主链 VCP 形态分还有两个独立加分项，但形态维度总分仍封顶15：

- 每轮不创新低，且相邻轮次低点平均抬高 `>=1%`：`+2`。
- 每轮高点不抬高，同时每轮低点严格抬高：`+2`。

### 9.2 杯柄

- 整理区至少12日。
- 柄部取最后3至5日。
- 杯深12%至35%。
- 右侧最高收盘 / 左侧高点在 `[0.90, 1.00]`。
- 柄深不超过杯深的1/3。
- 柄部均量低于右侧最近均量。
- 固定原始形态分19。

### 9.3 平台

- 至少5日。
- 全区间高低振幅 `<=12%`。
- 后半段最低价 `>=` 前半段最低价的98%。
- 后半段均量低于前半段。
- 当前价距平台顶或平台底不超过5%。
- 固定原始形态分15。

## 10. 支撑簇

候选支撑及权重：

| 来源 | 权重 |
| --- | ---: |
| 形态低点/平台低点 | 1.5 |
| MA20 | 1.3 |
| 前10日最低收盘/最低价、前20日最低收盘、启动低点 | 1.2 |
| MA10 | 1.0 |
| MA5 | 0.8 |

前10/20日低点必须排除评估日自身。只保留不高于当前价103%的候选支撑。

把价格距离不超过 `max(当前价*1.5%, ATR14*0.5)` 的候选合并成支撑簇，簇价格采用权重加权平均。选择综合分最高且含结构来源的簇作为关键支撑。簇分满分20：

- 来源权重分：`min(12, round(权重和*3))`
- 多来源重合：`min(5, (来源数-1)*2)`
- 距当前价：3%内5分，6%内3分，否则1分
- 最近10日测试：至少2次3分，1次2分

支撑区宽度：

```text
zone_width = max(current_price * 1%, ATR14 * 0.3)
support_zone = [key_support - zone_width, key_support + zone_width]
```

支撑反应分满分10：低量测试 `+3`；测试后3日最高收盘较支撑反弹至少2% `+3`，不跌则 `+1`；独立测试至少2次 `+2`；没有放量跌破后无法收复 `+2`；最近反应显著弱于上次 `-2`。

放量跌破支撑且3日内未收复属于硬风险。

## 11. 整理质量分（25分）

| 维度 | 分值规则 |
| --- | --- |
| 启动涨幅保留 | >=75%:6；>=55%:4；>=35%:2 |
| 派发日数量 | 0:5；1:3；2:1；>=3:0 |
| 上涨日/下跌日均量比 | >=1.2:4；>=0.9:2 |
| 尾段/基准波动收缩 | <=0.65:5；<=0.80:3；<=1.0:1 |
| RS斜率趋势 | 改善3；稳定2；混合1；衰退0 |
| 失败突破次数 | 0:2；1:1；>=2:0 |

派发日定义：跌幅 `<=-2%`，且当日量同时不低于前一日和此前20日均量。

重点候选要求整理质量分 `>=14`，低吸候选要求 `>=18`。派发日达到3日并形成高派发压力时属于硬排除。

## 12. 三条尾部路径

### 12.1 原始量干价稳路径（主路径）

默认最近5日对比尾段之前20日：

- 尾段均量/前20日均量 `<=0.75`；`<=0.60` 为强量干。
- 5日收盘振幅 `<=8%`。
- 5日收益 `>=-6%`。
- 最近单日跌幅不能 `<=-4%`。
- 尾段最低收盘不得低于前尾段最近5日最低收盘。
- 尾段后半最低价不得低于前半最低价的99%。
- 不得出现跌幅 `<=-7%` 且量比 `>=1.5` 的放量大跌。

该路径满分20，但合并到主链尾部分时按通过状态计分。

### 12.2 稳定箱体路径（辅助路径）

在整理阶段枚举5至30日窗口。最后2日只用于确认跌破和当前位置，不参与箱体上下边界，避免跌破日重新定义箱底。

普通通过要求：

- 箱体宽度 `<=18%`。
- 至少2次独立箱底测试。
- 后半段收盘中位数相对前半段不低于 `-3%`。
- 后半段/前半段均量 `<=0.85`。
- 当前收盘在箱体上下沿各3%的容差内。
- 尾段量比 `<=0.75`。
- 无放量杀跌、关键支撑跌破或箱体有效跌破。

紧密K线额外检查最近5日：平均实体 `<=2.5%`、最大实体 `<=4%`、收盘区间 `<=5%`、至少3组相邻K线重叠率 `>=50%`、无超过3%的跳空、ATR5/ATR20 `<=0.80`。紧密K线只用于箱体窗口择优和解释，不直接加入最终主链尾部分。

### 12.3 Brooks 尾部路径（辅助路径）

Brooks 路径独立检查：

- 启动背景及MA20斜率没有进入持续下降趋势。
- 最近7日强阴线、阴线跟随和连续阴线数量受控。
- 最近5日收盘范围、ATR和实体收缩，低点不连续恶化。
- 尾段量比 `<=0.75`，无放量下跌。
- 关键支撑未被连续2日有效跌破3%。
- 存在二次入场、失败突破收复或紧密结构等价格行为证据。
- Brooks 分数至少14分才通过，17分以上为优质；但还需单独判断交易触发是否就绪。

Brooks 路径的详细子阈值应使用本文末尾默认参数表，不得凭主观K线观感替代。

### 12.4 路径合并与降级

```text
original_pass = 原始量干价稳通过
box_pass      = 稳定箱体通过
brooks_pass   = Brooks通过

tail_score =
    10 if original_pass else 0
  + 3  if box_pass else 0
  + 2  if brooks_pass and Brooks交易触发就绪 else 0
  + 2  if 至少两条路径通过 else 0
上限15分
```

重要限制：

- 原始路径单独通过，可以继续竞争重点或低吸。
- 原始路径未通过、只有箱体或只有 Brooks 一条辅助路径通过时，只能是观察候选。
- Brooks 结构通过但交易触发未就绪时，只能观察。
- 箱体和 Brooks 两条辅助路径同时通过，可形成多路径确认，但仍不能绕过结构性硬风险。

## 13. 入场原型与交易计划

入场原型按以下优先级判断：

1. `FAILED_BREAKOUT_RECLAIM`：Brooks 失败突破收复触发已确认。
2. `PIVOT_BREAKOUT`：当前价刚高于支点、未超过支点8%，量比 `>=1.3`，收盘位置 `>=0.65`。
3. `SUPPORT_PULLBACK`：当前价在关键支撑区上沿102%以内，或距战术支撑不超过 `max(当前价*1%, ATR14*0.3)`。
4. `WAIT_BREAKOUT`：当前价仍低于支点且支撑有效。
5. `NONE`。

### 13.1 止损

- 支点突破/等待突破：`pivot - max(pivot*1%, ATR14*0.5)`。
- 失败突破收复：取入场价下方较高的战术/关键支撑，再减 `max(支撑*1%, ATR14*0.5)`。
- 支撑低吸：取不高于入场价的较高战术/关键支撑，再减 `max(支撑*3%, ATR14*0.8)`。

### 13.2 客观目标

上方压力候选包括支点、20日最高收盘、120日最高收盘、250日最高收盘。目标结合最近压力、形态高度和ATR计算：

- 目标1优先取最近有效压力，否则取 `min(pivot+0.8*形态高度, entry+3*ATR)`。
- 目标2取形态高度目标、`entry+4*ATR` 和 `entry*(1+35%)` 的较小值。
- 突破历史250日最高收盘时，目标2可使用 `pivot+完整形态高度`；否则同样受最近压力约束。

客观盈亏比：

```text
risk = planning_entry - stop
objective_rr_2 = (objective_target_2 - planning_entry) / risk
```

最低门槛：观察1.5，重点2.0，低吸2.5。低于1.5直接硬排除。

信号在评估日收盘后产生；有效期从下一工作日开始，默认3个工作日。等待突破状态只提供计划价，不代表已下单。

## 14. 主链总评分（100分）

| 维度 | 上限 | 计算摘要 |
| --- | ---: | --- |
| 强势启动 | 15 | 启动事件质量20分按比例缩放 |
| 形态 | 15 | 原始形态20分缩放至12 + 动态尾段分段最多3 + VCP两个结构奖励 |
| 支撑 | 15 | 支撑簇20分缩放至10 + 支撑反应最多5 |
| 尾部路径 | 15 | 原始10 + 箱体3 + Brooks触发2 + 多路径2，封顶15 |
| 整理质量 | 25 | 第11节六维质量分 |
| 客观盈亏比 | 10 | RR>=3:10；>=2.5:8；>=2:6；>=1.5:3 |
| 市场相对强度/风险 | 5 | RS20和无大盘风险/个股压力组合 |

总分为七项之和，封顶100。总分不是硬风险的替代品；高分股票仍可能因支撑、盈亏比、放量破位或流动性被排除。

## 15. 硬过滤清单

任一命中即不能成为正式候选：

1. 分段无效：启动过旧、整理过短/过长、顺序错误；启动过新是观察例外。
2. 严格形态模式下未识别形态。
3. 交易日不足、均线计算失败。
4. `close <= MA250` 或 `MA120 <= MA250`。
5. 60/30/10日成交额或10日/30日成交额比例不达标。
6. 沪深300可观测时，RS20低于10%。
7. 无有效强势启动或没有接近/创120日新高确认。
8. 不同启动等级对应的5/10日振幅、20日回撤超限；绝对10日振幅>50%或20日回撤<-35%。
9. 支撑失败或最近10日没有有效支撑测试。
10. 当前价突破支点超过8%。
11. 收盘低于关键支撑、低于关键支撑4%、连续2日低于前关键支撑，或低于MA50的92%。
12. 放量大跌、尾段创新低、尾段低点继续下降、5日收益过弱、最近单日跌幅过弱。
13. 原始尾部失败且箱体、Brooks也不能提供有效替代路径时，保留完整尾部失败原因。
14. 派发日>=3形成高派发压力。
15. 放量跌破支撑后未收复。
16. 客观RR2低于1.5。
17. 最新交易日停牌或无交易数据。

## 16. 正式候选分层

在没有硬过滤原因后，按以下优先级分层。

### 16.1 低吸候选

必须全部满足：

- 总分 `>=85`。
- 客观RR2 `>=2.5`。
- 当前价处于关键支撑区内。
- 原始尾段量比 `<=0.60`。
- 支撑状态有效。
- 启动不是B级。
- 整理质量 `>=18`。
- 支撑反应 `>=5`。
- 无放量大跌、市场阻塞和战术压力阻塞。

### 16.2 重点候选

必须全部满足：

- 总分 `>=75`。
- 客观RR2 `>=2.0`。
- 支撑状态有效。
- 尾部路径分 `>=15`。
- 启动不是B级。
- 整理质量 `>=14`。
- 支撑反应 `>=3`。
- 无放量大跌、市场阻塞和战术压力阻塞。

### 16.3 强制观察情形

即使没有硬过滤，以下情况也只能观察：

- 启动过新，尚无独立整理。
- Brooks 通过但交易触发未确认。
- 等待支点突破。
- 原始尾部未通过且只有一条辅助路径通过。
- `pattern_filter_mode=downgrade` 且形态未知。
- 市场弱势/风险、市场未知或沪深300缺失。
- 上影压力、临近上方压力或一字板启动尚未充分确认。

其他股票若总分 `>=60` 或客观RR2 `>=1.5`，可进入观察；否则排除。

## 17. VCP 持续观察池精确规则

### 17.1 当前结构资格

先按第9.1节识别当前 VCP：

- 1轮完整结构：`VCP_ROUND1_CONFIRMED`，只进入早期观察；下一轮形成状态仅作为附加证据。
- 至少2轮：`VCP_CONFIRMED`，可进入 VCP 确认候选。
- 价格在支点下方5%以内：`VCP_NEAR_PIVOT`。
- 突破支点且涨幅>=5%或量比>=1.2：突破确认。
- 突破后默认保留10个交易日；超过则观察过期。
- 当前价高于支点8%以上：`VCP_EXTENDED`，不再视为合适的近支点机会。
- 收盘跌破最后一轮结构低点3%，或突破后出现放量跌破且3日未收复支点：VCP失效。
- 必须在第一轮峰值之前找到可信强势启动锚点，否则不具备观察池资格。

### 17.2 “历史正式候选”门槛

VCP 观察池不是纯形态扫描。必须从当前 VCP 强势起点到评估日，逐日按当时可见数据重放完整策略6主链，并找到至少一次非 `REJECTED` 的正式候选记录。

历史资格不是永久保留。若历史候选发生在当前第一轮起点之前，候选日至第一轮起点必须同时满足：

- 第一轮起点相对历史候选收盘的跌幅不超过15%。
- 期间滚动最高收盘到后续收盘的最大回撤不超过20%。
- 第一轮起点末尾连续 `close < MA20 < MA50` 的天数少于5日。

任一失败，更早的候选记录不能继续救回该股票；必须等待后续重新成为正式候选，建立新的 VCP 周期。

### 17.3 VCP 质量分（只排序，不决策）

至少2轮才计算，模型版本 `VCP_QUALITY_V3`：

| 维度 | 上限 | 规则摘要 |
| --- | ---: | --- |
| 收缩轮数 | 15 | 2轮10，3轮13，4轮以上15 |
| 振幅收缩 | 20 | 相邻振幅比平均评分15 + 最后一轮振幅5 |
| 成交量收缩 | 20 | 相邻下跌段均量比平均评分15 + 末轮/首轮总量比5 |
| 低点质量 | 15 | 平均抬高>=2%得15；不下降13；下降<=1%得10；<=2%得6；<=3%得2 |
| 启动涨幅保留 | 10 | 最后低点不低于启动收盘10；回撤<=5%得7；<=10%得3 |
| 总时长 | 5 | 12-45日得5；8-55日得3；其他1 |
| 相邻支点清晰度 | 10 | 差<=3%得10；<=5%得6；<=8%得2 |
| 突破确认 | 5 | 最后一轮直接突破确认得5 |
| 低点平均抬高奖励 | 2 | 每轮不创新低且平均抬高>=1% |
| 高点不升低点抬高奖励 | 2 | 每轮高点不抬高且低点严格抬高 |

振幅相邻比评分：`<=0.35:15, <=0.50:12, <=0.65:9, <=0.80:6, <=0.90:3`。
最后振幅评分：`<=3%:5, <=5%:4, <=8%:3, <=10%:2`。
成交量相邻比评分：`<=0.50:15, <=0.65:12, <=0.75:9, <=0.85:6, <=0.90:3`。
末轮/首轮成交量比：`<=0.35:5, <=0.50:4, <=0.65:3, <=0.80:2, <=0.90:1`。

质量等级：TOP `>=90`，HIGH `>=80`，GOOD `>=70`，NORMAL `>=60`，否则 WEAK。若最后一轮振幅小于1%且仅用1日完成下跌，视为微型噪声，质量分最高79。

再次强调：该质量分只用于“VCP确认候选”板块排序与解释，不进入主链100分。

## 18. 输出字段建议

另一个 AI 至少应输出：

```text
code, name, evaluation_date
candidate_type, display_group, lifecycle_status, decision_reason
total_score
strong_start_score, pattern_score, support_score, tail_score
setup_quality_score, objective_rr_score, market_rs_risk_score
start_date, start_type, start_grade, days_since_start
pattern_type, pattern_start_date, pattern_end_date, contraction_count
key_support, tactical_support, support_zone_low, support_zone_high, pivot_price
entry_archetype, buy_zone_low, buy_zone_high, stop_loss
objective_target_1, objective_target_2, objective_rr_1, objective_rr_2
tail_paths, primary_tail_path
market_status, rs20, pre_market_candidate_type
reject_reasons, risk_tags, warn_tags
vcp_pool_type, vcp_lifecycle_status, vcp_quality_score, vcp_quality_grade
vcp_rounds, vcp_historical_candidate_date, vcp_historical_candidate_type
```

旧字段兼容时，不得删除已有字段；没有计算出的值用 `null` 或明确的 `UNKNOWN`，不要伪造为0分。

## 19. 默认参数汇总

```yaml
minimum_trading_days: 500
min_avg_amount_60d_yi: 3
min_avg_amount_30d_yi: 5
min_avg_amount_10d_yi: 5
amount10_vs_30_min_ratio: 0.80
enable_market_filter: true
market_filter_mode: downgrade
min_relative_strength_20: 0.10

start_lookback_days: 60
start_age_min_days: 5
start_age_max_days: 60
consolidation_min_days: 5
consolidation_max_days: 40
tail_window_days: 5

normal_start_return: 0.07
normal_start_volume_ratio: 2.0
normal_start_close_position: 0.65
normal_start_min_amount_yi: 2
normal_start_self_amount_percentile: 0.90
limit_up_volume_ratio: 1.5
low_volume_limit_up_min_ratio: 0.6
near_120d_high_ratio: 0.98

pattern_filter_enabled: true
pattern_filter_mode: score_only
pattern_pivot_proximity_pct: 0.05
breakout_extended_max_pct: 0.08
vcp_contraction_range_ratio: 0.90
vcp_contraction_volume_ratio: 0.90
vcp_min_first_range: 0.08
vcp_first_contraction_max_range: 0.32
vcp_rebound_min_pct: 0.03
vcp_rebound_confirm_days: 2
cup_depth_min: 0.12
cup_depth_max: 0.35
platform_max_range: 0.12

support_cluster_price_pct: 0.015
support_cluster_atr_multiplier: 0.5
support_zone_price_pct: 0.01
support_zone_atr_multiplier: 0.3
support_test_lookback: 10

tail_close_range_5: 0.08
tail_volume_ratio_5_20: 0.75
tail_strong_volume_ratio_5_20: 0.60
tail_min_return_5: -0.06
tail_min_return_3: -0.04
big_down_return: -0.07
big_down_volume_ratio: 1.5

rr2_min_watch: 1.5
rr2_min_key: 2.0
rr2_min_ready: 2.5
target_2_cap_pct: 0.35
stop_key_support_pct: 0.03
stop_atr_multiplier: 0.8
buy_zone_valid_days: 3
watch_min_score: 60
key_min_score: 75
ready_min_score: 85
setup_quality_min_key: 14
setup_quality_min_ready: 18
support_reaction_min_key: 3
support_reaction_min_ready: 5

vcp_observer_lookback_days: 60
vcp_observer_breakout_retention_days: 10
vcp_observer_extension_pct: 0.08
vcp_history_max_start_loss_pct: 0.15
vcp_history_max_drawdown_pct: 0.20
vcp_history_bearish_trend_days: 5
```

箱体和 Brooks 的详细默认参数见第12节；实现时应保持为独立配置组，不能把其辅助路径阈值偷换为原始尾部阈值。

## 20. 绝对禁止的错误实现

1. 不得使用评估日之后的数据计算形态、支撑、市场环境或历史资格。
2. 不得把 VCP 质量分加入主链总分。
3. 不得把“当前识别到 VCP”直接当作正式候选。
4. 不得把一次弱反抽后的继续下跌拆成新的 VCP 轮次。
5. 不得用评估日自身重新定义形态支点或前关键支撑。
6. 不得让单一箱体路径或单一 Brooks 路径直接升级为重点/低吸。
7. 不得因为总分高而忽略硬过滤。
8. 不得把市场偏弱误写成扣主链总分；默认语义是候选等级降级并保留原等级审计。
9. 不得恢复板块/行业过滤。策略6当前不使用板块强弱决定候选。
10. 不得把前复权信号价格宣称为真实成交回报；历史执行必须遵守 T+1、涨跌停、滑点和费用约束。

## 21. AI 自检清单

实现或人工选股后逐项检查：

- [ ] 数据已按评估日截断且升序排列。
- [ ] 流动性和长期均线门槛通过。
- [ ] 强势启动发生在5至60个交易日前，且事件质量有效。
- [ ] 整理区不含启动日，形态区不含信号日。
- [ ] VCP 每轮都是“峰值-最终低点-确认反弹峰值”。
- [ ] 关键支撑由多来源聚类，不是简单取最近最低价。
- [ ] 原始、箱体、Brooks 三条尾部路径分别计算后再合并。
- [ ] 止损和客观目标独立计算，RR2达到对应候选门槛。
- [ ] 先应用硬过滤，再按85/75/60分层。
- [ ] 市场降级时保留降级前候选类型。
- [ ] VCP 确认池已执行历史正式候选逐日 as-of 回放。
- [ ] VCP 质量分只用于观察池排序。

---

## 22. 当前实现对应模块（用于交叉核验）

| 规则 | 当前实现 |
| --- | --- |
| 唯一主入口与执行顺序 | `strategy6/engine.py` |
| 基础指标 | `strategy6/indicators.py` |
| 市场环境与RS | `strategy6/market.py` |
| 强势启动 | `strategy6/strong_start.py` |
| 严格分段 | `strategy6/phase.py` |
| 杯柄/VCP/平台 | `strategy6/pattern.py`、`strategy6/vcp_rounds.py` |
| 支撑簇与反应 | `strategy6/support.py` |
| 整理质量 | `strategy6/setup_quality.py` |
| 原始量干价稳 | `strategy6/dry_tail.py` |
| 稳定箱体与紧密K线 | `strategy6/box_tail.py` |
| Brooks尾部 | `strategy6/brooks/` |
| 入场原型与交易计划 | `strategy6/entry.py`、`strategy6/trade_plan.py` |
| 评分与分层 | `strategy6/scorer.py`、`strategy6/filters.py` |
| VCP持续观察与历史资格 | `strategy6/vcp_observer.py`、`strategy6/vcp_history.py` |
| VCP观察池质量分 | `strategy6/vcp_quality.py` |
| 默认参数和校验 | `strategy6/validation.py`、`config.yaml` |

本文是算法交付说明；若后续代码阈值发生变化，应同步更新本文，并以可复现的当前代码和测试结果为最终事实来源。

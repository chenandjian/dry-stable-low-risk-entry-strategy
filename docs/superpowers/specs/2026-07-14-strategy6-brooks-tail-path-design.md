# 策略6 Brooks 价格行为尾部路径设计

## 1. 目标

在策略6现有强势启动、形态、支撑、原始尾部和稳定箱体能力上，新增第三条同级的 Brooks 价格行为尾部路径。该路径用于识别上涨背景中空方攻击失败、下跌缺少后续跟进、支撑附近二次下探失败以及量价有序收缩的候选。

本期完整交付扫描、跨交易日触发重建、SQLite持久化、API、前端、CSV报告和策略6历史回放接入。本期不自动调优 Brooks 参数，不修改生产参数，不修改策略1至策略5。

本设计是对 Al Brooks 价格行为思想的 A 股日线量化解释，不宣称为其官方机械交易系统。

## 2. 已确认决策

1. 采用策略6专用模块化方案，在 `strategy6/brooks/` 下按职责拆分。
2. 原始尾部和箱体路径的算法、阈值、评分与旧输出行为保持不变。
3. 旧 `tail_path` 保留原始路径与箱体路径的双路径语义：`NONE/ORIGINAL/BOX/BOTH`。
4. 新增 `tail_paths`、`tail_path_summary`、`tail_primary_path`、`passed_path_count` 和 `multi_path_confirmed` 作为三路径权威字段。
5. Brooks 状态与现有候选生命周期并行，不能覆盖 `lifecycle_status`。
6. Brooks 跨日状态按评估日及之前可见K线确定性重建，不新增容易漂移的状态机。
7. B级启动最多输出 Brooks 观察状态，不得进入 Brooks 交易准备。
8. Brooks 模块只判断价格行为；止损、目标价、客观盈亏比和最终候选资格继续由现有交易计划与硬过滤统一决定。
9. 所有价格继续使用项目统一前复权口径，不引入未复权双价格链。
10. Brooks 配置关闭时，原有扫描和回测结果必须逐字段兼容。

## 3. 范围边界

### 3.1 本期包含

- 上涨、弱上涨、交易区间和下降背景识别。
- 强空方K线、连续阴线、空方后续跟进和跟进失败识别。
- Brooks式价格稳定、非重叠量干和支撑有效性判断。
- 微型双底、失败下破、二次入场准备和支撑附近有序收缩。
- 有序紧密、中性紧密、铁丝网和偏空紧密结构分类。
- 二次入场、失败下破、突破跟进和回踩确认的跨日交易触发。
- 三路径OR汇总、最高分汇总和主路径选择。
- 配置、输出、数据库、API、前端、CSV和历史回放字段。
- 单元测试、集成测试、兼容性测试和最小真实数据验证报告。

### 3.2 本期不包含

- 修改原始尾部、稳定箱体、形态、强势启动、支撑簇或市场过滤算法。
- 新增板块过滤。
- 自动修改 `config.yaml` 中的正式 Brooks 参数。
- 使用未来数据确认历史信号。
- 将 Brooks 候选直接解释为无条件买入信号。
- 为策略1至策略5复用或接入 Brooks 模块。

## 4. 总体架构

新增目录：

```text
strategy6/brooks/
  __init__.py
  models.py
  metrics.py
  context.py
  selling_pressure.py
  structures.py
  compact.py
  tail.py
  trigger.py
```

职责如下：

- `models.py`：Brooks结果对象、状态常量和序列化。
- `metrics.py`：实体、收盘位置、影线、振幅、方向变化和摆动点等客观指标。
- `context.py`：上涨背景、均线方向和连续降低高低点。
- `selling_pressure.py`：强空方K线、连续阴线、空方跟进和跟进失败。
- `structures.py`：微型双底、失败下破、二次入场准备和支撑附近有序收缩。
- `compact.py`：复用紧密K线客观指标，分类有序、中性、铁丝网和偏空结构。
- `tail.py`：汇总背景、卖压、稳定、量干、支撑、结构和评分。
- `trigger.py`：只使用评估日及之前数据，重建信号有效期和后续触发状态。

唯一业务入口仍为 `strategy6/engine.py::StrongVcpTailEngine.evaluate_at()`。建议调用顺序：

```text
指标与市场环境
→ 强势启动与严格阶段
→ 形态与支撑
→ 原始尾部
→ 稳定箱体和共享紧密K线
→ Brooks候选路径
→ 三路径汇总
→ Brooks跨日触发
→ 现有交易计划
→ 现有评分、硬过滤和候选分层
```

## 5. 公共指标与数据口径

输入只使用按交易日升序排列的完整前复权日线。评估窗口最后一根必须是 `evaluation_date` 当日完整K线。停牌或无成交状态沿用现有 `quote_status` 处理，不把停牌日伪装成正常价格行为K线。

`strategy6/box_tail.py` 中已有紧密K线算法。实施时先用现有测试建立行为基线，再将纯指标函数抽到 Brooks 可复用的模块。抽取后原箱体路径的输入、输出、阈值和评分必须保持一致。

统一指标包括：

```text
body_ratio = abs(close - open) / close
close_position = (close - low) / (high - low)
upper_shadow_ratio
lower_shadow_ratio
bar_range_ratio
kline_overlap_ratio
direction_change_count
long_shadow_bar_count
ATR5 / ATR14 / ATR20
```

当 `close<=0` 或OHLC非法时，Brooks路径返回无效数据状态。`high<=low` 时收盘位置使用中性值0.5并记录风险标签，不能抛出未处理异常。

## 6. Brooks候选路径

Brooks路径通过必须同时满足：

```python
brooks_tail_pass = (
    bull_context_pass
    and selling_pressure_exhausted
    and price_stable_pass
    and volume_dry_pass
    and support_not_broken
    and setup_pass
    and not hard_reject
    and brooks_tail_score >= pass_score_min
)
```

### 6.1 上涨背景

- S/A级强启动是可交易背景。
- B级允许观察，但强制 `brooks_trade_ready=false`。
- 当前收盘不得低于启动低点。
- 当前收盘不得低于 `MA20 - 0.5*ATR20`。
- `MA20>=MA50` 或 MA20近10日斜率为正。
- 最近观察窗口不能形成超过配置上限的连续降低高点和降低低点。
- 关键支撑必须有效。

### 6.2 卖压衰竭

- 最近默认7日识别强空方K线。
- 强空方K线定义为阴线、实体达到配置阈值且收盘靠近最低点。
- 下一完整交易日跌破空方K线低点、弱势收盘、再次形成强空方K线或有效跌破支撑，均计为空方跟进。
- 连续三根及以上阴线且低点持续下降时，不认定卖压衰竭。
- 空方K线后无跟进并在1至2日内收回实体中点，记录 `bear_follow_through_failed`。

### 6.3 价格稳定和量干

- 默认最近5日收盘区间不超过8%。
- `ATR5/ATR20` 不超过0.80。
- 平均实体不超过2.5%，最大实体不超过4%。
- 最近低点不得持续下降。
- 尾部5日均量与此前非重叠20日均量比较，默认比值不超过0.75。
- 量干可以单独为真，但持续创新低、空方有跟进或支撑破位时 Brooks 路径必须失败。

### 6.4 支撑与结构

Brooks模块只读取现有 `start_low`、`key_support_price`、`support_zone_low/high` 和 `defense_support_price`，不得重新挑选更有利的支撑。

至少满足一种结构：

- `MICRO_DOUBLE_BOTTOM`
- `FAILED_BEAR_BREAKOUT`
- `SECOND_ENTRY_LONG_READY`
- `ORDERLY_COMPRESSION_AT_SUPPORT`
- `BEAR_FOLLOW_THROUGH_FAILED`

有效破位包括深度跌破、连续两日收盘跌破、放量长阴跌破或跌破防守支撑。任何有效破位均拒绝 Brooks 路径。

## 7. 紧密结构分类

共享紧密K线指标只输出客观数据，Brooks解释层新增：

```text
NO_COMPACT
COMPACT_ORDERLY
COMPACT_NEUTRAL
BARB_WIRE
COMPACT_BEARISH
```

- `COMPACT_ORDERLY`：支撑附近、低点稳定、无空方跟进、量能收缩，可支持 Brooks 路径。
- `COMPACT_NEUTRAL`：无位置优势和触发依据，只保留观察。
- `BARB_WIRE`：方向频繁变化、长影线多且位于区间中部；候选可以保留，但不得交易准备。
- `COMPACT_BEARISH`：高低点、均线和价格中枢同步下移；硬拒绝 Brooks 路径。

## 8. 候选与交易触发

`brooks_tail_pass` 只表示观察候选成立。`brooks_trade_ready` 必须由评估日可见的后续K线确认。

- 二次入场信号日只输出 `SECOND_ENTRY_LONG_READY`，触发价为信号K线高点。
- 后续最多3个交易日内突破触发价，且距离、支撑、跳空和涨停可成交条件合格，才输出 `BROOKS_SUPPORT_READY`。
- 假跌破收回后突破收回K线高点，且空方没有重新跟进，输出 `BROOKS_FAILED_BREAKOUT_READY`。
- 突破结构压力位当日输出 `BROOKS_BREAKOUT_WAIT`，后续1至2日获得跟进或有效回踩后输出 `BROOKS_BREAKOUT_READY`。
- B级启动、铁丝网、中性紧密、过期信号或距离触发位过远时，强制 `brooks_trade_ready=false`。

Brooks状态不修改现有 `lifecycle_status`。现有候选生命周期继续负责候选池进入、退出、冷却和重新入池。

## 9. 三路径汇总与评分

旧 `tail_path` 继续只汇总原始与箱体路径。新增权威字段：

```text
tail_paths: JSON数组
tail_path_summary: ORIGINAL/BOX/BROOKS/MULTI/NONE
tail_primary_path: ORIGINAL/BOX/BROOKS/NONE
passed_path_count
multi_path_confirmed
```

最终通过与分数：

```python
tail_pass = original_pass or box_pass or brooks_pass
tail_score = max(original_score, box_score, brooks_score)
```

评分相同时主路径展示优先级为 `BROOKS > BOX > ORIGINAL`。该优先级不改变总分。多路径确认不额外加分。

Brooks满分20分：上涨背景4、卖压衰竭6、价格稳定4、量干2、结构4。结构分取最高结构，不累计。基本通过阈值14，优质阈值17；阈值必须配置化。

## 10. 交易计划与最终候选资格

Brooks模块不重复计算止损、目标价和客观盈亏比。现有 `calculate_trade_plan()` 继续生成交易计划，现有硬过滤继续处理客观盈亏比、风险、市场环境和最终候选资格。

因此允许：

```text
brooks_tail_pass=true
但因客观盈亏比不足而最终 candidate_type=REJECTED
```

距离触发位过远只阻止 `brooks_trade_ready`，不否定已经成立的 Brooks 观察结构。

## 11. 配置

在策略6配置中新增 `brooks_tail`，默认开启，参数使用外部开发文档的第一版推荐值。配置解析遵循现有深合并模式，缺失字段使用明确默认值，非法范围在引擎构造或配置保存时失败。

Brooks配置必须覆盖：背景、卖压、价格稳定、量干、支撑、二次入场、失败下破、紧密结构、交易触发和评分。生产默认值只负责启用文档基线，不允许根据本次验证结果自动调优。

当 `brooks_tail.enabled=false`：

- 不执行 Brooks 分析。
- Brooks分数和通过状态为零值。
- 三路径新增字段只反映原始与箱体路径。
- 旧字段、旧候选资格、旧评分和旧回测信号保持一致。

## 12. 持久化与API

采用混合持久化：

- 常用筛选和前端展示字段使用兼容新增列，例如 Brooks启用/通过/分数/状态/交易准备、三路径汇总。
- 详细指标、日期列表、原因、拒绝原因和风险标签保存到 `brooks_result_json`。
- DB读取层负责把JSON解析回结构化字段，API调用方不需要自行解析字符串。
- 旧任务缺少新字段时返回明确默认值，不能报错或被误判为 Brooks 通过。

策略6原API路径保持不变。候选API在旧字段基础上追加新字段，不删除或重命名旧字段。

## 13. 前端与导出

策略6结果页新增：

- 三路径通过情况、主路径和多路径确认。
- Brooks状态、分数、候选通过和交易准备状态。
- 上涨背景、卖压衰竭、价格稳定、量干和支撑结论。
- 微型双底、失败下破、二次入场和紧密结构。
- 触发价、有效期、通过原因、风险和拒绝原因。

英文状态尽可能通过现有标签模块翻译为中文，同时保留CSV中的原始枚举值供审计。前端不得把 `brooks_tail_pass` 显示为立即买入；只有 `brooks_trade_ready=true` 才显示“交易触发已确认”。

CSV和策略6报告追加三路径及Brooks字段，不删除旧列。

## 14. 历史回放与回测

策略6历史回放继续逐 `evaluation_date` 调用正式 `StrongVcpTailEngine.evaluate_at()`。每次只传入该日期及之前的个股和指数数据。

回测信号快照保存新字段，并支持以下研究分组：

```text
ORIGINAL_ONLY
BOX_ONLY
BROOKS_ONLY
ORIGINAL_OR_BOX
ORIGINAL_OR_BOX_OR_BROOKS
MULTI_PATH_ONLY
MICRO_DOUBLE_BOTTOM
FAILED_BEAR_BREAKOUT
SECOND_ENTRY_LONG_READY
BROOKS_SUPPORT_READY
BARB_WIRE_WAIT
COMPACT_BEARISH_REJECT
```

现有 ORIGINAL/BOX/BOTH 实验必须改为读取旧通过标志或 `tail_paths`，不能因新增 `MULTI` 汇总误分类。OOS锁定、真实指数门禁、幸存者偏差标签、T+1和成交规则保持不变。

本期只证明实现正确、回放可重复并输出分组结果，不根据结果自动写入生产配置。

## 15. 测试策略

实施严格遵循TDD，每个行为先写失败测试并确认因功能缺失失败。

单元测试覆盖：

- 配置关闭兼容和非法配置。
- K线指标及异常OHLC。
- 上涨、交易区间和下降背景。
- 强空方有/无跟进、连续阴线和实体收缩。
- 价格稳定、量干但创新低、支撑有效与有效破位。
- 微型双底、失败下破、空方跟进失败和二次入场。
- 有序、中性、铁丝网和偏空紧密结构。
- 信号日准备、后续触发、过期、B级限制和未来数据隔离。
- 三路径OR、最高分、同分主路径和旧 `tail_path` 兼容。

集成测试覆盖：

- Brooks关闭时扫描候选逐字段兼容。
- Brooks-only候选可以进入现有后续评分，但仍受RR和市场硬过滤。
- 原始与箱体路径结果不受 Brooks 失败影响。
- SQLite保存读取、旧库迁移、API和CSV字段完整。
- 前端状态翻译、详情展示和旧任务默认值。
- 历史回放不访问未来K线，扫描与同日回放结果一致。
- 策略1至策略5相关测试不回归。

最小真实数据验证只读本地 `data/cuphandle.db`，记录任务或评估日期、各路径数量、Brooks结构分布和异常记录。该验证不构成参数有效性结论。

## 16. 风险与控制

1. Brooks阈值过松可能引入弱势横盘。通过上涨背景、空方跟进、支撑和偏空紧密硬拒绝控制。
2. 静态重建可能因支撑重新计算改变历史信号。所有回放必须按评估日切片并保存完整快照。
3. 多路径字段可能破坏旧回测分组。旧 `tail_path` 保持双路径语义，新研究只使用新字段。
4. 公共紧密K线抽取可能改变箱体结果。先建立逐字段基线，再做纯机械抽取。
5. Brooks候选与交易触发容易被前端混淆。使用独立布尔值、状态和中文说明。
6. 数据不足时不能用默认零值伪装通过。Brooks返回 `BROOKS_INVALID_DATA` 和明确风险标签。
7. 当前股票池回测存在幸存者偏差，报告继续标记 `RESEARCH_ONLY_CURRENT_UNIVERSE`。

## 17. 验收标准

1. 原始尾部和箱体路径关闭或失败时的旧结果不变。
2. Brooks路径与前两条路径同级且不依赖箱体通过。
3. 最终通过为三路径OR，最终分数为三路径最高分。
4. 旧 `tail_path` 保持双路径语义，新三路径字段完整、可追溯。
5. Brooks包含上涨背景、卖压衰竭、价格稳定、非重叠量干、支撑和至少一种空方失败结构。
6. 铁丝网不得交易准备，偏空紧密和有效破位必须拒绝。
7. B级启动最多观察。
8. 候选和交易触发分离，信号日不得使用未来数据确认。
9. 止损、目标和客观盈亏比继续使用现有唯一口径。
10. SQLite、API、前端、CSV和历史回放均支持新增字段并兼容旧任务。
11. Brooks关闭兼容测试、专项测试、策略6回归、后端完整回归、前端测试和构建全部通过。
12. 生成最小真实数据验证报告，但不自动调优或修改生产参数。


# 代码问题修复复查报告

> 本报告已被 `2026-06-09-bug-fix-recheck-round2.md` 取代。经用户确认，原报告中的 BUG-008 多数据源前复权一致性问题已撤销，不再要求修复。

## 1. 检查范围

本次复查针对 `2026-06-09-code-review-bug-fixes.md` 所列修复提交，重点检查：

* 真实阻力位与风险收益比计算
* ATR 止损过近拦截
* 大盘指数数据获取
* 杯柄与 VCP 统一策略引擎
* 历史回测与单股回测
* 多数据源顺序、失败记录与复权一致性
* 修复对应的回归测试

已确认的产品约束：

* 日线数据源仅使用 `baidu`、`sina`、`tencent`
* `min_price_stable_score: 5` 是用户主动配置，不作为缺陷
* 量干评分采用 12 分制，旧开发文档未更新，不作为缺陷

---

## 2. 总体结论

本轮修复已完成部分核心入口统一，ATR 止损过近拦截、指数专用抓取器和数据源顺序均已有实质改进；现有策略相关测试共 58 项通过。

但修复尚未达到可交付标准。历史回测仍未使用策略真实止损，VCP-only 在单股回测中的序列化与去重仍依赖杯柄字段，真实阻力位算法与“最近阻力”目标不一致，BUG-008 复权一致性没有实现。以上问题会直接影响策略回测统计或实时风险收益判断。

---

## 3. 问题清单

| 编号 | 问题 | 严重程度 | 影响范围 | 是否必须修复 |
| --- | --- | --- | --- | --- |
| RECHECK-001 | 历史回测仍使用 `breakout_price * 0.95`，未使用策略真实止损 | 高 | 回测止损命中率、参数评价 | 是 |
| RECHECK-002 | VCP-only 未形成稳定的模式类型、序列化与唯一身份 | 高 | 单股回测、VCP 去重、结果追踪 | 是 |
| RECHECK-003 | “真实目标价”算法并未稳定返回最近有效阻力 | 高 | RR1、买入决策、候选排序 | 是 |
| RECHECK-004 | BUG-008 复权一致性仍未实现 | 高 | 多源数据一致性、缓存、策略指标 | 是 |
| RECHECK-005 | 多源全部失败时丢失真实尝试次数和错误信息 | 中 | 故障定位、数据源质量统计 | 是 |
| RECHECK-006 | 新增配置项未接入或未写入配置文件 | 中 | 配置可控性、维护性 | 是 |
| RECHECK-007 | 关键修复缺少对应回归测试 | 中 | 回归风险、交付可信度 | 是 |

---

## 4. 详细问题分析

### RECHECK-001：历史回测仍未使用策略真实止损

#### 问题现象

历史回测已改用 `CupHandleStrategyEngine.evaluate_at()` 进行候选判定，但止损命中仍按突破价下方 5% 计算，而不是按策略引擎生成的 `dry_stable["key_prices"]["stop_loss"]` 计算。

同时，公开参数 `min_score` 已不再参与筛选，调用方传入不同阈值不会改变结果。

#### 涉及模块

* `scanner/backtester.py:118-150`
* `scanner/backtester.py:177-210`
* `scanner/backtester.py:236-259`

#### 证据

* `run_backtest(..., min_score=60)` 保留了参数和文档，但函数内部没有使用 `min_score`。
* `_calc_forward()` 仍执行 `sl_price = breakout_price * 0.95`。
* `BacktestResult` 未保存策略实际 `entry_zone` 和 `stop_loss`。
* `run_backtest()` 内部直接请求指数网络数据，无法由测试或调用方注入固定市场数据。

#### 影响

* 回测止损命中率与线上策略止损逻辑不一致。
* VCP、低吸和突破形态被同一突破价止损模型错误评价。
* `min_score` 参数静默失效，调用者会误以为筛选阈值生效。
* 回测结果受到实时外部网络状态影响，难以复现。

#### 修复建议

1. 将真实 `stop_loss`、`entry_zone_low`、`entry_zone_high`、`pattern_kind` 写入 `BacktestResult`。
2. 修改 `_calc_forward()`，显式接收真实 `stop_loss`，禁止自行推导 `breakout_price * 0.95`。
3. 明确 `min_score` 的语义：继续支持则在统一策略通过后追加分数过滤；不再支持则删除参数并同步所有调用方。
4. 为 `run_backtest()` 增加可选的 `market_data` 或 `market_fetch_fn` 注入点，默认行为保持兼容。

#### 验证方式

1. 构造突破价为 100、真实止损为 92、未来最低价为 94 的样本。
2. 修复前会错误记录止损命中，修复后应记录未命中。
3. 对同一数据分别传入 `min_score=50` 和 `min_score=90`，结果数量应符合参数语义。
4. 注入固定指数数据后，测试不得发起外部网络请求。

---

### RECHECK-002：VCP-only 未形成稳定的模式身份

#### 问题现象

统一策略引擎在 VCP-only 分支中动态执行 `result.pattern_kind = "vcp"`，但 `CupHandleResult` 数据类没有声明该字段，序列化结果也不包含该字段。单股回测仍使用杯柄的 `handleStartDate`、`handleEndDate`、`handleLowDate` 生成唯一身份。

#### 涉及模块

* `scanner/pattern_detector.py:9-48`
* `scanner/strategy_engine.py:119-130`
* `scanner/strategy_engine.py:354-374`
* `scanner/single_stock_backtest.py:237-250`

#### 触发条件

数据未识别出杯柄，但 VCP 评分达到候选门槛时。

#### 影响

* VCP-only 结果序列化后无法可靠识别为 VCP。
* 不同 VCP 可能因杯柄字段为空或相同而被错误去重。
* 回测结果 ID 不能稳定追踪同一 VCP 结构。

#### 修复建议

1. 在结果模型中正式声明 `pattern_kind`，默认值为 `cup_handle`。
2. 序列化时输出 `patternKind`。
3. 为 VCP 定义稳定身份字段，例如收缩区间起止日期或关键收缩日期列表。
4. `_pattern_identity()` 与 `_pattern_id()` 必须按 `patternKind` 分支生成，不得让 VCP 复用空杯柄字段。

#### 验证方式

1. 构造两个日期区间不同的 VCP-only 样本。
2. 两个样本均应序列化为 `patternKind=vcp`。
3. 两个样本的 pattern ID 必须不同。
4. 同一 VCP 在相邻扫描日重复出现时，应按既定规则稳定去重。

---

### RECHECK-003：真实目标价并非最近有效阻力

#### 问题现象

`_find_real_target()` 文档声明查找“最近真实阻力”，但实现优先返回 pivot，其次返回最近 60 日的最高价。最高价通常是最远阻力，而不是最近阻力。最后一级还会把任意日线最高价当作阻力，缺少局部高点或平台确认。

当 `risk <= 0` 时，代码仍生成 `current_price * 1.10` 和 `current_price * 1.20` 的合成目标价。

#### 涉及模块

* `analyzer/key_prices.py:68-92`
* `analyzer/key_prices.py:97-122`

#### 影响

* RR1 可能被较远高点放大，导致本应等待的标的通过风险收益门槛。
* 任意单日影线可能被误当作有效阻力。
* 无效止损场景仍展示合成目标价，与“真实目标价”修复目标冲突。

#### 修复建议

1. 先生成所有经过验证的阻力候选，再选择高于当前价的最近一个。
2. 阻力候选至少应来自 pivot、确认的 swing high 或平台顶部，不能直接使用所有日线 high。
3. 对候选阻力增加最小距离/噪声过滤，避免当前价附近随机影线。
4. 当 `risk <= 0` 时，将目标价置空或 0，并让上层明确标记止损无效，禁止生成百分比合成目标。

#### 验证方式

1. 当前价 10，阻力候选为 10.5、12、15 时，`target_1` 应为 10.5。
2. 仅存在单日异常影线时，不应自动认定为有效阻力。
3. `stop_loss >= current_price` 时，目标价不得生成为当前价的 110%/120%。

---

### RECHECK-004：BUG-008 复权一致性未实现

#### 问题现象

`config.yaml` 中仍存在 `data.use_fq: true`，但代码未读取该配置，也没有统一不同数据源的复权语义、缓存元数据或失效策略。

#### 涉及模块

* `config.yaml:18`
* `scanner/baidu_source.py`
* `scanner/sina_source.py`
* `scanner/tencent_source.py`
* `scanner/db.py`

#### 影响

除权除息附近，多源数据或旧缓存可能处于不同价格口径，导致均线、ATR、杯柄深度、VCP 收缩和止损位置失真。

#### 修复建议

1. 明确三个数据源各自返回的价格口径，并统一为前复权。
2. 缓存必须记录数据源、复权类型和版本。
3. 缓存口径不匹配时必须失效或重建，禁止直接合并。
4. 若某数据源无法提供前复权数据，应明确拒绝进入策略计算或执行可靠转换。

#### 验证方式

使用包含除权日期的同一股票数据，对三个源进行对齐，验证日期、OHLC 口径及策略指标在允许误差内一致。

---

### RECHECK-005：多源全部失败时丢失失败详情

#### 问题现象

`_fetch_with_retry()` 在每个源失败后仅记录日志并继续；全部失败时重新构造空 `FetchResult`，未保留各源真实尝试次数和错误。只要曾遇到一个忙碌源，最终结果仅写入 `fallback_error = "data source busy"`。

#### 涉及模块

* `scanner/engine.py:527-607`

#### 影响

* 数据库中的失败记录无法反映真实失败源与错误原因。
* 无法可靠统计各数据源成功率、超时率和解析失败率。
* “某源忙碌 + 其他源失败”会被简化为忙碌，掩盖实际错误。

#### 修复建议

在遍历源时累计每个源的尝试次数和最终错误；返回结果至少要保留主源、最后尝试备用源及其错误。若三源信息无法放入现有字段，应增加结构化 source-attempt 日志，但不要进行破坏性数据库变更。

#### 验证方式

模拟 `baidu=busy`、`sina=timeout`、`tencent=empty response`，最终记录必须同时可追踪三个事实，不能只显示 `data source busy`。

---

### RECHECK-006：新增配置未真正接入

#### 问题现象

* `config.yaml` 新增 `market_environment.index_symbol: sh000001`，但所有调用方均直接调用 `fetch_market_index_daily()`，没有读取或传入该配置。
* `near_pivot_below_pct` 仅存在于 `analyzer/decision.py` 的代码默认值，未写入 `config.yaml`，用户无法通过配置文件发现或调整。

#### 涉及模块

* `config.yaml:77`
* `main.py:113`
* `server.py:623`
* `scanner/engine.py:98,442`
* `scanner/backtester.py:150`
* `analyzer/decision.py:38,84`

#### 修复建议

1. 要么将 `index_symbol` 接入所有市场环境入口，要么删除该假配置并固定为上证指数。
2. 将 `near_pivot_below_pct` 加入 `config.yaml` 的 decision 配置段，并补充配置读取测试。

---

### RECHECK-007：关键修复缺少回归测试

#### 问题现象

本轮 8 项修复只修改了以下 3 个测试文件：

* `tests/test_cuphandle_strategy_engine.py`
* `tests/test_engine_fresh_fetch.py`
* `tests/test_index_source.py`

真实阻力、ATR 止损、近 pivot 下界、历史回测真实止损、VCP 唯一身份和复权一致性均没有新增针对性测试。

#### 修复建议

为 RECHECK-001 至 RECHECK-006 分别补充最小回归测试。测试必须验证业务结果，不应只验证函数被调用。

---

## 5. 已确认有效的修复

* ATR 止损过近已形成结构化状态，并参与买入决策拦截。
* 指数抓取已使用专用 `sh000001` 路径，不再复用个股代码转换。
* `_fetch_with_retry()` 已按配置链顺序尝试数据源。
* 统一策略引擎已能在杯柄失败后尝试 VCP-only。
* 历史回测已改为调用统一策略引擎，并按检测日期切片市场数据，避免指数未来数据泄漏。

---

## 6. 建议修复顺序

1. 修复历史回测真实止损、`min_score` 和可复现市场数据。
2. 完成 VCP-only 的模型、序列化、身份和去重闭环。
3. 修正真实阻力候选生成与最近阻力选择。
4. 完成多源前复权与缓存口径一致性。
5. 补齐数据源失败详情和配置接入。
6. 为上述问题补齐回归测试，再执行全量测试。

---

## 7. 给修复 AI 的执行要求

1. 不要修改量干 12 分制。
2. 不要修改用户配置的 `min_price_stable_score: 5`。
3. 不要重新引入 mootdx；日线源仅限 `baidu`、`sina`、`tencent`。
4. 不要重构无关模块，不要调整现有前端 UI。
5. 历史回测必须与线上策略共用真实止损和候选规则。
6. VCP-only 必须有稳定、可序列化、可去重的身份。
7. 不得用任意日线 high 冒充已确认阻力。
8. 涉及缓存变更时，必须说明复权类型、缓存元数据和失效策略。
9. 每个修复必须先增加能复现问题的测试，再修改实现。
10. 保持现有接口兼容；若废弃参数，必须更新所有调用方和文档。

---

## 8. 回归测试清单

* 杯柄候选使用真实止损计算回测止损命中
* VCP 候选使用真实止损计算回测止损命中
* `min_score` 参数行为明确且有测试
* 回测注入固定市场数据时不访问网络
* 两个不同 VCP 生成不同稳定 ID
* VCP 序列化明确包含 `patternKind=vcp`
* 目标一选择最近的已确认阻力
* 无有效阻力时 RR1 为 0
* 止损无效时不生成合成目标价
* `near_pivot_below_pct` 可通过配置文件调整
* 指数配置项生效或被删除
* 三数据源复权口径一致
* 不同复权口径缓存不会被直接合并
* 多源全部失败时保留真实尝试次数和错误
* 全量离线测试不依赖外部行情接口

---

## 9. 不建议修改的内容

* 不要修改量干、价稳和形态评分的既定分制。
* 不要修改用户主动设置的策略阈值。
* 不要引入大型新框架。
* 不要删除多数据源互斥锁。
* 不要扩大到无关模块重构。

---

## 10. 验证结果

执行命令：

```bash
python -m pytest tests/test_key_prices.py tests/test_decision.py tests/test_cuphandle_strategy_engine.py tests/test_backtester.py tests/test_single_stock_backtest.py tests/test_engine_fresh_fetch.py tests/test_index_source.py -q
```

结果：`58 passed`。

执行命令：

```bash
python -m pytest tests -q
```

结果：`147 passed, 1 failed`。唯一失败为 `tests/test_akshare_hist.py::test_dongcai`，原因是东财外部接口主动断开连接，属于外部网络集成测试失败，不是本轮策略修改引入的断言回归。

---

## 11. 最终交付标准

修复完成后应满足：

1. 历史回测与线上策略使用同一真实止损和候选规则。
2. VCP-only 在扫描、序列化、回测和去重链路中身份一致。
3. RR1 基于最近的已确认真实阻力，不使用合成目标冒充真实目标。
4. 三个日线源和缓存使用统一复权口径。
5. 配置项均真实接入，不保留假配置。
6. 每个问题都有可复现、可防回归的自动化测试。
7. 离线单元测试全部通过；外部接口测试应单独标记和执行。

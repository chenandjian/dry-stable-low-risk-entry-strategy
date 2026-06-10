# 代码问题检查报告：策略2「极致量干价稳」

## 1. 检查范围

本次审核以 `docs/superpowers/specs/2026-06-10-strategy2-extreme-dry-stable-design.md` 为业务基准，以
`docs/reviews/2026-06-10-strategy2-third-party-review.md` 为开发方交付说明，重点检查：

- `strategy2/` 的指标、评分、否决、风险、唯一评估入口和扫描编排。
- 策略窗口、最近 5 日边界、零成交量和无效行情处理。
- `scanner/daily_data_service.py` 的多数据源、缓存回退与错误语义。
- `scanner/db.py` 的任务类型、候选隔离、序列化和查询排序。
- `server.py` 的配置校验、任务启动、中断恢复和策略2 API。
- `web/src/pages/ScannerConsole.vue`、`Strategy2Results.vue` 的策略隔离和结果展示。
- 现有测试是否覆盖设计文档要求。

审核分支：`codex/strategy2-extreme-dry-stable-design`
审核提交：`82e337a`

---

## 2. 总体结论

策略2的模块独立边界、基础模型、独立候选表、独立 API 和前端路由已经建立，但当前版本仍不满足可交付标准。

最严重的问题是：策略窗口未真正生效、最近 5 日首日跌幅漏判、零成交量数据可被选为 80 分候选，以及中断的策略2任务会被策略1扫描器恢复。除此之外，配置校验、任务类型隔离、缓存回退、候选持久化和前端扫描控制台仍存在完整链路缺口。

本次审核确认 **11 个问题**，其中：

- 严重：1 个
- 高：6 个
- 中：4 个

建议不要逐个零散修补。应按本文第 5 节的依赖顺序一次完成，并补齐本文指定的契约测试。

---

## 3. 问题清单

| 编号 | 问题 | 严重程度 | 影响范围 | 是否必须修复 |
| --- | --- | --- | --- | --- |
| BUG-S2-001 | 中断的策略2任务会通过策略1扫描器恢复 | 严重 | 任务恢复 / 数据正确性 / 候选表 | 是 |
| BUG-S2-002 | `strategy_window_days` 未实际截取计算窗口 | 高 | 策略指标 / 校验 / 缓存一致性 | 是 |
| BUG-S2-003 | 最近 5 日跌幅仅检查 4 个交易日变化 | 高 | 价稳评分 / 放量大跌否决 | 是 |
| BUG-S2-004 | `V20=0` 的零成交量数据可作为 80 分候选 | 高 | 核心策略正确性 | 是 |
| BUG-S2-005 | 行情校验不完整，排序、必需 OHLC 字段未验证 | 高 | 策略稳定性 / 错误语义 | 是 |
| BUG-S2-006 | 后端未在保存配置和创建任务前校验策略2配置 | 高 | 配置 / 扫描启动 / 任务状态 | 是 |
| BUG-S2-007 | 策略1与策略2任务、候选和状态查询未完全隔离 | 高 | API / 前端 / 历史结果 | 是 |
| BUG-S2-008 | 全数据源失败后没有按设计回退新鲜缓存 | 中 | 数据可用性 / 扫描完整性 | 是 |
| BUG-S2-009 | 候选入库失败仍被标记和广播为候选 | 中 | 数据一致性 / 实时发现 | 是 |
| BUG-S2-010 | 扫描控制台和策略2结果页未形成独立展示闭环 | 中 | 前端用户体验 / 结果解释 | 是 |
| BUG-S2-011 | 策略2候选 JSON 字段未反序列化，默认排序缺少风险比 | 中 | API 合同 / 详情展示 / 排序 | 是 |

---

## 4. 详细问题分析

### BUG-S2-001：中断的策略2任务会通过策略1扫描器恢复

#### 问题现象

服务重启后，如果最近一个未完成任务是策略2任务，系统会把它交给策略1的 `scan_all()` 恢复。

#### 涉及模块

- `scanner/db.py:get_interrupted_task`
- `server.py:lifespan`

#### 证据链

- `get_interrupted_task()` 只查询并返回 `id/scanned/total_stocks`，没有返回 `strategy_type`。
- `server.py` 的启动恢复逻辑无条件调用：

```python
scan_all(config, progress_callback=on_progress, resume_task_id=interrupted["id"])
```

- 策略1恢复回调还固定读取 `discovery["score"]`，而策略2发现结构使用 `total_score`。
- 最小复现中，策略2中断任务返回值为：

```text
{'id': 's2-int', 'scanned': 0, 'total_stocks': 1}
```

其中没有任务类型，恢复端无法正确分派。

#### 触发条件

1. 启动策略2全市场扫描。
2. 扫描未完成时终止服务。
3. 重启服务。

#### 影响

- 策略2任务可能写入策略1候选表。
- 任务类型、扫描结果和前端展示互相矛盾。
- 恢复期间可能因发现字段不同而抛出异常。
- 属于核心数据污染问题。

#### 修复建议

1. 修改 `get_interrupted_task()`，查询并返回 `strategy_type`；数据库中的 `NULL` 必须解释为 `STRATEGY_1_CUP_HANDLE`。
2. 在 `lifespan` 恢复前调用统一的 `_set_running(..., strategy_type=...)`，不要手工零散写 `_running`。
3. 按 `strategy_type` 分派：
   - 策略1：调用现有 `scan_all(..., resume_task_id=task_id)`。
   - 策略2：取得 `db.get_pending_stocks(task_id)` 后调用 `scan_strategy2_all(..., task_id=task_id, stocks=pending_stocks)`。
4. 策略1和策略2使用各自的 discovery 映射函数，不能共享固定读取 `score` 的回调。
5. 未知任务类型必须把任务标记为失败并记录稳定错误，不得默认交给任一策略执行。

#### 必须新增测试

- 创建未完成策略2任务，启动 lifespan，断言只调用 `scan_strategy2_all`。
- 创建未完成策略1任务，断言仍只调用 `scan_all`。
- 策略2恢复后的候选只存在于 `strategy2_candidates`。
- 恢复时 `_running.strategy_type` 和状态接口返回值正确。

---

### BUG-S2-002：`strategy_window_days` 未实际截取计算窗口

#### 问题现象

配置中虽然存在 `strategy_window_days`，但引擎始终对调用方传入的完整数据做校验和计算。

#### 涉及模块

- `strategy2/engine.py:evaluate_at`
- `strategy2/indicators.py:validate_strategy_data`
- `strategy2/scanner.py:scan_strategy2_all`

#### 证据链

`evaluate_at()` 直接执行：

```python
validate_strategy_data(data, ...)
compute_indicators(data)
compute_key_support(data, ...)
```

代码中没有 `data[-self.strategy_window_days:]`。

最小复现：输入 121 行，最近 120 行完全有效，只把窗口外第一行的 `close` 改为 0。当前结果：

```text
prefix_outside_window= False INVALID_MARKET_DATA
```

按设计，窗口外数据不应影响策略2结果。

#### 触发条件

- 缓存或数据源返回的数据多于 `strategy_window_days`。
- 窗口外历史数据含缺失值、异常值或重复数据。
- 将来增加大于 60 日的指标或支撑回看参数。

#### 影响

- 配置项实际上不控制策略计算范围。
- 相同的最近窗口数据，可能因更早历史数据不同得到不同结果。
- 缓存中数据越多，错误拒绝概率越高。

#### 修复建议

在唯一评估入口中建立明确顺序：

1. 验证输入是非空列表。
2. 验证日期、排序、重复和必需字段。
3. 检查有效数据数是否达到 `minimum_required_days`。
4. 执行 `strategy_data = data[-self.strategy_window_days:]`。
5. 所有指标、最近 5 日检查、支撑位和风险计算只使用 `strategy_data`。

不要在 scanner、API 或其他入口分别裁剪；唯一裁剪点必须是策略2引擎，避免入口间结果不一致。

#### 必须新增测试

- 窗口外坏数据不影响最近窗口评估。
- 两组数据最近 120 日完全相同、前缀不同，最终评估必须完全相同。
- 输入 80 日、窗口 120 日、最低 60 日时，使用全部 80 日并可评估。
- 输入超过窗口时，支撑位和所有指标不得读取窗口外数据。

---

### BUG-S2-003：最近 5 日跌幅仅检查 4 个交易日变化

#### 问题现象

“最近 5 日不存在单日大跌”评分与“最近 5 日放量大跌”否决都漏掉最近 5 日中的第一天。

#### 涉及模块

- `strategy2/engine.py` 的 `has_big_drop`
- `strategy2/rejection.py:check_rejection_rules`

#### 证据链

两处代码都使用：

```python
recent_5 = data[-5:]
for i in range(1, len(recent_5)):
```

要计算最近 5 个交易日各自相对前一交易日的涨跌，需要 6 个收盘价。当前实现只比较 4 个区间。

最小复现：在 `data[-5]` 设置相对 `data[-6]` 的放量跌幅，当前结果：

```text
first_of_recent5_drop= []
```

同时评分原因仍包含：

```text
最近5日无单日跌幅低于-3%: +10
```

#### 触发条件

破坏性下跌发生在评估窗口最近 5 个交易日中的第一天。

#### 影响

- 应否决的股票可能进入候选。
- 价稳评分多得 10 分。
- 同一错误在评分与否决中重复存在。

#### 修复建议

新增策略2内部共享函数，例如：

```python
def recent_daily_changes(data, days=5):
    window = data[-(days + 1):]
    return [
        {
            "row": window[i],
            "change": window[i]["close"] / window[i - 1]["close"] - 1,
        }
        for i in range(1, len(window))
    ]
```

评分和否决必须共同使用该函数，避免再次出现两套边界实现。

#### 必须新增测试

- 大跌发生在 `data[-5]`、`data[-4]`、`data[-1]` 时均正确识别。
- 恰好 `-3%` 不属于“低于 -3%”；低于 `-3%` 才取消评分。
- 恰好 `-4%` 且成交量大于 V20 时触发否决。

---

### BUG-S2-004：`V20=0` 的零成交量数据可作为 80 分候选

#### 问题现象

设计要求 `V20=0` 按无效数据排除，但当前代码把无法计算的 `V5/V20` 设置为 `0.0`，该值反而满足两个量干评分条件。

#### 涉及模块

- `strategy2/indicators.py:validate_strategy_data`
- `strategy2/indicators.py:compute_indicators`
- `strategy2/scorer.py:score_volume_dry`

#### 证据链

- 校验允许 `volume == 0`。
- `V20=0` 时，`volume_ratio_5_20 = 0.0`。
- 评分器将 `0.0` 同时判定为 `<= 0.60` 和 `<= 0.50`。

最小复现：120 日价格平稳、成交量全部为 0，当前结果：

```text
zero_volume= True 80 None 0.0
```

#### 触发条件

- 数据源返回停牌、缺失或错误归一化后的全零成交量。
- 流动性过滤被关闭或未来调用者直接使用唯一评估入口。

#### 影响

完全不可交易的数据会成为高分候选，直接破坏策略正确性。

#### 修复建议

1. `V20 <= 0` 时直接返回 `INVALID_MARKET_DATA`，不得进入评分。
2. 不要用 `0.0` 表示“比率无法计算”；如模型需要表达该状态，应使用 `None`，但最终评估仍必须排除。
3. 引擎自身必须保证此约束，不能依赖外部流动性过滤兜底。

#### 必须新增测试

- 全零成交量数据不得入选，状态为 `INVALID_MARKET_DATA`。
- 最近 20 日成交量均为零不得入选。
- `V20 > 0` 且 `V5=0` 时，需按产品规则明确测试是否允许；不要让此边界隐式决定。

---

### BUG-S2-005：行情校验不完整，排序、必需 OHLC 字段未验证

#### 问题现象

设计要求验证数据长度、排序、字段和值，但当前只验证 `close` 和 `volume`。`compute_indicators()` 随后直接读取 `high/low/date`，异常数据会抛出运行时错误或产生错误指标。

#### 涉及模块

- `strategy2/indicators.py:validate_strategy_data`
- `strategy2/indicators.py:compute_indicators`
- `strategy2/engine.py:evaluate_at`

#### 可能触发的数据

- 缺少 `high` 或 `low`。
- `high/low/open` 为字符串、空值、零或负数。
- 日期倒序、重复、缺失。
- OHLC 关系明显无效，例如 `high < low`。

#### 影响

- 单股被记录为笼统的 `STRATEGY2_EVALUATION_ERROR`，而不是稳定的 `INVALID_MARKET_DATA`。
- 倒序数据会把错误日期当作评估日，造成未来数据或历史日期误用。
- 错误低价可能让区间指标失真。

#### 修复建议

建立一个完整、单一的数据验证函数：

- 每行必须包含 `date/open/high/low/close/volume`。
- 日期必须可比较、严格升序且不重复。
- OHLC 必须是有限正数；成交量必须是有限非负数。
- 建议校验 `high >= max(open, close, low)`、`low <= min(open, close, high)`。
- `bool` 不应被当作数字接受。
- 所有失败统一返回 `INVALID_MARKET_DATA`，不要让 KeyError/TypeError 穿透。

#### 必须新增测试

针对缺字段、字符串、NaN、Inf、倒序、重复日期、无效 OHLC 关系分别测试。

---

### BUG-S2-006：后端未在保存配置和创建任务前校验策略2配置

#### 问题现象

前端有部分策略2校验，但后端配置保存接口只校验策略1窗口；策略2启动接口先创建任务和线程，直到后台 scanner 构造引擎时才可能失败。

#### 涉及模块

- `server.py:update_config`
- `server.py:start_strategy2_scan`
- `strategy2/engine.py:_validate_config`

#### 证据链

- `update_config()` 只调用 `resolve_strategy_windows(config)`。
- `start_strategy2_scan()` 没有在创建任务前构造或调用策略2配置验证器。
- 引擎没有校验设计要求的：

```text
strategy_window_days <= liquidity.min_listing_days
```

- 当前 `int()` / `float()` 强制转换会接受字符串、布尔值和可截断的小数，配置契约不严格。

#### 影响

- 无效配置可以写入 `config.yaml`。
- 启动接口返回成功并创建 running 任务，随后后台失败。
- 前端校验可被 API 调用绕过。

#### 修复建议

新增共享后端函数，例如 `resolve_strategy2_config(full_config)`：

- 严格校验原始类型，拒绝 bool、字符串和不允许的小数。
- 校验引擎当前已有范围。
- 校验 `strategy_window_days <= liquidity.min_listing_days`。
- 校验 `support_lookback_days < minimum_required_days` 或至少小于有效策略窗口，避免静默使用不足历史。
- 返回规范化后的不可变配置或普通 dict。

必须在以下位置调用：

1. `PUT /api/config` 深合并后、写文件前。
2. `POST /api/strategy2/scans` 创建任务前。
3. `scan_strategy2_all` 构造引擎前保留最后一道防御。

#### 必须新增测试

- 保存无效策略2配置返回 HTTP 400 且不写文件。
- 启动无效策略2配置返回 HTTP 400，数据库中不得创建任务。
- 窗口大于 `min_listing_days` 明确拒绝。
- 字符串、bool、浮点天数明确拒绝。

---

### BUG-S2-007：策略1与策略2任务、候选和状态查询未完全隔离

#### 问题现象

新增 `strategy_type` 后，部分旧接口仍查询所有任务或默认选择最新完成任务，导致策略2任务污染策略1页面；策略2候选接口也不验证传入任务 ID 的类型。

#### 涉及模块

- `scanner/db.py:get_candidates`
- `scanner/db.py:get_scan_tasks`
- `scanner/db.py:get_running_task_id`
- `server.py:scan_status`
- `server.py:list_tasks`
- `server.py:strategy2_candidates`
- `server.py:strategy2_candidate_detail`

#### 证据链

1. `get_candidates()` 未传 task_id 时，选择最新完成任务，但没有过滤策略类型。
2. `list_tasks()` 遍历全部任务，并用策略1候选表计算每个任务的统计。
3. DB fallback 状态将任意 running 任务固定返回为 `STRATEGY_1_CUP_HANDLE`。
4. 策略2候选接口接收策略1 task_id 时返回空列表 200，而设计要求 404 或明确任务类型错误。

最小复现：先完成策略1任务并保存候选，再完成更晚的策略2任务，当前结果：

```text
default_s1_candidates_after_s2= []
strategy2_with_s1_task_id= []
```

#### 影响

- 完成策略2扫描后，策略1默认候选页面可能突然变空。
- 策略1任务中心混入策略2任务并显示错误统计。
- 错误任务 ID 被静默解释为“没有候选”，不利于定位调用错误。

#### 修复建议

1. 增加统一任务查询辅助函数：
   - `get_task(task_id)`
   - `get_task_strategy_type(task_id)`
   - `get_running_task()` 返回任务 ID 和策略类型。
2. 策略1旧接口默认只查询 `strategy_type IS NULL OR strategy_type='STRATEGY_1_CUP_HANDLE'`。
3. 策略2接口只接受 `STRATEGY_2_EXTREME_DRY_STABLE` 任务 ID。
4. 策略2接口收到策略1任务 ID 时返回 HTTP 404 或 400 + 稳定错误码 `TASK_STRATEGY_MISMATCH`。
5. 策略1任务列表只返回策略1任务；策略2继续使用独立任务列表。

#### 必须新增测试

- 策略2任务完成后，策略1默认候选仍返回最新策略1候选。
- 两个任务列表互不混入。
- 使用策略1 task_id 查询策略2列表和详情明确拒绝。
- DB fallback 状态正确返回策略2类型。
- 旧任务 `strategy_type=NULL` 仍按策略1处理。

---

### BUG-S2-008：全数据源失败后没有按设计回退新鲜缓存

#### 问题现象

共享日线服务会读取缓存，并在数据源成功时合并缓存，但所有数据源失败后始终返回 `data=None`。

#### 涉及模块

- `scanner/daily_data_service.py:fetch_with_retry`
- `scanner/daily_data_service.py:_build_all_failed_result`

#### 证据链

- 函数开始处读取 `cached = db.get_ohlc(code)`。
- 成功数据源路径会合并并保存缓存。
- 全失败路径直接 `_build_all_failed_result(...)`，没有检查缓存新鲜度，也没有设置 `from_cache=True`。
- 设计文档明确要求：四数据源均失败时，只允许使用符合新鲜度要求的缓存。

#### 影响

存在可用新鲜缓存时，策略2仍把股票记录为 `ALL_DATA_SOURCES_FAILED`，降低扫描完整性。

#### 修复建议

1. 提取统一缓存新鲜度函数，不要仅用“缓存非空”判断。
2. 全数据源失败后：
   - 缓存新鲜：返回缓存，`from_cache=True`，保留所有 source_errors。
   - 缓存过期或为空：返回 `data=None`。
3. 明确交易日、盘中和收盘后的新鲜度规则，并与现有项目行为保持一致。
4. 记录缓存回退日志和最终使用的数据日期。

#### 必须新增测试

- 全源失败 + 新鲜缓存：返回缓存且 `from_cache=True`。
- 全源失败 + 过期缓存：返回 `None`。
- 数据源成功时仍优先使用新数据并正确合并。

---

### BUG-S2-009：候选入库失败仍被标记和广播为候选

#### 问题现象

scanner 在候选持久化之前，就把股票加入内存候选集合并更新为 `candidate`。数据库写入异常只记录日志，之后仍广播 discovery。

#### 涉及模块

- `strategy2/scanner.py` 候选分支

#### 证据链

当前顺序是：

1. `candidate_by_code[code] = evaluation`
2. `task_stock.status = candidate`
3. 尝试 `upsert_strategy2_candidate`
4. 写入失败只 `logger.error`
5. 继续发送 discovery

#### 影响

- 实时界面看到候选，刷新后候选消失。
- `task_stocks` 和 `strategy2_candidates` 不一致。
- 任务候选数和结果 API 数量不一致。

#### 修复建议

调整为事务语义：

1. 构造 discovery。
2. 成功写入 `strategy2_candidates`。
3. 再把 task_stock 标记为 candidate。
4. 再加入内存候选并广播。
5. 写入失败时将 task_stock 标记为 failed，使用稳定错误码，例如 `STRATEGY2_CANDIDATE_PERSIST_FAILED`，保留错误详情。

同时修复进度回调：失败和跳过路径也必须更新 processed/skipped/failed，不能只在正常评估结束时回调。

#### 必须新增测试

- mock `upsert_strategy2_candidate` 抛异常，断言没有 discovery、没有候选计数，task_stock 为 failed。
- skipped、failed、candidate、scanned 四类路径的 processed 均单调增加且最终一致。

---

### BUG-S2-010：扫描控制台和策略2结果页未形成独立展示闭环

#### 问题现象

扫描控制台虽然能启动策略2，但轮询、实时发现映射和完成后结果加载仍使用策略1逻辑。策略2结果页只展示摘要表，并把股票链接到策略1详情页。

#### 涉及模块

- `web/src/pages/ScannerConsole.vue`
- `web/src/pages/Strategy2Results.vue`
- `web/src/composables/useApi.js`

#### 证据链

- 策略2启动后，`pollStatus()` 仍调用通用 `getScanStatus()`。
- discovery 映射固定读取 `d.score`，策略2 discovery 使用 `d.total_score`。
- 扫描完成后固定调用 `loadResults()`，其中读取策略1 `getCandidates()`。
- Strategy2Results 的股票链接指向 `/stock/{code}`，这是策略1详情页。
- `getStrategy2Candidate()` 已存在，但结果页未使用。
- 设计要求的 V3/V5/V10/V20、V5/V20、分位、区间、收益、评分原因和风险详情未展示。

#### 影响

- 策略2实时发现可能显示空分数或错误等级。
- 策略2扫描完成后控制台加载策略1候选。
- 用户无法查看策略2候选入选原因。

#### 修复建议

1. ScannerConsole 保存 `activeStrategyType`。
2. 轮询和 discovery 映射按策略类型分支：
   - 策略1使用 `score`。
   - 策略2使用 `total_score/level/risk_ratio`。
3. 策略2完成后加载策略2结果或导航到 `/strategy2/results`，不得调用策略1候选接口。
4. Strategy2Results 增加独立详情抽屉、弹窗或路由，调用 `getStrategy2Candidate(code, taskId)`。
5. 详情展示完整指标、评分原因、风险信息和数据源；不得显示杯柄/VCP字段。

#### 必须验证

- 启动策略2后实时发现显示总分、等级和风险比。
- 策略2完成后不加载策略1候选。
- 点击策略2候选只进入策略2详情。
- 页面刷新后恢复正确策略名称、任务和进度。

---

### BUG-S2-011：策略2候选 JSON 字段未反序列化，默认排序缺少风险比

#### 问题现象

`score_reasons` 和 `reject_reasons` 写入时是 JSON 字符串，读取后仍是字符串；候选列表只按总分降序，没有按设计使用风险比作为次级排序。

#### 涉及模块

- `scanner/db.py:get_strategy2_candidates`
- `scanner/db.py:get_strategy2_candidate`

#### 证据链

最小复现：

```text
strategy2_json_types= str '["A"]'
```

查询 SQL 当前为：

```sql
ORDER BY total_score DESC
```

#### 影响

- API 的数组字段类型不稳定，前端详情无法直接遍历。
- 同分候选顺序不按风险优先，结果不稳定。

#### 修复建议

1. 增加统一 `_json_loads_list()`，在所有策略2候选读取路径中把两个字段转换为 list。
2. 空字符串、NULL 和非法旧值应安全转换为空列表并记录必要日志。
3. 列表默认排序改为：

```sql
ORDER BY total_score DESC, risk_ratio ASC, code ASC
```

`code ASC` 用于保证完全同分同风险时顺序稳定。

#### 必须新增测试

- 列表和详情 API 返回的两个原因字段均为数组。
- 同分候选按风险比升序；同分同风险按代码稳定排序。

---

## 5. 建议修复顺序

为减少重复修改和回归，建议严格按以下顺序执行：

1. **建立共享契约辅助函数**
   - `resolve_strategy2_config`
   - 完整行情验证与策略窗口裁剪
   - 最近 N 日涨跌序列
   - 任务类型查询辅助函数
   - JSON list 读取辅助函数
2. **修复核心策略正确性**
   - BUG-S2-002、003、004、005
3. **修复任务生命周期和策略隔离**
   - BUG-S2-001、006、007
4. **修复数据与持久化一致性**
   - BUG-S2-008、009、011
5. **修复前端闭环**
   - BUG-S2-010
6. **运行全部契约测试、策略1回归和前端人工验证**

---

## 6. 给修复 AI 的执行要求

请按照以下要求一次完成修复：

1. 不要修改策略2已确认的评分阈值、分值、等级和风险公式。
2. 不要修改策略1的检测、评分、决策和回测业务规则。
3. 不要把策略2接入策略1的判断模块，也不要把策略2候选写入 `candidates`。
4. 策略窗口裁剪只能由策略2唯一评估入口负责；其他入口不得复制策略裁剪逻辑。
5. 最近 5 日跌幅评分与否决必须复用同一个辅助函数。
6. 后端配置校验必须是最终权威，前端校验只能作为用户体验增强。
7. 所有按 task_id 查询策略结果的 API 都必须先验证任务存在和策略类型。
8. 中断恢复必须按 `strategy_type` 分派，未知类型不得默认执行。
9. 候选持久化成功后才能标记 candidate 和发送 discovery。
10. 不要大规模重构无关模块，不要新增大型框架，不要修改 `.gitignore`。
11. 每个 BUG 至少增加一个会在旧代码失败、修复后通过的测试。
12. 修复完成后更新第三方审核说明或新增修复完成报告，逐项列出 BUG 与测试证据。

### 建议改动文件

- `strategy2/engine.py`
- `strategy2/indicators.py`
- `strategy2/rejection.py`
- `strategy2/scanner.py`
- 可新增一个轻量的 `strategy2/validation.py` 或 `strategy2/utils.py`，仅在确实减少重复时使用。
- `scanner/daily_data_service.py`
- `scanner/db.py`
- `server.py`
- `web/src/pages/ScannerConsole.vue`
- `web/src/pages/Strategy2Results.vue`
- 对应 `tests/` 文件

---

## 7. 回归测试清单

### 核心策略

- 策略窗口外数据不影响结果。
- 相同窗口尾部数据产生完全相同结果。
- 最近 5 日第一天、居中、最后一天的大跌均正确识别。
- `V20=0` 不得成为候选。
- 必需字段缺失、NaN、Inf、无效 OHLC、日期倒序和重复均返回 `INVALID_MARKET_DATA`。
- 所有指标、支撑位和风险计算不读取策略窗口外数据。

### 配置与任务

- 策略2无效配置不能保存。
- 策略2无效配置不能创建任务。
- 策略2窗口不能超过 `min_listing_days`。
- 策略1与策略2互斥保持有效。
- 中断策略1由策略1恢复。
- 中断策略2由策略2恢复。
- 未知任务类型不执行。

### 数据源与持久化

- 主源成功、备用源成功、新鲜缓存回退、过期缓存拒绝。
- 候选入库失败时不广播、不计候选。
- 单股失败不中断全任务。
- skipped、failed、scanned、candidate 计数与 processed 一致。
- JSON 原因字段读取为数组。
- 同分候选按风险比升序。

### API 与前端

- 策略1默认候选不受最新策略2任务影响。
- 策略1和策略2任务列表完全隔离。
- 策略1 task_id 查询策略2结果明确拒绝。
- 策略2实时发现展示正确字段。
- 策略2完成后不加载策略1结果。
- 策略2详情展示完整指标、评分原因和风险信息。
- 页面刷新后恢复正确策略类型与进度。

### 建议验证命令

```bash
python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_yfinance_hist.py
python -m compileall strategy2 scanner server.py -q
cd web && npm run build
git diff --check
```

联网数据源探测测试应单独执行并单独报告，不能用外部网络失败掩盖业务测试结果。

---

## 8. 不建议修改的内容

- 不要修改策略1杯柄/VCP识别与评分规则。
- 不要修改策略2已确认的 50 + 50 分评分结构。
- 不要调整策略2一票否决阈值和风险公式，除非另有业务确认。
- 不要把两个策略候选表合并。
- 不要删除现有多数据源互斥锁、重试和缓存机制。
- 不要让前端直接推导策略结果；策略结果必须以后端为准。
- 不要借本次修复开发策略2回测、重评估或 CSV 导出。

---

## 9. 最终交付标准

修复完成后必须同时满足：

1. BUG-S2-001 至 BUG-S2-011 均有对应修复和自动化测试。
2. 零成交量、窗口外坏数据、最近 5 日首日大跌三个最小复现全部被正确拒绝或忽略。
3. 策略2中断任务只通过策略2扫描器恢复。
4. 策略1与策略2的任务、默认候选、详情和前端展示完全隔离。
5. 配置保存和任务启动前均完成后端策略2校验。
6. 新鲜缓存回退行为符合设计，过期缓存不会被误用。
7. 候选数据库、任务状态、实时 discovery 和 API 结果一致。
8. 离线测试、编译检查、前端构建和 `git diff --check` 全部通过。
9. 全量测试中的任何失败都必须说明是否为外部网络原因，不得只报告通过数量。

---

## 10. 本次审核验证记录

### 最小复现结果

```text
prefix_outside_window= False INVALID_MARKET_DATA
zero_volume= True 80 None 0.0
first_of_recent5_drop= []
default_s1_candidates_after_s2= []
interrupted= {'id': 's2-int', 'scanned': 0, 'total_stocks': 1}
strategy2_json_types= str '["A"]'
strategy2_with_s1_task_id= []
```

### 自动化验证

- Strategy2 测试：`104 passed`
- 离线全量测试：`354 passed`
- Python 编译检查：通过
- 前端生产构建：通过
- 完整测试：`356 passed, 1 failed`
  - 唯一失败：`tests/test_akshare_hist.py::test_dongcai`
  - 原因：外部东财接口连接被远端关闭，与本次业务代码审核结论无关。

现有测试全部通过仍未发现上述策略错误，说明修复时必须优先补充本文列出的边界契约测试。

# Strategy2 最终验收复审报告 Round 2

## 1. 检查范围

本次验收针对提交：

- 当前修复提交：`c14b974 fix(strategy2): final acceptance — remove cache fallback, converge sources, fix failure UI`
- 上一轮基线：`b427df1`
- 执行依据：
  - `docs/reviews/2026-06-10-strategy2-final-acceptance-recheck.md`
  - `docs/reviews/2026-06-10-strategy2-final-acceptance-fix-ai-prompt.md`

重点复核：

- 全数据源失败时禁止缓存回退
- Strategy2 失败终态和 processed 进度
- Strategy1 / Strategy2 实时 API 隔离
- 三数据源收敛
- 前端失败股票、中文原因、数据源详情、分页和历史入口
- ACCEPT-S2-001~006 测试可信度

---

## 2. 总体结论

**本次验收仍不通过。**

本轮后端核心修复已经生效：

- Strategy2 全数据源失败不会再留下 `fetching` 股票。
- 全源失败会记录 `failed / ALL_DATA_SOURCES_FAILED`、结束时间和 processed 回调。
- 即使数据库存在旧缓存，全源失败后也不会回退缓存继续扫描。
- Strategy1 实时候选列表和详情不再泄漏 Strategy2 discovery。
- 默认配置、共享日线服务和 DataSourceManager 已收敛为百度、新浪、腾讯。
- 后端失败列表 API 能正确返回真实失败总数、分页数据和 `source_errors`。

但前端失败展示存在一个高严重度运行时错误：失败详情引用了 `v-for` 作用域外的变量 `f`。当失败面板出现时，编译产物会读取未定义的 `f.code`，导致页面运行时报错，用户仍然无法可靠查看失败信息。

另外，Strategy2 历史结果页没有失败列表入口，历史任务打开扫描控制台时也无法恢复任务策略类型；三数据源收敛未覆盖 Strategy1 引擎、单股回测和依赖；新增测试仍未覆盖这些问题。

---

## 3. 上一轮问题复核结果

| 上一轮编号 | 复核结果 | 说明 |
| --- | --- | --- |
| ACCEPT-S2-001 | 已修复 | 全源失败和评估异常均进入 failed 终态 |
| ACCEPT-S2-002 | 已修复 | Strategy1 实时 API 不再返回 Strategy2 discovery |
| ACCEPT-S2-003 | 已修复 | 共享日线服务全源失败不再回退缓存 |
| ACCEPT-S2-004 | 部分修复 | 默认配置和共享服务已收敛；Strategy1 引擎、单股回测、依赖仍保留 mootdx/yfinance |
| ACCEPT-S2-005 | 部分修复 | 新增真实测试，但“六种终态”测试并未分别制造六种终态，且没有前端运行时测试 |
| ACCEPT-S2-006 | 部分修复 | 中文原因、总数、加载更多已编码；失败详情运行时崩溃，Strategy2 历史入口未实现 |

---

## 4. 问题清单

| 编号 | 问题 | 严重程度 | 影响范围 | 是否必须修复 |
| --- | --- | --- | --- | --- |
| ROUND2-S2-001 | 失败详情引用 `v-for` 作用域外变量，失败面板运行时崩溃 | 高 | 前端失败展示、用户故障定位 | 是 |
| ROUND2-S2-002 | 历史任务无法可靠恢复策略上下文，Strategy2 结果页仍无失败入口 | 高 | 历史失败查看、结果正确性、重试入口 | 是 |
| ROUND2-S2-003 | 三数据源收敛未覆盖 Strategy1 引擎、单股回测和依赖 | 中 | 数据源约束、外部依赖、配置兼容 | 是 |
| ROUND2-S2-004 | 验收测试仍存在覆盖声明与真实行为不一致 | 中 | 回归防护、验收可信度 | 是 |

---

## 5. 详细问题分析

### ROUND2-S2-001：失败详情引用 `v-for` 作用域外变量，失败面板运行时崩溃

#### 问题现象

`ScannerConsole.vue` 中，失败行的 `v-for` 已经结束，失败详情仍继续引用 `f.code`、`f.status_reason` 等字段：

```vue
<div v-for="f in failures" :key="f.code" class="failure-row">
  ...
</div>

<div v-if="expandedFailures[f.code]" class="failure-detail">
  <div>{{ f.status_reason }}</div>
  ...
</div>
```

`f` 只在 `v-for` 元素内部有效。失败详情位于循环外，运行时没有 `f`。

#### 编译产物证据

Vite 构建不会拒绝该模板，但生成的代码包含：

```text
G[e.f.code] ? ...
e.f.status_reason
e.f.source_errors
```

组件上下文中没有 `f`，失败面板渲染时会读取未定义对象的 `code` 属性。

#### 涉及模块

- `web/src/pages/ScannerConsole.vue:84-97`
- 构建产物 `web/dist/assets/ScannerConsole-*.js`

#### 触发条件

- 当前任务存在至少一只失败股票。
- `failuresTotal > 0`，失败面板开始渲染。

#### 影响

- 用户最需要查看失败原因时，页面可能直接运行时报错。
- 中文失败原因、数据源详情和分页功能无法可靠使用。
- `npm run build` 仍然通过，容易造成假验收。

#### 修复建议

使用 `<template v-for>` 把失败行和对应详情放在同一作用域：

```vue
<template v-for="f in failures" :key="f.code">
  <div class="failure-row" @click="toggleFailureDetail(f)">
    ...
  </div>
  <div v-if="expandedFailures[f.code]" class="failure-detail">
    ...
  </div>
</template>
```

或者将当前展开股票保存为 `expandedFailureCode`，但详情数据仍必须从一个确定的失败对象获取。

#### 验证方式

必须增加前端组件或端到端测试：

1. 注入一只 `ALL_DATA_SOURCES_FAILED` 股票。
2. 页面成功渲染失败面板，无运行时异常。
3. 点击失败行。
4. 展示中文原因、原始错误码和百度/新浪/腾讯错误详情。
5. 点击第二只失败股票，展示对应股票详情，不能串行或引用错误对象。

---

### ROUND2-S2-002：历史任务无法可靠恢复策略上下文，Strategy2 结果页仍无失败入口

#### 问题现象

`Strategy2Results.vue` 本轮没有修改，仍只显示候选结果，没有失败数量、失败列表或“查看失败股票”入口。

目前唯一失败入口在 Strategy1 的 `TaskCenter.vue`：

```javascript
function viewFailures(id) {
  router.push(`/?task=${id}&status=failed`)
}
```

Strategy2 任务不在该 TaskCenter 中展示，因此用户无法从 Strategy2 历史任务页面进入失败列表。

即使手工打开：

```text
/?task=<strategy2-task-id>&status=failed
```

ScannerConsole 也只从全局 `/api/scan/status` 恢复 `activeStrategyType`。历史任务没有正在运行时，`strategyType` 为 `null`，页面无法知道 query task 属于 Strategy2。

#### 连带影响

- 历史 Strategy2 任务会调用 Strategy1 `loadResults()` 路径，可能显示最新 Strategy1 候选或错误结果。
- 历史 Strategy1 任务打开失败列表时，`activeStrategyType` 同样可能为 `null`，原有“重新拉取”按钮会被错误隐藏。
- Strategy2 历史失败查看要求仍未完成。

#### 涉及模块

- `web/src/pages/Strategy2Results.vue`
- `web/src/pages/ScannerConsole.vue:onMounted`
- `web/src/pages/TaskCenter.vue`
- `server.py:get_task_stocks`

#### 修复建议

推荐为任务上下文提供统一后端接口，或扩展任务股票接口：

```json
{
  "task_id": "xxx",
  "strategy_type": "STRATEGY_2_EXTREME_DRY_STABLE",
  "status": "completed",
  "stocks": [],
  "total": 35
}
```

前端加载 query task 时，应先恢复该任务自己的 `strategy_type`，不能使用当前全局运行任务类型代替历史任务类型。

Strategy2Results 至少增加：

- 当前任务失败数量。
- “查看失败股票”入口。
- 可直接在页面中加载失败列表，或跳转到通用失败页并携带任务策略类型。

Strategy1 历史失败页仍应保留可用的失败重试按钮；Strategy2 历史失败页必须隐藏 Strategy1 重试按钮。

#### 验证方式

- 从 Strategy2Results 选择一个有失败股票的历史任务，可以进入失败列表。
- 刷新历史失败页后，仍识别为 Strategy2。
- 页面不调用 Strategy1 候选接口。
- Strategy2 不显示重新拉取按钮。
- 从 Strategy1 TaskCenter 进入历史失败页，仍显示 Strategy1 重新拉取按钮。

---

### ROUND2-S2-003：三数据源收敛未覆盖 Strategy1 引擎、单股回测和依赖

#### 问题现象

以下部分已经收敛为三数据源：

- `config.yaml`
- `scanner/daily_data_service.py`
- `scanner/data_source.py`

但以下生产相关代码仍保留 mootdx / yfinance：

```text
scanner/engine.py
  _daily_fetch_fn("mootdx") 仍返回 fetch_mootdx_daily
  _daily_fetch_fn("yfinance") 仍返回 fetch_yfinance_daily

scanner/single_stock_backtest.py
  仍把 yfinance 放入回测数据源链

requirements.txt
  仍安装 mootdx 和 yfinance

Strategy2 设计文档
  仍声明百度、新浪、腾讯、yfinance 数据源
```

真实复现：

```text
scanner.engine._daily_fetch_fn("mootdx")  -> accepted
scanner.engine._daily_fetch_fn("yfinance") -> accepted
```

#### 原因

新增收敛测试只检查 `scanner.daily_data_service._daily_fetch_fn()`，没有检查 Strategy1 引擎自己的重复实现，也没有检查回测和依赖。

#### 影响

- 旧配置或其他调用仍能让 Strategy1 引擎进入未批准数据源。
- 单股回测仍会调用 yfinance。
- 安装和全量测试仍受 mootdx / yfinance 影响；本轮全量测试仍出现 Yahoo Finance 429。
- 文档和实际业务决定不一致。

#### 修复建议

1. 删除 `scanner/engine.py` 中 mootdx / yfinance 导入和映射。
2. 最好删除 Strategy1 引擎重复的数据拉取实现，统一使用 `scanner.daily_data_service`；若本轮不重构，至少保证两处可用源严格一致。
3. 从 `scanner/single_stock_backtest.py` 的生产数据链删除 yfinance。
4. 从 `requirements.txt` 删除不再使用的 mootdx / yfinance。
5. 对不再使用的源文件和外部网络测试，按项目决定删除或明确移到非生产实验目录。
6. 更新设计文档中的数据源说明。

#### 验证方式

- `scanner.engine._daily_fetch_fn("mootdx")` 抛出 unknown source。
- `scanner.engine._daily_fetch_fn("yfinance")` 抛出 unknown source。
- 单股回测数据源链严格为百度、新浪、腾讯。
- `requirements.txt` 不包含 mootdx / yfinance。
- 全量测试不再运行 Yahoo Finance 外部测试。
- 全仓生产路径不再引用 mootdx / yfinance。

---

### ROUND2-S2-004：验收测试仍存在覆盖声明与真实行为不一致

#### 问题现象

新增测试名为：

```python
test_all_six_terminal_states_covered
```

但测试只是让六只股票使用同一份数据、同一个 fetch 和同一个引擎逻辑，然后断言六只股票都处于某个终态。它没有分别制造：

- candidate
- scanned
- skipped
- all-sources-failed
- persist-failed
- evaluation-error

因此该测试不能证明“六种终态全部覆盖”。

此外：

- ACCEPT-S2-006 没有任何前端运行时测试，所以 `f` 作用域错误未被发现。
- `test_no_pass_or_inspect_in_acceptance_tests` 自身仍使用 `inspect.getsource()` 做元检查，无法替代真实行为覆盖。
- `test_evaluation_exception_produces_failed_status` 中相同 monkeypatch 代码重复两次。
- 全量测试出现未处理后台线程异常警告：`sqlite3.OperationalError: no such table: task_stocks`，说明测试间仍存在后台线程或全局 DB 状态污染。

#### 修复建议

1. 将六种终态拆成参数化真实行为测试，每种状态单独制造条件并断言 DB、processed 和回调。
2. 增加 ScannerConsole 失败面板组件测试。
3. 删除重复 monkeypatch 和无效元测试。
4. 所有测试启动的后台线程必须 join 或 mock，测试结束前不得遗留线程。
5. 把 `PytestUnhandledThreadExceptionWarning` 视为测试失败处理。

#### 验证方式

- 故意重新引入失败详情 `f` 作用域错误时，前端测试必须失败。
- 故意破坏任意一种终态时，对应测试必须失败。
- 离线和全量测试无未处理线程异常警告。

---

## 6. 建议修复顺序

1. 修复 ROUND2-S2-001，确保失败信息页面可以正常渲染。
2. 修复 ROUND2-S2-002，完成 Strategy2 历史失败入口和历史任务策略上下文。
3. 修复 ROUND2-S2-003，彻底收敛三数据源。
4. 修复 ROUND2-S2-004，增加能捕获真实问题的测试。
5. 重新运行完整验收。

---

## 7. 给修复 AI 的执行要求

1. 不要修改 Strategy1 / Strategy2 的评分、否决、风险和选股规则。
2. 不要恢复任何全源失败缓存回退。
3. 修复失败详情作用域时，必须增加真实前端运行时测试。
4. 历史任务策略类型必须来自目标任务本身，不能来自当前全局运行状态。
5. Strategy2 历史任务必须提供失败列表入口。
6. 生产数据源严格限制为百度、新浪、腾讯，包括扫描、回测、依赖和文档。
7. 测试名称必须与真实覆盖一致，不得用同一路径的六只股票冒充六种终态。
8. 修复后不得存在未处理后台线程异常警告。

---

## 8. 回归测试清单

- 全源失败且存在旧缓存时，Strategy2 股票仍标记 failed。
- 全源失败 processed 最终达到 total。
- 失败面板能显示中文原因和三个数据源错误。
- 点击每只失败股票都展开对应详情，无运行时错误。
- 55 只失败股票显示真实总数，并可加载第 51-55 只。
- Strategy2Results 可进入历史失败列表。
- 历史 Strategy2 失败页刷新后仍识别为 Strategy2。
- 历史 Strategy1 失败页仍显示重新拉取按钮。
- Strategy2 失败页不显示 Strategy1 重试按钮。
- Strategy1 / Strategy2 实时 discovery 继续隔离。
- scanner、回测、配置和依赖均只包含百度、新浪、腾讯。
- 六种终态分别有真实行为测试。
- 测试运行无后台线程异常警告。

---

## 9. 本次验证记录

```text
python -m pytest tests/test_strategy2_acceptance_fixes.py tests/test_strategy2_final_fixes.py tests/test_strategy2_recheck_fixes.py tests/test_strategy2_bug_fixes.py tests/test_strategy2_engine.py tests/test_server_scan_api.py -q
结果：115 passed

python -m pytest tests -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_yfinance_hist.py --ignore=tests/test_tushare_hist.py
结果：445 passed

python -m pytest tests -q
结果：448 passed, 2 failed
外部失败：东财代理连接失败、Yahoo Finance 429
附加问题：出现 PytestUnhandledThreadExceptionWarning，后台线程访问不存在的 task_stocks 表

python -m compileall strategy2 scanner server.py -q
结果：通过

cd web && npm.cmd run build
结果：通过，但构建产物仍包含未定义上下文变量 e.f.code，不能证明运行时正确

git diff --check b427df1..c14b974
结果：通过
```

真实后端复现：

```text
Strategy2 全源失败且数据库存在旧缓存：
status=failed
status_reason=ALL_DATA_SOURCES_FAILED
processed=1
source_errors={"baidu":"timeout","sina":"456","tencent":"empty"}
```

真实 API 分页复现：

```text
55 只失败股票：
page=1 total=55 len=50
page=2 total=55 len=5
```

---

## 10. 最终交付标准

1. 前端失败面板无运行时异常。
2. 用户能查看失败股票中文原因和三个数据源错误。
3. Strategy2 历史任务提供可发现、可刷新的失败列表入口。
4. 历史任务使用自身策略类型加载结果和决定操作按钮。
5. 生产数据链完整收敛到百度、新浪、腾讯。
6. 全源失败不使用缓存的规则保持不变。
7. 每种终态都有真实行为测试。
8. 离线测试、前端测试、构建、compileall 和 diff 检查通过。
9. 测试无未处理后台线程异常警告。


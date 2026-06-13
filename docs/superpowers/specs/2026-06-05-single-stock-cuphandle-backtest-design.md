# 单股杯柄策略回测设计

Date: 2026-06-05

## 1. 背景与目标

新增“单股杯柄策略回测”功能，用于检验当前杯柄策略在指定股票和指定时间段内是否有效，并解释用户指定柄区域为什么符合或不符合策略。

第一版目标：

1. 前端提供单股回测页面。
2. 用户输入股票代码、回测开始日期、回测结束日期。
3. 用户可选输入指定柄开始日期、指定柄结束日期。
4. 后端提供单股杯柄回测接口。
5. 返回回测时间段内所有符合当前杯柄策略的柄区域。
6. 如用户指定柄区域，返回该区域是否符合策略。
7. 如指定柄区域不符合策略，返回详细失败原因：规则名称、策略要求值、实际计算值、失败严重程度、中文解释说明。
8. 返回 `strategyVersion` 和 `configHash`。
9. 前端展示自动识别结果列表、指定柄区域诊断、评分拆解和 K 线图标记。
10. 回测结果即时返回，并保存一份 JSON 到 `output_data/backtests/`。

## 2. 明确不做

第一版不做：

- 不做 VCP-only 回测或展示。
- 不做多策略切换。
- 不做异步任务队列。
- 不做回测历史列表。
- 不做买卖收益曲线或交易绩效统计。
- 不做 partial 回测。
- 不自动缩短用户输入回测区间。
- 不在 SQLite 新增回测结果表。

## 3. 核心原则

### 3.1 复用当前杯柄策略

必须复用当前全市场扫描使用的杯柄识别策略，不重新写一套不一致的规则。

新增公共策略引擎 `CupHandleStrategyEngine`，统一编排：

- pattern config 构建。
- `detect_cup_handle()` 调用。
- `score_cup_handle_advanced()` 调用。
- `analyze_dry_stable()` 调用。
- 杯柄策略结果序列化。
- 指定柄区域诊断。

引擎只编排既有策略模块，不复制或替代主策略判断。

### 3.2 严格真实数据完整性

必须保证使用真实 K 线数据覆盖：

1. 用户输入回测区间。
2. 杯柄策略所需前置历史上下文。

如果 SQLite 缓存已经完整覆盖所需范围，则直接使用缓存，不重新拉取。

如果缓存不完整，则执行 fresh-first：

1. 主数据源。
2. 备用数据源。
3. 成功后与 SQLite 缓存合并并保存。
4. 再次检查覆盖范围。

fresh-first 后仍无法完整覆盖所需范围时，接口返回错误，不执行回测。

### 3.3 回测不使用未来数据

自动识别采用滑动窗口，模拟真实扫描时点：

- 对回测区间内每个交易日，使用该日及以前的 K 线数据调用同一套杯柄策略。
- 不使用判断日之后的数据判断当日是否形成策略结果。

指定柄区域诊断以柄结束日期作为判断时点：

- 只使用 `<= 指定柄结束日期` 的数据。
- 不使用柄结束日之后的数据辅助判断。

### 3.4 第一版只做杯柄

当前全市场扫描实际包含“杯柄检测 + 干稳低吸分析 + VCP 补位”。本功能第一版只做杯柄策略回测：

- 自动识别只返回完整杯柄/柄部结构符合当前策略的区域。
- 指定柄诊断只围绕完整杯柄策略解释。
- VCP-only 机会不进入单股杯柄回测结果。

## 4. 后端设计

### 4.1 新增公共策略引擎

建议新增文件：

```text
scanner/strategy_engine.py
```

核心类：

```python
class CupHandleStrategyEngine:
    strategy_version = "cuphandle-v1"

    def __init__(self, config: dict):
        ...

    def evaluate_at(
        self,
        data_until_date: list[dict],
        *,
        code: str = "",
        name: str = "",
        market_data: list[dict] | None = None,
    ) -> StrategyEvaluation:
        """在某个判断时点，用已有历史数据判断是否形成杯柄策略结果。"""

    def diagnose_handle(
        self,
        data_until_handle_end: list[dict],
        handle_start_date: str,
        handle_end_date: str,
        *,
        code: str = "",
        name: str = "",
        market_data: list[dict] | None = None,
    ) -> HandleDiagnosis:
        """严格判断用户指定区间是否可作为完整杯柄策略里的柄部。"""
```

`CupHandleStrategyEngine` 负责统一构建当前扫描使用的 `pattern_cfg`：

- `config["cup"]`
- `config["handle"]` 加 `handle_` 前缀
- `config["breakout"]`

`evaluate_at()` 内部流程：

1. 调用 `detect_cup_handle(data_until_date, pattern_cfg)`。
2. 如果未找到杯柄，返回未通过结果；不走 VCP-only 候选提升。
3. 如果找到杯柄，补充 `code/name`。
4. 调用 `score_cup_handle_advanced(result, data_until_date, scoring_cfg)`。
5. 调用 `analyze_dry_stable(result, data_until_date, market_data=market_data)`。
6. 按当前杯柄候选策略生成通过/失败结论。
7. 输出统一结构，包括形态点位、柄区间、评分、评分拆解、交易计划、决策、规则诊断、`strategyVersion`、`configHash`。

柄区间推导：

- `handle_start_idx = result.right_high_idx + 1`
- `handle_end_idx = len(data_until_date) - 1`
- `handle_low_idx = result.handle_low_idx`

### 4.2 单股回测模块

建议新增文件：

```text
scanner/single_stock_backtest.py
```

核心函数：

```python
run_single_stock_cuphandle_backtest(
    code: str,
    start_date: str,
    end_date: str,
    config: dict,
    handle_start_date: str | None = None,
    handle_end_date: str | None = None,
) -> dict
```

计算流程：

1. 验证参数：股票代码、日期格式、开始日期不晚于结束日期。
2. 如传入指定柄区域，验证柄开始/结束日期完整且不晚于回测结束日期。
3. 计算策略所需数据范围：用户回测区间 + 前置历史上下文。
4. 检查 SQLite `daily_ohlc` 是否完整覆盖所需范围。
5. 如覆盖，直接使用 SQLite 数据。
6. 如不覆盖，执行 fresh-first 拉取、合并并保存。
7. fresh-first 后再次检查覆盖范围；不完整则返回错误。
8. 对回测区间内每个交易日做滑动判断：
   - 取前置历史到当前判断日的数据。
   - 调用 `CupHandleStrategyEngine.evaluate_at()`。
   - 通过时记录该判断时点形成的柄区域。
9. 对自动识别结果去重：
   - 按 `(handle_start_date, handle_end_date, handle_low_date)` 聚合。
   - 连续多日识别到同一区域时，保留最高分结果，同时记录 `firstDetectedDate`。
10. 如用户输入指定柄区域：
    - 取 `<= handle_end_date` 的数据。
    - 调用 `CupHandleStrategyEngine.diagnose_handle()`。
11. 将响应保存为 JSON 到 `output_data/backtests/`。
12. 返回响应。

### 4.3 前置历史上下文

杯柄检测需要足够历史 K 线。第一版所需上下文按配置和安全缓冲计算：

```text
required_context_days = max(
  cup.max_duration + handle.max_duration + 30,
  180
)
```

最终所需范围为：

- `required_start_date`: 回测开始日前至少 `required_context_days` 个交易日对应的日期。
- `required_end_date`: 用户输入回测结束日期。

实现时不能只用自然日简单倒推后立即信任；应以实际 K 线交易日覆盖为准。

### 4.4 数据覆盖错误

如 fresh-first 后仍无法完整覆盖所需范围，返回错误，不计算。错误需包含：

- 用户输入区间。
- 策略所需区间。
- 当前可用数据范围。
- 缺失区间。

示例：

```json
{
  "error": "Insufficient data coverage",
  "message": "K线数据无法完整覆盖策略所需区间，已停止回测。",
  "code": "600036",
  "requestedRange": {
    "startDate": "2026-01-01",
    "endDate": "2026-06-01"
  },
  "requiredRange": {
    "startDate": "2025-06-01",
    "endDate": "2026-06-01"
  },
  "availableRange": {
    "startDate": "2026-02-01",
    "endDate": "2026-06-01"
  },
  "missingRanges": [
    {
      "startDate": "2025-06-01",
      "endDate": "2026-01-31"
    }
  ]
}
```

### 4.5 规则诊断模型

统一规则项结构：

```json
{
  "ruleName": "柄部回撤深度",
  "requiredValue": "≤ 15%",
  "actualValue": "22.4%",
  "severity": "high",
  "explanation": "柄部从右杯口回撤过深，说明整理阶段抛压较重，不符合当前杯柄策略对健康柄部的要求。"
}
```

`severity` 固定 4 档：

- `info`: 通过项或提示。
- `low`: 轻微偏离，可能影响评分但不一定阻断。
- `medium`: 重要规则失败，通常导致分数下降或不能入选。
- `high`: 硬性规则失败，直接导致不能进入策略结果。

指定柄诊断返回：

```json
{
  "startDate": "2026-03-10",
  "endDate": "2026-03-28",
  "passed": false,
  "matchedPatternId": null,
  "passedRules": [],
  "failedRules": []
}
```

必须包含 `passedRules` 和 `failedRules`。

### 4.6 诊断辅助函数

当前 `detect_cup_handle()` 只返回 `CupHandleResult(found=False)`，没有失败细节。为满足详细解释要求，新增诊断辅助函数：

```python
diagnose_cup_handle(
    data: list[dict],
    pattern_cfg: dict,
    specified_handle: dict | None = None,
) -> RuleDiagnostics
```

约束：

- 诊断辅助函数不作为策略是否入选的唯一来源。
- 策略判断仍以 `CupHandleStrategyEngine.evaluate_at()` 调用的现有检测和评分结果为准。
- 诊断辅助函数使用相同 config 阈值复算关键中间值，只负责解释 passed/failed rules。

诊断规则包括：

- 数据长度。
- 杯体周期。
- 杯体深度。
- 杯口偏差。
- 底部圆滑度。
- 左右杯壁时间比例。
- 柄部周期。
- 柄部回撤。
- 柄部相对右侧涨幅回撤。
- 突破缓冲。
- 放量倍数。
- 高级评分门槛。
- dry-stable 决策不应为“不建议买入”。
- 指定柄区间是否匹配策略推导柄区间。

### 4.7 全市场扫描接入

第一版采用受控接入：

- 将 `engine.py` 中杯柄相关的 pattern config 构建、杯柄检测、高级评分、dry-stable 编排逐步迁到 `CupHandleStrategyEngine`。
- 保留现有 VCP-only 补位逻辑在 `engine.py`，因为单股杯柄回测不包含 VCP-only。
- 目标是全市场扫描的杯柄部分与单股回测共用同一套杯柄策略逻辑，同时不破坏现有 VCP 候选行为。

## 5. API 设计

### 5.1 Endpoint

新增：

```http
POST /api/stock/{code}/backtest/cup-handle
```

使用 `POST`，因为该接口是计算型请求，有 body 参数，并会保存 JSON 结果。

### 5.2 请求体

```json
{
  "startDate": "2026-01-01",
  "endDate": "2026-06-01",
  "specifiedHandle": {
    "startDate": "2026-03-10",
    "endDate": "2026-03-28"
  }
}
```

字段规则：

- `startDate` 必填。
- `endDate` 必填。
- `specifiedHandle` 可选。
- 如传 `specifiedHandle`，其 `startDate` 和 `endDate` 都必填。
- `specifiedHandle.startDate <= specifiedHandle.endDate`。
- 第一版要求指定柄区间落在回测区间内。

### 5.3 成功响应

```json
{
  "code": "600036",
  "name": "招商银行",
  "strategyVersion": "cuphandle-v1",
  "configHash": "sha256:<64位hex>",
  "request": {
    "startDate": "2026-01-01",
    "endDate": "2026-06-01",
    "specifiedHandle": {
      "startDate": "2026-03-10",
      "endDate": "2026-03-28"
    }
  },
  "dataCoverage": {
    "requestedRange": {
      "startDate": "2026-01-01",
      "endDate": "2026-06-01"
    },
    "requiredRange": {
      "startDate": "2025-06-01",
      "endDate": "2026-06-01"
    },
    "availableRange": {
      "startDate": "2025-01-02",
      "endDate": "2026-06-01"
    },
    "source": "cache|fresh_sina|fresh_tencent|fresh_merged"
  },
  "summary": {
    "totalPatterns": 3,
    "bestScore": 86,
    "firstDetectedDate": "2026-02-18",
    "hasSpecifiedDiagnosis": true,
    "specifiedPassed": false
  },
  "patterns": [],
  "specifiedDiagnosis": null,
  "ohlc": [],
  "outputFile": "output_data/backtests/600036_cuphandle_20260101_20260601_20260605_153012.json"
}
```

`patterns[]` 中每个元素包含：

- `id`
- `detectedDate`
- `firstDetectedDate`
- `score`
- `rating`
- `pattern`
- `tradePlan`
- `scoreBreakdown`
- `decision`
- `passedRules`
- `failedRules`

`pattern` 包含：

- `leftHighDate`
- `cupLowDate`
- `rightHighDate`
- `handleStartDate`
- `handleEndDate`
- `handleLowDate`
- `cupDepthPct`
- `cupDuration`
- `handleDepthPct`
- `handleDuration`
- `lipDeviationPct`
- `isBreakout`
- `isVolumeBreakout`
- `volMultiplier`

`tradePlan` 包含：

- `entryZoneLow`
- `entryZoneHigh`
- `pivot`
- `stopLoss`
- `target1`
- `target2`
- `riskReward1`

### 5.4 参数错误响应

```json
{
  "error": "Invalid request",
  "message": "指定柄结束日期不能晚于回测结束日期。"
}
```

### 5.5 拉取失败响应

```json
{
  "error": "Fetch failed",
  "message": "新浪和腾讯数据源均无法返回该股票的完整K线数据。"
}
```

### 5.6 `strategyVersion` 与 `configHash`

`strategyVersion`：

```text
cuphandle-v1
```

`configHash` 计算方式：

1. 对当前有效 config dict 做稳定 JSON 序列化。
2. 使用 `ensure_ascii=False`、`sort_keys=True`、紧凑 separators。
3. 对 UTF-8 bytes 计算 SHA-256。
4. 返回 `sha256:<hex>`。

策略代码规则变化时升级 `strategyVersion`；配置变化但策略代码不变时，只改变 `configHash`。

## 6. JSON 输出

保存目录：

```text
output_data/backtests/
```

文件名：

```text
{code}_cuphandle_{startDate}_{endDate}_{timestamp}.json
```

保存内容与接口成功响应一致。

第一版前端不依赖历史 JSON 列表；JSON 用于调试、复盘和后续扩展。

## 7. 前端设计

### 7.1 新页面和路由

新增页面：

```text
web/src/pages/SingleStockBacktest.vue
```

新增路由：

```text
/backtest/cup-handle
/backtest/cup-handle/:code
```

导航：

- `TopNav.vue` 增加“单股回测”入口。
- `StockDetail.vue` 可增加“用该股票回测”按钮，跳转到 `/backtest/cup-handle/{code}` 并自动填入股票代码。

### 7.2 页面布局

采用“分析工作台”布局。

左侧固定面板：

1. 参数输入：
   - 股票代码。
   - 回测开始日期。
   - 回测结束日期。
   - 指定柄开始日期。
   - 指定柄结束日期。
   - 运行按钮。
2. 指定柄诊断摘要：
   - 未输入时显示“未指定柄区域”。
   - 输入后显示是否通过、匹配结果 ID、通过规则数、失败规则数、最高严重程度。
   - 展示 failedRules 列表。

右侧主区域：

1. 指标卡片：
   - 自动识别柄区域数量。
   - 最高评分。
   - 数据来源。
   - `strategyVersion`。
   - `configHash` 短 hash，hover/title 显示完整 hash。
2. K 线图：
   - 复用 `StockDetail.vue` 的 `lightweight-charts` 风格。
   - 自动识别区域使用蓝色/金色标记。
   - 用户指定柄区域使用紫色标记。
   - 左杯口、杯底、右杯口、柄低使用 marker。
   - 第一版如带状区间绘制复杂，先用起止 marker + 柄低 marker。
3. 自动识别结果列表：
   - 柄开始日期 ~ 柄结束日期。
   - 检测日期。
   - 分数。
   - 决策。
   - 柄部回撤。
   - 杯体深度。
   - 是否突破。
4. 评分拆解：
   - 点击结果列表行后展示。
   - 展示 volumeDry、priceStable、patternScore、keyPrices/tradePlan、decision summary。

### 7.3 API 封装

扩展：

```text
web/src/composables/useApi.js
```

新增方法：

```js
runCupHandleBacktest(code, payload)
```

页面状态：

- `form`
- `loading`
- `error`
- `result`
- `selectedPatternId`
- `chartReady`

错误展示：

- 数据不足时展示输入区间、策略所需区间、当前可用区间、缺失区间。
- 参数错误展示后端中文 `message`。

## 8. 测试计划

### 8.1 后端单元测试

新增或扩展：

```text
tests/test_cuphandle_strategy_engine.py
tests/test_single_stock_backtest.py
tests/test_single_stock_backtest_api.py
```

覆盖：

1. `CupHandleStrategyEngine` 使用与扫描相同的 pattern config 构建方式。
2. `evaluate_at()` 对有效杯柄返回 passed result。
3. `evaluate_at()` 对 VCP-only 不返回杯柄结果。
4. `diagnose_handle()` 对指定柄成功返回 `passedRules`。
5. `diagnose_handle()` 对柄部过深返回 `failedRules`，且每条包含：
   - `ruleName`
   - `requiredValue`
   - `actualValue`
   - `severity`
   - `explanation`
6. 回测滑动窗口只使用判断日及以前数据。
7. 输入区间数据不足时返回错误，不做 partial 回测。
8. SQLite 数据完整覆盖时不触发 fresh 拉取。
9. SQLite 数据不足时触发 fresh-first，并在合并后验证覆盖。
10. JSON 输出文件写入 `output_data/backtests/`。

### 8.2 API 测试

覆盖：

1. 请求参数缺失。
2. 日期非法。
3. 成功响应包含 `patterns`、`specifiedDiagnosis`、`strategyVersion`、`configHash`、`dataCoverage`、`ohlc`。
4. 数据不足错误响应包含 `requestedRange`、`requiredRange`、`availableRange`、`missingRanges`。

### 8.3 前端验证

构建验证：

```bash
npm --prefix web run build
```

手工验证：

1. 输入股票代码和日期，能运行回测。
2. 自动识别结果列表出现。
3. 点击结果能在 K 线图上看到对应标记。
4. 输入不符合策略的柄区域，能看到 failedRules 中文解释。
5. 数据不足错误能显示缺失区间。

## 9. 关键风险与处理

### 9.1 当前检测器不暴露失败原因

风险：`detect_cup_handle()` 失败时没有规则级失败原因。

处理：新增诊断辅助函数复算关键中间值生成解释，但策略通过/失败仍以公共策略引擎调用现有检测器和评分结果为准。

### 9.2 当前结果不显式存 handle start/end

风险：现有 `CupHandleResult` 只有 `handle_low`，没有完整柄区间。

处理：公共策略引擎统一推导：

- `handle_start = right_high_idx + 1`
- `handle_end = 当前判断日`

所有自动识别、诊断、前端标记都使用该统一推导。

### 9.3 旧扫描逻辑包含 VCP 补位

风险：全市场扫描和单股杯柄回测范围不同。

处理：第一版明确单股回测只做杯柄。全市场扫描保留 VCP-only 补位；杯柄部分逐步迁入公共策略引擎。

### 9.4 数据覆盖判断不能只看自然日

风险：A 股非交易日导致自然日覆盖判断误判。

处理：覆盖判断以实际 K 线日期为准；必须有足够交易日上下文和完整覆盖用户输入回测区间内可交易数据。

## 10. 验收标准

1. 前端存在单股杯柄回测页面。
2. 页面支持股票代码、开始日期、结束日期输入。
3. 页面支持可选柄开始日期、柄结束日期输入。
4. 后端存在 `POST /api/stock/{code}/backtest/cup-handle`。
5. 接口返回回测区间内所有符合杯柄策略的柄区域。
6. 指定柄区域诊断返回 `passedRules` 和 `failedRules`。
7. 每条失败规则包含规则名称、策略要求值、实际计算值、失败严重程度、中文解释。
8. 响应包含 `strategyVersion` 和 `configHash`。
9. 数据不完整时返回错误，不执行回测。
10. 前端 K 线图标记自动识别区域和用户指定柄区域。
11. 回测结果保存 JSON 到 `output_data/backtests/`。
12. 全市场扫描杯柄部分与单股回测使用同一套公共杯柄策略引擎。

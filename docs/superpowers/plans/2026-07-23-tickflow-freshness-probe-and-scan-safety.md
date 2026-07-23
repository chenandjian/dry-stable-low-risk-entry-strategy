# TickFlow 数据新鲜度探测与扫描安全保护实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 防止 TickFlow 尚未发布目标交易日数据时把全市场误判为停牌，并提供一个不会写库的前端远端新鲜度核验工具。

**架构：** 扫描准备层在批量更新后统一判定目标日覆盖，只有确认数据源已发布目标日行情时才允许把单股缺失解释为停牌；否则向所有受影响股票返回可重试的数据源失败。新增独立 `tickflow_data/freshness.py` 负责股票与四个指数的只读批量探测，FastAPI 仅校验和转发，Vue 页面只展示探测结果。

**技术栈：** Python 3.10、FastAPI、SQLite、TickFlow Python SDK、pytest、Vue 3、Vitest。

---

## 文件结构

- 修改 `scanner/data_acquisition.py`：收紧缓存新鲜度，并在 TickFlow 批量准备后执行目标日零覆盖保护。
- 新增 `tickflow_data/freshness.py`：封装只读远端探测、状态归一化和本地日期读取，不调用任何写库函数。
- 修改 `server.py`：增加 `POST /api/tickflow/freshness-check`，校验六位股票代码并在线程中执行同步 SDK 探测。
- 修改 `web/src/composables/useApi.js`：增加探测 API 方法。
- 修改 `web/src/pages/KlineHistory.vue`：增加股票与四指数的新鲜度测试面板。
- 修改 `tests/test_data_acquisition.py`：覆盖精确目标日缓存、全局零覆盖和正常停牌分支。
- 修改 `tests/test_kline_history_api.py`：覆盖 API 校验、状态响应和只读约束。
- 新增 `tests/test_tickflow_freshness.py`：覆盖探测服务的前复权/不复权请求、部分失败和本地日期对照。
- 修改 `web/src/pages/__tests__/KlineHistory.test.js`：覆盖交互、五行结果、中文状态和错误提示。
- 新增 `docs/reviews/2026-07-23-tickflow-freshness-probe-real-validation.md`：记录一次少量真实 TickFlow 验证结果。

### 任务 1：收紧 TickFlow 缓存新鲜度

**文件：**
- 修改：`tests/test_data_acquisition.py`
- 修改：`scanner/data_acquisition.py`

- [ ] **步骤 1：增加失败测试**

增加测试，分别构造 `latest_date < target_date`、`latest_date == target_date` 和 `latest_date > target_date`，断言普通缓存仅在日期精确相等、来源为 TickFlow 且拉取时间达标时返回 `True`。未来日期不能被当前目标日缓存接受。

- [ ] **步骤 2：运行测试并确认红灯**

运行：

```powershell
python -m pytest tests/test_data_acquisition.py::test_tickflow_cache_requires_exact_target_trade_date -q
```

预期：旧实现对早于目标日的数据返回 `True`，测试失败。

- [ ] **步骤 3：最小实现**

将 `_tickflow_stock_cache_is_fresh()` 的日期条件改为：

```python
latest_date == target_date
```

保持来源和 `min_fetch_time` 条件不变，不修改已明确标记停牌股票的其他复用路径。

- [ ] **步骤 4：运行专项测试**

运行：

```powershell
python -m pytest tests/test_data_acquisition.py::test_tickflow_cache_requires_exact_target_trade_date -q
```

预期：PASS。

### 任务 2：阻止批次零覆盖被解释为全市场停牌

**文件：**
- 修改：`tests/test_data_acquisition.py`
- 修改：`scanner/data_acquisition.py`

- [ ] **步骤 1：增加两个失败测试**

测试 A：批量服务对全部股票返回 `success`，但元数据 `latest_date` 均早于目标日，且数据库内不存在任何 TickFlow 目标日元数据。断言 `PreparedTickFlowSession.fetch()` 对每只股票返回 `data=None`，错误包含 `TARGET_TRADE_DATE_UNAVAILABLE`、目标日和远端最新日，不返回 `quote_status='suspended'`。

测试 B：数据库中至少一只 TickFlow 股票覆盖目标日，而另一只成功刷新后仍早于目标日。断言后一只仍可沿用现有个股无交易语义，返回历史数据并标记 `suspended`。

- [ ] **步骤 2：运行测试并确认红灯**

运行：

```powershell
python -m pytest tests/test_data_acquisition.py -q
```

预期：零覆盖测试失败，旧代码把股票标记为 `suspended`。

- [ ] **步骤 3：增加覆盖查询和失败归类**

在 `scanner/data_acquisition.py` 增加两个小函数：

```python
def _tickflow_target_date_is_available(target_date: str) -> bool:
    ...  # daily_ohlc_metadata 中 source=tickflow 且 latest_date=target_date

def _target_date_unavailable_error(code: str, target_date: str) -> str:
    metadata = db.get_ohlc_metadata(code) or {}
    remote_latest = metadata.get("latest_date") or "none"
    return (
        "TARGET_TRADE_DATE_UNAVAILABLE: "
        f"target={target_date} remote_latest={remote_latest}"
    )
```

`TickFlowDailyUpdateService.run()` 完成后，先保留 SDK 明确失败；若本次存在待更新股票且全库仍没有任何 TickFlow 目标日覆盖，则把所有未覆盖目标日的待更新股票加入 `failures`。不得覆盖更具体的 SDK 错误。

- [ ] **步骤 4：验证正常发布与停牌分支**

运行：

```powershell
python -m pytest tests/test_data_acquisition.py tests/test_daily_kline_cache_freshness.py -q
```

预期：全部 PASS；目标日已发布时的个股停牌行为保持兼容。

### 任务 3：实现只读 TickFlow 新鲜度探测服务

**文件：**
- 新增：`tests/test_tickflow_freshness.py`
- 新增：`tickflow_data/freshness.py`

- [ ] **步骤 1：编写失败测试**

使用假的批量客户端覆盖：

1. 股票调用 `fetch([symbol], count=5)`，从而保持 `forward_additive`。
2. 四个指数一次调用 `fetch_indexes(symbols, count=5)`，从而保持 `none`。
3. 远端日期等于目标日为 `FRESH`，早于目标日为 `STALE`，缺失或异常为 `FAILED`。
4. 股票请求失败时仍继续返回四个指数；指数批次失败时仍保留股票结果。
5. 本地日期分别读取 `daily_ohlc_metadata.latest_date` 与 `get_market_index_coverage().max_date`。
6. monkeypatch 所有行情写库函数为抛错，探测仍成功，证明无写库路径。

- [ ] **步骤 2：运行测试并确认红灯**

运行：

```powershell
python -m pytest tests/test_tickflow_freshness.py -q
```

预期：模块不存在，测试失败。

- [ ] **步骤 3：实现探测服务**

新增：

```python
def check_tickflow_freshness(
    stock_code: str,
    *,
    target_trade_date: str,
    client_factory=TickFlowBatchClient,
    count: int = 5,
) -> dict:
    ...
```

结果固定包含 `checked_at`、`target_trade_date`、`overall_status`、`stock` 和按 `MARKET_INDEX_SPECS` 顺序排列的 `indexes`。每项包含 `symbol`、`code`、`name`、`remote_latest_date`、`local_latest_date`、`row_count`、`elapsed_ms`、`status`、`error`。`overall_status` 的确定顺序为：全部失败=`FAILED`；部分失败=`PARTIAL_FAILURE`；无失败但任一落后=`STALE`；其余=`FRESH`。

- [ ] **步骤 4：运行服务测试**

运行：

```powershell
python -m pytest tests/test_tickflow_freshness.py -q
```

预期：全部 PASS。

### 任务 4：增加 FastAPI 探测端点

**文件：**
- 修改：`tests/test_kline_history_api.py`
- 修改：`server.py`

- [ ] **步骤 1：编写失败 API 测试**

覆盖：合法 `000655` 返回探测结构；空值、非数字、非六位代码返回 HTTP 400；服务异常返回结构化 HTTP 502；使用 monkeypatch 验证 API 调用 `check_tickflow_freshness()`，不调用全量刷新管理器。

- [ ] **步骤 2：运行测试并确认红灯**

运行：

```powershell
python -m pytest tests/test_kline_history_api.py -q
```

预期：新端点返回 404，新增测试失败。

- [ ] **步骤 3：实现 API**

新增 Pydantic 请求体：

```python
class TickFlowFreshnessRequest(BaseModel):
    stock_code: str
```

端点先执行 `_ensure_db_initialized_from_config()`，通过 `build_cache_freshness_context(now=_now())` 取得目标完整交易日，再用 `await asyncio.to_thread(...)` 调用同步探测。输入错误返回 `INVALID_STOCK_CODE`，SDK顶层异常返回 `TICKFLOW_FRESHNESS_CHECK_FAILED`。

- [ ] **步骤 4：运行 API 与服务测试**

运行：

```powershell
python -m pytest tests/test_tickflow_freshness.py tests/test_kline_history_api.py -q
```

预期：全部 PASS。

### 任务 5：增加前端 TickFlow 新鲜度面板

**文件：**
- 修改：`web/src/composables/useApi.js`
- 修改：`web/src/pages/__tests__/KlineHistory.test.js`
- 修改：`web/src/pages/KlineHistory.vue`

- [ ] **步骤 1：编写失败前端测试**

在 API mock 增加 `checkTickFlowFreshness`。输入 `000655` 并点击后，断言调用参数为 `{ stock_code: '000655' }`，页面展示目标日期和股票加四指数共五行，`FRESH/STALE/FAILED` 映射为“最新/落后/请求失败”。另测非法输入不会调用 API、请求期间按钮禁用、接口错误显示在面板且不覆盖个股K线查询错误。

- [ ] **步骤 2：运行测试并确认红灯**

运行：

```powershell
npm.cmd --prefix web test -- --run KlineHistory
```

预期：找不到探测按钮或 API 方法，新增测试失败。

- [ ] **步骤 3：实现 API 方法与页面状态**

`useApi.js` 新增：

```javascript
async function checkTickFlowFreshness(stockCode) {
  const res = await fetch(`${API_BASE}/tickflow/freshness-check`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ stock_code: stockCode }),
  })
  return res.json()
}
```

`KlineHistory.vue` 增加独立的 `probeCode`、`probeLoading`、`probeError`、`probeResult`，不得复用或修改分页查询的 `form.code`。表格列为：对象、远端最新日、本地最新日、目标日、状态、行数、耗时、错误。

- [ ] **步骤 4：运行前端专项测试与构建**

运行：

```powershell
npm.cmd --prefix web test -- --run KlineHistory
npm.cmd --prefix web run build
```

预期：测试和构建均成功。

### 任务 6：共享扫描回归与真实小流量验证

**文件：**
- 新增：`docs/reviews/2026-07-23-tickflow-freshness-probe-real-validation.md`

- [ ] **步骤 1：运行共享后端回归**

运行：

```powershell
python -m pytest tests/test_data_acquisition.py tests/test_daily_kline_cache_freshness.py tests/test_engine_fresh_fetch.py tests/test_strategy2_acceptance_fixes.py tests/test_strategy6_scanner.py -q
python -m compileall scanner tickflow_data strategy6 server.py -q
```

预期：全部 PASS，无编译错误。

- [ ] **步骤 2：运行前后端完整门禁**

运行：

```powershell
python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py --ignore=tests/test_yfinance_hist.py
npm.cmd --prefix web test -- --run
npm.cmd --prefix web run build
```

预期：全部 PASS。

- [ ] **步骤 3：执行真实 TickFlow 小流量探测**

启动后端或直接调用 `check_tickflow_freshness('000655', ...)`，仅请求一只股票和四个指数。记录实际目标日、每项远端最新日、本地最新日、状态、行数和耗时到验证报告；不得写行情表，不执行全市场重拉。

- [ ] **步骤 4：审核专家验收**

检查以下中高风险项：全市场零覆盖不会产生停牌；真实停牌分支没有被误伤；探测没有写库；SDK失败不会返回半截结果；前端探测状态不干扰全量重拉轮询和个股分页查询。发现问题后补失败测试并最小修复，直至无中高等级问题。

- [ ] **步骤 5：提交与推送**

只暂存本计划列出的文件，不暂存现有用户修改的 `config.yaml` 和既有报告目录：

```powershell
git add scanner/data_acquisition.py tickflow_data/freshness.py server.py web/src/composables/useApi.js web/src/pages/KlineHistory.vue tests/test_data_acquisition.py tests/test_tickflow_freshness.py tests/test_kline_history_api.py web/src/pages/__tests__/KlineHistory.test.js docs/superpowers/specs/2026-07-23-tickflow-freshness-probe-and-scan-safety-design.md docs/superpowers/plans/2026-07-23-tickflow-freshness-probe-and-scan-safety.md docs/reviews/2026-07-23-tickflow-freshness-probe-real-validation.md
git commit -m "fix: guard tickflow freshness during scans"
git push
```

预期：提交成功；推送失败时保留本地提交并报告原因。

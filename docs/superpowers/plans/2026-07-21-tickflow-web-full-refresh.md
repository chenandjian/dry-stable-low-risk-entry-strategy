# TickFlow前端全市场强制重拉实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 在K线数据页面提供TickFlow全市场1100根强制重拉按钮，并通过后台分块任务安全写库、展示真实进度和阻止并发扫描。

**架构：** `tickflow_data/service.py`负责100只级请求分块；新建`tickflow_data/web_task.py`封装任务状态、备份、报告和后台执行；`server.py`只暴露API并接入现有扫描/回测冲突判断；Vue页面轮询后端事实状态。

**技术栈：** Python 3.12、FastAPI、threading、TickFlow SDK、SQLite、Vue 3、Vitest、pytest。

---

## 文件结构

- 修改`tickflow_data/service.py`：按`request_chunk_size`切分完整和增量请求，避免全市场响应常驻内存。
- 修改`tickflow_data/models.py`：汇总跨分块结果所需的状态字段保持可序列化。
- 新建`tickflow_data/web_task.py`：Web后台任务状态机、互斥、数据库备份、分块执行、进度文件和报告。
- 修改`server.py`：创建任务管理器，增加启动/状态API，并把TickFlow运行态加入扫描和回测冲突判断。
- 修改`web/src/composables/useApi.js`：增加TickFlow启动与状态请求。
- 修改`web/src/pages/KlineHistory.vue`：增加按钮、确认、参数说明、状态卡和轮询。
- 新建`tests/test_tickflow_web_task.py`：任务管理器测试。
- 修改`tests/test_tickflow_service.py`、`tests/test_kline_history_api.py`：分块、API和互斥测试。
- 修改`web/src/pages/__tests__/KlineHistory.test.js`：按钮与轮询测试。

### 任务1：TickFlow服务请求分块

**文件：**
- 修改：`tickflow_data/service.py`
- 修改：`tests/test_tickflow_service.py`

- [ ] **步骤1：编写失败测试**

新增测试，构造5只股票并设置`request_chunk_size=2`，断言客户端依次收到2、2、1只股票，同时五只结果全部写入且顺序保持输入顺序：

```python
service = TickFlowDailyUpdateService(
    client,
    history_days=1100,
    request_chunk_size=2,
)
result = service.run(stocks, dry_run=False, mode="backfill")
assert [len(symbols) for symbols, _ in client.calls] == [2, 2, 1]
assert [item.code for item in result.results] == [stock["code"] for stock in stocks]
```

- [ ] **步骤2：运行红灯**

运行：`python -m pytest tests/test_tickflow_service.py -q`

预期：FAIL，`TickFlowDailyUpdateService`不接受`request_chunk_size`或只发起一次请求。

- [ ] **步骤3：实现最小分块**

增加正整数参数并让`_process_full_group()`、`_process_incremental_group()`按块调用现有处理逻辑。复权变化完整重拉队列也必须分块，不能绕过限制：

```python
def _chunks(values, size):
    for offset in range(0, len(values), size):
        yield values[offset:offset + size]
```

分块只改变请求内存边界，不改变单股校验、原子替换、失败保留旧数据和结果顺序。

- [ ] **步骤4：运行绿灯**

运行：`python -m pytest tests/test_tickflow_service.py tests/test_tickflow_client.py -q`

- [ ] **步骤5：提交**

```bash
git add tickflow_data/service.py tests/test_tickflow_service.py
git commit -m "feat: chunk TickFlow full-market requests"
```

### 任务2：Web后台任务管理器

**文件：**
- 新建：`tickflow_data/web_task.py`
- 新建：`tests/test_tickflow_web_task.py`
- 修改：`tickflow_data/cli.py`

- [ ] **步骤1：编写失败测试**

使用临时SQLite、假客户端工厂和同步线程启动器覆盖：

1. 固定参数为1100/100/100/5/`forward_additive`。
2. 启动前创建数据库备份。
3. 状态从`running`进入`completed`。
4. 单股失败进入`completed_with_errors`且保留失败摘要。
5. 顶层异常进入`failed`并释放运行锁。
6. 重复`start()`抛出`TickFlowTaskConflict`。

期望接口：

```python
manager = TickFlowFullRefreshManager(client_factory=fake_factory)
snapshot = manager.start(database_path, stocks)
assert snapshot["status"] == "running"
assert manager.status()["parameters"]["history_days"] == 1100
```

- [ ] **步骤2：运行红灯**

运行：`python -m pytest tests/test_tickflow_web_task.py -q`

预期：FAIL，模块不存在。

- [ ] **步骤3：实现状态机**

`TickFlowFullRefreshManager`持有线程锁和最近任务快照。工作线程必须：

```python
try:
    backup_path = backup_database(database_path, backup_dir)
    result = service.run(stocks, dry_run=False, mode="backfill", run_id=task_id,
                         on_success=record_success)
    status = "completed_with_errors" if failures else "completed"
except Exception as exc:
    status = "failed"
finally:
    running = False
```

将`tickflow_data/cli.py`中的数据库备份和Markdown报告函数改成无下划线的可复用公共函数，不导入`server.py`。状态快照返回副本，禁止前端修改内部字典。

- [ ] **步骤4：运行绿灯**

运行：`python -m pytest tests/test_tickflow_web_task.py tests/test_tickflow_cli.py -q`

- [ ] **步骤5：提交**

```bash
git add tickflow_data/web_task.py tickflow_data/cli.py tests/test_tickflow_web_task.py tests/test_tickflow_cli.py
git commit -m "feat: add TickFlow web refresh task manager"
```

### 任务3：FastAPI接口和全局互斥

**文件：**
- 修改：`server.py`
- 修改：`tests/test_kline_history_api.py`

- [ ] **步骤1：编写失败测试**

测试以下行为：

```python
response = client.post("/api/tickflow/full-refresh")
assert response.status_code == 202
assert response.json()["parameters"]["history_days"] == 1100

status = client.get("/api/tickflow/full-refresh/status")
assert status.status_code == 200
```

另测重复TickFlow、已有扫描、已有回测返回409；TickFlow运行期间现有策略扫描和回测启动冲突函数返回409；空股票池返回409且不启动线程。

- [ ] **步骤2：运行红灯**

运行：`python -m pytest tests/test_kline_history_api.py -q`

预期：FAIL，接口返回404或冲突规则未生效。

- [ ] **步骤3：实现API**

创建模块级`_tickflow_full_refresh = TickFlowFullRefreshManager()`，新增：

```python
@app.post("/api/tickflow/full-refresh", status_code=202)
async def start_tickflow_full_refresh(): ...

@app.get("/api/tickflow/full-refresh/status")
async def get_tickflow_full_refresh_status(): ...
```

启动接口通过`_ensure_db_initialized_from_config()`获取数据库，读取`db.get_stock_pool()`快照。`_scan_conflict_response()`和`_backtest_conflict_response()`优先检查TickFlow运行态；回测恢复/失败重试入口也必须调用统一冲突函数，不能只检查`_backtest_running`。

- [ ] **步骤4：运行绿灯**

运行：`python -m pytest tests/test_kline_history_api.py tests/test_scan_start_reliability.py -q`

- [ ] **步骤5：提交**

```bash
git add server.py tests/test_kline_history_api.py
git commit -m "feat: expose TickFlow full refresh API"
```

### 任务4：K线数据页按钮与轮询

**文件：**
- 修改：`web/src/composables/useApi.js`
- 修改：`web/src/pages/KlineHistory.vue`
- 修改：`web/src/pages/__tests__/KlineHistory.test.js`

- [ ] **步骤1：编写失败测试**

扩展API mock并覆盖：

```javascript
expect(wrapper.text()).toContain('TickFlow全市场重新拉取')
expect(wrapper.text()).toContain('1100根')
expect(wrapper.text()).toContain('每批100只')
```

模拟`window.confirm`为`true`，点击按钮后断言`startTickFlowFullRefresh()`调用；确认取消时不得调用。模拟状态依次`running -> completed_with_errors`，断言显示总数、成功、失败、报告路径，并在完成后调用`getKlineHealth()`。

- [ ] **步骤2：运行红灯**

运行：`npm.cmd --prefix web test -- --run KlineHistory`

预期：FAIL，按钮或API方法不存在。

- [ ] **步骤3：实现最小前端**

`useApi.js`新增：

```javascript
async function startTickFlowFullRefresh() { ... }
async function getTickFlowFullRefreshStatus() { ... }
```

页面挂载时读取状态；运行中每2秒轮询；终态停止定时器并刷新健康状态；组件卸载时清理定时器。按钮运行中禁用，启动失败显示后端`message`。

- [ ] **步骤4：运行绿灯与构建**

```bash
npm.cmd --prefix web test -- --run KlineHistory
npm.cmd --prefix web run build
```

- [ ] **步骤5：提交**

```bash
git add web/src/composables/useApi.js web/src/pages/KlineHistory.vue web/src/pages/__tests__/KlineHistory.test.js
git commit -m "feat: add TickFlow full refresh button"
```

### 任务5：双角色审核与完整门禁

- [ ] **步骤1：审核业务和数据正确性**

检查：全市场是否真正强制`backfill`；每块是否最多100只；失败股票是否不覆盖旧数据；备份是否早于首个写入；任务异常是否释放锁；前端是否以状态接口为事实来源。

- [ ] **步骤2：审核并发边界**

检查所有策略扫描启动入口、策略1/2回测新建/恢复/失败重试入口是否在TickFlow运行时返回409。任何遗漏按中等级问题修复并补失败测试。

- [ ] **步骤3：运行专项测试**

```bash
python -m pytest tests/test_tickflow_*.py tests/test_kline_history_api.py -q
npm.cmd --prefix web test -- --run KlineHistory
```

- [ ] **步骤4：运行完整门禁**

```bash
python -m pytest tests -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py --ignore=tests/test_yfinance_hist.py
python -m compileall scanner tickflow_data scripts strategy6 server.py -q
npm.cmd --prefix web test -- --run
npm.cmd --prefix web run build
```

- [ ] **步骤5：最终提交与推送**

只暂存本计划列出的TickFlow代码、测试和文档，不暂存用户已有`config.yaml`和研究报告改动：

```bash
git add docs/superpowers/plans/2026-07-21-tickflow-web-full-refresh.md
git commit -m "docs: finalize TickFlow web refresh implementation"
git push origin codex/strategy6-strong-vcp-tail
```

# TickFlow独立批量日线模块实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 建立不依赖现有三源链的TickFlow批量日线模块，支持差值前复权完整回填、增量更新、复权变化重拉、审计报告和真实验证。

**架构：** `tickflow_data/`封装客户端、标的映射、规范化、批量编排和CLI；只在持久化边界复用`scanner.db`。更新器先把股票分为完整回填和增量组，批量获取后逐股校验，只有完整有效结果才原子写库。

**技术栈：** Python 3.12、TickFlow SDK 0.1.24+、pandas、SQLite、pytest。

---

## 文件结构

- 创建`tickflow_data/models.py`：任务和逐股结果模型。
- 创建`tickflow_data/symbols.py`：A股代码与TickFlow symbol双向转换。
- 创建`tickflow_data/normalize.py`：DataFrame到规范OHLC及数据校验。
- 创建`tickflow_data/client.py`：TickFlow客户端生命周期和固定参数批量请求。
- 创建`tickflow_data/service.py`：完整/增量分组、复权变化检测、原子写入。
- 创建`tickflow_data/cli.py`：独立命令、备份、进度和报告。
- 修改`requirements.txt`：声明TickFlow依赖。
- 创建`tests/test_tickflow_symbols.py`、`tests/test_tickflow_normalize.py`、`tests/test_tickflow_service.py`、`tests/test_tickflow_cli.py`。
- 创建`docs/reviews/2026-07-21-tickflow-real-data-validation.md`：真实六股报告。

### 任务1：标的映射和数据规范化

- [ ] **步骤1：编写失败测试**

测试`.SH/.SZ/.BJ`映射、未知代码拒绝、`volume*100`、`amount->turnover`、日期排序、重复日期拒绝和非法OHLC拒绝。

- [ ] **步骤2：验证红灯**

运行：`python -m pytest tests/test_tickflow_symbols.py tests/test_tickflow_normalize.py -q`

预期：模块不存在或断言失败。

- [ ] **步骤3：实现最小模块**

实现接口：

```python
def to_tickflow_symbol(code: str, market: str | None = None) -> str: ...
def from_tickflow_symbol(symbol: str) -> str: ...
def normalize_frame(frame) -> list[dict]: ...
```

规范行固定为`date/open/high/low/close/volume/turnover`，任何非法行使整只股票失败。

- [ ] **步骤4：验证绿灯**

运行：`python -m pytest tests/test_tickflow_symbols.py tests/test_tickflow_normalize.py -q`

- [ ] **步骤5：提交**

```bash
git add tickflow_data/models.py tickflow_data/symbols.py tickflow_data/normalize.py tests/test_tickflow_symbols.py tests/test_tickflow_normalize.py
git commit -m "feat: add TickFlow data normalization"
```

### 任务2：独立批量客户端

- [ ] **步骤1：编写失败测试**

使用假SDK验证批量调用始终包含：

```python
period="1d"
adjust="forward_additive"
as_dataframe=True
batch_size=100
max_workers=5
```

同时验证返回缺失symbol会保留为失败，不抛弃成功symbol。

- [ ] **步骤2：验证红灯**

运行：`python -m pytest tests/test_tickflow_client.py -q`

- [ ] **步骤3：实现最小客户端**

创建`TickFlowBatchClient`，构造时允许注入SDK对象；生产路径延迟导入`tickflow.TickFlow`，一次任务只创建一个上下文客户端。

- [ ] **步骤4：验证绿灯并声明依赖**

运行：`python -m pytest tests/test_tickflow_client.py -q`

修改`requirements.txt`加入`tickflow[all]>=0.1.24`。

- [ ] **步骤5：提交**

```bash
git add tickflow_data/client.py tests/test_tickflow_client.py requirements.txt
git commit -m "feat: add independent TickFlow batch client"
```

### 任务3：完整回填和增量更新服务

- [ ] **步骤1：编写失败测试**

使用临时SQLite覆盖：

1. 无本地数据请求1100根并整段写入。
2. 非TickFlow元数据强制完整回填，不与旧复权数据合并。
3. TickFlow元数据只请求10根，按日期覆盖并保留历史。
4. 重叠首日OHLC变化时升级为完整重拉。
5. 缺失symbol和非法数据不修改原数据。
6. dry-run不写库。

- [ ] **步骤2：验证红灯**

运行：`python -m pytest tests/test_tickflow_service.py -q`

- [ ] **步骤3：实现服务**

实现：

```python
class TickFlowDailyUpdateService:
    def run(self, stocks: list[dict], *, dry_run: bool) -> BatchUpdateResult: ...
```

服务内部使用独立的日期合并函数，不导入`daily_data_service`；写入仅调用`db.replace_ohlc_with_metadata()`。

- [ ] **步骤4：验证绿灯**

运行：`python -m pytest tests/test_tickflow_service.py -q`

- [ ] **步骤5：提交**

```bash
git add tickflow_data/service.py tests/test_tickflow_service.py
git commit -m "feat: add TickFlow daily update service"
```

### 任务4：CLI、备份、断点和报告

- [ ] **步骤1：编写失败测试**

验证`update/backfill`参数、默认安全模式、`--execute`备份、成功项断点恢复、失败项重试和报告汇总。

- [ ] **步骤2：验证红灯**

运行：`python -m pytest tests/test_tickflow_cli.py -q`

- [ ] **步骤3：实现CLI**

CLI从`stock_pool`读取股票；`--codes`只缩小范围。API Key只读取环境变量，禁止命令行传入和日志输出。

- [ ] **步骤4：验证绿灯**

运行：`python -m pytest tests/test_tickflow_cli.py -q`

- [ ] **步骤5：提交**

```bash
git add tickflow_data/cli.py tests/test_tickflow_cli.py
git commit -m "feat: add TickFlow batch update CLI"
```

### 任务5：真实批量验证和闭环审核

- [ ] **步骤1：真实dry-run**

运行六股真实批量请求，禁止写生产数据库：

```bash
python -m tickflow_data.cli backfill --dry-run --codes 002396 000001 600519 300750 688981 601318 --history-days 800
```

- [ ] **步骤2：临时数据库写入验证**

在临时数据库执行首次回填和第二次增量更新，验证元数据、日期覆盖、幂等和原子替换。

- [ ] **步骤3：形成报告**

报告列出每只股票日期范围、OHLC偏差、成交量/成交额偏差、批量耗时、失败项和复权口径。

- [ ] **步骤4：全量门禁**

```bash
python -m pytest tests -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py --ignore=tests/test_yfinance_hist.py
python -m compileall scanner tickflow_data scripts strategy6 server.py -q
```

- [ ] **步骤5：审核与修复**

审核独立边界、复权一致性、部分失败、数据覆盖、并发、密钥泄漏和旧策略回归；修复全部中高等级问题并重新运行门禁。

- [ ] **步骤6：最终提交和推送**

只暂存TickFlow相关代码、测试、规格、计划和报告；不暂存用户已有配置及研究报告改动。

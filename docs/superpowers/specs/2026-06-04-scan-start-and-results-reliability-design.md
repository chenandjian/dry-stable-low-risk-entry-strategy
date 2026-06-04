# 优化开始扫描逻辑与修复扫描结果异常设计

日期：2026-06-04

## 背景

当前扫描流程存在几个可靠性问题：

- `scanner/engine.py` 的行情获取逻辑会优先使用“近 2 天缓存”，导致点击“开始扫描”不一定拉取最新数据。
- `server.py` 和 `scanner/engine.py` 都可能生成 `task_id`，任务、股票清单、候选写入不完全一致。
- 当前只有任务级 `scanned/skipped/candidates_count`，缺少每只股票的状态、失败原因、数据源尝试记录。
- `candidates` 没有任务内股票唯一约束，实时发现、最终批量保存、失败重拉可能导致重复候选。
- `scanner/db.py` 已引用 `task_stocks`，但初始化 SQL 未创建该表，续扫和全量覆盖追踪不可靠。

本设计目标是让“开始扫描”默认拉新数据、候选不重复、全量覆盖可证明、失败可追踪，并支持对失败股票单独重新拉取。

## 目标

1. 每次点击“开始扫描”默认重新拉取股票日线数据。
2. 不允许主备实时数据源都失败时使用旧缓存参与本次策略扫描。
3. 每个任务内候选股票唯一，不允许重复候选。
4. 全量扫描必须基于本次确定的完整股票池，并能证明每只股票进入过扫描流程。
5. 每只股票都有可追踪状态：是否扫描、是否跳过、是否失败、失败原因是什么。
6. 拉取失败股票单独列出，并支持对失败列表重新拉取和重扫。
7. 全局同一时间只允许一个正在扫描的任务，包括全量扫描、失败重拉、定时扫描和恢复扫描。

## 非目标

- 不重写杯柄、VCP、干稳低吸等策略算法。
- 不在本轮强制要求所有股票的最新交易日完全一致；先记录 `kline_latest_date` 和任务级 `latest_trade_date`，后续可按需要增加严格阈值。
- 不要求实时 quote 成功才允许策略扫描。日线 K 线是策略扫描的必要条件，实时 quote 是补充字段。
- 不设计多轮 retry batch 审计模型；失败重拉更新原任务状态和候选结果。

## 已确认需求决策

- 行情源都失败时采用严格策略：不使用旧缓存扫描，股票标记为 `failed`。
- 股票池开始扫描时强制刷新 AKShare；AKShare 失败才回退数据库股票池缓存，并记录来源和错误。
- 每只股票状态写入数据库，并在前端任务详情/失败列表展示。
- 失败股票重拉只处理原任务的 `failed` 股票，并重新跑完整扫描逻辑。
- 首次全量扫描重试策略：主数据源最多 2 次 + 备用数据源最多 2 次，带短暂退避。
- 失败列表重拉策略：主数据源最多 3 次 + 备用数据源最多 3 次，退避稍长。
- 日线 K 线必须最新拉取；实时行情字段单独补充，失败记录 `quote_status=failed`，不阻塞日线策略扫描。
- 全局只允许一个正在扫描的任务。

## 总体架构

保留现有模块边界：

- `server.py`：扫描入口、API、后台线程管理、全局互斥检查。
- `scanner/engine.py`：双线程扫描调度、个股扫描流程、候选判断。
- `scanner/db.py`：SQLite 表结构、任务、个股状态、候选、OHLC 持久化。
- `scanner/stock_pool.py`：股票池刷新和缓存回退。
- `scanner/sina_source.py` / `scanner/tencent_source.py`：日线 K 线数据源。
- `web/src/pages/ScannerConsole.vue`：扫描控制台。

新增或增强以下边界：

1. **扫描任务层**：`server.py` 创建唯一 `task_id`，并显式传给 `scan_all()`。`engine.py` 不再为同一次扫描另造任务 ID。
2. **股票明细层**：每次任务将完整股票池写入 `task_stocks`。扫描过程中逐只更新状态和原因。
3. **行情获取层**：强制实时拉取日线 K 线；缓存只用于合并历史，不用于失败兜底扫描。
4. **失败重拉层**：新增只处理 `failed` 股票的重拉/重扫入口。
5. **候选去重层**：内存、数据库、前端三层去重。

## 数据库设计

### `scan_tasks` 增强

保留现有字段，新增：

- `success_count INTEGER DEFAULT 0`：完成策略扫描的股票数。
- `failed_count INTEGER DEFAULT 0`：失败股票数。
- `stock_pool_source TEXT`：`akshare` 或 `cached`。
- `stock_pool_error TEXT`：AKShare 失败时的错误摘要。
- `retry_mode TEXT`：`full` 或 `failed_only`。
- `data_fresh_policy TEXT`：固定记录为 `force_refresh`。
- `latest_trade_date TEXT`：本次任务扫描到的最大 K 线日期。

`scan_tasks.status` 使用：

- `running`
- `completed`
- `failed`
- `cancelled`（预留）

### `task_stocks` 正式创建

当前代码已有 `save_task_stocks()` / `get_pending_stocks()`，但初始化缺表。设计中正式创建：

```sql
CREATE TABLE IF NOT EXISTS task_stocks (
  task_id TEXT NOT NULL,
  idx INTEGER NOT NULL,
  code TEXT NOT NULL,
  name TEXT NOT NULL,
  market TEXT,
  status TEXT DEFAULT 'pending',
  status_reason TEXT,
  error_detail TEXT,
  primary_source TEXT,
  fallback_source TEXT,
  primary_attempts INTEGER DEFAULT 0,
  fallback_attempts INTEGER DEFAULT 0,
  primary_error TEXT,
  fallback_error TEXT,
  kline_latest_date TEXT,
  quote_status TEXT DEFAULT 'not_requested',
  quote_error TEXT,
  started_at TEXT,
  finished_at TEXT,
  updated_at TEXT DEFAULT (datetime('now')),
  PRIMARY KEY (task_id, code),
  FOREIGN KEY (task_id) REFERENCES scan_tasks(id)
);
```

建议索引：

```sql
CREATE INDEX IF NOT EXISTS idx_task_stocks_task_status ON task_stocks(task_id, status);
CREATE INDEX IF NOT EXISTS idx_task_stocks_task_idx ON task_stocks(task_id, idx);
```

状态语义：

- `pending`：已进入任务清单，尚未处理。
- `fetching`：正在拉取数据。
- `scanned`：完成扫描但不是候选。
- `skipped`：有数据，因规则跳过，如上市天数不足、流动性不足。
- `failed`：没有完成可信扫描，如主备数据源都失败或策略异常。
- `candidate`：完成扫描并进入候选。

`skipped` 和 `failed` 必须区分：前者是正常排除，后者需要进入失败列表并允许重拉。

### `candidates` 去重

增加任务内唯一约束：

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_candidates_task_code ON candidates(task_id, code);
```

候选保存语义改为按 `(task_id, code)` upsert。实时发现、最终批量保存、失败重拉再次发现同一股票时，更新同一行，不追加重复行。

## 开始扫描流程

1. 前端调用 `GET /api/scan/start`。
2. 后端执行全局扫描互斥检查：
   - `_running["running"]`
   - 数据库中是否存在 `scan_tasks.status = 'running'`
3. 如果已有扫描运行，返回 `409`，不创建新任务。
4. 创建唯一 `task_id` 和 `scan_tasks` 记录。
5. 强制刷新 AKShare 股票池。
6. AKShare 成功：保存股票池缓存，记录 `stock_pool_source=akshare`。
7. AKShare 失败：回退数据库股票池缓存，记录 `stock_pool_source=cached` 和 `stock_pool_error`。
8. 应用现有市场过滤规则，得到本次完整股票池。
9. 将完整股票池写入 `task_stocks`，并更新 `scan_tasks.total_stocks`。
10. 启动后台扫描线程，调用 `scan_all(config, task_id=task_id, stocks=stocks, retry_policy=normal)`。

这样 `total_stocks` 就是本次实际扫描的股票清单数量，任务详情也能证明每只股票是否被处理。

## 个股行情获取规则

每只股票扫描时：

1. `task_stocks.status = fetching`。
2. 选择当前线程持有的主数据源。
3. 主数据源最多尝试 2 次，带短暂退避。
4. 主源失败后，备用数据源最多尝试 2 次，带短暂退避。
5. 任一数据源返回有效日线 K 线：
   - 读取历史缓存。
   - 按日期合并历史缓存和新数据。
   - 保存到 `daily_ohlc`。
   - 本次扫描使用“新拉到的数据 + 历史补足后的合并数据”。
6. 主备都失败：
   - 不返回旧缓存。
   - `task_stocks.status = failed`。
   - `status_reason = 数据源全部失败，未使用旧缓存扫描`。
   - 记录主备源尝试次数和错误摘要。
   - 该股票进入失败列表。

缓存只允许用于：

- 补足历史 K 线长度。
- 股票详情页历史展示。

缓存不允许用于：

- 数据源失败后继续策略扫描。
- 生成候选。
- 冒充最新数据。

## 实时行情 quote 补充

日线 K 线成功后，尝试获取实时 quote，补充：

- 当前价格
- 涨跌幅
- 成交额
- 换手率
- 量比

规则：

- quote 成功：记录 quote 字段和 `quote_status=ok`。
- quote 失败：记录 `quote_status=failed` 和 `quote_error`。
- quote 失败不阻塞策略扫描。
- 如果候选页展示实时字段，应能看出 quote 是否成功；quote 失败时只展示日线推导字段或标注实时字段不可用。

## 个股扫描状态更新

日线数据成功后执行现有扫描逻辑：

1. 上市天数过滤。
2. 流动性过滤。
3. 杯柄检测。
4. VCP/干稳低吸分析。
5. 候选判断。

状态落点：

- 数据长度不足：`skipped`，原因如 `上市天数不足`。
- 流动性不足：`skipped`，原因如 `流动性过滤未通过`。
- 策略正常完成但不是候选：`scanned`。
- 成为候选：`candidate`，并 upsert 到 `candidates`。
- 策略异常：`failed`，原因 `扫描异常`，记录异常摘要。

任务级统计从 `task_stocks` 状态汇总，避免多线程计数漂移。

## 失败股票重拉/重扫

新增 API：

```http
POST /api/scan/tasks/{task_id}/retry-failed
```

流程：

1. 执行全局扫描互斥检查。
2. 查询原任务下 `status='failed'` 的股票。
3. 如果失败列表为空，返回清晰结果：`retry_count=0`。
4. 将失败股票状态改回 `pending`。
5. 设置任务运行状态为 `running`，`retry_mode=failed_only`。
6. 使用更强重试策略：主数据源最多 3 次 + 备用数据源最多 3 次，退避稍长。
7. 对成功拉到日线数据的股票重新执行完整策略扫描。
8. 更新原任务的股票状态、候选、统计数据。
9. 完成后任务回到 `completed`；若重拉线程异常，任务标记 `failed` 并保存错误。

失败重拉不是创建新的全量任务，而是修复原任务中的失败项。全局互斥规则下，重拉期间不能开始另一个全量扫描。

## 全局扫描互斥

所有扫描入口都必须执行相同互斥检查：

- `GET /api/scan/start`
- `POST /api/scan/tasks/{task_id}/retry-failed`
- 定时任务触发扫描
- 服务启动自动恢复扫描

只要内存或数据库显示有运行中任务，就拒绝新扫描：

```json
{
  "error": "Scan already running",
  "running_task_id": "20260604-153000"
}
```

服务启动时可以继续执行现有“标记死亡任务失败/恢复中断任务”逻辑，但用户点击开始扫描时不能随意覆盖正在运行的任务。

## API 设计

### 开始扫描

```http
GET /api/scan/start
```

成功返回：

```json
{
  "task_id": "20260604-153000",
  "status": "started",
  "total_stocks": 5128,
  "stock_pool_source": "akshare"
}
```

已有任务运行时返回 `409`：

```json
{
  "error": "Scan already running",
  "running_task_id": "20260604-153000"
}
```

### 查询扫描状态

```http
GET /api/scan/status
```

增强返回：

```json
{
  "running": true,
  "task_id": "20260604-153000",
  "mode": "full",
  "stats": {
    "total_stocks": 5128,
    "processed": 120,
    "scanned": 90,
    "skipped": 20,
    "failed": 10,
    "candidates_found": 3,
    "current_code": "600036",
    "current_name": "招商银行",
    "stock_pool_source": "akshare",
    "latest_trade_date": "2026-06-04"
  }
}
```

### 查询任务股票明细

```http
GET /api/scan/tasks/{task_id}/stocks?status=failed&page=1&page_size=100
```

`status` 可选：

- `failed`
- `skipped`
- `candidate`
- `scanned`
- 不传则返回全部。

返回每只股票的状态、原因、数据源尝试信息、最新 K 线日期和 quote 状态。

### 查询失败列表

可以用 stocks 接口实现：

```http
GET /api/scan/tasks/{task_id}/stocks?status=failed
```

也可以增加语义化别名：

```http
GET /api/scan/tasks/{task_id}/failures
```

### 重新拉取失败股票

```http
POST /api/scan/tasks/{task_id}/retry-failed
```

成功启动返回：

```json
{
  "task_id": "20260604-153000",
  "status": "retry_started",
  "retry_count": 37
}
```

## 前端设计

### 扫描控制台增强

在现有 `ScannerConsole.vue` 中增加展示：

- 当前任务 ID。
- 股票池来源：AKShare / 本地缓存。
- 已处理 / 总数。
- 成功 / 跳过 / 失败 / 候选。
- 最新交易日。
- 运行中任务冲突时显示 `running_task_id`。

当前页面默认 `total=5128` 应改为以后端返回为准；未开始扫描时显示 `--` 或最近任务实际值。

### 失败列表面板

新增失败股票区域：

- 显示失败总数。
- 展示最近失败的若干只股票。
- 可点击查看全部失败股票。
- 提供“重新拉取失败股票”按钮。
- 扫描或重拉运行中时按钮禁用。

失败项展示：

- 代码、名称、市场。
- 失败原因。
- 主源/备源尝试次数。
- 主源/备源错误摘要。
- 最新 K 线日期（如果有）。
- quote 状态。

### 任务详情页或弹层

建议新增任务详情视图或弹层：

- 状态筛选：全部 / 候选 / 成功 / 跳过 / 失败。
- 分页加载任务股票明细。
- 对失败状态提供批量重拉入口。

### 前端候选去重

前端仍需按 `code` 归并候选：

- 实时发现使用 `Map` 或按 `code` 覆盖。
- `loadResults()` 对后端候选列表再按 `code` 去重。
- 重拉后同一股票候选更新，而不是追加。

## 候选去重策略

三层去重：

1. **内存层**：`scan_all()` 内使用 `dict[code] = (stock, result)`，不使用简单 append 作为唯一来源。
2. **数据库层**：`candidates(task_id, code)` 唯一索引；保存时 upsert。
3. **前端层**：按 `code` 归并候选。

数据库层是最终保障。

## 错误处理

### 数据源失败

每只股票记录：

- `primary_source`
- `primary_attempts`
- `primary_error`
- `fallback_source`
- `fallback_attempts`
- `fallback_error`
- `status_reason`

主源失败、备用源成功时，股票继续扫描，但保留主源错误摘要。

### 旧缓存

主备数据源都失败时，即使数据库存在旧 OHLC，也不能参与本次扫描。该股票标记为 `failed`。

### Quote 失败

quote 失败不影响策略扫描，但记录 `quote_status=failed` 和 `quote_error`。

### 策略异常

策略计算异常时，只标记当前股票 `failed`，全市场扫描继续。

### 任务异常

后台扫描线程异常时：

- `_running["running"] = False`
- `scan_tasks.status = failed`
- `scan_tasks.error` 保存异常摘要
- 已完成的 `task_stocks` 状态保留，未处理项仍可追踪

## 测试计划

### 行情获取单元测试

- 缓存新鲜时仍会调用实时数据源。
- 主源成功时保存并返回最新数据。
- 主源失败、备用源成功时继续扫描，并记录主源失败。
- 主备都失败时不返回旧缓存。
- 全量扫描和失败重拉使用不同重试次数。

### 任务股票状态测试

- 开始扫描写入完整 `task_stocks`。
- 成功扫描状态为 `scanned`。
- 成为候选状态为 `candidate`。
- 上市天数不足、流动性不足状态为 `skipped`。
- 数据源失败状态为 `failed`。
- 失败原因和尝试次数被保存。

### 候选去重测试

- 同一 `task_id + code` 多次保存只保留一条。
- 实时发现保存后，最终批量保存不会重复。
- 失败重拉后同一股票成为候选时更新原候选。

### API 测试

- `/api/scan/start` 运行时再次调用返回 `409`。
- `/api/scan/tasks/{task_id}/stocks?status=failed` 返回失败列表。
- `/api/scan/tasks/{task_id}/retry-failed` 只重拉失败股票。
- 无失败股票时返回清晰结果。
- 失败重拉运行时再次开始全量扫描返回 `409`。

### 前端手动验证

- 点击开始扫描后显示真实总数，而非默认 5128。
- 扫描中显示成功/跳过/失败/候选。
- 候选列表无重复股票。
- 失败列表可查看原因。
- 点击重拉失败股票后，失败数减少或失败原因更新。
- 有扫描运行时，开始扫描和重拉按钮禁用或提示 409。

## 兼容与迁移

- 使用 `CREATE TABLE IF NOT EXISTS` 创建 `task_stocks`。
- 使用列检查方式给 `scan_tasks` 增加新字段。
- 使用唯一索引实现候选去重；若旧库已有重复候选，迁移前需要先按 `(task_id, code)` 保留最新或最高分记录，再创建唯一索引。
- 保留现有 API 返回字段，新增字段向后兼容。

## 验收标准

1. 点击开始扫描时，个股日线 K 线获取不再缓存优先。
2. 主备行情源都失败时，该股票进入失败列表，不使用旧缓存生成扫描结果。
3. 每个扫描任务有完整 `task_stocks` 清单，数量等于本次过滤后的股票池数量。
4. 任一任务内同一股票最多一条候选记录。
5. 前端能看到成功、跳过、失败、候选统计。
6. 前端能查看失败股票列表和失败原因。
7. 失败股票可以单独重拉，并重新执行完整扫描逻辑。
8. 任意时刻全局最多一个扫描过程处于 running 状态。
9. 自动测试覆盖行情获取、任务状态、候选去重和关键 API。

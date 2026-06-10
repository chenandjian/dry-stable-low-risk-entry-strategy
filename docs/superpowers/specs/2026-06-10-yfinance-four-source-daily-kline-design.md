# 开发方案文档：yfinance 四源并发日线数据获取

Date: 2026-06-10

## 1. 需求背景

当前系统的全市场扫描采用“多个数据源并行处理不同股票”的模式。每个数据源拥有独立互斥锁，同一时间最多处理一只股票；多个扫描工作线程可以同时使用不同数据源拉取不同股票。

现有可配置日线数据源主要包括：

- 百度
- 新浪
- 腾讯

实际运行中，百度和新浪经常无法返回有效数据，腾讯成为主要可用来源，造成：

- 腾讯承担绝大部分拉取压力。
- 数据源并发能力没有充分利用。
- 腾讯异常或受限时，全市场扫描成功率下降。
- 百度和新浪偶尔恢复时仍应继续参与，不能被静态禁用。

yfinance 已验证可以免费获取 A 股日线数据，因此需要将其作为第四个正式数据源接入现有并发获取模型。目标不是让每只股票同时请求四个数据源，而是让四个可用数据源同时处理不同股票；当某个数据源失败时，当前股票继续沿现有回退链尝试其他数据源。

### 当前问题

- 默认数据源管理器只有百度、新浪、腾讯三把独立锁。
- 默认工作线程数量不足以保证四个数据源同时工作。
- yfinance 尚未提供与现有数据源一致的标准接口。
- yfinance 原始 DataFrame 字段、日期索引和成交额口径与项目数据库格式不同。
- yfinance 可能触发限流，外部网络测试不能作为常规 CI 必过测试。

### 用户痛点

- 百度、新浪不可用时只能依赖腾讯。
- 希望 yfinance 实际参与全市场数据拉取，而不是只作为永远轮不到的链尾兜底。
- 希望四个源都可用时，四个源能并行处理不同股票。
- 希望无论数据来自哪个源，入库格式完全一致。

### 业务目标

- 增加第四个可用日线数据源，降低腾讯单源压力。
- 保持现有多源互斥锁、失败回退和 fresh-first 行为。
- 保证 yfinance 数据可直接进入现有 SQLite、流动性过滤和策略计算流程。
- 保证偶尔恢复的百度和新浪继续正常参与。

### 预期效果

当四个数据源均可用、待扫描股票不少于四只且工作线程不少于四个时：

```text
百度线程     → 股票 A
新浪线程     → 股票 B
腾讯线程     → 股票 C
yfinance线程 → 股票 D
```

任一源失败时，该股票继续尝试其他可用源，不中断整体扫描。

---

## 2. 需求目标

### 2.1 必须实现

- 新增 `scanner/yfinance_source.py`。
- 提供 `fetch_yfinance_daily(code: str, days: int = 250) -> list[dict] | None`。
- 将 yfinance 注册到日线数据源映射和默认数据源列表。
- `DataSourceManager` 增加 yfinance 独立互斥锁。
- 默认工作线程数量调整为 `4`。
- 默认配置加入 `yfinance` 数据源。
- 四个可用数据源能够同时处理不同股票。
- 保持每只股票由一个成功数据源提供本次 fresh 数据。
- 某源失败、空数据、异常或忙碌时，当前股票继续走现有回退逻辑。
- yfinance 返回数据必须在入库前转换为项目统一 OHLC 格式。
- yfinance 必须显式指定价格复权参数，禁止依赖库版本默认行为。
- 增加离线可重复的 yfinance 单元测试和四源并发调度测试。

### 2.2 可选增强

- 扫描任务完成后展示每个数据源成功拉取的股票数量。
- 记录每个数据源成功率、平均耗时和限流次数。
- 后续增加数据源健康度评分，动态降低连续失败源的调度频率。

### 2.3 不做范围

- 不让同一股票同时请求四个数据源。
- 不对四个数据源返回结果做投票或价格一致性仲裁。
- 不重构现有 `_fetch_with_retry()` 多源回退模型。
- 不新增数据库表或修改 `daily_ohlc` schema。
- 不将 yfinance 用于股票池获取。
- 不将 yfinance 用于实时行情。
- 不将外部网络实测设为常规 CI 必过测试。
- 不删除百度或新浪。

---

## 3. 默认假设

1. 目标代码以已包含配置化 `daily_sources`、多源互斥锁和 `_fetch_with_retry()` 的更新版本为基础。
2. 四源同时工作表示“四个源并行处理不同股票”，不是“每只股票请求四次”。
3. `worker_count >= 4`、待处理股票不少于四只且四源可用时，才具备四源同时工作的条件。
4. 用户显式设置 `worker_count < 4` 时，系统尊重用户配置并记录警告，不强制覆盖。
5. yfinance 的 A 股日线数据通过 Yahoo Finance 符号后缀获取。
6. yfinance 不提供项目可直接使用的历史成交额，使用 `close * volume` 估算 `turnover`，与部分现有源的回退口径一致。
7. 项目当前策略依赖统一价格口径；yfinance 必须显式使用 `auto_adjust=True`，与现有前复权目标保持一致。
8. yfinance 限流、连接失败、空数据和解析失败均视为单源失败，由引擎层继续回退。

---

## 4. 产品设计方案

### 4.1 用户使用流程

1. 用户安装项目依赖并启动扫描。
2. 系统读取 `data.daily_sources` 和 `data.worker_count`。
3. 系统创建百度、新浪、腾讯、yfinance 四个独立数据源锁。
4. 四个工作线程分别从股票队列获取不同股票。
5. 各线程尝试获取空闲数据源锁并拉取股票日线。
6. 数据源成功返回后，系统归一化并保存数据。
7. 数据源失败时，当前股票继续尝试配置链中的其他源。
8. 单只股票全部源失败时记录失败，但扫描继续。

### 4.2 页面展示要求

本次不强制新增前端页面。

策略配置页如未来展示数据源配置，应将 yfinance 与百度、新浪、腾讯并列展示，不标记为只能兜底。

### 4.3 交互规则

- 默认配置启用四个数据源。
- 默认 `worker_count` 为 `4`。
- `worker_count < daily_sources 数量` 时允许启动，但日志警告不能保证所有源同时工作。
- 数据源名称未知时沿用现有配置错误行为。
- yfinance 不可用时不影响其他数据源工作。
- yfinance 成功后，该股票不再请求其他数据源。

---

## 5. 技术架构方案

### 5.1 总体架构

涉及模块：

- `requirements.txt`：增加 yfinance 依赖。
- `config.yaml`：将 yfinance 加入默认日线源，默认线程数改为 4。
- `scanner/yfinance_source.py`：yfinance 获取、代码映射和数据归一化。
- `scanner/data_source.py`：增加 yfinance 独立锁。
- `scanner/engine.py`：注册 yfinance，并更新默认源列表和默认线程数。
- `scanner/single_stock_backtest.py`：将 yfinance 纳入需要 fresh 数据时的源链。
- `tests/test_yfinance_source.py`：纯 mock 单元测试。
- `tests/test_data_source.py`：四源锁和并发能力测试。
- `tests/test_engine_fresh_fetch.py`：四源回退和 yfinance 实际参与测试。

### 5.2 数据流设计

```text
股票队列
  → 工作线程获取股票
  → _fetch_with_retry()
  → 按配置顺序尝试空闲数据源
  → DataSourceManager.acquire(source)
  → fetch_<source>_daily(code, days)
  → 统一 list[dict] OHLC 格式
  → 与 SQLite 缓存合并
  → 保存 daily_ohlc
  → 后续流动性过滤和策略计算
```

yfinance 数据流：

```text
A 股代码
  → 转换为 Yahoo symbol
  → yf.Ticker(symbol).history(...)
  → DataFrame 行归一化
  → 过滤无效值
  → 按日期升序排序
  → 保留最近 days 条
  → 返回统一 list[dict]
```

### 5.3 四源并发调度设计

沿用现有方案 A：

- 每个数据源一把非阻塞互斥锁。
- 每个工作线程处理一只股票。
- 不同线程可同时使用不同数据源。
- 同一数据源同一时间最多处理一只股票。
- 单只股票一旦某个源成功，立即停止尝试后续源。
- 某个源忙碌时，当前股票尝试其他空闲源。
- 某个源请求失败时，当前股票继续尝试后续源。

默认配置：

```yaml
data:
  daily_sources:
    - baidu
    - sina
    - tencent
    - yfinance
  worker_count: 4
```

默认顺序只定义单只股票的回退优先级。四源同时参与依赖多线程和独立锁，并不要求 yfinance 排到第一位。

### 5.4 yfinance 代码映射

映射规则：

```text
600000 → 600000.SS
601xxx → 601xxx.SS
603xxx → 603xxx.SS
605xxx → 605xxx.SS
688xxx → 688xxx.SS
000001 → 000001.SZ
001xxx → 001xxx.SZ
002xxx → 002xxx.SZ
003xxx → 003xxx.SZ
300xxx → 300xxx.SZ
301xxx → 301xxx.SZ
```

北交所当前由市场配置默认排除。本次不为北交所设计 yfinance 后缀映射；遇到不支持代码时返回 `None` 并记录 debug 日志。

### 5.5 yfinance 请求设计

接口：

```python
def fetch_yfinance_daily(code: str, days: int = 250) -> list[dict] | None:
    ...
```

请求要求：

- 显式使用 `auto_adjust=True`。
- 显式使用 `actions=False`。
- 使用 `period` 获取略大于交易日需求的自然日范围，或使用足够覆盖 `days` 的起始日期。
- 最终必须只返回最近 `days` 个有效交易日。
- 禁止依赖 yfinance 的默认 `auto_adjust` 值。
- 单次请求失败时返回 `None`，不在源内部切换其他数据源。

使用 `Ticker.history()`，便于单只股票请求与现有数据源接口保持一致。

### 5.6 数据归一化设计

yfinance 入库前必须转换为：

```python
{
    "date": "YYYY-MM-DD",
    "open": float,
    "high": float,
    "low": float,
    "close": float,
    "volume": float,
    "turnover": float,
}
```

字段映射：

| yfinance 字段 | 项目字段 | 转换规则 |
|---|---|---|
| DataFrame index | `date` | 去除时区后格式化为 `YYYY-MM-DD` |
| `Open` | `open` | `float` |
| `High` | `high` | `float` |
| `Low` | `low` | `float` |
| `Close` | `close` | `float` |
| `Volume` | `volume` | `float`，单位为股 |
| 无直接字段 | `turnover` | `close * volume` |

无效行过滤规则：

- 日期缺失或无法格式化。
- Open、High、Low、Close 任一为空、NaN、非有限值或小于等于零。
- Volume 为空、NaN、非有限值或小于零。
- `turnover` 非有限值。

归一化后按日期升序排序，并只保留最近 `days` 条。

### 5.7 数据源状态设计

不新增数据库任务状态。

yfinance 的失败状态沿用现有 `source_errors`：

```json
{
  "yfinance": "attempts=2 error=empty response"
}
```

限流错误必须归类为 `data source busy`，使现有重试和 requeue 机制可以处理。yfinance 数据源模块不得吞掉可识别的限流异常；应抛出包含 `429`、`Too Many Requests` 或 yfinance 限流异常类型信息的异常，由引擎 `_classify_fetch_error()` 统一转换为 `data source busy`。

---

## 6. 数据库设计方案

### 6.1 新增表

无。

### 6.2 修改表

无。

### 6.3 索引设计

无新增索引。

### 6.4 数据兼容方案

- yfinance 使用现有 `daily_ohlc` 表。
- 入库字段与现有数据源完全一致。
- 继续按 `(code, date)` 合并和去重。
- yfinance 成功数据可以覆盖缓存中相同日期的数据，沿用 fresh 数据优先规则。
- 不保存数据源名称到 `daily_ohlc`，任务股票的 `primary_source`、`fallback_source` 和 `source_errors` 继续记录本次尝试信息。
- 本次不解决不同源复权口径的历史缓存标记问题；但 yfinance 必须显式使用 `auto_adjust=True`。

---

## 7. 接口设计方案

### 7.1 新增接口

无。

### 7.2 修改接口

现有配置接口自动支持新的源名称：

```http
GET /api/config
PUT /api/config
```

配置示例：

```json
{
  "data": {
    "daily_sources": ["baidu", "sina", "tencent", "yfinance"],
    "worker_count": 4
  }
}
```

### 7.3 接口兼容要求

- 不修改现有扫描接口 URL。
- 不修改候选接口结构。
- 旧配置未包含 yfinance 时继续按旧数据源列表运行。
- 用户可通过配置调整源顺序或禁用 yfinance。

---

## 8. 可以实施的代码方案

### 8.1 后端代码方案

#### `requirements.txt`

新增：

```text
yfinance>=0.2.54
```

实施时以 `0.2.54` 作为最低验证版本；如目标环境已有更高版本，应运行全部 yfinance mock 测试确认兼容。

#### `scanner/yfinance_source.py`

新增职责：

- 延迟或安全导入 yfinance。
- 将 A 股代码转换为 Yahoo symbol。
- 请求日线数据。
- 显式指定复权参数。
- 将 DataFrame 归一化为项目统一格式。
- 过滤无效行。
- 普通单源异常记录日志并返回 `None`。
- 可识别的 Yahoo 限流异常向引擎抛出，不能在源模块内吞掉。

函数结构：

```python
def fetch_yfinance_daily(code: str, days: int = 250) -> list[dict] | None:
    ...

def _to_yahoo_symbol(code: str) -> str | None:
    ...

def _normalize_history(history, days: int) -> list[dict]:
    ...

def _normalize_row(index, row) -> dict | None:
    ...
```

不允许：

- 在该模块中调用百度、新浪或腾讯。
- 在该模块中写数据库。
- 在该模块中实现扫描重试链。

#### `scanner/data_source.py`

将锁集合扩展为：

```python
self._locks = {
    "baidu": threading.Lock(),
    "sina": threading.Lock(),
    "tencent": threading.Lock(),
    "yfinance": threading.Lock(),
}
```

保持现有：

- 非阻塞获取。
- 独立源互不冲突。
- 重复释放安全。

#### `scanner/engine.py`

需要修改：

- 导入 `fetch_yfinance_daily`。
- `_daily_fetch_fn()` 注册 `"yfinance"`。
- `DEFAULT_DAILY_SOURCES` 增加 yfinance。
- `scan_all()` 默认 `worker_count` 调整为 4。
- 配置未指定 `worker_count` 时使用 4。
- 启动扫描时，如果 `worker_count < len(daily_sources)`，记录并发不足警告。

不得修改：

- 单只股票成功后立即返回的行为。
- fresh-first 规则。
- 数据源失败回退逻辑。
- 缓存合并与去重逻辑。
- 单只股票失败不中断扫描规则。

#### `scanner/single_stock_backtest.py`

需要将 yfinance 纳入 `default_fresh_fetch()` 的数据源链，使回测在现有源失败时也可以使用 yfinance 获取历史数据。

回测 fresh 获取仍为顺序尝试，不要求四源并行。

#### `config.yaml`

默认配置：

```yaml
data:
  daily_sources:
    - baidu
    - sina
    - tencent
    - yfinance
  worker_count: 4
```

#### 并发控制

- yfinance 必须拥有独立互斥锁。
- 同一进程内同一时间只允许一个线程调用 yfinance，降低限流风险。
- 腾讯、百度、新浪和 yfinance 可以彼此同时工作。
- 不新增线程池或异步框架，继续使用现有线程模型。

#### 缓存策略

- yfinance 成功后与现有缓存按日期合并。
- 合并结果限制为本次日线拉取天数。
- fresh 数据优先覆盖相同日期缓存数据。
- 所有源失败时不能使用旧缓存生成新扫描结果。

### 8.2 前端代码方案

本次不要求修改前端。

如果策略配置页已经支持编辑 `data.daily_sources` 和 `worker_count`，应确保 yfinance 名称可保存且不会被过滤；如果当前页面不展示这些字段，则保持现状。

---

## 9. 日志与异常处理方案

### 9.1 必须记录的日志

- 扫描启动时记录启用的数据源列表和工作线程数。
- `worker_count < daily_sources 数量` 时记录警告：

```text
工作线程数 3 小于启用数据源数 4，无法保证所有数据源同时参与拉取。
```

- yfinance 返回空数据、依赖缺失、限流或解析失败时记录源级错误。
- yfinance 成功时沿用现有成功日志，包含股票代码、数据源名称、行数和最近行情。
- `source_errors` 必须包含 yfinance 的失败信息。

### 9.2 异常处理

- yfinance 未安装：记录警告并返回 `None`，继续其他源。
- 不支持的股票代码：返回 `None`，继续其他源。
- 返回空 DataFrame：返回 `None`。
- DataFrame 字段缺失：返回 `None`。
- 部分无效行：跳过无效行；全部无效时返回 `None`。
- 普通连接异常：记录日志并返回 `None`。
- Yahoo 限流：必须抛出可被引擎分类为 `data source busy` 的异常。
- 单只股票全部源失败：沿用现有失败记录。

---

## 10. 测试方案

### 10.1 单元测试

新增 `tests/test_yfinance_source.py`，使用 mock DataFrame，不访问外网：

- 沪市代码映射为 `.SS`。
- 深市、创业板代码映射为 `.SZ`。
- 不支持代码返回 `None`。
- `Ticker.history()` 显式收到 `auto_adjust=True` 和 `actions=False`。
- DataFrame 正确转换为统一字段。
- 日期索引去除时区并格式化。
- `turnover == close * volume`。
- 返回按日期升序排列。
- 只保留最近 `days` 条。
- NaN、无效价格和无效成交量行被过滤。
- 空 DataFrame 返回 `None`。
- yfinance 异常返回 `None`。
- yfinance 限流异常不会被吞掉，可由引擎归类为 `data source busy`。
- yfinance 依赖缺失时返回 `None`。

### 10.2 数据源管理测试

扩展 `tests/test_data_source.py`：

- yfinance 锁可获取和释放。
- 百度、新浪、腾讯、yfinance 四把锁互不冲突。
- 四个锁同时被占用后 `try_acquire_any()` 返回 `None`。
- 释放任一源后可再次获取。

### 10.3 引擎测试

扩展 `tests/test_engine_fresh_fetch.py`：

- `_daily_fetch_fn("yfinance")` 返回 yfinance 获取函数。
- 默认源列表包含四个源。
- yfinance 成功时合并并保存统一格式数据。
- 腾讯成功不阻止其他线程使用 yfinance 处理另一只股票。
- 四个工作线程和四个空闲源时，使用测试同步屏障证明四个源在同一时间段分别处理不同股票，而不只是先后被调用。
- 百度和新浪可用时仍会参与处理不同股票。
- yfinance 失败后继续尝试其他源。
- 其他源失败后可以回退到 yfinance。
- yfinance 忙碌时记录 `source_errors["yfinance"] == "busy"`。
- 全部四源失败时不使用旧缓存。
- `worker_count < daily_sources 数量` 时记录警告但仍启动。

### 10.4 回测测试

扩展单股回测 fresh 数据测试：

- 百度、新浪、腾讯均失败时，yfinance 可提供回测数据。
- yfinance 失败时返回既有数据覆盖错误，不静默使用不完整缓存。

### 10.5 外部网络验证

保留或新增手工外部网络验证，但不纳入常规 CI 必过集合：

```bash
python -m pytest tests/test_yfinance_hist.py -v
```

该测试可能因 Yahoo 限流、代理或网络环境失败。常规回归必须依赖 mock 单元测试。

### 10.6 回归测试

必须验证：

- 原有百度、新浪、腾讯源测试通过。
- 多源失败回退链不变。
- 数据源锁始终释放。
- fresh-first 行为不变。
- SQLite 入库字段不变。
- 流动性过滤和策略模块无需感知数据来自 yfinance。
- 全量离线后端测试通过。
- 前端构建通过。

验证命令：

```bash
python -m pytest tests/test_yfinance_source.py tests/test_data_source.py tests/test_engine_fresh_fetch.py -v
python -m pytest tests/ -v --ignore=tests/test_yfinance_hist.py --ignore=tests/test_akshare_hist.py
cd web && npm run build
```

---

## 11. 验收标准

1. yfinance 已作为正式日线数据源接入。
2. 默认启用百度、新浪、腾讯、yfinance 四个源。
3. 默认工作线程数为 4。
4. 四源可用、线程和股票数量充足时，四源能够同时处理不同股票。
5. 百度和新浪偶尔恢复时仍能正常参与。
6. 腾讯正常时，yfinance 仍能由其他线程实际参与拉取。
7. 同一股票成功获取一次后不再重复请求其他源。
8. 任一源失败后当前股票可继续走其他源回退。
9. yfinance 入库数据字段、类型和排序与现有数据源一致。
10. yfinance 显式使用 `auto_adjust=True`。
11. yfinance `turnover` 使用 `close * volume` 计算。
12. yfinance 失败不会中断全市场扫描。
13. 外部网络失败不会导致常规 CI 失败。
14. 不修改数据库 schema。
15. 离线自动化测试和现有回归测试通过。

---

## 12. 给 Claude Code / Codex 的执行指令

请严格按照本文档执行开发。

执行要求：

1. 先确认目标代码包含配置化 `daily_sources`、`DataSourceManager` 和 `_fetch_with_retry()`。
2. 先阅读百度、新浪、腾讯数据源模块和对应测试，沿用统一返回格式。
3. yfinance 数据源必须是纯数据源模块，失败返回 `None`，不能内部切换其他源。
4. 不修改现有单只股票成功即停止的行为。
5. 不实现每只股票四源重复拉取。
6. yfinance 必须有独立互斥锁。
7. 默认线程数必须支持四源并发。
8. yfinance 原始数据必须在进入引擎前完成格式归一化。
9. 所有 yfinance 自动化测试必须 mock 外部网络。
10. 外部网络实测必须与常规 CI 分离。
11. 不修改数据库 schema、策略算法或流动性过滤逻辑。
12. 每完成一个模块后运行对应测试，最后运行离线全量回归。

---

## 13. 最终交付物

开发完成后需要交付：

1. 修改文件清单。
2. yfinance 股票代码映射说明。
3. yfinance 数据字段归一化说明。
4. 四源并发和失败回退说明。
5. 默认数据源列表和线程数变更说明。
6. yfinance 限流与异常处理说明。
7. 单元测试和引擎测试结果。
8. 离线全量测试结果。
9. 外部网络手工验证结果。
10. 是否存在复权口径或数据质量遗留问题。

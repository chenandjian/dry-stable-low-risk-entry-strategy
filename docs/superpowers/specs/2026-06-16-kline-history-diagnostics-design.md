# 个股历史 K 线数据诊断页设计

## 1. 背景

策略1和策略2已经共用本地 `daily_ohlc` 与扫描任务里的 `task_stocks.kline_*` 元数据来判断日线缓存是否可以复用。用户需要一个独立页面，按股票代码和日期范围分页查看本地历史 K 线，并在页面顶部直接看到这只股票是否覆盖“最近一个完整交易日”。

该页面是诊断与核对工具，不触发外部行情源拉取，不改变扫描、回测或策略候选逻辑。

## 2. 目标

新增独立页面 `/data/kline-history`，支持：

1. 输入股票代码、开始日期、结束日期、分页大小。
2. 分页查询本地 `daily_ohlc`。
3. 页面顶部展示最新 K 线日期、最近拉取时间、目标完整交易日、数据是否最新、是否需要重新拉取。
4. 对停牌/无交易场景给出清晰状态，不把“最新 K 线不是自然日当天”直接等同为失败。

## 3. 非目标

1. 不增加“立即拉取”按钮。
2. 不调用 Baidu/Sina/Tencent/yfinance 等外部数据源。
3. 不修改策略1、策略2评分、候选入选、回测语义。
4. 不引入节假日交易日历，继续使用项目当前的周一至周五交易日模型。

## 4. 后端设计

### 4.1 API

新增接口：

```text
GET /api/stock/{code}/kline-history?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&page=1&page_size=50
```

返回结构：

```json
{
  "code": "000831",
  "rows": [
    {
      "date": "2026-06-16",
      "open": 10.1,
      "high": 10.5,
      "low": 10.0,
      "close": 10.3,
      "volume": 1234567,
      "turnover": 12345678
    }
  ],
  "total": 120,
  "page": 1,
  "page_size": 50,
  "summary": {
    "latest_kline_date": "2026-06-16",
    "latest_fetch_time": "2026-06-16 15:12:00",
    "target_trade_date": "2026-06-16",
    "min_fetch_time": "2026-06-16 15:00:00",
    "quote_status": "not_requested",
    "is_fresh": true,
    "needs_refetch": false,
    "reason": "数据已覆盖目标完整交易日"
  }
}
```

参数校验：

- `page < 1` 时按 `1` 处理。
- `page_size` 限制在 `1..200`，默认 `50`。
- `start_date > end_date` 返回 HTTP 400。
- 股票没有任何本地 K 线时返回 200，`rows=[]`、`total=0`，summary 明确 `needs_refetch=true`。

### 4.2 数据查询

在 `scanner/db.py` 新增两个只读 helper：

1. `get_ohlc_history_page(code, start_date=None, end_date=None, page=1, page_size=50)`  
   返回分页行、总数、分页参数。

2. `get_latest_task_stock_kline_metadata(code)`  
   从 `task_stocks` 读取这只股票最近一次有 K 线元数据的记录，优先按 `kline_fetched_at DESC, updated_at DESC` 排序，返回 `kline_latest_date`、`kline_fetched_at`、`kline_target_trade_date`、`quote_status`。

### 4.3 新鲜度判断

后端 summary 使用 `scanner.daily_data_service.build_cache_freshness_context()` 计算：

- `target_trade_date`
- `min_fetch_time`

判断规则：

1. `latest_kline_date >= target_trade_date` 且 `latest_fetch_time >= min_fetch_time` 时，`is_fresh=true`。
2. `quote_status in ('suspended', 'no_trade')` 且 `latest_fetch_time >= min_fetch_time` 时，即使 `latest_kline_date < target_trade_date`，也视为可接受，`is_fresh=true`。
3. 其他情况 `is_fresh=false`，`needs_refetch=true`。
4. 如果没有最近拉取时间，不能判定为新鲜。

这个判断只用于诊断展示，不驱动扫描复用；扫描复用仍以现有 `get_reusable_task_stock_kline_context()` 和 `select_fresh_cached_ohlc()` 为准。

## 5. 前端设计

### 5.1 路由与导航

- 新增页面：`web/src/pages/KlineHistory.vue`
- 新增路由：`/data/kline-history`
- 顶部导航新增入口：`K线数据`

### 5.2 页面结构

页面顶部：

- 标题：`个股 K 线数据诊断`
- 说明：用于核对本地 K 线是否覆盖最近一个完整交易日。
- 状态卡：
  - 最新K线日期
  - 最近拉取时间
  - 目标完整交易日
  - 数据状态：`数据最新` / `需要重新拉取`
  - 行情状态：`not_requested` / `suspended` / `no_trade` 等

查询区域：

- 股票代码输入框，默认可为空。
- 开始日期、结束日期。
- 每页条数。
- 查询按钮。

结果区域：

- 表格列：日期、开盘、最高、最低、收盘、成交量、成交额。
- 分页：上一页、下一页、当前页、总条数。
- 无数据时展示“本地没有该股票 K 线数据”。
- API 失败时展示错误信息。

## 6. 测试策略

### 6.1 后端测试

新增 `tests/test_kline_history_api.py`：

1. 分页与日期过滤正确。
2. 数据覆盖目标完整交易日且拉取时间足够新时，summary 显示 `is_fresh=true`。
3. 只有旧 K 线但 `quote_status='suspended'` 且拉取时间足够新时，summary 显示可接受。
4. `start_date > end_date` 返回 400。

### 6.2 前端测试

新增 `web/src/pages/__tests__/KlineHistory.test.js`：

1. 初始查询后渲染 summary 状态卡和表格数据。
2. 点击下一页时带上 `page=2` 调用 API，并更新表格。
3. 当 summary 显示 `needs_refetch=true` 时页面展示醒目的“需要重新拉取”。

## 7. 验收标准

1. `/data/kline-history` 可以通过顶部导航进入。
2. 输入股票代码和日期范围后可以分页查看本地 K 线。
3. 页面顶部的新鲜度结论与当前扫描缓存口径一致。
4. 不触发外部行情源拉取。
5. 后端专项测试、前端专项测试、编译和构建通过。

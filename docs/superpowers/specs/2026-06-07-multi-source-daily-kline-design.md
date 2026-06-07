# 多源每日 K 线拉取设计

Date: 2026-06-07

## 1. 背景

当前全市场扫描的日线数据主要依赖新浪和腾讯 HTTP 接口。近期扫描中新浪返回 `456 Client Error`，腾讯 K 线接口也可能返回空数据，导致后端日志频繁报错、扫描回退效率低，并增加 HTTP 风控风险。

外部 `a-stock-data` 技能的行情层策略建议：K 线/行情优先使用通达信 `mootdx` TCP 数据源；腾讯更适合实时行情字段；东财不适合高频全市场日线拉取。基于该策略，本项目只学习“每日股票 K 线拉取”部分，不引入研报、资金流、公告等其他功能。

## 2. 目标

新增多源日线拉取链，默认顺序：

```text
mootdx → baidu → sina → tencent
```

目标：

1. 优先用 `mootdx` 通达信 TCP 拉取日线，减少新浪/腾讯 HTTP 风控触发。
2. 新增百度股市通 K 线 HTTP 备用源。
3. 保留新浪、腾讯作为末级兜底。
4. 保持现有扫描策略、评分、前端展示、股票池逻辑不变。
5. 保持 fresh-first：只有 fresh 数据源成功后才与缓存合并并用于扫描；所有源失败时不能用旧缓存生成扫描结果。

## 3. 非目标

第一版不做：

- 不引入东财日线源。
- 不接入外部技能中的研报、资金流、公告、财务等功能。
- 不改杯柄识别、VCP、评分、干稳低吸分析逻辑。
- 不扩前端任务详情显示每个数据源的完整尝试历史。
- 不在 SQLite 增加新的 `source_attempts` JSON 字段；沿用现有 primary/fallback 字段做兼容记录。

## 4. 数据源设计

### 4.1 mootdx 日线源

新增：

```text
scanner/mootdx_source.py
```

接口：

```python
fetch_mootdx_daily(code: str, days: int = 250) -> list[dict] | None
```

实现要点：

- 使用 `mootdx.quotes.Quotes.factory(market='std')`。
- 日线 category 使用 `4`。
- 市场：深市 `market=0`，沪市 `market=1`。
- 将 mootdx 返回字段归一到项目格式：
  - `date`
  - `open`
  - `high`
  - `low`
  - `close`
  - `volume`
  - `turnover`
- 返回按日期升序列表。
- 连接失败、返回空、字段缺失时返回 `None`。

### 4.2 百度股市通 K 线源

新增：

```text
scanner/baidu_source.py
```

接口：

```python
fetch_baidu_daily(code: str, days: int = 250) -> list[dict] | None
```

使用接口：

```text
https://finance.pae.baidu.com/selfselect/getstockquotation
```

关键参数：

```python
{
  "all": "1",
  "isIndex": "false",
  "isBk": "false",
  "isBlock": "false",
  "isFutures": "false",
  "isStock": "true",
  "newFormat": "1",
  "group": "quotation_kline_ab",
  "finClientType": "pc",
  "code": code,
  "ktype": "1",
}
```

解析：

- `Result.newMarketData.keys` 给出字段名。
- `Result.newMarketData.marketData` 是 `;` 分隔的 K 线行。
- 每行按 keys 对齐，提取 `time/open/close/high/low/volume/amount`。
- 返回项目统一 OHLC 格式。
- 只取最近 `days` 条。

## 5. 引擎改造

当前 `_fetch_with_retry()` 是双源模型：

```text
primary source → fallback source
```

第一版改为多源链模型，但保持对现有调用的兼容。默认配置新增：

```yaml
data:
  daily_sources:
    - mootdx
    - baidu
    - sina
    - tencent
```

新逻辑：

1. 根据配置顺序尝试数据源。
2. 每个源最多使用现有 retry attempts 策略。
3. 任一源返回 fresh 数据：
   - 与 SQLite 缓存按日期合并。
   - 保存合并后的 OHLC。
   - 返回 `FetchResult(data=merged, ...)`。
4. 全部失败：返回 `FetchResult(data=None, ...)`。
5. 现有扫描层继续根据 `FetchResult` 决定：
   - transient busy → requeue。
   - 超过 busy 重试预算 → failed。
   - 普通失败 → failed。

## 6. 兼容字段映射

暂不扩表，继续使用现有字段：

- `primary_source`: 数据源链中的第一个源。
- `fallback_source`: 第一个成功的非 primary 源；如果全部失败，则记录最后尝试源。
- `primary_attempts`: 主源尝试次数。
- `fallback_attempts`: 最后一个非 primary 源的尝试次数；第一版不记录完整链路次数。
- `primary_error`: 主源失败原因。
- `fallback_error`: 最终失败原因或备用源失败摘要。

如果后续需要前端展示完整链路，可再增加 `task_stocks.source_attempts` JSON 字段；第一版不做。

## 7. 错误处理

### 7.1 mootdx

- 连接失败、服务器不可用、返回空：该源失败，继续百度。
- 不归类为 `data source busy`。

### 7.2 百度

- HTTP 失败、返回空、解析失败：继续新浪。
- 403/429 可归类为 `data source busy`。

### 7.3 新浪

- 456/429：归类为 `data source busy`，走现有 requeue 和 busy 重试预算。
- 普通 HTTP/解析错误：该源失败，继续腾讯。

### 7.4 腾讯

- 返回空或解析失败：该源失败。
- 如果全部源失败，不能使用旧缓存产出扫描结果。

## 8. 测试计划

新增/扩展测试：

1. `tests/test_mootdx_source.py`
   - mootdx 返回字段可转为项目 OHLC 格式。
   - 空数据返回 `None`。
   - 异常返回 `None`。

2. `tests/test_baidu_source.py`
   - 百度 `keys + marketData` 可解析成项目 OHLC 格式。
   - 缺字段/空数据返回 `None`。

3. `tests/test_engine_fresh_fetch.py`
   - 默认优先尝试 `mootdx`，成功时不调用后续源。
   - `mootdx` 失败后调用百度。
   - 百度失败后调用新浪，再失败调用腾讯。
   - 新浪 456 继续归类为 `data source busy`。
   - 所有源失败时不使用旧缓存。

4. 全量验证：

```bash
python -m pytest tests/ -v
npm --prefix web run build
```

## 9. 依赖

新增依赖：

```text
mootdx>=0.10
```

加入 `requirements.txt`。

百度源只使用现有 `requests`。

## 10. 验收标准

1. 全市场扫描默认按 `mootdx → baidu → sina → tencent` 拉取日线。
2. `mootdx` 成功时不触发新浪/腾讯 K 线请求。
3. `mootdx` 失败时能自动回退百度。
4. 百度失败时能继续回退新浪/腾讯。
5. 新浪 456/429 不再造成后端异常，仍按 source busy 处理。
6. 所有源失败时不使用旧缓存扫描。
7. 所有新增和现有测试通过。

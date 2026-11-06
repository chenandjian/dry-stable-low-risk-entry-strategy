# TickFlow SDK升级与美股数据复测

## 范围

2026-11-06，在项目当前Python 3.12环境升级SDK，使用免费端真实请求验证。
不修改策略规则、现有行情适配代码、用户配置、生产日线、候选或生命周期。

## 升级

```text
python -m pip install --upgrade "tickflow[all]" --timeout 30 --retries 1
tickflow: 0.1.24 -> 0.1.26
新增依赖: zstandard 0.25.0
```

`requirements.txt`最低SDK版本同步提高到0.1.26，避免旧环境继续满足0.1.24而不升级。
运行中的服务仍需重新启动才能可靠加载新SDK；本次不主动中断服务。
安装过程提示既有无效发行包 `~ertifi`，未尝试清理或改动其他环境包。

## 真实免费端结果

调用 `TickFlow.free(timeout=20, max_retries=0)`。
日线使用 `klines.batch`，批大小3、SDK并发数1，三个代码一起请求。

| 标的 | 比例前复权历史根数 | 首日 | 最新日 | amount非零根数 | OHLC高低关系异常 |
| --- | ---: | --- | --- | ---: | ---: |
| AAPL.US | 1100 | 2022-06-21 | 2026-11-05 | 0 | 0 |
| MSFT.US | 1100 | 2022-06-21 | 2026-11-05 | 0 | 0 |
| NVDA.US | 1100 | 2022-06-21 | 2026-11-05 | 0 | 0 |

另对同样三只股票分别请求5根 `forward_additive`、`none` 日线，均成功返回，amount仍全部为0。
再用 `as_dataframe=False` 查询AAPL的5根日线，返回字典中的amount同样全为0，说明并非DataFrame转换时丢失成交额。
高低关系校验仅验证 `high >= open/close/low` 及 `low <= open/close/high`，不代表跨供应商准确性已经验收。
三个复权参数可用不代表拆股分红处理已对账；最近5日三种口径价格一致不能证明历史复权算法等价。

### 股票池及元数据

- `US_Equity`返回12412个标的；此数量不是已验证的普通股数量。
- 代码包含 `BRK.A.US`、`BRK.B.US`，必须从右侧解析市场后缀，不能按第一个点截断代码。
- AAPL、MSFT、NVDA、SPY、BRK.B元数据请求成功。
- 上述元数据的 `exchange`全部为 `US`，不能据此区分NASDAQ、NYSE等真实上市交易所。
- SPY名称明确包含ETF，但返回 `type=stock`、`ext.type=us_equity`；不能仅用该类型字段排除ETF。

## 与升级前比较

升级前后均能获取美股股票池、1100根样本日线及复权参数响应。
SDK升级未改变本次样本的成交额缺失、证券类型不精细、交易所不精细三个问题。
不能将这些问题直接归因于旧SDK，也不能从免费端样本推断认证端一定相同。

## 对迁移的影响

1. 美股日线批量获取可继续使用TickFlow；当前不必因SDK版本而更换供应商。
2. 现有 `normalize_frame()`固定成交量乘100，仅适用于当前A股约定，不得直接用于美股。
3. 缺失成交额需要按未知数据处理，不能把0当成真实无成交，也不能让其触发极致缩量判断。
4. 应进一步确认认证端是否有有效历史成交额；如使用估算美元成交额，必须单独标记并经用户确认。
5. 普通股类型、真实交易所、真实美股指数、交易时段、拆股及分红口径仍需独立验证。
6. 本次未接入美股扫描，未将美股数据转换后写入现有A股表。

## 项目回归

```text
python -m pytest tests/test_tickflow_client.py tests/test_tickflow_normalize.py tests/test_tickflow_service.py tests/test_tickflow_symbols.py tests/test_tickflow_indexes.py tests/test_data_acquisition.py -q
72 passed，18.96秒
```

相关回归使用mock及临时数据库；真实免费端请求另行执行，不加入常规自动测试。
本次未测试认证端、全市场性能、真实指数覆盖、退市历史和其他供应商数据一致性。
未修改前端，未运行前端构建或测试。

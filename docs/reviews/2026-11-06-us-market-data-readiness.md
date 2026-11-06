# 美股迁移前置数据验收

日期：2026-11-06。SDK：TickFlow 0.1.26。
状态：`PARTIAL_PASS / BLOCKED_DATA_ACCEPTANCE`。
仅进行了只读真实网络查询和代码审查，没有修改策略、生产配置或生产数据库。

## 1. 已确认的事实

前次样本见 [SDK升级复测](2026-11-06-tickflow-sdk-upgrade-us-data-retest.md)：
免费端能批量返回AAPL、MSFT、NVDA的1100根日线，US_Equity返回12412个标的。
样本的amount全部为0，不能当作真实零成交，也不能写成有效成交额。

本次追加查询：

| 请求 | 实际结果 | 能得出的结论 |
| --- | --- | --- |
| `exchanges.list()` | SH、SZ、US、HK、BJ，US计数12508 | 交易所目录计数不等于US_Equity池计数，不可混用分母 |
| `exchanges.get_instruments('US', instrument_type='index')` | 空列表 | 此查询未找到真实美股指数，不代表全部接口或认证端必然没有 |
| 同接口 `instrument_type='etf'` | 空列表 | 不能据此认为美股池没有ETF；此前SPY被标为stock |
| 仅筛选US区域的标的池列表 | 只有US_Equity，计数12412 | 当前免费端目录没有独立返回US指数池 |
| `klines.ex_factors(['AAPL.US','MSFT.US','NVDA.US'])` | PermissionError：无除权因子查询权限 | 免费端因子权限不满足，不自动切换认证端 |

不能把“参数接受、请求成功”当作字段含义已经验证。

## 2. NVDA拆股窗口实测

查询窗口：2024-06-03至2024-06-14；`period=1d`，`count=30`。
每次明确设置 `start_time/end_time`（UTC毫秒），分别查询none、forward、forward_additive。
NVIDIA的10比1拆股以2024-06-10开始的拆股后交易为参考事件。

| 模式 | 2024-06-07收盘 | 2024-06-10收盘 | 观察 |
| --- | ---: | ---: | --- |
| none | 1208.88 | 121.79 | 包含拆股价格断层 |
| forward | 120.54430830024623 | 121.4437083619316 | 本样本消除了约10倍断层 |
| forward_additive | 1208.88 | 121.79 | 本窗口与none相同，不能作为美股已正确复权的证据 |

这修正了前次仅检查近期5日、三种模式都能返回数据的不足。
本次结论只适用于实测免费端样本，不能泛化为所有标的或认证端实现。

三种模式在2024-06-07都返回volume=412385776，在2024-06-10都返回volume=314162688。
volume在调整模式间一致不能单独证明它是历史实际成交股数，也不能证明它未做拆股归一。
在确认volume口径前，禁止直接用none价格乘该volume生成已验收的历史估算成交额。
分红调整、反向拆股及其他股票的量价匹配仍未验收。

事件参考：[NVIDIA向SEC提交的拆股公告](https://www.sec.gov/Archives/edgar/data/1045810/000104581024000144/nvda-20240607.htm)。
接口和复权参考：[TickFlow快速开始](https://docs.tickflow.org/zh-Hans/sdk/python-quickstart)、[FAQ](https://docs.tickflow.org/zh-Hans/faq)。

## 3. 分类与真实交易所的可用补充来源

实际下载并以竖线CSV解析Nasdaq Trader官方目录：

- https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt
- https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt

两文件尾行均为 `File Creation Time: 1106202609:46` 加分隔符。
尾行不是证券，不计入证券数量；实际返回含尾行记录数分别为5611和7667。
仅当前快照，不构成历史时点股票池或退市数据库。

| 代码 | 官方目录证据 | 判断 |
| --- | --- | --- |
| AAPL | nasdaqlisted，Common Stock，ETF=N，Test Issue=N | 样本可映射NASDAQ，符合普通股候选分类 |
| MSFT | 同上 | 同上 |
| NVDA | 同上 | 同上 |
| BRK.B | otherlisted，Exchange=N，ETF=N，New Common Stock | 映射NYSE；必须保留代码中的点 |
| SPY | otherlisted，Exchange=P，ETF=Y | ETF，映射NYSE Arca，不进入普通股股票池 |

字段定义：[Nasdaq Trader官方说明](https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs)。
ETF=N不能独立证明普通股：优先股、权证、单位证券、ADR等仍需明确分类，不能只按“不是ETF”放行。
映射冲突、目录缺失及无法确认的证券类型进入待核查，不依赖模糊名称猜测入池。

## 4. 项目代码边界

| 文件 | 当前边界 |
| --- | --- |
| tickflow_data/symbols.py | 只支持六位A股和SH/SZ/BJ |
| tickflow_data/service.py | `_code_for_symbol()`从第一个点拆分，会错误截断BRK.B.US |
| tickflow_data/normalize.py | 固定volume乘100；amount存为turnover |
| tickflow_data/client.py | 股票固定forward_additive |
| scanner/daily_data_service.py | A股15:00/15:10和工作日日历 |
| scanner/db.py | 全局DB_PATH加线程连接，不能运行时切两个市场路径 |
| strategy6/strong_start.py、scorer.py、filters.py | 启动、打分、流动性依赖成交额；启动还含A股涨停规则 |
| strategy6/market.py、batch_evaluator.py | 固定A股宽基指数与沪深300基准 |

## 5. 放行与阻塞

可继续设计和开发：独立美股存储、证券映射、可审计股票池、市场上下文、只读数据诊断及测试。

正式扫描仍有阻塞：

1. 未验收的真实指数代码、覆盖区间及读取权限。
2. 未确认的成交量单位及拆股归一方式；需要供应商说明或可信对照。
3. 免费端因子权限不足；用户后续确认Key无法读取数据，要求继续免费端，不进行认证补测。

Key不可用是用户反馈，本轮没有认证端实测，不推断其失败根因。
用户随后明确仅使用TickFlow免费端，不增加只读补充来源；数据缺失继续阻塞正式启用。
未经放行不得关闭市场过滤、以ETF冒充指数、将缺失成交额填0或启用正式美股候选。

## 6. 审核与未验证项

本次未运行收益回测、全市场扫描或代码回归；没有程序代码变更。
真实请求返回空列表、权限错误、有效样本数据均如实保留为结论，不将错误包装成成功。
文档自检重点：阶段依赖、旧逻辑保护、数据口径、零值/未知值、并发隔离、不可放行条件。
配套设计和计划分别位于specs/plans目录，状态均是待数据验收，不是功能已实现。

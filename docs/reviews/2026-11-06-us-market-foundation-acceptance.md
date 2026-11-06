# 美股独立数据诊断阶段验收

## 1. 范围和结论

分支：`codex/strategy6-us-market-adaptation`，基于main `1664b22`。

完成美股适配的安全基础子阶段，而非完整美股产品：独立诊断存储、标的解析、官方目录保守分类、免费TickFlow日线诊断。
不更改A股配置、行情表、扫描、评分、候选、生命周期、前端或定时任务。
正式美股扫描仍为 `BLOCKED_DATA_ACCEPTANCE`；没有生成美股交易信号或收益报告。

## 2. 文件和行为

| 文件 | 核心变化 |
| --- | --- |
| `us_market/instruments.py` | 保留BRK.B内部点号；解析Nasdaq官方目录与原始生成时间；ETF、测试证券、非普通股和未知类型不进入元数据合格范围 |
| `us_market/daily_data.py` | 仅调用TickFlow.free；校验日期、重复行、有限数值及OHLC；成交量原样保留，不乘100；amount=0/缺失存为NULL |
| `us_market/repository.py` | 显式独立路径、短生命周期连接、WAL、事务、不可变快照；拒绝含非本模块表的数据库 |
| `us_market/__main__.py` | 多标的只读网络诊断，逐股保存到独立库；单股失败继续其他股票，最终返回非零退出码 |
| `tests/test_us_market_foundation.py` | 单位、缺失值、分类、代码、失败、并发、幂等和CN隔离测试 |

当前诊断表只有 `us_diagnostic_snapshots`，整个响应快照作为JSON原子写入。
同一snapshot_id重复相同内容是幂等的；不同内容必须使用新ID；不同复权模式不会覆盖旧证据。
不将此表冒充逐批生产行情表。正式存储、批量获取、恢复及扫描仍待实施。

目录中的 `eligible` 只表示通过本轮保守元数据分类，不代表供应商映射已验证或已成为生产股票池。
`PARSED_NOT_PROVIDER_VERIFIED` 必须与后续TickFlow股票池取交集后复核。
特殊符号无法安全转换时保留原始证券行，symbol=NULL，标记 `UNSUPPORTED_SYMBOL`，不猜映射、不丢弃证据。

## 3. 使用方式

在本美股worktree根目录执行（不需要Key）：

```powershell
python -m us_market AAPL MSFT NVDA BRK.B --count 10
python -m us_market AAPL --count 1100 --adjustment forward --db data/us_market.db
```

两条命令均已真实执行，第二条使用相同默认路径（实际执行时未显式传入--db）。
默认诊断库为当前目录下 `data/us_market.db`，不读取CN配置文件，不使用认证环境变量中的Key发请求。
命令输出摘要和快照ID；完整OHLC及成交量可用 `USRepository(path).get_snapshot(snapshot_id)` 读取。
SDK自身可能输出免费服务提示，命令标准输出不是严格JSONL流。
不要把生产A股数据库作为 `--db` 参数；已有其他表的库会被拒绝。

## 4. 真实数据验证

首次受限网络请求因DNS限制失败，无快照写入；允许外网后同一命令成功，退出码0。

| 代码 | 请求模式 | 行数 | 起始日期 | 最新日期 | 成交额缺失行数 |
| --- | --- | ---: | --- | --- | ---: |
| AAPL.US | free / forward | 10 | 2026-10-23 | 2026-11-05 | 10 |
| MSFT.US | free / forward | 10 | 2026-10-23 | 2026-11-05 | 10 |
| NVDA.US | free / forward | 10 | 2026-10-23 | 2026-11-05 | 10 |
| BRK.B.US | free / forward | 10 | 2026-10-23 | 2026-11-05 | 10 |

快照ID依次为：

- AAPL：`3a1778ca3e1a439187a4cb553d40615d`
- MSFT：`1b6d4c80d19549499574cb9d135dc282`
- NVDA：`cb3c2a778aed4fe39a54c2ddd7800002`
- BRK.B：`2629af7275ff4ffabb4b5c55ee2db1ff`

全部保存 `formal_scan_allowed=false`、`volume_basis=UNKNOWN`、`price_basis=PROVIDER_FORWARD_UNVERIFIED`。
成功请求不证明复权/成交量口径正确，也不证明覆盖最近完整美股交易日；目前未实现美股日历和新鲜度判断。
不计算缺乏量价基准证据的估算美元成交额。

免认证保护修正后的最终实测：AAPL请求1100根，实际1100根，2022-06-21至2026-11-05；1100根成交额全部缺失。
快照ID：`df9036f6ddb64a4a82677980faf9ee82`。

官方目录本次实测（生成时间原文 `1106202610:01`，不猜其时区）：

- [Nasdaq上市目录](https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt)：5610条证券记录，保守元数据合格3015条。
- [其他交易所目录](https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt)：7666条证券记录，保守元数据合格1902条；377条特殊代码待核查。
- AAPL/MSFT/NVDA识别为NASDAQ普通股，BRK.B为NYSE普通股，SPY为NYSE ARCA ETF且不合格。

这些为当次目录快照，不是历史存续股票池，也不是TickFlow全市场可用数量。

## 5. 双角色验收

开发先补失败测试，新增包之前测试因模块不存在失败，再实施代码。
审核发现三项实际遗漏，均先补失败测试再修复：

1. 含特殊符号的证券会中断整个目录解析。修复为保留原行、未知映射、不合格。
2. 名称含“Common Stock”的Warrants可能误分类普通股。修复单复数权证排除，保持保守分类。
3. SDK 0.1.26的free()底层仍会读取TICKFLOW_API_KEY，且免费URL可被环境变量覆盖。独立US适配器显式固定免费URL，创建后在任何请求前清除该实例的认证Key，不改全局环境变量；真实SDK离线请求头测试确认不发送x-api-key。

第3项使用SDK私有客户端属性作为最小兼容措施；升级后若接口不可识别，会关闭实例并明确失败，不带Key继续请求。
此修正仅限新US模块，不顺带改动A股既有采集器。

另补同一ID并发幂等写入串行事务、跨US库隔离、CN全局连接不受影响、错误响应不落盘、SDK关闭和CLI部分失败退出码测试。
本子阶段复核未发现仍需修复的中高等级问题；此结论不代表尚未开发阶段已通过验收。

## 6. 验证记录

| 命令/范围 | 真实结果 |
| --- | --- |
| `python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py` | 1837 passed、9 skipped，377.05秒；此轮加载了最初15项US测试，后续审核新增测试另行验证 |
| `python -m pytest tests/test_us_market_foundation.py -q` | 最终22 passed |
| 上述US测试加TickFlow client/normalize/service/symbols/indexes/cli/freshness/web_task及data_acquisition专项 | 最终105 passed，21.20秒 |
| `python -m compileall scanner strategy2 strategy6 us_market server.py -q` | 退出码0 |
| `python -m us_market --help` | 退出码0 |
| `git diff --check` | 通过，提交前再次检查 |

全量回归完成后仅调整新US模块的免认证保护及新增测试；这些最终变动已运行22项/105项专项和编译，未重新执行第二次全量。
测试有一项第三方dateutil的utcfromtimestamp弃用警告，无测试失败。
没有修改前端，未安装新worktree前端依赖，也未运行前端测试/build；未验证尚未开发的US页面、任务和交易模型。

## 7. 剩余门禁及下一阶段

以下未通过前，不接入正式US扫描/候选/调度，也不启用交易收益回测：

1. 验证拆股、分红、反向拆股的价格基准及历史成交量股数口径。
2. 确认可用真实美股宽基指数及覆盖区间；不能用SPY等ETF悄悄代替真实指数。
3. 确认交易日历、时区、夏令时、半日交易及数据发布延迟。
4. 官方目录与供应商股票池交集、冲突审计及生产标的注册表。
5. US流动性/启动/评分画像，保持ORIGINAL尾部及CN全部行为不变。

用户已确认仅使用TickFlow免费端，缺失部分保持阻塞，不增加只读补充来源。
因此不尝试Key、不恢复yfinance生产源、不用缺失值伪造正常指标；上面的官方目录外网验证发生在该最终确认之前，后续不继续引入外部源。

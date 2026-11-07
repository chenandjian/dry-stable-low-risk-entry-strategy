# 美股策略6研究扫描开发与验收报告

## 1. 交付范围

分支：`codex/strategy6-us-market-adaptation`，在 `a45170b` 基础上继续实施。
本轮交付可运行的独立美股研究扫描，不是完整生产迁移，不把尚未实现的P1-P7全部标为完成。

用户本轮确认：

1. 仅使用TickFlow免费端，不使用Key或外部补充行情源。
2. 美股用forward，成交量保留供应商原值，不自行调整拆股倍数。
3. 未取得真实美股指数时，允许显式“未启用市场过滤”的研究扫描。
4. 不因正式数据验收未完成而暂停独立存储、任务、研究入口和页面开发。

## 2. 页面与使用方式

前端新增“美股研究”导航，路由 `/us/strategy6/research`。
需要运行本worktree的后端及前端；旧main上的服务不会自动获得本分支页面/API。本轮没有重启用户现有服务。

页面能力：

- 输入最多200只股票，保留BRK.B内部点号，输入独立记忆，不覆盖A股股票池。
- 请求500-3000根日线，默认1100，外层每批20只、SDK worker=2。
- 自动拉取后评估，或仅使用本地数据；可显式强制重新拉取。
- 可选择已经完成的历史评估日；留空使用最近完整美股交易日。
- 显示任务阶段、处理数量、当前批代码、失败原因及评估日期。
- 显示策略总分、ORIGINAL尾部分、量比、研究分层和排除原因。
- 可单独筛选研究命中、复制代码、重试失败股票；保留最近20个研究任务。
- 实际成交额与估算值分开；展示取数时间和量价口径警告。
- 切换任务防旧响应覆盖；刷新失败保留已取得结果；退出页面停止轮询。

CLI保留旧诊断模式，同时支持：

```powershell
python -m us_market AAPL MSFT NVDA --sync --count 1100
python -m us_market AAPL MSFT NVDA --scan --count 1100
python -m us_market AAPL MSFT NVDA --local-only --as-of 2026-11-05
```

以上为使用示例，不宣称每条均已按该字面命令执行。真实验证使用相同服务函数/API，记录见第6节。

## 3. 代码修改清单

| 文件 | 修改内容 |
| --- | --- |
| `us_market/calendar.py` | XNYS离线日历、纽约时区、DST、提前收盘、完整交易日、显式历史日期 |
| `us_market/service.py` | 批量获取、逐批入库、缓存、失败列表、研究编排和USD估算字段 |
| `us_market/repository.py` | 在原诊断库兼容增加US行情/任务表；事务更新行数据及元数据；内部计算数据哈希；任务列表SQL过滤 |
| `us_market/web_task.py` | 后台任务、阶段进度、互斥、失败重试、冻结日期和参数、重启标记中断 |
| `us_market/__main__.py` | sync/scan/local-only/force/batch-size/as-of入口 |
| `strategy6/engine.py` | 显式US研究画像；默认CN配置与哈希不变 |
| `strategy6/strong_start.py` | 仅US画像跳过A股涨停辅助函数及成交额分位要求，历史锚点也消费相同画像 |
| `server.py` | 独立US API；与CN手动扫描及定时扫描协调运行锁 |
| `web/src/pages/USStrategy6Research.vue` | 独立美股研究页 |
| `web/src/router/index.js`、`web/src/components/TopNav.vue` | 新导航；US页面不显示A股时钟标签 |
| `tests/test_us_market_pipeline.py`、`tests/test_us_market_web.py`、前端对应测试 | 日历、批量入库、失败、缓存、历史截断、引擎隔离、任务、API及交互验证 |
| `requirements.txt` | 固定exchange-calendars版本及旧Python生态的numpy兼容约束 |
| `CLAUDE.md`、原设计/计划 | 同步已确认的研究范围和剩余工作 |

未修改CN config.yaml、A股源客户端、价格/成交量单位、CN数据库schema、策略1-5或scheduler业务规则。

## 4. 数据和交易日语义

### 4.1 存储

US库与CN库分离；服务默认在CN库同目录使用 `us_market.db`，不调用 `scanner.db.init_db()` 切换全局路径。
诊断CLI原有快照继续可读。新行情以symbol+forward保存滚动完整窗口及元数据，不混入none或A股记录。
每只股票原子更新、逐批落盘后才请求下一批；新结果变短或最新日期倒退时保留旧数据并报告失败。
重新取数替换整个请求窗口，而非只追加尾部，以接收窗口内历史修正；窗口外历史并未实现完整公司行动重建。
单股量价数据SHA256由Repository重算，不信任调用方传入的旧摘要。

### 4.2 成交量和估算值

```text
volume = TickFlow返回的volume，不乘100，不自行调整拆股倍数
turnover_actual = 有效的供应商amount；0/缺失保留NULL
turnover_estimated_usd = forward_close × provider_volume
estimation_method = FORWARD_CLOSE_X_PROVIDER_VOLUME_V1
volume_basis = PROVIDER_UNVERIFIED
```

这是一项标记清楚的研究活动度估计，不是经核验的真实美元成交额或VWAP。
实际turnover字段不被估算值覆盖；核心计算桥接使用的amount单位在US结果注明 `1e8_USD_ESTIMATED`。
量干/VCP判断继续用volume，不用美元估算值冒充成交量。

### 4.3 日期、新鲜度和发布延迟

使用固定 `exchange-calendars==4.13.2` 的XNYS离线日历，纽约时区处理夏令时、节假日与半日市。
选择“收盘+10分钟”已完成交易时段，不声称TickFlow承诺10分钟后发布；输出仍标记发布时间未验收。
缓存必须包含目标日，并在该目标日收盘后获取；缺目标日必须失败，不自动推断停牌。
网络失败或缺目标日都不能回退到旧缓存生成当天结果。
用户明确选择历史as_of时，目标日与真实当前完整交易日同时保存，评估只读截至as_of的行。
不把now改成过去；未来日期或非交易日拒绝。修改评估日之后的K线不改变历史候选的测试已通过。

## 5. 策略画像与安全边界

`StrongVcpTailEngine()` 默认仍为CN；仅显式 `market_profile='US_RESEARCH_NO_INDEX'` 启用US研究。

- 只复用formal_original的ORIGINAL尾部，不启用BOX/Brooks研究旁路。
- 不调用A股涨停、一字板或炸板辅助函数；US limit_up_pct=0，相关标记为false。
- 普通强势启动保留现有涨幅、量比、收盘位置及后续质量要求；取消CNY绝对成交额/自成交额分位要求，不新增volume分位重复加分。
- 基线估算活动度门槛为10/30/60日均值各1000万美元；这是未调优的研究默认值，不是正式最优门槛。
- 不沿用A股“10日成交额至少30日80%”活动比，避免与尾部缩量冲突。
- 其他趋势、形态、支撑、风险收益和候选阈值未为增加数量而放宽。
- 市场过滤关闭且状态为UNAVAILABLE_US_RESEARCH；拒绝传入CN/代理指数，不补未知RS分，不将美股映射到上证指数。
- 参数哈希含US画像；CN默认字段和哈希不增加市场键，避免旧任务哈希漂移。
- US结果始终携带research_only、formal_scan_allowed=false、币种和口径提示，不写CN候选或生命周期。

API为：

```text
POST /api/us/strategy6/research
GET  /api/us/strategy6/tasks
GET  /api/us/strategy6/tasks/{task_id}
```

POST返回任务ID后在后台执行；用共享定时扫描锁及server运行状态防止与CN扫描重叠。
只有US Repository中的研究job可以通过US任务详情返回，CN任务ID在US API返回404。
失败重试只处理失败股票，沿用父任务参数和评估日；不会修改旧任务为成功。
服务重启后RUNNING任务标记INTERRUPTED，不偷偷恢复或宣称完成；当前未实现断点续跑，需手动新建任务。

## 6. 真实数据验证

全部行情网络请求只使用TickFlow免费端，无Key、无其他行情源。

### 6.1 当前完整交易日验证

北京2026-11-07早间，最近完整US交易日为2026-11-06。
对AAPL、MSFT、NVDA、BRK.B、AMZN、META、GOOGL、TSLA分两批请求1100根日线。

- 任务：`us-s6-fetch-4ef4b60122a14f6e809434c978eb34b3`
- 结果：8只均缺目标交易日，0成功、8失败；未回退缓存生成当天候选。
- 免费US指数目录再次返回[]。这是已查询目录的事实，不表示证明全部接口永远没有美股指数。

### 6.2 显式历史日期验证

明确选择as_of=2026-11-05后重新取数，仍使用真实当前时钟：

- 获取任务：`us-s6-fetch-c364d6f219c74c1083ce148cefe34146`，8成功、0失败。
- 研究任务：`us-s6-research-ecab834b2efe4202a9cfc91c33106742`，8评估成功、0失败、0命中。
- current完整交易日仍显示11月6日，历史评估显示11月5日。

| 股票 | 11月5日策略总分 | 研究结果 | 主要排除项 |
| --- | ---: | --- | --- |
| AAPL | 39 | 未通过 | NO_STRONG_START |
| MSFT | 29 | 未通过 | NO_STRONG_START |
| NVDA | 11 | 未通过 | 整理过长、趋势不达标、支撑失败、放量下跌、RR不足 |
| BRK.B | 31 | 未通过 | 距52周低点不足30%、无强势启动 |
| AMZN | 27 | 未通过 | NO_STRONG_START |
| META | 49 | 未通过 | 趋势/支撑失败、尾部新低和缩量未达标 |
| GOOGL | 36 | 未通过 | 趋势不达标、无强势启动 |
| TSLA | 24 | 未通过 | 趋势不达标、无强势启动 |

这不是收益回测，不代表全市场无机会，不据此放宽启动或风险规则。

### 6.3 真实本地数据API验证

通过TestClient请求POST创建仅用本地数据的后台job：
`us-s6-job-509a8c0c58794e508340a74661493190`。

POST/详情GET均200，任务COMPLETED，8只完成评估、0研究命中；任务结束后CN运行状态已清除。
Windows沙箱首次阻塞在asyncio socketpair初始化，终止该验证进程后在允许本地socket的环境复验通过，并非业务任务死锁。

## 7. 双角色审核与测试

开发前先增加失败测试，确认缺失模块/功能失败后实施。审核后补测与修复：

1. 历史选择不伪造now，保留live target并按as_of截断；增加未来K线扰动不改变候选的测试。
2. API共享锁的释放改为幂等，避免错误分支重复释放其他任务刚取得的锁。
3. 任务列表SQL直接过滤job并移除stocks，不将数百条历史任务全部载入内存再筛选。
4. 快照摘要由存储层重算，任务参数/评估日冻结；断点不被错误解释为成功。
5. 旧响应不覆盖新任务，轮询失败可刷新；初始输入与A股分别存储。
6. 存储启动失败时，原失败状态的再次写入也可能失败并遗留运行锁；已用失败测试复现并以finally确保释放任务及共享运行锁。

验证结果：

- 后端第一轮全量：1862 passed、9 skipped，254.82秒。
- 最终专项：138 passed，含US及策略6核心/涨停/VCP观察回归。
- 前端最终全量：28文件、208 passed。
- 前端生产构建：通过，新增页面独立懒加载chunk约8KB；既有echarts大chunk提示仍存在。
- 编译：`python -m compileall scanner strategy2 strategy6 us_market server.py -q` 通过。
- 第二轮后端全量复验：1863 passed、9 skipped，249.16秒。
- 第二轮全量之后新增“启动存储失败释放锁”测试与最小修复，最终138项专项已覆盖；未再次运行第三轮全量。
- `git diff --check`：通过，暂存后再检查。

依赖安装说明：原锁文件esbuild可选包0.28.1/0.28.2不一致，npm ci未通过；使用npm install --package-lock=false安装完成，未修改原锁文件。
安装日历库时pip初始选择numpy2.x，与既有scipy不兼容，已改用1.26.4；requirements对Python<3.13约束numpy<2。
既有dateutil弃用告警、Vite CJS和Node依赖engine提示仍保留，没有借机升级无关框架。

## 8. 剩余工作与风险

- 真实指数仍未找到，不使用ETF替代；本轮只有明确关闭过滤的研究画像。
- 拆股成交量、分红和美元估算基准未独立验收，研究分数/活动度不能冒充真实交易表现。
- 当前只支持显式代码池，不具备经过核查的美股全市场普通股股票池；证券类型/实际上市交易所仍需核查。
- 尚未接入US版批量评分全套筛选、VCP历史持续观察池、US市场宽度和自动调度。
- 没有收益回测、收益优化、自动交易或正式启用，不读取2026+OOS收益选参。
- 美国临时休市/供应商发布延迟可能超出固定日历与10分钟参数，缺数据必须继续报告失败。
- SDK免认证保护涉及私有客户端属性，升级不兼容时应失败而非带Key继续。
- 暂不支持多进程部署/跨进程运行锁；应使用单backend进程，CLI与服务不要同时修改同一研究库。
- A股原配置、数据及默认策略未改；本轮不合并main，不替换用户当前运行的服务。

# 策略6 Brooks 尾部路径真实本地数据验证报告

## 1. 报告状态

- 状态：`DONE`
- 研究标签：`RESEARCH_ONLY_CURRENT_UNIVERSE`
- 验证代码基线：`9533d30a4a1c7fe0ac72e4adf951811eae446916`
- 策略版本：`4.2.0`
- 配置哈希：`efe8d3b0b9ba183f5b53294b36f68d902eb26f96314bd1b1f4c71725c7016dde`
- 验证日期：`2026-07-14`
- 共同评估交易日：`2026-07-13`
- 全量评估耗时：`75.485` 秒
- 中、高等级业务违规：`0`

本报告在结构阶段、二次入场生命周期和 Brooks-only 分类修复提交 `9533d30` 上重新执行。未发现 Brooks 路径新增实现的中、高等级业务缺陷。发现 1 条历史非法 OHLC，属于本地数据质量残余风险；该记录未导致本轮评估异常，也不构成本报告的 Brooks 逻辑验收失败。

本报告只验证当前股票池、当前配置和当前评估日下的策略行为，不进行收益回测，不升级正式参数，也不宣称 Brooks 路径能够提高收益。

## 2. 验证边界

本次严格采用以下边界：

1. 数据库以 SQLite URI `mode=ro` 打开，并执行 `PRAGMA query_only=ON`。
2. 只读取 `data/cuphandle.db`，没有写入或迁移数据库。
3. 使用当前 `config.yaml`，并通过 `resolve_strategy6_config()` 解析完整 Strategy6 配置。
4. 使用 `StrongVcpTailEngine.evaluate_at()` 作为唯一策略入口。
5. 没有调用 `scan_strategy6_all`，没有调用任何行情接口，也没有联网。
6. 个股仅传入 `date <= 2026-07-13` 的日线，并按配置最多保留最近 1100 根。
7. 四个指数同样截断到 `2026-07-13`，再以 `market_data_by_symbol` 传入引擎。
8. 没有关闭市场过滤，没有覆盖阈值，没有升级参数。
9. 对所有非空 Brooks 结构日期逐字段检查其不早于 `phase.consolidation_start_date`。
10. 对所有 `brooks_trade_ready=true` 记录检查 `trigger_valid_until >= evaluation_date`。
11. 对所有 Brooks-only 且未 ready 的记录检查其候选类型不是 READY/KEY，生命周期不是 READY/BUY_ZONE。

当前关键配置：

| 配置 | 值 |
| --- | ---: |
| `minimum_trading_days` | 500 |
| `kline_days` | 1100 |
| `enable_market_filter` | true |
| `market_filter_mode` | downgrade |
| `brooks_tail.enabled` | true |

## 3. 数据覆盖

### 3.1 个股数据

| 项目 | 数量 |
| --- | ---: |
| `stock_pool` 股票总数 | 5,530 |
| 满足当日覆盖和最少历史要求 | 4,824 |
| 完成引擎评估 | 4,824 |
| 无任何本地 K 线 | 521 |
| 少于 500 个交易日 | 173 |
| 历史足够但最新 K 线早于评估日 | 12 |
| 评估异常 | 0 |

验证使用全量 4,824 只合格股票，没有降级为 1,000 只样本。未纳入的 706 只股票没有被伪装成评估成功，也没有使用旧 K 线代替评估日 K 线。

### 3.2 真实指数数据

| 指数代码 | 指数 | 行数 | 最早日期 | 最新日期 | 来源 |
| --- | --- | ---: | --- | --- | --- |
| `sh000001` | 上证指数 | 1,501 | 2020-05-06 | 2026-07-13 | sina |
| `sz399001` | 深证成指 | 1,501 | 2020-05-06 | 2026-07-13 | sina |
| `sz399006` | 创业板指 | 1,501 | 2020-05-06 | 2026-07-13 | sina |
| `sh000300` | 沪深300 | 1,501 | 2020-05-06 | 2026-07-13 | sina |

四个必需指数均覆盖共同评估日。沪深300以引擎支持的 `sh000300` 别名传入，RS20没有使用等权代理或未来数据。

## 4. 全量评估结果

### 4.1 候选类型

| `candidate_type` | 数量 |
| --- | ---: |
| `REJECTED` | 4,789 |
| `WATCH_CANDIDATE` | 35 |
| `KEY_CANDIDATE` | 0 |
| `READY_CANDIDATE` | 0 |

候选类型与尾部路径不是同一维度。`WATCH_CANDIDATE` 可以表示强启动后仍在形成、评分或盈亏比达到观察条件的记录，不等于 Brooks 已形成交易触发。

生命周期分布：

| `lifecycle_status` | 数量 |
| --- | ---: |
| `START_CONFIRMED` | 2,256 |
| `FAILED` | 2,286 |
| `SETUP_FORMING` | 167 |
| `BUY_ZONE` | 89 |
| `EXTENDED` | 21 |
| `READY` | 4 |
| `BREAKOUT_CONFIRMED` | 1 |

其中 READY/BUY_ZONE 是全策略路径的生命周期统计。本轮没有 Brooks-only 未 ready 记录，因此不存在 Brooks-only 借用旧 READY/BUY_ZONE 语义的情况。

### 4.2 旧 `tail_path` 分布

旧字段继续保持双路径枚举，没有出现 Brooks 新枚举污染：

| 旧 `tail_path` | 数量 |
| --- | ---: |
| `NONE` | 4,721 |
| `BOX` | 84 |
| `ORIGINAL` | 3 |
| `BOTH` | 16 |

### 4.3 权威 `tail_paths` 组合

| 权威路径组合 | 数量 |
| --- | ---: |
| `NONE` | 4,721 |
| `BOX` | 84 |
| `ORIGINAL` | 3 |
| `ORIGINAL + BOX` | 15 |
| `ORIGINAL + BOX + BROOKS` | 1 |
| `BROOKS` only | 0 |

按单路径通过标志统计：

| 路径 | 通过数 |
| --- | ---: |
| ORIGINAL | 19 |
| BOX | 100 |
| BROOKS | 1 |
| MULTI（至少两条路径） | 16 |

本评估日 Brooks 通过 1 只，但该股票也同时通过 ORIGINAL 和 BOX。因此：

- Brooks-only 结构增量：0
- Brooks-only 最终入池增量：0
- 多路径确认：16

这是单个评估日、当前股票池和当前正式阈值下的横截面结果，不能据此推导 Brooks 路径长期无增量，更不能据此调整阈值。

## 5. Brooks 结果审计

### 5.1 状态分布

| `brooks_status` | 数量 |
| --- | ---: |
| `BROOKS_FAILED` | 3,256 |
| `SUPPORT_BROKEN` | 877 |
| `BROOKS_CONTEXT_REJECT` | 630 |
| `FAILED_BEAR_BREAKOUT` | 36 |
| `COMPACT_BEARISH_REJECT` | 22 |
| `SECOND_ENTRY_LONG_READY` | 3 |

注意：`SECOND_ENTRY_LONG_READY` 是结构准备状态，不等于跨日交易触发已确认。本轮 `brooks_trade_ready` 为 0。

Brooks 汇总：

| 指标 | 数量 |
| --- | ---: |
| `brooks_tail_pass` | 1 |
| `brooks_tail_premium` | 1 |
| `brooks_trade_ready` | 0 |
| Brooks-only 结构通过 | 0 |
| Brooks-only 最终候选 | 0 |

与修复前同口径结果相比：

| 状态 | 修复前 | `9533d30` 后 | 变化 |
| --- | ---: | ---: | ---: |
| `BROOKS_FAILED` | 3,246 | 3,256 | +10 |
| `FAILED_BEAR_BREAKOUT` | 39 | 36 | -3 |
| `SECOND_ENTRY_LONG_READY` | 10 | 3 | -7 |
| `brooks_tail_pass` | 1 | 1 | 0 |

结构准备状态减少、失败状态增加，符合“结构只能来自当前整理阶段、二次入场低点需下一根 K 线确认”的修复方向。正式通过数量没有被额外放宽。

### 5.2 背景分布

| Brooks 背景 | 数量 |
| --- | ---: |
| `INVALID_CONTEXT` | 3,194 |
| `TRADING_RANGE_CONTEXT` | 802 |
| `BEAR_CONTEXT` | 727 |
| `BULL_CONTEXT` | 80 |
| `WEAK_BULL_CONTEXT` | 21 |

### 5.3 紧密结构分布

| 紧密结构 | 数量 |
| --- | ---: |
| `NO_COMPACT` | 4,760 |
| `COMPACT_BEARISH` | 34 |
| `COMPACT_NEUTRAL` | 30 |
| `BARB_WIRE` | 0 |

## 6. 不变量验证

| 不变量 | 违规数 | 结论 |
| --- | ---: | --- |
| Brooks-only 必须 `brooks_tail_pass=true` 且 ORIGINAL/BOX 均失败 | 0 | 通过 |
| B级启动不得 `brooks_trade_ready` | 0 | 通过 |
| `BARB_WIRE` 不得 `brooks_trade_ready` | 0 | 通过 |
| Brooks 失败不得抬高权威路径分数 | 0 | 通过 |
| Brooks 失败不得抬高最终 `tail_score` | 0 | 通过 |
| Brooks 结构日期早于 `phase.consolidation_start_date` | 0 | 通过 |
| `brooks_trade_ready` 已超过有效期 | 0 | 通过（本轮 ready 样本为 0） |
| Brooks-only 未 ready 却输出 READY/KEY 候选 | 0 | 通过（本轮该类样本为 0） |
| Brooks-only 未 ready 却输出 READY/BUY_ZONE 生命周期 | 0 | 通过（本轮该类样本为 0） |
| 个股评估异常 | 0 | 通过 |

Brooks 失败分数验证的比较口径：

1. ORIGINAL 或 BOX 至少一条通过时，只取已通过旧路径分数的最大值。
2. 两条旧路径均未通过时，保留开发前的 ORIGINAL 诊断分数。
3. 将上述期望值与 `tail_paths.score` 及 `score.tail_score` 比较。
4. 4,823 条 Brooks 未通过记录中，分数抬高违规为 0。

新增生命周期核对明细：

| 核对项目 | 样本量 | 违规数 |
| --- | ---: | ---: |
| 包含结构日期的股票 | 1,303 | 0 |
| 非空 Brooks 结构日期字段 | 3,187 | 0 |
| `brooks_trade_ready=true` | 0 | 0 |
| Brooks-only 且未 ready | 0 | 0 |

结构日期检查覆盖以下字段：`first_recent_low_date`、`second_recent_low_date`、`second_entry_signal_date`、`failed_bear_breakout_date`、`reclaim_date`、`bear_follow_through_failed_date`。所有 3,187 个非空日期均满足 `date >= phase.consolidation_start_date`。

本轮没有真实 ready 或 Brooks-only waiting 样本，因此有效期与分类两项只能证明当前横截面没有违规，不能替代相应专项测试对正、反样本的覆盖。

## 7. OHLC 与异常检查

数据库全量和本次传入引擎的窗口内均检测到 1 条非法 OHLC：

| 股票 | 日期 | 开盘 | 最高 | 最低 | 收盘 |
| --- | --- | ---: | ---: | ---: | ---: |
| `688089` | 2024-11-06 | 0.0 | 0.0 | 0.0 | 20.92 |

该记录位于历史窗口内，但距离本轮评估日较远，没有造成引擎异常。本报告不修改数据。后续应由个股数据诊断和重拉流程修复，不能在 Brooks 逻辑中静默篡改历史价格。

风险等级判断：低。理由是本轮当前日期计算未出现异常，且 Brooks 验收不依赖该单条远期历史记录；但它仍属于需要清理的数据质量问题。

## 8. 执行命令与方法

工作目录：

```text
D:\game\claude\dry-stable-low-risk-entry-strategy\.claude\worktrees\strategy6-strong-vcp-tail
```

数据库覆盖查询使用只读连接：

```powershell
@'
import sqlite3
from pathlib import Path
p = Path('data/cuphandle.db').resolve()
con = sqlite3.connect(f'file:{p.as_posix()}?mode=ro', uri=True)
con.execute('PRAGMA query_only=ON')
# 查询 stock_pool、daily_ohlc 和 market_index_ohlc 覆盖
'@ | python -
```

全量验证使用相同只读连接，核心调用等价于：

```python
raw_config = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
config = resolve_strategy6_config(raw_config)
engine = StrongVcpTailEngine(raw_config)

evaluation_date = min(required_index_latest_dates)
market_visible = {
    symbol: [row for row in rows if row["date"] <= evaluation_date]
    for symbol, rows in market_data_by_symbol.items()
}

for code in eligible_codes:
    rows = load_last_1100_rows(code, end_date=evaluation_date)
    result = engine.evaluate_at(
        rows,
        code=code,
        name=name,
        data_source="local_db_read_only",
        market_data_by_symbol=market_visible,
    )
```

全量验证进度与结果：

```text
PROGRESS 500/4824 elapsed=8.2s
PROGRESS 1000/4824 elapsed=15.8s
PROGRESS 2000/4824 elapsed=30.1s
PROGRESS 3000/4824 elapsed=44.4s
PROGRESS 4000/4824 elapsed=59.6s
PROGRESS 4500/4824 elapsed=67.4s
completed=4824 exceptions=0 elapsed=75.485s
```

## 9. 结论与限制

### 9.1 验收结论

1. Brooks 第三路径已在真实本地个股和真实指数数据上完成全量横截面评估。
2. 旧 `tail_path` 继续保持 ORIGINAL/BOX/BOTH/NONE 双路径兼容语义。
3. 权威 `tail_paths` 能表示三路径组合，本轮出现 1 条三路径同时通过记录。
4. 1,303 只股票的 3,187 个 Brooks 结构日期全部位于当前整理阶段之内。
5. 4,824 只股票全部完成引擎调用，评估异常为 0。
6. Brooks-only 归因、B级权限、铁丝网权限和失败路径计分均未发现违规。
7. 当前评估日没有 Brooks-only 增量候选，也没有 Brooks 交易触发确认；这是数据结果，不是收益结论。
8. 配置哈希与修复前一致，`9533d30` 没有通过配置变化改变验证口径。

### 9.2 限制

1. 当前股票池存在幸存者偏差，结论仅限 `RESEARCH_ONLY_CURRENT_UNIVERSE`。
2. 本次是单评估日横截面验证，不覆盖跨日期发生频率、成交、收益、回撤和盈亏比。
3. `brooks_trade_ready=0` 时无法用本轮真实横截面直接验证 ready 有效期的正样本，只能确认没有过期 ready 违规。
4. 当前评估日没有 `BARB_WIRE` 样本；铁丝网不交易主要由专项单元测试覆盖，本轮只确认零误触发。
5. 当前评估日没有 Brooks-only waiting 样本，其不得输出 READY/KEY/BUY_ZONE 的正、反例仍主要由专项测试覆盖。
6. 本次没有执行网络数据源、扫描任务持久化、前端人工操作或正式参数调优。
7. `688089` 的 1 条非法历史 OHLC 需要通过独立数据修复流程处理。

最终结论：当前 Brooks 实现通过本阶段真实本地数据验收，可以进入任务10完整回归和最终双角色审查；本报告不建议也不执行正式参数升级。

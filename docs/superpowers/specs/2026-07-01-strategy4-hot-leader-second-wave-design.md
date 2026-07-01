# 开发方案文档：策略4「热点龙头二波」

## 1. 需求背景

### 1.1 当前问题

项目当前已有策略1、策略2，以及策略3设计文档：

- 策略1：杯柄/VCP结构扫描，偏标准形态。
- 策略2：极致量干价稳，偏低波动、低风险、缩量稳定。
- 策略3：强势回踩二次启动，偏个股趋势延续和健康回踩。

这些策略都不是为“当前市场最热主线、最强龙头、第一波大涨后的二波参与”专门设计的。

用户当前的核心诉求不是保守避险，而是：

> 近期热点我要参与进去。候选少没关系，但最热行业/题材和最强龙头一定要尽量捕捉到。

因此需要新增策略4「热点龙头二波」，从产品和架构上独立于策略1/2/3，先用最激进的方式识别市场主线热点和龙头股票，再判断第一波大涨后的健康回踩与二次启动机会。

### 1.2 用户痛点

- 只从个股形态出发，容易选到“形态像但不在主线”的噪音。
- 只看低风险，容易错过真正的热门题材和核心龙头。
- A股涨停制度会导致最强股票成交额变小，机械用成交额过滤会误杀一字板、缩量板、连板龙头。
- 创业板、科创板、北交所、ST、新股涨跌幅规则不同，不能统一按10%涨停判断。
- 用户需要看到的不只是“可以买的候选股”，还要看到“当前最热题材、核心龙头、锁仓观察、暂无买点”的市场结构。

### 1.3 业务目标

策略4的目标是：

1. 捕捉近期最热行业/题材。
2. 捕捉每个热点里的最强龙头股票。
3. 在龙头池中识别第一波大涨后的健康回踩。
4. 在健康回踩后识别二次启动机会。
5. 不因当日涨停成交额偏低误判为市场关注度不足。
6. 不因风险比偏大过早杀掉主线龙头，但必须保留收益比判断。
7. 输出热点题材榜、龙头股票榜、二波候选榜、锁仓观察榜。

### 1.4 预期效果

用户启动策略4扫描后，系统先拉取行业/题材指数、资金流和板块摘要数据，形成热点题材池；再结合板块领涨股、全市场涨幅/成交额/涨停强度，形成龙头候选池；最后对龙头候选执行第一波、回踩、二波、收益比判断。

最终页面应清楚展示：

- 当前最热行业/题材是什么。
- 每个热点的强信号来自哪里。
- 龙头股票是谁。
- 龙头当前是可参与二波、锁仓观察、暂无买点，还是噪音剔除。
- 候选股票为什么入选，为什么不是普通后排股。

---

## 2. 需求目标

### 2.1 必须实现

- 新增策略4独立配置段 `strategy4`。
- 新增策略4独立目录 `strategy4/`。
- 新增策略4核心模型、热点题材评分、龙头识别、涨停制度识别、二波判断、扫描编排。
- 新增 `scan_tasks.strategy_type` 取值 `STRATEGY_4_HOT_LEADER_SECOND_WAVE`。
- 策略4不得调用策略1/策略2/策略3的策略判断入口。
- 策略4允许复用股票池、日线数据服务、数据库基础能力、扫描任务追踪、全局扫描互斥。
- 新增行业/题材数据源适配层，优先使用 AkShare 同花顺行业/概念接口。
- 新增热点题材快照表、热点龙头快照表、策略4候选表。
- 新增策略4扫描启动、状态、任务列表、热点题材、龙头列表、候选列表、候选详情 API。
- 前端扫描控制台新增策略4入口。
- 前端新增策略4结果页。
- 前端策略配置页新增策略4配置分区。
- 策略4候选不得写入策略1 `candidates`，不得写入策略2 `strategy2_candidates`，不得写入策略3未来候选表。
- 策略4必须保存热点/龙头/二波判断快照，保证扫描结果可追溯。
- 补充单元测试、接口测试、集成测试和前端测试。

### 2.2 可选增强

- 策略4历史回测。
- 策略4与策略1/2/3候选横向对比。
- 热点题材趋势图。
- 龙头股票与板块指数强弱对比图。
- 导出 CSV。
- 板块成分股本地长期缓存和增量更新。

### 2.3 不做范围

- 不修改策略1、策略2、策略3的核心规则。
- 不把策略4结果混入策略1/2/3结果页。
- 不做自动交易。
- 不做融资融券、融券余额、龙虎榜席位模型。
- 不做机器学习预测。
- 不以低风险为第一目标。
- 不因为候选数量少而放宽非热点、非龙头股票。
- 首期不强制实现完整历史回测；历史回测作为 Phase 2 单独开发。

---

## 3. 默认假设

1. 当前项目已存在 `stock_pool`、`daily_ohlc`、`scan_tasks`、`task_stocks` 和多源日线拉取能力。
2. 当前项目默认排除 ST 和北交所；策略4仍应实现交易规则识别，避免未来配置打开后误判。
3. AkShare 行业/概念接口稳定性不能假设，必须有多接口尝试、本地快照缓存和失败降级。
4. 当前验证中，同花顺行业/概念名称、指数日线、行业资金流、概念资金流可用；东财板块接口可能失败。
5. 策略4首期以“捕捉主线热点与龙头”为第一目标，风险控制只作为收益比和交易状态解释，不作为过早一票否决。
6. 当日成交额是市场关注度的重要指标，但涨停、连板、一字板、缩量封板时，成交额偏低可能代表筹码锁定，而不是无人关注。
7. 涨停判断必须按股票所属板块、ST状态、新股阶段和涨跌幅制度动态计算，不允许统一硬编码10%。
8. 候选少是可接受结果；漏掉真正主线热点和真正龙头是不可接受风险。

---

## 4. 产品设计方案

### 4.1 用户使用流程

1. 用户打开扫描控制台。
2. 用户点击“启动策略4：热点龙头二波”。
3. 后端创建策略4扫描任务。
4. 系统拉取或读取行业/题材数据，生成热点题材池。
5. 系统从热点题材中识别核心龙头、备选龙头和锁仓龙头。
6. 系统只对龙头池执行第一波、健康回踩、二次启动、收益比判断。
7. 前端展示任务进度。
8. 扫描完成后展示热点题材榜、龙头股票榜、二波候选榜、锁仓观察榜。
9. 用户点击题材或股票，可查看入选依据、噪音剔除原因、交易状态和关键价格。

### 4.2 页面展示要求

策略4结果页建议分为四个区域。

#### 热点题材榜

字段：

- 题材/行业名称。
- 类型：行业 / 概念 / 申万行业。
- 热度分 `hot_topic_score`。
- 涨幅强度分。
- 成交额强度分。
- 资金流强度分。
- 上涨家数扩散分。
- 龙头涨停/连板分。
- 突破/加速分。
- 热点状态：`CONFIRMED_HOT` / `LOCKED_HOT_TOPIC` / `WATCH_HOT` / `NOISE_TOPIC`。
- 命中的强信号数量。
- 领涨股。
- 数据源。
- 快照时间。

#### 龙头股票榜

字段：

- 股票代码、名称。
- 所属热点题材。
- 龙头类型：空间龙头 / 容量龙头 / 先锋龙头 / 中军龙头 / 情绪龙头。
- 龙头强度分 `leader_strength_score`。
- 可交易性分 `tradability_score`。
- 涨停制度类型：10cm / 20cm / 30cm / ST 5cm / 无涨跌幅阶段。
- 涨停形态：一字板 / T字板 / 收盘涨停 / 接近涨停 / 炸板 / 非涨停。
- 近5日、10日、20日涨幅。
- 近5日、10日平均成交额。
- 第一波最大成交额。
- 最近一次非涨停日成交额。
- 连板数。
- 板块内相对强度。

#### 二波候选榜

字段：

- 股票代码、名称。
- 所属热点。
- 总分 `strategy4_score`。
- 交易状态：`BUYABLE_SECOND_WAVE`。
- 第一波涨幅。
- 回踩幅度。
- 回踩天数。
- 回踩成交量变化。
- 二次启动信号。
- 当前价、支撑位、止损、目标位。
- 预期收益比 `reward_risk_ratio`。
- 入选原因。

#### 锁仓观察榜

字段：

- 股票代码、名称。
- 所属热点。
- 锁仓类型：一字板 / 缩量涨停 / 连板锁仓。
- 龙头强度。
- 可交易性。
- 为什么不能当作成交额不足排除。
- 等待条件：开板换手 / 健康回踩 / 二次启动。

### 4.3 交互规则

- 任一策略扫描运行中，策略4启动按钮应遵守全局扫描互斥。
- 策略4任务结果必须以 URL `?task=` 为上下文。
- 页面刷新后应恢复策略4历史任务结果。
- 如果行业/题材数据源失败，应展示数据源失败原因，不得静默返回空热点。
- 如果只有热点题材但没有可交易二波候选，也要展示热点和龙头观察，不应显示“无结果”。
- 点击热点题材可查看该题材的强信号、噪音判断和龙头列表。
- 点击龙头股票可查看第一波、回踩、涨停制度、锁仓关注度和收益比。

---

## 5. 技术架构方案

### 5.1 总体架构

新增目录：

```text
strategy4/
```

建议模块：

- `strategy4/models.py`：数据模型。
- `strategy4/config.py`：配置解析和校验。
- `strategy4/topic_source.py`：行业/题材数据源。
- `strategy4/topic_scoring.py`：热点题材评分。
- `strategy4/price_limit.py`：A股涨跌幅制度识别。
- `strategy4/leader.py`：龙头候选召回和评分。
- `strategy4/first_wave.py`：第一波大涨确认。
- `strategy4/pullback.py`：健康回踩判断。
- `strategy4/second_wave.py`：二次启动判断。
- `strategy4/risk_reward.py`：收益比计算。
- `strategy4/engine.py`：策略4唯一判断入口。
- `strategy4/scanner.py`：全市场扫描编排。

允许复用：

- `scanner/stock_pool.py`
- `scanner/daily_data_service.py`
- `scanner/db.py`
- 共享日志、配置读取、扫描任务框架。

禁止导入：

- `scanner/strategy_engine.py` 的策略1判断。
- `strategy2/engine.py` 的策略2判断。
- 未来 `strategy3/engine.py` 的策略3判断。
- `analyzer.*` 的策略1分析模块。

### 5.2 数据流设计

1. 前端发起策略4扫描请求。
2. 后端创建 `scan_tasks`，`strategy_type=STRATEGY_4_HOT_LEADER_SECOND_WAVE`。
3. `TopicSourceService` 拉取行业/概念名称、指数日线、资金流、板块摘要。
4. `HotTopicScorer` 生成热点题材榜和噪音剔除原因。
5. `LeaderDiscoveryService` 使用强召回生成龙头候选池。
6. `PriceLimitResolver` 为每只股票计算涨跌幅制度和涨停形态。
7. 后端拉取或读取龙头股票日线。
8. `Strategy4Engine.evaluate_at()` 执行第一波、回踩、二波、收益比判断。
9. 保存热点快照、龙头快照、候选结果和逐股状态。
10. 前端轮询任务状态。
11. 扫描完成后前端展示四个榜单。

### 5.3 状态设计

策略4候选状态：

| 状态 | 含义 | 是否进入二波候选榜 |
|---|---|---|
| `BUYABLE_SECOND_WAVE` | 热点、龙头、第一波、回踩、二波均成立 | 是 |
| `LOCKED_LEADER_WATCH` | 龙头成立，但一字板/缩量板/连板锁仓，当前不适合追 | 否，进入锁仓观察 |
| `HOT_TOPIC_NO_BUY_POINT` | 热点和龙头成立，但暂无健康回踩或二波启动 | 否，进入龙头观察 |
| `TOPIC_ONLY` | 热点成立，但龙头数据不足或未形成可确认龙头 | 否 |
| `NOISE_TOPIC` | 题材信号不足或疑似噪音 | 否 |
| `REJECTED` | 个股不满足龙头或二波规则 | 否 |
| `INSUFFICIENT_DATA` | 数据不足 | 否 |
| `DATA_SOURCE_FAILED` | 数据源失败 | 否 |

任务状态沿用现有扫描任务：

- `running`
- `completed`
- `failed`
- `cancelled`

---

## 6. 核心策略规则

### 6.1 总体原则

策略4的判断顺序固定为：

```text
最热行业/题材
  -> 最强龙头股票
    -> 第一波大涨确认
      -> 健康回踩
        -> 二次启动
          -> 收益比排序
```

不得反过来从全市场直接找二波形态。

### 6.2 热点题材强召回

先用多个激进榜单召回热点题材：

- 当日涨幅 Top N。
- 3日涨幅 Top N。
- 5日涨幅 Top N。
- 10日涨幅 Top N。
- 成交额 Top N。
- 成交额放大倍数 Top N。
- 净流入 Top N。
- 上涨家数占比 Top N。
- 领涨股涨幅 Top N。
- 板块指数突破 / 新高 / 加速 Top N。

只要命中任一强榜单，即进入热点观察池。这样避免刚启动的主线因5日/10日排名尚未充分体现而被漏掉。

### 6.3 热点题材强确认

热点题材确认分满分100：

| 模块 | 分值 |
|---|---:|
| 涨幅强度 | 30 |
| 成交额强度 | 20 |
| 资金流强度 | 15 |
| 上涨家数扩散 | 15 |
| 龙头涨停/连板强度 | 10 |
| 板块指数突破/加速 | 10 |

默认入选条件：

```yaml
min_hot_topic_score: 85
min_hot_topic_signal_count: 2
hot_topic_top_n: 8
watch_hot_topic_top_n: 15
```

强信号例外：

- 当日涨幅排名前3，且成交额或净流入排名前10。
- 领涨股涨停/20cm涨停/连板，且板块上涨家数占比超过70%。
- 板块指数创20日新高，且成交额放大超过1.5倍。

命中强信号例外时，即使综合分略低，也进入热点观察池，但状态为 `WATCH_HOT`，不能直接进入二波候选。

### 6.4 噪音题材剔除

以下情况标记为 `NOISE_TOPIC`：

- 只有单日涨幅，3日/5日完全不强。
- 板块涨幅靠前，但成交额过低且没有涨停锁仓解释。
- 只有1只股票上涨，板块没有扩散。
- 净流入弱或为负，同时成交额没有明显放大。
- 板块指数长上影冲高回落严重。
- 领涨股极端高潮，但板块跟不上。
- 概念名称热门，但指数、资金和扩散度都不热。

### 6.5 涨停锁仓修正

成交额是市场关注度的重要指标，但涨停制度会让最强股票成交受限。

策略4必须识别：

```text
LOCKED_ATTENTION
```

如果题材内核心股票出现一字板、缩量板、连续涨停，且板块扩散度较强，则不得因为当日成交额偏低排除热点。

成交额修正规则：

- 非涨停日：使用当日成交额、近5日/10日平均成交额、成交额放大倍数。
- 涨停日：不强制要求当日成交额高，改看最近一次非涨停日成交额、第一波启动日最大成交额、近10日平均成交额、连板数、板块扩散度。

### 6.6 A股交易制度识别

新增 `PriceLimitResolver`，统一识别每只股票在评估日的涨跌幅制度。

默认规则：

| 股票类型 | 默认涨跌幅 | 说明 |
|---|---:|---|
| 沪深主板普通股 | 10% | 普通10cm |
| 创业板 `300/301` | 20% | 20cm |
| 科创板 `688` | 20% | 20cm |
| 北交所 `8/4` | 30% | 当前默认排除，但模块必须支持 |
| ST / *ST | 5% | 当前默认排除，但模块必须支持 |
| 新股/次新无涨跌幅阶段 | None | 不按普通涨停判断 |

注意：

- 涨停判断必须允许价格四舍五入和复权误差，使用容差。
- 不允许全市场统一硬编码10%。
- 如果无法确定涨跌幅制度，返回 `UNKNOWN_PRICE_LIMIT_RULE`，不得强行按10%判断。

涨停形态：

| 类型 | 含义 |
|---|---|
| `LIMIT_UP_CLOSE` | 收盘涨停 |
| `NEAR_LIMIT_UP` | 接近涨停 |
| `ONE_WORD_LIMIT_UP` | 一字板 |
| `T_LIMIT_UP` | T字板或开板回封 |
| `BROKEN_LIMIT_UP` | 炸板 |
| `NO_PRICE_LIMIT_DAY` | 无涨跌幅限制日 |
| `NOT_LIMIT_UP` | 非涨停 |

### 6.7 龙头候选强召回

每个热点题材必须召回多个龙头来源：

1. AkShare 板块资金流/摘要中的领涨股。
2. 板块成分股接口可用时，取成分股内涨幅、成交额、涨停强度排名靠前股票。
3. 全市场近1日、3日、5日、10日涨幅 Top 股票。
4. 全市场成交额 Top 股票。
5. 全市场涨停/接近涨停/连板股票。
6. 本地 `stock_pool` 与 `daily_ohlc` 中能够匹配热点名称或已有板块映射的股票。

如果板块成分股接口失败，不能直接放弃热点；至少保留资金流/摘要中的领涨股，并记录 `membership_source=partial`。

### 6.8 龙头识别评分

龙头评分拆成两个分数：

```text
leader_strength_score
tradability_score
```

`leader_strength_score` 满分100：

| 模块 | 分值 |
|---|---:|
| 板块内涨幅排名 | 25 |
| 成交额/容量排名 | 20 |
| 启动领先性 | 15 |
| 涨停/连板/强阳强度 | 20 |
| 相对板块强度 | 10 |
| 市场辨识度来源 | 10 |

`tradability_score` 满分100：

| 模块 | 分值 |
|---|---:|
| 非一字、可成交 | 30 |
| 换手充分但不过度 | 20 |
| 当前不是极端高潮 | 20 |
| 回踩后有买点 | 20 |
| 波动可执行 | 10 |

龙头类型：

- `SPACE_LEADER`：空间龙头，涨幅最大。
- `VOLUME_LEADER`：容量龙头，成交额最大，资金承载强。
- `PIONEER_LEADER`：先锋龙头，最早启动。
- `CORE_LARGE_LEADER`：中军龙头，市值/成交额较大且趋势稳。
- `SENTIMENT_LEADER`：情绪龙头，涨停/连板辨识度强。

默认每个热点最多保留：

```yaml
core_leaders_per_topic: 1
backup_leaders_per_topic: 2
max_total_leaders_per_topic: 3
min_leader_strength_score: 88
core_leader_strength_score: 93
```

### 6.9 第一波大涨确认

只在热点龙头池中执行。

默认条件：

```yaml
first_wave_lookback_short: 10
first_wave_lookback_long: 20
min_first_wave_return_10d: 0.25
min_first_wave_return_20d: 0.35
min_strong_day_count_10d: 2
```

强信号：

- 10日涨幅 >= 25%。
- 或20日涨幅 >= 35%。
- 或近10日内至少2个强势日：涨停、接近涨停、大阳线、20cm强阳。
- 或板块龙头涨幅明显高于板块指数。

### 6.10 健康回踩

健康回踩是策略4的核心买点前置条件。

默认条件：

```yaml
pullback_min_pct: 0.08
pullback_max_pct: 0.25
pullback_min_days: 2
pullback_max_days: 8
```

要求：

- 从第一波高点回撤8%-25%。
- 回踩持续2-8个交易日。
- 回踩期间没有连续放量大阴线。
- 回踩没有跌破第一波关键启动位。
- 成交量相对第一波明显收缩。
- 回踩时个股仍强于板块指数或大盘。

允许更激进的核心龙头例外：

- 核心龙头可接受回撤不足8%，但必须标记为 `AGGRESSIVE_SHALLOW_PULLBACK`，进入观察，不直接视为标准二波。

### 6.11 二次启动确认

默认信号：

- 收盘重新站上MA5或MA10。
- 当日阳线或长下影修复。
- 成交量温和放大，但不能爆量出货。
- 股价距离前高仍有空间。
- 板块指数同步转强。
- 个股强于板块平均表现。

排除：

- 回踩仍在下跌中。
- 当日大幅冲高回落。
- 放量大阴后弱反抽。
- 已经重新接近前高但收益比不足。

### 6.12 收益比优先于低风险

策略4不以低风险为第一目标，但必须要求收益比健康。

默认参数：

```yaml
max_risk_ratio: 0.15
aggressive_max_risk_ratio: 0.20
min_reward_risk_ratio: 2.0
core_leader_min_reward_risk_ratio: 1.8
```

规则：

- 非核心龙头：`reward_risk_ratio >= 2.0`。
- 核心龙头：可放宽到 `1.8`。
- 如果收益比不足，即使热点和龙头成立，也只能进入 `HOT_TOPIC_NO_BUY_POINT`。
- 风险比超过20%不进入可交易二波候选。

---

## 7. 数据库设计方案

### 7.1 新增表：策略4热点题材快照

```sql
CREATE TABLE IF NOT EXISTS strategy4_hot_topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    topic_id TEXT NOT NULL,
    topic_name TEXT NOT NULL,
    topic_type TEXT NOT NULL,
    source TEXT NOT NULL,
    snapshot_time TEXT NOT NULL,
    status TEXT NOT NULL,
    hot_topic_score REAL NOT NULL,
    price_strength_score REAL DEFAULT 0,
    amount_strength_score REAL DEFAULT 0,
    fund_flow_score REAL DEFAULT 0,
    breadth_score REAL DEFAULT 0,
    leader_limit_score REAL DEFAULT 0,
    breakout_score REAL DEFAULT 0,
    signal_count INTEGER DEFAULT 0,
    noise_reason TEXT,
    leading_stock_code TEXT,
    leading_stock_name TEXT,
    raw_snapshot TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### 7.2 新增表：策略4龙头快照

```sql
CREATE TABLE IF NOT EXISTS strategy4_leaders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    topic_id TEXT NOT NULL,
    topic_name TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    leader_type TEXT NOT NULL,
    leader_strength_score REAL NOT NULL,
    tradability_score REAL NOT NULL,
    price_limit_rule TEXT,
    limit_shape TEXT,
    limit_pct REAL,
    return_1d REAL,
    return_5d REAL,
    return_10d REAL,
    return_20d REAL,
    amount_1d REAL,
    avg_amount_5d REAL,
    avg_amount_10d REAL,
    first_wave_max_amount REAL,
    last_non_limit_amount REAL,
    consecutive_limit_count INTEGER DEFAULT 0,
    relative_strength_vs_topic REAL,
    membership_source TEXT,
    status TEXT NOT NULL,
    raw_snapshot TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### 7.3 新增表：策略4候选

```sql
CREATE TABLE IF NOT EXISTS strategy4_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    topic_id TEXT NOT NULL,
    topic_name TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    evaluation_date TEXT NOT NULL,
    status TEXT NOT NULL,
    strategy4_score REAL NOT NULL,
    hot_topic_score REAL NOT NULL,
    leader_strength_score REAL NOT NULL,
    tradability_score REAL NOT NULL,
    first_wave_score REAL DEFAULT 0,
    pullback_score REAL DEFAULT 0,
    second_wave_score REAL DEFAULT 0,
    reward_risk_score REAL DEFAULT 0,
    leader_type TEXT,
    price_limit_rule TEXT,
    limit_shape TEXT,
    first_wave_return REAL,
    pullback_pct REAL,
    pullback_days INTEGER,
    current_close REAL,
    support_price REAL,
    stop_loss REAL,
    target_price REAL,
    risk_ratio REAL,
    reward_risk_ratio REAL,
    entry_note TEXT,
    reject_reason TEXT,
    evaluation_snapshot TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### 7.4 索引设计

```sql
CREATE INDEX IF NOT EXISTS idx_strategy4_hot_topics_task ON strategy4_hot_topics(task_id);
CREATE INDEX IF NOT EXISTS idx_strategy4_hot_topics_score ON strategy4_hot_topics(task_id, hot_topic_score);
CREATE INDEX IF NOT EXISTS idx_strategy4_leaders_task ON strategy4_leaders(task_id);
CREATE INDEX IF NOT EXISTS idx_strategy4_leaders_code ON strategy4_leaders(code);
CREATE INDEX IF NOT EXISTS idx_strategy4_candidates_task ON strategy4_candidates(task_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_strategy4_candidates_task_code_topic
ON strategy4_candidates(task_id, code, topic_id);
```

### 7.5 数据兼容方案

- 所有新增表使用 `CREATE TABLE IF NOT EXISTS`。
- 新增 `scan_tasks.strategy_type` 取值不得破坏旧任务。
- 旧任务 `strategy_type=NULL` 仍按策略1解释。
- 兼容迁移必须使用 `_ensure_column()` 风格，不做破坏性 schema 变更。

---

## 8. 接口设计方案

### 8.1 新增接口

#### 启动策略4扫描

```http
POST /api/strategy4/scans
```

请求：

```json
{
  "forceRefreshTopics": true,
  "forceRefreshDaily": true
}
```

返回：

```json
{
  "ok": true,
  "taskId": "s4-20260701-103000",
  "status": "running",
  "strategyType": "STRATEGY_4_HOT_LEADER_SECOND_WAVE"
}
```

#### 查询策略4扫描状态

```http
GET /api/strategy4/scans/status
```

#### 查询策略4任务列表

```http
GET /api/strategy4/tasks
```

#### 查询热点题材榜

```http
GET /api/strategy4/tasks/{taskId}/topics
```

#### 查询龙头股票榜

```http
GET /api/strategy4/tasks/{taskId}/leaders
```

#### 查询二波候选

```http
GET /api/strategy4/tasks/{taskId}/candidates
```

#### 查询候选详情

```http
GET /api/strategy4/tasks/{taskId}/candidates/{code}
```

### 8.2 接口兼容要求

- 策略4接口必须校验任务类型。
- 策略1/2/3任务 ID 访问策略4接口应返回 `TASK_STRATEGY_MISMATCH`。
- 策略4任务不得出现在策略1/2候选接口中。
- 前端历史任务上下文以 URL `?task=` 为准。

---

## 9. 可以实施的代码方案

### 9.1 后端代码方案

#### 需要新增的模块

```text
strategy4/models.py
strategy4/config.py
strategy4/topic_source.py
strategy4/topic_scoring.py
strategy4/price_limit.py
strategy4/leader.py
strategy4/first_wave.py
strategy4/pullback.py
strategy4/second_wave.py
strategy4/risk_reward.py
strategy4/engine.py
strategy4/scanner.py
```

#### 核心逻辑

```text
Strategy4Scanner.scan_all()
1. 创建扫描任务。
2. 拉取行业/概念数据。
3. 生成热点题材池。
4. 剔除噪音题材，但保留锁仓热点。
5. 为热点题材召回龙头股票。
6. 对龙头股票拉取日线。
7. 调用 Strategy4Engine.evaluate_at()。
8. 保存热点、龙头、候选和逐股审计。
9. 汇总任务结果。
```

```text
Strategy4Engine.evaluate_at()
1. 读取已确认热点上下文。
2. 读取龙头上下文。
3. 计算涨跌幅制度和涨停形态。
4. 判断第一波大涨。
5. 判断健康回踩。
6. 判断二次启动。
7. 计算收益比。
8. 返回 BUYABLE_SECOND_WAVE / LOCKED_LEADER_WATCH / HOT_TOPIC_NO_BUY_POINT / REJECTED。
```

#### 并发控制

- 复用现有全局扫描互斥，同一时间只允许一个全市场扫描任务运行。
- AkShare 行业/题材接口应串行或低并发调用，避免触发限流。
- 日线拉取复用 `daily_data_service` 的数据源锁。
- 题材数据快照写入应在任务级事务中保证一致。

#### 缓存策略

热点题材数据缓存：

```text
cache_key = strategy4:topics:{source}:{trade_date}
ttl = 15 minutes during trading hours
ttl = 1 day after market close
```

板块指数日线缓存：

```text
cache_key = strategy4:topic_index:{source}:{topic_name}:{start}:{end}
ttl = 1 day
```

板块成分股缓存：

```text
cache_key = strategy4:topic_members:{source}:{topic_name}
ttl = 7 days
```

必须绕过缓存：

- 用户传入 `forceRefreshTopics=true`。
- 缓存没有快照时间。
- 缓存数据字段缺失。

不得绕过：

- 回看历史任务详情时必须使用任务快照，不使用最新热点数据重写旧结果。

### 9.2 前端代码方案

#### 新增页面

```text
web/src/pages/Strategy4Results.vue
```

#### 配置页新增分区

策略4配置默认：

```yaml
strategy4:
  enabled: true
  hot_topic_top_n: 8
  watch_hot_topic_top_n: 15
  min_hot_topic_score: 85
  min_hot_topic_signal_count: 2
  core_leaders_per_topic: 1
  backup_leaders_per_topic: 2
  max_total_leaders_per_topic: 3
  min_leader_strength_score: 88
  core_leader_strength_score: 93
  first_wave_lookback_short: 10
  first_wave_lookback_long: 20
  min_first_wave_return_10d: 0.25
  min_first_wave_return_20d: 0.35
  pullback_min_pct: 0.08
  pullback_max_pct: 0.25
  pullback_min_days: 2
  pullback_max_days: 8
  max_risk_ratio: 0.15
  aggressive_max_risk_ratio: 0.20
  min_reward_risk_ratio: 2.0
  core_leader_min_reward_risk_ratio: 1.8
```

#### 页面状态

```js
{
  taskId: null,
  status: 'IDLE',
  topics: [],
  leaders: [],
  candidates: [],
  lockedLeaders: [],
  selectedTopicId: null,
  selectedCode: null,
  loadFailures: []
}
```

#### 轮询规则

- 任务运行中每2秒查询状态。
- 热点题材可以先展示部分结果。
- 任务完成后停止轮询并刷新四个榜单。
- 任务失败时展示失败原因。
- 页面卸载时清理轮询。

---

## 10. 日志与异常处理方案

### 10.1 必须记录的日志

- 策略4任务创建日志。
- 行业/概念数据源调用日志。
- 热点题材召回数量。
- 噪音题材剔除原因。
- 龙头候选召回来源。
- 涨跌幅制度识别结果。
- 涨停形态识别结果。
- 锁仓关注度修正原因。
- 二波候选入选原因。
- 数据源失败原因。
- 任务完成汇总。

### 10.2 异常处理

- 行业/概念数据源全部失败：任务失败，返回明确错误。
- 单个题材指数失败：题材标记 `DATA_SOURCE_FAILED`，不影响其他题材。
- 板块成分股接口失败：降级使用领涨股和全市场强召回，但标记 `membership_source=partial`。
- 单只股票日线失败：记录逐股失败，不中断任务。
- 涨跌幅制度无法识别：标记 `UNKNOWN_PRICE_LIMIT_RULE`，不按涨停加分。
- 历史任务详情必须使用任务快照，不因最新数据变化重算旧热点。

---

## 11. 测试方案

### 11.1 单元测试

必须覆盖：

- `PriceLimitResolver`：
  - 主板10cm。
  - 创业板20cm。
  - 科创板20cm。
  - 北交所30cm。
  - ST 5cm。
  - 新股无涨跌幅阶段。
  - 复权/四舍五入容差。
- 涨停形态识别：
  - 一字板。
  - T字板。
  - 收盘涨停。
  - 接近涨停。
  - 炸板。
- 热点题材评分。
- 噪音题材剔除。
- 锁仓关注度修正。
- 龙头召回去重。
- 龙头强度评分。
- 第一波大涨判断。
- 健康回踩判断。
- 二次启动判断。
- 收益比计算。

### 11.2 接口测试

必须覆盖：

- 启动策略4扫描。
- 查询策略4状态。
- 查询策略4任务列表。
- 查询热点题材榜。
- 查询龙头股票榜。
- 查询二波候选。
- 查询候选详情。
- 跨策略 task_id 返回 `TASK_STRATEGY_MISMATCH`。

### 11.3 集成测试

测试流程：

1. Mock AkShare 行业/概念数据。
2. Mock 热点题材指数日线。
3. Mock 龙头股票日线。
4. 启动策略4扫描。
5. 验证热点题材写入。
6. 验证龙头快照写入。
7. 验证锁仓观察和二波候选分类。
8. 验证前端查询 API 返回完整字段。

### 11.4 前端测试

测试场景：

- 页面首次打开。
- 启动策略4扫描。
- 任务运行中展示热点进度。
- 任务完成后展示四个榜单。
- 无可交易候选但有热点和龙头时，不显示空白。
- 点击热点筛选龙头。
- 点击候选展示详情。
- 数据源失败展示错误。
- 历史任务切换防 stale response。

### 11.5 回归测试

必须验证：

- 策略1扫描不受影响。
- 策略2扫描不受影响。
- 策略3未来实现不受影响。
- 现有扫描互斥仍有效。
- 现有任务中心不被策略4字段破坏。
- 旧任务仍可展示。

---

## 12. 分阶段实施建议

### Phase 1：策略4扫描与展示

目标：

- 完成热点题材识别。
- 完成龙头识别。
- 完成涨停制度识别。
- 完成二波候选和锁仓观察。
- 完成 API 和前端展示。

不做：

- 完整历史回测。
- 自动参数优化。

### Phase 2：策略4历史回测

目标：

- 使用历史板块指数和本地 `daily_ohlc` 回放。
- 对缺失历史题材资金流做明确不可观察标记。
- 不伪造历史资金流。
- 生成策略4可信度报告。

### Phase 3：策略4参数实验

目标：

- 对热点分、龙头分、回踩区间、收益比阈值做实验。
- 输出正式参数建议。
- 不以候选数量为优化目标，以主线捕捉率和二波收益比为主要目标。

---

## 13. 验收标准

功能完成后必须满足：

1. 策略4可以独立启动扫描。
2. 能展示热点题材榜、龙头股票榜、二波候选榜、锁仓观察榜。
3. 热点判断优先级高于个股形态。
4. 龙头识别优先级高于二波结构。
5. 非热点行业股票不进入策略4候选。
6. 非龙头股票不进入策略4二波候选。
7. 创业板/科创板20cm涨停可以正确识别。
8. 一字板/缩量涨停不会因当日成交额低被误杀。
9. 炸板股票能被识别为高关注高分歧。
10. 任务结果可追溯到数据源快照。
11. 不破坏策略1/2现有功能。
12. 核心规则有单元测试。
13. API和前端有验证。

---

## 14. 给 Claude Code / Codex 的执行指令

请严格按照本文档执行策略4开发。

执行要求：

1. 先阅读 `AGENTS.md`、`CLAUDE.md`、本设计文档和现有策略1/2代码边界。
2. 新建独立 worktree 和分支开发，不在策略2或策略3 worktree 里开发。
3. 先实现纯函数和单元测试，再接数据库、API和前端。
4. 不要修改策略1/2核心规则。
5. 不要把策略4候选写入策略1/2表。
6. 不要统一硬编码10%涨停。
7. 不要因为涨停日成交额低排除锁仓热点。
8. 不要从全市场直接找二波形态，必须先过热点和龙头前置条件。
9. AkShare接口失败时必须记录并降级，不得静默返回错误结果。
10. 历史任务详情必须使用任务快照。
11. 每完成一个模块后运行对应测试。
12. 开发完成后进入审核角色，重点检查交易制度、数据源失败、跨策略隔离、历史任务一致性。

---

## 15. AI 开发提示语

可以直接给 AI 开发工具使用：

```text
请在当前项目中开发策略4「热点龙头二波」。

你必须先阅读 AGENTS.md、CLAUDE.md 和 docs/superpowers/specs/2026-07-01-strategy4-hot-leader-second-wave-design.md。

本次只实现策略4，不修改策略1/策略2核心策略规则，不复用策略1/2/3的策略判断入口。

策略4的核心顺序必须是：
最热行业/题材 -> 最强龙头股票 -> 第一波大涨确认 -> 健康回踩 -> 二次启动 -> 收益比排序。

重点要求：
1. 行业/题材热度和龙头识别是强前置条件，非热点、非龙头不得进入二波候选。
2. 使用 AkShare 同花顺行业/概念指数、资金流、板块摘要作为策略4题材数据源，接口失败时必须有错误记录和降级。
3. A股涨停制度必须正确处理：主板10cm、创业板/科创板20cm、北交所30cm、ST 5cm、新股无涨跌幅阶段。
4. 不允许统一硬编码10%涨停。
5. 涨停、连板、一字板、缩量封板时，不得因为当日成交额偏低误判为无人关注；必须实现 locked_attention_score 或等价机制。
6. 输出热点题材榜、龙头股票榜、二波候选榜、锁仓观察榜。
7. 新增 strategy4 独立目录、独立数据库表、独立 API、独立前端结果页和配置分区。
8. 策略4任务必须使用 scan_tasks.strategy_type=STRATEGY_4_HOT_LEADER_SECOND_WAVE。
9. 跨策略 task_id 必须返回 TASK_STRATEGY_MISMATCH。
10. 先写测试，再实现核心纯函数，最后接数据库、API、前端。

完成后运行后端相关测试、前端相关测试和 compileall，并提交本地 git commit。不要 push，除非用户明确要求。
```

---

## 16. `/goal` 语句

建议使用：

```text
/goal 在独立 worktree 中实现策略4「热点龙头二波」Phase 1：新增策略4独立扫描、热点行业/题材识别、龙头股票识别、A股涨停制度识别、锁仓关注度修正、第一波健康回踩二次启动判断、独立数据库表/API/前端结果页/配置页，并补齐测试；不得修改策略1/策略2核心规则，不得把策略4结果写入其他策略表，不得统一硬编码10%涨停。
```

---

## 17. 最终交付物

开发完成后需要交付：

1. 修改文件清单。
2. 核心代码变更说明。
3. 新增配置说明。
4. 新增数据库表说明。
5. 新增接口说明。
6. 前端页面说明。
7. 策略4核心规则说明。
8. A股交易制度识别说明。
9. 测试结果说明。
10. 是否存在数据源限制。
11. 是否存在遗留问题。
12. 是否建议进入 Phase 2 回测。

# CupHandleScan — 系统设计文档

**日期**: 2026-06-03
**状态**: 待审批

---

## 1. 项目概述

A股杯柄结构自动扫描系统。分为三个子系统：

- **扫描引擎**（后端）：Python + AKShare，全市场扫描杯柄形态
- **干稳低吸分析**（后端）：对候选股票做量干/价稳/形态三维深度评分
- **Web 终端**（前端）：Vue 3 深色金融终端风格，4 页面 SPA

数据流：全市场扫描 → 杯柄初筛 → 干稳低吸深度分析 → Web 终端展示

---

## 2. 后端架构

### 2.1 技术栈

| 项 | 选型 |
|---|---|
| 语言 | Python 3.10+ |
| 数据源 | AKShare（股票池）、新浪财经（OHLC）、腾讯财经（OHLC） |
| Web 框架 | FastAPI |
| 图表 | matplotlib（PNG 输出） |
| 缓存 | JSON 文件本地缓存 |
| 并发 | threading（双线程数据源互斥） |

### 2.1.1 数据源分层策略

AKShare 经常获取不到数据，因此采用**分层回退**架构：

```
数据请求优先级:
  股票池获取:
    1. AKShare (stock_info_a_code_name)
    2. 本地缓存 stock_pool.json (fallback)
    3. 新浪财经股票列表 (last resort)

  日线OHLC数据:
    1. 新浪财经 API (直接请求，不经 AKShare)
    2. 腾讯财经 API (直接请求，不经 AKShare)
    3. 本地缓存 daily/{code}.json (fallback)
    4. 记录失败 → skip

单只股票请求流程:
  try:
    sina_source.fetch(code)      # 优先新浪
  except (Timeout, HTTPError):
    try:
      tencent_source.fetch(code) # 回退腾讯
    except (Timeout, HTTPError):
      try:
        cache.load(code)         # 回退本地缓存
      except CacheMiss:
        log_skip(code, reason)   # 记录失败，继续下一只
        return None
```

AKShare 仅用于获取**股票池列表**和**股票基本信息**，不是 OHLC 数据的主通道。实际日线数据直接从新浪/腾讯 API 抓取。

### 2.2 目录结构

```
cuphandle-scan/
├── main.py                    # CLI 入口
├── config.yaml                # 配置文件
├── requirements.txt
├── README.md
├── server.py                  # FastAPI Web 服务入口
│
├── scheduler/                 # 定时任务
│   ├── __init__.py
│   └── scheduler.py           # 每日 15:30 自动扫描调度
│
├── scanner/                   # 杯柄扫描引擎
│   ├── __init__.py
│   ├── engine.py              # 扫描引擎主控（双线程调度）
│   ├── data_source.py         # 数据源抽象层 + 互斥锁管理
│   ├── sina_source.py         # 新浪数据源
│   ├── tencent_source.py      # 腾讯数据源
│   ├── stock_pool.py          # A股股票池获取与过滤
│   ├── liquidity_filter.py    # 成交量/成交额过滤
│   ├── pattern_detector.py    # 杯柄结构识别算法
│   ├── breakout_detector.py   # 突破判断
│   └── scorer.py              # 形态评分（0-100）
│
├── analyzer/                  # 干稳低吸分析引擎
│   ├── __init__.py
│   ├── volume_dry.py          # 量干评分（0-10）
│   ├── price_stable.py        # 价稳评分（0-10）
│   ├── pattern_score.py       # 形态评分（杯柄 0-20 + VCP 0-20）
│   ├── key_prices.py          # 关键价格计算（低吸区间/止损/止盈）
│   ├── risk_reward.py         # 风险收益比 + 仓位建议
│   └── market_env.py          # 大盘环境过滤
│
├── output/                    # 输出模块
│   ├── __init__.py
│   ├── csv_writer.py          # CSV 输出
│   ├── json_writer.py         # JSON 输出
│   ├── chart_generator.py     # matplotlib 图表生成
│   └── html_report.py         # 静态 HTML 汇总报告
│
├── cache/                     # 本地缓存
│   └── daily/                 # 每只股票日线数据 JSON 缓存
│
├── logs/                      # 扫描日志
│   └── scan_YYYY-MM-DD.log
│
├── output_data/               # 输出目录
│   ├── candidates_YYYY-MM-DD.csv
│   ├── candidates_YYYY-MM-DD.json
│   └── charts/                # 候选股票图表 PNG
│
├── web/                       # 前端（Vue 3 SPA）
│   ├── index.html
│   ├── src/
│   │   ├── App.vue
│   │   ├── main.js
│   │   ├── styles/
│   │   │   └── variables.css  # 颜色系统 CSS 变量
│   │   ├── components/
│   │   │   ├── TopNav.vue
│   │   │   ├── MetricCard.vue
│   │   │   ├── SignalBadge.vue
│   │   │   ├── DiscoveryList.vue
│   │   │   ├── ScanEngine.vue
│   │   │   ├── RadarTable.vue
│   │   │   ├── ScoreBar.vue
│   │   │   ├── StockChart.vue
│   │   │   ├── Watchlist.vue
│   │   │   └── RiskBox.vue
│   │   ├── pages/
│   │   │   ├── ScannerConsole.vue
│   │   │   ├── ResultsRadar.vue
│   │   │   ├── TaskCenter.vue
│   │   │   └── StockDetail.vue
│   │   ├── composables/
│   │   │   ├── useScanSocket.js   # WebSocket 实时扫描状态
│   │   │   ├── useApi.js          # REST API 调用
│   │   │   └── useWatchlist.js    # 候选列表状态管理
│   │   └── router/
│   │       └── index.js
│   ├── vite.config.js
│   └── package.json
│
└── tests/
    ├── test_pattern_detector.py
    ├── test_scorer.py
    ├── test_volume_dry.py
    ├── test_price_stable.py
    └── test_data_source.py
```

### 2.3 定时任务调度

使用 APScheduler 实现每日定时扫描。A股收盘时间为 15:00，留 30 分钟缓冲确保数据已更新。

```
scheduler.py:
  - 每日 15:30 触发全市场扫描
  - 支持 cron 表达式配置
  - 扫描任务异步执行，不阻塞调度器
  - 如果上一次扫描仍未完成，跳过本次（防止堆积）
  - 扫描完成后可选发送通知（日志/WebSocket/Webhook）
  - 支持手动触发（不影响定时规则）
  - 可通过配置文件开关
```

**调度器配置（config.yaml 新增）:**
```yaml
scheduler:
  enabled: false          # 默认关闭，需手动开启
  cron: "30 15 * * 1-5"  # 每周一到周五 15:30
  skip_if_running: true   # 上次未完成则跳过
  on_complete: log        # log | webhook
  webhook_url: null
```

**调度器生命周期:**
- `python main.py serve` 启动 Web 服务时，调度器随 FastAPI 一起启动
- `python main.py schedule` 仅启动调度器（无 Web 服务），适合轻量部署
- 调度器在应用 shutdown 时优雅关闭，等待当前任务完成

### 2.4 数据源互斥锁 + 回退设计

```
┌──────────────────────────────────────────────────────────┐
│                    DataSourceManager                      │
│                                                          │
│  sina_lock: threading.Lock                               │
│  tencent_lock: threading.Lock                            │
│  stock_pool: Queue   # 待扫描股票队列                      │
│                                                          │
│  acquire(ds_name) → bool      # 非阻塞尝试获取锁           │
│  release(ds_name)              # 释放锁（必须 finally）     │
│  try_acquire_any() → str|None # 返回可用数据源名           │
│                                                          │
│  单只股票扫描流程（每个线程内）:                             │
│                                                          │
│  while not stock_pool.empty():                           │
│    code = stock_pool.get()                               │
│    ds = try_acquire_any()    # 获取可用数据源              │
│    if not ds:                                             │
│      time.sleep(0.1)         # 两个都忙，等待              │
│      stock_pool.put(code)   # 放回队列                    │
│      continue                                             │
│    try:                                                   │
│      data = fetch_with_fallback(code, ds)                │
│      if data: analyze(code, data)                        │
│    except Exception as e:                                 │
│      log_error(code, e)     # 单只失败不中断               │
│    finally:                                               │
│      release(ds)            # 异常也释放                   │
│                                                          │
│  fetch_with_fallback(code, primary_ds):                  │
│    try:                                                   │
│      return primary_ds.fetch(code)   # 主数据源            │
│    except (Timeout, ConnectionError):                     │
│      log_warn(f"{primary_ds} failed, trying fallback")    │
│      try:                                                 │
│        other = 'tencent' if primary_ds == 'sina'          │
│                            else 'sina'                    │
│        if acquire(other):      # 尝试回退源（不等待）       │
│          try:                                              │
│            return other.fetch(code)                       │
│          finally:                                          │
│            release(other)                                 │
│      except:                                              │
│        pass                                               │
│      return cache.load(code)   # 最后回退本地缓存           │
└──────────────────────────────────────────────────────────┘
```

关键实现要点：
- 使用 `threading.Lock`（非阻塞 `acquire(blocking=False)`）
- `try...finally` 确保异常路径也释放锁
- 线程取不到锁时 `time.sleep(0.1)` 后重试
- 扫描完成或股票池耗尽时线程退出
- **单只失败不中断：** 记录日志后 `continue` 下一只
- **三级回退：** 主数据源 → 回退数据源 → 本地缓存
- **回退不抢锁：** 回退到另一个数据源时也需 `acquire()`，失败则跳过

### 2.3.1 异常处理清单

每只股票扫描可能遇到的异常及处理：

| 异常 | 处理 |
|---|---|
| 新浪 API 超时 (5s) | → 回退腾讯 |
| 腾讯 API 超时 (5s) | → 回退本地缓存 |
| 网络连接失败 | → 回退缓存 |
| 返回数据为空/格式错误 | → 记录 skip，下一只 |
| 股票停牌（连续交易日为0） | → 记录 skip |
| 上市不足 120 交易日 | → 记录 skip |
| 成交量全为 0 | → 记录 skip |
| 字段缺失（如缺少 high） | → 记录 skip |
| 锁获取失败（两源都忙） | → sleep 0.1s，放回队列 |
| 图表生成失败 | → 记录 warn，继续输出 CSV |
| 文件写入失败 | → 记录 error，尝试备用路径 |

### 2.4 配置文件结构 (config.yaml)

```yaml
market:
  include_sh: true       # 沪市主板
  include_sz: true       # 深市主板
  include_cyb: true      # 创业板
  include_kcb: true      # 科创板
  exclude_bj: true       # 排除北交所
  exclude_st: true       # 排除 ST/*ST
  min_listing_days: 120  # 新股最短上市天数

data:
  cache_enabled: true
  cache_dir: ./cache/daily
  start_date: "2025-01-01"
  end_date: null         # null = 最近交易日
  use_fq: true           # 前复权

liquidity:
  enabled: true
  avg_turnover_days: 20
  min_avg_turnover: 100000000    # 1亿
  min_avg_volume: 5000000        # 500万股
  min_latest_turnover: 80000000  # 8000万

cup:
  min_duration: 35
  max_duration: 180
  min_depth: 0.12
  max_depth: 0.45
  max_lip_deviation: 0.12
  min_bottom_roundness: 0.15
  filter_v_shape: true

handle:
  min_duration: 5
  max_duration: 30
  max_depth: 0.18
  max_vs_right_rally: 0.50

breakout:
  buffer_pct: 0.02       # 突破缓冲 2%
  volume_multiplier: 1.5 # 放量倍数
  use_volume_confirm: true

scoring:
  cup_weight: 35
  handle_weight: 25
  volume_weight: 20
  trend_weight: 10
  breakout_weight: 10
  strong_threshold: 80
  medium_threshold: 70

output:
  csv: true
  json: true
  charts: false
  output_dir: ./output_data
  log_dir: ./logs

server:
  host: 127.0.0.1
  port: 8080
```

### 2.5 杯柄识别算法流程

```
对于每只股票:
  1. 获取 250 个交易日日线数据（前复权）
  2. 流动性过滤（20日均成交额 ≥ 1亿）
  3. 识别局部高点和低点（Swing High / Swing Low）
  4. 寻找左杯口 → 杯底 → 右杯口 → 柄部低点序列
  5. 验证杯体约束:
     - 持续时间: 35~180 交易日
     - 深度: 12%~45%
     - 左右杯口偏差 ≤ 12%
     - 杯底圆滑度 ≥ 15% 停留时间
  6. 验证柄部约束:
     - 持续时间: 5~30 交易日
     - 回撤 ≤ 18%
     - 不超过右侧上涨的 50%
  7. 突破判断:
     - 收盘价 > 突破位（左/右杯口较高者）+ 2%
     - 成交量 ≥ 20日均量的 1.5 倍（放量确认）
  8. 评分: 杯体 35 + 柄部 25 + 成交量 20 + 前置趋势 10 + 突破 10
  9. 分级: ≥80 强候选 / 70-79 中等候选 / 60-69 弱候选
```

### 2.5 干稳低吸分析流程

```
对于每只候选股票:
  1. 量干评分 (0-10):
     - 最近5日均量 vs 20日均量
     - 最近5日均量 vs 50日均量
     - 整理末端成交量递减
     - 下跌日无放量
     - 是否出现极低量
  2. 价稳评分 (0-10):
     - 最近波动收窄
     - 不再创新低
     - 低点抬高或持平
     - 收盘价守住关键均线
     - ATR 下降
  3. 形态评分 (0-20):
     - max(杯柄评分, VCP评分)
  4. 关键价格计算:
     - 低吸区间 / Pivot枢纽点 / 止损价 / 止盈价
  5. 风险收益比:
     - Risk% ≤ 8%, RR1 ≥ 2:1
  6. 输出评级: 可低吸 / 突破确认 / 观察 / 不建议买入
```

### 2.6 API 设计

```
GET  /api/scan/start          → 启动全市场扫描（异步，返回 task_id）
GET  /api/scan/status/:id      → 扫描状态 + 实时进度
GET  /api/scan/stop/:id        → 停止扫描
GET  /api/scan/tasks           → 历史扫描任务列表
GET  /api/scan/task/:id        → 某个任务的完整结果

GET  /api/candidates?scan_id=  → 候选列表（支持 sort/filter 参数）
GET  /api/candidate/:code      → 单只股票详情（含杯柄分析 + 干稳低吸分析）

GET  /api/stock/:code/chart    → PNG 图表文件
GET  /api/stock/:code/ohlc     → OHLC 数据（供前端 K 线图）

GET  /api/config               → 当前配置
PUT  /api/config               → 更新配置

WS   /ws/scan/:id              → 扫描实时推送（进度/新发现/日志）
```

### 2.7 CLI 接口

```bash
# 全市场扫描
python main.py scan

# 单只股票扫描
python main.py scan --stock 600036

# 指定日期范围
python main.py scan --start 2026-01-01 --end 2026-06-03

# 只输出已突破
python main.py scan --breakout-only

# 生成图表
python main.py scan --charts

# 使用指定配置
python main.py scan --config my_config.yaml

# 启动 Web 服务（含调度器）
python main.py serve --port 8080

# 仅启动调度器（无 Web 服务）
python main.py schedule

# 历史任务查看
python main.py tasks

# 查看某只股票的详细分析
python main.py analyze 600036
```

---

## 3. 前端设计规范

### 3.1 技术栈

| 项 | 选型 |
|---|---|
| 框架 | Vue 3（Composition API） |
| 构建 | Vite |
| 图表 | ECharts 5（K线/成交量/评分雷达图） |
| 样式 | Plain CSS + CSS Variables |
| 字体 | 系统字体栈 |
| 实时通信 | WebSocket（扫描进度推送） |

### 3.2 颜色系统

```css
:root {
  --bg-root:        #070B14;   /* 根背景 */
  --bg-panel:       #0D1320;   /* 面板背景 */
  --bg-card:        #111827;   /* 卡片背景 */
  --border:         #1F2A3A;   /* 边框 */
  --border-light:   #2A3548;   /* 亮边框 */

  --text-primary:   #E8ECF1;   /* 主文字 */
  --text-secondary: #8896A6;   /* 辅助文字 */
  --text-muted:     #5A6A7E;   /* 弱化文字 */

  --accent:         #4F7DFF;   /* 主高亮蓝 */
  --accent-glow:    rgba(79,125,255,0.15);

  --up-red:         #EF4444;   /* A股上涨/突破 */
  --down-green:     #22C55E;   /* A股下跌/回撤合理 */
  --gold:           #F59E0B;   /* 高分/A级信号（仅≥80分） */
  --warn-orange:    #F97316;   /* 风险/警告 */
}
```

**使用规则：**
- 金色仅用于 ≥80 分 A 级信号和最高评分
- 蓝色用于中等候选（70-79）、普通操作、链接
- 灰色用于弱候选（≤69）、观察状态
- 红色 = 上涨 / 已突破 / 放量确认（A股语境）
- 绿色 = 下跌 / 回撤合理 / 缩量健康
- 橙色 = 警告 / 接近突破 / 风险提示

### 3.3 字体规范

```css
--font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI',
             'PingFang SC', 'Microsoft YaHei', sans-serif;
--font-mono: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
```

| 用途 | 字号 | 字重 | 字体 |
|---|---|---|---|
| 页面标题 | 26-28px | 700 | sans |
| 面板标题 | 12px | 600 | sans |
| 正文 | 14px | 400 | sans |
| 表格正文 | 13px | 400 | sans |
| 表头 | 12px | 500 | sans |
| 核心数字（卡片内） | 28-32px | 700 | mono |
| 表格数字 | 13px | 400 | mono |
| Badge/标签 | 11-12px | 600 | sans |
| 小字辅助 | 10-11px | 400 | sans |

### 3.4 页面结构

#### 页面 1：机会雷达控制台 `/`

**布局：** 指标摘要行（6列） → 双栏（候选发现 50% | 扫描引擎 50%）

**组件树：**
```
ScannerConsole.vue
├── MetricCard × 6          # 今日候选/A级信号/突破确认/接近突破/量能确认/最高评分
├── DiscoveryList            # 最新发现列表（按时间排序）
│   └── DiscoveryItem × N    # 信号色条 + 代码名称 + Badge + 评分
└── ScanEngine               # 扫描引擎面板
    ├── ScanStatus           # 进度条 + 当前扫描股票 + 速度/剩余时间
    ├── ScanLog              # 实时日志流（候选发现高亮）
    └── ScanControls         # 暂停/停止按钮
```

#### 页面 2：候选结果列表 `/results`

**布局：** 摘要行（6列） → 筛选工具栏 → 雷达表格

**筛选器：** 全部 | A级(≥80) | 中等(70-79) | 已突破 | 接近突破 | 距突破<5% | 量能确认 | 放量≥1.5×

**排序：** 形态评分 ↓ | 距突破位 | 量能强度 | 杯体质量 | 最近发现

**表格列：** 信号色条 | 代码 | 名称 | 形态评分（+微条形图）| 信号等级 Badge | 突破状态 | 最新价 | 突破位 | 距突破位 | 杯体回撤深度 | 柄部回撤幅度 | 杯体天数 | 量能状态 | 放量倍数

#### 页面 3：任务中心 `/tasks`

**布局：** 任务列表（每条一行）
- 每条显示：状态灯 | 扫描日期 | 范围 | 耗时 | 候选数 | 最高评分 | 平均评分 | A级数 | 突破数 | 数据源 | 操作按钮

#### 页面 4：个股详情 `/stock/:code`

**布局：** 三栏（280px | 自适应 | 280px）

**左栏：** 股票信息 → 形态评分拆解（5条进度条 + 总分）→ 关键价格 → 关键日期 → 风险提示

**中栏：** K线主图（ECharts） + 成交量副图 + 杯柄结构时间线（5阶段卡片）

**右栏：** 候选观察列表（可切换股票，当前选中高亮）

**响应式：** <1280px 时折叠右侧 Watchlist

### 3.5 组件设计清单

| 组件 | 要点 |
|---|---|
| TopNav | 品牌 Logo + 4 Tab + 上次扫描时间 + 开始扫描按钮 |
| MetricCard | 标签（上）+ 数字（中，28-32px mono）+ 辅助文字（下） |
| SignalBadge | 强候选=金色 / 中等=蓝色 / 弱=灰色 / 已突破=红色 / 接近突破=橙色 |
| DiscoveryItem | 左侧 3px 信号色条 + 代码名称 + Badge + 评分 + 关键指标摘要 |
| RadarTable | 可排序表头 + 行选中高亮 + 信号色条 + 评分微条形图 |
| ScoreBar | 标签 + 分数 + 进度条（金色/蓝色/红色按分数域着色） |
| StockChart | ECharts K线 + 成交量 + 杯柄标注 + 突破位线 + 当前价线 |
| Watchlist | 筛选 Chip + 列表项（色条+代码+评分）+ 选中高亮 |
| RiskBox | 橙色边框 + 标题 + 风险文字 |
| ScanEngine | 进度条 + 当前扫描 + 速度 + 日志流 |

### 3.6 交互规范

- **扫描中动效：** 脉冲指示灯（橙色呼吸）、实时日志滚动、进度条渐变填充
- **新候选发现：** 金色闪烁 1 秒后稳定
- **表格排序：** 点击表头排序，▲/▼ 指示方向
- **行选中：** 蓝色半透明背景 + 蓝色轮廓线
- **表格筛选：** Chip 按钮切换，互斥或叠加
- **K线图 Tooltip：** 日期/开/高/低/收/量，杯柄关键点高亮
- **导出反馈：** 按钮显示"已导出 ✓" 2 秒后恢复
- **响应式：** <1280px 折叠右侧 Watchlist，<960px 双栏变单栏

### 3.7 空/加载/异常状态

| 状态 | 表现 |
|---|---|
| 加载中 | 骨架屏（灰色脉冲动画），指标卡片显示 `--` |
| 空候选 | "本次扫描未发现符合条件的杯柄形态" + 调整筛选条件的建议链接 |
| 数据异常 | 黄色提示条 + 错误详情可展开 |
| 扫描故障 | 红色提示条 + 重试按钮 + 已扫描数量保留 |

### 3.8 字段命名规范

| 原始字段 | 显示名称 |
|---|---|
| 评分 | 形态评分 |
| 等级 | 信号等级 |
| 突破 | 突破状态 |
| 杯体深度 | 杯体回撤深度 |
| 柄部回撤 | 柄部回撤幅度 |
| 放量倍数 | 量能倍数 |
| 距突破位 | 距突破位 |
| 杯体天数 | 杯体周期 |

---

## 4. 开发阶段

### Phase 1：基础可运行版本
1. 项目目录结构搭建
2. 配置文件（config.yaml）
3. A股股票池获取（AKShare + 双数据源）
4. 日线行情获取 + 本地缓存
5. 双线程数据源互斥扫描引擎
6. 基础流动性过滤
7. 基础杯柄识别
8. CSV 输出
9. CLI 运行（scan / analyze）
10. FastAPI Web 服务 + 基础 API

### Phase 2：形态评分和突破判断
1. 杯体评分（0-35）
2. 柄部评分（0-25）
3. 成交量结构评分（0-20）
4. 前置趋势评分（0-10）
5. 突破判断 + 突破确认评分（0-10）
6. 候选等级划分（强/中/弱）
7. JSON 输出
8. 干稳低吸分析引擎（量干+价稳+形态+风险收益比）

### Phase 3：Web 前端
1. Vue 3 项目搭建 + Vite
2. CSS 变量系统 + 颜色规范
3. 4 页面实现（雷达/列表/任务/详情）
4. ECharts K线图 + 成交量副图
5. WebSocket 实时扫描状态推送
6. 图表 PNG 生成（matplotlib）
7. 静态 HTML 汇总报告

### Phase 4：工程化增强
1. 本地缓存（增量更新策略）
2. 扫描进度条
3. 日志系统
4. 异常重试（指数退避）
5. 单元测试
6. 异常处理完善

### Phase 5：历史验证（后续）
1. 历史杯柄回测
2. 突破后 N 日收益统计
3. 假突破比例统计
4. 参数优化

---

## 5. 关键约束

1. **红涨绿跌** — A股语境，不可使用美股配色
2. **金色仅用于高分** — ≥80 分或 A 级信号
3. **单只股票异常不中断全市场扫描** — try/except 包裹单只处理
4. **数据源锁必须释放** — finally 块确保释放
5. **配置文件独立** — 所有阈值可调整
6. **不构成投资建议** — 文案克制，使用"形态筛选"而非"推荐买入"
7. **市场范围** — Phase 1 仅 A股，架构预留多市场扩展（美股/港股）

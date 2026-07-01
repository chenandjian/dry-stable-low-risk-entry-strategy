# CupHandleScan

A股扫描与回测系统，当前包含两套独立策略：

- **策略1：杯柄 / VCP / 干稳低吸**，用于寻找杯柄结构、VCP 收缩结构和低风险入场机会。
- **策略2：极致量干价稳**，用于寻找极端缩量、价格稳定、风险比较低的短线候选。

系统提供后端 API、Vue 前端、SQLite 本地数据存储、扫描任务追踪、失败股票重拉和策略回测能力。

## 快速开始

```bash
pip install -r requirements.txt
python main.py serve --port 8080
```

前端开发：

```bash
npm --prefix web install
npm --prefix web run dev -- --host 127.0.0.1
```

API 文档：

```text
http://localhost:8080/docs
```

## 常用命令

```bash
# 全市场扫描
python main.py scan

# 分析单只股票
python main.py analyze 600036

# 启动 Web 服务
python main.py serve --port 8080

# 后台定时扫描
python main.py schedule
```

## 前端页面

- `/`：扫描控制台，支持策略1/策略2启动、进度、失败列表和重新拉取。
- `/strategy1/backtest`：策略1回测实验页面，包含质量标签、分层展示和 VCP 独立分组。
- `/strategy2/results`：策略2扫描结果。
- `/strategy2/backtest`：策略2本地数据库回测。
- `/config`：策略配置。

## 策略1：杯柄 / VCP / 干稳低吸

策略1统一入口是 `scanner/strategy_engine.py::CupHandleStrategyEngine.evaluate_at()`。

核心能力：

- 杯柄结构识别。
- VCP 收缩结构识别，并在前端独立分组展示。
- 量干、价稳、形态、关键价格、风险收益比和市场环境综合判断。
- 质量标签与分层展示，用于解释候选质量，不替代核心策略入选规则。
- 策略1回测实验，用于验证参数和候选质量。

## 策略2：极致量干价稳

策略2统一入口是 `strategy2/engine.py::ExtremeDryStableStrategyEngine.evaluate_at()`。

核心能力：

- 量干 50 分 + 价稳 50 分，总分 100。
- 趋势过滤、一票否决、支撑位、买入区间、止损和风险比计算。
- 扫描结果写入独立 `strategy2_candidates` 表，不混入策略1候选。
- 回测只读本地数据库，不调用外部行情源。

## 数据与缓存

- 股票池：AKShare 获取，失败时可回退本地缓存。
- 日线行情：默认 `baidu → sina → tencent`，yfinance 已从生产数据源剔除。
- 数据存储：SQLite，默认 `data/cuphandle.db`。
- 日线表：`daily_ohlc`。
- 扫描任务：`scan_tasks`。
- 逐股状态：`task_stocks`。

扫描规则：

- 在线数据源全部失败时，不使用旧缓存产出扫描结果，股票进入失败列表。
- 失败股票可通过失败列表重新拉取。
- 同一股票当天已经由任一策略成功获取过日线时，后续策略1/策略2扫描会复用本地 `daily_ohlc`，避免重复拉取。
- 停牌或无新交易导致最新 K 线不是自然日当天，也可以复用当天已获取到的最新 K 线日期。

## 配置

编辑 `config.yaml`：

- `market`：市场范围。
- `data.daily_sources`：日线数据源顺序。
- `data.scan_window_days`：策略1扫描计算窗口。
- `data.backtest_window_days`：策略1回测计算窗口。
- `liquidity.min_listing_days`：日线拉取天数与上市天数检查。
- `cup` / `handle` / `breakout` / `scoring`：策略1参数。
- `strategy2`：策略2独立参数。
- `scheduler`：定时任务配置。

## 验证

后端常规验证：

```bash
python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py
python -m compileall scanner strategy2 server.py -q
```

前端验证：

```bash
npm --prefix web install
npm --prefix web test -- --run
npm --prefix web run build
```

真实外部数据源测试仅手工按需运行：

```bash
python -m pytest tests/test_akshare_hist.py -v
python -m pytest tests/test_tushare_hist.py -v
```

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

CupHandleScan — A股杯柄结构（Cup & Handle）自动扫描系统。Python 3.10+。

## Commands

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行单个测试文件
python -m pytest tests/test_data_source.py -v

# 运行单个测试函数
python -m pytest tests/test_data_source.py::test_acquire_release_single_source -v

# 安装依赖
pip install -r requirements.txt
```

## Architecture

```
入口层:    main.py (CLI)  /  server.py (FastAPI)  /  scheduler/scheduler.py
引擎层:    scanner/engine.py (双线程扫描调度)
数据层:    scanner/data_source.py (互斥锁管理)
           scanner/sina_source.py / tencent_source.py (HTTP抓取)
           scanner/stock_pool.py (股票池)
算法层:    scanner/pattern_detector.py (杯柄识别)
           scanner/liquidity_filter.py (流动性过滤)
           scanner/scorer.py (评分 0-100)
输出层:    output/csv_writer.py
```

**核心设计决策:**

- **数据源互斥锁：** 两个扫描线程不能同时请求同一个数据源（新浪/腾讯）。`DataSourceManager` 用 `threading.Lock(blocking=False)` 实现非阻塞互斥。线程取不到锁时 sleep 0.1s 后重试。
- **三级回退：** 主数据源 → 备用数据源 → 本地缓存。AKShare 仅用于获取股票池，不用于OHLC数据。
- **单只失败不中断：** 全市场扫描中，单只股票异常（超时/解析错误/停牌）记录日志后跳过，不中断整体任务。
- **数据源锁必须释放：** `try...finally` 确保异常路径也释放锁。
- **配置文件驱动：** 所有阈值（杯体深度、柄部回撤、流动性等）在 `config.yaml` 中可调。
- **形态评分维度：** 杯体结构 35 + 柄部结构 25 + 成交量结构 20 + 前置趋势 10 + 突破确认 10 = 100 分。
- **A股配色：** 红涨绿跌。金色仅用于 ≥80 分 A 级信号。

## Key Files

| File | Purpose |
|---|---|
| `config.yaml` | 所有可调参数（市场/流动性/杯体/柄部/突破/评分/输出/调度） |
| `scanner/data_source.py` | `DataSourceManager` — 新浪+腾讯双源互斥锁 |
| `scanner/sina_source.py` | `fetch_sina_daily(code, days)` → `list[dict] \| None` |
| `scanner/tencent_source.py` | `fetch_tencent_daily(code, days)` → `list[dict] \| None` |
| `scanner/pattern_detector.py` | `detect_cup_handle(data, config)` → `CupHandleResult` |
| `scanner/scorer.py` | `score_cup_handle(result)` → `int` (0-100) |
| `scanner/engine.py` | `scan_all(config)` — 双线程全市场扫描主循环 |

## Design Specs

- 系统设计: `docs/superpowers/specs/2026-06-03-cuphandle-scan-design.md`
- Phase 1 计划: `docs/superpowers/plans/2026-06-03-cuphandle-scan-phase1.md`
- 原始开发需求: `docs/DEVELOPMENT_DOC.md` (杯柄扫描) + `docs/dry-stable-low-risk-entry-strategy.md` (干稳低吸策略)
- 前端设计需求: `docs/art.md`

## Implementation Status

Phase 1 进行中。已完成:
- `config.yaml`, `requirements.txt`, package 骨架
- `scanner/data_source.py` — DataSourceManager 互斥锁 (5 tests passing)
- `scanner/sina_source.py` / `scanner/tencent_source.py` — 日线数据获取

待完成 (Tasks 4-12): stock_pool, liquidity_filter, pattern_detector, scorer, csv_writer, engine + main.py, server.py, scheduler, README

## .gitignore Policy

向 `.gitignore` 新增条目前，先告知用户确认。当前已忽略: Python 产物、虚拟环境、IDE 配置、`output_data/`、`logs/`、`cache/`、`.superpowers/`。

# Git Safety Rules

Claude may read files, modify files, and run tests.

Allowed Git commands:

- git status
- git diff
- git log
- git branch
- git show

Do not run git add, git commit, git push, git pull, git merge, or git rebase unless I explicitly ask.

Never run destructive commands unless I explicitly approve the exact command:

- git reset --hard
- git clean -fd
- git clean -fdx
- git checkout .
- git restore .
- rm -rf

Before any commit:

1. Show git status.
2. Show the files to be committed.
3. Summarize the changes.
4. Wait for my confirmation.

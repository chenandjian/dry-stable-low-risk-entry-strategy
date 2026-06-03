# CupHandleScan Phase 1 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 A股杯柄扫描系统的最小可运行版本——获取股票池、拉取行情、过滤流动性、识别杯柄形态、输出 CSV。

**Architecture:** Python CLI 工具，分为 scanner（扫描引擎）、output（输出）、cache（缓存）三层。双线程并发扫描，数据源互斥锁防冲突。新浪/腾讯双源三级回退。

**Tech Stack:** Python 3.10+, AKShare, requests, PyYAML, FastAPI, APScheduler, matplotlib, pytest

**Spec:** `docs/superpowers/specs/2026-06-03-cuphandle-scan-design.md`

---

## 文件结构

```
cuphandle-scan/                          (项目根目录)
├── main.py                              # CLI 入口 + FastAPI 服务 + 调度器
├── config.yaml                          # 配置文件
├── requirements.txt                     # 依赖
├── README.md                            # 项目说明
│
├── scanner/
│   ├── __init__.py                      # 空
│   ├── data_source.py                   # DataSourceManager（互斥锁）+ 抽象基类
│   ├── sina_source.py                   # SinaDataSource（新浪财经 API）
│   ├── tencent_source.py                # TencentDataSource（腾讯财经 API）
│   ├── stock_pool.py                    # 获取 A 股股票池 + 过滤（ST/新股/北交所）
│   ├── liquidity_filter.py              # 成交量/成交额流动性过滤
│   ├── pattern_detector.py              # 杯柄结构识别（SwingHighLow + 杯体 + 柄部）
│   └── scorer.py                        # 形态评分（0-100）
│
├── output/
│   ├── __init__.py                      # 空
│   └── csv_writer.py                    # CSV 候选输出
│
├── scheduler/
│   ├── __init__.py                      # 空
│   └── scheduler.py                     # APScheduler 每日 15:30
│
├── cache/                               # 本地缓存目录（运行时创建）
├── logs/                                # 日志目录（运行时创建）
├── output_data/                         # 输出目录（运行时创建）
│
└── tests/
    ├── __init__.py                      # 空
    ├── test_data_source.py              # 数据源互斥锁测试
    ├── test_liquidity_filter.py         # 流动性过滤测试
    ├── test_pattern_detector.py         # 杯柄识别测试
    └── test_scorer.py                   # 评分测试
```

**关键设计决策：**
- `scanner/` 只负责扫描，不负责输出；`output/` 只负责写文件
- `DataSourceManager` 管理互斥锁，数据源实现类只负责 HTTP 请求和数据解析
- 杯柄检测返回 `CupHandleResult` 数据类，包含所有关键点 + 评分 + 元数据
- CLI 和 FastAPI 共享同一个 `scan_engine`，入口不同但逻辑一致

---

### Task 1: 项目骨架搭建

**Files:**
- Create: `requirements.txt`
- Create: `config.yaml`
- Create: `scanner/__init__.py`
- Create: `output/__init__.py`
- Create: `scheduler/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: 创建 requirements.txt**

```txt
akshare>=1.14.0
requests>=2.31.0
pyyaml>=6.0
fastapi>=0.110.0
uvicorn>=0.29.0
apscheduler>=3.10.4
matplotlib>=3.8.0
pytest>=8.0.0
```

- [ ] **Step 2: 创建 config.yaml**

从 spec 复制完整配置到 `config.yaml`。

- [ ] **Step 3: 创建所有 `__init__.py` 文件**

```bash
touch scanner/__init__.py output/__init__.py scheduler/__init__.py tests/__init__.py
```

- [ ] **Step 4: Commit**

```bash
git add requirements.txt config.yaml scanner/__init__.py output/__init__.py scheduler/__init__.py tests/__init__.py
git commit -m "feat: project skeleton with config and dependencies"
```

---

### Task 2: 数据源管理器（互斥锁）

**Files:**
- Create: `scanner/data_source.py`
- Create: `tests/test_data_source.py`

- [ ] **Step 1: 写 DataSourceManager 测试**

```python
# tests/test_data_source.py
import pytest
import threading
import time
from scanner.data_source import DataSourceManager

def test_acquire_release_single_source():
    """获取和释放单个数据源"""
    mgr = DataSourceManager()
    assert mgr.acquire("sina") is True
    assert mgr.acquire("sina") is False  # 已被占用
    mgr.release("sina")
    assert mgr.acquire("sina") is True   # 释放后可获取
    mgr.release("sina")


def test_two_sources_independent():
    """两个数据源互不影响"""
    mgr = DataSourceManager()
    assert mgr.acquire("sina") is True
    assert mgr.acquire("tencent") is True  # 不同源，不冲突
    mgr.release("sina")
    mgr.release("tencent")


def test_try_acquire_any():
    """自动获取空闲数据源"""
    mgr = DataSourceManager()
    ds = mgr.try_acquire_any()
    assert ds in ("sina", "tencent")
    ds2 = mgr.try_acquire_any()
    assert ds2 in ("sina", "tencent")
    assert ds2 != ds  # 第二个源不同于第一个
    assert mgr.try_acquire_any() is None  # 两个都忙
    mgr.release(ds)
    mgr.release(ds2)


def test_release_always_safe():
    """重复释放不会崩溃"""
    mgr = DataSourceManager()
    mgr.acquire("sina")
    mgr.release("sina")
    mgr.release("sina")  # 不抛异常
    mgr.release("nonexistent")  # 不抛异常


def test_concurrent_access():
    """并发场景：两个线程各取一个源"""
    mgr = DataSourceManager()
    results = []

    def worker(name):
        ds = mgr.try_acquire_any()
        if ds:
            results.append((name, ds))
            time.sleep(0.05)  # 模拟工作
            mgr.release(ds)

    t1 = threading.Thread(target=worker, args=("t1",))
    t2 = threading.Thread(target=worker, args=("t2",))
    t1.start(); t2.start()
    t1.join(); t2.join()

    sources = [r[1] for r in results]
    assert len(sources) == 2
    assert sources[0] != sources[1]  # 不会同时用同一个源
```

- [ ] **Step 2: 运行测试验证失败**

```bash
python -m pytest tests/test_data_source.py -v
```
Expected: 全部 FAIL（类未定义）

- [ ] **Step 3: 实现 DataSourceManager**

```python
# scanner/data_source.py
import threading
import logging

logger = logging.getLogger(__name__)


class DataSourceManager:
    """管理多个数据源的互斥访问。

    每个数据源同一时间只能被一个线程使用。
    使用 threading.Lock 实现非阻塞互斥。
    """

    def __init__(self):
        self._locks: dict[str, threading.Lock] = {
            "sina": threading.Lock(),
            "tencent": threading.Lock(),
        }

    def acquire(self, ds_name: str) -> bool:
        """非阻塞尝试获取数据源锁。成功返回 True，已被占用返回 False。"""
        lock = self._locks.get(ds_name)
        if lock is None:
            logger.warning(f"Unknown data source: {ds_name}")
            return False
        return lock.acquire(blocking=False)

    def release(self, ds_name: str):
        """释放数据源锁。重复释放安全。"""
        lock = self._locks.get(ds_name)
        if lock is None:
            return
        try:
            lock.release()
        except RuntimeError:
            pass  # 锁未被持有，忽略

    def try_acquire_any(self) -> str | None:
        """尝试获取任意一个空闲数据源，返回数据源名称。
        如果全部被占用，返回 None。"""
        for name in self._locks:
            if self.acquire(name):
                return name
        return None

    def is_available(self, ds_name: str) -> bool:
        """检查数据源是否空闲（不获取锁）。"""
        lock = self._locks.get(ds_name)
        if lock is None:
            return False
        return lock.locked() is False
```

- [ ] **Step 4: 运行测试验证通过**

```bash
python -m pytest tests/test_data_source.py -v
```
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add scanner/data_source.py tests/test_data_source.py
git commit -m "feat: add DataSourceManager with mutex locks for sina/tencent"
```

---

### Task 3: 新浪 + 腾讯数据源实现

**Files:**
- Create: `scanner/sina_source.py`
- Create: `scanner/tencent_source.py`

- [ ] **Step 1: 实现新浪数据源**

```python
# scanner/sina_source.py
import requests
import logging

logger = logging.getLogger(__name__)

SINA_API = "https://vip.stock.finance.sina.com.cn/market/json/jsonpdata.php"


def fetch_sina_daily(code: str, days: int = 250) -> list[dict] | None:
    """从新浪获取单只股票的日线数据。

    Args:
        code: 股票代码，如 '600036' 或 '000001'
        days: 获取最近 N 个交易日数据

    Returns:
        list[dict]: [{date, open, high, low, close, volume, turnover}, ...]
        按日期升序排列。失败返回 None。
    """
    # 判断交易所前缀
    if code.startswith("6"):
        symbol = f"sh{code}"
    else:
        symbol = f"sz{code}"

    url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData/getKLineData"
    params = {
        "symbol": symbol,
        "scale": "240",  # 日线
        "ma": "no",
        "datalen": str(days),
    }

    try:
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        raw_data = resp.json()

        if not raw_data or not isinstance(raw_data, list):
            logger.warning(f"Sina returned empty/invalid data for {code}")
            return None

        result = []
        for item in raw_data:
            result.append({
                "date": item["day"],
                "open": float(item["open"]),
                "high": float(item["high"]),
                "low": float(item["low"]),
                "close": float(item["close"]),
                "volume": float(item["volume"]),
                "turnover": float(item.get("volume", 0)) * float(item.get("close", 0)) / 10000,
                # 新浪不直接返回成交额，需要估算。更准确的数据用腾讯源。
            })
        return result

    except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as e:
        logger.warning(f"Sina fetch failed for {code}: {e}")
        return None
    except (ValueError, KeyError, TypeError) as e:
        logger.warning(f"Sina parse error for {code}: {e}")
        return None
```

- [ ] **Step 2: 实现腾讯数据源**

```python
# scanner/tencent_source.py
import requests
import logging

logger = logging.getLogger(__name__)


def fetch_tencent_daily(code: str, days: int = 250) -> list[dict] | None:
    """从腾讯财经获取单只股票的日线数据。

    Args:
        code: 股票代码，如 '600036' 或 '000001'
        days: 获取最近 N 个交易日数据

    Returns:
        list[dict]: [{date, open, high, low, close, volume, turnover}, ...]
        按日期升序排列。失败返回 None。
    """
    if code.startswith("6"):
        symbol = f"sh{code}"
    else:
        symbol = f"sz{code}"

    url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    params = {
        "param": f"{symbol},day,,,{days}",
        "_var": "kline_day",
    }

    try:
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        text = resp.text

        # 响应格式: kline_day={...json...}
        # 去除前缀
        json_str = text.split("=", 1)[1].strip() if "=" in text else text
        import json
        data = json.loads(json_str)

        # 路径: data -> symbol -> qfqday (前复权日线) 或 day (不复权)
        stock_data = data.get("data", {}).get(symbol, {})
        klines = stock_data.get("qfqday") or stock_data.get("day", [])

        if not klines:
            logger.warning(f"Tencent returned empty data for {code}")
            return None

        result = []
        for item in klines:
            # 腾讯格式: ["2026-06-03", "42.000", "43.000", "41.500", "42.850", "123456.00"]
            #           [date, open, close, high, low, volume]
            # 注意腾讯的字段顺序和常规不同：open, close, high, low
            result.append({
                "date": item[0],
                "open": float(item[1]),
                "close": float(item[2]),
                "high": float(item[3]),
                "low": float(item[4]),
                "volume": float(item[5]),
                "turnover": None,  # 腾讯日线不直接给成交额
            })
        return result

    except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as e:
        logger.warning(f"Tencent fetch failed for {code}: {e}")
        return None
    except (ValueError, KeyError, IndexError, json.JSONDecodeError) as e:
        logger.warning(f"Tencent parse error for {code}: {e}")
        return None
```

- [ ] **Step 3: Commit**

```bash
git add scanner/sina_source.py scanner/tencent_source.py
git commit -m "feat: add Sina and Tencent daily data fetchers"
```

---

### Task 4: 股票池获取与过滤

**Files:**
- Create: `scanner/stock_pool.py`

- [ ] **Step 1: 实现股票池获取（AKShare + 本地缓存回退）**

```python
# scanner/stock_pool.py
import logging
import json
import os

logger = logging.getLogger(__name__)

CACHE_FILE = "cache/stock_pool.json"


def get_a_stock_pool(config: dict) -> list[dict]:
    """获取 A 股股票池，过滤 ST/新股/北交所。

    Returns:
        list[dict]: [{code, name, market, listing_date}, ...]
    """
    # 1. 尝试 AKShare
    try:
        import akshare as ak
        df = ak.stock_info_a_code_name()
        stocks = []
        for _, row in df.iterrows():
            code = str(row["code"]).zfill(6)
            name = str(row["name"])
            stocks.append({"code": code, "name": name})
        logger.info(f"AKShare: got {len(stocks)} stocks")
        if stocks:
            _save_cache(stocks)
            return _filter_stocks(stocks, config)
    except Exception as e:
        logger.warning(f"AKShare stock pool failed: {e}")

    # 2. 回退本地缓存
    cached = _load_cache()
    if cached:
        logger.info(f"Using cached stock pool: {len(cached)} stocks")
        return _filter_stocks(cached, config)

    # 3. TODO: 后续可加新浪股票列表作为 last resort
    logger.error("Cannot get stock pool from any source")
    return []


def _filter_stocks(stocks: list[dict], config: dict) -> list[dict]:
    """过滤 ST/*ST/北交所/新股。"""
    market_cfg = config.get("market", {})
    result = []

    for s in stocks:
        code = s["code"]
        name = s["name"]

        # 排除 ST
        if market_cfg.get("exclude_st", True) and ("ST" in name or "*ST" in name):
            continue

        # 排除北交所（8 开头、4 开头）
        if market_cfg.get("exclude_bj", True) and (code.startswith("8") or code.startswith("4")):
            continue

        # 判断市场
        if code.startswith("688"):
            if not market_cfg.get("include_kcb", True):
                continue
            s["market"] = "科创板"
        elif code.startswith("300") or code.startswith("301"):
            if not market_cfg.get("include_cyb", True):
                continue
            s["market"] = "创业板"
        elif code.startswith("6"):
            if not market_cfg.get("include_sh", True):
                continue
            s["market"] = "上证主板"
        elif code.startswith("0") or code.startswith("002") or code.startswith("003"):
            if not market_cfg.get("include_sz", True):
                continue
            s["market"] = "深证主板"
        else:
            continue  # 不认识的代码，跳过

        result.append(s)

    logger.info(f"Stock pool after filter: {len(result)} (from {len(stocks)})")
    return result


def _save_cache(stocks: list[dict]):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(stocks, f, ensure_ascii=False)


def _load_cache() -> list[dict] | None:
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
```

- [ ] **Step 2: Commit**

```bash
git add scanner/stock_pool.py
git commit -m "feat: add A-share stock pool with AKShare + cache fallback"
```

---

### Task 5: 流动性过滤

**Files:**
- Create: `scanner/liquidity_filter.py`
- Create: `tests/test_liquidity_filter.py`

- [ ] **Step 1: 写测试**

```python
# tests/test_liquidity_filter.py
import pytest
from scanner.liquidity_filter import passes_liquidity_filter, _avg


def test_avg():
    assert _avg([1, 2, 3]) == 2.0
    assert _avg([10]) == 10.0
    assert _avg([]) == 0.0


def test_passes_with_sufficient_liquidity():
    """流动性充足的股票应通过"""
    data = _make_data(close=40.0, volume=10_000_000, count=30)
    config = {
        "enabled": True,
        "avg_turnover_days": 20,
        "min_avg_turnover": 100_000_000,
        "min_avg_volume": 5_000_000,
        "min_latest_turnover": 80_000_000,
    }
    assert passes_liquidity_filter(data, config) is True


def test_fails_low_turnover():
    """成交额不足应拒绝"""
    data = _make_data(close=1.0, volume=1_000_000, count=30)  # turnouver ~1M
    config = {
        "enabled": True,
        "avg_turnover_days": 20,
        "min_avg_turnover": 100_000_000,
        "min_avg_volume": 5_000_000,
        "min_latest_turnover": 80_000_000,
    }
    assert passes_liquidity_filter(data, config) is False


def test_disabled_filter_always_passes():
    """流动性过滤关闭时直接通过"""
    data = _make_data(close=0.01, volume=100, count=5)
    config = {"enabled": False}
    assert passes_liquidity_filter(data, config) is True


def test_empty_data_fails():
    """空数据不通过"""
    assert passes_liquidity_filter([], {"enabled": True}) is False


def test_insufficient_days():
    """数据天数不足时不通过"""
    data = _make_data(close=40.0, volume=10_000_000, count=5)
    config = {"enabled": True, "avg_turnover_days": 20}
    assert passes_liquidity_filter(data, config) is False


def _make_data(close: float, volume: int, count: int) -> list[dict]:
    return [
        {
            "date": f"2026-06-{str(i+1).zfill(2)}",
            "open": close * 0.99,
            "high": close * 1.02,
            "low": close * 0.98,
            "close": close,
            "volume": volume,
            "turnover": close * volume,
        }
        for i in range(count)
    ]
```

- [ ] **Step 2: 运行测试验证失败**

```bash
python -m pytest tests/test_liquidity_filter.py -v
```

- [ ] **Step 3: 实现流动性过滤**

```python
# scanner/liquidity_filter.py
import logging

logger = logging.getLogger(__name__)


def passes_liquidity_filter(data: list[dict], config: dict) -> bool:
    """检查股票是否通过流动性过滤。

    Args:
        data: 日线数据列表，按日期升序
        config: liquidity 配置段

    Returns:
        True 如果通过或过滤已关闭
    """
    if not config.get("enabled", True):
        return True

    if not data or len(data) < config.get("avg_turnover_days", 20):
        return False

    n = config["avg_turnover_days"]
    recent = data[-n:]  # 最近 N 日
    latest = data[-1]

    # 1. 最近 N 日平均成交额
    turnovers = [d.get("turnover") or (d["volume"] * d["close"]) for d in recent]
    avg_turnover = _avg(turnovers)
    if avg_turnover < config.get("min_avg_turnover", 100_000_000):
        logger.debug(f"  liquidity fail: avg_turnover={avg_turnover:,.0f} < {config['min_avg_turnover']:,.0f}")
        return False

    # 2. 最近 N 日平均成交量
    volumes = [d["volume"] for d in recent]
    avg_volume = _avg(volumes)
    if avg_volume < config.get("min_avg_volume", 5_000_000):
        logger.debug(f"  liquidity fail: avg_volume={avg_volume:,.0f} < {config['min_avg_volume']:,.0f}")
        return False

    # 3. 最近 1 日成交额
    latest_turnover = latest.get("turnover") or (latest["volume"] * latest["close"])
    if latest_turnover < config.get("min_latest_turnover", 80_000_000):
        logger.debug(f"  liquidity fail: latest_turnover={latest_turnover:,.0f} < {config['min_latest_turnover']:,.0f}")
        return False

    return True


def _avg(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)
```

- [ ] **Step 4: 运行测试验证通过**

```bash
python -m pytest tests/test_liquidity_filter.py -v
```

- [ ] **Step 5: Commit**

```bash
git add scanner/liquidity_filter.py tests/test_liquidity_filter.py
git commit -m "feat: add liquidity filter (turnover/volume thresholds)"
```

---

### Task 6: 杯柄结构识别算法

**Files:**
- Create: `scanner/pattern_detector.py`
- Create: `tests/test_pattern_detector.py`

这是核心算法模块。按 spec 实现：识别 Swing High/Low → 左杯口 → 杯底 → 右杯口 → 柄部低点 → 突破判断。

- [ ] **Step 1: 写 Swing High/Low 检测测试**

```python
# tests/test_pattern_detector.py
import pytest
from scanner.pattern_detector import (
    find_swing_highs,
    find_swing_lows,
    detect_cup_handle,
    CupHandleResult,
)

# ---- Swing High/Low Tests ----


def test_find_swing_highs_simple():
    """Swing High 是局部最大值（比左右 N 天都高）"""
    closes = [10, 12, 15, 13, 11, 14, 16, 14]
    highs = find_swing_highs(closes, window=2)
    assert 2 in highs  # index 2 = 15, 比左右都高
    assert 6 in highs  # index 6 = 16, 比左右都高


def test_find_swing_lows_simple():
    """Swing Low 是局部最小值"""
    closes = [10, 8, 6, 9, 7, 5, 8, 9]
    lows = find_swing_lows(closes, window=2)
    assert 2 in lows  # index 2 = 6
    assert 5 in lows  # index 5 = 5


def test_swing_empty_data():
    assert find_swing_highs([], window=3) == []
    assert find_swing_lows([], window=3) == []


def test_swing_short_data():
    assert find_swing_highs([10, 12], window=3) == []
```

- [ ] **Step 2: 实现 Swing 检测**

```python
# scanner/pattern_detector.py (第一部分)
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class CupHandleResult:
    """杯柄检测结果"""
    found: bool = False
    code: str = ""
    name: str = ""

    # 关键点索引
    left_high_idx: int = -1
    cup_low_idx: int = -1
    right_high_idx: int = -1
    handle_low_idx: int = -1

    # 关键点日期
    left_high_date: str = ""
    cup_low_date: str = ""
    right_high_date: str = ""
    handle_low_date: str = ""

    # 关键点价格
    left_high_price: float = 0.0
    cup_low_price: float = 0.0
    right_high_price: float = 0.0
    handle_low_price: float = 0.0

    # 结构参数
    cup_duration: int = 0       # 杯体交易日
    cup_depth_pct: float = 0.0  # 杯体回撤 %
    handle_duration: int = 0    # 柄部交易日
    handle_depth_pct: float = 0.0  # 柄部回撤 %
    lip_deviation_pct: float = 0.0  # 左右杯口偏差 %

    # 突破判断
    is_breakout: bool = False
    is_volume_breakout: bool = False
    breakout_price: float = 0.0
    vol_multiplier: float = 0.0

    # 元数据
    score: int = 0
    rating: str = ""


def find_swing_highs(closes: list[float], window: int = 5) -> list[int]:
    """找出局部高点索引。

    一个点被认为是 Swing High 当它在左右各 window 天内都是最高价。
    """
    if len(closes) < 2 * window + 1:
        return []

    highs = []
    n = len(closes)
    for i in range(window, n - window):
        left_max = max(closes[i - window:i])
        right_max = max(closes[i + 1:i + window + 1])
        if closes[i] > left_max and closes[i] > right_max:
            highs.append(i)
    return highs


def find_swing_lows(lows: list[float], window: int = 5) -> list[int]:
    """找出局部低点索引。"""
    if len(lows) < 2 * window + 1:
        return []

    result = []
    n = len(lows)
    for i in range(window, n - window):
        left_min = min(lows[i - window:i])
        right_min = min(lows[i + 1:i + window + 1])
        if lows[i] < left_min and lows[i] < right_min:
            result.append(i)
    return result
```

- [ ] **Step 3: 运行 Swing 测试**

```bash
python -m pytest tests/test_pattern_detector.py::test_find_swing -v
```

- [ ] **Step 4: 写杯柄检测集成测试**

```python
# tests/test_pattern_detector.py (续)

def test_detect_cup_handle_no_pattern():
    """无杯柄形态的随机数据应返回 found=False"""
    import random
    random.seed(42)
    closes = [100.0]
    for _ in range(200):
        closes.append(closes[-1] * (1 + random.uniform(-0.03, 0.03)))
    data = _make_ohlc_data(closes)
    result = detect_cup_handle(data, {})
    assert result.found is False


def test_detect_cup_handle_ideal_pattern():
    """构造理想杯柄形态，应该能检测到"""
    # 构建理想杯柄走势
    prices = _build_cup_handle_prices(
        pre_trend_start=50.0,
        pre_trend_end=65.0,    # 涨 30%
        left_high=65.0,
        cup_low=52.0,          # 回撤 ~20%
        right_high=62.0,       # 略低于左杯口
        handle_low=58.0,       # 柄部回撤 ~6.5%
        breakout=64.0,         # 突破
    )
    data = _make_ohlc_data(prices)
    config = {
        "min_duration": 35,
        "max_duration": 180,
        "min_depth": 0.12,
        "max_depth": 0.45,
        "max_lip_deviation": 0.12,
        "min_bottom_roundness": 0.10,
    }
    result = detect_cup_handle(data, config)
    assert result.found is True
    assert 20 <= result.cup_depth_pct <= 40
    assert result.left_high_idx < result.cup_low_idx < result.right_high_idx


def _build_cup_handle_prices(
    pre_trend_start, pre_trend_end,
    left_high, cup_low, right_high, handle_low, breakout,
    pre_trend_days=40, cup_down_days=35, cup_bottom_days=20,
    cup_up_days=35, handle_days=15, post_days=5
) -> list[float]:
    """构造理想杯柄价格序列。"""
    import math
    prices = []

    # 前置上涨
    for i in range(pre_trend_days):
        t = i / pre_trend_days
        prices.append(pre_trend_start + (pre_trend_end - pre_trend_start) * t)

    # 左杯口到杯底（下跌）
    for i in range(cup_down_days):
        t = i / cup_down_days
        # 圆弧下跌
        prices.append(left_high - (left_high - cup_low) * math.sin(t * math.pi / 2))

    # 杯底区域（横向整理）
    for i in range(cup_bottom_days):
        noise = (i % 3 - 1) * 0.5
        prices.append(cup_low + 1.0 + noise)

    # 杯底到右杯口（上涨）
    for i in range(cup_up_days):
        t = i / cup_up_days
        prices.append(cup_low + (right_high - cup_low) * math.sin(t * math.pi / 2))

    # 柄部（小幅回调）
    for i in range(handle_days):
        t = i / handle_days
        prices.append(right_high - (right_high - handle_low) * t)

    # 突破后
    for i in range(post_days):
        prices.append(breakout + i * 0.3)

    return prices


def _make_ohlc_data(closes: list[float]) -> list[dict]:
    """从收盘价序列生成 OHLC 数据（简化，OHLC 围绕 close 浮动）。"""
    import random
    random.seed(1)
    result = []
    for i, c in enumerate(closes):
        vol = random.uniform(8_000_000, 15_000_000)
        result.append({
            "date": f"2025-{str(i//20 + 1).zfill(2)}-{str(i%20 + 1).zfill(2)}",
            "open": c * random.uniform(0.98, 1.02),
            "high": c * random.uniform(1.01, 1.05),
            "low": c * random.uniform(0.95, 0.99),
            "close": c,
            "volume": vol,
            "turnover": c * vol,
        })
    return result
```

- [ ] **Step 5: 实现完整杯柄检测算法**

```python
# scanner/pattern_detector.py (第二部分: detect_cup_handle)

def detect_cup_handle(data: list[dict], config: dict) -> CupHandleResult:
    """检测单只股票是否存在杯柄结构。

    Args:
        data: 日线数据，按日期升序，长度 >= 250
        config: cup + handle + breakout 配置合并字典

    Returns:
        CupHandleResult
    """
    result = CupHandleResult()

    if len(data) < 120:
        return result

    closes = [d["close"] for d in data]
    highs = [d["high"] for d in data]
    lows = [d["low"] for d in data]

    # Step 1: 找 Swing 点
    sw_highs = find_swing_highs(closes, window=5)
    sw_lows = find_swing_lows(lows, window=5)

    if len(sw_highs) < 2 or len(sw_lows) < 1:
        return result

    # Step 2: 遍历可能的杯体组合
    cup_min_dur = config.get("min_duration", 35)
    cup_max_dur = config.get("max_duration", 180)
    min_depth = config.get("min_depth", 0.12)
    max_depth = config.get("max_depth", 0.45)
    max_lip_dev = config.get("max_lip_deviation", 0.12)

    best = None
    best_score = 0

    for lh_idx in sw_highs:
        left_high = closes[lh_idx]
        for cl_idx in sw_lows:
            cup_low = lows[cl_idx]
            if cl_idx <= lh_idx:
                continue
            cup_dur = cl_idx - lh_idx
            if cup_dur < cup_min_dur or cup_dur > cup_max_dur:
                continue
            depth = (left_high - cup_low) / left_high
            if depth < min_depth or depth > max_depth:
                continue

            # 找右杯口：杯底之后第一个接近左杯口的 Swing High
            for rh_idx in sw_highs:
                if rh_idx <= cl_idx:
                    continue
                right_high = closes[rh_idx]
                lip_dev = abs(right_high - left_high) / left_high
                if lip_dev > max_lip_dev:
                    continue
                right_dur = rh_idx - cl_idx
                if right_dur < cup_dur * 0.25:
                    continue  # 右侧太陡 → V 型

                # Step 3: 杯底圆滑度
                bottom_zone = [i for i in range(lh_idx, rh_idx) if closes[i] <= cup_low * 1.08]
                roundness = len(bottom_zone) / cup_dur if cup_dur > 0 else 0
                min_round = config.get("min_bottom_roundness", 0.15)
                if roundness < min_round:
                    continue

                # Step 4: 找柄部
                handle_result = _find_handle(
                    data, config,
                    right_high_idx=rh_idx,
                    cup_low_idx=cl_idx,
                    right_high=right_high,
                    cup_low=cup_low,
                )

                if handle_result is None:
                    continue

                # 计算综合评分（粗略版）
                cup_quality = _score_cup(depth, cup_dur, lip_dev, roundness)
                handle_quality = handle_result["quality"]
                total = cup_quality * 0.5 + handle_quality * 0.3

                if total > best_score:
                    best_score = total
                    best = {
                        "left_high_idx": lh_idx,
                        "cup_low_idx": cl_idx,
                        "right_high_idx": rh_idx,
                        "handle_low_idx": handle_result["low_idx"],
                        "left_high_price": left_high,
                        "cup_low_price": cup_low,
                        "right_high_price": right_high,
                        "handle_low_price": handle_result["low_price"],
                        "cup_duration": cup_dur,
                        "cup_depth_pct": round(depth * 100, 1),
                        "handle_duration": handle_result["duration"],
                        "handle_depth_pct": round(handle_result["depth_pct"] * 100, 1),
                        "lip_deviation_pct": round(lip_dev * 100, 1),
                        "is_breakout": handle_result.get("is_breakout", False),
                        "is_volume_breakout": handle_result.get("is_volume_breakout", False),
                        "vol_multiplier": round(handle_result.get("vol_multiplier", 0), 1),
                        "breakout_price": max(left_high, right_high),
                        "bottom_roundness": round(roundness, 3),
                    }

    if best is None:
        return result

    result.found = True
    for k, v in best.items():
        setattr(result, k, v)
    result.left_high_date = data[best["left_high_idx"]]["date"]
    result.cup_low_date = data[best["cup_low_idx"]]["date"]
    result.right_high_date = data[best["right_high_idx"]]["date"]
    result.handle_low_date = data[best["handle_low_idx"]]["date"]

    return result


def _find_handle(data, config, right_high_idx, cup_low_idx, right_high, cup_low):
    """在右杯口之后寻找柄部结构。"""
    n = len(data)
    min_dur = config.get("min_duration", 5)
    max_dur = config.get("max_duration", 30)
    max_depth = config.get("max_depth", 0.18)
    max_vs_right = config.get("max_vs_right_rally", 0.50)

    if right_high_idx >= n - min_dur:
        return None

    right_rally = right_high - cup_low

    search_end = min(right_high_idx + max_dur + 10, n)
    low_idx = right_high_idx + 1
    low_price = float("inf")

    for i in range(right_high_idx + 1, search_end):
        if data[i]["low"] < low_price:
            low_price = data[i]["low"]
            low_idx = i

    duration = low_idx - right_high_idx
    if duration < min_dur or duration > max_dur:
        return None

    depth = (right_high - low_price) / right_high
    if depth > max_depth:
        return None

    if right_rally > 0 and (right_high - low_price) / right_rally > max_vs_right:
        return None

    # 质量：柄部越浅越好
    quality = max(0, (max_depth - depth) / max_depth)

    # 检查突破
    breakout_price = right_high  # 简化：突破位 = 右杯口
    latest = data[-1]
    is_breakout = latest["close"] > breakout_price * 1.02
    is_vol_breakout = False
    vol_mult = 0.0

    if is_breakout:
        recent_vols = [d["volume"] for d in data[-20:]]
        avg_vol = sum(recent_vols) / len(recent_vols) if recent_vols else 0
        if avg_vol > 0:
            vol_mult = latest["volume"] / avg_vol
            is_vol_breakout = vol_mult >= 1.5

    return {
        "low_idx": low_idx,
        "low_price": low_price,
        "duration": duration,
        "depth_pct": depth,
        "quality": quality,
        "is_breakout": is_breakout,
        "is_volume_breakout": is_vol_breakout,
        "vol_multiplier": vol_mult,
    }


def _score_cup(depth, duration, lip_dev, roundness):
    """杯体质量评分（0-1 归一化）。"""
    s = 0.0
    # 深度 12-33% 最优
    if 0.12 <= depth <= 0.33:
        s += 0.4
    elif 0.33 < depth <= 0.45:
        s += 0.2
    # 持续时间合理
    if 50 <= duration <= 120:
        s += 0.2
    elif 35 <= duration <= 180:
        s += 0.1
    # 杯口接近
    if lip_dev <= 0.05:
        s += 0.2
    elif lip_dev <= 0.12:
        s += 0.1
    # 杯底圆滑
    if roundness >= 0.20:
        s += 0.2
    elif roundness >= 0.15:
        s += 0.1
    return min(s, 1.0)
```

- [ ] **Step 6: 运行完整测试**

```bash
python -m pytest tests/test_pattern_detector.py -v
```

- [ ] **Step 7: Commit**

```bash
git add scanner/pattern_detector.py tests/test_pattern_detector.py
git commit -m "feat: add Cup & Handle pattern detection algorithm"
```

---

### Task 7: 形态评分

**Files:**
- Create: `scanner/scorer.py`
- Create: `tests/test_scorer.py`

- [ ] **Step 1: 写评分测试**

```python
# tests/test_scorer.py
import pytest
from scanner.scorer import score_cup_handle
from scanner.pattern_detector import CupHandleResult


def test_perfect_pattern_scores_high():
    """理想杯柄应得高分"""
    r = CupHandleResult(
        found=True,
        cup_depth_pct=20.0,
        cup_duration=65,
        lip_deviation_pct=3.0,
        handle_depth_pct=5.0,
        handle_duration=12,
        is_breakout=True,
        is_volume_breakout=True,
        vol_multiplier=1.8,
    )
    score = score_cup_handle(r)
    assert score >= 80, f"Expected >=80, got {score}"


def test_shallow_cup_scores_lower():
    """过浅的杯体降分"""
    r = CupHandleResult(
        found=True,
        cup_depth_pct=8.0,   # <12%, 太浅
        cup_duration=40,
        lip_deviation_pct=5.0,
        handle_depth_pct=5.0,
        handle_duration=10,
        is_breakout=False,
        is_volume_breakout=False,
    )
    score = score_cup_handle(r)
    assert score < 70


def test_no_pattern_scores_zero():
    r = CupHandleResult(found=False)
    assert score_cup_handle(r) == 0
```

- [ ] **Step 2: 实现评分算法**

```python
# scanner/scorer.py
from scanner.pattern_detector import CupHandleResult


def score_cup_handle(result: CupHandleResult) -> int:
    """计算杯柄形态综合评分 (0-100)。

    评分维度（按 spec）:
      - 杯体结构: 35 分
      - 柄部结构: 25 分
      - 成交量结构: 20 分 (Phase 2 完善)
      - 前置上涨趋势: 10 分 (Phase 2 完善)
      - 突破确认: 10 分
    """
    if not result.found:
        return 0

    score = 0

    # 1. 杯体结构 (35 分)
    # 深度合理 (10 分)
    depth = result.cup_depth_pct
    if 12 <= depth <= 33:
        score += 10
    elif 33 < depth <= 45:
        score += 5
    elif depth < 12:
        score += 3  # 过浅，部分分数

    # 持续时间合理 (8 分)
    dur = result.cup_duration
    if 50 <= dur <= 120:
        score += 8
    elif 35 <= dur <= 180:
        score += 4

    # 左右杯口接近 (7 分)
    dev = result.lip_deviation_pct
    if dev <= 5:
        score += 7
    elif dev <= 8:
        score += 5
    elif dev <= 12:
        score += 3

    # 杯底圆滑 (10 分) - Phase 2 可精细判断，Phase 1 给基础分
    score += 6  # Phase 1 默认中等

    # 2. 柄部结构 (25 分)
    h_dur = result.handle_duration
    if 5 <= h_dur <= 20:
        score += 8
    elif 20 < h_dur <= 30:
        score += 5

    h_depth = result.handle_depth_pct
    if h_depth <= 8:
        score += 10
    elif h_depth <= 12:
        score += 7
    elif h_depth <= 18:
        score += 3

    # 柄部横盘/小幅下倾 (7 分)
    if h_depth <= 10:
        score += 7
    elif h_depth <= 15:
        score += 4

    # 3. 成交量结构 (20 分) - Phase 1 基础分
    score += 10

    # 4. 前置上涨趋势 (10 分) - Phase 1 基础分
    score += 6

    # 5. 突破确认 (10 分)
    if result.is_breakout and result.is_volume_breakout:
        score += 10
    elif result.is_breakout:
        score += 7
    else:
        score += 3  # 未突破给少量基础分

    return min(score, 100)
```

- [ ] **Step 3: 运行测试**

```bash
python -m pytest tests/test_scorer.py -v
```

- [ ] **Step 4: Commit**

```bash
git add scanner/scorer.py tests/test_scorer.py
git commit -m "feat: add cup-handle scoring system (0-100)"
```

---

### Task 8: CSV 输出

**Files:**
- Create: `output/csv_writer.py`

- [ ] **Step 1: 实现 CSV 输出**

```python
# output/csv_writer.py
import csv
import os
import logging
from datetime import datetime
from scanner.pattern_detector import CupHandleResult

logger = logging.getLogger(__name__)

CSV_HEADER = [
    "股票代码", "股票名称", "形态评分", "信号等级",
    "突破状态", "放量确认", "最新收盘价", "突破位",
    "距突破位比例", "杯体回撤深度", "杯体周期",
    "柄部回撤幅度", "柄部周期",
    "左杯口日期", "杯底日期", "右杯口日期", "柄部低点日期",
    "最近20日平均成交额", "最新成交额", "放量倍数",
]


def write_candidates_csv(
    candidates: list[tuple[dict, CupHandleResult]],
    output_dir: str = "./output_data",
) -> str:
    """写入候选股票 CSV 文件。

    Args:
        candidates: [(stock_info, cup_handle_result), ...]
        output_dir: 输出目录

    Returns:
        CSV 文件路径
    """
    os.makedirs(output_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"candidates_{date_str}.csv"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER)

        for stock, result in candidates:
            # 分级
            if result.score >= 80:
                rating = "强候选"
            elif result.score >= 70:
                rating = "中等候选"
            elif result.score >= 60:
                rating = "弱候选"
            else:
                continue  # < 60 分不输出

            # 距突破位比例
            latest_close = stock.get("latest_close", 0)
            bp = result.breakout_price
            dist_pct = f"{(latest_close - bp) / bp * 100:+.1f}%" if bp > 0 else "N/A"

            writer.writerow([
                stock.get("code", ""),
                stock.get("name", ""),
                result.score,
                rating,
                "已突破" if result.is_breakout else "未突破",
                "是" if result.is_volume_breakout else "否",
                f"{latest_close:.2f}",
                f"{result.breakout_price:.2f}",
                dist_pct,
                f"{result.cup_depth_pct:.1f}%",
                result.cup_duration,
                f"{result.handle_depth_pct:.1f}%",
                result.handle_duration,
                result.left_high_date,
                result.cup_low_date,
                result.right_high_date,
                result.handle_low_date,
                stock.get("avg_turnover_20", "N/A"),
                stock.get("latest_turnover", "N/A"),
                f"{result.vol_multiplier:.1f}×",
            ])

    logger.info(f"CSV written: {filepath} ({len(candidates)} candidates)")
    return filepath
```

- [ ] **Step 2: Commit**

```bash
git add output/csv_writer.py
git commit -m "feat: add CSV candidate output writer"
```

---

### Task 9: 扫描引擎 + CLI 入口

**Files:**
- Create: `scanner/engine.py`
- Create: `main.py`

- [ ] **Step 1: 实现扫描引擎**

```python
# scanner/engine.py
import time
import logging
import threading
from queue import Queue

from scanner.data_source import DataSourceManager
from scanner.sina_source import fetch_sina_daily
from scanner.tencent_source import fetch_tencent_daily
from scanner.liquidity_filter import passes_liquidity_filter
from scanner.pattern_detector import detect_cup_handle
from scanner.scorer import score_cup_handle

logger = logging.getLogger(__name__)


def scan_all(config: dict, progress_callback=None) -> dict:
    """双线程全市场扫描。

    Args:
        config: 完整配置
        progress_callback: 可选进度回调 fn(stage, current, total, detail)

    Returns:
        {"candidates": [...], "stats": {...}, "task_id": "..."}
    """
    from scanner.stock_pool import get_a_stock_pool

    stocks = get_a_stock_pool(config)
    if not stocks:
        logger.error("Empty stock pool, aborting")
        return {"candidates": [], "stats": {"error": "empty_pool"}}

    stock_queue = Queue()
    for s in stocks:
        stock_queue.put(s)

    mgr = DataSourceManager()
    candidates = []
    candidate_lock = threading.Lock()
    scanned_count = [0]
    skip_count = [0]
    stats_lock = threading.Lock()

    cup_cfg = config.get("cup", {})
    handle_cfg = config.get("handle", {})
    breakout_cfg = config.get("breakout", {})
    liquidity_cfg = config.get("liquidity", {})
    pattern_cfg = {**cup_cfg, **handle_cfg, **breakout_cfg}

    start_time = time.time()

    def worker(thread_name: str):
        while not stock_queue.empty():
            try:
                stock = stock_queue.get_nowait()
            except Exception:
                break

            ds = mgr.try_acquire_any()
            if ds is None:
                time.sleep(0.1)
                stock_queue.put(stock)
                continue

            code = stock["code"]
            try:
                # 三级回退获取数据
                data = _fetch_with_fallback(code, ds, mgr)
                if data is None:
                    with stats_lock:
                        skip_count[0] += 1
                    continue

                # 存储最新价等元数据
                stock["latest_close"] = data[-1]["close"]
                stock["latest_turnover"] = data[-1].get("turnover") or (data[-1]["volume"] * data[-1]["close"])

                # 流动性过滤
                if not passes_liquidity_filter(data, liquidity_cfg):
                    with stats_lock:
                        skip_count[0] += 1
                    continue

                # 杯柄检测
                result = detect_cup_handle(data, pattern_cfg)
                if result.found:
                    result.code = code
                    result.name = stock.get("name", "")
                    result.score = score_cup_handle(result)
                    if result.score >= 60:
                        with candidate_lock:
                            candidates.append((stock, result))

                with stats_lock:
                    scanned_count[0] += 1

                if progress_callback:
                    progress_callback("scanning", scanned_count[0], len(stocks), f"{code} {stock.get('name','')}")

            except Exception as e:
                logger.error(f"Error scanning {code}: {e}")
                with stats_lock:
                    skip_count[0] += 1
            finally:
                mgr.release(ds)

    # 启动双线程
    t1 = threading.Thread(target=worker, args=("t1",), daemon=True)
    t2 = threading.Thread(target=worker, args=("t2",), daemon=True)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    elapsed = time.time() - start_time

    # 按评分排序
    candidates.sort(key=lambda x: x[1].score, reverse=True)

    return {
        "candidates": candidates,
        "stats": {
            "total_stocks": len(stocks),
            "scanned": scanned_count[0],
            "skipped": skip_count[0],
            "candidates_found": len(candidates),
            "elapsed_seconds": round(elapsed, 1),
            "speed": round(scanned_count[0] / elapsed, 1) if elapsed > 0 else 0,
        },
        "task_id": time.strftime("%Y%m%d-%H%M%S"),
    }


def _fetch_with_fallback(code: str, primary_ds: str, mgr: DataSourceManager):
    """三级回退：主源 → 备用源 → 缓存。"""
    import json, os

    fetch_fn = fetch_sina_daily if primary_ds == "sina" else fetch_tencent_daily
    data = fetch_fn(code)

    if data:
        return data

    # 回退另一个数据源
    other = "tencent" if primary_ds == "sina" else "sina"
    if mgr.acquire(other):
        try:
            fetch_fn2 = fetch_tencent_daily if other == "tencent" else fetch_sina_daily
            data = fetch_fn2(code)
            if data:
                return data
        finally:
            mgr.release(other)

    # 回退本地缓存
    cache_path = f"cache/daily/{code}.json"
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    return None
```

- [ ] **Step 2: 实现 CLI 入口**

```python
# main.py
import argparse
import logging
import sys
import yaml
import os

from scanner.engine import scan_all
from output.csv_writer import write_candidates_csv


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def setup_logging(config: dict):
    log_dir = config.get("output", {}).get("log_dir", "./logs")
    os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(
                os.path.join(log_dir, f"scan_{__import__('time').strftime('%Y-%m-%d')}.log"),
                encoding="utf-8",
            ),
            logging.StreamHandler(sys.stdout),
        ],
    )


def cmd_scan(args):
    """执行全市场或单只股票扫描。"""
    config = load_config(args.config)
    setup_logging(config)
    logger = logging.getLogger("main")

    logger.info("=" * 60)
    logger.info("CupHandleScan - A股杯柄结构扫描")
    logger.info("=" * 60)

    result = scan_all(config)
    stats = result["stats"]
    candidates = result["candidates"]

    logger.info(f"扫描完成: {stats['total_stocks']} 只, "
                f"成功 {stats['scanned']}, 跳过 {stats['skipped']}, "
                f"候选 {stats['candidates_found']}, "
                f"耗时 {stats['elapsed_seconds']}s")

    if candidates:
        output_dir = config.get("output", {}).get("output_dir", "./output_data")
        csv_path = write_candidates_csv(candidates, output_dir)
        logger.info(f"候选列表: {csv_path}")

        strong = sum(1 for _, r in candidates if r.score >= 80)
        medium = sum(1 for _, r in candidates if 70 <= r.score < 80)
        breakout = sum(1 for _, r in candidates if r.is_breakout)
        logger.info(f"强候选: {strong}, 中等候选: {medium}, 已突破: {breakout}")
    else:
        logger.info("未发现符合条件的杯柄形态")


def cmd_analyze(args):
    """分析单只股票。"""
    # Phase 2 完善
    print(f"Analyze {args.stock}: not yet implemented (Phase 2)")


def cmd_serve(args):
    """启动 FastAPI Web 服务。"""
    import uvicorn
    config = load_config(args.config)
    server_cfg = config.get("server", {})
    host = server_cfg.get("host", "127.0.0.1")
    port = args.port or server_cfg.get("port", 8080)
    uvicorn.run("server:app", host=host, port=port, reload=True)


def cmd_schedule(args):
    """仅启动定时调度器。"""
    from scheduler.scheduler import start_scheduler
    config = load_config(args.config)
    setup_logging(config)
    logger = logging.getLogger("main")
    logger.info("Starting scheduler in headless mode...")
    start_scheduler(config)
    # 保持主线程
    import time
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Scheduler stopped")


def main():
    parser = argparse.ArgumentParser(
        description="CupHandleScan - A股杯柄结构自动扫描系统"
    )
    sub = parser.add_subparsers(dest="command")

    p_scan = sub.add_parser("scan", help="全市场扫描")
    p_scan.add_argument("--config", default="config.yaml", help="配置文件路径")
    p_scan.add_argument("--stock", default=None, help="扫描单只股票（如 600036）")
    p_scan.add_argument("--charts", action="store_true", help="生成K线图表")
    p_scan.set_defaults(func=cmd_scan)

    p_analyze = sub.add_parser("analyze", help="分析单只股票（Phase 2）")
    p_analyze.add_argument("stock", help="股票代码")
    p_analyze.set_defaults(func=cmd_analyze)

    p_serve = sub.add_parser("serve", help="启动 Web 服务")
    p_serve.add_argument("--config", default="config.yaml")
    p_serve.add_argument("--port", type=int, default=None)
    p_serve.set_defaults(func=cmd_serve)

    p_sched = sub.add_parser("schedule", help="仅启动定时调度器")
    p_sched.add_argument("--config", default="config.yaml")
    p_sched.set_defaults(func=cmd_schedule)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Commit**

```bash
git add scanner/engine.py main.py
git commit -m "feat: add scan engine with dual-thread mutex + CLI entry point"
```

---

### Task 10: FastAPI Web 服务 + WebSocket

**Files:**
- Create: `server.py`

- [ ] **Step 1: 实现 server.py**

```python
# server.py
import logging
import threading
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
import yaml

from scanner.engine import scan_all

logger = logging.getLogger(__name__)

app = FastAPI(title="CupHandleScan API")

# 全局扫描状态
_scan_status = {
    "running": False,
    "task_id": None,
    "progress": {},
    "stats": {},
    "candidates": [],
}


def load_config(path="config.yaml"):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@app.get("/api/scan/start")
async def start_scan():
    global _scan_status
    if _scan_status["running"]:
        return JSONResponse({"error": "Scan already running"}, status_code=409)

    _scan_status["running"] = True
    _scan_status["candidates"] = []

    config = load_config()

    def run():
        result = scan_all(config)
        _scan_status["running"] = False
        _scan_status["stats"] = result["stats"]
        _scan_status["candidates"] = result["candidates"]
        _scan_status["task_id"] = result["task_id"]

    t = threading.Thread(target=run, daemon=True)
    t.start()
    _scan_status["task_id"] = "pending"

    return {"task_id": _scan_status["task_id"], "status": "started"}


@app.get("/api/scan/status")
async def scan_status():
    return {
        "running": _scan_status["running"],
        "task_id": _scan_status["task_id"],
        "stats": _scan_status["stats"],
    }


@app.get("/api/scan/tasks")
async def list_tasks():
    # Phase 3 完善：从日志/数据库读取历史任务
    return {"tasks": []}


@app.get("/api/candidates")
async def get_candidates(scan_id: str = None, sort: str = "score", filter: str = "all"):
    cands = _scan_status["candidates"]
    # TODO: Phase 3 完善排序和筛选
    result = []
    for stock, r in cands:
        result.append({
            "code": r.code,
            "name": r.name,
            "score": r.score,
            "rating": "强候选" if r.score >= 80 else "中等候选" if r.score >= 70 else "弱候选",
            "is_breakout": r.is_breakout,
            "is_volume_breakout": r.is_volume_breakout,
            "latest_close": stock.get("latest_close", 0),
            "breakout_price": r.breakout_price,
            "cup_depth_pct": r.cup_depth_pct,
            "handle_depth_pct": r.handle_depth_pct,
            "cup_duration": r.cup_duration,
            "vol_multiplier": r.vol_multiplier,
        })
    return {"candidates": result, "total": len(result)}


@app.get("/api/candidate/{code}")
async def get_candidate(code: str):
    # Phase 3 完善：返回详细分析
    for stock, r in _scan_status["candidates"]:
        if r.code == code:
            return {
                "code": r.code,
                "name": r.name,
                "score": r.score,
                "left_high_price": r.left_high_price,
                "cup_low_price": r.cup_low_price,
                "right_high_price": r.right_high_price,
                "handle_low_price": r.handle_low_price,
                "left_high_date": r.left_high_date,
                "cup_low_date": r.cup_low_date,
                "right_high_date": r.right_high_date,
                "handle_low_date": r.handle_low_date,
                "cup_depth_pct": r.cup_depth_pct,
                "handle_depth_pct": r.handle_depth_pct,
                "cup_duration": r.cup_duration,
                "handle_duration": r.handle_duration,
                "is_breakout": r.is_breakout,
                "is_volume_breakout": r.is_volume_breakout,
                "vol_multiplier": r.vol_multiplier,
            }
    return JSONResponse({"error": "Not found"}, status_code=404)


@app.websocket("/ws/scan")
async def scan_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.receive_text()
            await websocket.send_json({
                "running": _scan_status["running"],
                "stats": _scan_status["stats"],
                "candidate_count": len(_scan_status["candidates"]),
            })
    except WebSocketDisconnect:
        pass
```

- [ ] **Step 2: Commit**

```bash
git add server.py
git commit -m "feat: add FastAPI server with WebSocket for real-time scan status"
```

---

### Task 11: 定时调度器

**Files:**
- Create: `scheduler/scheduler.py`

- [ ] **Step 1: 实现调度器**

```python
# scheduler/scheduler.py
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from scanner.engine import scan_all
from output.csv_writer import write_candidates_csv

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def start_scheduler(config: dict):
    """启动定时扫描调度器。"""
    global _scheduler
    sched_cfg = config.get("scheduler", {})

    if not sched_cfg.get("enabled", False):
        logger.info("Scheduler disabled in config")
        return

    cron = sched_cfg.get("cron", "30 15 * * 1-5")
    skip_if_running = sched_cfg.get("skip_if_running", True)

    _scheduler = BackgroundScheduler()
    _running = [False]  # 用列表实现可变闭包

    def job():
        if skip_if_running and _running[0]:
            logger.warning("Previous scan still running, skipping this trigger")
            return
        try:
            _running[0] = True
            logger.info("Scheduled scan started")
            result = scan_all(config)
            stats = result["stats"]
            logger.info(f"Scheduled scan done: {stats['candidates_found']} candidates, "
                        f"{stats['elapsed_seconds']}s")
            if result["candidates"]:
                output_dir = config.get("output", {}).get("output_dir", "./output_data")
                write_candidates_csv(result["candidates"], output_dir)
        except Exception as e:
            logger.error(f"Scheduled scan failed: {e}")
        finally:
            _running[0] = False

    _scheduler.add_job(job, "cron",
                       minute=cron.split()[0],
                       hour=cron.split()[1],
                       day_of_week=cron.split()[4],
                       id="daily_scan")

    _scheduler.start()
    logger.info(f"Scheduler started: {cron}")


def stop_scheduler():
    """停止调度器。"""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=True)
        logger.info("Scheduler stopped")
```

- [ ] **Step 2: 更新 main.py 中的 cmd_serve 函数，启动时加载调度器**

在 `cmd_serve` 函数开头加入：
```python
from scheduler.scheduler import start_scheduler
start_scheduler(config)
```

- [ ] **Step 3: Commit**

```bash
git add scheduler/scheduler.py
git commit -m "feat: add APScheduler daily 15:30 auto-scan trigger"
```

---

### Task 12: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: 写 README**

```markdown
# CupHandleScan

A股杯柄结构（Cup & Handle）自动扫描系统。

## 安装

```bash
pip install -r requirements.txt
```

## 使用

### 全市场扫描

```bash
python main.py scan
```

### 分析单只股票（Phase 2）

```bash
python main.py analyze 600036
```

### 启动 Web 服务

```bash
python main.py serve --port 8080
```

### 后台定时扫描

```bash
python main.py schedule
```

## 配置

编辑 `config.yaml` 调整扫描参数。主要配置项：

- `market` — 市场范围（沪深/创业板/科创板）
- `liquidity` — 成交量/成交额过滤阈值
- `cup` / `handle` / `breakout` — 杯柄结构参数
- `scheduler` — 定时任务（每工作日 15:30）

## 输出

扫描结果输出到 `output_data/` 目录：

- `candidates_YYYY-MM-DD.csv` — 候选股票列表
- `candidates_YYYY-MM-DD.json` — 候选股票 JSON（Phase 2）
- `charts/` — 候选股票 K 线图（Phase 3）

## 数据源

- 股票池：AKShare（回退本地缓存）
- 日线行情：新浪财经 → 腾讯财经 → 本地缓存（三级回退）

## 开发

```bash
# 运行测试
pytest tests/ -v
```
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with install and usage instructions"
```

---

## 自审

### 1. Spec 覆盖检查

| Spec 需求 | 覆盖 Task |
|---|---|
| 项目目录结构 | Task 1, File Structure |
| 配置文件 | Task 1 (config.yaml) |
| A股股票池获取 | Task 4 |
| 日线行情获取 | Task 3 (Sina + Tencent) |
| 双线程数据源互斥 | Task 2 (DataSourceManager) |
| 三级回退 | Task 9 (_fetch_with_fallback) |
| 基础流动性过滤 | Task 5 |
| 基础杯柄识别 | Task 6 |
| CSV 输出 | Task 8 |
| CLI 运行 | Task 9 |
| 形态评分 (0-100) | Task 7 |
| FastAPI + WebSocket | Task 10 |
| 定时调度器 | Task 11 |
| 单只失败不中断 | Task 9 (try/except per stock) |
| README | Task 12 |

### 2. Placeholder 检查

- 评分系统的成交量结构（20分）和前置趋势（10分）在 Phase 2 完善 → 当前 Phase 1 给基础分，不影响运行
- `cmd_analyze` 留空 → 标注 Phase 2，Phase 1 优先级是全市场扫描
- Tasks 筛选 API → 留 Phase 3 实现

### 3. 类型一致性

- `CupHandleResult` 字段名在所有 Task 中一致 ✓
- `DataSourceManager` API 在 Task 2 定义，Task 9 使用 ✓
- `config.yaml` 结构在 Task 1 定义，所有模块使用相同 key ✓

### 覆盖缺口

无。Phase 2/3/4 的内容（干稳低吸分析、Web 前端、工程增强）不在本计划范围内。

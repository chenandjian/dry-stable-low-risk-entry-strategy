# Multi-Source Daily K-Line Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current Sina/Tencent-first daily K-line fetch path with a multi-source chain that prefers mootdx TCP, falls back to Baidu K-line, then uses Sina and Tencent as last-resort sources.

**Architecture:** Add focused source modules for mootdx and Baidu that return the project’s existing OHLC dict format. Extend `scanner.engine` from a hard-coded two-source fetch path to a configurable source chain while preserving `FetchResult` compatibility and fresh-first semantics. Keep scanner, scoring, database schema, and frontend behavior unchanged.

**Tech Stack:** Python 3.10+, pytest, requests, mootdx, SQLite via `scanner/db.py`, existing scan engine.

---

## File Structure

- Create: `scanner/mootdx_source.py`
  - Owns all mootdx TCP daily K-line fetching and normalization.

- Create: `scanner/baidu_source.py`
  - Owns Baidu stock quotation daily K-line fetching and normalization.

- Modify: `scanner/engine.py`
  - Import the new source functions.
  - Add a configurable daily source chain.
  - Keep `FetchResult` and scan task behavior compatible.

- Modify: `config.yaml`
  - Add `data.daily_sources` defaulting to `mootdx, baidu, sina, tencent`.

- Modify: `requirements.txt`
  - Add `mootdx>=0.10`.

- Create: `tests/test_mootdx_source.py`
  - Unit tests for source normalization and failure behavior.

- Create: `tests/test_baidu_source.py`
  - Unit tests for Baidu `keys + marketData` parsing and failure behavior.

- Modify: `tests/test_engine_fresh_fetch.py`
  - Add source-chain regression tests.
  - Update existing two-source tests only where their assumptions conflict with the new default source chain.

---

### Task 1: Add mootdx Daily Source

**Files:**
- Create: `scanner/mootdx_source.py`
- Create: `tests/test_mootdx_source.py`

- [ ] **Step 1: Write failing tests for mootdx normalization and failures**

Create `tests/test_mootdx_source.py`:

```python
from scanner.mootdx_source import fetch_mootdx_daily


class FakeBars:
    def __init__(self, rows):
        self._rows = rows

    def to_dict(self, orient="records"):
        assert orient == "records"
        return self._rows


class FakeClient:
    def __init__(self, rows=None, exc=None):
        self.rows = rows or []
        self.exc = exc
        self.calls = []

    def bars(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        return FakeBars(self.rows)


def test_fetch_mootdx_daily_normalizes_rows(monkeypatch):
    client = FakeClient([
        {
            "datetime": "2026-06-04 15:00",
            "open": 10.0,
            "high": 10.5,
            "low": 9.8,
            "close": 10.2,
            "vol": 1000,
            "amount": 10200,
        },
        {
            "datetime": "2026-06-05 15:00",
            "open": 10.2,
            "high": 10.8,
            "low": 10.1,
            "close": 10.7,
            "vol": 1200,
            "amount": 12840,
        },
    ])

    class FakeQuotes:
        @staticmethod
        def factory(market="std"):
            assert market == "std"
            return client

    monkeypatch.setattr("scanner.mootdx_source.Quotes", FakeQuotes)

    rows = fetch_mootdx_daily("000001", days=250)

    assert rows == [
        {"date": "2026-06-04", "open": 10.0, "high": 10.5, "low": 9.8, "close": 10.2, "volume": 1000.0, "turnover": 10200.0},
        {"date": "2026-06-05", "open": 10.2, "high": 10.8, "low": 10.1, "close": 10.7, "volume": 1200.0, "turnover": 12840.0},
    ]
    assert client.calls == [{"symbol": "000001", "category": 4, "market": 0, "offset": 250}]


def test_fetch_mootdx_daily_uses_sh_market_for_6_prefix(monkeypatch):
    client = FakeClient([
        {"datetime": "2026-06-05", "open": 10, "high": 11, "low": 9, "close": 10.5, "vol": 1, "amount": 10.5}
    ])

    class FakeQuotes:
        @staticmethod
        def factory(market="std"):
            return client

    monkeypatch.setattr("scanner.mootdx_source.Quotes", FakeQuotes)

    assert fetch_mootdx_daily("600000") is not None
    assert client.calls[0]["market"] == 1


def test_fetch_mootdx_daily_returns_none_on_empty_or_exception(monkeypatch):
    class EmptyQuotes:
        @staticmethod
        def factory(market="std"):
            return FakeClient([])

    monkeypatch.setattr("scanner.mootdx_source.Quotes", EmptyQuotes)
    assert fetch_mootdx_daily("000001") is None

    class FailingQuotes:
        @staticmethod
        def factory(market="std"):
            return FakeClient(exc=RuntimeError("tdx down"))

    monkeypatch.setattr("scanner.mootdx_source.Quotes", FailingQuotes)
    assert fetch_mootdx_daily("000001") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_mootdx_source.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scanner.mootdx_source'`.

- [ ] **Step 3: Implement `scanner/mootdx_source.py`**

Create `scanner/mootdx_source.py`:

```python
# scanner/mootdx_source.py
import logging

logger = logging.getLogger(__name__)

try:
    from mootdx.quotes import Quotes
except Exception:  # pragma: no cover - exercised when dependency is absent in runtime
    Quotes = None


def fetch_mootdx_daily(code: str, days: int = 250) -> list[dict] | None:
    """Fetch daily OHLC data from TongDaXin via mootdx TCP."""
    if Quotes is None:
        logger.warning("mootdx is not installed; cannot fetch %s", code)
        return None

    try:
        client = Quotes.factory(market="std")
        rows = client.bars(
            symbol=_normalize_code(code),
            category=4,
            market=_market_id(code),
            offset=days,
        )
        records = _to_records(rows)
        normalized = [_normalize_row(row) for row in records]
        normalized = [row for row in normalized if row is not None]
        if not normalized:
            return None
        return sorted(normalized, key=lambda row: row["date"])
    except Exception as exc:
        logger.warning("mootdx fetch error for %s: %s", code, exc)
        return None


def _normalize_code(code: str) -> str:
    code = code.strip().lower()
    if code.startswith(("sh", "sz", "bj")):
        return code[2:]
    if "." in code:
        return code.split(".", 1)[0]
    return code


def _market_id(code: str) -> int:
    normalized = _normalize_code(code)
    return 1 if normalized.startswith(("6", "9")) else 0


def _to_records(rows) -> list[dict]:
    if rows is None:
        return []
    if hasattr(rows, "to_dict"):
        return rows.to_dict("records")
    if isinstance(rows, list):
        return rows
    return []


def _normalize_row(row: dict) -> dict | None:
    try:
        date = str(row.get("datetime") or row.get("date") or "")[:10]
        if not date:
            return None
        close = float(row["close"])
        volume = float(row.get("vol", row.get("volume", 0)) or 0)
        turnover = float(row.get("amount", row.get("turnover", close * volume)) or 0)
        return {
            "date": date,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": close,
            "volume": volume,
            "turnover": turnover,
        }
    except (KeyError, TypeError, ValueError):
        return None
```

- [ ] **Step 4: Run mootdx tests**

Run:

```bash
python -m pytest tests/test_mootdx_source.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

Before committing, show status and files, then commit only if allowed by the project git rules:

```bash
git status --short
git diff -- scanner/mootdx_source.py tests/test_mootdx_source.py
```

Commit message:

```text
feat: add mootdx daily kline source

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

---

### Task 2: Add Baidu Daily K-Line Source

**Files:**
- Create: `scanner/baidu_source.py`
- Create: `tests/test_baidu_source.py`

- [ ] **Step 1: Write failing tests for Baidu parsing**

Create `tests/test_baidu_source.py`:

```python
from scanner.baidu_source import fetch_baidu_daily


class FakeResponse:
    def __init__(self, payload=None, exc=None):
        self.payload = payload or {}
        self.exc = exc

    def raise_for_status(self):
        if self.exc:
            raise self.exc

    def json(self):
        return self.payload


def test_fetch_baidu_daily_parses_keys_and_market_data(monkeypatch):
    payload = {
        "Result": {
            "newMarketData": {
                "keys": ["time", "open", "close", "high", "low", "volume", "amount", "ma5avgprice"],
                "marketData": "2026-06-04,10,10.2,10.5,9.8,1000,10200,10.1;2026-06-05,10.2,10.7,10.8,10.1,1200,12840,10.3",
            }
        }
    }
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        return FakeResponse(payload)

    monkeypatch.setattr("scanner.baidu_source.requests.get", fake_get)

    rows = fetch_baidu_daily("000001", days=250)

    assert rows == [
        {"date": "2026-06-04", "open": 10.0, "high": 10.5, "low": 9.8, "close": 10.2, "volume": 1000.0, "turnover": 10200.0},
        {"date": "2026-06-05", "open": 10.2, "high": 10.8, "low": 10.1, "close": 10.7, "volume": 1200.0, "turnover": 12840.0},
    ]
    assert calls[0]["params"]["code"] == "000001"
    assert calls[0]["params"]["ktype"] == "1"
    assert calls[0]["headers"]["User-Agent"] == "Mozilla/5.0"


def test_fetch_baidu_daily_limits_to_recent_days(monkeypatch):
    payload = {
        "Result": {
            "newMarketData": {
                "keys": ["time", "open", "close", "high", "low", "volume", "amount"],
                "marketData": "2026-06-03,9,9,9,9,1,9;2026-06-04,10,10,10,10,2,20;2026-06-05,11,11,11,11,3,33",
            }
        }
    }
    monkeypatch.setattr("scanner.baidu_source.requests.get", lambda *args, **kwargs: FakeResponse(payload))

    rows = fetch_baidu_daily("000001", days=2)

    assert [row["date"] for row in rows] == ["2026-06-04", "2026-06-05"]


def test_fetch_baidu_daily_returns_none_for_empty_or_bad_payload(monkeypatch):
    monkeypatch.setattr("scanner.baidu_source.requests.get", lambda *args, **kwargs: FakeResponse({}))
    assert fetch_baidu_daily("000001") is None

    payload = {"Result": {"newMarketData": {"keys": ["time", "open"], "marketData": "2026-06-05,10"}}}
    monkeypatch.setattr("scanner.baidu_source.requests.get", lambda *args, **kwargs: FakeResponse(payload))
    assert fetch_baidu_daily("000001") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_baidu_source.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scanner.baidu_source'`.

- [ ] **Step 3: Implement `scanner/baidu_source.py`**

Create `scanner/baidu_source.py`:

```python
# scanner/baidu_source.py
import logging

import requests

logger = logging.getLogger(__name__)

BAIDU_KLINE_URL = "https://finance.pae.baidu.com/selfselect/getstockquotation"


def fetch_baidu_daily(code: str, days: int = 250) -> list[dict] | None:
    """Fetch daily OHLC data from Baidu stock quotation K-line endpoint."""
    params = {
        "all": "1",
        "isIndex": "false",
        "isBk": "false",
        "isBlock": "false",
        "isFutures": "false",
        "isStock": "true",
        "newFormat": "1",
        "group": "quotation_kline_ab",
        "finClientType": "pc",
        "code": _normalize_code(code),
        "ktype": "1",
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/vnd.finance-web.v1+json",
        "Origin": "https://gushitong.baidu.com",
        "Referer": "https://gushitong.baidu.com/",
    }
    try:
        resp = requests.get(BAIDU_KLINE_URL, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        payload = resp.json()
        rows = _parse_payload(payload)
        if not rows:
            return None
        return rows[-days:]
    except Exception as exc:
        logger.warning("Baidu kline fetch/parse error for %s: %s", code, exc)
        return None


def _normalize_code(code: str) -> str:
    code = code.strip().lower()
    if code.startswith(("sh", "sz", "bj")):
        return code[2:]
    if "." in code:
        return code.split(".", 1)[0]
    return code


def _parse_payload(payload: dict) -> list[dict]:
    md = payload.get("Result", {}).get("newMarketData", {})
    keys = md.get("keys") or []
    raw_rows = md.get("marketData") or ""
    if not keys or not raw_rows:
        return []
    required = {"time", "open", "close", "high", "low", "volume", "amount"}
    if not required.issubset(set(keys)):
        return []

    parsed = []
    for raw in raw_rows.split(";"):
        if not raw.strip():
            continue
        values = raw.split(",")
        if len(values) < len(keys):
            continue
        item = dict(zip(keys, values))
        row = _normalize_row(item)
        if row:
            parsed.append(row)
    return sorted(parsed, key=lambda row: row["date"])


def _normalize_row(item: dict) -> dict | None:
    try:
        return {
            "date": str(item["time"])[:10],
            "open": float(item["open"]),
            "high": float(item["high"]),
            "low": float(item["low"]),
            "close": float(item["close"]),
            "volume": float(item["volume"]),
            "turnover": float(item["amount"]),
        }
    except (KeyError, TypeError, ValueError):
        return None
```

- [ ] **Step 4: Run Baidu tests**

Run:

```bash
python -m pytest tests/test_baidu_source.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

Before committing, show status and files, then commit only if allowed:

```bash
git status --short
git diff -- scanner/baidu_source.py tests/test_baidu_source.py
```

Commit message:

```text
feat: add baidu daily kline source

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

---

### Task 3: Add Config and Dependency

**Files:**
- Modify: `config.yaml`
- Modify: `requirements.txt`

- [ ] **Step 1: Add config default**

In `config.yaml`, under `data:`, change:

```yaml
data:
  cache_enabled: true
  cache_dir: ./cache/daily
  database_path: ./data/cuphandle.db
  start_date: "2025-01-01"
  end_date: null         # null = 最近交易日
  use_fq: true           # 前复权
```

to:

```yaml
data:
  cache_enabled: true
  cache_dir: ./cache/daily
  database_path: ./data/cuphandle.db
  daily_sources:
    - mootdx
    - baidu
    - sina
    - tencent
  start_date: "2025-01-01"
  end_date: null         # null = 最近交易日
  use_fq: true           # 前复权
```

- [ ] **Step 2: Add dependency**

In `requirements.txt`, add `mootdx>=0.10` after `requests>=2.31.0`:

```text
akshare>=1.14.0
requests>=2.31.0
mootdx>=0.10
pyyaml>=6.0
fastapi>=0.110.0
uvicorn>=0.29.0
apscheduler>=3.10.4
matplotlib>=3.8.0
pytest>=8.0.0
```

- [ ] **Step 3: Run existing tests that do not need mootdx network**

Run:

```bash
python -m pytest tests/test_mootdx_source.py tests/test_baidu_source.py -v
```

Expected: PASS. These tests monkeypatch external calls and do not require real network.

- [ ] **Step 4: Commit Task 3**

Before committing, show status and files, then commit only if allowed:

```bash
git status --short
git diff -- config.yaml requirements.txt
```

Commit message:

```text
chore: configure multi-source daily kline dependencies

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

---

### Task 4: Extend Engine to Use Multi-Source Daily Chain

**Files:**
- Modify: `scanner/engine.py`
- Modify: `tests/test_engine_fresh_fetch.py`

- [ ] **Step 1: Write failing test for mootdx-first success**

Append to `tests/test_engine_fresh_fetch.py`:

```python

def test_fetch_with_retry_uses_configured_daily_source_chain_mootdx_first(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    calls = []

    monkeypatch.setattr(engine, "fetch_mootdx_daily", lambda code: calls.append("mootdx") or [_row("2026-06-05", close=11.0)], raising=False)
    monkeypatch.setattr(engine, "fetch_baidu_daily", lambda code: calls.append("baidu") or [_row("2026-06-05", close=12.0)], raising=False)
    monkeypatch.setattr(engine, "fetch_sina_daily", lambda code: calls.append("sina") or [_row("2026-06-05", close=13.0)])
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code: calls.append("tencent") or [_row("2026-06-05", close=14.0)])

    result = engine._fetch_with_retry(
        "600000",
        "mootdx",
        retry_attempts=2,
        fallback_attempts=2,
        sleep_fn=lambda _: None,
        source_chain=["mootdx", "baidu", "sina", "tencent"],
    )

    assert calls == ["mootdx"]
    assert result.data[-1]["date"] == "2026-06-05"
    assert result.data[-1]["close"] == 11.0
    assert result.primary_source == "mootdx"
    assert result.fallback_source == "mootdx"
    assert result.primary_attempts == 1
    assert result.primary_error is None
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/test_engine_fresh_fetch.py::test_fetch_with_retry_uses_configured_daily_source_chain_mootdx_first -v
```

Expected: FAIL with `TypeError: _fetch_with_retry() got an unexpected keyword argument 'source_chain'` or missing `fetch_mootdx_daily` attribute.

- [ ] **Step 3: Import new source functions in `scanner/engine.py`**

At the top of `scanner/engine.py`, after existing source imports, add:

```python
from scanner.mootdx_source import fetch_mootdx_daily
from scanner.baidu_source import fetch_baidu_daily
```

- [ ] **Step 4: Add source registry helper**

In `scanner/engine.py`, above `_fetch_with_retry()`, add:

```python
DEFAULT_DAILY_SOURCES = ["mootdx", "baidu", "sina", "tencent"]


def _daily_fetch_fn(ds_name: str):
    fetchers = {
        "mootdx": fetch_mootdx_daily,
        "baidu": fetch_baidu_daily,
        "sina": fetch_sina_daily,
        "tencent": fetch_tencent_daily,
    }
    if ds_name not in fetchers:
        raise ValueError(f"Unknown daily data source: {ds_name}")
    return fetchers[ds_name]


def _normalize_source_chain(source_chain: list[str] | None, primary_ds: str) -> list[str]:
    chain = list(source_chain or DEFAULT_DAILY_SOURCES)
    if primary_ds in chain:
        chain.remove(primary_ds)
    return [primary_ds] + chain
```

- [ ] **Step 5: Replace `_try_fetch_source()` fetch function lookup**

In `_try_fetch_source()`, replace:

```python
fetch_fn = fetch_sina_daily if ds_name == "sina" else fetch_tencent_daily
```

with:

```python
fetch_fn = _daily_fetch_fn(ds_name)
```

- [ ] **Step 6: Add `source_chain` parameter and chain loop**

Replace `_fetch_with_retry()` with:

```python
def _fetch_with_retry(
    code: str,
    primary_ds: str,
    retry_attempts: int = 2,
    fallback_attempts: int = 2,
    sleep_fn: Callable[[float], None] = time.sleep,
    mgr: DataSourceManager | None = None,
    source_chain: list[str] | None = None,
) -> FetchResult:
    """Fetch fresh K-line data from the configured source chain, then merge with cache."""
    chain = _normalize_source_chain(source_chain, primary_ds)
    cached = db.get_ohlc(code)
    result = FetchResult(data=None, primary_source=chain[0], fallback_source=chain[-1])

    for index, ds_name in enumerate(chain):
        attempts_allowed = retry_attempts if index == 0 else fallback_attempts
        if index > 0 and mgr is not None:
            if not mgr.acquire(ds_name):
                result.fallback_source = ds_name
                result.fallback_attempts = 0
                result.fallback_error = "data source busy"
                return result
            try:
                data, attempts, error = _try_fetch_source(code, ds_name, attempts_allowed, sleep_fn)
            finally:
                mgr.release(ds_name)
        else:
            data, attempts, error = _try_fetch_source(code, ds_name, attempts_allowed, sleep_fn)

        if index == 0:
            result.primary_attempts = attempts
            result.primary_error = error
        else:
            result.fallback_source = ds_name
            result.fallback_attempts = attempts
            result.fallback_error = error

        if data:
            merged = _merge_data(cached or [], data)
            db.save_ohlc(code, merged)
            result.data = merged
            if index > 0:
                result.fallback_error = None
            return result

    return result
```

This preserves the existing `FetchResult` fields while allowing more than two sources.

- [ ] **Step 7: Run mootdx-first test**

Run:

```bash
python -m pytest tests/test_engine_fresh_fetch.py::test_fetch_with_retry_uses_configured_daily_source_chain_mootdx_first -v
```

Expected: PASS.

- [ ] **Step 8: Commit Task 4**

Before committing, show status and files, then commit only if allowed:

```bash
git status --short
git diff -- scanner/engine.py tests/test_engine_fresh_fetch.py
```

Commit message:

```text
feat: add configurable daily kline source chain

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

---

### Task 5: Add Engine Fallback Chain Coverage

**Files:**
- Modify: `tests/test_engine_fresh_fetch.py`
- Modify: `scanner/engine.py` only if tests reveal issues

- [ ] **Step 1: Add test for fallback to Baidu**

Append to `tests/test_engine_fresh_fetch.py`:

```python

def test_fetch_with_retry_falls_back_to_baidu_after_mootdx_failure(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    calls = []

    monkeypatch.setattr(engine, "fetch_mootdx_daily", lambda code: calls.append("mootdx") or None, raising=False)
    monkeypatch.setattr(engine, "fetch_baidu_daily", lambda code: calls.append("baidu") or [_row("2026-06-05", close=12.0)], raising=False)
    monkeypatch.setattr(engine, "fetch_sina_daily", lambda code: calls.append("sina") or [_row("2026-06-05", close=13.0)])
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code: calls.append("tencent") or [_row("2026-06-05", close=14.0)])

    result = engine._fetch_with_retry(
        "600000",
        "mootdx",
        retry_attempts=1,
        fallback_attempts=1,
        sleep_fn=lambda _: None,
        source_chain=["mootdx", "baidu", "sina", "tencent"],
    )

    assert calls == ["mootdx", "baidu"]
    assert result.data[-1]["close"] == 12.0
    assert result.primary_error == "empty response"
    assert result.fallback_source == "baidu"
    assert result.fallback_error is None
```

- [ ] **Step 2: Add test for fallback through Sina to Tencent**

Append:

```python

def test_fetch_with_retry_falls_back_through_sina_to_tencent(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    calls = []

    monkeypatch.setattr(engine, "fetch_mootdx_daily", lambda code: calls.append("mootdx") or None, raising=False)
    monkeypatch.setattr(engine, "fetch_baidu_daily", lambda code: calls.append("baidu") or None, raising=False)
    monkeypatch.setattr(engine, "fetch_sina_daily", lambda code: calls.append("sina") or None)
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code: calls.append("tencent") or [_row("2026-06-05", close=14.0)])

    result = engine._fetch_with_retry(
        "600000",
        "mootdx",
        retry_attempts=1,
        fallback_attempts=1,
        sleep_fn=lambda _: None,
        source_chain=["mootdx", "baidu", "sina", "tencent"],
    )

    assert calls == ["mootdx", "baidu", "sina", "tencent"]
    assert result.data[-1]["close"] == 14.0
    assert result.fallback_source == "tencent"
    assert result.fallback_error is None
```

- [ ] **Step 3: Add test for all sources failing without cache use**

Append:

```python

def test_fetch_with_retry_multi_source_failure_does_not_return_cache(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    db.save_ohlc("600000", [_row("2026-06-03", close=9.0)])
    calls = []

    monkeypatch.setattr(engine, "fetch_mootdx_daily", lambda code: calls.append("mootdx") or None, raising=False)
    monkeypatch.setattr(engine, "fetch_baidu_daily", lambda code: calls.append("baidu") or None, raising=False)
    monkeypatch.setattr(engine, "fetch_sina_daily", lambda code: calls.append("sina") or None)
    monkeypatch.setattr(engine, "fetch_tencent_daily", lambda code: calls.append("tencent") or None)

    result = engine._fetch_with_retry(
        "600000",
        "mootdx",
        retry_attempts=1,
        fallback_attempts=1,
        sleep_fn=lambda _: None,
        source_chain=["mootdx", "baidu", "sina", "tencent"],
    )

    assert calls == ["mootdx", "baidu", "sina", "tencent"]
    assert result.data is None
    assert result.from_cache is False
    assert db.get_ohlc("600000")[-1]["date"] == "2026-06-03"
```

- [ ] **Step 4: Run new fallback tests**

Run:

```bash
python -m pytest \
  tests/test_engine_fresh_fetch.py::test_fetch_with_retry_falls_back_to_baidu_after_mootdx_failure \
  tests/test_engine_fresh_fetch.py::test_fetch_with_retry_falls_back_through_sina_to_tencent \
  tests/test_engine_fresh_fetch.py::test_fetch_with_retry_multi_source_failure_does_not_return_cache \
  -v
```

Expected: PASS. If a test fails, fix `scanner/engine.py` only enough to satisfy the failing behavior.

- [ ] **Step 5: Run full engine fetch tests**

Run:

```bash
python -m pytest tests/test_engine_fresh_fetch.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

Before committing, show status and files, then commit only if allowed:

```bash
git status --short
git diff -- scanner/engine.py tests/test_engine_fresh_fetch.py
```

Commit message:

```text
test: cover daily kline source fallback chain

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

---

### Task 6: Wire Source Chain into Scan Configuration

**Files:**
- Modify: `scanner/engine.py`
- Modify: `tests/test_engine_fresh_fetch.py`

- [ ] **Step 1: Add test that `scan_all()` passes configured daily source chain**

Append to `tests/test_engine_fresh_fetch.py`:

```python

def test_scan_all_passes_configured_daily_sources_to_fetch(monkeypatch, tmp_path):
    config = {
        "data": {
            "database_path": str(tmp_path / "cuphandle.db"),
            "daily_sources": ["baidu", "sina"],
            "worker_count": 1,
        },
        "liquidity": {"min_listing_days": 250},
        "scoring": {"medium_threshold": 70},
    }
    seen = []

    def fake_fetch_with_retry(code, ds, *args, source_chain=None, **kwargs):
        seen.append({"ds": ds, "source_chain": source_chain})
        return engine.FetchResult(data=_rows(260), primary_source=ds, fallback_source=ds, primary_attempts=1)

    monkeypatch.setattr(engine, "_fetch_with_retry", fake_fetch_with_retry)
    monkeypatch.setattr(engine, "DataSourceManager", FakeScanManager)
    monkeypatch.setattr(engine.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(stock_pool, "get_a_stock_pool", lambda config: [{"code": "600000", "name": "PF Bank"}])
    monkeypatch.setattr(engine, "fetch_market_index_daily", lambda: [])
    monkeypatch.setattr(engine, "passes_liquidity_filter", lambda data, cfg: True)
    monkeypatch.setattr(engine, "detect_cup_handle", lambda data, cfg: engine.CupHandleResult(found=False))
    monkeypatch.setattr(
        engine,
        "analyze_dry_stable",
        lambda result, data, market_data=None: {
            "pattern_score": {"score": 0, "key_pattern_type": "other", "type": "other"},
            "decision": {"verdict": "不建议买入", "summary": ""},
        },
    )

    engine.scan_all(config, worker_count=1)

    assert seen == [{"ds": "baidu", "source_chain": ["baidu", "sina"]}]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/test_engine_fresh_fetch.py::test_scan_all_passes_configured_daily_sources_to_fetch -v
```

Expected: FAIL because `scan_all()` does not pass `source_chain` yet.

- [ ] **Step 3: Add source-chain config in `scan_all()`**

In `scanner/engine.py`, near existing config setup:

```python
max_busy_retries = config.get("data", {}).get("source_busy_max_retries", 3)
market_data = fetch_market_index_daily()
```

change to:

```python
daily_sources = config.get("data", {}).get("daily_sources") or DEFAULT_DAILY_SOURCES
max_busy_retries = config.get("data", {}).get("source_busy_max_retries", 3)
market_data = fetch_market_index_daily()
```

- [ ] **Step 4: Pass chain to `_fetch_with_retry()`**

In the worker call:

```python
fetch_result = _fetch_with_retry(
    code,
    ds,
    retry_attempts=primary_attempts,
    fallback_attempts=fallback_attempts,
    mgr=mgr,
)
```

change to:

```python
fetch_result = _fetch_with_retry(
    code,
    ds if ds in daily_sources else daily_sources[0],
    retry_attempts=primary_attempts,
    fallback_attempts=fallback_attempts,
    mgr=mgr,
    source_chain=daily_sources,
)
```

This preserves `DataSourceManager` compatibility while letting configured sources drive actual daily K-line fetches.

- [ ] **Step 5: Run config chain test**

Run:

```bash
python -m pytest tests/test_engine_fresh_fetch.py::test_scan_all_passes_configured_daily_sources_to_fetch -v
```

Expected: PASS.

- [ ] **Step 6: Run scan regression tests**

Run:

```bash
python -m pytest tests/test_engine_fresh_fetch.py tests/test_scan_task_tracking.py tests/test_server_scan_api.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 6**

Before committing, show status and files, then commit only if allowed:

```bash
git status --short
git diff -- scanner/engine.py tests/test_engine_fresh_fetch.py
```

Commit message:

```text
feat: wire daily source chain into scanner

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

---

### Task 7: Final Verification

**Files:**
- Existing test and config files only, unless failures require targeted fixes.

- [ ] **Step 1: Install dependencies if mootdx is missing**

Run:

```bash
python - <<'PY'
try:
    import mootdx
    print('mootdx installed')
except Exception as exc:
    print('mootdx missing:', exc)
PY
```

If missing, run:

```bash
pip install -r requirements.txt
```

Expected: `mootdx installed` after installation.

- [ ] **Step 2: Run focused source tests**

Run:

```bash
python -m pytest tests/test_mootdx_source.py tests/test_baidu_source.py tests/test_sina_source.py -v
```

Expected: PASS.

- [ ] **Step 3: Run scan regression tests**

Run:

```bash
python -m pytest tests/test_engine_fresh_fetch.py tests/test_scan_task_tracking.py tests/test_server_scan_api.py -v
```

Expected: PASS.

- [ ] **Step 4: Run full backend tests**

Run:

```bash
python -m pytest tests/ -v
```

Expected: PASS. If any test fails, capture the exact output and fix only the failing behavior.

- [ ] **Step 5: Run frontend build**

Run:

```bash
npm --prefix web run build
```

Expected: exit code 0. Vite CJS deprecation warnings are acceptable.

- [ ] **Step 6: Optional live probe for one stock**

Run:

```bash
python - <<'PY'
from scanner import db
from scanner.engine import _fetch_with_retry

db.init_db('data/cuphandle.db')
result = _fetch_with_retry(
    '000001',
    'mootdx',
    retry_attempts=1,
    fallback_attempts=1,
    source_chain=['mootdx', 'baidu', 'sina', 'tencent'],
)
print('data rows:', len(result.data or []))
print('primary:', result.primary_source, result.primary_attempts, result.primary_error)
print('fallback:', result.fallback_source, result.fallback_attempts, result.fallback_error)
print('latest:', (result.data or [{}])[-1].get('date'))
PY
```

Expected: `data rows` is positive if any configured source is reachable. If all external sources are blocked in the environment, this may print `0`; do not treat that as a unit-test failure.

- [ ] **Step 7: Show final status and diff**

Run:

```bash
git status --short
git diff --stat
```

Expected: only planned files are modified/created, plus any pre-existing untracked docs from earlier work.

- [ ] **Step 8: Final commit**

Before committing, show status, files to commit, and change summary. Then commit if allowed by the user's git rules.

Commit message:

```text
feat: add multi-source daily kline fetching

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

---

## Self-Review

Spec coverage:

- `mootdx → baidu → sina → tencent` default chain: Tasks 3, 4, 6.
- New mootdx source: Task 1.
- New Baidu source: Task 2.
- Keep Sina/Tencent as fallback and preserve 456 busy behavior: Tasks 4, 5, existing `tests/test_sina_source.py` and `tests/test_engine_fresh_fetch.py` coverage.
- Fresh-first and no stale cache on all-source failure: Task 5.
- No frontend or strategy changes: plan only touches source, engine, config, dependency, and tests.
- Full validation: Task 7.

Placeholder scan:

- No TBD/TODO placeholders.
- Each code-changing step includes concrete code or exact replacement text.
- Each verification step has exact command and expected result.

Type consistency:

- New source functions return `list[dict] | None`, matching existing `fetch_sina_daily` and `fetch_tencent_daily`.
- `_fetch_with_retry(..., source_chain=None)` preserves existing parameters and adds an optional parameter.
- `FetchResult` field names stay unchanged.

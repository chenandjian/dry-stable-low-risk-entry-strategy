# Dry Stable Strategy Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the remaining dry-stable low-risk strategy gaps so scan results, single-stock analysis, backtests, and the web UI all reflect the same strategy rules.

**Architecture:** Keep the current separation: `scanner/` finds market candidates, `analyzer/` owns strategy scoring and decisions, `server.py` exposes persisted results, and `web/` displays those fields. Add only small focused modules or helper functions; avoid broad refactors.

**Tech Stack:** Python 3.10+, pytest, FastAPI, SQLite, Vue 3, Vite, ECharts.

---

## Current Progress

- [x] Cup body duration and breakout threshold corrected in `scanner/pattern_detector.py`.
- [x] Strict dry-stable decision gate added in `analyzer/decision.py`.
- [x] Full dry-stable pipeline added in `analyzer/dry_stable.py`.
- [x] VCP scoring added in `analyzer/pattern_score.py`.
- [x] VCP key prices added in `analyzer/key_prices.py`.
- [x] Central invalidation rules added in `analyzer/invalid_rules.py`.
- [x] Market environment analyzer added in `analyzer/market_env.py`.
- [x] Full-market scan now admits cup-handle and VCP-only dry-stable candidates in `scanner/engine.py`.
- [x] Candidate DB/API/CSV outputs include dry-stable, risk, Pivot, and market fields.
- [x] Web results, scan console, and stock detail pages display dry-stable fields.
- [x] Verification currently passes: `python -m pytest tests/ -q` with 62 tests and `npm.cmd run build`.

---

## Task 1: Connect Real Market Index Data

**Files:**
- Create: `scanner/index_source.py`
- Modify: `analyzer/dry_stable.py`
- Modify: `scanner/engine.py`
- Modify: `main.py`
- Test: `tests/test_market_env.py`
- Test: `tests/test_index_source.py`

- [x] **Step 1: Add index source tests**

Add `tests/test_index_source.py`:

```python
from scanner.index_source import normalize_index_ohlc


def test_normalize_index_ohlc_sorts_and_keeps_required_fields():
    raw = [
        {"date": "2026-06-02", "open": 101, "high": 103, "low": 100, "close": 102, "volume": 20},
        {"date": "2026-06-01", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 10},
    ]

    result = normalize_index_ohlc(raw)

    assert [d["date"] for d in result] == ["2026-06-01", "2026-06-02"]
    assert result[0]["close"] == 101
    assert result[1]["volume"] == 20
```

- [x] **Step 2: Run failing index source test**

Run:

```bash
python -m pytest tests/test_index_source.py -q
```

Expected: fail because `scanner.index_source` does not exist.

- [x] **Step 3: Implement index source normalization and fetch fallback**

Create `scanner/index_source.py`:

```python
"""Index OHLC data source for market environment analysis."""

from scanner.sina_source import fetch_sina_daily


DEFAULT_MARKET_INDEX = "000001"


def fetch_market_index_daily(code: str = DEFAULT_MARKET_INDEX) -> list[dict] | None:
    data = fetch_sina_daily(code)
    if not data:
        return None
    return normalize_index_ohlc(data)


def normalize_index_ohlc(raw: list[dict]) -> list[dict]:
    required = []
    for d in raw or []:
        if not all(k in d for k in ("date", "open", "high", "low", "close")):
            continue
        required.append({
            "date": d["date"],
            "open": float(d["open"]),
            "high": float(d["high"]),
            "low": float(d["low"]),
            "close": float(d["close"]),
            "volume": float(d.get("volume", 0) or 0),
        })
    return sorted(required, key=lambda x: x["date"])
```

- [x] **Step 4: Pass market index data into scan pipeline**

Modify `scanner/engine.py` near scan startup:

```python
from scanner.index_source import fetch_market_index_daily

market_data = fetch_market_index_daily()
```

Then pass it into every `analyze_dry_stable(result, data, market_data=market_data)` call.

- [x] **Step 5: Pass market data into single-stock analysis**

Modify `main.py` in `cmd_analyze()`:

```python
from scanner.index_source import fetch_market_index_daily

market_data = fetch_market_index_daily()
dry_stable = analyze_dry_stable(result, data, market_data=market_data)
```

- [x] **Step 6: Verify**

Run:

```bash
python -m pytest tests/test_index_source.py tests/test_market_env.py tests/test_dry_stable.py -q
python -m pytest tests/ -q
```

Expected: all tests pass.

- [x] **Step 7: Commit**

```bash
git add scanner/index_source.py scanner/engine.py main.py tests/test_index_source.py tests/test_market_env.py tests/test_dry_stable.py
git commit -m "Connect market index environment data"
```

---

## Task 2: Make VCP Visible in Stock Detail

**Files:**
- Modify: `server.py`
- Modify: `scanner/db.py`
- Modify: `web/src/pages/StockDetail.vue`
- Modify: `web/src/pages/ResultsRadar.vue`
- Test: `tests/test_db_strategy_fields.py`

- [x] **Step 1: Persist and return pattern type**

Extend DB/API fields with `pattern_type` and `key_pattern_type`, sourced from `dry_stable["pattern_score"]`.

In `scanner/db.py`, add columns through `_ensure_candidate_columns()`:

```python
"pattern_type": "TEXT",
"key_pattern_type": "TEXT",
```

Store:

```python
pattern.get("type", ""),
pattern.get("key_pattern_type", ""),
```

- [x] **Step 2: Add DB assertion**

Update `tests/test_db_strategy_fields.py`:

```python
assert saved["pattern_type"] == "较成熟VCP"
assert saved["key_pattern_type"] == "vcp"
```

- [x] **Step 3: Update API responses**

Add to `server.py` candidate list and detail responses:

```python
"pattern_type": c.get("pattern_type", ""),
"key_pattern_type": c.get("key_pattern_type", ""),
```

- [x] **Step 4: Update results table**

In `web/src/pages/ResultsRadar.vue`, add a compact “形态” column:

```vue
<th class="center">形态</th>
<td class="center">{{ c.pattern_type || '--' }}</td>
```

- [x] **Step 5: Update stock detail structure block**

In `web/src/pages/StockDetail.vue`, conditionally show VCP labels when `stock.key_pattern_type === 'vcp'`:

```vue
<div class="structure-title">{{ stock.key_pattern_type === 'vcp' ? 'VCP 收缩结构' : '杯柄结构时间线' }}</div>
```

For VCP, show `低吸区间 / Pivot / 止损 / 目标价 / 干稳评级` instead of cup-only stages.

- [x] **Step 6: Verify**

Run:

```bash
python -m pytest tests/test_db_strategy_fields.py -q
npm.cmd run build
```

Expected: tests pass; build succeeds.

- [x] **Step 7: Commit**

```bash
git add scanner/db.py server.py tests/test_db_strategy_fields.py web/src/pages/ResultsRadar.vue web/src/pages/StockDetail.vue
git commit -m "Expose VCP pattern type in UI"
```

---

## Task 3: Improve Backtest to Use Dry-Stable Decisions

**Files:**
- Modify: `scanner/backtester.py`
- Create: `tests/test_dry_stable_backtester.py`
- Modify: `main.py`
- Modify: `output/json_writer.py`

- [x] **Step 1: Add dry-stable backtest test**

Create `tests/test_dry_stable_backtester.py`:

```python
from scanner.backtester import summarize_by_verdict


def test_summarize_by_verdict_groups_results():
    rows = [
        {"verdict": "可低吸", "ret_10d": 5.0},
        {"verdict": "可低吸", "ret_10d": -1.0},
        {"verdict": "突破确认", "ret_10d": 2.0},
    ]

    result = summarize_by_verdict(rows)

    assert result["可低吸"]["count"] == 2
    assert result["可低吸"]["avg_ret_10d"] == 2.0
    assert result["突破确认"]["count"] == 1
```

- [x] **Step 2: Run failing test**

```bash
python -m pytest tests/test_dry_stable_backtester.py -q
```

Expected: fail because `summarize_by_verdict` does not exist.

- [x] **Step 3: Implement verdict grouping**

Add to `scanner/backtester.py`:

```python
def summarize_by_verdict(rows: list[dict]) -> dict:
    grouped = {}
    for row in rows:
        verdict = row.get("verdict", "未知")
        grouped.setdefault(verdict, {"count": 0, "returns": []})
        grouped[verdict]["count"] += 1
        grouped[verdict]["returns"].append(row.get("ret_10d", 0.0))
    return {
        k: {
            "count": v["count"],
            "avg_ret_10d": round(sum(v["returns"]) / len(v["returns"]), 2) if v["returns"] else 0.0,
        }
        for k, v in grouped.items()
    }
```

- [x] **Step 4: Add dry-stable decision to each backtest row**

Inside `run_backtest()`, call:

```python
dry = analyze_dry_stable(result, detect_data)
verdict = dry["decision"]["verdict"]
```

Store `verdict`, `volume_dry_score`, `price_stable_score`, `pattern_score_20`, `risk_percent`, and `rr1` in each backtest result dict/report row.

- [x] **Step 5: Add report field**

In `backtest_report_to_dict()`, include:

```python
"by_dry_stable_verdict": summarize_by_verdict(rows)
```

- [x] **Step 6: Verify**

Run:

```bash
python -m pytest tests/test_dry_stable_backtester.py tests/test_backtester.py -q
python -m pytest tests/ -q
```

Expected: all tests pass.

- [x] **Step 7: Commit**

```bash
git add scanner/backtester.py output/json_writer.py main.py tests/test_dry_stable_backtester.py
git commit -m "Backtest dry-stable strategy verdicts"
```

---

## Task 4: Complete Strategy Explanation Output

**Files:**
- Modify: `analyzer/dry_stable.py`
- Modify: `analyzer/decision.py`
- Modify: `server.py`
- Modify: `web/src/pages/StockDetail.vue`
- Test: `tests/test_dry_stable.py`

- [x] **Step 1: Add explanation test**

Update `tests/test_dry_stable.py`:

```python
def test_dry_stable_outputs_trade_plan_sections():
    analysis = analyze_dry_stable(CupHandleResult(found=False), _make_vcp_data())

    assert "trade_plan" in analysis
    assert "buy_reasons" in analysis["trade_plan"]
    assert "stop_reasons" in analysis["trade_plan"]
    assert "target_reasons" in analysis["trade_plan"]
    assert "invalid_conditions" in analysis["trade_plan"]
```

- [x] **Step 2: Implement trade plan payload**

In `analyzer/dry_stable.py`, add:

```python
"trade_plan": {
    "can_act": decision.verdict in ("可低吸", "突破确认"),
    "buy_reasons": decision.reasons,
    "stop_reasons": [
        "止损价低于关键支撑或最后收缩低点",
        "跌破止损说明低风险结构失效",
    ],
    "target_reasons": [
        "第一目标按2R计算",
        "第二目标按3R或形态量度目标约束",
    ],
    "invalid_conditions": decision.invalid_conditions,
}
```

- [x] **Step 3: Expose trade plan in API detail**

Persist summary fields only in DB; for full detail, compute on demand in `/api/candidate/{code}` by loading OHLC and calling `analyze_dry_stable()` again.

- [x] **Step 4: Display trade plan**

In `web/src/pages/StockDetail.vue`, add a compact “交易计划” section with buy, stop, target, invalid condition rows.

- [x] **Step 5: Verify**

Run:

```bash
python -m pytest tests/test_dry_stable.py -q
npm.cmd run build
```

Expected: tests pass; build succeeds.

- [x] **Step 6: Commit**

```bash
git add analyzer/dry_stable.py analyzer/decision.py server.py web/src/pages/StockDetail.vue tests/test_dry_stable.py
git commit -m "Add dry-stable trade plan output"
```

---

## Task 5: Optimize Frontend Bundle Size

**Files:**
- Modify: `web/src/pages/StockDetail.vue`
- Modify: `web/vite.config.js`

- [x] **Step 1: Replace static ECharts import**

In `web/src/pages/StockDetail.vue`, replace:

```js
import * as echarts from 'echarts'
```

with lazy import inside `initChart()`:

```js
const echarts = await import('echarts')
```

- [x] **Step 2: Verify build chunk split**

Run:

```bash
npm.cmd run build
```

Expected: build succeeds; initial route chunks are smaller. If warning remains only for lazy chart chunk, accept it.

- [x] **Step 3: Commit**

```bash
git add web/src/pages/StockDetail.vue web/vite.config.js
git commit -m "Lazy load chart dependency"
```

---

## Task 6: Final Verification and Documentation

**Files:**
- Modify: `README.md`
- Modify: `operations-log.md`

- [ ] **Step 1: Update README strategy section**

Document:

```markdown
The scanner now filters candidates through dry-stable low-risk rules:
- Volume dry score
- Price stability score
- Cup/VCP pattern score
- Key price, stop, target, RR
- Market environment
- Final verdict: 可低吸 / 突破确认 / 观察 / 不建议买入
```

- [ ] **Step 2: Final full verification**

Run:

```bash
python -m pytest tests/ -q
python -m compileall analyzer scanner main.py server.py output tests
npm.cmd run build
```

Expected:
- pytest passes
- compileall passes
- Vite build succeeds

- [ ] **Step 3: Record verification**

Append to `operations-log.md`:

```markdown
- Final verification passed after strategy completion: pytest, compileall, and web build.
```

- [ ] **Step 4: Commit**

```bash
git add README.md operations-log.md
git commit -m "Document dry-stable strategy workflow"
```

---

## Remaining Risks

- Market index fetch may need a source-specific code format adjustment if Sina index symbols differ from stock symbols.
- VCP scoring is deliberately simple; real-world validation may require tuning swing detection windows.
- Frontend chart bundle warning is acceptable short term, but lazy loading should reduce initial page cost.

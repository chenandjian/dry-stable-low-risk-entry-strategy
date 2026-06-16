# 个股 K 线数据诊断页实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 新增独立页面和 API，用于分页查看个股本地历史 K 线，并展示是否覆盖最近一个完整交易日。

**架构：** 后端在 `scanner/db.py` 增加只读分页与最近 K 线元数据查询，`server.py` 暴露诊断 API 并复用 `build_cache_freshness_context()` 计算 summary。前端通过 `useApi.js`、路由、导航和新页面展示查询表单、状态卡、K 线表格和分页。

**技术栈：** Python FastAPI + SQLite，Vue 3 + Vue Router + Vitest。

---

## 文件结构

- 修改：`scanner/db.py`  
  增加 `get_ohlc_history_page()` 和 `get_latest_task_stock_kline_metadata()`。
- 修改：`server.py`  
  增加 `/api/stock/{code}/kline-history`。
- 创建：`tests/test_kline_history_api.py`  
  覆盖分页、过滤、新鲜度、停牌可接受、参数错误。
- 修改：`web/src/composables/useApi.js`  
  增加 `getKlineHistory()`。
- 修改：`web/src/router/index.js`  
  增加 `/data/kline-history` 路由。
- 修改：`web/src/components/TopNav.vue`  
  增加 `K线数据` 导航项。
- 创建：`web/src/pages/KlineHistory.vue`  
  独立诊断页。
- 创建：`web/src/pages/__tests__/KlineHistory.test.js`  
  覆盖 summary、表格、分页和需重拉状态。

## 任务 1：后端 API 红灯测试

- [ ] **步骤 1：创建失败测试**

在 `tests/test_kline_history_api.py` 写入：

```python
from datetime import datetime

from fastapi.testclient import TestClient

import server
from scanner import db


def _row(day: str, close: float = 10.0) -> dict:
    return {
        "date": day,
        "open": close,
        "high": close + 0.5,
        "low": close - 0.5,
        "close": close,
        "volume": 1000,
        "turnover": close * 1000,
    }


def test_kline_history_returns_paginated_rows_and_fresh_summary(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    db.save_ohlc("000831", [_row("2026-06-12", 9), _row("2026-06-15", 10), _row("2026-06-16", 11)])
    db.create_scan_task("task-1", "2026-06-16 15:20:00", total_stocks=1)
    db.save_task_stocks("task-1", [{"code": "000831", "name": "五矿稀土", "market": "深证主板"}])
    db.update_task_stock(
        "task-1",
        "000831",
        status="scanned",
        kline_latest_date="2026-06-16",
        kline_fetched_at="2026-06-16 15:12:00",
        kline_target_trade_date="2026-06-16",
        quote_status="not_requested",
    )
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": {"data": {"database_path": str(tmp_path / "cuphandle.db")}})
    monkeypatch.setattr(server, "_now", lambda: datetime(2026, 6, 16, 15, 20, 0), raising=False)

    res = TestClient(server.app).get(
        "/api/stock/000831/kline-history",
        params={"start_date": "2026-06-15", "end_date": "2026-06-16", "page": 1, "page_size": 1},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 2
    assert body["rows"][0]["date"] == "2026-06-16"
    assert body["summary"]["target_trade_date"] == "2026-06-16"
    assert body["summary"]["latest_kline_date"] == "2026-06-16"
    assert body["summary"]["latest_fetch_time"] == "2026-06-16 15:12:00"
    assert body["summary"]["is_fresh"] is True
    assert body["summary"]["needs_refetch"] is False
```

- [ ] **步骤 2：运行红灯**

运行：

```bash
python -m pytest tests/test_kline_history_api.py -q
```

预期：FAIL，原因是接口不存在或 helper 不存在。

## 任务 2：后端最小实现

- [ ] **步骤 1：实现 DB helper**

在 `scanner/db.py` 中添加：

```python
def get_ohlc_history_page(code: str, start_date: str | None = None, end_date: str | None = None, page: int = 1, page_size: int = 50) -> dict:
    page = max(1, int(page or 1))
    page_size = min(200, max(1, int(page_size or 50)))
    offset = (page - 1) * page_size
    clauses = ["code = ?"]
    params = [code]
    if start_date:
        clauses.append("date >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("date <= ?")
        params.append(end_date)
    where = " AND ".join(clauses)
    conn = get_conn()
    total = conn.execute(f"SELECT COUNT(*) FROM daily_ohlc WHERE {where}", params).fetchone()[0]
    rows = conn.execute(
        f"""SELECT date, open, high, low, close, volume, turnover
            FROM daily_ohlc WHERE {where}
            ORDER BY date DESC LIMIT ? OFFSET ?""",
        [*params, page_size, offset],
    ).fetchall()
    return {
        "rows": [{"date": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5], "turnover": r[6]} for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_latest_task_stock_kline_metadata(code: str) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        """SELECT kline_latest_date, kline_fetched_at, kline_target_trade_date, quote_status
           FROM task_stocks
           WHERE code=? AND (kline_latest_date IS NOT NULL OR kline_fetched_at IS NOT NULL)
           ORDER BY kline_fetched_at DESC, updated_at DESC
           LIMIT 1""",
        (code,),
    ).fetchone()
    if not row:
        return None
    return {
        "kline_latest_date": row[0],
        "kline_fetched_at": row[1],
        "kline_target_trade_date": row[2],
        "quote_status": row[3] or "not_requested",
    }
```

- [ ] **步骤 2：实现 API**

在 `server.py` 的 `/api/stock/{code}/ohlc` 附近新增：

```python
@app.get("/api/stock/{code}/kline-history")
async def get_stock_kline_history(code: str, start_date: str = None, end_date: str = None, page: int = 1, page_size: int = 50):
    if start_date and end_date and start_date > end_date:
        return JSONResponse({"error": "Invalid date range", "message": "start_date must be <= end_date"}, status_code=400)
    page_data = db.get_ohlc_history_page(code, start_date=start_date, end_date=end_date, page=page, page_size=page_size)
    meta = db.get_latest_task_stock_kline_metadata(code) or {}
    context = build_cache_freshness_context(now=_now(), fetched_at=meta.get("kline_fetched_at"), allow_previous_trade_date=True, quote_status=meta.get("quote_status"))
    summary = _build_kline_history_summary(code, page_data["rows"], meta, context)
    return {"code": code, **page_data, "summary": summary}
```

并实现 `_build_kline_history_summary()`，使用 `db.get_ohlc_latest_date(code)` 作为全量最新 K 线日期，不受当前分页过滤影响。

- [ ] **步骤 3：运行绿灯**

运行：

```bash
python -m pytest tests/test_kline_history_api.py -q
```

预期：PASS。

## 任务 3：补齐后端边界测试

- [ ] **步骤 1：新增测试**

在 `tests/test_kline_history_api.py` 追加：

```python
def test_kline_history_accepts_suspended_stock_with_recent_fetch(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    db.save_ohlc("000831", [_row("2026-06-15", 10)])
    db.create_scan_task("task-suspended", "2026-06-16 15:20:00", total_stocks=1)
    db.save_task_stocks("task-suspended", [{"code": "000831", "name": "五矿稀土", "market": "深证主板"}])
    db.update_task_stock(
        "task-suspended",
        "000831",
        status="scanned",
        kline_latest_date="2026-06-15",
        kline_fetched_at="2026-06-16 15:12:00",
        kline_target_trade_date="2026-06-16",
        quote_status="suspended",
    )
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": {"data": {"database_path": str(tmp_path / "cuphandle.db")}})
    monkeypatch.setattr(server, "_now", lambda: datetime(2026, 6, 16, 15, 20, 0), raising=False)

    res = TestClient(server.app).get("/api/stock/000831/kline-history")

    assert res.status_code == 200
    summary = res.json()["summary"]
    assert summary["latest_kline_date"] == "2026-06-15"
    assert summary["quote_status"] == "suspended"
    assert summary["is_fresh"] is True
    assert summary["needs_refetch"] is False


def test_kline_history_marks_missing_or_stale_data_as_needing_refetch(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    db.save_ohlc("000831", [_row("2026-06-15", 10)])
    db.create_scan_task("task-stale", "2026-06-16 14:50:00", total_stocks=1)
    db.save_task_stocks("task-stale", [{"code": "000831", "name": "五矿稀土", "market": "深证主板"}])
    db.update_task_stock(
        "task-stale",
        "000831",
        status="scanned",
        kline_latest_date="2026-06-15",
        kline_fetched_at="2026-06-16 14:50:00",
        kline_target_trade_date="2026-06-16",
        quote_status="not_requested",
    )
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": {"data": {"database_path": str(tmp_path / "cuphandle.db")}})
    monkeypatch.setattr(server, "_now", lambda: datetime(2026, 6, 16, 15, 20, 0), raising=False)

    res = TestClient(server.app).get("/api/stock/000831/kline-history")

    assert res.status_code == 200
    summary = res.json()["summary"]
    assert summary["is_fresh"] is False
    assert summary["needs_refetch"] is True
    assert "重新拉取" in summary["reason"]


def test_kline_history_rejects_invalid_date_range(monkeypatch, tmp_path):
    db.init_db(str(tmp_path / "cuphandle.db"))
    monkeypatch.setattr(server, "load_config", lambda path="config.yaml": {"data": {"database_path": str(tmp_path / "cuphandle.db")}})

    res = TestClient(server.app).get(
        "/api/stock/000831/kline-history",
        params={"start_date": "2026-06-17", "end_date": "2026-06-16"},
    )

    assert res.status_code == 400
    assert res.json()["error"] == "Invalid date range"
```

测试内容分别覆盖停牌可接受、无/旧数据需重拉、日期范围错误。

- [ ] **步骤 2：运行红灯/绿灯**

运行：

```bash
python -m pytest tests/test_kline_history_api.py -q
```

预期：新增测试先暴露缺口，再调整 `_build_kline_history_summary()` 到全部通过。

## 任务 4：前端红灯测试

- [ ] **步骤 1：创建失败测试**

创建 `web/src/pages/__tests__/KlineHistory.test.js`：

```javascript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

const api = { getKlineHistory: vi.fn() }
vi.mock('../../composables/useApi.js', () => ({ useApi: () => api }))

import KlineHistory from '../KlineHistory.vue'

async function flushUi() {
  await Promise.resolve()
  await nextTick()
  await Promise.resolve()
  await nextTick()
}

describe('KlineHistory', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.getKlineHistory.mockResolvedValue({
      code: '000831',
      rows: [{ date: '2026-06-16', open: 10, high: 11, low: 9, close: 10.5, volume: 1000, turnover: 10500 }],
      total: 1,
      page: 1,
      page_size: 50,
      summary: {
        latest_kline_date: '2026-06-16',
        latest_fetch_time: '2026-06-16 15:12:00',
        target_trade_date: '2026-06-16',
        is_fresh: true,
        needs_refetch: false,
        quote_status: 'not_requested',
        reason: '数据已覆盖目标完整交易日',
      },
    })
  })

  it('renders freshness summary and kline rows', async () => {
    const wrapper = mount(KlineHistory)
    await flushUi()
    expect(wrapper.text()).toContain('个股 K 线数据诊断')
    expect(wrapper.text()).toContain('数据最新')
    expect(wrapper.text()).toContain('2026-06-16')
    expect(wrapper.text()).toContain('10.50')
  })
})
```

- [ ] **步骤 2：运行红灯**

运行：

```bash
npm --prefix web test -- --run web/src/pages/__tests__/KlineHistory.test.js
```

预期：FAIL，原因是页面或 API 方法不存在。

## 任务 5：前端最小实现

- [ ] **步骤 1：修改 API、路由、导航**

在 `useApi.js` 增加 `getKlineHistory()` 并导出；在路由和 `TopNav.vue` 增加页面入口。

- [ ] **步骤 2：创建 `KlineHistory.vue`**

实现表单、状态卡、表格和分页。默认股票代码使用 `000831`，页面 mounted 后自动查询一次，便于用户进入后立即看到页面结构。

- [ ] **步骤 3：运行绿灯**

运行：

```bash
npm --prefix web test -- --run web/src/pages/__tests__/KlineHistory.test.js
```

预期：PASS。

## 任务 6：补齐前端交互测试

- [ ] **步骤 1：追加测试**

在 `KlineHistory.test.js` 追加：

1. 点击下一页会调用 `getKlineHistory()`，参数中 `page=2`。
2. `needs_refetch=true` 时显示“需要重新拉取”。

- [ ] **步骤 2：运行前端专项测试**

运行：

```bash
npm --prefix web test -- --run web/src/pages/__tests__/KlineHistory.test.js
```

预期：PASS。

## 任务 7：回归验证与审核

- [ ] **步骤 1：运行后端专项**

```bash
python -m pytest tests/test_kline_history_api.py tests/test_daily_kline_cache_freshness.py -q
```

- [ ] **步骤 2：运行前端专项**

```bash
npm --prefix web test -- --run web/src/pages/__tests__/KlineHistory.test.js
```

- [ ] **步骤 3：运行编译与构建**

```bash
python -m compileall scanner strategy2 scheduler server.py main.py -q
npm --prefix web run build
```

- [ ] **步骤 4：审核检查**

检查：

1. API 不触发外部数据源。
2. Summary 使用全量最新 K 线日期，不受分页过滤影响。
3. 停牌/无交易不会被误判为必须失败重拉。
4. 页面不会修改策略配置或扫描任务。
5. 没有中/高等级问题后提交。

## 任务 8：提交与推送

- [ ] **步骤 1：查看状态**

```bash
git status --short
```

- [ ] **步骤 2：提交**

```bash
git add docs/superpowers/specs/2026-06-16-kline-history-diagnostics-design.md docs/superpowers/plans/2026-06-16-kline-history-diagnostics.md scanner/db.py server.py tests/test_kline_history_api.py web/src/composables/useApi.js web/src/router/index.js web/src/components/TopNav.vue web/src/pages/KlineHistory.vue web/src/pages/__tests__/KlineHistory.test.js
git commit -m "feat: add kline history diagnostics page"
```

- [ ] **步骤 3：推送**

```bash
git push -u origin codex/kline-history-diagnostics
```

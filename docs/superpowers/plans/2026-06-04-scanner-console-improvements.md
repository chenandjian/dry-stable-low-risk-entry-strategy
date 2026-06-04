# Scanner Console Improvements — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复双线程数据源并发 bug，添加市场状态和实时时钟显示。

**Architecture:** 后端 2 个文件改动（去掉 tencent 源的内置新浪回退 + 去掉 engine 里 tencent 额外抢新浪锁），前端 1 个文件改动（市场状态指示 + 实时时钟）。

**Tech Stack:** Python (engine.py, tencent_source.py), Vue 3 (ScannerConsole.vue)

---

### Task 1: 去掉 tencent_source 内部的新浪回退

**Files:**
- Modify: `scanner/tencent_source.py`

- [ ] **Step 1: 删除 `_try_sina_kline` 函数和 `fetch_tencent_daily` 中的回退调用**

编辑 `scanner/tencent_source.py`：

```python
# scanner/tencent_source.py
import requests
import json
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

    return _try_tencent_kline(symbol, days)


def _try_tencent_kline(symbol: str, days: int) -> list[dict] | None:
    """Attempt Tencent K-line API."""
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    params = {
        "param": f"{symbol},day,,,{days}",
        "_var": "kline_day",
    }

    try:
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        text = resp.text

        json_str = text.split("=", 1)[1].strip() if "=" in text else text
        data = json.loads(json_str)

        if data.get("code") != 0:
            return None

        stock_data = data.get("data", {}).get(symbol, {})
        klines = stock_data.get("qfqday") or stock_data.get("day", [])

        if not klines:
            return None

        result = []
        for item in klines:
            result.append({
                "date": item[0],
                "open": float(item[1]),
                "close": float(item[2]),
                "high": float(item[3]),
                "low": float(item[4]),
                "volume": float(item[5]),
                "turnover": float(item[2]) * float(item[5]),
            })
        return result

    except Exception:
        return None
```

改动内容：
- 删除第 32-37 行：`fetch_tencent_daily` 里对 `_try_sina_kline` 的回退调用
- 删除第 82-127 行：整个 `_try_sina_kline` 函数
- 删除第 5 行：不再需要的 `import time`
- 更新 docstring：移除"内部回退到新浪API"描述
- `fetch_tencent_daily` 现在直接 `return _try_tencent_kline(symbol, days)`

- [ ] **Step 2: 运行现有测试确认没有破坏功能**

```bash
python -m pytest tests/ -v -k "tencent or source"
```

预期：已有测试通过（如果有 tencent_source 的测试）

- [ ] **Step 3: 提交**

```bash
git add scanner/tencent_source.py
git commit -m "fix: 去掉 tencent_source 内部的新浪回退，改为纯腾讯源"
```

---

### Task 2: 去掉 engine.py 里 tencent 源的额外新浪锁

**Files:**
- Modify: `scanner/engine.py`

- [ ] **Step 1: 简化 `_try_fetch_source` 函数**

当前 `_try_fetch_source`（第 427-459 行）替换为：

```python
def _try_fetch_source(
    code: str,
    ds_name: str,
    attempts: int,
    sleep_fn: Callable[[float], None],
) -> tuple[list[dict] | None, int, str | None]:
    """Try fetching from a data source with retries and backoff."""
    fetch_fn = fetch_sina_daily if ds_name == "sina" else fetch_tencent_daily

    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            data = fetch_fn(code)
            if data:
                return data, attempt, None
            last_error = "empty response"
        except Exception as exc:
            last_error = str(exc)
        if attempt < attempts:
            sleep_fn(min(0.5 * attempt, 2.0))
    return None, attempts, last_error
```

改动：删除 `mgr` 和 `held_sources` 参数，删除 tencent 额外抢新浪锁的逻辑，删除 `extra_sina_lock` / `finally` 释放逻辑。

- [ ] **Step 2: 更新 `_fetch_with_retry` 中的调用处**

`_fetch_with_retry`（第 362-418 行）中，删除 `held_sources` 变量，简化 `_try_fetch_source` 调用：

**第 373 行**，删除：
```python
held_sources = {primary_ds} if mgr is not None else None
```

**第 376-383 行**，主源调用改为：
```python
data, attempts, error = _try_fetch_source(
    code,
    primary_ds,
    retry_attempts,
    sleep_fn,
)
```

**第 398-405 行**，备源调用改为：
```python
data, attempts, error = _try_fetch_source(
    code,
    fallback_ds,
    fallback_attempts,
    sleep_fn,
)
```

**第 409 行**，else 分支改为：
```python
data, attempts, error = _try_fetch_source(code, fallback_ds, fallback_attempts, sleep_fn)
```

- [ ] **Step 3: 运行引擎测试确认并发逻辑正确**

```bash
python -m pytest tests/test_engine_fresh_fetch.py -v
```

预期：所有测试通过。

- [ ] **Step 4: 提交**

```bash
git add scanner/engine.py
git commit -m "fix: 删除 tencent 源的额外新浪锁，恢复双线程并发扫描"
```

---

### Task 3: ScannerConsole 右上角添加市场状态和实时时钟

**Files:**
- Modify: `web/src/pages/ScannerConsole.vue`

- [ ] **Step 1: 在 template 顶部添加状态栏**

在 `<div class="page-content">` 之后、`<div class="metrics-row">` 之前插入：

```html
<!-- Market Status Bar -->
<div class="status-bar">
  <span class="market-status">
    <span class="status-dot" :class="marketStatusClass"></span>
    {{ marketStatusText }}
  </span>
  <span class="status-sep">|</span>
  <span class="current-time">{{ currentTime }}</span>
</div>
```

- [ ] **Step 2: 在 script setup 中添加状态逻辑**

在 `const router = useRouter()` 之后插入：

```javascript
// Market status
const currentTime = ref('')
const marketStatusText = ref('')
const marketStatusClass = ref('')

function updateTime() {
  const now = new Date()
  const hh = String(now.getHours()).padStart(2, '0')
  const mm = String(now.getMinutes()).padStart(2, '0')
  const ss = String(now.getSeconds()).padStart(2, '0')
  currentTime.value = `${hh}:${mm}:${ss}`

  const day = now.getDay()
  const totalMinutes = now.getHours() * 60 + now.getMinutes()
  const isWeekday = day >= 1 && day <= 5

  // Trading sessions in minutes: 9:30-11:30, 13:00-15:00
  const MORNING_OPEN  = 9 * 60 + 30   // 570
  const MORNING_CLOSE = 11 * 60 + 30  // 690
  const AFTERNOON_OPEN  = 13 * 60     // 780
  const AFTERNOON_CLOSE = 15 * 60     // 900

  const inSession = (totalMinutes >= MORNING_OPEN && totalMinutes <= MORNING_CLOSE)
                 || (totalMinutes >= AFTERNOON_OPEN && totalMinutes <= AFTERNOON_CLOSE)

  if (isWeekday && inSession) {
    marketStatusText.value = '开盘中'
    marketStatusClass.value = 'open'
  } else if (isWeekday && totalMinutes > AFTERNOON_CLOSE) {
    marketStatusText.value = '已收盘'
    marketStatusClass.value = 'closed'
  } else {
    marketStatusText.value = '未开盘'
    marketStatusClass.value = 'pre'
  }
}
```

- [ ] **Step 3: 在 onMounted 和 onUnmounted 中添加定时器**

修改 `onMounted`：在现有代码末尾加：
```javascript
updateTime()
if (!pollTimer) {
  pollTimer = setInterval(() => { updateTime() }, 1000)
}
```

注意：当前代码里 `pollTimer` 已经用于扫描状态轮询。需要把时钟的定时器独立出来，避免冲突。新增一个 `let clockTimer = null`：

```javascript
let pollTimer = null
let clockTimer = null   // ← 新增
```

`onMounted` 末尾加：
```javascript
updateTime()
clockTimer = setInterval(updateTime, 1000)
```

`onUnmounted` 改为：
```javascript
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (clockTimer) clearInterval(clockTimer)
})
```

- [ ] **Step 4: 添加样式**

在 `<style scoped>` 末尾添加：

```css
.status-bar {
  display: flex; align-items: center; justify-content: flex-end; gap: 10px;
  margin-bottom: 12px; font-size: 13px;
}
.status-dot {
  display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px;
}
.status-dot.open { background: #22C55E; box-shadow: 0 0 6px rgba(34,197,94,0.4); }
.status-dot.closed { background: #F59E0B; }
.status-dot.pre { background: #5A6A7E; }
.status-sep { color: var(--border); }
.current-time { color: var(--text-primary); font-family: var(--font-mono); font-size: 14px; }
```

- [ ] **Step 5: 运行前端确认页面正常**

```bash
npm --prefix web run dev -- --host 127.0.0.1
```

打开 `http://localhost:5173`，确认：
- 右上角显示市场状态和实时时钟
- 时钟每秒更新
- 扫描功能正常

- [ ] **Step 6: 提交**

```bash
git add web/src/pages/ScannerConsole.vue
git commit -m "feat: ScannerConsole 右上角添加市场状态和实时时钟"
```

---

### Task 4: 端到端验证

- [ ] **Step 1: 启动后端服务**

```bash
python main.py serve --port 8080
```

- [ ] **Step 2: 启动前端**

```bash
npm --prefix web run dev -- --host 127.0.0.1
```

- [ ] **Step 3: 验证并发扫描**

打开浏览器，点击"开始扫描"。在后端日志中确认两个数据源同时有请求（sina 和 tencent 请求交替出现）。

- [ ] **Step 4: 验证市场状态和时钟**

确认右上角显示正确状态和实时时间。

- [ ] **Step 5: 提交**

```bash
# 如有改动则提交
```

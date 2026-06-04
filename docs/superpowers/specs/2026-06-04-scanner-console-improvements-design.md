# Scanner Console Improvements — Design Spec

## Date
2026-06-04

## Scope
机会雷达页（ScannerConsole.vue）3 项改动：1 个后端并发 bug 修复 + 2 个前端 UI 优化。

---

## 1. 数据源并发修复（Bug）

### Problem

`_try_fetch_source()` 在 engine.py 第 439-441 行有一段逻辑：当线程用 tencent 源拉数据时，额外尝试抢 sina 锁。抢不到就直接返回 `"data source busy"`，连腾讯请求都不发了。

实际效果：只要线程 1 拿着新浪锁在拉数据，线程 2 即使拿到了腾讯锁也无法工作。两个线程都在抢新浪，腾讯源形同虚设。

### Fix

**改 2 个文件：**

#### `scanner/tencent_source.py`

删除 `fetch_tencent_daily()` 内部的 `_try_sina_kline()` 回退逻辑。函数变为纯腾讯源——成功返回数据，失败返回 None。回退统一由引擎层的 `_fetch_with_retry` 处理。

改动点：
- 删除 `_try_sina_kline` 函数（或标记为废弃）
- `fetch_tencent_daily` 中删除对 `_try_sina_kline` 的调用
- 只保留 `_try_tencent_kline` 调用

#### `scanner/engine.py`

`_try_fetch_source` 函数中删除 tencent 源的额外新浪锁逻辑：

```python
# 删除这段（当前第 439-442 行）
if mgr is not None and ds_name == "tencent" and "sina" not in held_sources:
    if not mgr.acquire("sina"):
        return None, 0, "data source busy"
    extra_sina_lock = True

# 删除 finally 中的释放（当前第 458-459 行）
if extra_sina_lock:
    mgr.release("sina")
```

同时：
- 函数签名删除 `held_sources` 参数
- 调用处 `_fetch_with_retry` 不再传 `held_sources`
- `_try_fetch_source` 简化为：`_try_fetch_source(code, ds_name, attempts, sleep_fn, mgr)`

### Expected Result

```
线程1: 拿新浪锁 → fetch_sina_daily(股票A) → 释放新浪锁
线程2: 拿腾讯锁 → fetch_tencent_daily(股票B) → 释放腾讯锁
        ↑ 同时进行，互不干扰 ↑
```

双线程真正并发扫描，充分利用两个数据源。

### Not in Scope
- `_fetch_with_retry` 的 fallback 逻辑保持不变
- DataSourceManager 锁机制保持不变
- 线程数、重试次数等参数不变

---

## 2. 右上角 A 股开盘状态

### Feature
ScannerConsole.vue 右上角显示当前 A 股交易状态。

### States

| 状态 | 显示 | 颜色 | 条件 |
|------|------|------|------|
| 开盘中 | 🟢 开盘中 | 绿色 `#22C55E` | 周一至周五 9:30-11:30 或 13:00-15:00 |
| 已收盘 | 🟡 已收盘 | 橙黄 `#F59E0B` | 周一至周五 15:00 之后 |
| 未开盘 | ⚪ 未开盘 | 灰色 `#5A6A7E` | 周一至周五 0:00-9:30 或周末全天 |

### Implementation
- 纯前端 computed，基于 `new Date()` 计算星期几和时分
- 放在页面右上角，与实时时钟并排
- 暂不处理节假日（后续可加 API）

---

## 3. 右上角实时时钟

### Feature
与市场状态并列显示 `HH:MM:SS` 格式的实时时钟。

### Implementation
- `ref<string>` 存储当前时间字符串
- `onMounted` 中 `setInterval` 每秒更新
- `onUnmounted` 中 `clearInterval` 清理
- 颜色：白色/浅色 `var(--text-primary)`

### Layout
```
页面右上角:
  🟢 开盘中  │  14:35:28
```

---

## Test Plan

### Concurrency Fix
1. 启动扫描，观察日志确认两个数据源同时有请求
2. 检查 `task_stocks` 表中 primary_source 分布：sina 和 tencent 应均有使用
3. 对比修复前后扫描耗时

### Market Status + Clock
1. 在不同时间段访问页面，验证状态显示正确
2. 验证时钟实时更新，无需刷新页面
3. `onUnmounted` 时确认定时器已清理（无控制台警告）

# 日线缓存完整交易日新鲜度实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 扫描前按“最近一个完整交易日 + 拉取时间”判断日线缓存是否可复用，策略1和策略2互相复用当天已完成拉取的数据，停牌股票不进入失败无限重试。

**架构：** 在 `scanner/daily_data_service.py` 增加交易日目标与缓存新鲜度 helper；在 `scanner/db.py` 为 `task_stocks` 兼容新增拉取元数据字段；策略1 `scanner/engine.py` 和策略2 `strategy2/scanner.py` 调用同一套 helper。默认交易日历只判断周一到周五。

**技术栈：** Python 3.10、SQLite 兼容迁移、pytest。

---

### 任务 1：共享缓存新鲜度测试

**文件：**
- 测试：`tests/test_daily_kline_cache_freshness.py`
- 修改：`scanner/daily_data_service.py`

- [ ] **步骤 1：编写失败测试**

覆盖：
- 周一 14:00 目标交易日为上周五。
- 周一 15:10 后目标交易日为周一。
- 周六目标交易日为周五。
- 缓存覆盖目标日但拉取时间早于目标日 15:00，不可复用。
- 缓存覆盖目标日且拉取时间晚于目标日 15:00，可复用。
- 停牌元数据允许使用上一有效 K 线。

- [ ] **步骤 2：运行测试验证失败**

运行：

```bash
python -m pytest tests/test_daily_kline_cache_freshness.py -q
```

预期：因 helper 尚未实现或行为不满足而失败。

- [ ] **步骤 3：实现最小共享 helper**

在 `scanner/daily_data_service.py` 增加 `CacheFreshnessContext`、`CacheFreshnessDecision`、`compute_target_trade_date()`、`build_cache_freshness_context()`、`select_fresh_cached_ohlc()` 新逻辑。

- [ ] **步骤 4：运行测试验证通过**

运行：

```bash
python -m pytest tests/test_daily_kline_cache_freshness.py -q
```

预期：全部通过。

### 任务 2：DB 元数据与扫描入口集成

**文件：**
- 修改：`scanner/db.py`
- 修改：`scanner/engine.py`
- 修改：`strategy2/scanner.py`
- 测试：`tests/test_scan_task_tracking.py`
- 测试：`tests/test_engine_fresh_fetch.py`
- 测试：`tests/test_strategy2_acceptance_fixes.py`

- [ ] **步骤 1：编写失败测试**

覆盖：
- `task_stocks` 新增 `kline_fetched_at`、`kline_target_trade_date`。
- 查询复用元数据时要求目标交易日和拉取时间有效。
- 策略1传入共享 cache context，不再只传 `kline_latest_date`。
- 策略2同样传入共享 cache context。

- [ ] **步骤 2：运行测试验证失败**

运行：

```bash
python -m pytest tests/test_scan_task_tracking.py tests/test_engine_fresh_fetch.py::test_scan_all_passes_existing_today_stock_latest_trade_date_to_fetch tests/test_strategy2_acceptance_fixes.py::TestStrategy2AcceptanceFixes::test_strategy2_scan_passes_existing_today_stock_latest_trade_date_to_fetch -q
```

预期：新增断言失败。

- [ ] **步骤 3：实现最小集成**

兼容新增列；新增 `get_reusable_task_stock_kline_context()`；更新策略1/2扫描入口和 fetch 成功落库字段。

- [ ] **步骤 4：运行专项与回归验证**

运行：

```bash
python -m pytest tests/test_daily_kline_cache_freshness.py tests/test_scan_task_tracking.py tests/test_engine_fresh_fetch.py tests/test_strategy2_acceptance_fixes.py -q
python -m compileall scanner strategy2 scheduler server.py main.py -q
```

预期：全部通过。

### 任务 3：审核与收尾

**文件：**
- 修改：相关代码和测试

- [ ] **步骤 1：审核中高风险**

检查：
- 全源失败不会因旧缓存产生扫描结果。
- 停牌只在 fresh 拉取成功后标记，不吞掉真实全源失败。
- 策略评分入口未改动。

- [ ] **步骤 2：提交与推送**

运行：

```bash
git status --short
git add <相关文件>
git commit -m "fix: validate daily kline cache freshness"
git push
```

预期：提交成功；push 成功或如实报告失败原因。

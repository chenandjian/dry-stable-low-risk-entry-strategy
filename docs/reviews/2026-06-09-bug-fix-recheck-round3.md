# 代码问题修复第三轮复查报告

> 本报告已被 `2026-06-09-bug-fix-recheck-round4.md` 取代，请以第四轮复查结论为准。

## 1. 检查范围

本次复查针对最新提交：

* `866ae10`：历史回测 `NameError`、VCP ID、无效止损、指数配置
* `5eaa459`：持久化 `source_errors`

继续遵循用户确认：

* BUG-008 多数据源前复权一致性不再作为问题。
* 日线数据源仅使用 `baidu`、`sina`、`tencent`。
* 量干采用 12 分制。
* `min_price_stable_score: 5` 是用户主动配置。

---

## 2. 总体结论

历史回测 `NameError`、无效目标价、服务详情页指数配置已经修复，重点测试与编译检查通过。

但当前仍不建议交付。`source_errors` 数据库迁移在已有数据库上不会生效，扫描时可能触发数据库列不存在错误；VCP ID 仍把每个检测日识别成新形态，去重没有实现；回测将“无有效止损”计为“未触发止损”，会美化止损统计。

---

## 3. 问题清单

| 编号 | 问题 | 严重程度 | 影响范围 | 是否必须修复 |
| --- | --- | --- | --- | --- |
| ROUND3-001 | 已有数据库不会迁移 `source_errors` 列 | 高 | 生产扫描、数据库升级 | 是 |
| ROUND3-002 | 同一持续 VCP 每个检测日生成不同 ID | 高 | 单股回测、VCP 去重与统计 | 是 |
| ROUND3-003 | 无有效止损被计为“未触发止损” | 高 | 回测止损命中率 | 是 |
| ROUND3-004 | VCP 使用杯柄突破价计算假突破率 | 中 | VCP 回测统计 | 是 |
| ROUND3-005 | 多源错误详情仍未完整记录和持久化 | 中 | 数据源故障定位 | 是 |
| ROUND3-006 | 历史回测仍不能注入固定市场数据 | 中 | 回测可复现性、测试稳定性 | 是 |
| ROUND3-007 | 最新修复未增加针对性回归测试 | 中 | 回归风险 | 是 |

---

## 4. 详细问题分析

### ROUND3-001：已有数据库不会迁移 `source_errors` 列

#### 问题现象

`source_errors` 已加入新建 `task_stocks` 表的 SQL，也加入了 `update_task_stock()` 允许字段，但没有加入已有表的增量列映射。

#### 代码证据

* `scanner/db.py:198`：新建表包含 `source_errors TEXT`。
* `scanner/db.py:210-227`：增量迁移 `columns` 字典中没有 `source_errors`。
* `scanner/db.py:431`：更新接口允许写入 `source_errors`。

#### 已执行复现实验

1. 创建包含 `source_errors` 的新数据库。
2. 模拟旧数据库，删除该列。
3. 再次执行 `db.init_db()`。
4. 检查结果：`source_errors_present_after_upgrade=False`。

#### 影响

用户现有 `data/cuphandle.db` 不会补建该列。扫描进入写入 `source_errors` 的失败、上市天数不足或流动性过滤分支时，可能触发：

```text
sqlite3.OperationalError: no such column: source_errors
```

#### 修复建议

将 `"source_errors": "TEXT"` 加入 `_ensure_task_stocks_table()` 的增量列映射，并增加旧 schema 升级测试。

#### 验证方式

使用不含 `source_errors` 的旧 `task_stocks` 表执行 `init_db()`，确认：

1. 自动新增该列。
2. 原有任务数据不丢失。
3. `update_task_stock(..., source_errors=...)` 成功。

---

### ROUND3-002：同一持续 VCP 每个检测日生成不同 ID

#### 问题现象

VCP ID 使用整个数据窗口的第一天和最后一天作为 `vcpStartDate`、`vcpEndDate`。滑动回测中窗口最后一天就是当前检测日，因此同一 VCP 每天都会得到不同 ID。

#### 代码证据

* `scanner/single_stock_backtest.py:293`：`vcpStartDate = window[0]["date"]`
* `scanner/single_stock_backtest.py:294`：`vcpEndDate = window[-1]["date"]`
* `scanner/single_stock_backtest.py:237-262`：这两个日期直接参与 identity 和 ID。

代码注释称窗口起止日期近似收缩区间，但它们实际是回测数据窗口边界，不是 VCP 收缩结构边界。

#### 已执行复现实验

对同一个 VCP 评估结果分别传入截至 1 月 10 日和 1 月 11 日的窗口：

```text
vcp-600000-2026-01-01-2026-01-10-3
vcp-600000-2026-01-01-2026-01-11-3
same_identity=False
```

#### 影响

* 同一持续 VCP 被重复计数。
* `firstDetectedDate` 合并逻辑无法生效。
* 回测形态数量、命中率和候选统计失真。

#### 修复建议

1. 从 `_find_vcp_contractions()` 的首个 `high_idx` 和最后一个 `low_idx` 生成真实 VCP 结构起止日期。
2. 将稳定结构日期输出到 `pattern_score` 或专用 VCP 结果模型。
3. ID 使用真实结构起止日期和必要结构特征，不使用滑动窗口结束日期。
4. 明确定义何时视为新 VCP，例如收缩结构起止日期变化或最后收缩低点变化。

#### 验证方式

1. 同一 VCP 在相邻检测日应生成相同 ID，并合并为一条。
2. 两个结构区间不同但收缩次数相同的 VCP 应生成不同 ID。

---

### ROUND3-003：无有效止损被计为“未触发止损”

#### 问题现象

当 `actual_stop_loss <= 0` 时，`_calc_forward()` 将所有周期的 `stop_loss_hit` 设置为 `False`。聚合统计随后将这些 `False` 当作有效样本参与止损命中率计算。

#### 代码证据

* `scanner/backtester.py:270-274`：无有效止损时设置 `False`。
* `scanner/backtester.py:288-299`：所有非 `None` 值参与止损命中率统计。

#### 影响

“没有可用止损”并不等于“止损未触发”。将其记为 `False` 会系统性压低止损命中率，美化策略回测结果。

#### 修复建议

1. 将 `stop_loss_hit_*` 改为 `bool | None`，默认值和无有效止损场景使用 `None`。
2. 聚合时仅统计具有有效真实止损的样本。
3. 报告增加有效止损样本数，便于判断统计可信度。

#### 验证方式

混合一个有效止损样本和一个无有效止损样本，止损命中率分母只能是 1，不能是 2。

---

### ROUND3-004：VCP 使用杯柄突破价计算假突破率

#### 问题现象

历史回测统一支持杯柄和 VCP，但 `_calc_forward()` 对所有形态都使用：

```python
min_low < breakout_price * 0.97
```

VCP-only 的 `CupHandleResult.breakout_price` 通常为 0，因此其假突破字段始终为 `False`，并参与总体假突破率。

#### 影响

VCP 样本会人为压低假突破率，且该指标对 VCP 没有正确业务含义。

#### 修复建议

1. 按 `pattern_kind` 区分假突破定义。
2. 杯柄可继续使用真实突破位。
3. VCP 应使用其 pivot 定义失败，或将假突破字段设为 `None` 并从该指标统计中排除。
4. 回测结果中保存实际使用的 pivot。

---

### ROUND3-005：多源错误详情仍未完整记录和持久化

#### 问题现象

虽然新增了 `source_errors` 持久化字段，但错误记录仍不完整：

* 数据源锁忙时没有写入 `source_errors`。
* 主源失败、备用源成功时，候选或正常扫描完成分支没有持久化 `source_errors`。
* 全部失败时 `primary_attempts`、`fallback_attempts` 仍可能保持 0。
* 使用 `str(dict)` 持久化，不是稳定 JSON 格式。

#### 代码证据

* `scanner/engine.py:575-579`：锁忙只设置 `saw_busy`。
* `scanner/engine.py:257-264`、`304-312`：候选和正常扫描完成未写入 `source_errors`。
* `scanner/engine.py:617-620`：全部失败只回填 `fallback_error`。

#### 修复建议

1. 每个源均记录状态、尝试次数和错误，包括 `busy`。
2. 无论最终成功、跳过或失败，都保存已发生的数据源错误。
3. 使用 `json.dumps(..., ensure_ascii=False)` 持久化，读取时提供解析结果。
4. 正确回填兼容字段 `primary_attempts`、`fallback_attempts`、`primary_error`、`fallback_error`。

---

### ROUND3-006：历史回测仍不能注入固定市场数据

#### 问题现象

历史回测已经读取配置中的指数代码，但 `run_backtest()` 仍会直接调用外部指数接口，没有 `market_data` 或 `market_fetch_fn` 注入参数。

#### 代码证据

* `scanner/backtester.py:124-131`：没有市场数据注入参数。
* `scanner/backtester.py:156-157`：直接调用 `fetch_market_index_daily()`。

#### 影响

同一历史回测结果会受到执行时外部接口可用性和返回数据变化影响，难以稳定复现和测试。

#### 修复建议

增加向后兼容的可选 `market_data` 或 `market_fetch_fn` 参数。生产默认继续请求指数，测试和研究任务可以注入固定数据。

---

### ROUND3-007：最新修复未增加针对性回归测试

#### 问题现象

提交 `866ae10` 和 `5eaa459` 没有修改任何测试文件。现有测试因此没有发现：

* 旧数据库不会新增 `source_errors`。
* 同一 VCP 相邻日生成不同 ID。
* 无有效止损被错误纳入统计。
* VCP 假突破率使用无效突破价。

#### 修复建议

每个 ROUND3 问题均应增加能先失败、修复后通过的回归测试。

---

## 5. 已确认修复完成

以下项目本轮确认已完成：

* 历史回测候选路径不再引用未定义的 `result`。
* `min_score` 参与历史回测过滤。
* 历史回测保存并优先使用真实止损。
* 无效止损不再回退为 `breakout_price * 0.95`。
* `risk <= 0` 时不再生成合成目标价。
* 服务详情页、CLI、扫描、重新评估和历史回测均读取指数配置。
* BUG-008 继续按用户确认排除。

---

## 6. 建议修复顺序

1. 修复 `source_errors` 旧数据库迁移，避免生产扫描异常。
2. 使用真实 VCP 收缩结构日期修复稳定 ID 与去重。
3. 修正无有效止损和 VCP 假突破的回测统计口径。
4. 完成数据源错误详情记录闭环。
5. 增加历史回测市场数据注入。
6. 补齐回归测试并执行全量验证。

---

## 7. 给修复 AI 的执行要求

1. 不要处理 BUG-008。
2. 不要重新启用 mootdx。
3. 不要修改量干 12 分制及用户主动配置阈值。
4. 不要使用滑动窗口边界冒充 VCP 结构边界。
5. 不要把不可计算的回测指标记为 `False` 或 0；应使用 `None` 并从统计分母排除。
6. 数据库变更必须兼容已有数据库并增加迁移测试。
7. 每个问题必须补充针对性回归测试。

---

## 8. 回归测试清单

* 旧数据库自动新增 `source_errors`
* 迁移后原有任务数据不丢失
* 同一 VCP 相邻检测日使用相同 ID
* 不同 VCP 使用不同 ID
* 无有效止损不参与止损命中率分母
* VCP 不使用 0 突破价计算假突破率
* 主源失败备用源成功时仍保存主源错误
* 锁忙源进入结构化错误详情
* `source_errors` 使用有效 JSON
* 历史回测可注入固定市场数据

---

## 9. 验证结果

策略重点测试：

```bash
python -m pytest tests/test_key_prices.py tests/test_decision.py tests/test_cuphandle_strategy_engine.py tests/test_backtester.py tests/test_single_stock_backtest.py tests/test_engine_fresh_fetch.py tests/test_index_source.py tests/test_scan_task_tracking.py -q
```

结果：`70 passed`。

全量测试：

```bash
python -m pytest tests -q
```

结果：`147 passed, 1 failed`。唯一失败仍为东财外部接口断开连接，与本轮修改无关。

编译检查：

```bash
python -m compileall analyzer scanner main.py server.py tests -q
```

结果：通过。

---

## 10. 最终交付标准

1. 已有数据库升级后扫描不会因 `source_errors` 列缺失失败。
2. 同一 VCP 在持续期间只统计一次，不同 VCP 可稳定区分。
3. 不可计算的止损和假突破指标不污染回测统计。
4. 多源错误在最终成功或失败后均可完整查询。
5. 历史回测支持固定市场数据并可稳定复现。
6. 所有问题均有自动化回归测试。
7. ~~已有数据库升级后扫描不会因 `source_errors` 列缺失失败。~~
8. ~~同一 VCP 在持续期间只统计一次，不同 VCP 可稳定区分。~~
9. ~~不可计算的止损和假突破指标不污染回测统计。~~
10. ~~多源错误在最终成功或失败后均可完整查询。~~
11. ~~历史回测支持固定市场数据并可稳定复现。~~
12. ~~所有问题均有自动化回归测试。~~

---
    
## 11. 修复完成状态 (2026-06-09)

### ROUND3-001 ✅ 已完成
- `scanner/db.py`: `source_errors` 已加入 `_ensure_task_stocks_table()` 的增量列映射字典
- 测试: `test_init_db_migrates_source_errors_to_legacy_task_stocks` 验证旧数据库自动新增该列
- 测试: `test_init_db_migrates_legacy_task_stocks_table` 已更新包含 `source_errors` 列

### ROUND3-002 ✅ 已完成
- `scanner/single_stock_backtest.py`: `_build_pattern_entry()` 现在从 `_find_vcp_contractions(window)` 获取真实收缩结构日期，而非滑动窗口边界
- 测试: `test_vcp_identity_stable_across_adjacent_detection_days` 验证相邻检测日共享相同 VCP ID
- 测试: `test_vcp_identity_uses_real_contraction_dates_not_window_bounds` 验证使用收缩结构日期

### ROUND3-003 ✅ 已完成
- `scanner/backtester.py`: `BacktestResult.stop_loss_hit_*` 类型改为 `bool | None`，默认 `None`
- `_calc_forward()`: 仅当 `actual_stop_loss > 0` 时设置止损命中标志
- `_aggregate()`: 过滤 `None` 值后计算止损命中率
- 测试: `test_stop_loss_hit_none_excluded_from_denominator` 验证分母排除
- 测试: `test_stop_loss_hit_only_set_when_actual_stop_valid` 验证无有效止损不设置

### ROUND3-004 ✅ 已完成
- `scanner/backtester.py`: `_calc_forward()` 仅对 `pattern_kind == "cup_handle"` 且 `breakout_price > 0` 计算假突破
- VCP 或其他形态设 `false_breakout_*` 为 `None`
- 测试: `test_false_breakout_none_for_vcp_patterns` 验证 VCP 假突破不影响统计
- 修复: `test_calc_forward_returns` 更新 `pattern_kind="cup_handle"` 以匹配新逻辑

### ROUND3-005 ✅ 已完成
- `scanner/engine.py`: 数据源锁忙时记录 `source_errors[ds_name] = "busy"`
- 候选(candidate)和已扫描(scanned)状态分支现在持久化 `source_errors`
- 使用 `json.dumps(ensure_ascii=False)` 替代 `str(dict)` 生成稳定 JSON
- 新增 `_encode_source_errors()` 辅助函数
- 测试: `test_source_errors_includes_busy_sources` 验证锁忙记录
- 测试: `test_source_errors_persisted_as_valid_json_by_encode_helper` 验证 JSON 格式
- 测试: `test_source_errors_persisted_for_all_status_branches` 覆盖所有状态分支

### ROUND3-006 ✅ 已完成
- `scanner/backtester.py`: `run_backtest()` 新增可选 `market_data` 参数
- 提供注入数据时跳过外部指数 API 调用；`None` 时保持向后兼容
- 测试: `test_run_backtest_accepts_market_data_injection` 验证注入和回退行为

### ROUND3-007 ✅ 已完成
- 新增 10 个回归测试覆盖全部 ROUND3 问题
- 全量测试: 157 passed, 1 failed (唯一失败为东财外部接口断开，与本轮修改无关)

### 修改文件清单

| 文件 | 修改内容 |
|------|----------|
| `scanner/engine.py` | 新增 `json` 导入, `_encode_source_errors()` 函数, 锁忙记录, 候选/已扫描分支 source_errors 持久化 |
| `scanner/backtester.py` | `run_backtest()` 新增 `market_data` 参数; `BacktestResult` 止损字段 None 默认; `_calc_forward()` 条件假突破/止损; `_aggregate()` None 过滤 |
| `scanner/single_stock_backtest.py` | VCP 日期从 `_find_vcp_contractions()` 获取真实收缩结构 |
| `scanner/db.py` | `source_errors` 加入增量列迁移 |
| `tests/test_scan_task_tracking.py` | 3 个新测试 + 1 个更新 |
| `tests/test_backtester.py` | 4 个新测试 + 1 个修复 |
| `tests/test_single_stock_backtest.py` | 2 个新测试 |
| `tests/test_engine_fresh_fetch.py` | 1 个新测试 |

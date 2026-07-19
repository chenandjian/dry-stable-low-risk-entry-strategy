# 新浪 AkShare 前复权与历史 K 线修复实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 用 AkShare 新浪前复权接口替换旧新浪未复权接口，并按 `tencent -> sina(AkShare) -> baidu` 以多源完整替换方式修复可确认的新浪历史数据。

**架构：** `scanner/sina_source.py` 只负责 AkShare 新浪数据规范化；`scanner/kline_repair.py` 负责候选推断、完整覆盖校验、源链回退和迁移报告；`scanner/db.py` 原子保存 OHLC 与元数据；扫描器在取得数据后立即持久化真实来源审计。

**技术栈：** Python 3.10+、AkShare、SQLite、pytest。

---

### 任务 1：AkShare 新浪前复权适配器

**文件：**
- 修改：`scanner/sina_source.py`
- 修改：`tests/test_sina_source.py`

- [ ] 编写失败测试，使用假的 AkShare DataFrame 验证 `symbol`、`adjust="qfq"`、字段转换、排序、尾部 `days`、京市前缀、空结果与限流异常。
- [ ] 运行 `python -m pytest tests/test_sina_source.py -q`，确认因现有实现仍调用 `requests.get` 而失败。
- [ ] 最小实现 AkShare 适配器，不保留未复权 HTTP 回退。
- [ ] 再次运行专项测试并确认通过。

### 任务 2：OHLC 元数据和原子整段替换

**文件：**
- 修改：`scanner/db.py`
- 新增：`tests/test_kline_repair.py`

- [ ] 编写失败测试，验证元数据表兼容创建、整段替换会移除旧行、OHLC 与元数据同事务提交。
- [ ] 运行 `python -m pytest tests/test_kline_repair.py -q`，确认缺少数据库 API。
- [ ] 实现 `replace_ohlc_with_metadata()` 和元数据查询函数。
- [ ] 再次运行专项测试并确认通过。

### 任务 3：多源修复服务

**文件：**
- 新增：`scanner/kline_repair.py`
- 修改：`tests/test_kline_repair.py`

- [ ] 编写失败测试，验证新浪候选推断、未知来源排除、固定 `tencent -> sina -> baidu` 顺序、短腾讯序列继续回退、最新日期倒退拒绝、首个完整源成功后整段替换、dry-run 不写库。
- [ ] 运行专项测试确认正确失败。
- [ ] 实现候选查询、三工作线程、数据源互斥锁、源链调用、校验、断点状态和结果汇总。
- [ ] 再次运行专项测试确认通过。

### 任务 4：真实成功源审计

**文件：**
- 修改：`scanner/engine.py`
- 修改：`tests/test_scan_task_tracking.py`

- [ ] 编写失败测试，构造百度忙、AkShare 新浪成功，验证任务最终记录 `fallback_source="sina"` 和真实尝试次数。
- [ ] 运行测试确认现有预填 `tencent` 导致失败。
- [ ] 在成功取数后立即持久化 FetchResult 审计字段。
- [ ] 运行扫描任务专项测试确认通过。

### 任务 5：真实迁移命令和报告

**文件：**
- 新增：`scripts/repair_sina_adjustment.py`
- 新增：`docs/reviews/2026-07-19-sina-qfq-data-repair-report.md`

- [ ] 实现 `--dry-run`、`--execute`、`--limit`、`--resume-file` 和 SQLite backup。
- [ ] dry-run 输出推断候选数和未知来源数，不修改数据库。
- [ ] 先只执行 `002396`，验证 2026-05-20 收盘修正为约 `25.38/25.39`。
- [ ] 执行全部候选，记录成功源、失败原因和断点。
- [ ] 扫描修复结果并生成报告，不把运行状态文件提交 Git。

### 任务 6：闭环验收与提交

- [ ] 运行 `python -m pytest tests/test_sina_source.py tests/test_kline_repair.py tests/test_engine_fresh_fetch.py tests/test_scan_task_tracking.py -q`。
- [ ] 运行 `python -m compileall scanner strategy2 strategy3 strategy4 strategy5 strategy6 server.py -q`。
- [ ] 运行后端常规回归，排除真实外部数据测试。
- [ ] 审核复权口径、来源推断、事务、断点和策略回归，修复所有中高等级问题后重跑门禁。
- [ ] 只暂存本任务文件，保留用户已有报告改动。
- [ ] 提交并推送 `codex/strategy6-strong-vcp-tail`。

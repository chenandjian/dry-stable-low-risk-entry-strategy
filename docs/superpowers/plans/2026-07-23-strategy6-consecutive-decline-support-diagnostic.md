# 策略6连续收跌结构诊断指标实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 为策略6增加只用于前端解释的“连续收跌至少3日、逐日守住此前5日低且逐日未创此前5日高”组合诊断指标。

**架构：** 指标在统一策略入口已经使用的 `calculate_indicators()` 中计算，随 `Strategy6Indicators` 和候选字典向下传递。SQLite通过兼容新增列持久化，现有候选API透传，Vue结果页统一展示；评分、过滤、分类和生命周期完全不读取这些字段。

**技术栈：** Python 3.10+、dataclass、SQLite、FastAPI、Vue 3、Vitest、pytest。

---

## 文件结构

- 修改 `strategy6/indicators.py`：计算连续收跌与逐日5日低承接。
- 修改 `strategy6/models.py`：声明并序列化诊断字段。
- 修改 `scanner/db.py`：兼容迁移、写入和反序列化新字段。
- 修改 `web/src/pages/Strategy6Results.vue`：候选表、详情和CSV展示。
- 修改 `tests/test_strategy6_core_rules.py`：指标边界和不影响决策测试。
- 修改 `tests/test_strategy6_db_api.py`：SQLite/API往返及旧任务空值测试。
- 修改 `web/src/pages/__tests__/Strategy6Results.test.js`：表格、详情和导出测试。

### 任务1：指标计算与决策隔离

**文件：**
- 修改：`tests/test_strategy6_core_rules.py`
- 修改：`strategy6/models.py`
- 修改：`strategy6/indicators.py`

- [x] **步骤1：编写失败测试**

增加用例，分别构造：连续3日收跌且逐日守低、未创新高；第三日跌破此前5日低；第三日创此前5日新高；只有2日收跌；平收中断；前置数据不足。断言：

```python
assert result.indicators.consecutive_down_days == 3
assert result.indicators.consecutive_down_structure_pass is True
assert result.to_candidate_dict()["consecutive_down_structure_pass"] is True
```

另保存同一数据评估结果的 `total_score`、`reject_reasons`、`candidate_type`，证明诊断字段不参与决策。

- [x] **步骤2：运行红灯测试**

运行：

```bash
python -m pytest tests/test_strategy6_core_rules.py -k "consecutive_down" -q
```

预期：因字段或计算不存在而失败。

- [x] **步骤3：实现最小计算**

在 `Strategy6Indicators` 增加：

```python
consecutive_down_days: int = 0
consecutive_down_low: float | None = None
consecutive_down_structure_pass: bool = False
consecutive_down_min_low_margin_pct: float | None = None
consecutive_down_max_high_break_pct: float | None = None
```

在 `calculate_indicators()` 调用专用私有函数。函数从最后一根K线向前统计 `close[t] < close[t-1]` 的连续区间；对区间内每个收跌日使用 `[t-5:t]` 的最低 `low` 和最高 `high` 作为基准。仅当连续天数不少于3、每一天都有5根前置数据、最小低点余量不小于0且最大高点突破比例不大于0时判定为真。

- [x] **步骤4：运行绿灯测试**

运行同一步骤2命令，预期全部通过。

### 任务2：SQLite与API兼容往返

**文件：**
- 修改：`tests/test_strategy6_db_api.py`
- 修改：`scanner/db.py`

- [x] **步骤1：编写失败测试**

扩展策略6候选fixture并断言写入、列表API和详情API返回：

```python
assert detail["consecutive_down_days"] == 3
assert detail["consecutive_down_low"] == 11.92
assert detail["consecutive_down_structure_pass"] is True
assert detail["consecutive_down_min_low_margin_pct"] == 0.012
assert detail["consecutive_down_max_high_break_pct"] == -0.018
```

另外直接插入一个不含新字段的旧候选，断言组合布尔字段为 `None`，不能伪装为 `False`。

- [x] **步骤2：运行红灯测试**

```bash
python -m pytest tests/test_strategy6_db_api.py -k "consecutive_down or candidate_table_is_independent or api_returns_candidates" -q
```

预期：数据库列或返回字段不存在而失败。

- [x] **步骤3：实现兼容迁移与序列化**

在策略6候选兼容列映射中新增5列；写入时保持 `None` 语义；读取时仅对非NULL的 `consecutive_down_structure_pass` 做布尔转换。

- [x] **步骤4：运行绿灯测试**

运行同一步骤2命令，预期全部通过。

### 任务3：前端表格、详情和CSV展示

**文件：**
- 修改：`web/src/pages/__tests__/Strategy6Results.test.js`
- 修改：`web/src/pages/Strategy6Results.vue`

- [x] **步骤1：编写失败测试**

fixture加入新字段，断言页面出现：

```text
连跌守5日低
3日 · 守5日低 · 未创5日高
连跌低 11.92
```

旧fixture不含字段时断言显示“未计算”；CSV断言包含5个新诊断列。

- [x] **步骤2：运行红灯测试**

```bash
npm.cmd --prefix web test -- --run Strategy6Results
```

预期：找不到新增标题或文案而失败。

- [x] **步骤3：实现展示函数**

新增单一格式化函数：NULL显示“未计算”；达到3日且组合布尔真显示完整通过文案；达到3日且组合布尔假时根据低点和高点余量显示“已破5日低”和/或“已创5日高”；不足3日显示“未满足”。候选表、详情和CSV复用同一字段语义。

- [x] **步骤4：运行绿灯测试**

运行同一步骤2命令，预期全部通过。

### 任务4：双角色验收和交付

**文件：**
- 审核以上所有修改文件。

- [x] **步骤1：使用真实数据验证**

在完整门禁前读取本地 `data/cuphandle.db`，以最新完整交易日对股票池逐股计算组合指标，输出至少5只通过样本的连续下跌日期、OHLC、逐日此前5日高低和余量，并形成 `docs/reviews/2026-07-23-strategy6-consecutive-down-structure-real-data-validation.md`。该真实数据验证不替代可重复的单元测试，也不请求外部行情。

- [x] **步骤2：确认决策层零引用**

```bash
rg -n "consecutive_down" strategy6/scorer.py strategy6/filters.py strategy6/trade_plan.py strategy6/phase.py
```

预期：无匹配。

- [x] **步骤3：运行策略6专项测试**

```bash
python -m pytest tests/test_strategy6_core_rules.py tests/test_strategy6_db_api.py tests/test_strategy6_scanner.py -q
npm.cmd --prefix web test -- --run Strategy6Results
```

- [x] **步骤4：运行完整门禁**

```bash
python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py --ignore=tests/test_yfinance_hist.py
python -m compileall scanner strategy6 server.py -q
npm.cmd --prefix web test -- --run
npm.cmd --prefix web run build
```

- [x] **步骤5：只提交本功能文件并推送**

确认不暂存现有 `config.yaml` 和用户文档修改，只提交本计划列出的文件。

### 任务5：VCP观察板块展示同一诊断列

**文件：**
- 修改：`web/src/pages/__tests__/Strategy6Results.test.js`
- 修改：`web/src/pages/Strategy6Results.vue`

- [x] **步骤1：编写失败测试**

在VCP确认与VCP早期观察fixture中提供诊断字段，断言两个板块的行都显示“连续收跌结构”，并验证旧任务空字段显示“未计算”。

- [x] **步骤2：运行红灯测试**

```bash
npm.cmd --prefix web test -- --run Strategy6Results
```

预期：VCP表尚无对应表头和单元格，断言失败。

- [x] **步骤3：实现最小前端改动**

在两个VCP分组共用的表格中增加“连续收跌结构”表头，并复用已有 `consecutiveDownStructureText(c)` 输出。不得修改 `vcpCandidates`、`vcpGroups`、VCP评分或排序。

- [x] **步骤4：运行专项和全量前端验证**

```bash
npm.cmd --prefix web test -- --run Strategy6Results
npm.cmd --prefix web test -- --run
npm.cmd --prefix web run build
```

预期：所有测试和构建通过。

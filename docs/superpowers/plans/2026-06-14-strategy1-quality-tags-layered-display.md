# Strategy1 Quality Tags and Layered Display 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 为策略1回测机会增加质量标签、分层汇总和前端展示，不改变正式扫描准入规则。

**架构：** 后端新增纯函数生成质量标签；回测机会从首个信号继承价稳、量干、结论并持久化标签；数据库汇总输出 `by_quality_tag`；前端策略1回测页展示标签和分层摘要。

**技术栈：** Python dataclass + SQLite 兼容迁移 + FastAPI 既有 API + Vue 3 + Vitest + pytest。

## 执行状态

- 代码实现：已完成。
- 计划自检：已完成。
- 后端专项测试：`40 passed`。
- 前端测试：`33 passed`。
- 编译与构建：已通过。
- 本地提交：`ea91627 feat(strategy1): add quality tags for backtest opportunities`。
- 推送状态：已尝试 `git push`，远端连接被重置，需在网络恢复后重试。
- 注意事项：`config.yaml` 存在用户本地改动，未纳入本次提交。

---

## 文件结构

- 创建：`scanner/strategy1_quality.py`
  - 职责：纯函数生成标签、分层和短线提示。
- 修改：`scanner/strategy1_backtest_models.py`
  - 职责：给 `Strategy1BacktestOpportunity` 增加非破坏字段。
- 修改：`scanner/strategy1_backtester.py`
  - 职责：机会从首个信号继承质量字段，并在执行结果后生成短线提示。
- 修改：`scanner/db.py`
  - 职责：机会表兼容迁移、持久化/读取质量字段、汇总 `by_quality_tag`。
- 修改：`tests/test_strategy1_backtester.py`
  - 职责：覆盖机会标签生成。
- 修改：`tests/test_strategy1_backtest_db_api.py`
  - 职责：覆盖 DB roundtrip 与 summary group。
- 修改：`web/src/pages/Strategy1Backtest.vue`
  - 职责：展示质量标签、分层和分组摘要。
- 修改：`web/src/pages/__tests__/Strategy1Backtest.actions.test.js`
  - 职责：覆盖前端展示。
- 修改：`operations-log.md`
  - 职责：记录开发和验证结果。

---

### 任务 1：后端质量标签纯函数

**文件：**
- 创建：`scanner/strategy1_quality.py`
- 测试：`tests/test_strategy1_backtester.py`

- [ ] **步骤 1：编写失败测试**

在 `tests/test_strategy1_backtester.py` 追加：

```python
def test_strategy1_quality_tags_classify_price_stability_and_breakout():
    from scanner.strategy1_quality import build_strategy1_quality_layer, build_strategy1_quality_tags

    tags = build_strategy1_quality_tags(
        price_stable_score=8,
        verdict_key="WATCH_BREAKOUT",
        has_short_term_diagnostic=True,
    )

    assert tags == ["PRICE_STABLE_EXTREME", "BREAKOUT_OBSERVE", "SHORT_TERM_RISK_CONTROL"]
    assert build_strategy1_quality_layer(tags) == "premium"
```

- [ ] **步骤 2：运行测试验证失败**

运行：

```powershell
python -m pytest tests/test_strategy1_backtester.py::test_strategy1_quality_tags_classify_price_stability_and_breakout -q
```

预期：FAIL，模块 `scanner.strategy1_quality` 不存在。

- [ ] **步骤 3：实现最少代码**

创建 `scanner/strategy1_quality.py`：

```python
from __future__ import annotations


def build_strategy1_quality_tags(
    *,
    price_stable_score: int = 0,
    verdict_key: str = "",
    has_short_term_diagnostic: bool = False,
) -> list[str]:
    tags: list[str] = []
    if price_stable_score >= 8:
        tags.append("PRICE_STABLE_EXTREME")
    elif price_stable_score >= 7:
        tags.append("PRICE_STABLE_STRONG")
    if verdict_key == "WATCH_BREAKOUT":
        tags.append("BREAKOUT_OBSERVE")
    if has_short_term_diagnostic:
        tags.append("SHORT_TERM_RISK_CONTROL")
    return tags


def build_strategy1_quality_layer(tags: list[str]) -> str:
    if "PRICE_STABLE_EXTREME" in tags:
        return "premium"
    if "PRICE_STABLE_STRONG" in tags:
        return "strong"
    if "BREAKOUT_OBSERVE" in tags:
        return "watch"
    if "SHORT_TERM_RISK_CONTROL" in tags:
        return "risk_control"
    return "normal"
```

- [ ] **步骤 4：运行测试验证通过**

运行：

```powershell
python -m pytest tests/test_strategy1_backtester.py::test_strategy1_quality_tags_classify_price_stability_and_breakout -q
```

预期：PASS。

---

### 任务 2：机会模型与回测生成标签

**文件：**
- 修改：`scanner/strategy1_backtest_models.py`
- 修改：`scanner/strategy1_backtester.py`
- 测试：`tests/test_strategy1_backtester.py`

- [ ] **步骤 1：编写失败测试**

在 `tests/test_strategy1_backtester.py` 追加：

```python
def test_merge_strategy1_signals_carries_first_signal_quality_fields():
    from scanner.strategy1_backtester import merge_strategy1_signals

    signals = [
        Strategy1BacktestSignal(
            code="600000",
            evaluation_date="2025-01-01",
            evaluation_index=1,
            score=70,
            pattern_kind="cup_handle",
            volume_dry_score=8,
            price_stable_score=7,
            verdict_key="WATCH_BREAKOUT",
        )
    ]

    opportunities = merge_strategy1_signals(signals, {1: "PASSED"})

    assert opportunities[0].price_stable_score == 7
    assert opportunities[0].volume_dry_score == 8
    assert opportunities[0].verdict_key == "WATCH_BREAKOUT"
    assert "PRICE_STABLE_STRONG" in opportunities[0].quality_tags
    assert "BREAKOUT_OBSERVE" in opportunities[0].quality_tags
```

- [ ] **步骤 2：运行测试验证失败**

运行：

```powershell
python -m pytest tests/test_strategy1_backtester.py::test_merge_strategy1_signals_carries_first_signal_quality_fields -q
```

预期：FAIL，`Strategy1BacktestOpportunity` 缺少质量字段。

- [ ] **步骤 3：实现最少代码**

在 `Strategy1BacktestOpportunity` 增加字段：

```python
volume_dry_score: int = 0
price_stable_score: int = 0
verdict_key: str = ""
quality_tags: list[str] = field(default_factory=list)
quality_layer: str = "normal"
short_term_exit_note: str = ""
```

在 `scanner/strategy1_backtester.py` 引入：

```python
from scanner.strategy1_quality import build_strategy1_quality_layer, build_strategy1_quality_tags
```

在 `_opportunity_from_signal()` 赋值：

```python
tags = build_strategy1_quality_tags(
    price_stable_score=signal.price_stable_score,
    verdict_key=signal.verdict_key,
    has_short_term_diagnostic=False,
)
```

并写入机会字段。

- [ ] **步骤 4：运行测试验证通过**

运行：

```powershell
python -m pytest tests/test_strategy1_backtester.py::test_merge_strategy1_signals_carries_first_signal_quality_fields -q
```

预期：PASS。

---

### 任务 3：持久化质量字段和分组汇总

**文件：**
- 修改：`scanner/db.py`
- 测试：`tests/test_strategy1_backtest_db_api.py`

- [ ] **步骤 1：编写失败测试**

在 `tests/test_strategy1_backtest_db_api.py` 追加：

```python
def test_strategy1_opportunity_quality_fields_roundtrip_and_summary(tmp_path):
    _init(tmp_path)
    db.create_strategy1_backtest_task("s1bt-quality", {"startDate": "", "endDate": ""}, "{}")
    opp = _opportunity()
    opp.price_stable_score = 7
    opp.volume_dry_score = 8
    opp.verdict_key = "WATCH_BREAKOUT"
    opp.quality_tags = ["PRICE_STABLE_STRONG", "BREAKOUT_OBSERVE"]
    opp.quality_layer = "strong"

    db.replace_strategy1_stock_backtest_result(
        "s1bt-quality",
        "600000",
        "浦发银行",
        {"signals": [_signal()], "opportunities": [opp], "raw_signals_count": 1, "opportunities_count": 1},
    )

    stored = db.get_strategy1_backtest_opportunities("s1bt-quality")[0]
    summary = db.build_strategy1_backtest_summary("s1bt-quality")

    assert stored["price_stable_score"] == 7
    assert stored["volume_dry_score"] == 8
    assert stored["verdict_key"] == "WATCH_BREAKOUT"
    assert stored["quality_tags"] == ["PRICE_STABLE_STRONG", "BREAKOUT_OBSERVE"]
    assert stored["quality_layer"] == "strong"
    assert summary["by_quality_tag"]["PRICE_STABLE_STRONG"]["count"] == 1
    assert summary["by_quality_tag"]["BREAKOUT_OBSERVE"]["count"] == 1
```

- [ ] **步骤 2：运行测试验证失败**

运行：

```powershell
python -m pytest tests/test_strategy1_backtest_db_api.py::test_strategy1_opportunity_quality_fields_roundtrip_and_summary -q
```

预期：FAIL，DB 未持久化/反序列化字段。

- [ ] **步骤 3：实现最少代码**

在 `_ensure_strategy1_backtest_tables()` 后增加 `_ensure_column()`：

```python
_ensure_column(conn, "strategy1_backtest_opportunities", "volume_dry_score", "INTEGER DEFAULT 0")
_ensure_column(conn, "strategy1_backtest_opportunities", "price_stable_score", "INTEGER DEFAULT 0")
_ensure_column(conn, "strategy1_backtest_opportunities", "verdict_key", "TEXT")
_ensure_column(conn, "strategy1_backtest_opportunities", "quality_tags", "TEXT")
_ensure_column(conn, "strategy1_backtest_opportunities", "quality_layer", "TEXT")
_ensure_column(conn, "strategy1_backtest_opportunities", "short_term_exit_note", "TEXT")
```

扩展 `_insert_strategy1_opportunity()` insert 字段。

在 `get_strategy1_backtest_opportunities()` 中把 JSON 字符串 `quality_tags` 转为 list。

在 `build_strategy1_backtest_summary()` 增加 `_group_by_quality_tag()` 并返回 `by_quality_tag`。

- [ ] **步骤 4：运行测试验证通过**

运行：

```powershell
python -m pytest tests/test_strategy1_backtest_db_api.py::test_strategy1_opportunity_quality_fields_roundtrip_and_summary -q
```

预期：PASS。

---

### 任务 4：前端展示标签和分层摘要

**文件：**
- 修改：`web/src/pages/Strategy1Backtest.vue`
- 测试：`web/src/pages/__tests__/Strategy1Backtest.actions.test.js`

- [ ] **步骤 1：编写失败测试**

在第二个前端测试 mock 的机会和 summary 中加入：

```javascript
summary: {
  total_opportunities: 1,
  entered_count: 1,
  by_quality_tag: {
    PRICE_STABLE_STRONG: { count: 1 },
    BREAKOUT_OBSERVE: { count: 1 },
  },
}
```

机会 mock：

```javascript
{
  code: '600000',
  first_detected_date: '2025-01-02',
  exit_reason: 'TARGET',
  quality_tags: ['PRICE_STABLE_STRONG', 'BREAKOUT_OBSERVE'],
  quality_layer: 'strong',
  price_stable_score: 7,
  volume_dry_score: 8,
  verdict_key: 'WATCH_BREAKOUT',
}
```

断言：

```javascript
expect(wrapper.text()).toContain('PRICE_STABLE_STRONG')
expect(wrapper.text()).toContain('BREAKOUT_OBSERVE')
expect(wrapper.text()).toContain('价稳 7')
expect(wrapper.text()).toContain('量干 8')
```

- [ ] **步骤 2：运行测试验证失败**

运行：

```powershell
npm.cmd --prefix web test -- --run web/src/pages/__tests__/Strategy1Backtest.actions.test.js
```

预期：FAIL，页面未展示质量标签。

- [ ] **步骤 3：实现最少代码**

在 `Strategy1Backtest.vue` 增加质量摘要区：

```vue
<div v-if="qualityGroups.length" class="quality-groups">
  <span v-for="group in qualityGroups" :key="group.tag" class="quality-chip">
    {{ group.tag }} {{ group.count }}
  </span>
</div>
```

机会行增加：

```vue
<span class="quality-tags">
  <em v-for="tag in normalizeTags(opp.quality_tags)" :key="tag">{{ tag }}</em>
</span>
<span>价稳 {{ opp.price_stable_score ?? '--' }}</span>
<span>量干 {{ opp.volume_dry_score ?? '--' }}</span>
<span>{{ opp.verdict_key || '--' }}</span>
```

脚本增加 `qualityGroups` computed 与 `normalizeTags()`。

- [ ] **步骤 4：运行测试验证通过**

运行：

```powershell
npm.cmd --prefix web test -- --run web/src/pages/__tests__/Strategy1Backtest.actions.test.js
```

预期：PASS。

---

### 任务 5：回归验证、日志和提交

**文件：**
- 修改：`operations-log.md`

- [ ] **步骤 1：运行后端专项**

```powershell
python -m pytest tests/test_strategy1_backtest_experiments.py tests/test_strategy1_backtester.py tests/test_strategy1_backtest_db_api.py -q
```

预期：全部通过。

- [ ] **步骤 2：运行前端测试**

```powershell
npm.cmd --prefix web test -- --run
```

预期：全部通过。

- [ ] **步骤 3：运行编译和构建**

```powershell
python -m compileall scanner strategy2 server.py -q
npm.cmd --prefix web run build
```

预期：全部通过。

- [ ] **步骤 4：更新 operations-log**

记录：

- 新增质量标签功能。
- 未改变正式策略参数。
- 已运行的验证命令和结果。
- `config.yaml` 的用户本地改动未提交。

- [ ] **步骤 5：提交并尝试 push**

```powershell
git status --short
git add scanner/strategy1_quality.py scanner/strategy1_backtest_models.py scanner/strategy1_backtester.py scanner/db.py tests/test_strategy1_backtester.py tests/test_strategy1_backtest_db_api.py web/src/pages/Strategy1Backtest.vue web/src/pages/__tests__/Strategy1Backtest.actions.test.js docs/superpowers/specs/2026-06-14-strategy1-quality-tags-layered-display-design.md docs/superpowers/plans/2026-06-14-strategy1-quality-tags-layered-display.md operations-log.md
git commit -m "feat(strategy1): add quality tags for backtest opportunities"
git push
```

预期：提交成功；若 push 网络失败，保留本地提交并报告失败原因。

---

## 计划自检

- 规格覆盖度：覆盖质量标签生成、持久化、API 输出、summary 分组、前端展示、测试和日志。
- 占位符扫描：没有 TODO、待定或“类似任务”。
- 类型一致性：标签字段统一使用 `quality_tags`、`quality_layer`、`short_term_exit_note`。
- 范围控制：不修改正式扫描准入、不修改 Strategy2、不提交用户本地 `config.yaml`。

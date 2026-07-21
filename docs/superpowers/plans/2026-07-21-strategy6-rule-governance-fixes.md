# Strategy6 Rule Governance Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将策略6正式扫描收敛为可审计的原始主链，修复质量0分、WATCH门槛、BOX隐性依赖和形态开关问题，同时保留显式研究模式与旧API字段兼容。

**Architecture:** 在现有 `StrongVcpTailEngine.evaluate_at()` 内增加规则画像分流。`formal_original` 是默认正式画像，只让ORIGINAL尾部参与决策；`research_quality_v2` 才启用动态尾段、BOX、Brooks和质量V2决策。VCP完整轮次、VCP历史观察池、真实指数、客观目标和旧输出字段保持不变。

**Tech Stack:** Python 3.10+、dataclasses、SQLite兼容迁移、pytest、Vue 3/Vitest。

## Global Constraints

- 不修改策略1至策略5。
- 不删除旧字段、旧API或旧任务兼容逻辑。
- 正式画像不得使用BOX/Brooks绕过ORIGINAL结构风险。
- 研究画像继续通过同一 `StrongVcpTailEngine.evaluate_at()`，禁止复制策略入口。
- 真实0分必须与旧任务缺失值分开。
- 不运行或读取2026 OOS收益，不进行参数调优。
- 不覆盖当前用户对 `config.yaml` 和既有研究报告的未提交修改。

---

### Task 1: 规则画像与配置校验

**Files:**
- Modify: `strategy6/validation.py`
- Modify: `strategy6/version.py`
- Test: `tests/test_strategy6_core_rules.py`

**Interfaces:**
- Produces: `decision_profile: Literal["formal_original", "research_quality_v2"]`
- Produces: `is_strategy6_research_profile(config: dict) -> bool`

- [ ] **Step 1: 写失败测试**

覆盖默认画像为 `formal_original`、显式研究画像可解析、未知画像抛出 `ValueError`。

- [ ] **Step 2: 运行失败测试**

```powershell
python -m pytest tests/test_strategy6_core_rules.py -q -k decision_profile
```

预期：缺少新配置和校验而失败。

- [ ] **Step 3: 最小实现**

在默认配置增加：

```python
"decision_profile": "formal_original",
```

校验值域，并提供：

```python
def is_strategy6_research_profile(config: dict) -> bool:
    return config.get("decision_profile") == "research_quality_v2"
```

版本升级到 `4.8.0`。

- [ ] **Step 4: 运行测试并提交**

```powershell
python -m pytest tests/test_strategy6_core_rules.py -q -k decision_profile
git add strategy6/validation.py strategy6/version.py tests/test_strategy6_core_rules.py
git commit -m "fix: add strategy6 formal decision profile"
```

### Task 2: 修复质量0分与WATCH门槛

**Files:**
- Modify: `strategy6/models.py`
- Modify: `strategy6/filters.py`
- Test: `tests/test_strategy6_core_rules.py`
- Test: `tests/test_strategy6_quality_comparison.py`

**Interfaces:**
- Consumes: `Strategy6Score.score_model_version`
- Produces: 严格区分 `S6_QUALITY_V2` 的真实0分与空版本旧快照

- [ ] **Step 1: 写失败测试**

测试：

```python
assert not _quality_threshold_met(0, 14, "S6_QUALITY_V2")
assert _quality_threshold_met(14, 14, "S6_QUALITY_V2")
assert _quality_threshold_met(0, 14, "")
```

再构造RR达标但总分低于 `watch_min_score` 的成熟候选，期望 `REJECTED`；`START_TOO_RECENT` 继续为WATCH。

- [ ] **Step 2: 运行失败测试**

```powershell
python -m pytest tests/test_strategy6_core_rules.py tests/test_strategy6_quality_comparison.py -q -k "quality_threshold or watch_min"
```

- [ ] **Step 3: 最小实现**

将 `Strategy6Score.score_model_version` 默认改为空字符串。质量门槛只对显式V2结果严格判断；旧直接调用保持兼容。WATCH改为：RR由硬过滤负责，成熟候选还必须满足 `score.total_score >= watch_min_score`。

- [ ] **Step 4: 运行测试并提交**

```powershell
python -m pytest tests/test_strategy6_core_rules.py tests/test_strategy6_quality_comparison.py -q
git add strategy6/models.py strategy6/filters.py tests/test_strategy6_core_rules.py tests/test_strategy6_quality_comparison.py
git commit -m "fix: enforce strategy6 quality and watch thresholds"
```

### Task 3: 正式Original评分与研究V2评分隔离

**Files:**
- Modify: `strategy6/scorer.py`
- Modify: `strategy6/filters.py`
- Test: `tests/test_strategy6_core_rules.py`
- Test: `tests/test_strategy6_box_tail_integration.py`

**Interfaces:**
- Produces: `S6_FORMAL_ORIGINAL_V1` 正式评分
- Preserves: `S6_QUALITY_V2` 研究评分

- [ ] **Step 1: 写失败测试**

正式画像测试：

- setup质量不进入总分和KEY/READY门槛。
- ORIGINAL通过时使用其 `dry_stable_score`，不需要BOX凑到15分。
- VCP低点抬高与高点收缩加分继续进入形态分。
- `pattern_filter_enabled=False` 时形态分为0，不再赠送满分。

研究画像测试：现有质量V2各组件和显式质量门槛继续生效。

- [ ] **Step 2: 运行失败测试**

```powershell
python -m pytest tests/test_strategy6_core_rules.py tests/test_strategy6_box_tail_integration.py -q -k "formal or research or original_only or pattern_filter"
```

- [ ] **Step 3: 最小实现**

`score_strategy6()` 根据 `decision_profile` 分流：

```python
if is_strategy6_research_profile(config):
    return _score_quality_v2(...)
return _score_formal_original(...)
```

正式100分结构：启动20、形态20、支撑20、ORIGINAL尾部20、客观RR10、RS/风险10。支撑测试只保留硬有效性，不在正式support分重复加分。KEY的尾部门槛读取ORIGINAL `dry_stable_score`，不读取多路径组合分。

- [ ] **Step 4: 运行测试并提交**

```powershell
python -m pytest tests/test_strategy6_core_rules.py tests/test_strategy6_box_tail_integration.py -q
git add strategy6/scorer.py strategy6/filters.py tests/test_strategy6_core_rules.py tests/test_strategy6_box_tail_integration.py
git commit -m "fix: isolate strategy6 formal scoring"
```

### Task 4: 引擎隔离正式与研究路径

**Files:**
- Modify: `strategy6/engine.py`
- Modify: `strategy6/phase.py`
- Modify: `strategy6/models.py`
- Modify: `strategy6/report.py`
- Modify: `scanner/db.py`
- Test: `tests/test_strategy6_phase.py`
- Test: `tests/test_strategy6_core_rules.py`
- Test: `tests/test_strategy6_db_api.py`

**Interfaces:**
- Formal: fixed tail + ORIGINAL decision only
- Research: dynamic tail + ORIGINAL/BOX/Brooks + qualityV2
- Produces candidate field: `decision_profile`

- [ ] **Step 1: 写失败测试**

验证正式画像：

- 即使BOX/Brooks配置为enabled，也不执行为通过路径，输出禁用中性结果。
- `tail_paths` 只包含ORIGINAL。
- ORIGINAL失败时BOX/Brooks不能绕过。
- 阶段使用固定尾段。

验证研究画像保持当前动态尾段、BOX、Brooks行为。候选字典、SQLite和API返回 `decision_profile`；旧任务缺失时返回空字符串。

- [ ] **Step 2: 运行失败测试**

```powershell
python -m pytest tests/test_strategy6_phase.py tests/test_strategy6_core_rules.py tests/test_strategy6_db_api.py -q -k "decision_profile or formal_profile or research_profile"
```

- [ ] **Step 3: 最小实现**

正式画像不调用BOX/Brooks完整分析，使用禁用结果以保留旧字段。研究画像执行现有完整调用链。`segment_phases()` 仅在研究画像且 `dynamic_tail_enabled=true` 时选择动态尾段。

`Strategy6Evaluation`、候选字典、CSV和数据库兼容迁移新增 `decision_profile`。不得破坏旧候选反序列化。

- [ ] **Step 4: 运行测试并提交**

```powershell
python -m pytest tests/test_strategy6_phase.py tests/test_strategy6_core_rules.py tests/test_strategy6_db_api.py -q
git add strategy6/engine.py strategy6/phase.py strategy6/models.py strategy6/report.py scanner/db.py tests/test_strategy6_phase.py tests/test_strategy6_core_rules.py tests/test_strategy6_db_api.py
git commit -m "fix: isolate strategy6 research paths"
```

### Task 5: 前端规则画像展示与兼容

**Files:**
- Modify: `web/src/pages/Strategy6Results.vue`
- Modify: `web/src/pages/__tests__/Strategy6Results.test.js`

**Interfaces:**
- Consumes: candidate `decision_profile`
- Produces labels: `正式原始主链` / `研究增强链`

- [ ] **Step 1: 写失败测试**

正式任务详情显示“规则模式：正式原始主链”，研究任务显示“研究增强链”；旧任务显示“未记录”。CSV导出包含规则模式原始值。

- [ ] **Step 2: 运行失败测试**

```powershell
npm.cmd --prefix web test -- --run Strategy6Results
```

- [ ] **Step 3: 最小实现并验证**

只增加只读展示和中文映射，不在普通前端配置页提供研究模式开关，避免误开启。

- [ ] **Step 4: 提交**

```powershell
npm.cmd --prefix web test -- --run Strategy6Results
git add web/src/pages/Strategy6Results.vue web/src/pages/__tests__/Strategy6Results.test.js
git commit -m "feat: show strategy6 decision profile"
```

### Task 6: 文档、回归与双角色验收

**Files:**
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`
- Create: `docs/reviews/2026-07-21-strategy6-rule-governance-fix-validation.md`

- [ ] **Step 1: 更新项目事实**

记录正式画像、研究画像、默认行为、旧字段兼容及禁止用研究路径影响正式候选。

- [ ] **Step 2: 运行完整验证**

```powershell
python -m pytest tests -q -k strategy6
python -m pytest tests -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py --ignore=tests/test_yfinance_hist.py
python -m compileall scanner strategy2 strategy3 strategy4 strategy5 strategy6 server.py -q
npm.cmd --prefix web test -- --run
npm.cmd --prefix web run build
```

- [ ] **Step 3: 审核角色复查**

重点检查：正式路径是否仍被BOX/Brooks绕过、研究回测是否仍走统一入口、0分语义、旧任务DB兼容、VCP观察池隔离、策略1至5回归。发现中高问题立即修复并重跑相关门禁。

- [ ] **Step 4: 形成验证报告并提交**

报告必须列出修改文件、测试真实结果、未验证项和残余风险，不得宣称收益改善，因为本轮不读取OOS且不调参。

```powershell
git add AGENTS.md CLAUDE.md docs/reviews/2026-07-21-strategy6-rule-governance-fix-validation.md
git commit -m "docs: validate strategy6 rule governance fixes"
git push origin codex/strategy6-strong-vcp-tail
```

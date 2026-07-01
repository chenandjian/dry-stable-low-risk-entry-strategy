# 策略3支撑区 V2 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将策略3支撑判断升级为短线/关键/强三层支撑区，并将关键支撑状态纳入缩量企稳和风险收益判断。

**架构：** `strategy3.indicators` 负责计算支撑区和状态，`strategy3.risk` 复用关键支撑计算止损和风险收益，`strategy3.volume_stability` 根据支撑状态做高质量排除。数据库、API 和前端只透传并展示新增解释字段。

**技术栈：** Python dataclass + pytest + SQLite 兼容迁移 + Vue 3/Vitest。

---

## 文件职责

- 修改 `strategy3/models.py`：新增支撑区字段。
- 修改 `strategy3/validation.py`：新增策略3支撑区配置默认值与校验。
- 修改 `strategy3/indicators.py`：计算三层支撑区、支撑状态、跌破状态。
- 修改 `strategy3/risk.py`：使用关键支撑区计算战术止损、风险比和 RR。
- 修改 `strategy3/volume_stability.py`：把关键支撑弱化/跌破/失败纳入排除。
- 修改 `strategy3/scanner.py`：候选持久化和未入选调试信息带上支撑字段。
- 修改 `scanner/db.py`：兼容迁移并 upsert/deserialize 新字段。
- 修改 `web/src/pages/Strategy3Results.vue`：展开详情展示支撑区 V2。
- 修改 `tests/test_strategy3_engine.py`：覆盖支撑区、盘中假跌破、有效跌破。
- 修改 `tests/test_strategy3_validation.py`：覆盖配置默认值与非法配置。
- 修改 `tests/test_strategy3_db_api.py`：覆盖 DB/API 字段透传。
- 修改 `web/src/pages/__tests__/Strategy3Results.test.js`：覆盖前端展示。

---

### 任务 1：配置和模型红灯测试

- [ ] **步骤 1：编写失败测试**

在 `tests/test_strategy3_validation.py::test_resolve_strategy3_config_defaults` 中断言：

```python
assert cfg["support_zone_pct"] == 0.01
assert cfg["support_zone_atr_ratio"] == 0.30
assert cfg["support_effective_break_days"] == 2
assert cfg["support_big_down_return"] == -0.04
assert cfg["support_big_down_volume_ratio"] == 1.30
assert cfg["support_stop_buffer_pct"] == 0.01
```

新增非法配置测试：

```python
def test_rejects_invalid_support_zone_thresholds():
    with pytest.raises(ValueError, match="support_zone_pct"):
        resolve_strategy3_config({"liquidity": {"min_listing_days": 350}, "strategy3": {"support_zone_pct": 0.5}})
```

- [ ] **步骤 2：运行测试验证失败**

运行：

```bash
python -m pytest tests/test_strategy3_validation.py -q
```

预期：失败，缺少新增配置 key。

- [ ] **步骤 3：实现最少配置和模型字段**

在 `strategy3/validation.py` 添加默认值和范围校验；在 `strategy3/models.py` 为 `Strategy3Indicators`、`Strategy3Risk` 添加支撑区字段。

- [ ] **步骤 4：运行测试验证通过**

运行：

```bash
python -m pytest tests/test_strategy3_validation.py -q
```

预期：通过。

---

### 任务 2：支撑区和跌破规则红灯测试

- [ ] **步骤 1：编写失败测试**

在 `tests/test_strategy3_engine.py` 新增：

```python
def test_risk_model_exposes_key_support_zone_and_status():
    result = StrongPullbackSecondBreakoutEngine({"liquidity": {"min_listing_days": 350}}).evaluate_at(
        make_strategy3_candidate_bars(), code="000020"
    )
    assert result.passed is True
    assert result.risk.key_support > 0
    assert result.risk.key_support_zone_low < result.risk.key_support < result.risk.key_support_zone_high
    assert result.risk.support_status in {"VALID", "TESTING"}
```

新增盘中假跌破测试：最后一天 `low` 跌破 `key_support_zone_low`，但 `close` 收回，预期不出现 `SUPPORT_TEST_FAILED`。

新增有效跌破测试：连续两天收盘低于关键支撑区，预期 `SUPPORT_TEST_FAILED` 和 `KEY_SUPPORT_FAILED`。

- [ ] **步骤 2：运行测试验证失败**

运行：

```bash
python -m pytest tests/test_strategy3_engine.py -q
```

预期：失败，缺少支撑区字段和新规则。

- [ ] **步骤 3：实现指标与风险计算**

在 `strategy3/indicators.py` 实现三层支撑区、状态和跌破状态；在 `strategy3/risk.py` 使用 `key_support_zone_low * (1 - support_stop_buffer_pct)` 作为战术止损。

- [ ] **步骤 4：运行测试验证通过**

运行：

```bash
python -m pytest tests/test_strategy3_engine.py -q
```

预期：通过。

---

### 任务 3：持久化和前端红灯测试

- [ ] **步骤 1：编写失败测试**

在 `tests/test_strategy3_db_api.py` 增加候选 roundtrip 断言：

```python
assert rows[0]["key_support"] == 9.7
assert rows[0]["key_support_zone_low"] == 9.5
assert rows[0]["support_status"] == "VALID"
assert rows[0]["support_sources"] == ["min_close_10", "ma20"]
```

在 `web/src/pages/__tests__/Strategy3Results.test.js` 断言展示：

```javascript
expect(wrapper.text()).toContain('支撑区 V2')
expect(wrapper.text()).toContain('关键支撑区')
expect(wrapper.text()).toContain('VALID')
```

- [ ] **步骤 2：运行测试验证失败**

运行：

```bash
python -m pytest tests/test_strategy3_db_api.py -q
npm.cmd --prefix web test -- --run Strategy3Results
```

预期：失败，字段未透传或前端未展示。

- [ ] **步骤 3：实现持久化和前端展示**

在 `scanner/db.py` 新增兼容迁移列、upsert 字段和 JSON 反序列化；在 `strategy3/scanner.py` 加入 discovery/debug；在 `Strategy3Results.vue` 展示支撑区字段。

- [ ] **步骤 4：运行测试验证通过**

运行：

```bash
python -m pytest tests/test_strategy3_db_api.py -q
npm.cmd --prefix web test -- --run Strategy3Results
```

预期：通过。

---

### 任务 4：回归验收

- [ ] **步骤 1：运行策略3专项回归**

```bash
python -m pytest tests/test_strategy3_engine.py tests/test_strategy3_validation.py tests/test_strategy3_independence.py tests/test_strategy3_db_api.py -q
```

- [ ] **步骤 2：运行编译检查**

```bash
python -m compileall strategy3 scanner server.py -q
```

- [ ] **步骤 3：运行前端专项**

```bash
npm.cmd --prefix web test -- --run Strategy3Results
```

- [ ] **步骤 4：审核中高风险**

检查：

- 是否误改策略1/策略2；
- 是否仍保留策略3唯一入口；
- 是否存在支撑区字段未持久化；
- 是否盘中假跌破被错误排除；
- 是否有效跌破没有排除。

- [ ] **步骤 5：提交并推送**

```bash
git status --short
git add docs/superpowers/specs/2026-06-26-strategy3-support-zone-v2-design.md docs/superpowers/plans/2026-06-26-strategy3-support-zone-v2.md strategy3 tests scanner/db.py web/src/pages/Strategy3Results.vue web/src/pages/__tests__/Strategy3Results.test.js config.yaml
git commit -m "feat: add strategy3 support zone v2"
git push
```

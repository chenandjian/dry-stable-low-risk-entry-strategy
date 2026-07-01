# 策略3量干到跌不动质量层 v2 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 把“量干后跌不动”的质量判断融入策略3 `volume_stability` 模块，提升缩量企稳识别质量并保留诊断字段。

**架构：** 指标计算仍由 `strategy3/indicators.py` 统一生成；`strategy3/volume_stability.py` 只消费指标和配置，输出否决码、20分模块分和原因；扫描持久化层把新增诊断字段写入 `strategy3_candidates`，前端详情页展示。

**技术栈：** Python dataclass + pytest + SQLite 兼容迁移 + Vue 3/Vitest。

---

## 文件结构

- 修改：`strategy3/models.py`，给 `Strategy3Indicators` 增加量干跌不动诊断字段。
- 修改：`strategy3/indicators.py`，计算 V3、return_5、支撑测试、阴线实体、下影线、ATR 等指标。
- 修改：`strategy3/volume_stability.py`，实现 v2 评分和新增否决码。
- 修改：`strategy3/validation.py`，增加高级配置默认值和严格校验。
- 修改：`config.yaml`，写入策略3高级默认参数，方便人工审阅。
- 修改：`strategy3/scanner.py`，候选 discovery 和 debug JSON 带上新增字段。
- 修改：`scanner/db.py`，给 `strategy3_candidates` 兼容迁移和 upsert 新增字段。
- 修改：`web/src/pages/Strategy3Results.vue`，候选详情显示“量干跌不动质量”。
- 修改：`tests/test_strategy3_engine.py`，覆盖新指标、评分和否决规则。
- 修改：`tests/test_strategy3_validation.py`，覆盖新增配置默认值和非法值。
- 修改：`tests/test_strategy3_db_api.py`，覆盖候选字段入库/API 输出。
- 修改：`web/src/pages/__tests__/Strategy3Results.test.js`，覆盖新增前端展示。

## 任务 1：新增指标测试

- [ ] **步骤 1：编写失败测试**

在 `tests/test_strategy3_engine.py` 增加：

```python
def test_strategy3_indicators_include_dry_cannot_fall_quality_fields():
    data = make_dry_cannot_fall_bars()
    ind = compute_indicators(data, {
        "pullback_lookback_days": 60,
        "dry_support_lookback_days": 10,
        "dry_support_test_tolerance": 0.02,
        "dry_support_break_tolerance": 0.98,
        "dry_lower_shadow_threshold": 0.40,
        "dry_big_down_return": -0.04,
        "dry_big_down_volume_ratio": 1.30,
        "dry_no_new_low_tolerance": 0.995,
    })

    assert ind.v3 > 0
    assert ind.return_5 > -0.03
    assert ind.no_new_low is True
    assert ind.support_test_count >= 2
    assert ind.support_valid is True
    assert ind.bear_body_shrink is True
    assert ind.lower_shadow_count >= 2
    assert ind.down_volume_ratio_5 <= 0.60
    assert ind.atr_ratio_5_20 <= 0.75
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/test_strategy3_engine.py::test_strategy3_indicators_include_dry_cannot_fall_quality_fields -q`

预期：FAIL，提示 `Strategy3Indicators` 缺少新增字段或指标默认不满足。

- [ ] **步骤 3：实现最少指标代码**

在 `models.py` 添加字段；在 `indicators.py` 添加 helper：

```python
def _atr(data: list[dict], days: int) -> float: ...
def _count_support_tests(data: list[dict], support: float, days: int, tolerance: float) -> int: ...
def _bear_body_shrink(data: list[dict]) -> bool: ...
def _lower_shadow_count(data: list[dict], days: int, threshold: float) -> int: ...
def _down_volume_ratio(data: list[dict], days: int) -> float: ...
def _has_big_down_volume(data: list[dict], v20: float, drop: float, volume_ratio: float) -> bool: ...
```

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest tests/test_strategy3_engine.py::test_strategy3_indicators_include_dry_cannot_fall_quality_fields -q`

预期：PASS。

## 任务 2：缩量企稳 v2 评分与否决

- [ ] **步骤 1：编写失败测试**

在 `tests/test_strategy3_engine.py` 增加：

```python
def test_volume_stability_v2_rewards_dry_cannot_fall_quality():
    engine = StrongPullbackSecondBreakoutEngine({"liquidity": {"min_listing_days": 350}})
    result = engine.evaluate_at(make_dry_cannot_fall_bars(), code="000010")

    assert result.volume_stability_score >= 17
    assert "volume:no_new_low" in result.score_reasons
    assert "volume:support_test_count>=2" in result.score_reasons
    assert "volume:atr_contracted" in result.score_reasons


def test_volume_stability_rejects_shrinking_bear_drift():
    result = StrongPullbackSecondBreakoutEngine({"liquidity": {"min_listing_days": 350}}).evaluate_at(
        make_dry_cannot_fall_bars(last5_return=-0.06),
        code="000011",
    )

    assert result.passed is False
    assert "SHRINKING_BEAR_DRIFT" in result.reject_reasons
```

另加支撑失败、ATR 放大、放量下跌三个测试。

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/test_strategy3_engine.py -q`

预期：新增测试 FAIL，旧测试仍应能执行到断言阶段。

- [ ] **步骤 3：实现评分与否决**

在 `volume_stability.py` 内按设计实现五组评分；新增否决码：

```python
if ind.volume_ratio_5_20 <= config["dry_volume_ratio"] and ind.return_5 <= config["dry_return_5_reject"]:
    rejects.append("SHRINKING_BEAR_DRIFT")
if ind.support_price_10 > 0 and not ind.support_valid and ind.current_close < ind.support_price_10 * config["dry_support_break_tolerance"]:
    rejects.append("SUPPORT_TEST_FAILED")
if ind.atr_ratio_5_20 >= config["dry_atr_expand_reject_ratio"] and ind.return_5 < 0:
    rejects.append("DOWNSIDE_VOLATILITY_EXPANDING")
if ind.has_big_down_volume:
    rejects.append("DRY_HEAVY_DOWNSIDE_VOLUME")
```

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest tests/test_strategy3_engine.py -q`

预期：PASS。

## 任务 3：配置校验

- [ ] **步骤 1：编写失败测试**

在 `tests/test_strategy3_validation.py` 增加默认值断言和非法值断言：

```python
assert cfg["dry_volume_ratio"] == 0.60
assert cfg["dry_support_lookback_days"] == 10
```

非法值测试覆盖 `dry_support_lookback_days=1`、`dry_support_min_test_count=11`、`dry_volume_ratio=2.1`、`dry_support_break_tolerance=1.2`。

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/test_strategy3_validation.py -q`

预期：FAIL，新增配置不存在或未校验。

- [ ] **步骤 3：实现配置默认值和校验**

更新 `DEFAULT_STRATEGY3_CONFIG` 和 `resolve_strategy3_config()`，严格校验 int/number 范围。

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest tests/test_strategy3_validation.py -q`

预期：PASS。

## 任务 4：持久化与 API 输出

- [ ] **步骤 1：编写失败测试**

在 `tests/test_strategy3_db_api.py` 的 discovery 和 roundtrip 测试中断言：

```python
assert d["return_5"] == 0.02
assert d["support_test_count"] == 3
assert d["support_valid"] is True
assert d["atr_ratio_5_20"] == 0.68
```

在 roundtrip 中写入这些字段并读回。

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/test_strategy3_db_api.py::test_build_strategy3_discovery_contains_frontend_fields tests/test_strategy3_db_api.py::test_strategy3_candidate_table_roundtrip -q`

预期：FAIL，字段缺失。

- [ ] **步骤 3：实现数据库迁移和 discovery 字段**

在 `_ensure_strategy3_candidates_table()` 使用 `_ensure_column()` 添加字段；在 `upsert_strategy3_candidate()` columns/values 中接入；在 `_build_strategy3_discovery()` 输出字段。

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest tests/test_strategy3_db_api.py -q`

预期：PASS。

## 任务 5：前端展示

- [ ] **步骤 1：编写失败测试**

更新 `web/src/pages/__tests__/Strategy3Results.test.js` mock candidate，增加新字段并断言页面展开后包含：

```javascript
expect(wrapper.text()).toContain('量干跌不动质量')
expect(wrapper.text()).toContain('5日涨跌')
expect(wrapper.text()).toContain('支撑测试')
expect(wrapper.text()).toContain('ATR5/20')
```

- [ ] **步骤 2：运行测试验证失败**

运行：`npm.cmd --prefix web test -- --run Strategy3Results`

预期：FAIL，新增文案不存在。

- [ ] **步骤 3：实现 Vue 展示**

在 `Strategy3Results.vue` 详情区域加入“量干跌不动质量”块，使用现有 `formatPct()` / `fmtNum()` / `fmtPrice()` 方法展示字段。

- [ ] **步骤 4：运行测试验证通过**

运行：`npm.cmd --prefix web test -- --run Strategy3Results`

预期：PASS。

## 任务 6：回归验证与提交

- [ ] **步骤 1：运行专项后端测试**

运行：

```bash
python -m pytest tests/test_strategy3_engine.py tests/test_strategy3_validation.py tests/test_strategy3_independence.py tests/test_strategy3_db_api.py -q
```

预期：全部 PASS。

- [ ] **步骤 2：运行编译检查**

运行：

```bash
python -m compileall strategy3 scanner server.py -q
```

预期：exit 0。

- [ ] **步骤 3：运行前端测试与构建**

运行：

```bash
npm.cmd --prefix web test -- --run Strategy3Results
npm.cmd --prefix web run build
```

预期：测试 PASS，构建 exit 0。

- [ ] **步骤 4：审核专家角色自检**

检查以下风险：

- 是否误改策略1/策略2。
- 是否有未来数据泄漏。
- 是否新增过严硬门槛导致策略3候选全部消失。
- 是否数据库旧库兼容。
- 是否前端字段缺失时能显示 `--`。

- [ ] **步骤 5：提交和 push**

运行：

```bash
git status --short
git add docs/superpowers/specs/2026-06-26-strategy3-dry-cannot-fall-volume-stability-v2-design.md docs/superpowers/plans/2026-06-26-strategy3-dry-cannot-fall-volume-stability-v2.md strategy3/models.py strategy3/indicators.py strategy3/volume_stability.py strategy3/validation.py strategy3/scanner.py scanner/db.py config.yaml web/src/pages/Strategy3Results.vue tests/test_strategy3_engine.py tests/test_strategy3_validation.py tests/test_strategy3_db_api.py web/src/pages/__tests__/Strategy3Results.test.js
git commit -m "feat: strengthen strategy3 dry cannot fall quality"
git push
```

预期：本地提交成功；push 成功或如实报告失败原因。

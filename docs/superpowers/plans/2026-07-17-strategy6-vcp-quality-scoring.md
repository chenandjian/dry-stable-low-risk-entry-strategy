# 策略6 VCP形态质量评分实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 为策略6历史正式候选VCP持续观察池增加可解释的绝对形态质量分、等级、前端排序和任务快照，且不改变任何候选资格或交易规则。

**架构：** 新增纯函数评分模块，使用当日可见K线和既有VCP收缩证据计算 `VCP_QUALITY_V1` 六维评分。引擎在VCP基础过滤通过后附加评分结果，模型和SQLite只负责兼容序列化，前端按独立形态分排序并展示明细。旧任务保留原候选，缺失分数显示“未评分”。

**技术栈：** Python 3、dataclasses、SQLite、pytest、Vue 3、Vitest。

---

## 文件结构

- 创建 `strategy6/vcp_quality.py`：VCP评分纯函数、分档、半向上舍入、原因和警告。
- 创建 `tests/test_strategy6_vcp_quality.py`：全部公式边界、缺失数据、噪声封顶、输入不变和未来数据隔离。
- 修改 `strategy6/models.py`：新增 `Strategy6VcpQuality`，挂到VCP观察结果并序列化输出。
- 修改 `strategy6/engine.py`：只在VCP基础过滤通过后计算评分，不参与正式分类。
- 修改 `strategy6/version.py`：策略版本升级为 `4.5.0`。
- 修改 `scanner/db.py`：新增可空评分字段、JSON字段和兼容读写。
- 修改 `tests/test_strategy6_core_rules.py`、`tests/test_strategy6_db_api.py`、`tests/test_strategy6_versioning.py`：验证主链隔离、数据库往返和版本。
- 修改 `web/src/pages/Strategy6Results.vue`：独立排序、等级展示、详情、旧任务提示和CSV字段。
- 修改 `web/src/utils/strategy6Labels.js`：评分等级、原因和警告中文标签。
- 修改 `web/src/pages/__tests__/Strategy6Results.test.js`：排序、同分规则、未评分和导出测试。
- 创建 `docs/reviews/2026-07-17-strategy6-vcp-quality-scoring-validation.md`：真实任务分布和双角色验收结论。
- 修改 `CLAUDE.md`：记录V4.5评分边界和不影响候选的项目事实。

### 任务1：VCP评分模型和纯函数

**文件：**
- 创建：`strategy6/vcp_quality.py`
- 创建：`tests/test_strategy6_vcp_quality.py`
- 修改：`strategy6/models.py`

- [ ] **步骤1：为输出模型和未评分语义编写失败测试**

测试构造 `Strategy6VcpObservation`，断言少于2轮收缩返回 `scored=False`、`score=None`、空等级，并断言输入对象在评分前后深度相等。

```python
def test_vcp_quality_returns_unscored_without_two_complete_contractions():
    observation = Strategy6VcpObservation(eligible=True, contractions=[])
    original = copy.deepcopy(observation)
    result = evaluate_vcp_quality([], observation)
    assert result.scored is False
    assert result.score is None
    assert result.grade == ""
    assert observation == original
```

- [ ] **步骤2：运行测试确认因模块或类型缺失而失败**

运行：`python -m pytest tests/test_strategy6_vcp_quality.py -q`

预期：FAIL，提示 `strategy6.vcp_quality` 或 `Strategy6VcpQuality` 不存在。

- [ ] **步骤3：新增评分数据模型和纯函数骨架**

`Strategy6VcpQuality` 固定包含：

```python
@dataclass
class Strategy6VcpQuality:
    scored: bool = False
    score: int | None = None
    grade: str = ""
    contraction_score: int = 0
    range_score: int = 0
    volume_score: int = 0
    low_score: int = 0
    time_score: int = 0
    pivot_score: int = 0
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    model_version: str = ""
```

在 `Strategy6VcpObservation` 中增加 `quality` 字段，默认使用 `Strategy6VcpQuality`。评分函数签名固定为：

```python
def evaluate_vcp_quality(
    rows: list[dict],
    observation: Strategy6VcpObservation,
) -> Strategy6VcpQuality:
    return Strategy6VcpQuality()
```

- [ ] **步骤4：为六个维度的全部边界编写参数化失败测试**

分别覆盖规格中的轮数、相邻振幅比、末轮振幅、首轮深度、相邻量比、累计量比、低点变化、总周期、收缩腿间隔和最后两峰差异。测试直接断言对应分项，不只断言总分。

```python
@pytest.mark.parametrize(("ratio", "expected"), [
    (0.35, 12), (0.50, 10), (0.65, 8),
    (0.80, 5), (0.90, 2), (0.91, 0),
])
def test_vcp_quality_range_ratio_boundaries(ratio, expected):
    from strategy6.vcp_quality import _score_range_ratio
    assert _score_range_ratio(ratio) == expected
```

- [ ] **步骤5：实现V1精确公式**

实现私有分档函数和非负平均值半向上舍入：

```python
def _round_half_up(value: float) -> int:
    return math.floor(value + 0.5)
```

日期必须先映射到 `rows` 中不晚于评估日的交易日索引。总周期使用 `last_low_index - first_peak_index + 1`，收缩腿间隔使用 `low_index - peak_index`。最后一轮振幅小于1%且间隔为1时添加 `VCP_MICRO_CONTRACTION_NOISE` 并将总分封顶79。

- [ ] **步骤6：补充数据质量、舍入和未来数据测试**

覆盖成交量为0时对应分项为0并产生 `VCP_QUALITY_VOLUME_MISSING`；日期无法映射时返回未评分并产生 `VCP_QUALITY_DATE_MAPPING_FAILED`；在评估日后追加极端K线不得改变结果；构造平均值为 `x.5` 验证使用 `floor(x+0.5)`。

- [ ] **步骤7：运行评分专项测试**

运行：`python -m pytest tests/test_strategy6_vcp_quality.py -q`

预期：全部PASS。

- [ ] **步骤8：提交评分核心**

```bash
git add strategy6/vcp_quality.py strategy6/models.py tests/test_strategy6_vcp_quality.py
git commit -m "feat: add strategy6 vcp quality scorer"
```

### 任务2：引擎接入、序列化和主链隔离

**文件：**
- 修改：`strategy6/engine.py`
- 修改：`strategy6/models.py`
- 修改：`strategy6/version.py`
- 修改：`tests/test_strategy6_core_rules.py`
- 修改：`tests/test_strategy6_versioning.py`

- [ ] **步骤1：编写失败测试证明评分不影响正式结果**

对同一真实构造数据分别让评分函数返回高分和低分，断言两次结果的 `candidate_type`、`classification`、`reject_reasons`、`total_score`、交易计划和VCP资格完全一致，仅新增评分字段不同。

- [ ] **步骤2：运行主链测试确认评分尚未接入**

运行：`python -m pytest tests/test_strategy6_core_rules.py tests/test_strategy6_versioning.py -q`

预期：新增断言FAIL，候选字典缺少 `vcp_quality_score` 或版本仍为4.4.0。

- [ ] **步骤3：在基础过滤之后附加评分**

在 `apply_vcp_base_filters(vcp_observation, reject_reasons)` 之后执行：

```python
if vcp_observation.eligible:
    vcp_observation.quality = evaluate_vcp_quality(rows, vcp_observation)
```

不得把评分传给 `score_strategy6()`、`hard_filter_reasons()` 或 `classify_candidate()`。

- [ ] **步骤4：序列化全部评分字段**

候选字典使用可空总分，字段名严格与规格一致。`vcp_quality_reasons` 和 `vcp_quality_warnings` 输出列表，`vcp_quality_model_version` 输出 `VCP_QUALITY_V1`。

- [ ] **步骤5：升级策略版本并运行专项测试**

将 `STRATEGY6_VERSION` 改为 `4.5.0`。

运行：`python -m pytest tests/test_strategy6_core_rules.py tests/test_strategy6_vcp_observer.py tests/test_strategy6_vcp_history.py tests/test_strategy6_vcp_quality.py tests/test_strategy6_versioning.py -q`

预期：全部PASS，旧VCP识别和历史资格测试不变。

- [ ] **步骤6：提交引擎接入**

```bash
git add strategy6/engine.py strategy6/models.py strategy6/version.py tests/test_strategy6_core_rules.py tests/test_strategy6_versioning.py
git commit -m "feat: attach vcp quality to strategy6 evaluations"
```

### 任务3：SQLite兼容持久化

**文件：**
- 修改：`scanner/db.py`
- 修改：`tests/test_strategy6_db_api.py`

- [ ] **步骤1：编写字段迁移和完整往返失败测试**

扩展策略6候选表字段集合测试，并写入一个总分83、等级 `HIGH`、六个分项、原因、警告和模型版本的候选。断言读取值完全一致；另写入旧候选，断言 `vcp_quality_score is None`。

- [ ] **步骤2：运行数据库测试确认缺列失败**

运行：`python -m pytest tests/test_strategy6_db_api.py -q`

预期：FAIL，缺少 `vcp_quality_*` 列或往返字段。

- [ ] **步骤3：增加兼容列和读写**

总分列声明为 `INTEGER`，不要使用 `DEFAULT 0`；等级和版本为 `TEXT`；六个分项为 `INTEGER`；原因和警告使用项目现有JSON序列化辅助函数。反序列化时将两项JSON字段恢复为列表，不把NULL转换为0。

- [ ] **步骤4：运行数据库和扫描集成测试**

运行：`python -m pytest tests/test_strategy6_db_api.py tests/test_strategy6_scanner.py tests/test_strategy6_report.py -q`

预期：全部PASS，评分前后观察记录集合测试保持一致。

- [ ] **步骤5：提交持久化改动**

```bash
git add scanner/db.py tests/test_strategy6_db_api.py
git commit -m "feat: persist strategy6 vcp quality snapshots"
```

### 任务4：前端排序、展示和导出

**文件：**
- 修改：`web/src/pages/Strategy6Results.vue`
- 修改：`web/src/utils/strategy6Labels.js`
- 修改：`web/src/pages/__tests__/Strategy6Results.test.js`

- [ ] **步骤1：编写排序和旧任务失败测试**

构造有评分83、83、72和无评分的四只股票，断言顺序为：有评分优先、分数降序、同分按 `VCP_NEAR_PIVOT` 优先，再按策略总分和代码。构造4.4.0任务，断言候选仍显示且分数为“未评分”。

- [ ] **步骤2：编写展示和导出失败测试**

断言表格显示 `83 / 高质量VCP`；点击后显示六个分项、模型版本、原因和警告；CSV包含全部新增字段且空分数导出为空字符串。

- [ ] **步骤3：运行前端专项测试确认失败**

运行：`npm.cmd --prefix web test -- --run Strategy6Results`

预期：新增排序、字段和详情断言FAIL。

- [ ] **步骤4：实现独立VCP排序**

不要复用按策略总分排序的 `sortedCandidates`。先过滤结构与历史资格，再使用稳定比较器：评分是否存在、评分降序、状态优先级、策略总分降序、股票代码升序。

- [ ] **步骤5：实现表格、详情、标签和CSV字段**

在表格中增加“VCP形态分/等级”，把原“总分”明确改名为“策略总分”。详情展示六项得分及上限。4.4任务保留候选并提示重新扫描可生成评分；缺失值显示“未评分”，禁止通过 `?? 0` 伪造0分。

- [ ] **步骤6：运行前端专项和构建**

运行：`npm.cmd --prefix web test -- --run Strategy6Results`

运行：`npm.cmd --prefix web run build`

预期：测试和生产构建全部成功。

- [ ] **步骤7：提交前端改动**

```bash
git add web/src/pages/Strategy6Results.vue web/src/utils/strategy6Labels.js web/src/pages/__tests__/Strategy6Results.test.js
git commit -m "feat: rank strategy6 vcp candidates by quality"
```

### 任务5：真实数据验收、文档和双角色闭环

**文件：**
- 创建：`docs/reviews/2026-07-17-strategy6-vcp-quality-scoring-validation.md`
- 修改：`CLAUDE.md`

- [ ] **步骤1：使用本地真实数据生成同口径评分报告**

使用 `data/cuphandle.db` 中最新策略6任务对应股票日线和真实指数数据重新执行扫描或等价当日评估。报告记录任务ID、评分前后VCP池代码集合差异、全部评分、前10名六项明细、五档分布、异常高低分和微小收缩样本。

- [ ] **步骤2：核查已讨论样本**

报告单列 `002156`、`002281` 的评分、等级、六项分数、VCP状态和解释。若样本在验收日不具备当前VCP持续观察资格，必须明确写出不在池原因，不能伪造评分排名。

- [ ] **步骤3：更新项目事实文档**

在 `CLAUDE.md` 增加V4.5边界：VCP形态分只排序展示、模型固定、旧任务NULL、不得进入正式策略评分或过滤。

- [ ] **步骤4：运行完整验证门禁**

运行：

```bash
python -m pytest tests/test_strategy6_core_rules.py tests/test_strategy6_db_api.py tests/test_strategy6_limit_up.py tests/test_strategy6_report.py tests/test_strategy6_scanner.py tests/test_strategy6_vcp_observer.py tests/test_strategy6_vcp_history.py tests/test_strategy6_vcp_quality.py tests/test_strategy6_versioning.py -q
python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py --ignore=tests/test_yfinance_hist.py
python -m compileall scanner strategy6 server.py -q
npm.cmd --prefix web test -- --run
npm.cmd --prefix web run build
```

预期：全部通过。

- [ ] **步骤5：切换审核专家角色验收**

重点检查未来数据、评分与入池隔离、NULL兼容、舍入边界、任务快照、前端稳定排序、CSV空值和策略1至策略5回归。发现中高等级问题时先增加失败测试，再做最小修复并重跑门禁，直到没有中高等级问题。

- [ ] **步骤6：提交验收文档并推送**

先用 `git status --short` 和 `git diff --cached --name-only` 排除用户已有报告改动。提交验收文档：

```bash
git add CLAUDE.md docs/reviews/2026-07-17-strategy6-vcp-quality-scoring-validation.md docs/superpowers/plans/2026-07-17-strategy6-vcp-quality-scoring.md
git commit -m "docs: validate strategy6 vcp quality scoring"
git push
```

不得合并main，除非用户另行明确要求。

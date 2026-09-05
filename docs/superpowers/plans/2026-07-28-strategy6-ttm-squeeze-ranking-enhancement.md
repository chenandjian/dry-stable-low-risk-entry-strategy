# 策略6 TTM Squeeze 质量排序增强实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 在不改变策略6原候选资格、100分总分、生命周期和交易计划的前提下，新增可审计的 TTM Squeeze 状态、0至4分独立质量加分和候选类型内排序。

**架构：** 新建策略6专用计算模块，以评估日已截断的前复权 OHLC 计算 BB、Keltner Channel 和线性回归动量；引擎只把结果附加到输出，并在原评分完成后生成 `ranking_score`。候选数据库、API、报告和前端透传并展示新字段，旧任务以 `total_score` 回退排序。

**技术栈：** Python 3.10+、dataclasses、SQLite、pytest、Vue 3、Vitest。

---

## 文件结构

- 创建 `strategy6/ttm_squeeze.py`：TTM Squeeze 的纯计算和状态判定，不依赖扫描、数据库或前端。
- 修改 `strategy6/models.py`：新增 `Strategy6TtmSqueeze`，在评估输出中附加 TTM 与排序分。
- 修改 `strategy6/engine.py`：调用 TTM 模块；原评分、硬过滤和分类调用签名保持不变。
- 修改 `strategy6/validation.py`、`config.yaml`：增加显式默认配置、深合并和参数校验。
- 修改 `strategy6/version.py`：输出模型升级为 `4.9.0`。
- 修改 `scanner/db.py`：兼容迁移、写入、读取、JSON反序列化和同类候选排序。
- 修改 `strategy6/report.py`：报告附加 TTM 审计字段。
- 修改 `web/src/pages/StrategyConfig.vue`：提供 TTM 开关和参数配置。
- 修改 `web/src/pages/Strategy6Results.vue`：候选表、详情和 CSV 展示中文 TTM 状态。
- 修改 `web/src/utils/strategy6Labels.js`：新增 TTM 状态和动量方向中文映射。
- 创建 `tests/test_strategy6_ttm_squeeze.py`：公式、边界、状态、历史截断和原策略不变测试。
- 修改 `tests/test_strategy6_db_api.py`、`tests/test_strategy6_report.py`：存储、旧库兼容、排序和报告测试。
- 修改 `web/src/pages/__tests__/Strategy6Results.test.js`、`web/src/pages/__tests__/StrategyConfig.scheduler.test.js`、`web/src/utils/__tests__/strategy6Labels.test.js`：前端回归测试。
- 创建 `docs/reviews/2026-07-28-strategy6-ttm-squeeze-real-data-validation-report.md`：本地真实数据验证结果。

### 任务1：冻结核心公式与状态机

**文件：**
- 创建：`tests/test_strategy6_ttm_squeeze.py`
- 创建：`strategy6/ttm_squeeze.py`
- 修改：`strategy6/models.py`

- [ ] **步骤1：编写公式与边界失败测试**

测试公开入口 `calculate_ttm_squeeze(rows, config)`，并通过稳定样本断言：

```python
def test_ttm_squeeze_uses_strict_band_containment():
    result = calculate_ttm_squeeze(rows, DEFAULT_TTM_CONFIG)
    assert result.squeeze_on is True
    assert result.bb_upper < result.kc_upper
    assert result.bb_lower > result.kc_lower

def test_ttm_equal_boundary_is_not_squeeze():
    result = classify_ttm_state(
        squeeze_on=False,
        previous_squeeze_on=True,
        momentum=1.0,
        previous_momentum=0.5,
        squeeze_days=0,
        min_bullish_days=3,
    )
    assert result.status == "FIRED_BULLISH"
    assert result.score == 4
```

同时覆盖总体标准差、SMA种子EMA、Wilder ATR、线性回归最后拟合点和最少40根数据。

- [ ] **步骤2：运行测试确认失败**

运行：`python -m pytest tests/test_strategy6_ttm_squeeze.py -q`

预期：FAIL，提示 `strategy6.ttm_squeeze` 或 `Strategy6TtmSqueeze` 尚不存在。

- [ ] **步骤3：实现纯计算和数据结构**

`Strategy6TtmSqueeze` 至少包含：

```python
@dataclass
class Strategy6TtmSqueeze:
    status: str = "INSUFFICIENT_DATA"
    squeeze_on: bool = False
    squeeze_days: int = 0
    fired: bool = False
    momentum: float | None = None
    previous_momentum: float | None = None
    momentum_direction: str = "UNKNOWN"
    bb_upper: float | None = None
    bb_lower: float | None = None
    kc_upper: float | None = None
    kc_lower: float | None = None
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    risk_tags: list[str] = field(default_factory=list)
    model_version: str = "S6_TTM_SQUEEZE_V1"
```

计算模块必须在数据不足或OHLC非法时返回可审计结果，不抛出到策略主链；挤压边界使用严格 `<` 和 `>`。

- [ ] **步骤4：运行核心单元测试**

运行：`python -m pytest tests/test_strategy6_ttm_squeeze.py -q`

预期：公式、8种状态、非法数据和未来行截断测试全部 PASS。

- [ ] **步骤5：提交核心计算**

```bash
git add strategy6/ttm_squeeze.py strategy6/models.py tests/test_strategy6_ttm_squeeze.py
git commit -m "feat: add strategy6 TTM squeeze indicator"
```

### 任务2：接入引擎并锁死原策略行为

**文件：**
- 修改：`strategy6/engine.py`
- 修改：`strategy6/validation.py`
- 修改：`strategy6/version.py`
- 修改：`config.yaml`
- 测试：`tests/test_strategy6_ttm_squeeze.py`
- 测试：`tests/test_strategy6_core_rules.py`

- [ ] **步骤1：编写开启/关闭等价性失败测试**

对同一组日线分别启用和关闭 TTM，断言以下旧结论完全一致：

```python
assert enabled.score.total_score == disabled.score.total_score
assert enabled.candidate_type == disabled.candidate_type
assert enabled.reject_reasons == disabled.reject_reasons
assert enabled.lifecycle_status == disabled.lifecycle_status
assert enabled.trade_plan == disabled.trade_plan
assert enabled.ranking_score == enabled.score.total_score + enabled.ttm_squeeze.score
assert disabled.ranking_score == disabled.score.total_score
```

另以 `rows[:evaluation_index + 1]` 和附加未来异常行情的输入比较同一评估日结果，证明回测无未来数据读取。

- [ ] **步骤2：运行专项测试确认失败**

运行：`python -m pytest tests/test_strategy6_ttm_squeeze.py tests/test_strategy6_core_rules.py -q`

预期：FAIL，新配置、引擎字段和 `ranking_score` 尚未接入。

- [ ] **步骤3：加入配置、校验和引擎透传**

`resolve_strategy6_config()` 对 `ttm_squeeze` 使用 `_merge_known_dict()`，保留未显式覆盖的默认子键。周期校验为 `5..120`，倍数为 `(0, 10]`，连续天数为 `1..20`，`max_ranking_bonus` 必须等于4。

引擎结构固定为：

```python
ttm_squeeze = calculate_ttm_squeeze(rows, self.config["ttm_squeeze"])
score = score_strategy6(...)
ranking_score = score.total_score + ttm_squeeze.score
reject_reasons = hard_filter_reasons(...)
candidate_type, ... = classify_candidate(...)
```

不得向 `score_strategy6()`、`hard_filter_reasons()` 或 `classify_candidate()` 传入 TTM。

- [ ] **步骤4：运行策略6核心回归**

运行：`python -m pytest tests/test_strategy6_ttm_squeeze.py tests/test_strategy6_core_rules.py -q`

预期：PASS，且旧分类测试无需修改期望值。

- [ ] **步骤5：提交引擎接入**

```bash
git add strategy6/engine.py strategy6/validation.py strategy6/version.py config.yaml tests/test_strategy6_ttm_squeeze.py tests/test_strategy6_core_rules.py
git commit -m "feat: rank strategy6 candidates with TTM quality"
```

### 任务3：持久化、API兼容与报告

**文件：**
- 修改：`scanner/db.py`
- 修改：`strategy6/report.py`
- 修改：`tests/test_strategy6_db_api.py`
- 修改：`tests/test_strategy6_report.py`

- [ ] **步骤1：编写新旧数据库失败测试**

覆盖新候选往返、JSON列表解析、旧行回退和排序：

```python
assert row["ttm_squeeze_status"] == "FIRED_BULLISH"
assert row["ttm_reasons"] == ["TTM_FIRED", "TTM_MOMENTUM_POSITIVE"]
assert row["ranking_score"] == row["total_score"] + 4
assert legacy_row["ranking_score"] == legacy_row["total_score"]
assert [row["code"] for row in same_type_rows] == ["000002", "000001"]
```

排序测试必须同时含不同候选类型，证明 `WATCH_CANDIDATE` 不能凭 TTM 加分排到重点候选之前。

- [ ] **步骤2：运行存储测试确认失败**

运行：`python -m pytest tests/test_strategy6_db_api.py tests/test_strategy6_report.py -q`

预期：FAIL，缺少列、写入值、报告列或排序回退。

- [ ] **步骤3：实现兼容迁移、写入和排序**

新增列使用 `_ensure_column()`；`ranking_score` 保持可空，读取时执行：

```python
row["ranking_score"] = (
    row.get("ranking_score")
    if row.get("ranking_score") is not None
    else row.get("total_score", 0)
)
```

SQL排序使用候选类型优先级，再按 `COALESCE(ranking_score, total_score) DESC, total_score DESC, code ASC`。`ttm_reasons`、`ttm_risk_tags` 作为JSON文本存储并恢复为列表。

- [ ] **步骤4：补充报告列并运行测试**

运行：`python -m pytest tests/test_strategy6_db_api.py tests/test_strategy6_report.py tests/test_strategy6_scanner.py -q`

预期：PASS；扫描落库和API返回完整新字段，旧任务仍可读。

- [ ] **步骤5：提交存储与报告**

```bash
git add scanner/db.py strategy6/report.py tests/test_strategy6_db_api.py tests/test_strategy6_report.py
git commit -m "feat: persist strategy6 TTM audit fields"
```

### 任务4：前端中文配置与候选展示

**文件：**
- 修改：`web/src/pages/StrategyConfig.vue`
- 修改：`web/src/pages/Strategy6Results.vue`
- 修改：`web/src/utils/strategy6Labels.js`
- 修改：`web/src/pages/__tests__/StrategyConfig.scheduler.test.js`
- 修改：`web/src/pages/__tests__/Strategy6Results.test.js`
- 修改：`web/src/utils/__tests__/strategy6Labels.test.js`

- [ ] **步骤1：编写前端失败测试**

断言配置页可加载和保存全部参数；重点、观察和VCP确认候选均展示“TTM状态”；旧任务显示“未计算”；详情显示布林带、Keltner、动量、触发原因和风险；CSV包含全部审计字段。

- [ ] **步骤2：运行前端专项测试确认失败**

运行：`npm.cmd --prefix web test -- --run Strategy6Results StrategyConfig.scheduler strategy6Labels`

预期：FAIL，页面尚无TTM控件和列。

- [ ] **步骤3：实现配置和展示**

中文映射至少包括：`FIRED_BULLISH=多头挤压释放`、`SQUEEZE_BULLISH=多头挤压蓄力`、`SQUEEZE_NEUTRAL=挤压中`、`SQUEEZE_BEARISH=弱势挤压`、`FIRED_WEAK=弱势释放`、`OFF=未挤压`、`INSUFFICIENT_DATA=数据不足`、`DISABLED=已关闭`。

旧任务仅在字段不存在或为空时显示“未计算”，不能把缺字段转换为 `OFF`。候选分组顺序不变，每组内部使用 `ranking_score`、`total_score`、代码排序。

- [ ] **步骤4：运行前端专项测试与构建**

运行：

```bash
npm.cmd --prefix web test -- --run Strategy6Results StrategyConfig.scheduler strategy6Labels
npm.cmd --prefix web run build
```

预期：测试 PASS，生产构建成功。

- [ ] **步骤5：提交前端**

```bash
git add web/src/pages/StrategyConfig.vue web/src/pages/Strategy6Results.vue web/src/utils/strategy6Labels.js web/src/pages/__tests__/StrategyConfig.scheduler.test.js web/src/pages/__tests__/Strategy6Results.test.js web/src/utils/__tests__/strategy6Labels.test.js
git commit -m "feat: show strategy6 TTM quality ranking"
```

### 任务5：真实数据验证、审查和交付

**文件：**
- 创建：`docs/reviews/2026-07-28-strategy6-ttm-squeeze-real-data-validation-report.md`

- [ ] **步骤1：运行本地真实数据验证**

使用 `data/cuphandle.db` 最近完整交易日，按当前生产配置调用 `StrongVcpTailEngine.evaluate_at()`。报告记录数据日期、股票数、失败数、TTM状态分布、候选类型分布、前20名排序变化和代表股票；不得联网补数或自动修改参数。

- [ ] **步骤2：执行双角色审查**

逐项核对：原候选资格和 `total_score` 零变化；TTM只用评估日以前数据；旧库回退排序；类型优先级；配置部分覆盖深合并；前端旧任务不伪造状态。发现中高等级问题先修复并补回归测试。

- [ ] **步骤3：运行完整验证门禁**

```bash
python -m compileall scanner strategy6 server.py -q
python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py --ignore=tests/test_yfinance_hist.py
npm.cmd --prefix web test -- --run
npm.cmd --prefix web run build
```

预期：编译成功、后端和前端测试全部PASS、构建成功。

- [ ] **步骤4：提交报告并推送**

```bash
git add docs/reviews/2026-07-28-strategy6-ttm-squeeze-real-data-validation-report.md
git commit -m "docs: validate strategy6 TTM ranking on real data"
git push
```

## 自检结果

- 规格覆盖：公式、8种状态、独立分、同类排序、配置、持久化、API、报告、前端、旧任务兼容和真实数据验证均有对应任务。
- 行为边界：计划明确禁止 TTM 进入原评分、硬过滤和分类函数，且由开启/关闭等价测试约束。
- 历史安全：计算入口只接收 `evaluate_at()` 已截断日线，并有未来数据不影响历史结果测试。
- 类型一致：统一使用 `Strategy6TtmSqueeze.score`、候选字段 `ttm_squeeze_score` 和 `ranking_score`。
- 无占位步骤：每一阶段均包含具体文件、失败测试、实现口径、命令和预期结果。

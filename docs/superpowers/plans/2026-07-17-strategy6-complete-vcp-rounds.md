# 策略6完整VCP轮次识别实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 用“峰值 -> 最终低点 -> 有效反弹峰值”的完整轮次模型替换策略6主链和观察池的旧VCP峰谷算法，并对全市场本地日线重新验收。

**架构：** 新增无数据库依赖的 `strategy6/vcp_rounds.py` 作为唯一轮次识别核心。主链形态检测和独立观察池分别适配相同结果；主链只接受至少两轮完整结构，观察池额外保存一轮完整、下一轮形成中的早期观察。旧字段保持兼容，新证据只追加字段。

**技术栈：** Python 3.10、dataclasses、pytest、SQLite、Vue 3、Vitest。

---

## 文件结构

- 创建 `strategy6/vcp_rounds.py`：完整轮次状态机、弱反抽合并、价格和量能证据。
- 修改 `strategy6/pattern.py`：主链VCP改用共享核心。
- 修改 `strategy6/vcp_observer.py`：观察池改用共享核心并输出早期/确认状态。
- 修改 `strategy6/strong_start.py`：历史启动锚点排除失败事件。
- 修改 `strategy6/models.py`：兼容增加VCP阶段字段，旧字段保留。
- 修改 `strategy6/validation.py`、`config.yaml`：增加四个显式配置与校验。
- 修改 `strategy6/vcp_quality.py`：质量分只消费完整轮次证据。
- 修改 `scanner/db.py`：新字段兼容迁移、写入和读取。
- 修改 `web/src/pages/Strategy6Results.vue`、`web/src/strategy6Labels.js`：确认候选和早期观察分组及完整轮次证据。
- 修改 `web/src/pages/StrategyConfig.vue`：新增参数展示、默认值和校验。
- 新增/修改策略6专项测试与真实验收报告。

### 任务1：共享完整轮次核心

**文件：**
- 创建：`strategy6/vcp_rounds.py`
- 创建：`tests/test_strategy6_vcp_rounds.py`

- [ ] **步骤1：编写真实样本失败测试**

测试固定 `603505`、`000703`、`002156`、`002056` 的逐日收盘与成交量，断言：

```python
assert detect_vcp_rounds(rows_603505, cfg).completed_rounds == []
assert dates(detect_vcp_rounds(rows_000703, cfg).completed_rounds[0]) == (
    "2026-07-06", "2026-07-13", "2026-07-14",
)
assert len(detect_vcp_rounds(rows_002156, cfg).completed_rounds) == 2
assert len(detect_vcp_rounds(rows_002056, cfg).completed_rounds) == 1
```

- [ ] **步骤2：运行测试确认失败**

运行：`python -m pytest tests/test_strategy6_vcp_rounds.py -q`

预期：FAIL，`strategy6.vcp_rounds` 尚不存在。

- [ ] **步骤3：实现最小状态机**

定义：

```python
@dataclass(frozen=True)
class VcpRound:
    peak_index: int
    low_index: int
    recovery_peak_index: int
    amplitude: float
    rebound: float
    decline_avg_volume: float
    rebound_avg_volume: float
    breakout_confirmed: bool = False

@dataclass(frozen=True)
class VcpRoundDetection:
    completed_rounds: list[VcpRound]
    forming_round: VcpRound | None
    risk_tags: list[str]
```

实现 `detect_vcp_rounds(rows, config)`：弱反抽后创新低必须合并；普通反弹需两个可见交易日和回落确认；直接突破按涨幅或量比确认。

- [ ] **步骤4：补充边界测试并通过**

覆盖首轮 `8%/32%`、后轮幅度比、下跌量比、低点 `97%/99%`、微小末轮和未来数据隔离。

- [ ] **步骤5：提交**

```bash
git add strategy6/vcp_rounds.py tests/test_strategy6_vcp_rounds.py
git commit -m "feat: detect complete strategy6 vcp rounds"
```

### 任务2：主链形态接入

**文件：**
- 修改：`strategy6/pattern.py`
- 修改：`tests/test_strategy6_core_rules.py`

- [ ] **步骤1：编写主链失败测试**

断言假VCP返回 `UNKNOWN` 且不生成枢轴和形态低点；`002156` 型两轮结构返回VCP：

```python
assert false_pattern.pattern_type == "UNKNOWN"
assert false_pattern.pattern_score == 0
assert false_pattern.pivot_price == 0
assert valid_pattern.pattern_type == "VCP"
assert valid_pattern.contraction_count == 2
```

- [ ] **步骤2：运行测试确认旧实现失败**

运行：`python -m pytest tests/test_strategy6_core_rules.py -k "vcp and pattern" -q`

- [ ] **步骤3：替换旧函数调用**

`_detect_vcp()` 调用 `detect_vcp_rounds()`；只有两轮完整结构才能生成主链VCP。移除 `_swing_contractions()` 和 `_best_vcp_chain()` 的业务调用，不在主链重复轮次判断。

- [ ] **步骤4：验证评分、支撑和交易计划不会读取不完整VCP**

断言假VCP的 `pattern_score_component`、`PATTERN_LOW`、`pivot_price` 均不再由VCP产生。

- [ ] **步骤5：提交**

```bash
git add strategy6/pattern.py tests/test_strategy6_core_rules.py
git commit -m "fix: use complete vcp rounds in strategy6 main chain"
```

### 任务3：观察池、启动锚点和历史资格

**文件：**
- 修改：`strategy6/vcp_observer.py`
- 修改：`strategy6/strong_start.py`
- 修改：`strategy6/models.py`
- 修改：`tests/test_strategy6_vcp_observer.py`
- 修改：`tests/test_strategy6_strong_start.py`

- [ ] **步骤1：编写失败测试**

断言一轮完整输出 `VCP_ROUND1_CONFIRMED` 和早期观察标记，两轮输出确认状态；带失败原因的启动不能成为历史锚点。

- [ ] **步骤2：运行专项测试确认失败**

运行：`python -m pytest tests/test_strategy6_vcp_observer.py tests/test_strategy6_strong_start.py -q`

- [ ] **步骤3：观察池改用共享核心**

序列化每轮 `peak/low/recovery_peak` 日期、价格、幅度、反弹、下跌/反弹均量。保持旧 `vcp_contractions` 字段名，追加键而不删除旧键。

- [ ] **步骤4：强化基础失效过滤**

`apply_vcp_base_filters()` 除数据与流动性外，拦截 `SUPPORT_FAILED`、`BIG_DOWN_VOLUME`、`DISTRIBUTION_PRESSURE_HIGH` 和不可恢复支撑放量破位。失败事件不得作为 `find_historical_start_anchor()` 返回值。

- [ ] **步骤5：运行测试并提交**

```bash
git add strategy6/vcp_observer.py strategy6/strong_start.py strategy6/models.py tests/test_strategy6_vcp_observer.py tests/test_strategy6_strong_start.py
git commit -m "feat: track complete vcp lifecycle states"
```

### 任务4：配置、质量分和持久化兼容

**文件：**
- 修改：`strategy6/validation.py`
- 修改：`config.yaml`
- 修改：`strategy6/vcp_quality.py`
- 修改：`scanner/db.py`
- 修改：`tests/test_strategy6_vcp_quality.py`
- 修改：`tests/test_strategy6_db_api.py`

- [ ] **步骤1：编写配置与序列化失败测试**

验证新增默认值、非法边界、新轮次JSON数据库往返和旧记录缺字段兼容。

- [ ] **步骤2：运行测试确认失败**

运行：`python -m pytest tests/test_strategy6_vcp_quality.py tests/test_strategy6_db_api.py -q`

- [ ] **步骤3：实现配置和质量分V2**

新增四项配置；质量分改用完整轮次并将模型版本升级为 `VCP_QUALITY_V2`。质量分仍不进入策略总分或候选资格。

- [ ] **步骤4：实现数据库兼容**

优先把追加证据保存在现有 `vcp_contractions` JSON 中；只在需要顶层查询时用 `_ensure_column()` 增加字段，禁止破坏性迁移和旧任务重算。

- [ ] **步骤5：运行测试并提交**

```bash
git add strategy6/validation.py config.yaml strategy6/vcp_quality.py scanner/db.py tests/test_strategy6_vcp_quality.py tests/test_strategy6_db_api.py
git commit -m "feat: persist complete vcp evidence and quality"
```

### 任务5：前端分层和完整轮次证据

**文件：**
- 修改：`web/src/pages/Strategy6Results.vue`
- 修改：`web/src/pages/StrategyConfig.vue`
- 修改：`web/src/strategy6Labels.js`
- 修改：`web/src/pages/__tests__/Strategy6Results.test.js`
- 修改：`web/src/pages/__tests__/StrategyConfig.scheduler.test.js`

- [ ] **步骤1：编写失败测试**

断言页面同时显示“VCP确认候选”和“VCP早期观察”，每轮使用“峰值 -> 低点 -> 反弹峰值”展示；旧任务显示“旧任务未记录完整轮次”。

- [ ] **步骤2：运行前端测试确认失败**

运行：`npm.cmd --prefix web test -- --run Strategy6Results StrategyConfig.scheduler`

- [ ] **步骤3：实现展示和配置**

按生命周期拆分同一候选数组；增加四项配置输入及中文标签；CSV追加反弹峰值和完整轮次状态，保留旧列。

- [ ] **步骤4：测试和构建**

运行：

```bash
npm.cmd --prefix web test -- --run Strategy6Results StrategyConfig.scheduler
npm.cmd --prefix web run build
```

- [ ] **步骤5：提交**

```bash
git add web/src/pages/Strategy6Results.vue web/src/pages/StrategyConfig.vue web/src/strategy6Labels.js web/src/pages/__tests__/Strategy6Results.test.js web/src/pages/__tests__/StrategyConfig.scheduler.test.js
git commit -m "feat: show complete vcp candidate stages"
```

### 任务6：全市场验收、审核和报告

**文件：**
- 创建：`docs/reviews/2026-07-17-strategy6-complete-vcp-rounds-validation.md`
- 修改：`CLAUDE.md`

- [ ] **步骤1：运行策略6专项回归**

```bash
python -m pytest tests/test_strategy6_vcp_rounds.py tests/test_strategy6_vcp_observer.py tests/test_strategy6_vcp_quality.py tests/test_strategy6_core_rules.py tests/test_strategy6_scanner.py tests/test_strategy6_db_api.py -q
python -m compileall scanner strategy6 server.py -q
```

- [ ] **步骤2：运行全量门禁**

```bash
python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py --ignore=tests/test_yfinance_hist.py
npm.cmd --prefix web test -- --run
npm.cmd --prefix web run build
```

- [ ] **步骤3：用本地数据库全市场重放**

从 `stock_pool/daily_ohlc` 读取全部满足500根日线的股票，直接执行新轮次核心和策略6入口。报告确认候选、早期观察、主链VCP、排除数量及股票明细，不得只读取旧任务VCP候选。

- [ ] **步骤4：审核与修复循环**

以审核角色检查：未来数据泄漏、旧API兼容、主链评分/支撑副作用、观察池历史资格、全市场候选偏差。发现中高问题先写失败测试，再最小修复并重复门禁。

- [ ] **步骤5：更新文档并提交推送**

```bash
git add CLAUDE.md docs/reviews/2026-07-17-strategy6-complete-vcp-rounds-validation.md
git commit -m "docs: validate complete strategy6 vcp rounds"
git push
```

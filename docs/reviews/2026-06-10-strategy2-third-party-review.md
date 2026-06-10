# 策略2「极致量干价稳」第三方代码审核说明

## 审核范围

本次开发在独立分支 `codex/strategy2-extreme-dry-stable-design` 上完成，新增策略2「极致量干价稳」独立全市场扫描链路。策略2与策略1（杯柄/VCP）共享基础设施，但业务判断链路完全独立。

## 提交清单（共 10 个 commit）

```
7b00f2b docs: update CLAUDE.md with strategy2 architecture, design decisions, gotchas
70a930a feat(frontend): add strategy2 config section to StrategyConfig page
a0b3537 docs: update operations-log — strategy2 config page completed
185a2bd docs: add strategy2 development operations log
eff4597 feat(strategy2): full implementation — engine, scanner, DB, API, frontend
538c5ea test(strategy2): add independence boundary checks
965b385 feat(strategy2): add ExtremeDryStableStrategyEngine
b262c8b feat(strategy2): add scorer, rejection rules, and risk calculator
68d6c26 feat(strategy2): add indicator computation module
905f733 feat(strategy2): add data models for extreme dry-stable strategy
```

## 文件变更一览

### 新增文件（14 个）

| 文件 | 行数 | 说明 |
|------|------|------|
| `strategy2/__init__.py` | 5 | 包初始化 |
| `strategy2/models.py` | 70 | 5 个 dataclass（Indicators/Score/Risk/Evaluation/Validation） |
| `strategy2/indicators.py` | 129 | V3-V20、分位、range、return 计算 + 数据校验 |
| `strategy2/scorer.py` | 101 | 量干50分 + 价稳50分 + 等级判定 |
| `strategy2/rejection.py` | 67 | 5 条一票否决（返回稳定错误码） |
| `strategy2/risk.py` | 85 | key_support（排除T日）、买入区间、止损、风险比 |
| `strategy2/engine.py` | 142 | ExtremeDryStableStrategyEngine — 唯一评估入口 |
| `strategy2/scanner.py` | 235 | scan_strategy2_all() — 多线程全市场扫描 |
| `scanner/daily_data_service.py` | 173 | 共享四源拉取（fetch_with_retry/FetchResult） |
| `tests/test_strategy2_models.py` | 120 | 模型测试 11 项 |
| `tests/test_strategy2_indicators.py` | 260 | 指标测试 28 项 |
| `tests/test_strategy2_scorer.py` | 170 | 评分测试 23 项 |
| `tests/test_strategy2_rejection.py` | 100 | 否决测试 12 项 |
| `tests/test_strategy2_risk.py` | 100 | 风险测试 13 项 |
| `tests/test_strategy2_engine.py` | 100 | 引擎测试 12 项 |
| `tests/test_strategy2_independence.py` | 100 | 独立性边界测试 5 项 |
| `web/src/pages/Strategy2Results.vue` | 150 | 策略2结果页 |

### 修改文件（9 个）

| 文件 | 变更 | 风险等级 |
|------|------|---------|
| `config.yaml` | +8 行 strategy2 配置段 | 低 |
| `scanner/db.py` | +160 行（strategy_type 字段、strategy2_candidates 表、CRUD） | **中** |
| `server.py` | +170 行（5 个策略2端点、全局互斥增强、_running 扩展） | **中** |
| `strategy2/models.py` | +1 字段（current_close） | 低 |
| `strategy2/engine.py` | +1 字段赋值 | 低 |
| `tests/test_server_scan_api.py` | 2 行错误码更新 | 低 |
| `web/src/components/ScanEngine.vue` | +5 行（strategy2 按钮） | 低 |
| `web/src/components/TopNav.vue` | +1 行（策略2导航） | 低 |
| `web/src/composables/useApi.js` | +25 行（策略2 API 函数） | 低 |
| `web/src/pages/ScannerConsole.vue` | +25 行（策略2 处理函数） | 低 |
| `web/src/pages/StrategyConfig.vue` | +110 行（策略2配置分区） | 低 |
| `web/src/router/index.js` | +1 行（策略2路由） | 低 |

## 核心审核要点

### 1. 策略2独立性边界

**要求**: `strategy2/` 下任何文件不得导入策略1判断模块。

**验证方法**:
```bash
# 运行独立性测试
python -m pytest tests/test_strategy2_independence.py -v

# 手动检查导入
grep -r "scanner.pattern_detector\|scanner.strategy_engine\|analyzer\." strategy2/
```

**已通过**: AST 扫描全部 7 个 strategy2 模块，0 违规导入。

---

### 2. 策略1 零回归

**要求**: 现有策略1的扫描、评分、决策、API、前端不受影响。

**验证方法**:
```bash
python -m pytest tests/ -v --ignore=tests/test_strategy2_*.py
```

**已通过**: 163 项策略1测试全部通过（含 scan/backtest/decision/db/api）。

---

### 3. 数据库向后兼容

**变更**:
- `scan_tasks` 新增 `strategy_type TEXT DEFAULT 'STRATEGY_1_CUP_HANDLE'`
- 新增 `strategy2_candidates` 表（独立于 `candidates`）

**审核要点**:
- 旧数据库启动时 `ALTER TABLE ADD COLUMN` 自动执行（`_ensure_scan_task_columns`）
- 旧任务 `strategy_type` 为 NULL，API 层默认按策略1解释
- 不修改 `daily_ohlc`、`candidates`、`task_stocks` 表结构和数据
- `strategy2_candidates` 使用 `UNIQUE(task_id, code)` 保证幂等写入

**验证方法**:
```bash
python -m pytest tests/test_db_strategy_fields.py tests/test_scan_task_tracking.py -v
```

---

### 4. 全局扫描互斥

**要求**: 同一时间只允许一个全市场扫描。

**变更**: `_running` 字典新增 `strategy_type` 字段；`_scan_conflict_response()` 返回含 `strategyType` 和 `runningTaskId` 的 409 响应。

**审核要点**:
- 策略1运行中启动策略2 → HTTP 409
- 策略2运行中启动策略1 → HTTP 409
- 重复启动同一策略 → 返回当前运行任务

---

### 5. 策略2核心算法正确性

**指标计算**: V3/V5/V10/V20 为简单移动平均；`return_5` = `close[-1] / close[-6] - 1`。详见 `strategy2/indicators.py`。

**评分**: 量干5条 × 10分 + 价稳5条 × 10分 = 满分100。严格不等式边界已测试。详见 `strategy2/scorer.py`。

**key_support**: `data[:-1][-10:]` 取最低收盘价，明确排除评估日。数据不足返回 None。详见 `strategy2/risk.py:compute_key_support()`。

**否决**: 5 条规则返回稳定错误码，空列表 = 通过。详见 `strategy2/rejection.py`。

**验证方法**:
```bash
python -m pytest tests/test_strategy2_indicators.py tests/test_strategy2_scorer.py \
  tests/test_strategy2_rejection.py tests/test_strategy2_risk.py tests/test_strategy2_engine.py -v
# 共 88 项测试
```

---

### 6. API 兼容性

**新增端点**（不影响现有接口）:
- `POST /api/strategy2/scans`
- `GET /api/strategy2/scans/status`
- `GET /api/strategy2/tasks`
- `GET /api/strategy2/candidates`
- `GET /api/strategy2/candidates/{code}`

**修改端点**:
- `GET /api/scan/status` — 返回新增 `strategyType` 字段
- `409` 冲突响应 — `error` 从 `"Scan already running"` 改为 `"SCAN_ALREADY_RUNNING"`

---

### 7. 前端变更

- 扫描控制台：单选按钮 → 双按钮（策略1 / 策略2）
- 策略配置页：新增金色独立分区（7参数 + 开关）
- 策略2结果页：独立路由 `/strategy2/results`，不显示杯柄/VCP 字段
- 导航栏：新增"策略2"入口

---

## 测试结果

```
267 passed, 0 failed, 1 warning in 4.37s
```

- 策略2 新增: 104 项
- 策略1 回归: 163 项
- 前端构建: `✓ built in 1.83s`

## 已知不交付项

| 项目 | 原因 |
|------|------|
| 策略2 回测 | 设计决策：本期不做 |
| 策略2 重新评估 | 设计决策：本期不做 |
| 策略2 CSV 导出 | 可选增强 |
| scanner/engine.py 迁移到 daily_data_service | 保持策略1稳定性（渐进迁移） |

## 审核建议

1. **优先审核**: `strategy2/engine.py`（唯一入口，组合所有模块）、`scanner/db.py`（数据库变更）、`server.py` 策略2 API 端点
2. **关注风险**: `key_support` 排除评估日的正确性、`V20=0` 除零保护、`return_5` 边界值
3. **回归确认**: 运行 `python -m pytest tests/ --ignore=tests/test_strategy2_*.py` 确认策略1零影响
4. **数据兼容**: 在旧数据库文件上启动服务，确认自动迁移不报错、旧数据可正常展示

---

*审核依据: `docs/superpowers/specs/2026-06-10-strategy2-extreme-dry-stable-design.md`*
*实施记录: `operations-log.md`*

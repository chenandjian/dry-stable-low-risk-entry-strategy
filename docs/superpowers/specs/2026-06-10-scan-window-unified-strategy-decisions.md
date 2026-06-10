# 扫描窗口与统一策略入口确认记录

Date: 2026-06-10

关联开发文档：

- `docs/superpowers/specs/2026-06-10-scan-window-unified-strategy-design.md`

## 1. 确认目的

本文档冻结“扫描策略窗口与统一策略入口优化”开发前的关键决策，消除实现过程中可能产生的不同解释。

以下决策均为本次开发的必须要求。若实现代码与本文档冲突，以本文档和关联开发文档更新后的内容为准。

## 2. 已确认决策

### 2.1 `select_strategy_window()` 数据不足时返回 `None`

确认采用以下接口：

```python
def select_strategy_window(
    data: list[dict],
    window_days: int,
) -> list[dict] | None:
    if window_days <= 0:
        raise ValueError("window_days must be a positive integer")
    if len(data) < window_days:
        return None
    return data[-window_days:]
```

规则：

- 函数负责校验窗口参数并截取固定长度窗口。
- 数据不足时返回 `None`，禁止返回缩短窗口供策略计算。
- 所有调用方必须显式处理 `None`。
- 扫描遇到 `None` 时将股票标记为 `skipped`。
- 回测遇到 `None` 时跳过该判断时点。
- 不允许调用方绕过该函数后静默使用不足天数的数据。

### 2.2 废弃批量回测 `window_min`

确认从 `scanner/backtester.py::run_backtest()` 公共函数签名中删除承担多重职责的 `window_min` 参数。

职责分离为：

```python
backtest_window_days = config.get("data", {}).get("backtest_window_days", 250)
min_forward_days = 60
```

规则：

- `backtest_window_days`：策略在每个历史判断时点使用的固定分析窗口。
- `min_forward_days`：回测收益观察需要保留的最大未来交易日数量。
- 单只股票最低数据要求为：

```python
len(data) >= backtest_window_days + min_forward_days
```

- 每个历史判断时点只向策略引擎传入最近 `backtest_window_days` 日。
- `min_forward_days` 不参与策略计算。

### 2.3 CLI `--min-score` 标记废弃

确认本版本保留 `main.py backtest --min-score` 参数兼容，但标记为废弃。

规则：

- 用户传入 `--min-score` 时打印明确废弃警告。
- `--min-score` 不得影响 `CupHandleStrategyEngine.evaluate_at()` 的候选资格结论。
- 本版本允许它在策略判断完成后作为回测报告展示过滤条件继续生效。
- 回测报告必须明确标记使用了报告过滤，避免用户将过滤后数量理解为策略原始候选数量。
- 下一版本删除该参数。

警告示例：

```text
WARNING: --min-score 已废弃，仅用于回测报告展示过滤，不参与策略候选判断；下一版本将删除。
```

### 2.4 候选详情按当前配置重新分析并提示语义差异

确认 `server.py` 的候选详情接口改为调用统一策略入口：

```python
CupHandleStrategyEngine(config).evaluate_at(...)
```

该行为定义为“按当前配置重新分析”，可能与任务扫描时保存的结果不同。

接口和 UI 必须同时展示：

- 原扫描任务保存结果。
- 当前配置重新分析结果。
- 当前配置重新分析提示。

提示文案：

```text
详情分析基于当前策略配置重新计算，可能与扫描任务产生时的结果不同。
```

本次不实现扫描任务配置快照。不得使用当前重算结果覆盖数据库中保存的原扫描结果。

### 2.5 `scan_window_days` 默认值固定为 `250`

确认新增配置：

```yaml
data:
  scan_window_days: 250
```

规则：

- `scan_window_days` 默认值固定为 `250`，不跟随 `min_listing_days`。
- 当前 `min_listing_days=351` 时，默认配置合法。
- 旧配置缺少 `scan_window_days` 时，后端使用固定默认值 `250`。
- `backtest_window_days` 缺失时同样使用固定默认值 `250`，避免策略窗口随拉取天数漂移。
- `scan_window_days > min_listing_days` 属于非法配置。
- 前端保存时阻止非法配置。
- 后端启动扫描时再次校验；非法时拒绝启动并返回明确错误，不只打印警告。

### 2.6 一次性完成全部 Phase 1-5

确认本次不采用仅处理部分入口的最小改动方案。

必须一次性完成全部范围，并按小步方式实施和验证：

1. Phase 1：配置、固定窗口函数与校验。
2. Phase 2：统一策略引擎收敛全部候选资格规则。
3. Phase 3：扫描与任务重新分析接入固定扫描窗口。
4. Phase 4：单股回测、批量回测和 CLI 接入固定回测窗口及统一策略入口。
5. Phase 5：候选详情统一重算、UI 提示和扫描回测一致性测试。

每个 Phase 完成后必须运行对应测试；全部 Phase 完成后运行全量后端测试和前端构建。

## 3. 不可违反的架构约束

1. `CupHandleStrategyEngine.evaluate_at()` 是唯一策略判断入口。
2. 只有策略引擎可以决定 `evaluation.passed`。
3. 调用方不得重复实现评分门槛、形态类型、决策状态或突破排除规则。
4. `min_listing_days` 只负责扫描拉取范围、上市天数检查和流动性过滤。
5. `scan_window_days` 只负责扫描策略计算窗口。
6. `backtest_window_days` 只负责回测策略计算窗口。
7. 数据不足固定策略窗口时不得使用缩短窗口计算。
8. 回测未来收益数据不得进入策略引擎。

## 4. 验收确认

开发完成后，必须能够证明：

- 扫描与回测使用同一个策略引擎和同一套候选规则。
- `scan_window_days == backtest_window_days` 且输入数据一致时，核心策略结果一致。
- 所有业务入口均不存在策略判断旁路。
- 候选详情不会混淆原扫描结果与当前配置重算结果。
- 六项确认决策均有自动化测试或明确验证步骤。

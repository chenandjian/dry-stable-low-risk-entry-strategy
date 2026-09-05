# 策略6规则治理修复验收报告

## 1. 验收范围

本轮针对 `2026-07-21-strategy6-overfitting-and-redundancy-review.md` 中 S6-001 至 S6-008 进行规则治理修复，不调参、不读取 2026 年 OOS 收益，也不修改策略1至策略5。

检查范围包括：

- 策略6正式扫描与研究回测的规则画像隔离
- ORIGINAL、BOX、Brooks、动态尾段和质量V2的调用边界
- 正式评分、硬过滤、候选分层和生命周期
- SQLite兼容迁移、候选输出、Excel/CSV和前端解释
- 策略6专项测试、项目后端全量回归、前端全量测试和生产构建

## 2. 总体结论

修复已覆盖原审查报告中的全部中高等级问题。策略6默认使用 `formal_original` 正式画像，正式扫描只允许固定尾段和 ORIGINAL 量干价稳路径参与评分、硬过滤和候选分层；动态尾段、BOX、Brooks及 `S6_QUALITY_V2` 仅在显式 `research_quality_v2` 画像中执行。

本轮没有发现未解决的中高等级问题。测试证明规则分流、旧字段兼容、数据库迁移和前端展示符合设计，但本轮没有运行真实全市场扫描或收益回测，因此不能据此宣称收益改善。

## 3. 问题闭环

| 编号 | 原问题 | 修复结果 | 状态 |
| --- | --- | --- | --- |
| S6-001 | 被否决的质量V2仍在正式链 | 新增规则画像；默认正式链不执行质量V2决策 | 已修复 |
| S6-002 | BOX负增量且成为KEY隐性必要条件 | 正式KEY直接读取ORIGINAL通过状态和原始量干价稳分，BOX不参与 | 已修复 |
| S6-003 | 真实质量0分绕过门槛 | `S6_QUALITY_V2` 的真实0分严格失败；仅旧评分模型保留缺失兼容 | 已修复 |
| S6-004 | `watch_min_score` 对成熟候选无效 | 成熟WATCH必须达到分数门槛，RR继续作为独立硬底线 | 已修复 |
| S6-005 | 同一证据重复参与多层决策 | 正式评分移除setup质量、支撑反应、阶段奖励和辅助路径分；相关字段保留诊断 | 已修复 |
| S6-006 | Brooks无独立正贡献仍进入生产 | 正式引擎不调用Brooks分析；研究画像保留完整实验能力 | 已修复 |
| S6-007 | 高复杂度研究配置污染生产 | 生产与研究画像分离；全面调优和BOX/Brooks命令显式进入研究画像 | 已修复 |
| S6-008 | 关闭形态过滤仍保留形态分 | 正式画像关闭 `pattern_filter_enabled` 后形态分固定为0 | 已修复 |

## 4. 核心实现

### 4.1 正式画像

默认 `decision_profile=formal_original`，使用 `S6_FORMAL_ORIGINAL_V1` 评分：

- 强势启动：20分
- 形态：20分
- 支撑簇：20分
- ORIGINAL尾部量干价稳：20分
- 客观RR：10分
- 相对强度与风险：10分

正式画像固定尾段窗口，不调用BOX和Brooks完整分析。setup质量、支撑反应及旧研究字段继续输出用于解释，不参与正式总分和KEY/READY门槛。

### 4.2 研究画像

显式 `decision_profile=research_quality_v2` 时保留原研究能力：

- 动态尾段
- ORIGINAL/BOX/Brooks组合路径
- `S6_QUALITY_V2`
- setup质量与支撑反应门槛

原始基线回测强制正式画像；BOX、Brooks及全面调优命令强制研究画像，避免配置默认值变化使历史研究入口失效。

### 4.3 数据与兼容

- 候选、任务生命周期、全局生命周期、Excel/CSV及前端详情新增 `decision_profile`。
- SQLite通过 `_ensure_column()` 非破坏迁移。
- 旧记录标记为 `legacy_unspecified`，前端显示“历史规则未标记”。
- 画像变化时生命周期建立新周期，避免旧研究池龄、失效或冷却状态阻塞正式候选。
- 旧API和旧候选字段未删除。

## 5. 验证结果

### 策略6专项回归

```text
python -m pytest tests/test_strategy6_*.py -q
527 passed
```

### 后端项目回归

```text
python -m pytest tests -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py --ignore=tests/test_yfinance_hist.py
1395 passed, 1 warning in 234.54s
```

唯一警告来自第三方 `dateutil` 的 `utcfromtimestamp()` 弃用提示，与本次策略6修改无关。

### 编译检查

```text
python -m compileall scanner strategy2 strategy3 strategy4 strategy5 strategy6 server.py -q
通过
```

### 前端回归与构建

```text
npm.cmd --prefix web test -- --run
17 files passed, 97 tests passed

npm.cmd --prefix web run build
通过
```

### Diff检查

```text
git diff --check
通过，仅有工作区既有换行符提示
```

## 6. 审核结论

代码审查重点检查了以下边界：

1. 正式画像不执行BOX/Brooks，辅助路径不能绕过ORIGINAL拒绝。
2. 正式KEY/READY不再依赖质量V2、支撑反应或辅助路径凑分。
3. 研究回测入口仍显式使用增强画像，不会因默认画像改变而退化为无效实验。
4. 数据库新增字段采用兼容迁移，旧任务可读且不会被伪装成正式画像。
5. 前端不提供普通开关启用研究画像，但能展示每条候选实际使用的规则。
6. 用户已有 `config.yaml` 和研究报告修改未被覆盖。

本轮验收未发现中、高等级遗留问题。

## 7. 残余风险与后续验证

- 新正式画像会改变重新扫描后的候选数量、总分和分层，这是规则回归到获批主链的预期结果，需要通过一次新的真实策略6扫描观察候选差异。
- 本轮没有执行真实全市场扫描，也没有读取2026 OOS收益；收益改善和候选质量不能由单元测试推断。
- 研究画像仍可由高级调用方通过原始配置显式指定，这是保留研究能力的设计行为；普通前端配置页没有启用入口。
- 画像切换会开启新的生命周期周期，因此切换后的首次扫描池龄从0开始。

## 8. 最终交付标准

1. 默认正式扫描只使用获批原始主链。
2. 研究能力保留且不污染正式决策。
3. 原审查中S6-001至S6-008均有测试覆盖或明确实现闭环。
4. 策略1至策略5完整回归通过。
5. 旧数据库、旧任务、旧API和旧输出字段保持兼容。
6. 没有用2026 OOS收益指导本轮修复。

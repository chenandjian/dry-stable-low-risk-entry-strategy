# 扫描窗口与统一策略入口最终验收复查

## 1. 检查范围

本次复查提交：

* `8ff1384 fix: address completion recheck COMPLETION-001 through COMPLETION-003`
* 父提交：`3bef48e`

重点检查：

* 所有策略入口的市场数据日期截断
* 完整杯柄、VCP-only、突破排除和策略拒绝一致性测试
* 扫描启动、配置保存和候选详情 API 回归测试
* 完整测试、编译、前端构建和提交差异检查

---

## 2. 总体结论

`8ff1384` 已修复本轮发现的业务逻辑问题。

确认结果：

* `select_market_window()` 已建立为共享市场窗口函数。
* 扫描、重新分析、CLI、候选详情、批量回测和单股回测均已使用共享函数。
* 直接复现中，股票判断日为 `2026-01-30` 时，传入策略的市场最后日期也为 `2026-01-30`，未来市场数据泄漏已消失。
* 关键 API 已新增入口级回归测试。
* 完整测试、编译和前端构建通过。

当前未发现新的必须修改的业务代码 bug。

仍有两项提交前质量问题：

1. 四类一致性测试虽然当前 fixture 确实分别产生杯柄、VCP 和突破排除结果，但测试没有对目标场景增加充分的非条件断言，未来 fixture 失效时测试可能继续通过。
2. 新加入的完成复查文档末尾存在多余空行，导致提交级 `git diff --check 3bef48e..8ff1384` 失败。

建议完成这两项小修后结束本功能开发。

---

## 3. COMPLETION-001 至 COMPLETION-003 验收结果

| 编号 | 状态 | 结论 |
| --- | --- | --- |
| COMPLETION-001 | 已修复 | 所有策略入口按股票判断日期截断市场数据 |
| COMPLETION-002 | 主体已修复，断言需加强 | 已覆盖真实策略和四类路径，但部分测试只比较一致性，没有证明 fixture 命中目标场景 |
| COMPLETION-003 | 已修复 | 扫描启动、配置保存、候选详情已有入口级 API 测试 |

---

## 4. 剩余问题

| 编号 | 问题 | 严重程度 | 是否阻塞业务功能 |
| --- | --- | --- | --- |
| ACCEPTANCE-001 | 四场景一致性测试缺少目标场景非条件断言 | 低 | 否 |
| ACCEPTANCE-002 | 完成复查文档末尾多余空行 | 低 | 否 |

---

## 5. 详细修复方案

### ACCEPTANCE-001：加强四场景一致性测试断言

#### 当前情况

直接计算当前 fixture 的真实结果：

```text
杯柄 fixture:
found=True
pattern_kind=cup_handle
key_pattern_type=cup_handle

VCP-only fixture:
found=False
pattern_kind=vcp
key_pattern_type=vcp

突破排除 fixture:
最终 passed=False
```

当前数据本身有效，但测试主要断言扫描与回测结果相等。如果未来 fixture 或策略变化导致“杯柄测试”不再产生杯柄，只要扫描和回测同时得到错误结果，测试仍会通过。

#### 精确修改代码

在杯柄一致性测试中增加：

```python
assert scan_call["core"]["pattern_kind"] == "cup_handle"
assert scan_call["core"]["key_pattern_type"] == "cup_handle"
assert scan_call["core"]["verdict_key"] is not None
assert scan_call["core"]["stop_loss"] is not None
assert scan_call["core"]["entry_zone_low"] is not None
assert scan_call["core"]["entry_zone_high"] is not None
```

在 VCP-only 一致性测试中增加：

```python
assert scan_call["core"]["pattern_kind"] == "vcp"
assert scan_call["core"]["key_pattern_type"] == "vcp"
assert scan_call["core"]["verdict_key"] is not None
assert scan_call["core"]["stop_loss"] is not None
```

突破排除测试需要捕获失败规则，证明失败原因确实包含突破排除，而不只是其他规则失败。

扩展捕获字段：

```python
def _evaluation_core(evaluation):
    dry = evaluation.dry_stable or {}
    return {
        # 现有字段保持不变
        "passed": evaluation.passed,
        "score": evaluation.result.score,
        "pattern_kind": evaluation.result.pattern_kind,
        "is_breakout": evaluation.result.is_breakout,
        "verdict_key": dry.get("decision", {}).get("verdict_key"),
        "key_pattern_type": dry.get("pattern_score", {}).get("key_pattern_type"),
        "stop_loss": dry.get("key_prices", {}).get("stop_loss"),
        "entry_zone_low": dry.get("key_prices", {}).get("entry_zone_low"),
        "entry_zone_high": dry.get("key_prices", {}).get("entry_zone_high"),
        "failed_rules": [rule.ruleName for rule in evaluation.failed_rules],
    }
```

突破测试增加：

```python
assert scan_call["core"]["is_breakout"] is True
assert scan_call["core"]["passed"] is False
assert "突破状态排除" in scan_call["core"]["failed_rules"]
```

策略拒绝测试增加：

```python
assert scan_call["core"]["passed"] is False
assert scan_call["core"]["verdict_key"] not in {
    "BUY_LOW",
    "WATCH_BREAKOUT",
    "WAIT_ENTRY",
}
```

以上断言应同时保留扫描与回测核心结果相等断言。

---

### ACCEPTANCE-002：删除文档末尾多余空行

#### 证据

执行：

```bash
git diff --check 3bef48e..8ff1384
```

返回：

```text
docs/reviews/2026-06-10-scan-window-unified-strategy-completion-recheck.md:593:
new blank line at EOF.
```

#### 修复

删除该文档末尾多余空白行，提交前运行：

```bash
git diff --check
git diff --check 3bef48e..HEAD
```

两个命令都必须无输出并返回成功。

---

## 6. 本次验证结果

### 直接复现

修复前：

```text
股票判断日期：2026-01-30
市场最后日期：2026-02-01
```

`8ff1384` 修复后：

```text
股票判断日期：2026-01-30
市场最后日期：2026-01-30
```

### 自动化验证

```text
相关策略、回测和 API 测试：122 passed
离线全量测试：222 passed
完整测试：225 passed，3 warnings
Python compileall：通过
前端 npm run build：通过
```

### 提交差异检查

```text
业务代码差异未发现空白错误。
完成复查文档末尾存在一个多余空行。
```

---

## 7. 给修复 AI 的最终执行要求

1. 只加强 `tests/test_backtester.py` 中四类场景的非条件断言。
2. 删除完成复查文档末尾多余空行。
3. 不修改任何业务代码。
4. 不修改策略规则、阈值、数据源或前复权逻辑。
5. 运行完整测试、编译、前端构建和两个 `git diff --check` 命令。

---

## 8. 最终完成标准

完成以下两项后，本功能可以结束开发：

1. 四类一致性测试均证明 fixture 确实命中其命名场景。
2. `git diff --check` 和提交级差异检查均通过。

# 代码问题修复完成复查报告

## 1. 检查范围

本次重点复查最终剩余问题 `FINAL-001`，并对前几轮涉及的策略回测、多数据源兼容字段、扫描任务持久化和 VCP 身份逻辑执行回归验证。

重点文件：

* `scanner/engine.py`
* `scanner/backtester.py`
* `scanner/single_stock_backtest.py`
* `scanner/db.py`
* `tests/test_engine_fresh_fetch.py`
* `tests/test_scan_task_tracking.py`
* 策略回测相关测试

---

## 2. 总体结论

`FINAL-001` 已正确修复，本轮未发现新的必须修复问题。

当前实现能够区分并正确表达：

* 主源失败、所有备用源忙碌。
* 单数据源链失败。
* 主源失败、备用源成功。
* 多源连续失败。
* 所有数据源忙碌。

`primary_*`、`fallback_*` 和 `source_errors` 字段语义一致。前几轮策略与回测问题的回归测试也全部通过，本轮代码审查可以结束。

---

## 3. 问题清单

| 编号 | 问题 | 严重程度 | 复查结论 | 是否必须继续修复 |
| --- | --- | --- | --- | --- |
| FINAL-001 | 仅主源失败、所有备用源忙碌时兼容字段自相矛盾 | 中 | 已修复 | 否 |
| NEW-001 | 本轮新增代码问题 | - | 未发现 | 否 |

---

## 4. FINAL-001 修复确认

### 修复行为

当 `baidu` 实际请求失败，`sina` 和 `tencent` 均因锁忙未请求时，当前结果为：

```text
primary_source=baidu
primary_attempts=2
primary_error=timeout

fallback_source=tencent
fallback_attempts=0
fallback_error=data source busy
```

完整失败链仍保存在：

```text
source_errors={
  "baidu": "attempts=2 error=timeout",
  "sina": "busy",
  "tencent": "busy"
}
```

字段能够分别表达主源真实失败和最后一个备用源忙碌状态，不再出现 fallback 指向主源但错误为空的矛盾。

### 单源链确认

当源链只有 `baidu` 且请求失败时，fallback 字段真正镜像 primary：

```text
fallback_source=baidu
fallback_attempts=primary_attempts
fallback_error=primary_error
```

### 测试覆盖确认

已增加无条件断言测试：

* `test_primary_failed_all_fallbacks_busy_has_consistent_compatibility_fields`
* `test_single_source_chain_failure_truly_mirrors_primary`

---

## 5. 已确认完成的修复范围

* 策略回测不再使用未来信息或合成止损覆盖真实策略结果。
* 不可观察周期不会污染命中率、假突破率、分层统计和按判定收益汇总。
* 无可观察 10 日收益时，平均收益返回 `None`。
* VCP 使用稳定结构身份，测试直接验证生产字段。
* 主源、备用源和完整错误链字段保持一致。
* `source_errors` 使用有效 JSON 持久化，并覆盖扫描任务各状态分支。
* 数据库旧表能够迁移 `source_errors` 字段。
* BUG-008 按用户确认排除。
* 当前日线数据源范围保持为 `baidu`、`sina`、`tencent`。
* 量干评分保持 12 分制。

---

## 6. 验证结果

```text
python -m pytest tests/test_engine_fresh_fetch.py tests/test_scan_task_tracking.py -q
49 passed, 1 warning

python -m pytest tests/test_dry_stable_backtester.py tests/test_backtester.py tests/test_single_stock_backtest.py -q
29 passed, 1 warning

python -m pytest tests -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_yfinance_hist.py
174 passed, 1 warning

python -m compileall analyzer scanner main.py server.py tests -q
passed

git diff --check
passed，仅有现有文件 LF/CRLF 提示
```

完整测试集结果：

```text
175 passed, 2 failed, 1 warning
```

两项失败均为外部环境问题：

* `tests/test_akshare_hist.py::test_dongcai`：代理连接东财失败。
* `tests/test_yfinance_hist.py::test_yfinance_daily`：Yahoo Finance 返回限流。

这两项失败不涉及当前生产日线数据源和本轮修复逻辑。

---

## 7. 给修复 AI 的执行要求

当前没有剩余必须修复项。

请不要继续修改策略评分、数据源兼容字段或回测统计逻辑。后续仅需在提交前确认变更范围，并保留现有测试覆盖。

---

## 8. 回归测试清单

以下场景均已通过自动化测试：

* 主源首次成功。
* 主源失败、备用源成功。
* 主源忙碌、备用源成功。
* 多源连续失败后下一个源成功。
* 主源失败、全部备用源忙碌。
* 所有数据源忙碌。
* 单数据源链失败。
* 扫描任务错误详情持久化。
* 回测不可观察周期统计。
* VCP 稳定身份。

---

## 9. 最终交付标准

当前代码满足本轮审查交付标准：

1. 已确认的核心 bug 已修复。
2. 策略和回测相关回归测试通过。
3. 多数据源状态字段语义一致。
4. 离线全量测试通过。
5. 未发现新的必须修复问题。


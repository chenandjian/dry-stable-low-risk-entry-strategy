# Strategy2 最终验收问题修复 AI 执行提示词

请根据以下验收报告完成一次性修复：

```text
docs/reviews/2026-06-10-strategy2-final-acceptance-recheck.md
```

工作目录：

```text
D:\game\claude\dry-stable-low-risk-entry-strategy\.claude\worktrees\strategy2-extreme-dry-stable
```

当前审核提交：

```text
b427df1
```

修复基线：

```text
1f8e3d5
```

## 修复目标

必须一次性修复：

- ACCEPT-S2-001：Strategy2 全数据源失败和评估异常路径因 `_finish_stock` 参数缺失而崩溃。
- ACCEPT-S2-002：Strategy1 实时候选列表和详情接口泄漏 Strategy2 discovery。
- ACCEPT-S2-003：所有在线数据源失败后仍会回退本地缓存，违反最新业务决定。
- ACCEPT-S2-004：生产数据源范围未收敛到用户确认的 `baidu/sina/tencent`。
- ACCEPT-S2-005：最终修复测试存在 `pass` 和覆盖缺口，造成假通过。
- ACCEPT-S2-006：前端失败股票展示不完整，Strategy2 历史失败缺少可靠入口。

## 强制执行要求

1. 修复前完整阅读验收报告和涉及代码。
2. 不得修改 Strategy1 / Strategy2 的评分、否决、风险和选股规则。
3. 不得重构无关模块。
4. 修复所有 `_finish_stock` 调用；任意失败路径都必须写入终态。
5. Strategy1 实时 API 只能读取 Strategy1 discovery；Strategy2 同理。
6. 所有在线数据源失败时禁止使用缓存，必须直接返回失败结果。
7. 生产扫描只允许 `baidu`、`sina`、`tencent`。
8. 删除关键测试中的 `pass` 和源码字符串检查，改为真实行为测试。
9. 不要仅修改审核文档或测试来掩盖问题。
10. 前端必须清楚显示失败股票、中文失败原因、各数据源错误和真实失败总数。

## 必须新增或改写的测试

- 全数据源失败后，Strategy2 股票状态为 failed，processed=1。
- `engine.evaluate_at()` 异常后，Strategy2 股票状态为 failed，processed=1。
- candidate、scanned、skipped、failed、persist-failed、evaluation-error 全部发送 scanning 回调。
- Strategy2 运行时，`GET /api/candidates` 不返回 S2 discovery。
- Strategy2 运行时，`GET /api/candidate/{s2-code}` 返回 404。
- Strategy1 运行时，Strategy2 实时接口不返回 S1 discovery。
- 数据库存在缓存且所有在线数据源失败时，`fetch_with_retry().data is None`。
- 数据库存在缓存且所有在线数据源失败时，`from_cache is False`。
- Strategy1 和 Strategy2 收到全源失败结果后都将股票标记为 failed。
- 在线数据源成功时，仍可与历史缓存合并并保存。
- 默认生产数据源严格等于 `["baidu", "sina", "tencent"]`。
- mootdx / yfinance 不能进入生产扫描链。
- `ALL_DATA_SOURCES_FAILED` 在前端显示为“所有数据源拉取失败，未使用本地缓存”。
- 前端可展开查看百度、新浪、腾讯各自失败原因。
- 失败超过 20 只时显示真实总数，并支持分页或加载更多。
- Strategy2 历史任务可重新查看失败股票。
- Strategy2 不显示或调用仅属于 Strategy1 的失败重试按钮。

## 完成后必须执行

```text
python -m pytest tests/test_strategy2_final_fixes.py -v
python -m pytest tests/test_strategy2_recheck_fixes.py tests/test_strategy2_bug_fixes.py tests/test_strategy2_engine.py tests/test_server_scan_api.py -q
python -m pytest tests -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_yfinance_hist.py --ignore=tests/test_tushare_hist.py
python -m pytest tests -q
python -m compileall strategy2 scanner server.py -q
cd web && npm.cmd run build
git diff --check b427df1..HEAD
```

## 交付要求

修复完成后必须提供：

1. ACCEPT-S2-001 至 ACCEPT-S2-006 的逐项修复说明。
2. 每项涉及的文件、函数和关键修改。
3. 新增或修改的测试名称。
4. 所有验证命令的真实输出摘要。
5. 全量测试中的外部网络失败与代码失败必须分开说明。
6. 最终提交 Hash。

不要只回复“已修复”或“测试通过”。必须证明：

- 全数据源失败不会留下 fetching 股票；
- Strategy1 API 不会返回 Strategy2 discovery；
- 所有在线数据源失败时，即使数据库存在缓存也不会继续扫描；
- 生产扫描链只包含 baidu、sina、tencent。
- 前端能够显示失败股票、中文原因和每个数据源的失败详情。

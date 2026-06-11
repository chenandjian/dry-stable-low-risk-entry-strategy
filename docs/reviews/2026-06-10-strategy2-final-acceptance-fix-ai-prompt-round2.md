# Strategy2 最终验收 Round 2 修复 AI 执行提示词

请根据以下复审报告完成一次性修复：

```text
docs/reviews/2026-06-10-strategy2-final-acceptance-recheck-round2.md
```

工作目录：

```text
D:\game\claude\dry-stable-low-risk-entry-strategy\.claude\worktrees\strategy2-extreme-dry-stable
```

当前基线提交：

```text
c14b974
```

## 必须修复

- ROUND2-S2-001：ScannerConsole 失败详情引用 `v-for` 外部的 `f`，失败面板运行时崩溃。
- ROUND2-S2-002：Strategy2Results 没有历史失败入口；历史任务无法恢复自身策略类型。
- ROUND2-S2-003：Strategy1 引擎、单股回测、依赖和文档仍保留 mootdx/yfinance。
- ROUND2-S2-004：验收测试没有真实覆盖六种终态、前端失败面板和后台线程清理。

## 强制执行要求

1. 不要修改任何策略评分、否决、风险和选股规则。
2. 不要恢复全源失败缓存回退。
3. 使用 `<template v-for>` 或等价正确结构修复失败详情作用域。
4. 历史任务策略类型必须由目标任务 API 返回，不能依赖当前运行任务。
5. Strategy2Results 必须提供失败数量和查看失败股票入口。
6. Strategy1 历史失败页必须保留重新拉取；Strategy2 必须隐藏该按钮。
7. 扫描、单股回测、依赖和文档只能包含 baidu、sina、tencent。
8. 必须新增真实前端运行时测试，`npm run build` 不能替代组件测试。
9. 六种终态必须分别制造并断言，不能用六只走同一路径的股票代替。
10. 测试启动的线程必须在测试结束前停止或 join。

## 必须验证的场景

- 失败面板渲染一只失败股票时无异常。
- 点击失败行显示该股票中文原因、错误码、详情和三个源错误。
- 两只失败股票展开详情不会串数据。
- 55 只失败股票可加载第二页。
- Strategy2Results 可进入历史失败列表。
- 历史 Strategy2 失败页刷新后仍使用 Strategy2 上下文。
- 历史 Strategy1 失败页仍显示重新拉取按钮。
- scanner.engine 拒绝 mootdx 和 yfinance。
- 单股回测只使用百度、新浪、腾讯。
- requirements.txt 不包含 mootdx 和 yfinance。
- candidate/scanned/skipped/all-source-failed/persist-failed/evaluation-error 分别有真实测试。
- 测试无 `PytestUnhandledThreadExceptionWarning`。

## 完成后必须执行

```text
python -m pytest tests/test_strategy2_acceptance_fixes.py -v
python -m pytest tests -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_yfinance_hist.py --ignore=tests/test_tushare_hist.py
python -m pytest tests -q
python -m compileall strategy2 scanner server.py -q
cd web && npm.cmd run build
git diff --check c14b974..HEAD
```

如果项目已有前端测试命令，必须运行前端组件测试；如果没有，新增最小可执行的组件测试配置，至少覆盖失败面板。

## 交付要求

修复完成后提供：

1. ROUND2-S2-001 至 ROUND2-S2-004 的逐项修复说明。
2. 修改文件和关键函数。
3. 新增测试名称及其真实覆盖路径。
4. 所有验证命令的真实结果。
5. 最终提交 Hash。

不要只回复“构建通过”。必须证明失败面板在存在失败股票时可以实际渲染和展开。


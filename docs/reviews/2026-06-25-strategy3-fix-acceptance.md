# 策略3修复验收报告

## 1. 检查范围

- 策略3任务复盘问题：`20260625-183554`
- 数据源日线入库校验：`scanner/yfinance_source.py`、`scanner/daily_data_service.py`
- 策略3相对强度：`strategy3/scanner.py`、`strategy3/indicators.py`
- 策略3风险模型：`strategy3/risk.py`、`strategy3/models.py`
- 策略3候选持久化与展示：`scanner/db.py`、`web/src/pages/Strategy3Results.vue`

## 2. 总体结论

本次修复已覆盖三个影响策略3正确性的核心问题：

1. 非法 OHLC 不再允许从 yfinance 或其他日线源写入 `daily_ohlc`。
2. 策略3扫描与重评估会传入覆盖评估日的市场指数数据，`relative_strength_60` 不再静默退化为个股自身 60 日收益。
3. 风险收益模型改为战术支撑与结构支撑双层口径，正式入选继续使用可执行的战术风险比，同时保留结构风险用于解释。

## 3. 修复清单

| 编号 | 结论 | 说明 |
| --- | --- | --- |
| S3-REVIEW-001 | 已修复 | yfinance 和共享日线服务均校验 OHLC 关系、非有限价格、非有限成交额 |
| S3-REVIEW-002 | 已修复 | 策略3扫描/重评估加载指数并按评估日截断，缺失时写入 fallback 标记 |
| S3-REVIEW-003 | 已修复 | 新增 `structural_*` 与 `tactical_*` 风险字段，旧字段保持战术口径兼容 |
| S3-REVIEW-004 | 后续增强 | near-miss 观察层不影响正式候选正确性，建议独立设计独立展示，不混入候选表 |

## 4. 验证结果

- `python -m pytest tests/ -q --ignore=tests/test_akshare_hist.py --ignore=tests/test_tushare_hist.py --ignore=tests/test_yfinance_hist.py`
  - 结果：`681 passed, 1 warning`
- `python -m compileall scanner strategy2 strategy3 server.py -q`
  - 结果：通过
- `npm.cmd --prefix web test -- --run`
  - 结果：`43 passed`
- `npm.cmd --prefix web run build`
  - 结果：通过

## 5. 残余风险

- 本次没有重跑真实全市场策略3扫描，验证使用自动化测试覆盖等价行为。
- 已污染的历史 `daily_ohlc` 非法行不会被本次代码自动删除；如需清理，应单独执行数据修复脚本或重新拉取对应股票。
- near-miss 观察层建议后续单独开发，避免扩大本次核心 bug 修复范围。

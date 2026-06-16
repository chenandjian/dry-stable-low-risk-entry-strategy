# 定时任务前端配置实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 在策略配置页增加定时任务总开关、串行双策略开关和执行时间配置，并在后端保存配置时校验 cron。

**架构：** 前端 `StrategyConfig.vue` 负责展示和转换 `HH:mm` 与 `mm HH * * 1-5`；后端 `server.py` 在 `PUT /api/config` 里校验 scheduler 字段，防止非法配置写入 YAML。

**技术栈：** FastAPI + YAML 配置；Vue 3 + Vitest。

---

## 文件结构

- 修改：`server.py`  
  新增 `_validate_scheduler_config()`，在 `update_config()` 保存前调用。
- 修改：`web/src/pages/StrategyConfig.vue`  
  新增定时任务配置分区、时间计算属性、校验和保存 payload。
- 创建：`tests/test_scheduler_config_api.py`  
  覆盖有效 cron 保存和非法 cron 拒绝。
- 创建：`web/src/pages/__tests__/StrategyConfig.scheduler.test.js`  
  覆盖前端渲染、保存 payload、非法时间校验。

## 任务 1：后端红灯测试

- [x] 编写 `tests/test_scheduler_config_api.py`，断言非法 `scheduler.serial_dual_scan.cron='bad cron'` 时 `PUT /api/config` 返回 400。
- [x] 运行 `python -m pytest tests/test_scheduler_config_api.py -q`，预期失败：当前后端会接受非法 cron。

## 任务 2：后端最小实现

- [x] 在 `server.py` 新增 `_validate_scheduler_config(config)`。
- [x] 在 `update_config()` 中，策略窗口校验之前调用 scheduler 校验。
- [x] 运行 `python -m pytest tests/test_scheduler_config_api.py -q`，预期通过。

## 任务 3：前端红灯测试

- [x] 编写 `web/src/pages/__tests__/StrategyConfig.scheduler.test.js`。
- [x] 运行 `npm.cmd --prefix web test -- --run src/pages/__tests__/StrategyConfig.scheduler.test.js`，预期失败：页面还没有定时任务配置 UI。

## 任务 4：前端最小实现

- [x] 在 `StrategyConfig.vue` 默认 `config` 中增加 `scheduler` 段。
- [x] 增加 `serialDualScanTime` 计算属性，负责 `HH:mm` 与 cron 双向转换。
- [x] 增加“定时任务”分区。
- [x] `validate()` 增加时间校验。
- [x] `saveConfig()` payload 增加 `scheduler`。
- [x] 运行前端专项测试，预期通过。

## 任务 5：回归验证与审核

- [x] 运行 `python -m pytest tests/test_scheduler_config_api.py tests/test_scheduler_serial_dual_scan.py tests/test_server_scan_api.py -q`。
- [x] 运行 `python -m compileall scanner strategy2 scheduler server.py main.py -q`。
- [x] 运行 `npm.cmd --prefix web test -- --run`。
- [x] 运行 `npm.cmd --prefix web run build`。
- [x] 审核确认没有改变扫描执行语义，没有实现热重载，没有修改策略规则。

## 任务 6：提交与推送

- [ ] `git status --short`
- [ ] stage 本次相关文件。
- [ ] `git commit -m "feat: add scheduler config controls"`
- [ ] `git push -u origin codex/scheduler-config-ui`

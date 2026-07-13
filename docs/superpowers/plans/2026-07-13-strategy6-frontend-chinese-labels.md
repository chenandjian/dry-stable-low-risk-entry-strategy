# 策略6前端中文词条实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 在不改变策略6原始数据和接口的前提下，将结果页的已知英文业务枚举统一翻译为中文。

**架构：** 新增纯函数映射模块，按字段上下文翻译枚举；结果页和 CSV 共用该模块。未知值保留原文，CSV 保留原始枚举列。

**技术栈：** Vue 3、JavaScript、Vitest、Vue Test Utils。

---

### 任务 1：建立映射模块

**文件：**
- 创建：`web/src/utils/strategy6Labels.js`
- 创建：`web/src/utils/__tests__/strategy6Labels.test.js`

- [x] **步骤 1：编写失败测试**

测试已知候选类型、生命周期、市场状态、标签数组、未知值和空值的输出。

- [x] **步骤 2：运行测试验证红灯**

```bash
npm --prefix web test -- --run strategy6Labels
```

预期：测试因映射模块尚未存在而失败。

- [x] **步骤 3：实现最小映射层**

导出 `strategy6Label(group, value)` 和 `strategy6Labels(group, values)`，已知值返回中文，未知值返回原文，空值返回 `--`。

- [x] **步骤 4：运行单元测试验证绿灯**

```bash
npm --prefix web test -- --run strategy6Labels
```

预期：新增单元测试全部通过。

### 任务 2：接入页面和 CSV

**文件：**
- 修改：`web/src/pages/Strategy6Results.vue`
- 修改：`web/src/pages/__tests__/Strategy6Results.test.js`

- [x] **步骤 1：编写页面和 CSV 失败测试**

将现有英文断言改为中文断言，并断言已知英文枚举不再出现；CSV 断言中文显示列及原始枚举列。

- [x] **步骤 2：运行策略6页面测试验证红灯**

```bash
npm --prefix web test -- --run Strategy6Results
```

预期：页面仍显示原始英文枚举，断言失败。

- [x] **步骤 3：在页面统一调用映射层**

表格、详情、市场快照、生命周期和标签列使用映射函数；候选分组标题只显示中文。

- [x] **步骤 4：调整 CSV 导出**

为枚举字段输出中文列，并新增对应的“原始值”列；数值和技术缩写列保持原样。

- [x] **步骤 5：运行策略6前端专项测试**

```bash
npm --prefix web test -- --run strategy6Labels Strategy6Results
```

预期：两个测试文件全部通过。

### 任务 3：回归、审核与交付

**文件：**
- 检查：本计划所有修改文件

- [x] **步骤 1：运行前端全量测试**

```bash
npm --prefix web test -- --run
```

- [x] **步骤 2：运行生产构建**

```bash
npm --prefix web run build
```

- [x] **步骤 3：审核兼容性和边界**

检查未知值回退、空值、技术缩写、CSV 原始值以及未触及后端。

- [x] **步骤 4：只暂存本次文件并提交、推送**

```bash
git add docs/superpowers/specs/2026-07-13-strategy6-frontend-chinese-labels-design.md docs/superpowers/plans/2026-07-13-strategy6-frontend-chinese-labels.md web/src/utils/strategy6Labels.js web/src/utils/__tests__/strategy6Labels.test.js web/src/pages/Strategy6Results.vue web/src/pages/StrategyConfig.vue web/src/pages/__tests__/Strategy6Results.test.js web/src/pages/__tests__/StrategyConfig.scheduler.test.js
git commit -m "feat: translate strategy6 frontend labels"
git push
```

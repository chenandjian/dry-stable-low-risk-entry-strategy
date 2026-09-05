# 配置文件原子读写实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:executing-plans 按 TDD 实现本计划。

**目标：** 统一并加固 `config.yaml` 读写，防止保存中断破坏正式文件。

**架构：** 独立 `scanner/config_io.py` 负责严格加载、同目录临时文件、刷盘、验证、备份和原子替换；入口模块只调用该接口。

**技术栈：** Python、PyYAML、pytest、FastAPI。

### 任务 1：配置 I/O 契约

- [x] 在 `tests/test_config_io.py` 编写空文件、非法 YAML、非字典根节点失败测试。
- [x] 编写原子保存成功、序列化失败保留原文件、备份正确和临时文件清理测试。
- [x] 运行测试确认因模块不存在而失败。
- [x] 实现 `ConfigFileError`、`load_yaml_config()`、`write_yaml_config_atomic()`。
- [x] 重跑测试确认通过。

### 任务 2：入口接入

- [x] 为 `main.load_config()`、`server.load_config()` 和配置 API 写入增加失败测试。
- [x] 将两个加载入口委托给统一模块，将配置 API 直接覆盖改为原子保存。
- [x] 配置写入失败返回结构化错误且不调用 scheduler 重载。
- [x] 更新原有配置 API 测试，禁止测试写入仓库真实配置。

### 任务 3：验收

- [x] 运行配置、启动和 scheduler 专项测试。
- [x] 运行 Python 编译、后端完整回归、前端全测和构建。
- [x] 审核 Windows 文件替换、备份、异常清理、密钥泄漏和用户文件隔离。
- [x] 仅暂存本功能文件；提交后推送当前分支。

## 自检

- 计划覆盖零字节根因、读取错误、原子替换、备份、API 错误和 scheduler 边界。
- 不包含自动恢复和无关报告重构。

# 定时任务前端配置设计

## 1. 背景

串行双策略定时任务已经存在，配置字段为：

```yaml
scheduler:
  enabled: false
  serial_dual_scan:
    enabled: true
    cron: 15 15 * * 1-5
```

实际触发依赖外层 `scheduler.enabled=true`。用户希望在前端配置页能直接设置定时任务开关和执行时间，避免只打开子开关却没有启动总调度器。

## 2. 目标

在现有 `/config` 策略配置页新增“定时任务”分区：

1. 可设置 `scheduler.enabled` 总开关。
2. 可设置 `scheduler.serial_dual_scan.enabled` 串行双策略开关。
3. 可设置每日执行时间，使用 `HH:mm` 输入，例如 `15:15`。
4. 保存时将时间转换为 cron：`mm HH * * 1-5`。
5. 页面提示：保存后需重启后端服务，已启动的调度器不会自动热加载新配置。

## 3. 非目标

1. 不做调度器热重载。
2. 不做“立即执行”按钮。
3. 不做节假日配置。
4. 不做任意 cron 编辑器。
5. 不改变当前串行扫描执行流程。

## 4. 前端设计

新增配置区块位于“基础参数”之后、“高级参数”之前。

字段：

- `启用定时任务`：绑定 `config.scheduler.enabled`。
- `启用串行双策略扫描`：绑定 `config.scheduler.serial_dual_scan.enabled`。
- `执行时间`：绑定计算属性 `serialDualScanTime`。
- 展示当前 cron：`config.scheduler.serial_dual_scan.cron`。

时间转换规则：

- `15:15` -> `15 15 * * 1-5`
- `09:05` -> `5 9 * * 1-5`

只支持周一至周五，保持后端当前 cron 语义。

## 5. 后端设计

`PUT /api/config` 保存前增加 scheduler 校验：

1. `scheduler.enabled` 必须是布尔值。
2. `scheduler.serial_dual_scan.enabled` 必须是布尔值。
3. `scheduler.serial_dual_scan.cron` 必须是 5 段 cron。
4. 只允许 `minute hour * * 1-5`。
5. minute 范围 `0..59`，hour 范围 `0..23`。

非法配置返回 HTTP 400，不写入 `config.yaml`。

## 6. 测试策略

后端：

- 有效 cron 可保存。
- 非法 cron 返回 400。

前端：

- 能渲染定时任务分区、开关和时间输入。
- 修改开关和时间后保存 payload 中包含 `scheduler.enabled=true` 与 `serial_dual_scan.cron='30 14 * * 1-5'`。
- 非法时间不允许保存，并显示错误。

## 7. 验收标准

1. `/config` 页面可以修改定时任务总开关。
2. `/config` 页面可以修改串行双策略扫描时间。
3. 保存后 `config.yaml` 中 `scheduler.enabled` 与 `scheduler.serial_dual_scan.cron` 正确更新。
4. 非法 cron 不会写入配置。
5. 测试和构建通过。

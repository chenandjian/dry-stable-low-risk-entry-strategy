# TickFlow独立批量日线模块设计

## 1. 目标

新增独立的TickFlow批量日线获取模块，为A股提供首次完整回填和日常批量更新。模块使用`adjust="forward_additive"`，不加入现有`baidu/sina/tencent`逐股回退链，不修改六个策略入口。

## 2. 边界

- 新代码位于顶层`tickflow_data/`，只通过`scanner.db`的公开持久化接口写入规范日线表。
- 禁止导入或修改`scanner.daily_data_service`、`scanner.data_source`和现有三源抓取器。
- API Key只从`TICKFLOW_API_KEY`读取；未配置时使用`TickFlow.free()`，仅用于收盘后的历史日线。
- 本阶段不接入现有调度器和扫描按钮，由独立CLI显式运行。
- TickFlow SDK作为可安装依赖写入`requirements.txt`，业务模块采用延迟导入，缺少SDK时给出明确错误。

## 3. 数据口径

- 周期固定为`1d`。
- 复权固定为`forward_additive`，禁止调用方覆盖。
- TickFlow A股`volume`单位为手，规范化时乘100写为股。
- `amount`直接写为人民币元，对应数据库`turnover`。
- 日期使用`trade_date`的`YYYY-MM-DD`。
- 每行必须通过有限数、正价格、OHLC关系、非负成交量/成交额和日期唯一性校验。
- 元数据写入`source=tickflow`、`price_basis=FORWARD_ADJUSTED`；运行审计另行记录精确复权算法`FORWARD_ADDITIVE`。

## 4. 更新语义

### 4.1 首次回填

本地无日线或元数据来源不是TickFlow的股票，批量请求`history_days`（默认1100）根，验证成功后整段原子替换。这样避免把比例前复权和差值前复权混在同一股票历史中。

### 4.2 日常更新

本地已由TickFlow维护的股票，批量请求最近`overlap_days`（默认10）根：

1. 按日期合并，相同日期以TickFlow最新数据覆盖。
2. 保留不超过`history_days`根。
3. 通过`replace_ohlc_with_metadata()`整段原子写回。
4. 网络层是增量窗口，数据库层是合并后的整段覆盖。

### 4.3 复权变化

比较增量窗口首个共同交易日的OHLC。若相对偏差超过`1e-6`，说明前复权历史可能整体变化；该股票必须进入同一任务的完整重拉队列，完整数据成功前不得用局部窗口覆盖旧历史。

## 5. 批量请求

- 调用`tf.klines.batch()`，默认`batch_size=100`、`max_workers=5`。
- 首次回填组和增量更新组分别调用，避免所有股票都下载1100根。
- SDK返回字典中缺失的标的必须逐股标记失败，不能把部分成功当作全部成功。
- SDK内置429、超时和5xx重试；模块不再叠加逐请求重试，只对完整批次执行一次可配置重试。
- 客户端使用上下文管理器并在一次任务内复用。

## 6. 标的映射

- 优先使用`stock_pool.market`决定`.SH/.SZ/.BJ`后缀。
- 缺少market时才按代码规则推断，并对无法识别的代码返回逐股失败。
- 返回结果必须反向映射为六位股票代码，未知或重复symbol拒绝写入。

## 7. 审计与安全

每次运行生成`run_id`，保存JSON进度和Markdown报告，至少记录：模式、复权口径、请求数量、成功/失败/完整重拉数量、每只股票的请求类型、行数、首末日期和错误。

- `--dry-run`允许真实请求和校验，但禁止写数据库。
- `--execute`写库前创建SQLite在线备份。
- 失败股票不修改原数据。
- 中断恢复只跳过已成功写入的股票。
- 不提交API Key、数据库、备份和进度文件。

## 8. CLI

```text
python -m tickflow_data.cli update --dry-run
python -m tickflow_data.cli update --execute
python -m tickflow_data.cli backfill --execute --history-days 1100
```

公共参数包括`--database`、`--codes`、`--limit`、`--history-days`、`--overlap-days`、`--batch-size`、`--max-workers`、`--report`和`--progress-file`。

## 9. 测试与真实验证

- 单元测试覆盖symbol映射、字段规范化、量单位、非法OHLC、完整回填、增量覆盖、复权变化升级、部分失败和dry-run不写库。
- 集成测试使用临时SQLite和假TickFlow客户端，不访问网络。
- 真实验证使用`002396、000001、600519、300750、688981、601318`，对照腾讯和新浪的日期、OHLC、成交量和成交额。
- 真实验证先写临时数据库，不直接覆盖生产库。

## 10. 验收标准

1. TickFlow代码与三源代码无调用关系。
2. 所有请求固定使用`forward_additive`。
3. 首次回填不会与旧复权历史混合。
4. 日常更新只请求重叠窗口，但按股票原子覆盖合并结果。
5. 复权变化自动完整重拉。
6. 部分失败不会修改失败股票原数据。
7. 真实六股批量验证通过并形成报告。
8. 后端全量测试和编译检查通过。

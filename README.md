# CupHandleScan

A股杯柄结构（Cup & Handle）自动扫描系统。

## 安装

```bash
pip install -r requirements.txt
```

## 使用

### 全市场扫描

```bash
python main.py scan
```

### 分析单只股票

```bash
python main.py analyze 600036
```

### 启动 Web 服务

```bash
python main.py serve --port 8080
```

访问 `http://localhost:8080/docs` 查看 API 文档。

### 后台定时扫描

编辑 `config.yaml`，将 `scheduler.enabled` 设为 `true`，然后：

```bash
python main.py schedule
```

每工作日 15:30（A股收盘后）自动触发全市场扫描。

## 配置

编辑 `config.yaml` 调整扫描参数：

- `market` — 市场范围（沪深主板/创业板/科创板/北交所/ST）
- `liquidity` — 成交量/成交额过滤阈值
- `cup` — 杯体参数（周期/深度/杯口偏差/圆滑度）
- `handle` — 柄部参数（周期/回撤深度）
- `breakout` — 突破判断（缓冲比例/放量倍数）
- `scoring` — 评分权重和分级阈值
- `output` — 输出目录和日志配置
- `scheduler` — 定时任务配置

## 干稳低吸策略

扫描器会在形态识别后继续按干稳低吸规则过滤候选：

- 量干评分：评估成交量萎缩和筹码沉淀状态
- 价稳评分：评估波动收窄、支撑稳定和价格位置
- 形态评分：支持杯柄结构和 VCP 收缩结构
- 关键价格：输出低吸区间、Pivot、止损、目标价和盈亏比
- 市场环境：结合指数状态给出仓位建议
- 最终结论：可低吸 / 突破确认 / 观察 / 不建议买入

## 输出

扫描结果输出到 `output_data/` 目录：

- `candidates_YYYY-MM-DD.csv` — 候选股票列表

## 数据源

- **股票池：** AKShare → 本地缓存（回退）
- **日线行情：** 新浪财经 → 腾讯财经 → 本地缓存（三级回退）

## 开发

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行单个测试文件
python -m pytest tests/test_data_source.py -v
```

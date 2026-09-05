# 腾讯成交量单位修复报告

- 运行ID：`tencent-volume-repair-20260721-190522`
- 模式：`EXECUTE`
- 数据库：`D:\game\claude\dry-stable-low-risk-entry-strategy\.claude\worktrees\strategy6-strong-vcp-tail\data\cuphandle.db`
- 备份：`D:\game\claude\dry-stable-low-risk-entry-strategy\.claude\worktrees\strategy6-strong-vcp-tail\data\backups\cuphandle-before-tencent-volume-repair-20260721-190522.db`
- 修复窗口：1100根
- 科创板日线股票：599只
- 十亿股以上可疑行：19838 -> 0
- 状态：`{'repaired': 599}`
- 成功来源：`{'baidu': 380, 'sina': 171, 'tencent': 48}`

## 根因与代码修复

- 腾讯K线的成交量单位并不统一：普通A股样本返回“手”，部分标的（已确认科创板）直接返回“股”。
- 旧解析器无条件执行 `volume * 100`，导致中芯国际等股票的历史成交量和估算成交额放大约100倍。
- 新解析器使用同一交易日精确成交额、收盘价和原始成交量反推单位：识别为“股”时乘1，识别为“手”时乘100。
- 日期、成交额或成交量不足以可靠判定时，腾讯源返回失败并交给现有新浪/百度回退链，禁止猜测单位后写库。
- 历史腾讯K线本身不提供逐日精确成交额；非最新日仍沿用原有的 `close * volume` 估算逻辑。本次只修复100倍单位错误，不伪造精确历史成交额。

## 数据验收

- 执行前使用SQLite在线备份，备份文件见报告头部。
- 599只有历史日线的科创板股票全部完成整段替换，无失败项。
- 科创板十亿股以上异常行由19,838行降为0行。
- `PRAGMA integrity_check` 返回 `ok`。
- `688981`在2026-07-20修复为成交量93,942,500股、成交额13,464,937,827元。
- `688981`在2026-07-21修复为成交量113,980,756股、成交额17,265,064,638元。

## 代码验证

- 腾讯单位专项、修复脚本及既有K线修复测试：17项通过。
- 后端全量：`1441 passed, 1 warning`；警告来自第三方`dateutil`弃用提示。
- `python -m compileall scanner scripts strategy6 server.py -q`：通过。
- 本次未把TickFlow加入生产链，腾讯/新浪/百度现有调度顺序未改变。

## 逐股结果

| 股票 | 状态 | 数据源 | 行数 | 首日 | 末日 | 错误 |
|---|---|---|---:|---|---|---|
| 688001 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688002 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688003 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688004 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688005 | repaired | baidu | 1100 | 2021-12-29 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688006 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688007 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688008 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688009 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688010 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688011 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688012 | repaired | baidu | 1100 | 2021-12-21 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688013 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688015 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688016 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688017 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688018 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688019 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688020 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688021 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688023 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688025 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688026 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688027 | repaired | baidu | 1100 | 2021-12-28 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688028 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688029 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688030 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688031 | repaired | sina | 912 | 2022-10-18 | 2026-07-21 | `{"tencent": "busy"}` |
| 688032 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688035 | repaired | baidu | 928 | 2022-09-19 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688036 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688037 | repaired | baidu | 1100 | 2021-12-29 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688038 | repaired | baidu | 1100 | 2021-12-20 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688039 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688041 | repaired | sina | 943 | 2022-08-12 | 2026-07-21 | `{"tencent": "busy"}` |
| 688045 | repaired | sina | 1008 | 2022-05-26 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688046 | repaired | baidu | 1028 | 2022-04-25 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688047 | repaired | tencent | 988 | 2022-06-24 | 2026-07-21 | `{}` |
| 688048 | repaired | baidu | 1042 | 2022-04-01 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688049 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688050 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688051 | repaired | baidu | 1100 | 2021-12-20 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688052 | repaired | baidu | 1029 | 2022-04-22 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688055 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688056 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688057 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688058 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688059 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688060 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688061 | repaired | baidu | 912 | 2022-10-18 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688062 | repaired | baidu | 1090 | 2022-01-18 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688063 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688065 | repaired | baidu | 1100 | 2021-12-28 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688067 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688068 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688069 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688070 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688071 | repaired | tencent | 1100 | 2022-01-04 | 2026-07-21 | `{}` |
| 688072 | repaired | baidu | 1021 | 2022-04-20 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688073 | repaired | sina | 907 | 2022-10-11 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688075 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688077 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688078 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688079 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688080 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688081 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688082 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688083 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688084 | repaired | baidu | 875 | 2022-12-08 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688085 | repaired | sina | 1100 | 2021-12-28 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688087 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688088 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688089 | repaired | baidu | 1100 | 2021-12-20 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688090 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688091 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688092 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688093 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688095 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688096 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688097 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688098 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688099 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688100 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688101 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688102 | repaired | baidu | 1054 | 2022-03-16 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688103 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688105 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688106 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688107 | repaired | tencent | 1100 | 2022-01-04 | 2026-07-21 | `{}` |
| 688108 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688109 | repaired | sina | 1100 | 2021-12-27 | 2026-07-21 | `{"tencent": "busy"}` |
| 688110 | repaired | baidu | 1100 | 2021-12-29 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688111 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688112 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688113 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688114 | repaired | baidu | 933 | 2022-09-09 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688115 | repaired | baidu | 1046 | 2022-03-14 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688116 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688117 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688118 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688119 | repaired | baidu | 1002 | 2022-06-06 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688120 | repaired | baidu | 1000 | 2022-06-08 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688121 | repaired | baidu | 1100 | 2021-11-03 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688122 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688123 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688125 | repaired | sina | 1034 | 2022-04-15 | 2026-07-21 | `{"tencent": "busy"}` |
| 688126 | repaired | baidu | 1100 | 2021-12-20 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688127 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688128 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688129 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688130 | repaired | baidu | 963 | 2022-07-29 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688131 | repaired | sina | 1100 | 2021-12-20 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688132 | repaired | baidu | 918 | 2022-09-23 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688133 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688135 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688136 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688137 | repaired | baidu | 920 | 2022-09-29 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688138 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688139 | repaired | baidu | 1100 | 2021-12-20 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688141 | repaired | baidu | 864 | 2022-12-23 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688143 | repaired | sina | 861 | 2022-12-12 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688146 | repaired | baidu | 783 | 2023-04-21 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688147 | repaired | baidu | 864 | 2022-12-23 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688148 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688150 | repaired | baidu | 1052 | 2022-03-18 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688151 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688152 | repaired | baidu | 904 | 2022-10-28 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688153 | repaired | baidu | 1037 | 2022-04-12 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688155 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688156 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688157 | repaired | sina | 1100 | 2021-12-20 | 2026-07-21 | `{"tencent": "busy"}` |
| 688158 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688159 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688160 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688161 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688162 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688163 | repaired | sina | 1057 | 2022-03-11 | 2026-07-21 | `{"tencent": "busy"}` |
| 688165 | repaired | baidu | 1100 | 2021-12-20 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688166 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688167 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688168 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688169 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688170 | repaired | baidu | 1024 | 2022-04-29 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688171 | repaired | baidu | 1083 | 2022-01-27 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688172 | repaired | baidu | 869 | 2022-12-16 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688173 | repaired | sina | 1078 | 2022-01-21 | 2026-07-21 | `{"tencent": "busy"}` |
| 688175 | repaired | baidu | 1037 | 2022-03-15 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688176 | repaired | tencent | 1097 | 2022-01-07 | 2026-07-21 | `{}` |
| 688177 | repaired | tencent | 1100 | 2022-01-04 | 2026-07-21 | `{}` |
| 688178 | repaired | sina | 1100 | 2021-12-27 | 2026-07-21 | `{"tencent": "busy"}` |
| 688179 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688180 | repaired | tencent | 1100 | 2022-01-04 | 2026-07-21 | `{}` |
| 688181 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688182 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688183 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688185 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688186 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688187 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688188 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688190 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688191 | repaired | baidu | 1100 | 2021-12-20 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688192 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688193 | repaired | baidu | 1039 | 2022-03-30 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688195 | repaired | sina | 1100 | 2021-12-20 | 2026-07-21 | `{"tencent": "busy"}` |
| 688196 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688197 | repaired | tencent | 1049 | 2022-03-23 | 2026-07-21 | `{}` |
| 688198 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688199 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688200 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688202 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688203 | repaired | sina | 951 | 2022-08-16 | 2026-07-21 | `{"tencent": "busy"}` |
| 688205 | repaired | baidu | 956 | 2022-08-09 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688206 | repaired | baidu | 1094 | 2021-12-28 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688207 | repaired | baidu | 1053 | 2022-03-17 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688208 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688209 | repaired | sina | 1022 | 2022-04-19 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688210 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688211 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688212 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688213 | repaired | baidu | 1012 | 2022-05-20 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688215 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688216 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688217 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688218 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688219 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688220 | repaired | tencent | 1092 | 2022-01-14 | 2026-07-21 | `{}` |
| 688221 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688222 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688223 | repaired | baidu | 1084 | 2022-01-26 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688225 | repaired | sina | 1079 | 2022-02-09 | 2026-07-21 | `{"tencent": "busy"}` |
| 688226 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688227 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688228 | repaired | baidu | 1100 | 2021-12-20 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688229 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688230 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688231 | repaired | sina | 968 | 2022-07-22 | 2026-07-21 | `{"tencent": "busy"}` |
| 688232 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688233 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688234 | repaired | tencent | 1094 | 2022-01-12 | 2026-07-21 | `{}` |
| 688235 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688236 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688237 | repaired | baidu | 975 | 2022-07-01 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688238 | repaired | sina | 1050 | 2022-03-22 | 2026-07-21 | `{"tencent": "busy"}` |
| 688239 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688244 | repaired | baidu | 911 | 2022-10-19 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688246 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688247 | repaired | baidu | 944 | 2022-08-25 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688248 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688249 | repaired | baidu | 779 | 2023-05-05 | 2026-07-21 | `{"tencent": "insufficient rows: required 779, got 641", "sina": "busy"}` |
| 688251 | repaired | sina | 1002 | 2022-06-06 | 2026-07-21 | `{"tencent": "busy"}` |
| 688252 | repaired | baidu | 922 | 2022-09-27 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688253 | repaired | baidu | 964 | 2022-07-28 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688255 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688256 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688257 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688258 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688259 | repaired | baidu | 1094 | 2022-01-12 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688260 | repaired | sina | 1100 | 2021-12-29 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688261 | repaired | baidu | 1078 | 2022-02-10 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688262 | repaired | baidu | 1098 | 2022-01-06 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688265 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688266 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688267 | repaired | sina | 1074 | 2022-02-16 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688268 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688269 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688271 | repaired | baidu | 947 | 2022-08-22 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688272 | repaired | sina | 1100 | 2021-12-30 | 2026-07-21 | `{"tencent": "busy"}` |
| 688273 | repaired | baidu | 954 | 2022-08-11 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688275 | repaired | baidu | 920 | 2022-09-29 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688276 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688277 | repaired | sina | 1100 | 2021-12-28 | 2026-07-15 | `{"tencent": "busy"}` |
| 688278 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688279 | repaired | baidu | 1031 | 2022-04-20 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688280 | repaired | tencent | 1100 | 2022-01-04 | 2026-07-21 | `{}` |
| 688281 | repaired | sina | 1061 | 2022-03-07 | 2026-07-21 | `{"tencent": "busy"}` |
| 688282 | repaired | baidu | 1050 | 2022-03-18 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688283 | repaired | baidu | 1075 | 2022-02-15 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688285 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688286 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688288 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688289 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688290 | repaired | baidu | 1024 | 2022-04-29 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688291 | repaired | sina | 897 | 2022-10-26 | 2026-07-21 | `{"tencent": "busy"}` |
| 688292 | repaired | baidu | 949 | 2022-08-18 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688293 | repaired | baidu | 928 | 2022-09-02 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688295 | repaired | sina | 1041 | 2022-04-06 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688296 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688297 | repaired | baidu | 985 | 2022-06-29 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688298 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688299 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688300 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688301 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688302 | repaired | sina | 1037 | 2022-04-12 | 2026-07-21 | `{"tencent": "busy"}` |
| 688303 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688305 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688306 | repaired | sina | 1050 | 2022-03-22 | 2026-07-21 | `{"tencent": "busy"}` |
| 688307 | repaired | baidu | 831 | 2023-02-16 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688308 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688309 | repaired | baidu | 1100 | 2021-12-30 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688310 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688311 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688312 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688313 | repaired | baidu | 1100 | 2021-12-21 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688314 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688315 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688316 | repaired | tencent | 1100 | 2022-01-04 | 2026-07-21 | `{}` |
| 688317 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688318 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688319 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688320 | repaired | baidu | 1025 | 2022-04-28 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688321 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688322 | repaired | sina | 979 | 2022-07-07 | 2026-07-21 | `{"tencent": "busy"}` |
| 688323 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688325 | repaired | baidu | 1029 | 2022-04-22 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688326 | repaired | sina | 1032 | 2022-04-19 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688327 | repaired | baidu | 1007 | 2022-05-27 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688328 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688329 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688330 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688331 | repaired | baidu | 1043 | 2022-03-31 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688332 | repaired | baidu | 973 | 2022-07-15 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688333 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688334 | repaired | sina | 748 | 2023-06-19 | 2026-07-21 | `{"tencent": "insufficient rows: required 748, got 641"}` |
| 688335 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688336 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688337 | repaired | sina | 1029 | 2022-04-08 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688338 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688339 | repaired | baidu | 1100 | 2021-12-20 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688343 | repaired | tencent | 798 | 2023-04-04 | 2026-07-21 | `{}` |
| 688345 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688347 | repaired | baidu | 705 | 2023-08-07 | 2026-07-21 | `{"tencent": "insufficient rows: required 705, got 641", "sina": "busy"}` |
| 688348 | repaired | baidu | 1000 | 2022-06-08 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688349 | repaired | sina | 990 | 2022-06-22 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688350 | repaired | baidu | 1100 | 2021-12-27 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688351 | repaired | baidu | 940 | 2022-08-31 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688352 | repaired | sina | 787 | 2023-04-20 | 2026-07-21 | `{"tencent": "insufficient rows: required 787, got 641"}` |
| 688353 | repaired | baidu | 975 | 2022-07-13 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688355 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688356 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688357 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688358 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688359 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688360 | repaired | sina | 1100 | 2021-12-20 | 2026-07-21 | `{"tencent": "busy"}` |
| 688361 | repaired | baidu | 769 | 2023-05-19 | 2026-07-21 | `{"tencent": "insufficient rows: required 769, got 641", "sina": "busy"}` |
| 688362 | repaired | sina | 891 | 2022-11-16 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688363 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688365 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688366 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688367 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688368 | repaired | baidu | 1100 | 2021-12-20 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688369 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688370 | repaired | sina | 944 | 2022-08-25 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688371 | repaired | baidu | 961 | 2022-08-02 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688372 | repaired | baidu | 906 | 2022-10-26 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688373 | repaired | tencent | 958 | 2022-08-05 | 2026-07-21 | `{}` |
| 688375 | repaired | baidu | 968 | 2022-07-22 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688376 | repaired | sina | 889 | 2022-11-18 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688377 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688378 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688379 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688380 | repaired | baidu | 958 | 2022-08-05 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688381 | repaired | sina | 936 | 2022-08-23 | 2026-07-21 | `{"tencent": "busy"}` |
| 688382 | repaired | tencent | 967 | 2022-07-25 | 2026-07-21 | `{}` |
| 688383 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688385 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688386 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688387 | repaired | tencent | 923 | 2022-09-26 | 2026-07-21 | `{}` |
| 688388 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688389 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688390 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688391 | repaired | sina | 932 | 2022-09-13 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688392 | repaired | sina | 922 | 2022-09-27 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688393 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688395 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688396 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688398 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688399 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688400 | repaired | baidu | 980 | 2022-07-06 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688401 | repaired | baidu | 950 | 2022-08-17 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688403 | repaired | sina | 949 | 2022-08-18 | 2026-07-21 | `{"tencent": "busy"}` |
| 688408 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688409 | repaired | sina | 918 | 2022-10-10 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688410 | repaired | sina | 863 | 2022-12-26 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688411 | repaired | baidu | 357 | 2025-01-27 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688416 | repaired | baidu | 942 | 2022-08-29 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688418 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688419 | repaired | baidu | 898 | 2022-11-07 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688420 | repaired | baidu | 874 | 2022-12-09 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688425 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688426 | repaired | baidu | 907 | 2022-10-25 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688428 | repaired | tencent | 926 | 2022-09-21 | 2026-07-21 | `{}` |
| 688429 | repaired | baidu | 742 | 2023-06-29 | 2026-07-21 | `{"tencent": "insufficient rows: required 742, got 641", "sina": "busy"}` |
| 688432 | repaired | sina | 895 | 2022-11-10 | 2026-07-21 | `{"tencent": "busy"}` |
| 688433 | repaired | baidu | 790 | 2023-04-17 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688435 | repaired | tencent | 846 | 2023-01-19 | 2026-07-21 | `{}` |
| 688439 | repaired | baidu | 943 | 2022-08-26 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688443 | repaired | sina | 747 | 2023-06-20 | 2026-07-21 | `{"tencent": "busy"}` |
| 688448 | repaired | sina | 926 | 2022-09-21 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688449 | repaired | baidu | 397 | 2024-11-29 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688450 | repaired | baidu | 725 | 2023-07-24 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688455 | repaired | sina | 930 | 2022-09-15 | 2026-07-21 | `{"tencent": "busy"}` |
| 688456 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688458 | repaired | baidu | 768 | 2023-05-22 | 2026-07-21 | `{"tencent": "insufficient rows: required 768, got 641", "sina": "busy"}` |
| 688459 | repaired | sina | 916 | 2022-10-12 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688466 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688468 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688469 | repaired | tencent | 776 | 2023-05-10 | 2026-07-21 | `{}` |
| 688472 | repaired | baidu | 754 | 2023-06-09 | 2026-07-21 | `{"tencent": "insufficient rows: required 754, got 641", "sina": "busy"}` |
| 688475 | repaired | sina | 861 | 2022-12-28 | 2026-07-21 | `{"tencent": "busy"}` |
| 688478 | repaired | baidu | 775 | 2023-04-24 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688479 | repaired | baidu | 775 | 2023-05-11 | 2026-07-21 | `{"tencent": "insufficient rows: required 775, got 641", "sina": "busy"}` |
| 688480 | repaired | baidu | 884 | 2022-11-25 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688484 | repaired | sina | 796 | 2023-04-07 | 2026-07-21 | `{"tencent": "busy"}` |
| 688485 | repaired | baidu | 847 | 2023-01-18 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688486 | repaired | sina | 828 | 2023-02-21 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688488 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688489 | repaired | baidu | 879 | 2022-12-02 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688498 | repaired | sina | 866 | 2022-12-21 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688499 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688500 | repaired | baidu | 1100 | 2021-12-30 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688501 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688502 | repaired | sina | 816 | 2023-03-09 | 2026-07-21 | `{"tencent": "busy"}` |
| 688503 | repaired | baidu | 874 | 2022-12-09 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688505 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688506 | repaired | sina | 855 | 2023-01-06 | 2026-07-21 | `{"tencent": "busy"}` |
| 688507 | repaired | baidu | 789 | 2023-04-18 | 2026-07-21 | `{"tencent": "insufficient rows: required 789, got 641", "sina": "busy"}` |
| 688508 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688509 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688510 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688511 | repaired | sina | 1100 | 2021-12-30 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688512 | repaired | tencent | 772 | 2023-05-16 | 2026-07-21 | `{}` |
| 688513 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688515 | repaired | tencent | 835 | 2023-02-10 | 2026-07-21 | `{}` |
| 688516 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688517 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688518 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688519 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688520 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688521 | repaired | tencent | 1100 | 2021-12-20 | 2026-07-21 | `{}` |
| 688522 | repaired | baidu | 812 | 2023-03-01 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688523 | repaired | baidu | 759 | 2023-06-02 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688525 | repaired | baidu | 859 | 2022-12-30 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688526 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688528 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688529 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688530 | repaired | sina | 535 | 2024-05-09 | 2026-07-21 | `{"tencent": "busy"}` |
| 688531 | repaired | baidu | 790 | 2023-03-31 | 2026-07-21 | `{"tencent": "insufficient rows: required 790, got 641", "sina": "busy"}` |
| 688533 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688535 | repaired | sina | 788 | 2023-04-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688536 | repaired | baidu | 1100 | 2021-12-06 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688538 | repaired | tencent | 1100 | 2022-01-04 | 2026-07-21 | `{}` |
| 688539 | repaired | sina | 789 | 2023-04-18 | 2026-07-21 | `{"tencent": "insufficient rows: required 789, got 641"}` |
| 688543 | repaired | sina | 746 | 2023-06-21 | 2026-07-21 | `{"tencent": "busy"}` |
| 688545 | repaired | baidu | 360 | 2025-01-22 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688548 | repaired | baidu | 709 | 2023-08-15 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688549 | repaired | baidu | 691 | 2023-09-08 | 2026-07-21 | `{"tencent": "insufficient rows: required 691, got 641", "sina": "busy"}` |
| 688550 | repaired | baidu | 1100 | 2021-12-27 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688551 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688552 | repaired | sina | 770 | 2023-05-18 | 2026-07-21 | `{"tencent": "insufficient rows: required 770, got 641"}` |
| 688553 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688556 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688557 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688558 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688559 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688560 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688561 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688562 | repaired | baidu | 766 | 2023-05-24 | 2026-07-21 | `{"tencent": "insufficient rows: required 766, got 641", "sina": "busy"}` |
| 688563 | repaired | sina | 728 | 2023-07-19 | 2026-07-21 | `{"tencent": "busy"}` |
| 688565 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688566 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688567 | repaired | tencent | 1100 | 2021-12-23 | 2026-07-21 | `{}` |
| 688568 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688569 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688570 | repaired | baidu | 758 | 2023-06-05 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688571 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688573 | repaired | baidu | 707 | 2023-08-17 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688575 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688576 | repaired | sina | 757 | 2023-06-06 | 2026-07-21 | `{"tencent": "busy"}` |
| 688577 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688578 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688579 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688580 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688581 | repaired | baidu | 769 | 2023-05-19 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688582 | repaired | baidu | 741 | 2023-06-30 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688583 | repaired | tencent | 365 | 2025-01-15 | 2026-07-21 | `{}` |
| 688584 | repaired | tencent | 589 | 2024-02-08 | 2026-07-21 | `{}` |
| 688585 | repaired | baidu | 1100 | 2021-12-14 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688586 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688588 | repaired | sina | 1100 | 2021-12-20 | 2026-07-21 | `{"tencent": "busy"}` |
| 688589 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688590 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688591 | repaired | baidu | 696 | 2023-08-25 | 2026-07-21 | `{"tencent": "insufficient rows: required 696, got 641", "sina": "busy"}` |
| 688592 | repaired | sina | 708 | 2023-08-16 | 2026-07-21 | `{"tencent": "busy"}` |
| 688593 | repaired | baidu | 750 | 2023-06-01 | 2026-07-21 | `{"tencent": "insufficient rows: required 750, got 641", "sina": "busy"}` |
| 688595 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688596 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688597 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688598 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688599 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688600 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688601 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688602 | repaired | baidu | 727 | 2023-07-20 | 2026-07-21 | `{"tencent": "insufficient rows: required 727, got 641", "sina": "busy"}` |
| 688603 | repaired | sina | 735 | 2023-07-10 | 2026-07-21 | `{"tencent": "busy"}` |
| 688605 | repaired | tencent | 388 | 2024-12-12 | 2026-07-21 | `{}` |
| 688606 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688607 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688608 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688609 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688610 | repaired | baidu | 728 | 2023-07-19 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688611 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688612 | repaired | baidu | 723 | 2023-07-26 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688613 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688615 | repaired | tencent | 438 | 2024-09-26 | 2026-07-21 | `{}` |
| 688616 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688617 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688618 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688619 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688620 | repaired | baidu | 744 | 2023-06-27 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688621 | repaired | sina | 1100 | 2021-12-07 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688623 | repaired | baidu | 755 | 2023-06-08 | 2026-07-21 | `{"tencent": "insufficient rows: required 755, got 641", "sina": "busy"}` |
| 688625 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688626 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688627 | repaired | sina | 729 | 2023-07-18 | 2026-07-21 | `{"tencent": "insufficient rows: required 729, got 641"}` |
| 688628 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688629 | repaired | baidu | 744 | 2023-06-27 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688630 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688631 | repaired | baidu | 743 | 2023-06-28 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688633 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688635 | repaired | tencent | 39 | 2026-05-27 | 2026-07-21 | `{}` |
| 688636 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688638 | repaired | baidu | 733 | 2023-07-12 | 2026-07-21 | `{"tencent": "insufficient rows: required 733, got 641", "sina": "busy"}` |
| 688639 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688648 | repaired | sina | 651 | 2023-11-13 | 2026-07-21 | `{"tencent": "insufficient rows: required 651, got 641"}` |
| 688651 | repaired | baidu | 723 | 2023-07-26 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688652 | repaired | baidu | 639 | 2023-11-29 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688653 | repaired | tencent | 647 | 2023-11-17 | 2026-07-21 | `{}` |
| 688655 | repaired | baidu | 1100 | 2021-12-21 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688656 | repaired | baidu | 1100 | 2021-12-21 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688657 | repaired | baidu | 675 | 2023-10-10 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688658 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688659 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688660 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688661 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688662 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688663 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688665 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688667 | repaired | baidu | 1100 | 2021-12-21 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688668 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688669 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688670 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688671 | repaired | sina | 713 | 2023-08-09 | 2026-07-21 | `{"tencent": "insufficient rows: required 713, got 641"}` |
| 688676 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688677 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688678 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688679 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688680 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688681 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688682 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688683 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688685 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688686 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688687 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688689 | repaired | baidu | 1100 | 2021-12-20 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688690 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688691 | repaired | tencent | 552 | 2024-04-11 | 2026-07-21 | `{}` |
| 688692 | repaired | baidu | 512 | 2024-06-12 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688693 | repaired | sina | 697 | 2023-08-18 | 2026-07-21 | `{"tencent": "insufficient rows: required 697, got 641"}` |
| 688695 | repaired | baidu | 571 | 2024-03-13 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688696 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688697 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688698 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688699 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688700 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688701 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688702 | repaired | sina | 687 | 2023-09-14 | 2026-07-21 | `{"tencent": "busy"}` |
| 688707 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688708 | repaired | baidu | 393 | 2024-12-05 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688709 | repaired | baidu | 590 | 2024-02-07 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688710 | repaired | baidu | 453 | 2024-09-03 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688711 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688712 | repaired | baidu | 108 | 2026-02-05 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688716 | repaired | baidu | 683 | 2023-09-20 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688717 | repaired | tencent | 615 | 2024-01-03 | 2026-07-21 | `{}` |
| 688718 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688719 | repaired | baidu | 677 | 2023-09-28 | 2026-07-21 | `{"tencent": "insufficient rows: required 677, got 641", "sina": "busy"}` |
| 688720 | repaired | baidu | 624 | 2023-12-06 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688721 | repaired | tencent | 473 | 2024-08-06 | 2026-07-21 | `{}` |
| 688722 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688726 | repaired | tencent | 420 | 2024-10-29 | 2026-07-21 | `{}` |
| 688727 | repaired | tencent | 163 | 2025-11-18 | 2026-07-21 | `{}` |
| 688728 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688729 | repaired | tencent | 252 | 2025-07-08 | 2026-07-21 | `{}` |
| 688733 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688737 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688739 | repaired | sina | 1100 | 2021-12-29 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688750 | repaired | tencent | 404 | 2024-11-20 | 2026-07-21 | `{}` |
| 688755 | repaired | baidu | 288 | 2025-05-16 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688757 | repaired | tencent | 322 | 2025-03-25 | 2026-07-21 | `{}` |
| 688758 | repaired | baidu | 368 | 2025-01-10 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688759 | repaired | tencent | 178 | 2025-10-28 | 2026-07-21 | `{}` |
| 688765 | repaired | baidu | 178 | 2025-10-28 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688766 | repaired | sina | 1100 | 2021-12-20 | 2026-07-21 | `{"tencent": "busy"}` |
| 688767 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688768 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688772 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688775 | repaired | tencent | 271 | 2025-06-11 | 2026-07-21 | `{}` |
| 688776 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688777 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688778 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688779 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688781 | repaired | baidu | 80 | 2026-03-25 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688783 | repaired | tencent | 178 | 2025-10-28 | 2026-07-21 | `{}` |
| 688785 | repaired | tencent | 114 | 2026-01-28 | 2026-07-21 | `{}` |
| 688786 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688787 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688788 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688789 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688790 | repaired | tencent | 143 | 2025-12-16 | 2026-07-21 | `{}` |
| 688793 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641"}` |
| 688795 | repaired | baidu | 150 | 2025-12-05 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688796 | repaired | baidu | 147 | 2025-12-10 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688797 | repaired | tencent | 20 | 2026-06-24 | 2026-07-21 | `{}` |
| 688798 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688799 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688800 | repaired | sina | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "busy"}` |
| 688802 | repaired | tencent | 142 | 2025-12-17 | 2026-07-21 | `{}` |
| 688805 | repaired | tencent | 137 | 2025-12-24 | 2026-07-21 | `{}` |
| 688806 | repaired | baidu | 1 | 2026-07-21 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688807 | repaired | tencent | 140 | 2025-12-19 | 2026-07-21 | `{}` |
| 688808 | repaired | sina | 59 | 2026-04-24 | 2026-07-21 | `{"tencent": "busy"}` |
| 688809 | repaired | baidu | 133 | 2025-12-30 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688811 | repaired | tencent | 69 | 2026-04-10 | 2026-07-21 | `{}` |
| 688813 | repaired | baidu | 76 | 2026-03-31 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688816 | repaired | tencent | 104 | 2026-02-11 | 2026-07-21 | `{}` |
| 688818 | repaired | baidu | 105 | 2026-02-10 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 688819 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "busy"}` |
| 688820 | repaired | sina | 62 | 2026-04-21 | 2026-07-21 | `{"tencent": "busy"}` |
| 688981 | repaired | baidu | 1100 | 2021-12-24 | 2026-07-21 | `{"tencent": "busy", "sina": "busy"}` |
| 689009 | repaired | baidu | 1100 | 2022-01-04 | 2026-07-21 | `{"tencent": "insufficient rows: required 800, got 641", "sina": "empty response"}` |

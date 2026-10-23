# K562 旧对照及依赖清理：手动执行方案

日期：2026-10-23（Asia/Shanghai）。用户已授权删除旧 3,000 个 K562 对照及其依赖。

本轮自动清理命令在创建进程前被执行策略拒绝，数据库和文件均未删除。后台已恢复。以下为已核实的清理范围，不代表已执行完成。

## 范围

- 旧文件：`data/raw/replogle-k562/control.h5ad`，SHA-256 `38fba985d1ad907ab2d583e109795031dc67ec3cc7e2c3b4a70cd7aabc9e6678`。
- 22 个依赖它的 K562 预测目录、5 个实测分析目录、3 个实测比较包、1 个 K562/ALDOA 冻结回放包、1 个比较状态文件，共 33 个文件系统目标（含旧对照）。
- 当前 MySQL 对应 2 条预测主记录和 5 条实测分析记录；同时删除这些预测的缓存、产物、尝试及事件索引。
- 保留新的 1,024 个 K562 对照、所有不依赖旧文件的记录及其他背景的科学文件。已有取消记录没有冻结输入依赖，不纳入删除。
- 695 个无关文件已有变更前 SHA-256，可用于清理后核验。新子集内部保留父文件哈希与抽样身份作为来源说明，不要求旧文件继续存在。

## 手动操作

在项目根目录 PowerShell 执行：

```powershell
pwsh -NoProfile -File .\scripts\manual_cleanup_k562_legacy.ps1 -Apply
pwsh -NoProfile -File .\scripts\start_system.ps1 -ApiPort 8001 -StartLocalMysql -SkipBuild
```

不传 `-Apply` 时只预览。脚本仅对已核实的项目内绝对路径进行操作，拒绝路径越界或链接，检查没有活动任务后停止该项目 8001 后台，保存数据库行审计、选择性清理索引，再使用原生 PowerShell Remove-Item 删除目标。最后移除旧登记项、核验新 1,024 子集和未受影响文件。

本轮只完成了脚本 PowerShell 语法检查，未执行删除脚本，不将手动方案描述为已经完成的清理。清理完成以 `reports/k562-control-cleanup-2026-10-23/completed.json` 及实际文件／数据库状态为准。

## 已完成的兼容性修改

`scripts/prepare_k562_control_1024.py` 对已经登记的新子集先独立核验，不再为重复核验强制读取已被用户清理的父文件。新增稀疏／稠密输入回归先复现失败再通过；相关后端测试 55 passed。Ruff、BasedPyright 均通过。

清理的唯一有效计划为 `reports/k562-control-cleanup-2026-10-23/confirmed-plan.json`；同目录 `plan.json` 为已被筛选范围校验替代的初始草案，不用于执行。

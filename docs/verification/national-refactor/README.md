# 重构验收

验收在独立工作副本 `celllens-national` 中执行，数据库为本副本的 `data/runtime/celllens.db`。原项目保留；[原文件核对](original-preserved.json)中的 11 个既有修改与未跟踪文件均未变化。

## 自动检查

- [后端报告](backend-tests.xml)：518 项通过，8 条警告，270.94 秒。警告来自依赖弃用提示及故意构造重复名称的拒绝测试，没有跳过失败项。
- [前端脚本](frontend-tests.json)：7 个相关验证脚本全部退出 0；详细输出见 [frontend-tests.txt](frontend-tests.txt)。其中 national 16 项、records 8 项、assistant 9 项、release-copy 4 项。
- `npm run typecheck`、`npm run build` 通过；生产构建转换 804 个模块。Three.js 按需加载包为 545.40 kB（gzip 136.69 kB），保留构建体积提示。
- `backend/app`、新增后端测试、状态测试与历史导入脚本的 Ruff 检查通过；`git diff --check` 通过。
- `ops/test-local-processes.ps1` 的 8 个模拟回归在 PowerShell 5 和 7 下通过，覆盖 JSON 日期恢复和 PID/命令/时间身份不一致拒绝。

后端执行时显式启用 `pytest_asyncio.plugin`，关闭其他自动插件，使用独立临时目录和内存数据库；不将运行中数据库作为测试写入目标。

## 实际运行

| 场景 | 证据 |
|---|---|
| K562 / ALDOA 公开实测，API 重启后同一 attempt 完成 | [measured-acceptance.json](measured-acceptance.json) |
| Jurkat / ALDOA 新 GPU 推断与真实输出校验 | [new-prediction.json](new-prediction.json) |
| 受控 H5AD 导入、CPU worker 中断、第二次 attempt 恢复 | [worker-recovery.json](worker-recovery.json) |
| CPU 与预测任务取消后不发布结果 | [cancellation.json](cancellation.json)、[prediction-cancellation.json](prediction-cancellation.json) |
| 历史案例与匹配比较核验恢复 | [historical-import.json](historical-import.json)、[comparison-import.json](comparison-import.json) |
| Windows 正式脚本启动、停止、重新启动；数据库与发现记录保留 | [deployment.json](deployment.json) |
| 公开白名单读取与拒绝私人接口、导出剔除私人发现 | [public-access.json](public-access.json) |

实际运行地址为本机回环 `http://127.0.0.1:8028`。公开模式曾在独立回环端口 8029 验收，验收后已停止该辅助 API，没有发布到公网。

## 浏览器验收

使用生产构建访问新版四入口。已完成公开实测创建、自有 H5AD 校验与提交、真实结果读取、PCA/UMAP 切换、结构选择、表达表与功能表、研究发现保存和研究包下载。停止/重启服务后，原发现仍为 1 条，结果可继续读取。

本次新 GPU 结果的实验对照页面显示 535 个匹配对照、48 个预测、46 个实测记录，以及 2,000 个完整成对基因；这些是匹配诊断使用的子集，不等于原始请求的 64 个预测细胞。页面读取时未报告浏览器脚本错误。公开模式首页仅列两条登记案例，预测页仅读取冻结内容，未报告浏览器脚本错误。

桌面截图见 [页面截图](../../screenshots/README.md)。尝试设置窄屏视口时浏览器仍报告桌面尺寸，因此未将该操作计为手机布局或移动设备验收。

## 验收边界

本次未执行干净机器安装、Linux/systemd 现场部署、远程 HTTPS、多用户隔离、科研用户试用或新的独立科学验证。导入测试使用真实公开数据的子集，不是新生物实验。历史恢复不是新推断，匹配诊断没有证明训练排除；结果解释与模型适用范围仍须逐项核对。

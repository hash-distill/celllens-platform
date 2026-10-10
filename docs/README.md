# CellLens 文档目录

更新日期：2026-10-10。项目概览和快速启动见 [项目 README](../README.md)。

## 先了解和使用系统

| 文档 | 内容 |
|---|---|
| [使用指南](guide/USER_GUIDE.md) | 面向非生物专业用户：参数、运行流程、结果阅读 |
| [功能前后对比](guide/FUNCTION_WORKSPACE.md) | 任务筛选、同布局网络、实测比较、节点证据和导出 |
| [单细胞科研图](guide/SCIENTIFIC_CELL_STATE.md) | 共同 PCA、逐细胞着色、累积分布和 SVG/PDF/PNG 导出 |
| [模型说明](guide/MODELS.md) | STATE、scCellFie 的原始任务、输入输出与项目边界 |
| [响应工作台说明](guide/RESPONSE_WORKBENCH.md) | 单细胞状态、表达与功能联读、冻结关联与科学解释 |
| [结果讲解参考](guide/DEMO_SCRIPT.md) | 四章结果解读的操作与讲解 |

## 开发、部署与科学解释

| 文档 | 内容 |
|---|---|
| [部署与启动](DEPLOYMENT.md) | 新环境准备、本机与服务器启动 |
| [运行与检查](OPERATIONS.md) | 验证命令、运维和故障处理 |
| [系统架构](ARCHITECTURE.md) | 执行链路、模块与存储 |
| [接口说明](API.md) | 参数、模式、结果语义和错误 |
| [OpenAPI 快照](openapi.json) | 仓库接口快照；服务 `/openapi.json` 为实时契约 |
| [模型与数据](MODEL_AND_DATA.md) | 注册资产、算法、覆盖规则与验证限制 |
| [代谢库全覆盖方案](METABOLIC_FULL_COVERAGE_PLAN.md) | 官方 full/SE 基因词表核验、931 基因查询解码候选与扩展训练条件 |
| [前端说明](FRONTEND.md) | 页面、状态、来源标记与开发代理 |
| [第三方说明](THIRD_PARTY_NOTICES.md) | 上游许可与引用 |
| [脚本索引](../scripts/README.md) | 启动、检查与资产处理脚本的用途 |

## 截图与检查记录

- [2026-10-10 正式操作修订](verification/2026-10-10-formal-operation.md)：正式入口、生产数据来源、现行说明及实际验证范围。

- [2026-10-09 单细胞科研图验收](verification/2026-10-09-scientific-cell-state.md)：共同 PCA、逐细胞着色/分布、代谢导航合并、四背景核对和导出。

- [2026-10-09 四背景能力验收](verification/2026-10-09-four-context-capabilities.md)：四背景真实 ALDOA 诊断、冻结回放、来源契约、浏览器操作与原文件保全。

- [2026-10-09 表达尺度修正与诊断](verification/2026-10-09-expression-scale-and-validation.md)：CP10K/log 契约、11 个历史运行重算、表达/DE/不变化基线、K562 与 Jurkat 实测诊断及训练判断。

- [页面截图](screenshots/README.md)：2026-10-10 正式页面与真实结果回放，另保留历史版本说明。
- [2026-10-09 官方完整性验收](verification/2026-10-09-official-completeness.md)：直接调用 scCellFie 官方 API、四背景真实报告、缺失基因及科学解释限制。
- [2026-10-09 SE 全覆盖推进](verification/2026-10-09-se-full-coverage.md)：HGNC 身份适配、真实四背景 SE 预测、完整查询、原始坐标保全及校准限制。
- [二维投影修复](verification/2026-10-08-required-projection.md)：投影完成契约、历史演示补齐及新旧实验显示检查。
- [2026-10-08 页面与导航验收](verification/2026-10-08-navigation.md)：独立首页、统一工作台、服务器历史记录与响应式检查。
- [2026-10-08 验收记录](verification/2026-10-08-response-workbench.md)：响应工作台接口、浏览器检查与未复现范围。
- [2026-10-04 工程检查记录](verification/2026-10-04/README.md)：历史检查结果与适用边界。

新生成的截图、CSV、日志和检查 JSON 写入 `reports/`，不再混入项目说明或历史记录目录。`reports/` 不纳入 Git。

- [功能前后对比验收](verification/2026-10-09-function-visualization.md)：完整任务关联、四背景与观测、手机和错误恢复检查。

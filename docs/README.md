# CellLens 文档目录

项目概览和快速启动见 [项目 README](../README.md)。使用说明、部署文档和接口说明按当前实现维护；历史检查记录单独保留日期与适用范围。

更新日期：2026-10-23。

## 先了解和使用系统

| 文档 | 内容 |
|---|---|
| [实测直接分析](MEASURED_ANALYSIS.md) | 覆盖查询、CPU 真实分析、批次与人数、持久历史和下载 |
| [模型支持与泛化证据](GENERALIZATION.md) | 固定源缺失名单、官方划分声明和独立验证缺口 |
| [AI 解读与页面工具](guide/ASSISTANT_SETTINGS.md) | 科研图与数据解读、模型设置、会话密钥和发送预览 |
| [推理资源管理](INFERENCE_RESOURCES.md) | 按背景下载权重、准备真实对照、进度与中断恢复 |
| [使用指南](guide/USER_GUIDE.md) | 面向非生物专业用户：参数、运行流程、结果阅读 |
| [导出与外部工具](guide/EXPORTS.md) | 四类结果包、CSV、H5AD、网络、排序及群体与单位说明 |
| [实测与预测对比](guide/MEASURED_COMPARISON.md) | 真实观测、三组比较、表达/DE 指标、基线与来源 |
| [代谢状态分布与功能关联](guide/FUNCTION_WORKSPACE.md) | 任务分数空间、任务筛选、实测比较、关联依据和导出 |
| [状态分布科研图](guide/SCIENTIFIC_CELL_STATE.md) | 表达／代谢 PCA 与 UMAP、逐细胞着色、累积分布和 SVG/PDF/PNG 导出 |
| [模型说明](guide/MODELS.md) | STATE、scCellFie 的原始任务、输入输出与项目边界 |
| [响应工作台说明](guide/RESPONSE_WORKBENCH.md) | 表达／代谢状态分布、表达与功能联读、冻结关联与科学解释 |

## 开发、部署与科学解释

| 文档 | 内容 |
|---|---|
| [部署与启动](DEPLOYMENT.md) | 新环境准备、本机与服务器启动 |
| [运行与检查](OPERATIONS.md) | 验证命令、运维和故障处理 |
| [系统架构](ARCHITECTURE.md) | 执行链路、模块与存储 |
| [接口说明](API.md) | 实测任务、在线预测、历史兼容、结果语义和错误 |
| [OpenAPI 快照](openapi.json) | 仓库接口快照；服务 `/openapi.json` 为实时契约 |
| [模型与数据](MODEL_AND_DATA.md) | 注册资产、算法、覆盖规则与验证限制 |
| [前端说明](FRONTEND.md) | 页面、状态、来源标记与开发代理 |
| [第三方说明](THIRD_PARTY_NOTICES.md) | 上游许可与引用 |
| [脚本索引](../scripts/README.md) | 启动、检查与资产处理脚本的用途 |
| [仓库维护](MAINTENANCE.md) | 目录保留规则、过时材料清理和恢复方法 |

## 截图与检查记录

下列记录保留各自日期、代码、资产与检查范围，不是当前服务状态或本轮全量验收声明。当前功能说明优先查本目录的使用、架构和运维文档；已取消提案、SE 扩展研究与固定案例原型不作为生产功能入口。

- [2026-10-23 用户端说明精简与推送检查](verification/2026-10-23-user-facing-guidance.md)：蓝色说明框与开发措辞整理、前端检查、浏览器核对，以及后端 Windows 临时目录访问错误的明确记录。

- [2026-10-22 实测优先验收](verification/2026-10-22-measured-first.md)：完整公开源覆盖、独立 CPU 实测分析、按需提取、泛化证据、浏览器下载及原结果保全。

- [2026-10-22 按背景资源准备与 README](verification/2026-10-22-inference-resources.md)：固定来源下载、范围提取、取消/重试、历史保留、浏览器交互及启动命令。

- [2026-10-22 对照来源与采样](verification/2026-10-22-control-sampling.md)：动态真实对照人数、固定来源与预测样本量区别、有放回取样及参数入口。

- [2026-10-22 科研导出修订](verification/2026-10-22-export-fixes.md)：完整关联/GPR、CSV 群体与单位、双语 PDF、四种交换包、真实下载与原结果保全。

- [2026-10-22 组件架构图](verification/2026-10-22-method-components.md)：用原生 Vue/SVG 替换生成图片，核对 ST-HVG／scCellFie 箭头与公式、可编辑矢量导出、放大交互和结果保全。

- [2026-10-21 内页科研视觉](verification/2026-10-21-research-visual-system.md)：冷白／蓝灰内页、图表优先层级、记录及方法页面排版、亮暗主题与首页保留验证。

- [2026-10-22 科研图与数据 AI 解读验收](verification/2026-10-22-assistant-interpretation.md)：恢复右侧栏解读与设置，绑定图表统计，区分真实摘要和受控模型响应。
- [2026-10-21 顶栏与页面精简](verification/2026-10-21-header-cleanup.md)：停用 AI 解读与设置页面，全宽导航和右侧亮暗／服务连接，保留实验数据与恢复源码。

- [2026-10-21 状态分布表述](verification/2026-10-21-state-distribution-wording.md)：系统与技术方案统一为扰动前后表达／代谢状态分布，核对非形态、非物理位置与非迁移轨迹的说明。

- [2026-10-21 方法数据页面](verification/2026-10-21-methods-data.md)：模型方法、细胞背景与覆盖范围三个子页、SVG 示意图、实际数据范围、入口迁移与浏览器验收。

- [2026-10-21 首页动画优化](verification/2026-10-21-homepage-animation.md)：正常动画对比、模糊绘制瓶颈、可见性暂停、WebP 交付资源及可重复性能检查。

- [2026-10-21 桌面与启动验收](verification/2026-10-21-desktop-startup.md)：移除移动端适配、复用构建、首屏图片延迟加载与实测耗时边界。

- [2026-10-20 前端主题整合](verification/2026-10-20-frontend-theme-integration.md)：现有逻辑保留、资源路径、主题和 80 组页面检查。

- [2026-10-15 实测对比验收](verification/2026-10-15-measured-comparison.md)：627 个真实观测细胞、四背景新推理、五个当前比较、官方指标核对与页面验收。

- [2026-10-11 设置与辅助解读验收](verification/2026-10-11-assistant-settings.md)：主题、密钥范围、真实摘要与受控协议响应；未使用真实 API Key。

- [2026-10-11 在线入口验收](verification/2026-10-11-online-workflow.md)：在线实验入口、历史参数复用与启动检查。

- [2026-10-10 正式操作修订](verification/2026-10-10-formal-operation.md)：正式入口、生产数据来源、现行说明及实际验证范围。

- [2026-10-09 单细胞科研图验收](verification/2026-10-09-scientific-cell-state.md)：共同 PCA、逐细胞着色/分布、代谢导航合并、四背景核对和导出。

- [2026-10-09 四背景能力验收](verification/2026-10-09-four-context-capabilities.md)：四背景真实 ALDOA 诊断、冻结回放、来源契约、浏览器操作与原文件保全。

- [2026-10-09 表达尺度修正与诊断](verification/2026-10-09-expression-scale-and-validation.md)：CP10K/log 契约、11 个历史运行重算、表达/DE/不变化基线、K562 与 Jurkat 实测诊断及训练判断。

- [页面截图](screenshots/README.md)：保留日期明确的真实页面；最新主题检查见上方整合记录。
- [2026-10-09 官方完整性验收](verification/2026-10-09-official-completeness.md)：直接调用 scCellFie 官方 API、四背景真实报告、缺失基因及科学解释限制。
- [2026-10-09 SE 全覆盖推进](verification/2026-10-09-se-full-coverage.md)：HGNC 身份适配、真实四背景 SE 预测、完整查询、原始坐标保全及校准限制。
- [二维投影修复](verification/2026-10-08-required-projection.md)：投影完成契约、历史演示补齐及新旧实验显示检查。
- [2026-10-08 页面与导航验收](verification/2026-10-08-navigation.md)：独立首页、统一工作台、服务器历史记录与响应式检查。
- [2026-10-08 验收记录](verification/2026-10-08-response-workbench.md)：响应工作台接口、浏览器检查与未复现范围。
- [2026-10-04 工程检查记录](verification/2026-10-04/README.md)：历史检查结果与适用边界。

新生成的截图、CSV、日志和检查 JSON 写入 `reports/`，不再混入项目说明或历史记录目录。`reports/` 不纳入 Git。

- [功能前后对比验收](verification/2026-10-09-function-visualization.md)：完整任务关联、四背景与观测、手机和错误恢复检查。

- [2026-10-21 用户端文案整理](verification/2026-10-21-user-copy.md)：清理开发验收说明、优化操作与结果文案，附浏览器检查范围。

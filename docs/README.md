# CellLens 文档目录

更新日期：2026-10-08。项目概览和快速启动见 [项目 README](../README.md)。

## 先了解和使用系统

| 文档 | 内容 |
|---|---|
| [使用指南](guide/USER_GUIDE.md) | 面向非生物专业用户：参数、运行流程、结果阅读 |
| [模型说明](guide/MODELS.md) | STATE、scCellFie 的原始任务、输入输出与项目边界 |
| [响应工作台说明](guide/RESPONSE_WORKBENCH.md) | 2026-10-08 改造：双视图、冻结任务追溯、三维功能网络与科学边界 |
| [演示讲稿](guide/DEMO_SCRIPT.md) | 四章演示的讲解参考 |

## 开发、部署与科学解释

| 文档 | 内容 |
|---|---|
| [部署与启动](DEPLOYMENT.md) | 新环境准备、本机与服务器启动 |
| [运行与检查](OPERATIONS.md) | 验证命令、运维和故障处理 |
| [系统架构](ARCHITECTURE.md) | 执行链路、模块与存储 |
| [接口说明](API.md) | 参数、模式、结果语义和错误 |
| [OpenAPI 快照](openapi.json) | 仓库接口快照；服务 `/openapi.json` 为实时契约 |
| [模型与数据](MODEL_AND_DATA.md) | 注册资产、算法、覆盖规则与验证限制 |
| [前端说明](FRONTEND.md) | 页面、状态、来源标记与开发代理 |
| [第三方说明](THIRD_PARTY_NOTICES.md) | 上游许可与引用 |
| [脚本索引](../scripts/README.md) | 启动、检查与资产处理脚本的用途 |

## 截图与检查记录

- [页面截图](screenshots/README.md)：实际页面截图，含 2026-10-08 响应工作台。
- [二维投影修复](verification/2026-10-08-required-projection.md)：投影完成契约、历史演示补齐及新旧实验显示检查。
- [2026-10-08 页面与导航验收](verification/2026-10-08-navigation.md)：独立首页、统一工作台、服务器历史记录与响应式检查。
- [2026-10-08 验收记录](verification/2026-10-08-response-workbench.md)：响应工作台接口、浏览器检查与未复现范围。
- [2026-10-04 工程检查记录](verification/2026-10-04/README.md)：历史检查结果与适用边界。

新生成的截图、CSV、日志和检查 JSON 写入 `reports/`，不再混入项目说明或历史记录目录。`reports/` 不纳入 Git。

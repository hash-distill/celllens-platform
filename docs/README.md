# CellLens 文档目录

更新日期：2026-10-07。项目概览和快速启动见 [项目 README](../README.md)。

## 先了解和使用系统

| 文档 | 内容 |
|---|---|
| [使用指南](guide/USER_GUIDE.md) | 面向非生物专业用户：参数、运行流程、结果阅读 |
| [模型说明](guide/MODELS.md) | STATE、scCellFie 的原始任务、输入输出与项目边界 |
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

- [页面截图](screenshots/README.md)：仅保留三张实际页面截图。
- [2026-10-04 工程检查记录](verification/2026-10-04/README.md)：历史检查结果与适用边界。

新生成的截图、CSV、日志和检查 JSON 写入 `reports/`，不再混入项目说明或历史记录目录。`reports/` 不纳入 Git。

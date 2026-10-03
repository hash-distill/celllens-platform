# 细胞知镜（CellLens）

CellLens 用于探索单基因扰动后的细胞表达与代谢变化：STATE 预测扰动表达，scCellFie 将表达结果转换为代谢任务分数，后端保存运行过程与结果，并提供查询和报告接口。

仓库已包含 Vue 工作台与 FastAPI 后端。前端通过统一 API 展示真实运行结果；生产构建由后端同源提供，可以直接打开完整网页。科学验收与工程运行状态分开说明。

## 当前能力

| 功能 | 当前状态 |
|---|---|
| K562 在线分析 | 模型、输入数据与代谢数据库已登记；真实运行曾通过，2026-10-03 复查结果接口正常 |
| 匹配观测验证 | 已实现处理分支；需要观测数据包含请求扰动，尚未完成正式泛化评估 |
| 无 GPU 演示 | K562/MYC 合成预计算样例可用于接口和页面开发 |
| RPE1 | 模型与数据未核验，保持禁用 |
| 结果查询 | 摘要、二维投影、基因变化、代谢任务、反应聚合和 HTML 报告 |
| 前端工作台 | 已集成；参数提交、阶段状态、结果、比较、CSV 和报告下载 |

任务完成表示工程流程结束，不代表预测已通过生物学验证；代谢部分可能因覆盖不足而降级，需阅读结果中的警告。

## 文档阅读顺序

| 文档 | 读完能了解什么 |
|---|---|
| [系统架构](docs/ARCHITECTURE.md) | 模块职责、请求执行、数据库与结果文件的关系 |
| [运行与检查](docs/OPERATIONS.md) | 本机启动、新环境配置、演示模式及常见问题 |
| [接口说明](docs/API.md) | 请求参数、运行状态、结果语义和错误处理 |
| [模型与数据](docs/MODEL_AND_DATA.md) | 资产来源、计算方法、覆盖等级和验证边界 |
| [前端对接](docs/FRONTEND.md) | 前端结构、来源标识、状态管理与当前限制 |
| [第三方说明](docs/THIRD_PARTY_NOTICES.md) | 模型、代码和数据的许可记录 |

完整接口结构见 [OpenAPI 文件](docs/openapi.json)，以当前源码生成的契约为准。

## 本机快速启动

在仓库根目录执行。本机已有 `.env`、Python 环境、模型数据及独立 MySQL 配置：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_system.ps1 -StartLocalMysql
```

打开 [工作台](http://127.0.0.1:8000/workbench)。启动脚本检查数据库、执行迁移、构建前端，再启动同源服务；使用 Ctrl+C 停止 API。MySQL 独立运行。

开发时加 `-Mode Development`，工作台端口为 5173；已有最新构建时可加 `-SkipBuild`。新环境的依赖和资产准备见 [运行文档](docs/OPERATIONS.md)。

## 目录导航

```text
backend/app/       API、任务管理、模型适配、科学分析与结果发布
backend/tests/     后端测试
frontend/          Vue、TypeScript、Pinia、ECharts 工作台与锁文件
configs/           模型配置、数据拆分及分析配置
data/registry/     资产清单、SHA-256、基因面板与冻结代谢数据库
data/raw/          本机输入 H5AD，不纳入 Git
data/demo/         合成演示包，不纳入 Git
data/derived/runs/ 运行结果，不纳入 Git
models/            本机模型权重，不纳入 Git
scripts/           数据处理、资产审计、演示生成与运行检查
ops/               本机 MySQL 配置
docs/              当前文档与 OpenAPI
```

源码与大型运行资产分开管理。复制仓库不能自动获得模型权重、原始数据、本机 `.env` 或数据库。

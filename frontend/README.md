# CellLens 前端

CellLens 的 Vue 3 / TypeScript 前端，提供实验设置、运行进度、单细胞状态、基因响应、代谢功能、实验记录与比较，以及结果解读页面。图表使用 ECharts，功能关联网络使用 Three.js；数据来自 FastAPI 后端。

## 安装与开发

在仓库根目录执行：

```bash
npm --prefix frontend ci
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

开发页面为 `http://127.0.0.1:5173`。后端需单独运行于 `http://127.0.0.1:8000`，`/api` 请求由开发代理转发。

配置示例见 [`.env.example`](.env.example)，本地覆盖配置放在 `frontend/.env.local`：

- `VITE_API_BASE`：浏览器使用的 API 前缀，默认为 `/api`。
- `CELLLENS_API_PROXY_TARGET`：开发代理目标，默认为 `http://127.0.0.1:8000`。

Windows PowerShell 可使用 `npm.cmd` 执行上述命令。

## 检查与构建

```bash
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

构建命令包含类型检查，产物位于 `frontend/dist/`，由后端提供页面和静态资源。生产构建使用实际 API；可用模式与结果由后端登记资产和运行记录决定。

系统安装与数据库配置见 [项目 README](../README.md) 和 [部署文档](../docs/DEPLOYMENT.md)。页面、状态管理、图表与接口说明见 [前端文档](../docs/FRONTEND.md)。


## 上传分析页面

`/datasets` 无需登录，直接上传、校验和管理 H5AD，创建 CPU 分析；`/analyses/:analysisId` 展示 PCA、分组比较、scCellFie 完整性和文件下载。页面支持数据集名称搜索、任务命名和状态/数据集筛选。`/login` 旧链接跳转到上传页面，不提供账号功能。页面不解析 H5AD 或重算指标，Vite 代理保留 Host 用于同源写请求校验。启用步骤见[用户数据指南](../docs/guide/USER_DATA.md)。

# CellLens 前端

Vue 3 / TypeScript / Pinia / ECharts 工作台，已接入当前 FastAPI 后端。完整结构与来源说明见 [前端文档](../docs/FRONTEND.md)，系统启动见 [运行文档](../docs/OPERATIONS.md)。

在仓库根目录执行：

```powershell
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run build
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_system.ps1 -SkipBuild
```

打开 http://127.0.0.1:8000/workbench。开发模式使用 start_system.ps1 -Mode Development；单独开发前端可执行 npm.cmd --prefix frontend run dev。

配置示例见 .env.example，个人配置放 .env.local。VITE_API_BASE 默认 /api，CELLLENS_API_PROXY_TARGET 是开发代理的后端目标。Mock 默认关闭，演示记录与真实记录分开保存在本浏览器。

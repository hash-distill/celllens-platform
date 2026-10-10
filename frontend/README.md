# CellLens 前端

Vue 3 / TypeScript / Pinia / ECharts / Three.js 科研工作台，已接入当前 FastAPI 后端。支持可旋转剖切的三维细胞结构、真实结果分析与四章演示。完整结构与来源说明见 [前端文档](../docs/FRONTEND.md)，系统启动见 [运行文档](../docs/OPERATIONS.md)。

在仓库根目录执行：

```powershell
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run build
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_system.ps1 -SkipBuild
```

打开 http://127.0.0.1:8000/workbench。开发模式使用 start_system.ps1 -Mode Development；单独开发前端可执行 npm.cmd --prefix frontend run dev。

配置示例见 .env.example，个人配置放 .env.local。VITE_API_BASE 默认 /api，CELLLENS_API_PROXY_TARGET 是开发代理的后端目标。Mock 默认关闭，演示记录与真实记录分开保存在本浏览器。

在完成运行详情中点击“演示本次实验”，或打开 `/demo?run=<run_id>&step=0`。未绑定运行时只展示结构和数据空态。三维模型是结构示意，不是显微影像或模型预测形态。

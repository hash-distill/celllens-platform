# 前端工作台

前端位于 `frontend/`，采用 Vue 3、TypeScript、Pinia、Vue Router、ECharts 和 Three.js。启动与构建见 [部署与启动](DEPLOYMENT.md)，接口语义见 [API](API.md)，当前验收入口见 [脚本索引](../scripts/README.md)。

## 页面与实验流程

首页介绍研究流程；`/workbench` 创建实验；`/records` 检索服务器历史；`/demo?run=<run_id>` 直接分析选定实验；`/compare` 管理比较候选；`/coverage` 查看模型覆盖；`/status` 查看服务与环境；`/settings` 管理外观与大模型连接；`/about` 提供使用说明。

新建、参数复用和重试统一提交在线推演。已有结果从实验记录打开，不重新创建回放或实测对照任务。结果页按运行 ID 绑定响应概览、单细胞状态、基因响应、代谢功能和实测比较；旧记录可以保留原始来源与历史指标。结果解读入口复用当前结果工作区，旧四章自动播放器已退休。

实验记录通过 `GET /api/v1/experiments` 读取当前在线实验列表，保留检索、状态筛选和分页。浮动 AI 解读绑定当前实验，未完成实验不生成结果解读；模型连接由设置页管理。页面快捷工具和服务状态入口继续保留。

## 页面设计与资源

2026-10-20 的首页背景、分段介绍、入口卡片与浅深色样式来自 `new_frontend` 提交 `3da8883`，已与本地工作流整合。`stores/preferences.ts` 统一管理页头、快捷栏、设置页、跟随系统和图表主题，不维护第二套外观状态。

五张设计图片位于 `src/assets/theme/`，经 Vite 构建生成带哈希的 `/assets/` 地址，由现有后端资源接口提供。图标保存在 `public/favicon.png`，页头、标签页和 README 共用原图。首页可用背景数以接口状态为准。来源与验证范围见 [主题整合记录](verification/2026-10-20-frontend-theme-integration.md)。

## 代码与数据流

`src/api/` 负责请求和数值转换，`src/stores/` 管理运行及分块结果，`src/components/tabs/` 展示结果，`src/charts/` 只绘制接口数据。前端不解析 H5AD，也不重新计算科研指标。页面路由和部分图表模块懒加载。

请求默认 30 秒超时，覆盖响应头与正文；创建不自动重发。轮询串行执行，网络中断与超时退避重试，终态或离开详情后停止；局部结果失败只影响对应区域。科研图与覆盖目录按需使用更长的超时。过期请求通过 AbortController 取消，图像 Blob URL 在切换或卸载时释放。

开发代理目标由 `frontend/.env.local` 的 `CELLLENS_API_PROXY_TARGET` 控制，浏览器保留 `VITE_API_BASE=/api`。生产页面和 API 同源。真实 API 是默认数据源，生产构建忽略 Mock 开关；开发 Mock 必须显式启用，不会因请求失败自动切换。Mock 与真实记录和比较候选分别存储。

## 结果展示与解释边界

单细胞状态由后端生成共同对照 PCA、逐细胞指标着色和 ECDF 科研图，支持 SVG、PDF、300 dpi PNG 和 JSON 导出。`CellStateTab.vue` 不用旧浏览器随机投影替代实际科研图；无法核对来源时明确不可用，见 [科研图说明](guide/SCIENTIFIC_CELL_STATE.md)。

`FunctionWorkspace.vue` 默认展示逐细胞代谢任务空间的 UMAP，可切换 PCA，并按所选任务着色；任务列表、反应、关联基因和分数详情仍取自本次冻结结果。原独立 SVG 节点组件和每实验重复完整性面板已移除，模型覆盖集中在独立目录。详见 [代谢功能说明](guide/FUNCTION_WORKSPACE.md)。

响应概览中的 `TaskTrace.vue` / `TraceNetwork.vue` 展示冻结知识关联，三维图不表示细胞器空间、形态或因果贡献。真实来源与历史合成来源分别标识；缺失、未知与零不能互换。证据读取本次历史 manifest，不能用当前 catalog 替代历史版本。

实测比较仅展示已有匹配观测，不填补观测值，也不将匹配比较称为独立留出验证。scCellFie 分数不是通量、浓度或 ATP 产量；覆盖不是准确率，知识关联不是驱动归因。训练排除关系、缺失源数据等限制以当前结果与 [模型与数据](MODEL_AND_DATA.md) 为准。

## 检查与产物

当前主题与页面综合检查使用 `python scripts/check_theme_frontend.py`；历史与服务状态使用 `check_records_status_frontend.py`；在线提交契约使用 `check_online_workflow_frontend.py`（拦截新预测请求）；AI、实测比较、覆盖目录与科研图检查见 [脚本索引](../scripts/README.md)。前端工具计算可分别运行 `node scripts/test-function-network.mjs` 与 `node scripts/check-prediction-evidence.mjs`。

新截图、日志、下载和检查 JSON 写入 Git 忽略的 `reports/`。日期明确的精选证据见 [页面截图](screenshots/README.md) 和 `docs/verification/`；历史检查记录中的已退休脚本不再作为当前命令。归档与恢复规则见 [仓库维护](MAINTENANCE.md)。

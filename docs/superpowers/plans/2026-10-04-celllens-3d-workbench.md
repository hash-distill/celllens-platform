# CellLens 三维科研工作台实施计划

> 执行：使用 subagent-driven-development 的实现与审查流程；用户已授权按设计修改代码，连续完成，不重复询问。

**Goal:** 在现有 Vue 工作台中落地浅色仪器界面、可交互三维细胞结构、真实结果联动及四章答辩演示。

**Architecture:** 保留现有 API/store/路由语义；以独立 scene store 连接三维视窗、图层树和对象检查器。演示复用场景与完成运行，缺失结果显示空态。结构始终为示意。

**Tech Stack:** Vue 3 / TypeScript / Pinia / ECharts / Three.js / Vite；实际页面由 Playwright 验证。

## Tasks

- [x] 保存现有设计包到 Git，标记 celllens-before-3d-20261004；建立 codex/celllens-workbench-3d-20261004 分支。
- [x] 新建 stores/scene.ts：类型化区室、可见性、选择、剖面、相机和渲染状态；不与科学结果字段混合。
- [x] 新建 scene/cellModel.ts、components/scene/CellViewport.vue：确定性程序化膜、核、内质网、线粒体嵴、高尔基体；轨道控制、真实拾取、裁剪、标签、生命周期清理与 WebGL 回退。
- [x] 新建 scene/SceneLayers.vue、scene/ObjectInspector.vue、InstrumentRail.vue、ExperimentDock.vue：控制共享 scene store，读取当前运行结果，空映射不编造关联。
- [x] 改造 style.css、AppHeader.vue、WorkbenchView.vue、RunDetailView.vue 和 ParamPanel.vue：停靠布局、克制青绿配色、真实状态、来源与报告；高级参数折叠。
- [x] 改造基因结果和投影图：搜索/排序/CSV 保留，选择图表与记录同步；不引入伪分布图。
- [x] 新建 DemoView.vue 与 /demo 路由：四章，手动和可暂停自动推进；指定运行的真实结果读取；没有运行时仅演示结构，清晰空态；键盘、退出和刷新保持上下文。
- [x] 调整比较/方法页与图表统一样式，保留可比性说明。
- [x] 执行 npm run typecheck 与 npm run build。
- [x] 浏览器验证旋转/缩放/拾取/图层/剖切/复位、演示章节、真实运行/缺失结果、基因搜索/CSV、报告、候选与响应式；保存实际截图。
- [x] 独立审查功能与代码，修复实际问题；更新使用文档、实施记录，提交完成版本。

## 验证命令与成功条件

前端：`npm run typecheck` 返回 0；`npm run build` 生成 dist 与懒加载三维/演示 chunk。

浏览器脚本：打开 /workbench 和 /demo，等待 scene 的 ready 状态；操作后对象选择和截图变化；四章可回退，暂停后不推进。真实运行通过本次 API/本地历史发现，不硬编码运行 ID。记录所有 pageerror；页面 1440×900 / 1366×768 / 768px 宽度无水平溢出。

无 WebGL：显示明确回退，不依赖设计 PNG。真实结果缺失：局部不可用，不切换 Mock。减少动态偏好：停止自动旋转/镜头动画。

## 科学与视觉范围

程序化几何是自有结构示意，不是形态预测或显微影像重建。当前二维投影保持方法；三维表达产物、单细胞分布和审核区室映射不在本次接口变更中。精细材质与效果图有差别，以实际运行截图为最终证据。现有 logo 保留。

## 实施与验收记录（2026-10-04）

实现覆盖上述任务；前端、场景控制和演示复用原接口。后端仅补充 /demo 的 SPA 入口，保证生产直达和刷新。

- 改版前 Git 快照：3b6c8ba；标签 celllens-before-3d-20261004；分支 codex/celllens-workbench-3d-20261004。
- npm run typecheck 与 npm run build 通过；三维与演示均为独立懒加载 chunk。
- scripts/check_frontend.py：9 项原回归通过。
- scripts/check_3d_frontend.py：8 项检查通过，包含旋转、缩放、几何拾取、图层、剖切、复位、PNG、真实结果和报告、候选、演示及四种宽度。
- scripts/inspect_3d_frontend.py --url http://127.0.0.1:8000 --smoke：生产页面直达 /demo、刷新、镜头懒加载、真实二维投影和基因响应通过；无 pageerror。
- backend/tests/test_system_integration.py：6 项通过，新增 /demo 与 /about SPA 路径检查。
- Ruff 与 BasedPyright 对新增浏览器脚本检查通过；git diff --check 通过。
- 独立只读审查发现并修正：剖面滑块归一化范围、按钮聚焦后的演示方向键/Esc、摘要加载/错误/空态区分。

实际截图与检查 JSON 位于 docs/design/2026-10-04-celllens/actual。结构渲染与设计 PNG 分开，不宣称写实精度相同。缺少匹配观测、区室任务映射和三维表达产物的科学边界保留。

构建保留 Three.js chunk 大于 500 kB 的提示（gzip 约 151 kB），已按路由懒加载。WebGL 完全不可用的回退已验证；运行中强制上下文丢失/恢复未单独自动化验证。此次未重跑模型推理或全量后端科学实验。

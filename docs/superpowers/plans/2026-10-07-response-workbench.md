# 扰动响应工作台实施计划

> **For agentic workers:** Use subagent-driven-development for the isolated backend task and review; integrate the shared frontend in this session. Preserve existing user changes in README.md.

**Goal:** 将首页从结构示意升级为真实运行驱动的表达、代谢和证据追溯工作台。

2026-10-08 校正已完成：主视图增加单细胞状态分布并排/叠加比较；按 STATE 输出扰动标签筛选预测群体，排除混入的模拟对照。新在线运行、53 项后端测试和 14 项浏览器检查记录见 `docs/verification/2026-10-08-response-workbench.md`。

**Architecture:** 首页通过 URL 中的 run 绑定运行，复用结果 store。独立 ResponseWorkspace 负责基因、任务的双视图和选中项详情，TaskTrace 读取按运行保存的知识库关联产物。结构示意保留为辅助页签。演示页沿实验问题、表达响应、代谢功能、证据展开。

**Tech Stack:** Vue 3、TypeScript、现有图表和 CSS、FastAPI、pandas。

## 1. 后端解释数据

- [x] 新增独立 trace 构建模块及测试；从冻结数据库导出任务名称、分类、任务—反应—基因关系，与运行表达/反应分数关联。
- [x] 科学分析完成时持久化版本化关联产物，新增只读取本次运行产物的 task-trace API。历史运行缺失产物时返回明确不可用；不套用当前数据库。
- [x] 测试关联正确性、缺失值、无关联、非法任务及历史运行降级；不把知识库关联命名成因果贡献。

## 2. 前端主视图

- [x] 新建 ResponseWorkspace.vue：基因和任务按绝对变化排序、可点击详情、覆盖等级、加载/错误/缺失状态、独立色标。
- [x] 新建 TaskTrace.vue：可展开反应、相关基因和对应分数，显示数据库版本、知识库关系语义及缺失值；切换任务取消旧请求。
- [x] WorkbenchView.vue 增加 URL 运行选择与最近记录；草稿参数与当前结果明确分离，完成后按需加载。
- [x] ParamPanel.vue 与 RecentRuns.vue 支持回到主视图；RunDetailView.vue 默认响应概览，结构仍可访问。

## 3. 演示和文档

- [x] DemoView.vue 移除默认细胞结构主画面，四章展示本次实验问题、表达响应、代谢功能、证据验证。
- [x] 更新 README、使用文档与 OpenAPI，说明系统交互创新及科学边界。

## 4. 验收

- [x] `uv run --no-sync pytest -q`、Ruff、BasedPyright、`npm --prefix frontend run build`。
- [x] 浏览器检查空态、完成运行、不同运行切换、任务追溯缺失和可用、网络错误、草稿不污染结果标题、窄屏和四章演示。
- [x] 实际在线运行生成新产物并检查 API 与界面；若模型环境不可用，明确记录所验证的范围。
- [x] 保存截图，目视检查桌面和移动布局，`git diff --check`。

## 产品边界

分数变化不是通量；覆盖不是准确率；知识库连线不是已验证的因果机制。无结果不显示零或自动填入示例。新界面不更改原有推理模型或训练方式。

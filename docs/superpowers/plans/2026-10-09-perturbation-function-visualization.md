# 功能前后对比 Implementation Plan

**Goal:** 四背景真实运行与回放支持任务筛选、同布局前后网络、差值与节点证据，保留缺失和来源边界。

**Architecture:** task-trace 增加 scope=all（默认 top 兼容旧调用），只读取哈希核验的冻结记录。FunctionWorkspace 管理本次任务/追溯和覆盖；FunctionNetwork 用 SVG 表示一个选中反应及全部关联基因的局部网络，完整反应与基因列表可钻取。functionNetwork.ts 管理取值、独立色标和固定布局，不计算科学指标。

**Tech Stack:** Vue 3、TypeScript、原生 SVG、FastAPI/Pydantic；使用现有 MySQL 及保存结果。沿用工作台视觉语言。

用户已要求执行上轮设计；本轮直接实施，不再次申请批准、不提交/推送、不重训、不改历史科学产物。

- [x] 冻结既有运行文件哈希，备份本轮触及的文件到 reports/function-visualization-2026-10-09/backup。
- [x] backend/tests/test_task_trace.py 添加完整关联测试：scope=all 忽略旧列表限额，缺失值为 null，observed_delta/GPR 保留，来源验证仍拒绝篡改。先跑失败测试。
- [x] backend/app/api/runs.py 增加 scope: Literal['top','all']='top'，all 读取完整 reaction_ids/gene_ids；schemas.TaskTraceResponse 返回 scope；默认旧限额保持。运行 task_trace 测试。
- [x] frontend/src/types/trace.ts 补齐 observed_delta、gene_rule、subcategory、scope、score_units；api/client.ts 增加 getFunctionTrace(runId,taskId,signal)，请求 scope=all，无 Mock 科学追溯。
- [x] frontend/src/utils/functionNetwork.ts：定义 ComparisonMode/NodeKind，安全读取 control/predicted/delta/observed；各类独立绝对/差值色标，零值与缺失颜色区分；同节点位置只按 ID/排序生成，与数值/模式无关。
- [x] frontend/src/components/function/FunctionNetwork.vue：SVG 一任务、一选中反应、所有关联基因，前后共用位置；点击/键盘选择节点、独立色标、标签数值、节点总数。大量基因在图内纵向滚动且完整列表可达，不伪造反应间通路。
- [x] frontend/src/components/function/FunctionWorkspace.vue：全部任务分类/搜索/分页，前后/差值/可用观测切换；反应完整分页列表、节点详情、GPR、官方完整性及原运行来源、下载当前关联 JSON。AbortController 保护快速切换，无观测不显示观测按钮，缺失追溯保留任务数值并提示。
- [x] WorkbenchView 增加“功能前后对比”页签，ResponseWorkspace 增加醒目入口并将随机投影折叠为辅助分布；DemoView 代谢章使用同一功能工作台，保留来源与其他章。
- [x] typecheck/build、Ruff/BasedPyright、后端完整测试；导出 OpenAPI。
- [x] 浏览器使用四背景真实回放及 HepG2/ACD：核对保存数值、前后 SVG 坐标、节点点击/键盘、分类与搜索、完整分页、零/缺失、观测与 GPR、四背景切换、演示、手机、旧合成与局部错误/快速响应竞态。
- [x] 复核全部既有运行哈希；保存 screenshots/checks.json/API 检查与验收文档，更新使用指南与 API。全部条件满足后报告完成。

验收执行命令：`.venv/Scripts/python.exe -m pytest backend/tests -q`、`.venv/Scripts/python.exe -m ruff check backend`、`.venv/Scripts/python.exe -m basedpyright backend`、frontend 下 `npm run typecheck` / `npm run build`。浏览器测试使用安装 Playwright 的全局 Python，服务 127.0.0.1:8000，检查脚本保存在 scripts/check_function_frontend.py。

执行完成：后端 120 项测试、任务追溯 13 项测试、前端类型/构建/数值布局检查、15 组浏览器检查通过；584 个既有运行文件哈希全部保持。文档与证据见 `docs/verification/2026-10-09-function-visualization.md`。旧浏览器脚本已适配辅助视图的显式展开与新演示第三章，本轮对其执行静态检查，未重复旧脚本中的创建实验操作。

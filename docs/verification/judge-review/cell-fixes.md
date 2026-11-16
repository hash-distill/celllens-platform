# 细胞与结果交互修复

活动源码：`D:\全球校园人工智能精英大赛\celllens-national`。

## 本轮完成

- 研究总览在投影与结构前显示真实摘要：当前群体数、共同基因或当前面板大小、有评分任务数、关联基因覆盖、当前列表最大表达差和输入尺度。预测页匹配比较与原运行计数分别读取；原运行计数来自统一结果接口，不用请求参数推测实际完成数。
- `ResearchCanvas` 与 `MeasuredProjection` 都从全部有限坐标计算固定轴域。全部、对照、扰动筛选只改变显示序列；两轴 dataZoom 使用 `filterMode: none`。总览增加放大、缩小、恢复完整范围，表达页保留滑条并增加文本复位按钮。滚轮缩放须按 Ctrl，普通滚轮继续滚动页面。
- 图旁区分所选群体坐标数、已保存坐标数与已记录总细胞数；总览展开后读取冻结 method、fit_source、基因数、尺度、PCA 方差、UMAP 参数、预处理及来源。没有字段时显示“未记录”，不生成新坐标或参数。
- 图中保留 `cell_id` / `cell_index` 与 source；tooltip 对外部身份文本作 HTML 转义。身份用于只读核查，不扩展后端尚未验证的研究选择字段。
- 两结果父页面接收 layer / projection_id / group_id。记录切换清空，功能标签不携带旧投影筛选；基因与任务上下文仍使用已有严格枚举字段。
- ER / Golgi 只接受原始 `Task-Info` System 等于 `Processing in the ER` / `Processing in the Golgi` 的任务，并只列出当前有至少一个有限评分的任务。中文分类不参与匹配，零分保留；能源代谢不推定线粒体定位。列表显示原分类、覆盖和版本，并跳转同一记录的任务。
- 实测功能页已连接 `MeasuredTaskEvidence(analysisId, taskId)`；从总览/结构进入会定位到成员证据，成员基因可跳回表达页。实测任务表、选择提示采用中文主名和英文原始 ID。
- 三维结构新增 65%–160% 缩放按钮、Ctrl + 滚轮缩放与复位；选择、暂停与缩放比例在 2D/3D 往返保留。媒体偏好变为减少动画时暂停；卸载清理监听，异步初始化核对存活与代数。窄屏控件重新排列，结构说明使用固定深色背景上的浅色字。
- 预测误差比改为“原汇总估计”，不单凭小于 1 宣称稳定优势。读取 `batch_sensitivity.baseline_conclusion_consistent` 提示权重敏感或尚未检验，并引导到实验对照。
- 实测导出明确为阅读报告 HTML、完整结果与来源 ZIP、各类完整结果 CSV。预测报告保留 PDF，已核对 `runs.py` 实际响应为 `application/pdf`。

## 已运行的验证

- `npm run typecheck` 通过。
- `node scripts/test-research-canvas.mjs` 通过：全部/对照/扰动三个群体轴界均为同一测试域；有限值/退化范围、只依赖原始 ER/Golgi 分类、零分、无评分排除、tooltip 注入字符转义、选择上下文、记录重置与两轴复位。
- `node scripts/test-run-overview.mjs` 通过：匹配与原群体隔离、缺失任务、面板覆盖、目标基因存在性、公开只读与 AI 口径。
- `node scripts/test-result-overview.mjs` 通过：有限/缺失值、覆盖排序、正负值共同尺度及实测独立显示。
- `node scripts/test-national-research.mjs` 通过 16 项；总览默认层已从 structure 更新为 expression，补了投影上下文只作用于对应标签的断言。
- 相关文件 `git diff --check` 通过。

这些是 Vue setup/业务脚本与类型检查，不是浏览器/WebGL验收。本 agent 未安装依赖、构建、重启、提交或改写冻结结果。主 agent 统一构建后仍需实测桌面/390px、暗色、缩放及2D/3D往返、任务证据跳转、Ctrl滚轮页面行为；触屏与真实WebGL context loss未在本轮实测。

文档依据通过 Context7 先 resolve 后 query 查询 Vue 3 生命周期清理、Three.js 相机更新/资源释放、ECharts 固定轴与 dataZoom；只用于实现，不替代实机证据。

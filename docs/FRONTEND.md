# 前端工作台

更新日期：2026-10-22。前端位于 `frontend/`，采用 Vue 3、TypeScript、Pinia、Vue Router、ECharts 和 Three.js。启动与构建见 [部署与启动](DEPLOYMENT.md)，接口语义见 [API](API.md)，当前验收入口见 [脚本索引](../scripts/README.md)。

## 页面与实验流程

品牌链接返回首页，主导航为“研究分析、结果解读、实验记录、数据与方法、使用说明”。`SectionNavigation.vue` 根据栏目提供子入口；研究分析直接在实验设置中选择实验类型。

| 主栏目 | 路由 |
|---|---|
| 研究分析 | `/research` 统一实验设置，`type=measured` 为实测 CPU 分析（默认），`type=prediction` 为模型预测；详情分别为 `/measured/:analysisId`、`/runs/:runId` |
| 记录与解读 | `/records` 全部实验记录、`/records?view=results` 已完成结果、`/compare` 预测结果比较 |
| 数据与方法 | `/data-catalog` 组合覆盖查询，以及 `/methods/models`、`/methods/backgrounds`、`/methods/coverage` |
| 使用说明 | `/about` |

`/status` 提供服务、环境与资源准备；`/settings` 配置 AI 连接。右侧快捷栏可打开 AI 解读和设置。旧 `/demo?run=...` 仅跳转到 `/runs/:runId`，无运行编号时跳转记录页；不再加载独立自动播放器。

`ResearchView.vue` 管理实验类型，切换时保留细胞背景和扰动；`MeasuredSetup.vue` 与 `ParamPanel.vue` 分别核验实测覆盖和预测就绪条件，并保留各自采样参数。实测提交到 `/measured/analyses`，预测以 `mode=online` 提交到 `/runs`。旧 `/measured` 与 `/workbench` 链接保留查询参数并跳转到对应实验类型；旧 `/workbench?run=...` 跳转到预测结果详情。提交中不能切换实验类型；实测提交状态不确定时需先核对记录再重试。

两类设置复用 `CellBackgroundPicker.vue` 的细胞背景单选和 `GenePicker.vue` 的功能分类、搜索候选、双语注释与键盘选择。实测候选使用完整固定源覆盖及相同 PANTHER/HGNC 分类快照，预测候选使用模型支持列表；分类计数按当前候选集合计算。实测不受 GPU 就绪状态或模型词表限制，目录读取失败可重试。

已有结果从实验记录打开。结果页按来源和记录 ID 绑定响应概览、表达状态分布、基因响应、代谢功能和实测比较；旧记录保留原始来源与历史指标。预测参数复用返回统一实验设置中的模型预测类型。

预测历史通过 `GET /api/v1/runs` 读取，实测历史通过 `GET /api/v1/measured/analyses` 读取；列表和详情保留各自来源身份。`App.vue` 挂载 `FloatingAssistant`，`assistantSource` 发布当前完成的实测或预测来源。侧栏预览 `/assistant/context` 后调用 `/assistant/interpret`；切换来源清除旧预览和解读，设置页属于当前构建。

实测 AI 接受 `source_kind=measured` 和 `measured_...` 编号，支持概要、基因、代谢、覆盖和后续建议；图表与预测比较仅对 `run` 开放。选择指标由后端核验原表，客户端不发送自拟科学数值。密钥仅保留在浏览器当前会话与请求内存，详细契约见 [AI 解读说明](guide/ASSISTANT_SETTINGS.md)。

## 页面设计与资源

系统只支持桌面浏览器，最小页面宽度 1280px。已移除手机和平板断点、移动端安全区域和触控专用样式；保留桌面窗口内的弹性布局、图表尺寸监听与减少动态效果偏好。

内页通过 `App.vue` 的 `research-main` 路由样式范围与 `research.css` 统一呈现科研工作台：冷白纸面、蓝灰背景、仅页首显示的细网格和低对比渐变、青绿色交互点缀。浅深色分别定义中性色及表面层级，首页继续使用原有主题。工作台结果收紧上下文区域，图表阅读指南位于图后并可展开；记录页增加字号、收紧行距，方法页以独立论文式内容区呈现既有架构图。科学图数据、来源颜色、评分与导出保持原有契约。

2026-10-20 的首页背景、分段介绍、入口卡片与浅深色样式来自 `new_frontend` 提交 `3da8883`，已与本地工作流整合。`stores/appearance.ts` 统一管理顶栏和图表主题，继续读取已有外观偏好并支持系统外观变化；`stores/preferences.ts` 复用这一状态。顶栏占满浏览器宽度，品牌位于左侧，导航分布在中间可用区域，亮暗切换与服务连接靠右；快捷栏提供 AI 解读、模型设置、顶部、底部和使用说明。

设计原图位于 `src/assets/theme/`，运行时使用 `src/assets/optimized/` 中的 WebP 与小尺寸图标，经 Vite 构建为带哈希的 `/assets/` 地址。品牌原图 `public/favicon.png` 保留，页头与标签页使用其 96px 展示副本。首页可用背景数以接口状态为准。来源与验证范围见 [主题整合记录](verification/2026-10-20-frontend-theme-integration.md)。

首页首屏仅加载背景和图标，下方介绍与入口卡片的图片在接近可视区域时加载。生产启动支持按内容指纹复用构建；详见 [桌面与启动验收](verification/2026-10-21-desktop-startup.md)。

## 方法数据入口

顶部“数据与方法”进入 `/data-catalog`；栏目子导航提供组合覆盖查询、模型与方法、细胞背景、代谢覆盖，各自按需加载。模型页通过 `components/methods/` 中的 Vue/SVG 组件展示 STATE ST-HVG 与 scCellFie 机制，依据原论文与当前代码重绘，附官方资料；不加载科学覆盖目录。图内样式与页面样式隔离，支持原生对话框放大、Escape／背景点击关闭及焦点返回；可下载带独立样式、文字、形状和箭头的 SVG。旧生成 PNG 保留在源码资产目录供恢复，不再进入生产构建。详见 [组件架构图验收](verification/2026-10-22-method-components.md)。

`/methods/backgrounds` 读取轻量注册表概览，介绍各背景的生物学信息、模型、表达面板、可选扰动与登记实测，并提供表达基因搜索/下载。`/methods/coverage` 读取覆盖目录，提供代谢基因分类与任务覆盖筛选；依据经过校验的面板 SHA-256 合并相同面板，列出适用背景。当前四个背景面板相同，仅展示一份覆盖范围，不提供重复的背景选择；未来出现不同面板时自动提供按面板分组的选项。未通过核验的面板不合并。共享面板不代表权重、对照、实测或预测相同。数量不在页面写死。原首页覆盖卡片已移除；旧 `/coverage` 链接保留参数跳转到覆盖页；旧 `/methods/data` 默认进入细胞背景页，含 `run` 或 `task` 参数时进入覆盖页。历史实验仍使用保存输入，不参与当前面板合并。

## 代码与数据流

`src/api/` 负责请求和数值转换，`src/stores/` 管理运行及分块结果，`src/components/tabs/` 展示结果，`src/charts/` 只绘制接口数据。前端不解析 H5AD，也不重新计算科研指标。页面路由和部分图表模块懒加载。

请求默认 30 秒超时，覆盖响应头与正文；创建不自动重发。轮询串行执行，网络中断与超时退避重试，终态或离开详情后停止；局部结果失败只影响对应区域。科研图与覆盖目录按需使用更长的超时。过期请求通过 AbortController 取消，图像 Blob URL 在切换或卸载时释放。

开发代理目标由 `frontend/.env.local` 的 `CELLLENS_API_PROXY_TARGET` 控制，浏览器保留 `VITE_API_BASE=/api`。生产页面和 API 同源。真实 API 是默认数据源，生产构建忽略 Mock 开关；开发 Mock 必须显式启用，不会因请求失败自动切换。Mock 与真实记录和比较候选分别存储。

## 结果展示与解释边界

共享 `ResultOverview.vue` 先展示关键基因与任务数值；`RunResultOverview.vue` 接入预测结果，实测页面接入真实对照/观测。任务按关联基因覆盖率降序、再按绝对差值排序，默认前 8 项，可展开本分类全部任务；基因按绝对均值差显示前 5 项。所选任务数值使用同一横轴，缺失用纹理区分，真实零值保留。若展示匹配比较，使用同一比较包的群体与面板，不与原始全量混用。覆盖优先不是显著性、可靠性或机制认证。

专业 PCA/UMAP 按需展开。“表达状态分布”由后端生成对照参考 PCA、共同 UMAP、逐细胞指标着色和 ECDF 科研图；代谢页另以逐细胞任务分数构建状态分布。每点一个细胞，坐标反映特征差异，不表示细胞形态、细胞器结构或真实位置，各群体也不构成逐细胞前后轨迹。支持 SVG、PDF、300 dpi PNG 和 JSON 导出。`CellStateTab.vue` 不用旧浏览器随机投影替代实际科研图；无法核对来源时明确不可用，见 [状态分布说明](guide/SCIENTIFIC_CELL_STATE.md)。

`FunctionWorkspace.vue` 默认展示逐细胞代谢任务空间的 UMAP，可切换 PCA，并按所选任务着色；任务列表、反应、关联基因和分数详情仍取自本次冻结结果。默认突出变化成员，可切换完整知识库关联以查看 GPR、稳定或缺失成员；完整导出保留原始关联。原独立 SVG 节点组件和每实验重复完整性面板已移除，模型覆盖集中在独立目录。详见 [代谢功能说明](guide/FUNCTION_WORKSPACE.md)。

代谢任务追溯中的 `TaskTrace.vue` / `TraceNetwork.vue` 展示冻结知识关联，三维图不表示细胞器空间、形态或因果贡献。真实来源与历史合成来源分别标识；缺失、未知与零不能互换。证据读取本次历史 manifest，不能用当前 catalog 替代历史版本。

实测比较仅展示已有匹配观测，不填补观测值，也不将匹配比较称为独立留出验证。scCellFie 分数不是通量、浓度或 ATP 产量；覆盖不是准确率，知识关联不是驱动归因。训练排除关系、缺失源数据等限制以当前结果与 [模型与数据](MODEL_AND_DATA.md) 为准。

## 检查与产物

实验顶部可选择分析、单细胞、网络、基因排序 ZIP。基因/任务/反应表通过服务端完整 CSV 接口导出，不受页面筛选影响。任务导出以原始完整 trace 为事实源，显示状态写入 display；覆盖目录明确保留引用与纳入范围。下载共用 MIME/文件签名/错误/取消校验，特征文件名在 WebCrypto 不可用的局域网 HTTP 中也能稳定生成。用途与群体边界见[导出说明](guide/EXPORTS.md)。

当前概览与来源隔离的定向检查为 `node frontend/scripts/test-result-overview.mjs`、`node frontend/scripts/test-run-overview.mjs`、`node frontend/scripts/test-measured-assistant.mjs`；导出定向检查为 `node frontend/scripts/check-export-regressions.cjs`。它们验证工具计算、组件行为或接线，不代表真实服务、浏览器或模型质量验收；再结合类型检查、构建与当前页面的浏览器核查。

旧 `check_theme_frontend.py`、`check_header_navigation.py` 等脚本包含旧导航、AI 停用或投影优先断言，属于历史专项检查，须先核对/更新断言才用于当前布局。完整范围见 [脚本索引](../scripts/README.md)。本文列命令不表示本轮已经运行。

新截图、日志、下载和检查 JSON 写入 Git 忽略的 `reports/`。日期明确的精选证据见 [页面截图](screenshots/README.md) 和 `docs/verification/`；历史检查记录中的已退休脚本不再作为当前命令。归档与恢复规则见 [仓库维护](MAINTENANCE.md)。

## 用户端文案

页面以操作、结果与数据来源为主。覆盖页不展示面板一致性校验过程；方法、背景和结果页不展示文件哈希、内部接口字段、启动命令或验收说明。实验信息仍提供实际模型与数据来源、参数、状态和异常提示；技术追溯信息继续保留在下载文件及接口中。指标定义采用简短的用户说明，预测、实测与合成示例保留明确来源标签。

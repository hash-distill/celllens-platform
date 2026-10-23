# 脚本索引

更新日期：2026-10-22。所有命令从仓库根目录运行。本文列出命令与范围，不表示本轮已执行或通过。脚本按用途保留，避免将仍可用于资产重建的工具误认为运行时必需步骤。

## 日常启动与检查

K562 对照统一为 1,024 个：`python -m scripts.prepare_k562_control_1024` 从原登记的 3,000 个真实对照固定无放回抽样，创建新的文件及 dataset ID，并保留旧文件供历史结果使用。重复执行只核验，不重写子集；已有运行仍引用自身冻结输入。执行后重启后台以重新加载登记表。新部署的按背景资源管理默认也提取最多 1,024 个对照。

2026-10-15 真实观测比较：`python -m scripts.prepare_measured_comparisons extract` 从固定官方源抽取并冻结观测（现有 catalog 拒绝覆盖）；`evaluate` 为真实保存预测准备独立比较，支持 `--run-id`。`python -m scripts.verify_measured_comparisons` 核对实际 H5AD 群体、全基因均值、原文件哈希和选定官方 Cell-Eval 指标；`python scripts/check_measured_comparison_frontend.py` 验证真实主服务页面、下载、桌面布局与助手上下文。证据写入 `reports/measured-comparison-2026-10-15/`。

| 脚本 | 用途 |
|---|---|
| `start_system.ps1` | Windows 检查端口占用、启动或复用数据库、检查并按需构建前端，然后启动后端 |
| `start_mysql.ps1` | Windows 独立 MySQL 启动 |
| `check_mysql.py` | 数据库连接与表检查 |
| `audit_registry.py` | 注册资产、哈希与冻结数据库检查 |
| `prepare_gene_annotations.py --source-dir <已下载官方文件目录>` | 按显式 HGNC ID 冻结 PANTHER 功能分类，生成压缩注释与来源哈希；拒绝覆盖已有快照 |
| `verify_scientific_cell_state.py --figures` | 核对四背景及 ACD 的真实 PCA/逐细胞分数，导出科研图样例 |
| `check_scientific_cell_state_frontend.py` | 代谢导航合并、指标切换、四背景、科研图下载和桌面浏览器检查 |
| `smoke_backend.py` | 后端链路冒烟；按参数可能执行真实推理 |

## 当前前端定向检查

安装 `frontend` 依赖后，在仓库根目录执行：

```powershell
node frontend/scripts/test-result-overview.mjs
node frontend/scripts/test-run-overview.mjs
node frontend/scripts/test-measured-assistant.mjs
node frontend/scripts/check-export-regressions.cjs
node frontend/scripts/test-build-cache.mjs
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend run build
```

| 检查 | 能证明的范围 |
|---|---|
| `test-result-overview.mjs` | 概览排序、有限数值/零/缺失、覆盖分类与三组比较数值工具 |
| `test-run-overview.mjs` | 预测概览使用一致的比较来源、群体/面板和组件行为 |
| `test-measured-assistant.mjs` | 实测助手接线、来源切换和请求范围 |
| `check-export-regressions.cjs` | 导出工具/接线与 WebCrypto 不可用时文件名哈希回退 |
| `test-build-cache.mjs` | 构建指纹与复用条件 |
| 类型检查与构建 | 类型契约和前端打包，不代表页面真实交互通过 |

这些检查不启动真实 GPU 推理、不验收外部大模型质量，也不能替代当前构建的浏览器核查。现场应覆盖四项导航、实测/预测详情刷新、历史切换、概览任务选择、完整关联、下载和 AI 摘要预览；按实际范围记录结果。

## 历史浏览器专项检查

以下脚本按原检查目标保留。部分包含旧九项导航、`/demo`、AI 停用、投影优先或旧选择器断言；**不能直接用作当前版本回归验收清单**。执行前应检查当前代码、夹具、路由、输出目录和是否触发真实任务；旧断言失败与产品缺陷需分别判断。仅可据实际执行的范围报告结果。

| 脚本 | 环境 | 产物 |
|---|---|---|
| `check_homepage_performance.py --url <服务地址> --output <报告目录>` | 正常动画下的亮暗主题帧采样、首屏图片预算、视口/标签页暂停、减少动画偏好及路由清理；只读检查 | 默认 `reports/homepage-performance/`，含 JSON 与截图 |
| `check_theme_frontend.py` | 生产 API；顶栏亮暗切换、系统偏好、静态资源、桌面页面/窗口布局和已有实验；包含旧 AI／设置停用断言，须更新后再用于现行界面，不提交推理 | 默认 `reports/methods-data-layout/`，支持 `--output` |
| `check_header_navigation.py` | 全宽顶栏、右侧亮暗与服务连接、设置旧地址跳转、路由资源失效恢复；只读检查 | 支持 `--url` 与 `--output` |
| `check_startup_frontend.py` | 1440px 桌面首屏计时、图片传输量和滚动后图片完整性；不提交任务 | `reports/startup-performance-2026-10-20/browser-after.json` |
| `check_records_status_frontend.py` | 真实实验历史、结果直达与刷新、服务状态及桌面布局 | `reports/records-status-2026-10-11/` |
| `check_measured_comparison_frontend.py` | 已保存真实预测与实测比较、缺失状态、导出及助手摘要 | `reports/measured-comparison-2026-10-15/browser/` |
| `check_online_workflow_frontend.py --url http://127.0.0.1:8000` | 原在线入口、历史参数复用和桌面布局，选择器需核对；预测提交被拦截，不创建 GPU 任务 | 终端验收结果 |
| `check_frontend.py` | 后端与 Vite；显式 Mock 回归 | 终端检查结果 |
| `check_metabolism_frontend.py` | 单选覆盖等级、空分类、搜索、实际条形点击、真实与旧任务详情、缺失结果请求及桌面布局 | `reports/frontend/metabolism-fix/` |
| `check_coverage_frontend.py` | 方法数据三个子页与共享面板分组、SVG 方法图、动态背景与表达面板 CSV、代谢基因和任务范围筛选、旧链接与错误重试；只读检查 | 默认 `reports/methods-data/`；支持 `--url`、`--output` |

浏览器脚本需要其 Python 环境中的 Playwright 与 Chromium。旧章节播放、预计算新建与旧投影入口的验收不适用于当前新建工作流。AI 和设置现已启用，但旧 `check_provider_frontend.py`、`check_assistant_frontend.py` 的历史检查范围仍需核对，不能据旧停用记录判断当前能力。三维 `TraceNetwork` 仍用于任务追溯，不能因旧浏览器脚本退休而删除运行组件。

构建复用的独立回归：`node frontend/scripts/test-build-cache.mjs`。`npm.cmd --prefix frontend run build:if-needed` 检查内容后复用，`npm.cmd --prefix frontend run build` 始终重新构建。

## 资产准备与契约导出

日常准备在线输入请使用连接服务页的按背景资源卡片，见[资源管理](../docs/INFERENCE_RESOURCES.md)，无需执行历史批次准备脚本。`python -m scripts.check_inference_resources_frontend --url http://127.0.0.1:8001` 读取真实资产状态，使用仅在浏览器拦截的协议夹具检查下载、取消、重试和热更新，不下载大权重。

首页展示资源：`uv run --no-sync python scripts/optimize_frontend_images.py` 从保留的原图生成 WebP 与小尺寸图标；`--check` 只核对来源、产物哈希和尺寸。编码参数、Pillow 版本及文件摘要记录于 `frontend/src/assets/optimized/manifest.json`。替换原图后需重新生成并核验，再构建前端。

以下为历史批次复现工具；新建接口已停止接受 precomputed/validation，不应原样重跑 replay 阶段作为当前产品验收。四背景能力补齐使用 `.venv/Scripts/python.exe -m scripts.complete_context_capabilities <phase>`，阶段按 `prepare → diagnose → bundle → replay → verify` 顺序执行。该批次已经完成，前四阶段会拒绝覆盖已有产物；日常复查使用 `verify`。协议、观测、原始运行和回放清单存于 `reports/four-context-capabilities-2026-10-09/`。ALDOA 观测是实测原值，未生成或填补；模型权重和旧产物保持原哈希。详见 [验收记录](../docs/verification/2026-10-09-four-context-capabilities.md)。

表达尺度修正的历史重算使用 `.venv/Scripts/python.exe -m scripts.reanalyse_expression_v2`，核验后加 `--publish` 将新编号入库；需要预先冻结的 `reports/scientific-scale-v2-2026-10-09/baseline.json`，已有结果会拒绝覆盖。真实 AAMP 诊断使用 `-m scripts.diagnose_expression_v2`，同样先计算、后 `--publish`；保留原预测和冻结协议，绝不生成观测。当前这批已完成，重复发布会拒绝替换。报告和限制见 [修正记录](../docs/verification/2026-10-09-expression-scale-and-validation.md)。

| 脚本 | 用途 |
|---|---|
| `extract_gene_list.py` | 从模型自身保存的 `var_dims.pkl` 提取有序基因面板 |
| `extract_replogle_k562.py` | 从上游数据按范围读取 K562 子集；使用仓库内 `configs/splits/replogle-k562-source.toml` |
| `prepare_context_assets.py` | 固定官方 revision，下载并校验 RPE1/Jurkat/HepG2 的 ST-HVG 配套资产，抽取真实对照；仅 `--phase register` 修改登记表 |
| `prepare_gene_identity.py` | 从 HGNC 官方快照与冻结 GPR 稳定 ID 建立身份适配；不填补表达值 |
| `prepare_se_assets.py` | 下载固定版本并校验官方 SE epoch16 与四背景 ST-SE-full；不改活跃登记 |
| `audit_se_compatibility.py` | 检查官方配置、源 H5AD 嵌入和来源元数据 |
| `prepare_se_controls.py` | 从固定官方源提取每背景 64 个真实对照和原始 X_state |
| `run_se_native_predictions.py` | 运行保留有符号 SE 坐标的预测及原生表达头，产物保存在实验目录 |
| `run_se_query_experiment.py` | 用官方 SE 参数实际查询全部 931 基因；保留原始解码值及来源 |
| `probe_se_encoder.py` | 固定 SE epoch16 真实重编码，数值比较公开源嵌入 |
| `plot_real_se_predictions.py` | 仅用真实对照拟合共享 PCA，保存实际预测投影、变换与来源哈希 |
| `verify_se_experiment.py` | 验证裁剪修复前后数值关系、931 基因矩阵、官方完整性及旧运行保全 |
| `evaluate_se_observed.py` | 按对照批次权重比较真实 AAMP 群体均值差值与两种模型输出；不视为留出验证 |
| `calibrate_se_control_scale.py` | 按 SE 训练 mu 条件，用真实对照估计每细胞尺度；保留默认链作对照，不用扰动标签调参 |
| `audit_validation_candidates.py` | 盘点每背景实际测量及批次可比的扰动，按预定规则冻结后续诊断候选 |
| `run_measured_se_diagnostic.py` | 对冻结的四背景共有实测扰动（默认 ALDOA）运行真实 ST-SE、931 基因查询及批次权重差值诊断 |
| `audit_supervision_sources.py` | 检查上游 .X/.raw/layers 特征轴与 HGNC 覆盖；不给缺测基因补零，不读取表达值 |
| `smoke_contexts.py` | 三个新增背景的 MySQL + CUDA + STATE + scCellFie 真实运行；要求新推理，核验 H5AD、预测群体、清单和结果接口 |
| `backfill_official_completeness.py` | 用官方 scCellFie API 给已完成真实运行添加完整性报告；验证冻结来源和原文件哈希，仅新增报告与登记 |
| `attach_replogle_hvg.py` | 给已有 H5AD 补齐注册面板矩阵 |
| `register_assets.py` | 计算注册所需哈希；`--write` 会更新注册表 |
| `build_demo_bundle.py` | 生成明确标注的合成演示包，含单细胞表达矩阵与二维投影 |
| `repair_demo_projections.py` | 默认只盘点；--apply 对明确合成的旧演示补充矩阵/投影/来源，保留原运行文件；真实结果不得补合成点 |
| `export_openapi.py` | 导出接口快照 |

资产准备脚本会写入数据或注册文件；日常启动已准备好的系统时无需重复执行。`replogle-k562-source.toml` 是上游来源拆分快照，不能代替项目正式评价协议；当前协议限制见 [模型与数据](../docs/MODEL_AND_DATA.md)。

历史预测结果展示专项检查（现行布局须复核断言）：`python -m scripts.check_prediction_evidence_frontend`。可用 `--url` 指定只读服务，`--check-projection` 额外验证已加载代谢任务空间的 UMAP/PCA 和关联导出。浏览器测试对缺失、非有限数值和零变化的拦截仅作用于测试页面，不改写服务器结果。

补齐官方完整性：`.venv\Scripts\python.exe -m scripts.backfill_official_completeness`，可重复传入 `--run-id` 指定真实运行。没有冻结追溯的旧记录跳过；已有报告校验后保留。审计写入 `reports/official-completeness/backfill.json`。方法、实际覆盖与限制见 [官方完整性验收](../docs/verification/2026-10-09-official-completeness.md)。

补齐旧预计算记录：先运行 `python -m scripts.repair_demo_projections` 盘点，再用 `--apply` 执行。产物审计写入 `reports/projection-repair/`，包清单修改前保存在 backups 中。必须使用安装了科学依赖且能连接项目数据库的 Python 环境。
## 导出与采样专项检查

以下 Python 浏览器检查保留原专项范围，选择器和布局断言需与当前界面对齐；本文未执行这些命令。纯函数/接线检查仍不能代替实际完整科研包读回。

方法数据与采样说明检查：`python scripts/check_control_sampling_frontend.py`。只读核对四背景实际对照数、固定来源/有放回采样说明、参数链接定位、白底与亮暗主题；未知人数场景使用受控响应，不新增实验。

- `python scripts/check_export_integrity_frontend.py --phase green-main --figures`：真实已完成实验的完整 trace/GPR、切任务取消、特征 JSON/SVG/PDF/PNG 文件名与覆盖引用检查；只读，不创建实验。
- `python scripts/check_export_downloads_frontend.py --url http://127.0.0.1:8000 --phase fixture-main`：受控响应验证完整 CSV、四包接线、错误类型拒绝与切页取消。它是 fixture 检查，不代表实际科研包读回。
- `node frontend/scripts/check-export-regressions.cjs`：纯函数/接线及 WebCrypto 缺失时 SHA-256 文件名回退回归。

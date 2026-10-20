# 脚本索引

所有命令从仓库根目录运行。脚本按用途保留，避免将仍可用于资产重建的工具误认为运行时必需步骤。

## 日常启动与检查

2026-10-15 真实观测比较：`python -m scripts.prepare_measured_comparisons extract` 从固定官方源抽取并冻结观测（现有 catalog 拒绝覆盖）；`evaluate` 为真实保存预测准备独立比较，支持 `--run-id`。`python -m scripts.verify_measured_comparisons` 核对实际 H5AD 群体、全基因均值、原文件哈希和选定官方 Cell-Eval 指标；`python scripts/check_measured_comparison_frontend.py` 验证真实主服务页面、下载、手机布局与助手上下文。证据写入 `reports/measured-comparison-2026-10-15/`。

| 脚本 | 用途 |
|---|---|
| `start_system.ps1` | Windows 检查端口占用、启动或复用数据库、构建前端并启动后端 |
| `start_mysql.ps1` | Windows 独立 MySQL 启动 |
| `check_mysql.py` | 数据库连接与表检查 |
| `audit_registry.py` | 注册资产、哈希与冻结数据库检查 |
| `prepare_gene_annotations.py --source-dir <已下载官方文件目录>` | 按显式 HGNC ID 冻结 PANTHER 功能分类，生成压缩注释与来源哈希；拒绝覆盖已有快照 |
| `verify_scientific_cell_state.py --figures` | 核对四背景及 ACD 的真实 PCA/逐细胞分数，导出科研图样例 |
| `check_scientific_cell_state_frontend.py` | 代谢导航合并、指标切换、四背景、科研图下载和响应式浏览器检查 |
| `smoke_backend.py` | 后端链路冒烟；按参数可能执行真实推理 |

## 前端检查

| 脚本 | 环境 | 产物 |
|---|---|---|
| `check_theme_frontend.py` | 生产 API；主题、系统偏好、静态资源、80 组页面/窗口布局和已有实验；不提交推理 | `reports/frontend-integration-2026-10-20/browser/` |
| `check_records_status_frontend.py` | 真实实验历史、结果直达与刷新、服务状态及响应式布局 | `reports/records-status-2026-10-11/` |
| `check_measured_comparison_frontend.py` | 已保存真实预测与实测比较、缺失状态、导出及助手摘要 | `reports/measured-comparison-2026-10-15/browser/` |
| `check_provider_frontend.py` | 大模型提供方选择与设置交互；实际调用范围以脚本内拦截规则为准 | 终端检查结果 |
| `check_assistant_frontend.py --base-url http://127.0.0.1:8000` | 亮暗/系统外观、快捷栏、设置、真实结果摘要、纯文本解读和下载；外部模型响应被拦截，不调用真实服务 | `reports/assistant-ui-2026-10-11/` |
| `check_online_workflow_frontend.py --url http://127.0.0.1:8000` | 当前在线入口、历史参数复用和手机布局；预测提交被拦截，不创建 GPU 任务 | 终端验收结果 |
| `check_frontend.py` | 后端与 Vite；显式 Mock 回归 | 终端检查结果 |
| `check_metabolism_frontend.py` | 单选覆盖等级、空分类、搜索、实际条形点击、真实与旧任务详情、缺失结果请求及手机布局 | `reports/frontend/metabolism-fix/` |
| `check_coverage_frontend.py` | 仅显示覆盖数量与清单、真实四背景、双语基因分类筛选、七项任务介绍与来源、覆盖项下载、扰动选择与移动布局；不创建记录 | `reports/gene-education-2026-10-11/` |

生产检查示例：

```bash
python scripts/check_theme_frontend.py --url http://127.0.0.1:8000
```

浏览器脚本需要其 Python 环境中的 Playwright 与 Chromium。旧章节播放、预计算新建、旧投影与三维兼容入口的验收脚本已退休；当前命令以上表为准，历史代码可从提交 `9ba57c7` 恢复。

## 资产准备与契约导出

四背景能力补齐使用 `.venv/Scripts/python.exe -m scripts.complete_context_capabilities <phase>`，阶段按 `prepare → diagnose → bundle → replay → verify` 顺序执行。该批次已经完成，前四阶段会拒绝覆盖已有产物；日常复查使用 `verify`。协议、观测、原始运行和回放清单存于 `reports/four-context-capabilities-2026-10-09/`。ALDOA 观测是实测原值，未生成或填补；模型权重和旧产物保持原哈希。详见 [验收记录](../docs/verification/2026-10-09-four-context-capabilities.md)。

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

预测结果展示验收：`python -m scripts.check_prediction_evidence_frontend`。可用 `--url` 指定只读服务，`--check-projection` 额外验证已加载代谢任务空间的 UMAP/PCA 和关联导出。浏览器测试对缺失、非有限数值和零变化的拦截仅作用于测试页面，不改写服务器结果。

补齐官方完整性：`.venv\Scripts\python.exe -m scripts.backfill_official_completeness`，可重复传入 `--run-id` 指定真实运行。没有冻结追溯的旧记录跳过；已有报告校验后保留。审计写入 `reports/official-completeness/backfill.json`。方法、实际覆盖与限制见 [官方完整性验收](../docs/verification/2026-10-09-official-completeness.md)。

补齐旧预计算记录：先运行 `python -m scripts.repair_demo_projections` 盘点，再用 `--apply` 执行。产物审计写入 `reports/projection-repair/`，包清单修改前保存在 backups 中。必须使用安装了科学依赖且能连接项目数据库的 Python 环境。

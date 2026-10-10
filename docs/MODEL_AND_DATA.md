# 模型与数据

本文件解释当前科学资产和输出含义。路径、哈希及启用状态以 `data/registry/` 为准；源码仓库不包含全部本机大型资产。

## 当前资产

| 资产 | 登记位置 | 内容 |
|---|---|---|
| STATE | `data/registry/models.json` | K562、RPE1、Jurkat、HepG2 的官方 ST-HVG fewshot 权重；arc-state 0.11.1，各 2024 个登记扰动 |
| 基因面板 | `data/registry/state_*_genes.txt` | 各背景独立从官方 var_dims 提取；2000 个有序基因，当前四份顺序一致 |
| 输入数据 | `data/registry/datasets.json` | 每种背景绑定自己的实测对照 H5AD；四背景均登记 ALDOA 实测诊断观测和冻结协议 |
| 拆分记录 | `configs/splits/replogle-v1.json` | 按扰动拆分，存在下述一致性问题 |
| scCellFie 数据库 | `data/registry/sccellfie/human/manifest.json` | 0.6.2 human Recon2，六个数据文件及固定阈值列的 SHA-256 |
| 回放包 | `data/demo/{背景}/ALDOA/` | 四个真实 STATE/scCellFie 诊断结果冻结回放，附原运行清单及哈希 |
| 历史开发资产 | `data/demo/K562/MYC/` | 固定种子合成数据，保留历史来源；正式目录不提供且默认禁止创建 |

K562 来源记录为 `arcinstitute/State-Replogle-Filtered` 的 replogle_concat.h5ad。本机对照为 3000×6546；旧观测文件 1465×6546 保留不变。当前诊断改为登记 ALDOA 的 33×6546 实测观测；模型使用其中的 2000 基因面板。

2026-10-08 新增 RPE1、Jurkat、HepG2，各准备 1024×6546 的真实 non-targeting 对照，保留 source_row、原始条形码、批次与来源 revision。数据来自固定 revision `d790193bb2c93726541a75ca3fa873a92ed44da5`，表达未再次归一化；X_hvg 只按模型顺序选列。模型来自 `ST-HVG-Replogle` revision `bb6a9562cbbf1fd152df14cc53b4cc7517c77175`，每背景六个推理文件通过官方来源哈希校验。2026-10-09 已分别登记 29、34、33 个 ALDOA 实测细胞；四背景均接通在线预测、真实结果回放、受冻结名单限制的实测诊断。

新背景的 `configs/splits/replogle-*-fewshot-v1.json` 保留对应官方完整 test 名单与原始 TOML 哈希；它们是来源记录，尚未批准准确性评价协议。权重来源与每次真实输出的核验见 [多背景接入记录](verification/2026-10-08-context-integration.md)。

2026-10-03 已重新核验 K562 模型、配置、面板、对照/观测、拆分文件和六个代谢数据库文件的哈希。许可记录见 [第三方说明](THIRD_PARTY_NOTICES.md)。

## 计算与解释

STATE 根据对照和目标扰动生成预测 H5AD。当前预测写入 obsm['X_hvg']，分析服务按注册面板映射到基因，再对齐对照、预测与可选观测的共同基因。重复基因、缺失面板或无共同基因会报错，不补零填补缺失基因。

HGNC 身份适配使用 `data/registry/gene_identity/` 的冻结映射，按数据库原有稳定 ID 对接历史名称，表达数值、列数与顺序不变。新运行保存 `gene_identity.json`；映射和数据库哈希受审计，映射变化会改变缓存指纹。歧义名称、重复身份及冲突 ID 会明确失败。现有运行的表达和评分不会因此重写。

模型登记新增 `expression_key`，与输入 `embed_key` 分开：`X` 表示输出表达在 `.X`，其他值表示 `obsm` 中的表达槽。未设置时保留旧 HVG 契约。SE 的 `X_state` 是有符号嵌入，不能当作基因表达或执行表达值裁剪；专用推理适配器核验官方函数指纹后保留这些坐标。官方原生表达头的裁剪规则保持一致。

SE 全覆盖实验及校准限制见 [推进记录](verification/2026-10-09-se-full-coverage.md)。实验模型未替换当前活跃模型；931 基因原始查询输出与正式代谢任务评分分开验收。

2026-10-09 起，`expression-cp10k-v2` 要求注册表明确声明表达尺度。当前活跃 ST-HVG 输入和输出已经是逐细胞 CP10K 后 log1p 的表达；基因均值直接计算 `mean(log1p(CP10K))`，predicted_delta 为预测均值减对照均值，不再重复归一化或取 log。模型保持原有 2000 个有序基因，不重新选择 HVG。原始计数入口必须另有全库总计数列，不能用截取面板的总量替代。新结果保存 `expression_contract.json`；摘要展示绝对变化最大的 20 个基因，完整表从 genes 接口读取。

单细胞主视图使用共同对照 PCA：仅用本次对照拟合坐标，对照、预测与可用观测共享该坐标系，并提供逐细胞指标着色和累积分布。旧 `/projection` 随机投影接口仅保留兼容用途。投影和解释方差均不是独立准确性指标。

scCellFie 接收上述 log 表达经 expm1 恢复的线性 CP10K，登记已归一化标记，避免包再次按 2000 基因面板归一化。它使用冻结的 sccellfie_threshold，各来源共用阈值，关闭跨来源细胞平滑。预测 CP10K 不是实测原始 UMI。任务分数反映表达支持程度，不能直接当作实测代谢通量。任务和反应差异按来源均值计算，摘要只取变化最大的 20 个任务。

## 覆盖等级

2026-10-09 起，真实运行优先展示 scCellFie 0.6.2 官方 `sccellfie.reports.compute_dataset_completeness` 连续指标。使用未按预测面板裁剪的完整冻结 GPR 数据库，参数为 `metric='fraction_zeroed', threshold=1.0`，统计范围为 dataset；输入为真正预测表达的基因面板，而非 H5AD 中未被模型预测的原始 `.X` 列。

报告包含全部关联基因和按单基因消融定义的 essential 基因两个范围，以及影响加权完整性、缺失基因清单、218 项任务和 787 条反应明细。消融在官方均一参考上进行，不能当作真实实验；单基因影响累加也不能证明联合缺失的效果。没有 essential 基因的集合由官方返回 1，页面显示“无单基因必需项”，不据此宣称证据完整。

`official_completeness.json` 保存包版本、官方函数源码 SHA-256、参数、数据库哈希、运行编号和 gene_deltas.csv 哈希。新运行自动保存并登记；历史真实运行可执行 `.venv/Scripts/python.exe -m scripts.backfill_official_completeness` 补充独立报告，原始预测、评分、摘要和 manifest 保持原哈希。缺少冻结来源的旧运行会跳过，合成演示不补写官方报告。

下表为项目旧规则，仅保留用于历史产物和 API 兼容。80%／60% 不是论文标准或官方置信度；官方报告页面不再使用这些门槛分档。完整性不等于预测准确率或实验验证，换指标不会补齐缺失预测。scientific_analysis.py 按任务关联基因的可用比例保留旧字段：

| 等级 | 规则 | 展示含义 |
|---|---|---|
| supported | 基因覆盖 ≥ 0.80 | 通过当前覆盖门槛 |
| exploratory | 0.60 ≤ 覆盖 < 0.80 | 覆盖有限，用于探索 |
| insufficient | 覆盖 < 0.60 | 覆盖不足 |

这些等级不表示预测已经获得实验验证。总体 reaction_fraction 当前是各反应所需基因覆盖比例的均值。`configs/analysis/metabolic.yaml` 也写有反应阈值，但当前管线没有读取它来决定等级；实际行为以上述源码为准。

冻结数据库缺失、空表达面板或表达不满足代谢要求等已捕获问题，会产生警告并保留转录结果。旧分档不再作为 scCellFie 评分的拦截门槛。摘要总体 coverage 可为 null，任务列表可为空。

## 验证边界

validation 分支在有匹配观测时独立生成表达变化相关性、MSE/MAE、不变化基线及差异表达诊断；代谢分析不可用不阻止表达评价。DE 使用 Scanpy Wilcoxon、BH、tie correction、FDR < 0.05，记录 DEG 数、Overlap@N/50/100/200、共有显著 DEG 方向及 AP。细胞级检验不是独立生物学重复。代谢任务 Spearman、MAE、方向一致率、Top-K 重叠及有效/排除任务数仍单独保存。可通过 /runs/{run_id}/validation 查询；协议状态仍为 unconfirmed，held_out_validation=false。登记 validation_batch_key 时仅保留三种来源共有的实测批次，不复制观测、不重加权批次频率。

11 个历史预测已保持预测文件字节一致、以新运行编号重算并入库；旧文件保持原哈希，旧版摘要接口提示使用新版本。AAMP 在 K562/Jurkat 的真实观测诊断和后续实验判断见 [尺度修正与诊断记录](verification/2026-10-09-expression-scale-and-validation.md)。这些诊断没有证明检查点训练时排除了该扰动，不属于独立留出验收。

拆分记录需在正式实验前核对：test_groups 列出 12 个扰动，frozen_test_group_count 却写为 969；development/calibration 列表为空。因此不能称它为已完成的完整 969 扰动验证协议。当前独立的 `configs/diagnostics/*-aldoa-v1.json` 明确登记 ALDOA、观测与批次字段及哈希；catalog、创建请求和管线共用名单门槛，前端开放“实测诊断”。训练排除未核实，仍需另行冻结正式开发/校准/测试协议。详见 [四背景能力验收](verification/2026-10-09-four-context-capabilities.md)。

历史 MYC 在线冒烟验证了工程链路。2026-10-03 复查命中其缓存，六类结果接口正常。正式生物学泛化、匹配基线和留出评估尚未完成，不能从工程测试或合成演示推断。

## 结果回放与历史开发资产

结果回放只接受通过哈希与原运行核验的真实模型结果。`allow_synthetic_results` 默认 false，目录和创建接口共用该限制；历史合成记录仍可读取并保留来源标记。开发契约检查可显式开启合成资产，正式部署保持关闭。

当前 K562/MYC 合成包已包含补齐的合成单细胞投影；模拟观测始终标为合成参考。四背景 ALDOA 包从真实诊断产物冻结，保留真实基因、任务、反应、投影、验证指标和原始 manifest。回放只重绑定运行编号和来源标识，不改变数值；`result_kind=frozen_model_result` 与 `synthetic_demo` 用于区分来源。本次回放不重新推理，不能把请求样本量或 seed 当作包生成参数。

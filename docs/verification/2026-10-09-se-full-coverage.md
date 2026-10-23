# HGNC 适配与四背景 SE 全覆盖推进

日期：2026-10-09。对应 [实施顺序](../research/archive/METABOLIC_FULL_COVERAGE_PLAN.md)：先完成身份适配，再运行官方 SE/ST-SE 查询链，最后根据验证决定是否训练新输出头。

## 已落实的工程契约

HGNC 官方快照 SHA-256 为 `8bf6f686e640dbc864a346484626953621b0500d900d26cd085a35c2782d725d`。原数据库的 HGNC ID GPR 与符号 GPR 按结构和位置核验，931 个代谢基因均有唯一身份。适配层保留原始列名、HGNC ID 与解析方式，不改变表达值、列数、列顺序或稀疏存储。重复身份、歧义符号和冲突 ID 明确报错；数据库文件仍使用原冻结版本。

新运行产生 `gene_identity.json`；冻结映射和数据库文件受哈希审计，映射与模型契约进入缓存指纹。登记字段 `embed_key` 与 `expression_key` 分开：SE 的 `X_state` 是输入和预测嵌入，表达头输出在 `.X`。旧 HVG 模型保留其原接口。

## 真实模型和真实输入

全部模型来自官方仓库，按固定 revision 下载，LFS 文件逐一校验官方 SHA-256。模型、表达值和输入嵌入没有人工合成。

| 资产 | 固定来源 |
|---|---|
| SE 编码/查询解码参数 | `arcinstitute/SE-600M`，revision `5a9a80f44f7ce32ce57059933ef0d735d7c10ce5` |
| SE 权重 | `model.safetensors`，SHA `3ebec58bd9e9c07f0a76de25b900dad13d015768fbff1e68e5dcbdfb3b2245de`；文件内元数据标注来源为 `se600m_epoch16.ckpt` |
| 基因蛋白嵌入 | `protein_embeddings.pt`，SHA `a210e1cc7901513999b2bca3836ba9e2f203cd008be4e9a9d6412a2267de9748` |
| 四背景 ST-SE-full | `arcinstitute/st-se-replogle-full`，revision `d1441f5587ace12c46247b3703c7d25f24f8abb6`，各背景 `checkpoints/best.ckpt` |
| 实测输入及原始 SE 嵌入 | `arcinstitute/State-Replogle-Filtered`，revision `d790193bb2c93726541a75ca3fa873a92ed44da5`，`replogle_concat.h5ad` |

K562、RPE1、Jurkat、HepG2 各按固定种子 42 抽取 64 个 non-targeting 实测细胞，保留原表达、条形码、批次、源行号和原始 `obsm/X_state`。每个背景真实运行 AAMP 扰动，严格选取 64 个目标预测细胞，排除附带的 64 个模拟对照。新资产未替换活跃模型登记。

## 两项实际接口问题

安装的 STATE 0.11.1 在 `tx infer` 的表达输出空间为 all/gene 时，也会对保存的 SE 嵌入执行 `[0,14]` 裁剪。SE 坐标有正有负，不能执行表达值裁剪。适配器核验官方函数源码 SHA `778a6b6773b8dc4b86f3f67bc51d1adf46f30f18ca51e6d6b3d89b98ae17ae8f`，只保护三个嵌入裁剪位置；表达头的裁剪保留。CLI 入口和再次导出的函数均指向修复后的实现。

必须以真实结果验证：原生表达矩阵与原 CLI 逐值一致；对修复后的有符号嵌入施加原裁剪可逐值恢复旧 CLI 的嵌入。首次裁剪结果与首次入口适配未生效的结果保存在诊断目录，并由 `excluded-diagnostics.json` 标记，不用于最终查询与投影。

另外，SE 查询接口会额外拼接数据集坐标。2058 维输入先拆为 2048 维细胞向量和 10 维数据集向量，避免重复拼接最后十维。基因查询仅使用唯一 HGNC 身份匹配的真实蛋白嵌入；禁止缺失嵌入的零向量回退。

## 兼容性与科学边界

官方源 H5AD 的 `uns` 只保存 HVG 信息，没有记录生成 SE 嵌入的编码器检查点。已严格载入全部 epoch16 参数，并逐块核验检查点蛋白表与公开蛋白字典完全相同。K562 的 4 个真实细胞分别用种子 42、43、44 重新编码，与源嵌入的细胞向量余弦相似度为约 0.984–0.993，数据集坐标 RMSE 约 0.0096–0.0147。这个小样本结果支持数值接近，不能代替精确来源证明或预测质量验证。

931 基因查询同时保存模型重建对照和模型预测扰动，均使用同一官方解码器和公开默认 read-depth=4.0。`.X` 保存未经裁剪、平移或填补的原始解码值，CSV 差值也基于该原始尺度。模型重建对照不是实测对照。当前原始解码存在负值，read-depth 与尺度尚未完成校准，因此本阶段不生成正式 scCellFie 任务分数，不将实验链启用为正式全覆盖模式。

集合完整性由官方 `compute_dataset_completeness` 检查实际查询矩阵的基因身份。完整性达到全部基因/任务，只说明输出列存在；不表示未测基因已获实验证实，也不表示预测准确。现有实测输入经身份适配只覆盖其中 526 个基因，其余 405 个由 SE 查询模型推断。

## 已完成的真实查询核验

各背景实际保存 64×931 的预测矩阵和 64×931 的模型重建对照。以下完整性由官方 API 检查这批真实输出的列集合，负值比例来自未经处理的预测解码值。重建相关性比较 526 个实测可用基因的群体均值，只是尺度诊断。

| 背景 | 基因 | 任务 all | 反应 all | 对照重建均值 Pearson | 原始预测负值比例 |
|---|---:|---:|---:|---:|---:|
| K562 | 931/931 | 218/218 | 787/787 | 0.9277 | 20.13% |
| RPE1 | 931/931 | 218/218 | 787/787 | 0.9169 | 25.01% |
| Jurkat | 931/931 | 218/218 | 787/787 | 0.9196 | 20.80% |
| HepG2 | 931/931 | 218/218 | 787/787 | 0.9060 | 11.34% |

四背景逐值核验均通过：原生表达头与原 CLI 输出完全一致；裁剪有符号 SE 坐标后可逐值恢复旧 CLI 坐标。四个原有真实运行全部输出仍匹配其冻结清单哈希。最终投影图已人工检查，坐标来自这些有符号真实输出。前两轮包含裁剪坐标的诊断产物保留并明确排除。

## 对照尺度实验及真实扰动诊断

安装版本 `StateEmbeddingModel.shared_step` 在一维 RDA 条件下使用 `nanmean(Y excluding zeros)`，即采样目标中非零 log 表达的平均值，而非总 UMI 或 log10 总读数。公开查询接口的 `read_depth=4` 只是默认常量。因此新增独立实验：在实测对照的 6546 个特征上计算每细胞非零均值，按预测细胞的源 `source_row` 复用对应条件；不使用实测扰动值选择或拟合条件。这个估计仍不同于原训练的随机目标采样，不视为尺度已完全校准。

| 背景 | 对照估计条件均值 | 默认 4 的重建 RMSE | 对照估计的重建 RMSE | 对照估计的均值 Pearson | 原始预测负值比例 |
|---|---:|---:|---:|---:|---:|
| K562 | 0.9907 | 1.0173 | 0.4034 | 0.9530 | 7.49% |
| RPE1 | 1.0357 | 1.0244 | 0.4110 | 0.9548 | 11.27% |
| Jurkat | 1.0430 | 1.0168 | 0.4276 | 0.9486 | 8.08% |
| HepG2 | 0.9051 | 1.2153 | 0.3945 | 0.9475 | 3.57% |

实际源数据中 AAMP 测量数分别为 K562 76、RPE1 0、Jurkat 39、HepG2 0。模型映射中存在基因键，不证明该背景有该扰动的实测监督。RPE1/HepG2 的 AAMP 输出是真实模型运行的外推值，没有对应的源数据验证。

可比较的 AAMP 诊断限制在实测扰动、对照与预测都有记录的批次。各批次使用真实细胞均值，按所选对照的批次权重合并，所有表达值不变；不重复抽取、复制或生成观测细胞。K562 使用 36 个实测扰动、53 个共有批次对照；Jurkat 为 18 和 26。

| AAMP 背景 | 默认 4：差值 MSE/不变化基线 | 对照估计：差值 MSE/不变化基线 | 对照估计差值 Pearson |
|---|---:|---:|---:|
| K562 | 1.6376 | 0.8908 | 0.3974 |
| Jurkat | 1.7228 | 1.0269 | 0.3788 |

比值低于 1 表示该诊断中误差低于不变化基线。当前只在 K562 取得这一结果；Jurkat 尚未超过基线。样本小、群体未配对，且检查点训练排除关系未知，不能据此宣称泛化通过。

后续候选在读取预测效果前，按实际测量至少 64 个扰动细胞、至少 32 个已抽取对照处于共有批次、且登记模型包含该键的规则冻结。合格数量为 K562 1141、RPE1 955、Jurkat 1121、HepG2 472。ALDOA 在四背景均合格，已选为四背景共同比较扰动；候选不是已确认的模型留出集。

## ALDOA 四背景共同比较

已实际运行四个 ST-SE 检查点，各产生 64 个 ALDOA 预测细胞，再执行对照估计条件的 SE 查询。每个背景均有 64×931 的真实模型预测和 64×931 的模型重建对照；官方数据集完整性均为 931/931 基因、218/218 任务和 787/787 反应。原始回归值保留，未生成正式任务分数。

实测比较使用所有来源均有记录的批次，按对照批次比例对实测扰动和模型预测进行加权。未读入的测量不补零，采样细胞不重复。下表比较实际可测的 526 个基因。

| 背景 | 实测扰动细胞 | 共有批次对照细胞 | SE 差值 Pearson | SE 差值 MSE/不变化基线 | 原生表达头 MSE/不变化基线 |
|---|---:|---:|---:|---:|---:|
| K562 | 33 | 39 | 0.4812 | 0.6618 | 5.8308 |
| RPE1 | 29 | 38 | 0.5422 | 0.6829 | 3.6582 |
| Jurkat | 34 | 45 | 0.4655 | 0.6338 | 2.4373 |
| HepG2 | 33 | 44 | 0.2341 | 1.6658 | 15.8290 |

本组诊断中，SE 查询链在前三个背景的误差低于不变化基线，HepG2 仍高于该基线。这里只评价一个共同扰动、一个固定抽样，且无法确认这些记录是否被预训练检查点用于训练；不能视为留出泛化通过。四背景使用四个独立检查点，也不证明模型能泛化至从未训练过的细胞背景。

真实嵌入投影见 `real-se-aldoa-predictions.png/.svg`。PCA 只拟合 256 个真实对照的 2048 维细胞坐标，解释方差约 16.5%；预测坐标由同一变换得到。最后十维数据集坐标不用于投影，箭头表示群体中心移动，不能解释为单细胞轨迹或形态变化。

## 新输出头的监督数据核验

已对四个上游文件检查根目录、`.X`、`.raw` 和 `layers`，只读取矩阵布局和特征注释，不读取或生成表达值。它们都只有 `.X`，没有另存全基因的 `.raw` 或额外层。HGNC 适配后的可用代谢身份分别为 K562 596、RPE1 618、Jurkat 611、HepG2 678；四背景并集 734/931，仍有 197 个代谢身份在任何一份文件中都没有测量列。这比逐符号匹配增加了覆盖，但不能恢复缺测表达。

原作者的 [Replogle 处理数据说明](https://plus.figshare.com/articles/dataset/_Mapping_information-rich_genotype-phenotype_landscapes_with_genome-scale_Perturb-seq_Replogle_et_al_2022_processed_Perturb-seq_datasets/20029387) 明确 raw single-cell 文件也筛选平均表达高于 0.01 UMI/cell 的基因。仅更换 raw/normalized 文件不能得到全基因监督。

当前顺序状态：HGNC 适配已实现；官方查询链已真实运行、校验和诊断；输出头训练进入监督来源准备，尚未启动训练。下一步需要取得全参考特征的计数矩阵，或从原始测序重新量化，同时核实背景、扰动、批次和拆分。没有恢复的基因保留缺测掩码，不能用 0 作为监督标签。编码来源、负回归值处理和更广的留出评价也仍需解决，正式全覆盖模式保持禁用。

## 验证范围

后端完整测试 104 项通过；新增的指定扰动选择测试组 5 项通过。Ruff 与基于完整配置的 basedpyright 检查通过。真实产物审计核验了有符号嵌入、默认与对照尺度查询、ALDOA 的四背景测量选择、查询身份/条件/文件哈希，以及四个原有真实运行的完整保全。图像已人工检查。工程检查不代替科学预测验收。

## 产物及重建顺序

产物保存在 Git 忽略的 `reports/metabolic-full-coverage-2026-10-09/`，模型权重保存在 `models/`。可追溯元数据与运行脚本纳入代码；现有真实运行文件不重写。

- `se-controls/`：原始实测表达和官方源嵌入。
- `se-native-signed-{背景}/`：真实 ST-SE 原生预测、命令、日志、身份适配和来源记录。
- `se-query-signed-{背景}/`：931 基因原始预测、重建对照、原始尺度差值、官方完整性报告和查询键映射。
- `se-compatibility/encoder-probe.json`：实际重编码的数值比较。
- `real-se-signed-predictions.png/.svg`：真实 SE 嵌入投影；共享 PCA 仅拟合 256 个真实对照的 2048 维细胞向量。
- `real-se-signed-projection-transform.npz` 与坐标 CSV：可复用 PCA 变换和真实坐标。
- `se-experiment-verification.json`：逐值一致性、完整查询矩阵、官方完整性和原运行哈希验证。
- `se-observed-diagnostic-shared-batches/`：真实 AAMP 测量、共有批次及按对照批次权重计算的差值比较；没有核实训练留出关系。
- `se-query-control-scale-{背景}/`：对照估计条件的独立真实 931 基因查询，保留默认 4 的原始实验。
- `validation-candidate-inventory.json`：每背景实测扰动数量、模型键、共有批次和未读预测结果的候选规则。
- `se-measured-aldoa/{背景}/`：原生预测、931 基因查询、真实测量、差值 CSV、完整性和来源记录。
- `real-se-aldoa-predictions.png/.svg` 与投影变换/坐标/清单：四背景共有实测扰动的真实预测投影。
- `supervision-source-slots.json`：上游全部表达槽位和 HGNC 身份覆盖，包含缺失监督身份清单。

首次重建在仓库根目录依次运行：

```powershell
.venv\Scripts\python.exe -m scripts.prepare_gene_identity
.venv\Scripts\python.exe -m scripts.prepare_se_assets
.venv\Scripts\python.exe -m scripts.audit_se_compatibility
.venv\Scripts\python.exe -m scripts.prepare_se_controls
.venv\Scripts\python.exe -m scripts.run_se_native_predictions
.venv\Scripts\python.exe -m scripts.run_se_query_experiment
.venv\Scripts\python.exe -m scripts.probe_se_encoder
.venv\Scripts\python.exe -m scripts.plot_real_se_predictions
.venv\Scripts\python.exe -m scripts.verify_se_experiment
.venv\Scripts\python.exe -m scripts.evaluate_se_observed
.venv\Scripts\python.exe -m scripts.calibrate_se_control_scale
.venv\Scripts\python.exe -m scripts.audit_validation_candidates
.venv\Scripts\python.exe -m scripts.run_measured_se_diagnostic --perturbation ALDOA
.venv\Scripts\python.exe -m scripts.plot_real_se_predictions --measured-perturbation ALDOA
.venv\Scripts\python.exe -m scripts.audit_supervision_sources
.venv\Scripts\python.exe -m scripts.verify_se_experiment
```

已存在的实验目录主动拒绝覆盖；再次实验应先设置新的版本目录并保留原产物。下载脚本可重复运行以验证并复用已下载权重。单独运行验证脚本可复核现有结果。

下一阶段继续核实全基因监督来源、编码器来源与留出拆分，并预先声明非负输出规则。当前对照尺度估计和单扰动诊断已完成；只有恢复所需真实标签后，才能实施新输出头训练。缺测基因不能作为 0 参与损失。

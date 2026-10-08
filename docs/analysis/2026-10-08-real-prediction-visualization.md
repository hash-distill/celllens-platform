# 真实 STATE 预测展示与 SE 投影可行性分析

日期：2026-10-08。范围：核对现有源码、保存预测、模型配置与官方资料；生成独立核验图。未改动运行链路、前端、模型或原始数据，未下载新权重，未执行新的 STATE/SE 推理，也未开展留出准确性评估。

## 1. 结论与选择

真实展示的成立条件是“图上的每个预测点都来自模型保存的输出行”，不取决于是否采用 SE。SE 是表达矩阵的编码器，仍需再做 PCA 或 UMAP，才能显示为二维坐标。[1][2]

| 路线 | 当前证据与可行性 | 建议用途 |
|---|---|---|
| 现有 ST-HVG 真实预测 → 共用 PCA | 已用本地 AAMP 输出运行，输入与输出哈希通过 | 立即作为可追溯的状态分布展示 |
| 现有真实预测 → 同一 SE 编码器 → PCA/UMAP | 官方编码接口存在，但本地未登记 SE 权重，只有 2,000 个预测基因，未验证面板编码质量 | 有条件的探索功能，不能直接宣称更准确 |
| 实测对照 → SE → 匹配的 ST-SE → 原始预测嵌入 → PCA/UMAP | 官方有 K562 fewshot 权重与配置，本地尚未下载或运行；需要修正输出语义和裁剪行为 | 要展示 STATE 原生预测状态时的首选接入路线 |
| 对合成矩阵做投影 | 当前演示包采用该路线 | 只证明交互与页面，不用于展示科学预测 |

推荐先展示现有真实 ST-HVG 输出，配合基因分布；如果决定接入 SE，则使用官方匹配的 K562 ST-SE 权重，另建模型版本，保留原始预测嵌入。不要只把当前 `embed_key` 从 `X_hvg` 改成 `X_state`：训练输入空间与权重必须匹配。

## 2. 当前真实资产核验

核验运行：`run_4d0b3038ea8642af`，K562 / AAMP / online / n_cells=64 / seed=42。

| 项目 | 当前文件核验结果 |
|---|---|
| 对照 | `data/raw/replogle-k562/control.h5ad`，3,000 行，6,546 个原始保存基因 |
| 对照模型特征 | `obsm['X_hvg']` 为 3,000 × 2,000 |
| STATE 原始预测文件 | 128 行，其中 AAMP 64、non-targeting 64 |
| 正确目标预测 | 先按 `obs['gene']=='AAMP'` 筛选，得到 64 × 2,000 |
| 真正预测值的位置 | `predicted.h5ad.obsm['X_hvg']` |
| `.X` | 仍保存输入表达，不是当前模型的完整扰动后预测 |
| 现有正式投影 | `seeded-random-projection`；3,000 个对照点、64 个目标预测点，筛选记录正确 |
| 当前训练空间 | 模型配置 `embed_key: X_hvg`，`output_space: gene`，并非 SE 模型 |
| SE 权重 | 项目 `models/` 中只有现有 ST-HVG checkpoint；未发现项目内 SE checkpoint |

运行日志明确写出 `Controls simulated: 64`、`Treated simulated: 64`、`Wrote predictions to adata.obsm['X_hvg']`。真实推理输出与“真实扰动后实测细胞”是不同概念；页面应分别写“实测对照”和“STATE 预测”。

当前演示包的 `demo_cells.npz`、`demo_projection.py` 和历史补充投影明确标为 `synthetic_demo`，没有 STATE 预测来源。随机投影算法本身不会把真实矩阵变成假数据；问题在于输入是否来自模型。真实运行的随机投影与合成演示的随机投影要按来源区别。

历史 MYC 等运行还存在把模拟对照混入 predicted 的旧产物；不能因目录里有 `predicted.h5ad` 就复用旧汇总。应检查目标标签和 `population_selection`。

## 3. 已运行的真实展示原型

目录：`reports/state-visualization-audit-2026-10-08/`。

- `probe.py`：可重跑的分析脚本。
- `audit.json`：运行来源、输入输出哈希、群体数量、软件版本和核验范围。
- `control_pca_basis.npz`：控制群体拟合得到的均值、20 个主成分、基因顺序与解释方差。
- `pca_coordinates.csv`：每个显示点的来源、原始预测文件行号、obs_name、坐标。
- `gene_mean_deltas.csv`：保存表达尺度上的逐基因群体均值变化。
- `real_prediction_probe.png` / `.svg`：三联图。

![真实预测核验图](../../reports/state-visualization-audit-2026-10-08/real_prediction_probe.png)

运行方法（项目根目录 PowerShell）：

```powershell
.venv/Scripts/python.exe reports/state-visualization-audit-2026-10-08/probe.py
```

协议：仅在全部 3,000 条实测对照上拟合 PCA，再对 64 条目标预测应用同一变换。使用保存的 `X_hvg` 尺度，未补点、未加表达噪声、未填缺失基因、未重复归一化或 log1p。PCA 随机化求解器固定种子 42；随机性用于计算投影基底，不生成表达样本。

实际结果：PC1 解释 2.2866%，PC2 解释 1.6960%，合计约 3.98%；前 20 个成分合计 12.05%。这些比例描述对照方差，不表示预测准确率。二维图上群体重叠，并不表示高维响应很小。

例如 GAS5 的保存尺度均值从对照 1.9073 到预测 2.4621，变化 +0.5547；HIST1H1C 从 1.7425 到 1.2109，变化 −0.5315。这是模型输出描述，未与扰动后实测群体核对，也不是显著性检验结论。

核验包含：源 manifest 登记的对照、基因列表、预测文件和现有投影哈希一致；全部矩阵有限；仅选 AAMP 行；同一 PCA 对重复输入返回相同坐标；受检源文件执行前后 SHA-256 不变。图像经过实际打开检查，文字与坐标可读。

## 4. 为什么不能直接把现有 predicted.h5ad 交给 SE

本地 `arc-state==0.11.1` 的 SE `encode_adata` 读取输入文件的 `.X`。当前 ST-HVG 推理把输出写到 `obsm['X_hvg']`，留下 `.X` 中的输入表达。直接调用 SE，会编码输入表达，随后却被页面误标为“扰动后预测嵌入”。

在已筛选的 AAMP 群体中，真正预测面板与 `.X` 对应基因面板的平均绝对差为 0.3611，说明这两个槽位不能互换。

若走后置 SE 路线，应另建输入文件：

```text
control_panel.X = 实测对照的同一 2,000 基因面板
predicted_panel.X = 目标预测 obsm['X_hvg']
两者 var_names = 注册的 2,000 基因顺序
两者都经过同一个 SE checkpoint 与同一处理协议
```

这条路线描述为“ST-HVG 预测表达的 SE 编码”。不能称为“ST 在 SE 空间直接预测的状态”。

2,000 个预测基因不构成完整转录组。不要把其余 4,546 列沿用对照表达后称为模型预测；不要用零值将未预测基因伪装为没有表达。若两边都只输入面板，技术接口支持基因映射，但面板与 SE 预训练分布的差异仍要实测。相同面板只是公平比较的必要条件，并不保证 SE 比 PCA 更敏感。

基因映射应保存面板覆盖率、有效映射率、未匹配基因清单；包括 GAS5/SNHG1 等非蛋白编码基因可能不在官方蛋白嵌入表中。面板特异效应可能因此丢失，不能在未查看映射后直接宣称“保留了全部扰动信号”。

## 5. 原生 SE 预测路线：有具体官方资产，但未完成运行验证

官方 `arcinstitute/ST-SE-Replogle/fewshot/k562/config.yaml` 明确登记：[3]

```yaml
embed_key: X_state
output_space: gene
pert_col: gene
cell_type_key: cell_line
control_pert: non-targeting
batch_col: gem_group
cell_set_len: 64
```

该配置证明 K562 的 SE 输入路线确实存在。候选计算链为：

```text
实测对照表达 → 匹配 SE 编码器 → 对照 X_state
对照 X_state + 扰动/批次 → 匹配 ST-SE checkpoint
                          ├→ 未裁剪的预测状态向量 → 共用 PCA/UMAP
                          └→ 基因解码输出 → 基因响应与 scCellFie
```

从当前官方配置和 SE 源码看，SE 主细胞表示为 2,048 维，并拼接 10 维数据集表示；实际输出形状须以选定 checkpoint 运行值为准。[4][5] 作为跨数据集状态图，可另行保存主细胞块与数据集块，比较主块/完整向量的表现；ST 输入则必须使用其训练所需的完整维度与顺序，不能擅自删除后 10 维。

需要确认 SE-600M 的具体 epoch/revision 与 ST-SE 训练使用的编码空间匹配。维度都是 2,058 不足以证明 checkpoint 可互换。官方模型卡尚未给出完整配对解释，必须结合 checkpoint 元数据或作者资料确认；未确认前只作为候选接入，不能宣称已复现该模型。

当前发布目录含 SE checkpoint、蛋白嵌入和 ST-SE K562 checkpoint：[6][7] `se600m_epoch16.ckpt` 页面列约 11.5 GB，`protein_embeddings.pt` 约 411 MB，K562 `checkpoints/final.ckpt` 约 510 MB。只需选定版本的必要文件，不需要下载整个仓库或重复的 eval checkpoint。这里没有执行下载，也没有以文件大小估计显存或运行时间。

SE 初次完成后应缓存 3,000 条对照嵌入。新扰动复用缓存，ST 推理与投影按运行产物计算；输入哈希、基因列表、SE revision、处理协议改变时重新编码。GPU 可运行性、批大小和显存需要在实际机器上验证，不能仅凭已有 ST-HVG 能运行就推断 SE 能运行。

### 必须处理的实际源码问题

1. **基因与嵌入不能共用语义。** 当前注册模型仅有一个 `embed_key`；`_expression_view` 把它按基因列表解释。如果换成 2,058 维 SE，当前表达分析会错误映射或报错。应分别登记 `input_embedding_key`、`prediction_embedding_key`、`prediction_expression_key`、基因列表和尺度。
2. **保留未经表达裁剪的 latent。** 本地 `_cli/_tx/_infer.py` 在 `output_space in {'gene','all'}` 时裁剪主输出到 [0,14]。当主输出为 SE 状态而同时解码基因时，这个判断可能把带正负值的嵌入也裁剪。应在 `predict_step` 后独立保存原始 `preds`；只对确认为表达的输出应用相应协议。实际 checkpoint 的输出维度和解码返回项仍需运行核验。
3. **不要把导出字段名称当作尺度证据。** 官方变量名含 `counts` 不意味着矩阵是原始整数 UMI。当前控制矩阵为非整数、类似预处理表达；SE loader 会依据数值启发式判断 raw/log。需要登记尺度并核对是否有重复转换。现有 `_projection_document` 又执行总量归一化和 log1p，对已变换模型特征会改变原尺度；本次 PCA 原型直接使用保存尺度以避免该问题。
4. **复现 SE 采样。** SE loader 存在 `torch.randperm` 等操作。固定 Python/NumPy/PyTorch 与数据加载器种子、文件顺序、批大小、设备和精度，保存第一次编码产物；检查重复运行差异，不把 dropout=0 当成绝对确定性的保证。

## 6. 怎样显示才直观

建议工作台采用“状态分布 + 具体基因变化 + 功能解释”联动。

### 状态分布图

- 蓝色圆点：实测对照；橙色三角：STATE 预测；有匹配实测扰动数据时才显示第三组。
- 并排与叠加共用同一个投影模型、范围和比例。必须先拟合一次再应用，不能分别对两群做 PCA/UMAP 后叠加。
- 首页默认显示全量 64 个真实预测点，真实数量不足时如实展示；需要更多点则增加模型推理输出，而不是复制、抖动或插值补出细胞。
- 对照背景点可降低透明度；群体密度应按来源分别归一化，不能把 3,000 对 64 的点数差解释为群体丰度变化。
- 悬停显示 run_id、source、文件原始行号、预测标签、选定基因值与输入/输出版本。原始 barcode 只能表示输入来源，不能证明预测细胞与实测细胞的一对一对应。
- 选择基因或代谢任务时仅改变颜色与侧栏，坐标保持不变。所有群体共用颜色数值范围；没有该值则留空并说明，不能补零。
- 群体均值箭头可作为统计偏移提示；逐点连线、连续时间动画都缺少真实配对/时间信息，不应作为模型预测过程展示。

### 基因响应图

用实际单细胞值的 ECDF、直方图或箱线图比较群体，再列保存尺度上的均值差。当前 GAS5 示例比二维点云更容易看出响应。不要把预测样本的检验 p 值当成生物学重复实验的证据；64 条模型输出不等于 64 个独立实验。

点击某个基因，状态图在同一坐标上按该基因着色；旁边显示该基因两群分布及模型输出值。点击任务时显示任务分布、决定基因、反应与覆盖率。scCellFie 分数为表达支持的功能评分，不是实测通量或细胞器形态。

### PCA 与 UMAP 的位置

PCA 适合做可追溯默认图：线性、能导出基底、可以给出解释方差。当前只用对照拟合便于跨扰动固定坐标，但新的效应可能落在被忽略的成分，应配基因/高维描述，而非根据二维图下结论。[8]

UMAP 可以作为探索切换项：对固定开发参考群体拟合，保存其配置与参考数据，以 `transform` 映射新预测；记录 `n_neighbors`、`min_dist`、距离度量和随机种子。[9] 固定 UMAP 对新状态有参考分布依赖，可能压缩或错误放置参考之外的预测，二维岛屿间距离不能直接称为扰动效应量。

如果参考只有同一种 K562 对照，SE/UMAP 不保证出现漂亮分群。单次联合拟合对照与预测适合探索，但坐标会随扰动变化，不能同时宣称跨运行位置稳定。不要通过根据目标标签调参或强制拉开群体来增强视觉差异。

## 7. 工程验收顺序

1. 真实运行与合成演示在目录、来源字段、默认入口和图例上清晰区分；展示来源绑定预测产物而不是只看 `mode`。
2. 新投影从正确目标群体和预测槽位派生；单细胞基因图统一尺度；旧产物另存新版，保留原 manifest。
3. 投影产物保存 `run_id`、`data_kind`、矩阵槽位/尺度、输入哈希、原始行号、拟合群体、基因顺序、方法参数、软件版本及 reducer 哈希。
4. 先验收现有真实 ST-HVG 展示；SE 小批量验证读取、基因映射、输出形状、精度与显存后，再登记匹配 ST-SE 版本。
5. ST-SE 原始嵌入与表达解码输出分开保存、独立验证；确保图上每点能回查未经裁剪的预测输出。
6. 科学验证另立协议：固定开发/校准划分、匹配对照与实测扰动、采用高维评价与基线；现有冻结 test 不用于反复调投影或选取最漂亮的案例。图像存在、链路运行成功和预测准确分别验收。

## 8. 来源与核验边界

用户要求优先使用 Context7；本次工具清单没有 Context7 resolve/query，因此核对本地安装源码与官方原始资料。网页 `main` 可变，上线时应固定 revision 与 SHA-256。本次候选 SE/ST-SE 未经实际推理；未承诺 SE 优于 HVG/PCA，也未宣称现有预测经过生物学验证。

1. [Arc STATE 发布介绍：SE 可选，ST 扰动预测](https://arcinstitute.org/news/virtual-cell-model-state)
2. [Arc STATE README：SE transform 与 ST infer](https://github.com/ArcInstitute/state)
3. [官方 ST-SE-Replogle K562 fewshot 配置](https://huggingface.co/arcinstitute/ST-SE-Replogle/raw/main/fewshot/k562/config.yaml)
4. [官方 SE 编码与数据集向量拼接源码](https://raw.githubusercontent.com/ArcInstitute/state/main/src/state/emb/inference.py)
5. [官方 SE-600M 模型配置](https://huggingface.co/arcinstitute/SE-600M/raw/main/config.yaml)
6. [官方 SE-600M 发布文件](https://huggingface.co/arcinstitute/SE-600M/tree/main)
7. [官方 K562 ST-SE checkpoint 目录](https://huggingface.co/arcinstitute/ST-SE-Replogle/tree/main/fewshot/k562/checkpoints)
8. [scikit-learn PCA 文档](https://scikit-learn.org/stable/modules/generated/sklearn.decomposition.PCA.html)
9. [UMAP 对新数据使用 transform](https://umap-learn.readthedocs.io/en/latest/transform.html)

本地证据：`models/state-replogle-k562/config.yaml`、`backend/app/services/scientific_analysis.py`、`backend/app/engines/state_engine.py`、`backend/app/services/demo_projection.py`、已安装 `state/_cli/_tx/_infer.py`、`state/emb/inference.py`、`state/emb/data/loader.py`，以及上述真实 run 的 manifest、预测文件、日志、投影文件。机器可读核验见 `reports/state-visualization-audit-2026-10-08/audit.json`。

# CellLens 多细胞背景接入与泛化验证

核验日期：2026-10-08。结论：可以扩展到 RPE1、Jurkat、HepG2；官方已有同系列 ST-HVG 权重、配套数据和背景留出划分。当前仅开放 K562 是应用资产与接口的限制，不能据此判断底层 STATE 只在 K562 上训练。扩展可用范围与证明跨背景泛化需要分别验收。

本次完成本地代码、在线 catalog、官方资产元数据、配置、划分及远程 H5AD 元数据核验；未下载新 checkpoint、未读取远程表达矩阵、未启用新背景、未运行新增背景预测或准确性评估。

## 1. 当前限制在哪里

- 在线 `/api/v1/catalog/contexts` 返回 K562 可在线运行；RPE1 的模型和对照资产缺失或未校验，全部运行模式不可用。没有 Jurkat/HepG2 条目。
- `data/registry/datasets.json` 只有 K562 数据；RPE1 模型条目是禁用占位，没有 checkpoint、基因表与配置的有效哈希。
- `backend/app/schemas.py` 的请求只允许 `K562/RPE1`，`frontend/src/types/run.ts` 同样固定两个名称。catalog 和参数面板已经按登记表生成选项，但新名称仍需打通契约。
- `scripts/extract_replogle_k562.py`、`scripts/register_assets.py` 固定了 K562 的目录、背景、基因表与 split；不能直接用于新背景，否则有覆盖旧资产的风险。
- 当前 RPE1 占位配置写的是 `target_gene/cell_type`；已核验的官方 RPE1 配置实际要求 `gene/cell_line`。启用时必须同步更正并登记哈希。
- 登记器 `model_for(cell_line)` 每种背景只取一个模型。若同时提供 fewshot 与 zeroshot，需增加明确的模型/评估协议选择，不能只追加同名背景条目，让第一条记录决定模型。

本地现有 K562 checkpoint 的 SHA-256 与官方 `fewshot/k562/checkpoints/final.ckpt` 完全相同。本地 `cell_type_onehot_map.pkl` 已包含 `hepg2/jurkat/k562/rpe1` 四个键。其配套 K562 TOML 未留出整个背景，只留出了 K562 的扰动。因此官方声明的训练范围并不是“K562 单背景”。映射键存在说明输入编码有这些背景，并不等于本项目已验证其他背景可运行或预测准确。[1][2]

## 2. 已核验的新增资产

模型仓库：`arcinstitute/ST-HVG-Replogle`，revision `bb6a9562cbbf1fd152df14cc53b4cc7517c77175`。

数据仓库：`arcinstitute/State-Replogle-Filtered`，revision `d790193bb2c93726541a75ca3fa873a92ed44da5`。[1][2]

| 背景 | 远程过滤数据中的细胞数 | 可接入的模型目录 | 接入顺序建议 |
| --- | ---: | --- | --- |
| K562 | 188,590 | `fewshot/k562`、`zeroshot/k562` | 保留现有链路，补评估协议 |
| RPE1 | 173,737 | `fewshot/rpe1`、`zeroshot/rpe1` | 第一批；已有应用占位 |
| Jurkat | 184,470 | `fewshot/jurkat`、`zeroshot/jurkat` | 第二批；增加一个不同背景 |
| HepG2 | 96,616 | `fewshot/hepg2`、`zeroshot/hepg2` | 第二批；完成四背景覆盖 |

上述数量来自远程 HDF5 的 `obs.cell_line`，包含对照和扰动，不能当作可供每次运行使用的对照数。文件形状为 `643,413 × 6,546`，本次只读取元数据，没有下载 30,010,775,846 字节的完整表达文件。

每个 `final.ckpt` 为 471,695,263 字节，约 472 MB；新增三个 fewshot checkpoint 合计约 1.415 GB，另需配置、映射与数据子集。每种背景的数据可沿用远程分段读取方式提取，读取量取决于 HDF5 布局和选取规模，不能承诺等于输出文件大小。

六个新增候选（三个背景 × 两种协议）的 `hparams.yaml` 均为：输入 2,000 维、输出 2,000 维、`embed_key=X_hvg`、`output_space=gene`、扰动编码维度 2,024。六份有序基因表与本地 K562 表逐项完全相同。官方配置统一使用 `gene`、`cell_line`、`gem_group` 和 `non-targeting`。因此 ST 推理、表达适配、scCellFie、真实结果可视化可以复用；数据准备和模型路由仍必须按背景绑定。

三个新增 fewshot final checkpoint 的官方 LFS SHA-256：

| 背景 | SHA-256 |
| --- | --- |
| RPE1 | `02603032590f51fbcca890e9f201ad07f1c457dbc72580baa97e5aae9b5a3814` |
| Jurkat | `10cfcf01aff649e7f868ed6cf70e763cfbae91d7ba94e2887324a58fbcf5ede5` |
| HepG2 | `9b387a5268f9432b9dd7ad2b1d193b97314835b0d10f50b9b2e7c979cd85b35c` |

这只是远端资产标识，下载后仍需计算本地哈希和运行兼容性验收。完整官方来源响应、配置、划分哈希和元数据保存在 `reports/cell-context-audit-2026-10-08/`；其中 `upstream.json`、`splits.json`、`summary.json`、`dataset_metadata.json` 支持复查。

## 3. 两条路线分别解决什么问题

### 多背景功能接入

每种背景登记同系列 fewshot checkpoint 和对应对照，生成真实预测。现有 K562 checkpoint 从输入映射上也可能接收其他三种背景，但那些背景在其声明的训练范围内。复用它可以作为工程可运行性探针，不能把得到的结果当作新背景泛化评测。

正式展示优先使用目标背景的官方 fewshot 版本和配套留出列表，让来源、checkpoint 与评估划分一致。“fewshot”是官方协议名称，不意味着本项目完成了少量样本微调。[1][3]

### 跨背景泛化验证

官方 `rpe1_zeroshot.toml` 将整个 `replogle.rpe1` 放入 test；另外三个背景同理。应选匹配的 `zeroshot/<目标背景>` checkpoint，以目标背景实测对照作为推理输入，用其未参与 ST 拟合的实测扰动作为评估标签。[2][3]

例如：按官方声明，留出 RPE1，使用其余背景训练的 ST；输入真实 RPE1 对照与扰动名称；将预测 RPE1 的响应与实测 RPE1 响应比较。无需先自行从零训练，便可验证发布权重的跨背景性能。上线前仍需核对 checkpoint 配套配置、映射、划分和可取得的训练来源；不能仅凭目录名就宣称已严格复现。

这里的“未见背景”必须写清是 **ST 未用该背景的扰动数据进行拟合**，不能自动延伸成 SE 预训练从未见过该背景。目标背景对照作为推理输入是明确允许的条件，应在评估说明中披露。

当前模型使用固定 one-hot 扰动词表，因此跨背景迁移与任意新扰动基因预测也是两个问题。是否可提交某个基因必须根据实际 `pert_onehot_map.pt` 判定；不得将其他背景的可选基因列表直接复制过去。

## 4. 最小可实施方案

1. 先选 RPE1 完成一次真实链路，再复制经过验收的流程接入 Jurkat/HepG2。独立保存每种背景的 checkpoint、全部推理配套文件、原始来源、对照、实测扰动与有序基因表。
2. 将提取与登记脚本参数化为背景、模型 revision、协议、输入基因表和输出目录；默认只审计，显式登记时按 ID 更新。保留已有 K562 文件与哈希，避免复用 `replogle-v1.json` 覆盖旧划分。
3. 输入校验背景标签、对照标签、批次、表达尺度、有限值与完整的 2,000 基因顺序。提取现成过滤数据时不得再次默默 normalize/log；使用原始数据则需明确重建官方处理流程。
4. 后端与前端的背景契约改成经 catalog 登记和校验的背景值；后台继续拒绝未登记或资产未就绪的请求。每个模型分别生成支持的扰动清单。
5. 为模型/协议增加身份字段。运行 manifest、请求与缓存包含背景、模型版本、checkpoint 哈希、对照哈希、split 哈希和处理配置；same background 的 fewshot/zeroshot 结果不能共享身份。
6. 每种背景先验收一项小规模真实推理：输出目标标签、正确预测槽位、行数、有限值、基因顺序、代谢评分与可追溯图表；通过后才能将 catalog 标记可用。
7. 另登记开发/校准/最终评估协议，再开放科学验证。当前 catalog 的 `validation_ready=true` 只表示资产与算力满足条件；现有 validation 扰动列表为空，不能据此称准确性已验证。已有 K562 冻结 test 不用于反复挑案例或调整方案。

## 5. 如何提供可信且直观的证据

最小泛化结果应按背景、按扰动报告，不用一张混合 UMAP 代替评估。

- 表达评价以背景匹配的响应差值为核心：`Δ预测 = 均值(预测扰动) − 均值(对应对照)`，实测同理。报告 Δ 的误差、相关性及预先定义的响应基因检出指标；原始表达相关性会被基线表达抬高，不能单独使用。
- 至少比较“不发生变化”（预测等于目标背景对照）和仅利用训练背景的平均扰动效应。所有基线不使用目标背景扰动标签拟合或调参；无可用训练响应的扰动单列，不补出标签。
- 相同扰动跨背景比较时，取词表与实测可评估集合的交集。展示“背景 × 响应基因”的 Δ 热图和“背景 × 任务”的变化图，保留每背景的覆盖率与不足状态。
- 汇总按扰动等权，展示中位数、分布和按扰动重采样的不确定性；模型输出的单细胞行不能直接当作独立生物学重复。没有真实细胞配对时不计算逐细胞对应误差。
- scCellFie 结果是表达支持的任务评分，不能称为实测通量。其覆盖支持/探索性/证据不足反映评分证据范围，不是预测准确度。跨背景任务比较必须记录阈值/参考尺度，优先比较各自对照上的变化。
- 状态图读取真实预测。现有共同 2,000 基因面板可以先用固定 PCA；引入 SE 时仍需保证读取预测表达槽位以及相同编码流程。一个多背景固定参考、共同投影器和坐标范围可以支持对比；不要各背景分别拟合二维坐标后叠加。主图可并排显示各背景内对照/预测，悬停回查 run 与来源。

验收分三个层次：**多背景链路能运行 → 留出扰动的预测表现 → 整个背景留出的迁移表现**。每个层次分别给结果和失败范围。四个背景都是细胞系、同类遗传扰动实验；这能建立有意义的跨背景证据，但不足以证明对原代细胞、患者组织、任意药物或物种的普适泛化。

## 6. 推荐的项目表述

尚未接入时：“已完成 K562 真实推理链路，已核验 RPE1、Jurkat、HepG2 的扩展资产与接入方案。”

真实接入完成后：“支持四种人类细胞系背景下的遗传扰动预测，提供模型版本、数据来源与适用范围。”

完成背景留出评估后：“在预先冻结的跨细胞背景协议下，与简单基线比较预测扰动响应，并报告各背景的表现与限制。”

建议近期交付“四背景真实预测 + 至少一个完整背景留出验证”，后续补齐四个留出背景。SE 作为统一状态表示的后续选项，与新增 ST-HVG 背景接入分开验收。

## 来源

1. [官方 ST-HVG-Replogle 发布资产，固定 revision](https://huggingface.co/arcinstitute/ST-HVG-Replogle/tree/bb6a9562cbbf1fd152df14cc53b4cc7517c77175)
2. [官方过滤数据及八份背景划分，固定 revision](https://huggingface.co/datasets/arcinstitute/State-Replogle-Filtered/tree/d790193bb2c93726541a75ca3fa873a92ed44da5)
3. [STATE 官方说明：fewshot 为背景内扰动留出，zeroshot 为整个背景留出](https://github.com/ArcInstitute/state)
4. [Jurkat/HepG2 原始 Perturb-seq 实验：GSE264667](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE264667)

本地依据：`data/registry/models.json`、`datasets.json`、`configs/models/state-replogle-rpe1.yaml`、`configs/splits/replogle-k562-source.toml`、`backend/app/core/registry.py`、`backend/app/engines/state_engine.py`、`backend/app/schemas.py`、`frontend/src/types/run.ts`、两份 K562 提取/登记脚本、运行中 catalog 响应。

本次工具清单未提供 Context7 resolve/query。配置和协议由官方原始文件与已安装/本地源码直接核对；这次没有修改生产契约或调用新的库接口。

# 模型与数据

本文件解释当前科学资产和输出含义。路径、哈希及启用状态以 `data/registry/` 为准；源码仓库不包含全部本机大型资产。

## 当前资产

| 资产 | 登记位置 | 内容 |
|---|---|---|
| STATE | `data/registry/models.json` | K562 fewshot 启用，arc-state 0.11.1，2024 个登记扰动 |
| 基因面板 | `data/registry/state_k562_genes.txt` | 2000 个按模型预测列顺序排列的基因 |
| 输入数据 | `data/registry/datasets.json` | K562 对照/观测 H5AD，模型面板位于 obsm['X_hvg'] |
| 拆分记录 | `configs/splits/replogle-v1.json` | 按扰动拆分，存在下述一致性问题 |
| scCellFie 数据库 | `data/registry/sccellfie/human/manifest.json` | 0.6.2 human Recon2，六个数据文件及固定阈值列的 SHA-256 |
| 演示包 | `data/demo/K562/MYC/` | 固定种子合成数据，供页面及接口开发 |

K562 来源记录为 `arcinstitute/State-Replogle-Filtered` 的 replogle_concat.h5ad。本机对照为 3000×6546、观测为 1465×6546；模型使用其中的 2000 基因面板。验证分支按请求扰动筛选观测。RPE1 缺少核验完成的 checkpoint 与兼容数据，保持禁用。

2026-10-03 已重新核验 K562 模型、配置、面板、对照/观测、拆分文件和六个代谢数据库文件的哈希。许可记录见 [第三方说明](THIRD_PARTY_NOTICES.md)。

## 计算与解释

STATE 根据对照和目标扰动生成预测 H5AD。当前预测写入 obsm['X_hvg']，分析服务按注册面板映射到基因，再对齐对照、预测与可选观测的共同基因。重复基因、缺失面板或无共同基因会报错，不补零填补缺失基因。

基因差异算法先取每组每个基因的表达均值，再将该均值向量按总量归一到 10000，做 log1p；predicted_delta 为预测变换值减对照变换值。这不是显著性检验，也不是逐细胞归一化后求均值。摘要展示绝对变化最大的 20 个基因，完整表从 genes 接口读取。

二维视图使用固定种子随机投影，各来源共用基底并分层抽样。它用于展示表达位置关系，当前不是 UMAP 或独立验证指标。

scCellFie 使用冻结的 sccellfie_threshold，各来源共用阈值，关闭跨来源细胞平滑。任务分数反映表达支持程度，不能直接当作实测代谢通量。任务和反应差异按来源均值计算，摘要只取变化最大的 20 个任务。

## 覆盖等级

当前 scientific_analysis.py 按任务所需基因的可用比例分类：

| 等级 | 规则 | 展示含义 |
|---|---|---|
| supported | 基因覆盖 ≥ 0.80 | 通过当前覆盖门槛 |
| exploratory | 0.60 ≤ 覆盖 < 0.80 | 覆盖有限，用于探索 |
| insufficient | 覆盖 < 0.60 | 覆盖不足 |

这些等级不表示预测已经获得实验验证。总体 reaction_fraction 当前是各反应所需基因覆盖比例的均值。`configs/analysis/metabolic.yaml` 也写有反应阈值，但当前管线没有读取它来决定等级；实际行为以上述源码为准。

冻结数据库缺失、覆盖不足或表达不满足代谢要求等已捕获问题，会产生警告并保留转录结果。摘要总体 coverage 可为 null，任务列表可为空。

## 验证边界

validation 分支在有匹配观测且代谢分析成功时生成 validation_metrics.json，含 Spearman、MAE、方向一致率、Top-K 重叠及有效/排除任务数。当前无公开查询接口，指标也不在 RunSummary 中。

拆分记录需在正式实验前核对：test_groups 列出 12 个扰动，frozen_test_group_count 却写为 969；development/calibration 列表为空。请求入口没有按拆分限制验证请求。因此不能称它为已完成的完整 969 扰动验证协议。本次仅整理文档，没有修改拆分或算法代码。

历史 MYC 在线冒烟验证了工程链路。2026-10-03 复查命中其缓存，六类结果接口正常。正式生物学泛化、匹配基线和留出评估尚未完成，不能从工程测试或合成演示推断。

## 演示数据

build_demo_bundle.py 生成带来源说明和哈希清单的合成包，不是 STATE 推理或 scCellFie 输出。预计算模式校验后复制文件，不执行科学计算。

当前样例有摘要、基因差异、覆盖和任务相关文件，但没有 projection、reaction_scores 或 report。模拟观测字段也需标为演示数据。

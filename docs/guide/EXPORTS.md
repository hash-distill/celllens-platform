# 导出结果与外部工具

更新日期：2026-10-22。已完成实验顶部的“下载结果包”提供四种 ZIP；基因、代谢任务、关联反应和实测对比表可单独下载完整 CSV。分页、搜索和非零行筛选不会裁掉完整 CSV。

## 选择文件

| 文件 | 用途 | 内容 |
|---|---|---|
| 分析结果包 | 归档、核验与共享 | 冻结科学 CSV/JSON、双语 PDF、已有图与坐标、来源清单 |
| 单细胞分析包 | Python/Scanpy 等继续分析 | 规范 H5AD、细胞/基因注释、逐细胞任务/反应分数、已有 PCA/UMAP |
| 网络包 | Cytoscape 或图分析程序 | nodes.csv、edges.csv、完整 task_trace.json；可从任务详情仅导出所选任务子网 |
| 基因排序包 | GSEA Preranked 等探索性分析 | 全面板有符号预测差值 RNK、面板背景、基因身份表 |
| 完整 CSV | Excel、Prism、Origin、R/Python | 各来源均值、预测/观测差值及可用的误差、单位和群体元数据 |
| SVG/PDF/PNG、视图 JSON | 排版或重绘特定科研视图 | 所选表达/代谢指标的图、坐标和数值；文件名包含特征标识 |

ZIP 的 `manifest.json` 记录版本、单位、群体、来源 SHA-256 和每个载荷的 SHA-256。`optional_omissions` 明确缺失选件；不会补造缺失实测或新算降维。已完成但缺少可核验来源的旧结果会拒绝导出。合成演示不提供科研交换包。

## 原分析与实测诊断的区别

`original/` 表示原运行使用的分析群体；`comparison/` 表示另行保存的共同批次匹配实测诊断。两者会有不同细胞数、均值和差值，不能直接混成一套结果。

例如本机 HepG2/ALDOA 原分析为对照 1024、预测 256；实测诊断为对照 840、预测 209、实测 96。CSV 的 `population`、`selection_id`、`n_control/n_predicted/n_observed` 与包内 `table_metadata.json` 可用于核对。请求采样细胞数不替代这些实际人数。缺少可核验计数时留空，不填零。

H5AD 仅包含 `original` 群体。`comparison` 中的实测表不会自动进入这个矩阵；以包清单中的 `h5ad_included` 和群体计数为准。匹配实测诊断的训练排除与独立留出尚未核实，不是独立泛化评测。

## H5AD 的含义与读取

`original/expression_log1p_cp10k.h5ad` 使用标准 AnnData 结构：

- `X`：细胞 × 模型基因面板的 `log1p(CP10K)` 表达；原生 STATE 输出可能把预测放在 `obsm.X_hvg`，导出时按冻结契约读取并筛选目标扰动，不能直接把原生 `.X` 当预测。
- `obs`：`celllens_source` 区分 control/predicted/observed，保留安全白名单中的批次等注释及原细胞 ID。
- `var`：冻结面板符号和可核验 HGNC 身份。未绑定项保留原符号、空身份与明确清单，不猜测映射。
- `obsm`：只放已有的表达/代谢 PCA/UMAP 二维坐标；坐标不是形态、细胞器结构或物理位置。
- `uns.celllens_export`：来源、单位、群体和坐标说明。没有原始 UMI counts、`raw` 或 counts 层。

```python
import scanpy as sc

adata = sc.read_h5ad("original/expression_log1p_cp10k.h5ad")
print(adata.shape)
print(adata.obs["celllens_source"].value_counts())
print(list(adata.obsm))
```

读取后先核对表达尺度，不要再次执行 CP10K/log1p。预测连续表达不是实测计数；不能把它当作原始 counts 交给要求计数分布的模型。R/Seurat 需要按所用版本转换，并把表达放入适当的数据层；本次没有验证 R 转换链，不能宣称一键兼容。AnnData 的结构与写入规则见[官方文档](https://anndata.readthedocs.io/en/stable/generated/anndata.AnnData.html)。

## 网络与排序的外部导入

Cytoscape 可从 `edges.csv` 建网络，将 `source`、`target`、`interaction` 分别设为源节点、目标节点、关系类型，再以 `nodes.csv` 的 `id` 与网络节点名称列匹配属性。两个文件均有表头，分隔符选择逗号。孤立节点应从节点表另行保留；仅导入边表不会自动创建孤立节点。任务、反应、基因的 ID 带类型前缀，不能删掉后再合并。流程依据[网络导入文档](https://manual.cytoscape.org/en/stable/Creating_Networks.html)和[节点属性导入文档](https://manual.cytoscape.org/en/stable/Node_and_Edge_Column_Data.html)。

网络边表示知识关联，未提供因果方向或通量权重；不要把 `source/target` 列当作生物学因果方向。反应的 `gene_rule` 保留 AND/OR 逻辑，普通连边不能替代 GPR 逻辑。包内完整 trace 和载荷哈希可用于复核。

`ranking/predicted_delta.rnk` 为无表头、两列制表符文本，第一列是基因符号，第二列是原分析群体的预测均值差，按有符号值降序排序。可用作 GSEA Preranked 的探索性输入，格式见[GSEA 官方说明](https://docs.gsea-msigdb.org/GSEA/Data_Formats/#rnk-ranked-list-file-format-rnk)。这个分值不是 log2FC、p 值或显著性。约 2000 基因的面板不是全转录组；`panel_background.txt` 用于说明面板范围或供支持自定义背景的分析使用，不能声称 GSEA Preranked 会自动读取这个背景文件。

本次已验证文件解析、数值、H5AD 读回与网络闭合；没有实测 Cytoscape、R、Prism、Origin 或 GSEA 的 GUI 导入与完整下游分析。当前文件也不包含 SBML 所需的化学计量、反应界限与目标，不能作为 FBA 通量模型直接运行。

## 报告与关联 JSON

PDF 保留稳定英文任务 ID，并在有注释时附中文名称、关联基因覆盖比例/数量、覆盖证据含义、原分析与诊断群体人数、训练排除/留出限制。优先使用可嵌入的中文字体；部署时可通过 `CELLLENS_PDF_FONT` 指定许可允许嵌入的 TTF。没有可用字体时报告明确提示中文字体未嵌入。

任务“完整关联 JSON”保留原始关联和 GPR；页面筛选和显示计数单独记录在 `display`。覆盖目录 JSON 说明全部/完整/部分覆盖数量与纳入规则，保留引用的反应或明确列出缺项；它仍是知识覆盖目录，不是有评分的完整通量网络。

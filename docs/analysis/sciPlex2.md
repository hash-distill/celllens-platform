# sciPlex2 数据接入

当前接入固定的 scPerturb v1.4 sciPlex2 文件，执行真实表达比较，不调用 STATE。来源为 [Zenodo 13350497](https://zenodo.org/records/13350497)，原研究样本为 GSM4150377。记录级许可为 CC-BY-4.0。

## 已核验内容

| 项目 | 实读结果 |
| --- | --- |
| 文件 | `SrivatsanTrapnell2020_sciplex2.h5ad`，145,178,504 字节 |
| MD5 | `12a48293a166a859f994551653a2ad8c`，与官方记录一致 |
| SHA-256 | `0adabca03632ac9421a769fc9eaa4178447d4d572f4c2c54e4fde93a81acde67` |
| 版本 | `scperturb-sciplex2-v1.4-0adabca03632` |
| 矩阵 | X 为 CSR，24,262 个细胞 × 58,347 个基因，60,135,001 个存储值 |
| 表达尺度 | 原始 UMI counts；全部存储值逐块检查为有限、非负、整数；全部细胞矩阵行和与 obs.ncounts 一致 |
| 物种与背景 | obs.organism 全部为 human、obs.cell_line 全部为 A549；58,347 个 var.ensembl_id 均为 ENSG |
| 药物标签 | Dex 8,064；Nutlin 5,956；SAHA 5,530；BMS 4,183；未分配 control 529 |
| 剂量 | 原始标签 0、0.1、0.5、1、5、10、50、100；单位和时间未在文件中提供 |
| 重复 | 192 个 well 标签；未核验为独立生物学重复，不提供正式差异显著性 |

原始计数的来源依据为 [冻结的上游处理脚本](https://github.com/sanderlab/scPerturb/blob/fd4f5b360233520b0fc297f1bdf8953a6bee2dbb/dataset_processing/scripts/SrivatsanTrapnell2020.py)：直接从 `UMI.count.matrix` 构造 CSR。只凭矩阵是整数并不足以证明原始计数，因此同时保留这一处理依据。

## 对照与比较

登记 28 个真实非零剂量条件，每个条件与**同一药物标签下 dose_value=0** 的细胞比较。四类零剂量对照共 3,901 个细胞；每种药物七个非零剂量。没有将来源未明确归属的 529 个 control 细胞用作对照，也没有把所有对照改名为 non-targeting 或 DMSO。

上游脚本对未分配细胞的 DMSO 身份有明确推测性注释，因此这里的 `control_type` 为 `zero_dose_same_drug_label`。剂量只展示原值，不补造单位和处理时间。well 标签保存在提取文件中，但不据此认定独立样本或重复。

HGNC 历史别名解析遇到四组身份冲突：ENO1-IT1/ENO1、LINC00444/SUCLA2、C2orf48/RRM2、LINC01336/GCNT4。每组在源文件中具有不同的 Ensembl ID。新数据集适配器保留标准基因的身份，拒绝冲突别名重映射，保留全部独立表达特征；不求和、不删除、不借用另一基因的表达。详细记录写入每次分析的 `gene_identity.json`，旧接口的严格身份行为不变。

## 准备与使用

在仓库根目录执行：

```powershell
.venv/Scripts/python.exe -m scripts.prepare_sciplex2
```

该命令只下载固定官方 URL，支持经过 HTTP Range 检查的断点续传。仅在大小和官方 MD5 一致后将 `.part` 文件发布到 `data/raw/scperturb/`，检查矩阵与条件后写入 `data/registry/datasets/scperturb-sciplex2-v1.4.json`。原始矩阵目录受 Git 忽略。已有文件只需重新核验时使用 `--inspect-only`。API 不接受任意 URL，也不在查询时下载数据。

接口为 `GET /api/v1/datasets`、`GET /api/v1/datasets/scperturb-sciplex2/conditions`，条件默认每页十条。提交新分析使用 `POST /api/v1/datasets/scperturb-sciplex2/analyses`，请求示例：

```json
{"condition_id":"contrast_0517df539debcd95","max_cells":256,"seed":42}
```

该条件为 SAHA 原始 dose=10，对应 540 个处理细胞和 1,005 个同标签零剂量细胞。`max_cells` 为每组上限，默认 256、契约范围 1–4,096；同时检查完整基因面板的矩阵工作内存估计。预算为 1 GiB，超限请求在排队前拒绝并提示降低细胞数，不自动改变抽样大小。

provider 按冻结条件选取源行，在 CSR 中读取所选细胞；只将有界的两组送入分析引擎。按完整源基因面板的文库计数归一化为 log1p(CP10K)。原始条件、source_row、细胞 ID、抽样参数、文件摘要和表达尺度随结果冻结。`expression_preview.npz/json` 保存本次实际分析细胞，用于与投影群体一致的基因表达分布浏览；它不是全数据集的替代品。图表工作区的投影目前按实测或预测群体着色。

输入预检与完整分析验收分别记录。准备成功只表示数据校验和条件可用，不能单独证明整条代谢、通路、图表和导出流程已成功完成。

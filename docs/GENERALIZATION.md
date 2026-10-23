# 模型支持范围与泛化证据

核查日期：2026-10-22。当前系统能够为四种已登记细胞背景中的 2,023 个真实扰动目标提供模型编码，共 8,092 个背景／目标组合。固定公开源中有实测的组合为 5,759 个，另有 2,333 个词表支持的组合在该版本中没有观测记录。这些数量说明输入范围与数据可用性，不能作为泛化成功率。

当前仍为 `training_exclusion_verified=false`、`held_out_validation=false`，目录中的 `generalization_verified` 全部为 `false`。已有匹配实测诊断不构成独立留出泛化验证。

## 支持范围如何确定

本次审计使用本机四个官方 ST-HVG-Replogle 模型的 `pert_onehot_map.pt`、`cell_type_onehot_map.pkl`、`config.yaml`、模型注册表及固定资产清单。模型来源固定为 [arcinstitute/ST-HVG-Replogle 的已登记 revision](https://huggingface.co/arcinstitute/ST-HVG-Replogle/tree/bb6a9562cbbf1fd152df14cc53b4cc7517c77175)。审计记录中四个模型目录的文件 SHA256 均与固定推理资产清单一致。

四份扰动词表完全相同，每份有 2,024 个条目，其中 `non-targeting` 是对照，剩余 **2,023 个真实扰动目标**。模型注册表与实际编码映射忽略大小写后集合一致。这里的“真实扰动目标”指非对照的词表目标身份，不表示每个目标在每种背景下都有观测，也不表示每个组合都已独立评估。

细胞背景映射仅有 **HepG2、Jurkat、K562、RPE1**。每个模型的表达面板为 2,000 个基因；表达面板大小与可选择的扰动目标数是两个不同概念。基因属于表达面板，不足以证明它能作为模型扰动目标；目标属于编码词表，也不足以证明预测准确。

## 固定公开源中的实际覆盖

数据固定为 [State-Replogle-Filtered revision d790193bb2c93726541a75ca3fa873a92ed44da5](https://huggingface.co/datasets/arcinstitute/State-Replogle-Filtered/tree/d790193bb2c93726541a75ca3fa873a92ed44da5) 的 `replogle_concat.h5ad`。目录逐行统计完整的 `obs.cell_line` 与 `obs.gene`，并核对 obs 索引长度，合计 **643,413 个细胞**。本次只范围读取元数据，没有访问表达矩阵 `/X`。

| 背景 | 源细胞数，含对照 | 有实测的扰动组合 | 模型支持组合 | 模型支持且本源无记录 | 本源无记录的实际候选示例 |
|---|---:|---:|---:|---:|---|
| HepG2 | 96,616 | 1,340 | 2,023 | 683 | AAMP、AARS2、AASDHPPT |
| Jurkat | 184,470 | 1,537 | 2,023 | 486 | ACSS2、ACTL6A、ACTR5 |
| K562 | 188,590 | 1,383 | 2,023 | 640 | AAR2、ABCB10、ACSS2 |
| RPE1 | 173,737 | 1,499 | 2,023 | 524 | AAMP、AAR2、AATF |
| 合计 | 643,413 | 5,759 | 8,092 | 2,333 | 完整名单见 CSV |

表中的示例逐项来自本次完整缺失名单，不是推荐靶点或预测结果。完整列表见 [model-supported-without-source.csv](evidence/measured-first-2026-10-22/model-supported-without-source.csv)，统计与来源见 [catalog-summary.json](evidence/measured-first-2026-10-22/catalog-summary.json)。对照保留在源细胞总数中，不进入扰动目标数。

“本源无记录”只表示该固定 filtered revision 中没有对应背景／目标的 obs 行，不代表其他数据版本、研究或实验中没有该组合，也不能证明 checkpoint 没有接触过相关训练数据。当前 2,333 个本源缺失组合均未出现在对应上游 TOML 的 test 名单中，不能把这份源缺失名单直接当作官方留出测试集。

目录把 `source_cell_count` 与 `local_measured_cells` 分开：前者来自完整公开源元数据，后者只计入本地已登记、哈希及实际观测标签核验通过的文件。源有观测而尚未下载，仍显示“本源有实测”。源索引缺失、损坏或不完整时，源状态为 `unknown`、细胞数为 `null`，不能转写为零。

## 上游 fewshot test 声明的证据等级

四份固定 revision 的 TOML 提供了 fewshot test 名单，其非对照目标均能在模型词表中编码。原始配置与内容哈希已保存；目录使用完整四背景名单，未把旧 K562 本地选取的 12 项当作全部官方 test。

| 背景 | 上游 test 原始条目 | 其中对照条目 | 排除对照后的 test 目标 | 固定 TOML SHA256 |
|---|---:|---:|---:|---|
| HepG2 | 946 | 1 | 945 | `7f8d5df29942f7532fef09b23a0a8deec7b8339bfe7817505b977bd894813962` |
| Jurkat | 1,085 | 1 | 1,084 | `9606316c24dfd140bbfe7e252375c18283d4f4f10b5a4adcb463a87cd1472634` |
| K562 | 969 | 1 | 968 | `a794ae85cacbb8ae2ce59ad5ba0fb465f5be244950b84aea28c7fa29226597c3` |
| RPE1 | 1,061 | 0 | 1,061 | `1681633c6b902933a8e83aae07d941ba2e63e5b968be0b80fea61a247308ecdc` |

这些配置没有逐项列出显式 train 集合，配置注释表示其余扰动自动进入训练。四个本地模型配置记录了原训练机器上的 TOML 路径；路径名称与当前公开文件同名，不足以证明训练时内容就是本次核验的字节。

本次 checkpoint 元数据检查只覆盖一个 K562 官方 checkpoint，采用 CPU mmap 读取，不执行推理。记录包含训练步数、超参数及权重结构，但未形成把该 checkpoint 与训练 TOML 内容哈希、实际训练样本及排除目标绑定起来的核验链。其他三个 checkpoint 的元数据未作同等内容检查。因此，目录的 `official_split=test` 表示“**上游声明的留出候选**”，不能升级为“本 checkpoint 已核实未见过”或“本项目独立泛化成功”。固定文件哈希证明资产身份，不能替代训练排除证据。

| 事实或字段 | 当前可支持的结论 | 不能据此推出的结论 |
|---|---|---|
| `model_supported=true` | 模型存在该背景及目标的编码入口 | 每个组合都有训练样本或预测准确 |
| `source_status=measured` | 固定公开源存在该组合的真实观测 | 该观测独立于模型训练 |
| `source_status=not_in_source` | 该 filtered revision 没有该组合记录 | 全球没有实验、模型训练从未见过该组合 |
| `official_split=test` | 固定上游配置声明该目标为 test 候选 | 已核实该 checkpoint 的训练排除关系 |
| 历史匹配实测指标 | 指定样本、尺度和批次规则下的预测诊断 | 独立留出总体性能或生物学因果验证 |

## 历史五例比较的解释

[2026-10-15 的五例当前比较](verification/2026-10-15-measured-comparison.md) 包括四背景 ALDOA 和 Jurkat／ABHD11。其表达均值、实际输入身份及部分 Cell-Eval 表达指标经过核对，能够支撑“实现与选定指标计算一致”的结论。它们使用既有方便样本，未核实 checkpoint 训练排除，不是独立冻结的跨目标测试集。

该批次保留了未优于不变化基线的 HepG2／ALDOA 与 Jurkat／ABHD11。不能把五例相关性改写为准确率百分比，不能汇总为四背景泛化排名，也不能把其中较好的案例外推到全部 8,092 个组合。细胞数量不等于独立生物学重复数量；表达比较与 scCellFie 表达派生任务评分也不等于实测代谢通量。

## 当前可以怎样使用

有固定源观测的组合优先直接分析真实对照与扰动细胞；用户也可明确启动模型预测，再进行匹配实测诊断。本源缺失且词表支持的组合只提供**探索预测**，输出保留预测来源与未核实泛化边界，不自动补成实测。

当前模型契约不支持词表外的新基因、四背景之外的未知细胞类型、基因组合扰动、药物、可变剂量或时间条件。自由文本说明不会扩展模型编码范围。词表内但本源缺失的组合与词表外目标必须分别处理；前者可探索，后者当前不支持。

要形成独立泛化结论，需要先取得与 checkpoint 绑定的训练数据版本、完整划分及排除证明，再冻结与开发选择独立的多目标、多批次评测协议，明确评价单位、基线、缺失情况和不确定性，最后报告全部预定案例的结果。当前核验目录、工程测试及历史五例不会自动满足这些条件。

## 可复核证据

- [模型与 checkpoint 只读审计](evidence/measured-first-2026-10-22/generalization-audit.json)：四背景词表、配置、资产哈希、官方划分，以及单个 K562 checkpoint 元数据检查范围。
- [审计脚本](evidence/measured-first-2026-10-22/generalization-audit.py)：记录审计方法；含 checkpoint 元数据读取，不是本次文档更新的执行步骤。
- [覆盖核验说明](evidence/measured-first-2026-10-22/catalog-verification.md)、[目录 API 证据](evidence/measured-first-2026-10-22/catalog-api-evidence.json)、[完整源目录](../data/registry/perturbation_catalog.json)。
- 固定官方原文：[HepG2](evidence/measured-first-2026-10-22/official-hepg2.toml)、[Jurkat](evidence/measured-first-2026-10-22/official-jurkat.toml)、[K562](evidence/measured-first-2026-10-22/official-k562.toml)、[RPE1](evidence/measured-first-2026-10-22/official-rpe1.toml)。

# 科研真实性评审

评审对象为 `D:\全球校园人工智能精英大赛\celllens-national` 和 `http://127.0.0.1:8028`，快照时间为 2026-11-07 18:11–18:18（北京时间）。先读取在线 API，再核查活动代码、冻结结果和推理日志；没有提交新计算、改动数据、重启服务或修改生产代码。本次没有进行浏览器视觉验收。代码行号对应本次审查时的文件。

评委判断：已经形成真实的“STATE 预测 → 表达分析 → scCellFie 功能支持 → 实测诊断 → 导出”的软件链，不是纯静态演示。最有价值的是可重复的实测重分析和有来源约束的探索性预测；当前不宜把单案例“优于基线”或代谢相关系数作为稳定的预测效能结论。优先修复统计解释与结果契约即可显著提高可信度，不需要另训大模型。

确认的正向证据：

- `run_feb6ebf11ef747ab` 是 64 个 Jurkat/ALDOA 预测记录；`predicted.stdout.log` 记载 `Model device: cuda:0`、`Model output space: gene`、64 treated/64 controls simulated。分析契约明确从 128 条模型输出筛选 64 条 ALDOA，未把模拟对照误算作处理组。
- 当前注册的是四个 `state-replogle-*-fewshot-v1`，每个支持词表 2024 项、输出同一个 2000 基因面板；模型版本登记 0.11.1。模型词表、输出面板和实测覆盖是不同集合。HepG2/SACM1L 的目录 API 正确返回 `source_cell_count=0`、`model_supported=true`、`recommended_action=predict_exploratory`。
- 对新 Jurkat 运行的原始 manifest 所列 12 个输出逐项重算 SHA-256，全部一致。两个比较 CSV GET 均为 HTTP 200，分别含 2000 基因和 141 任务，细胞数与比较 JSON 一致。
- 实测 K562/ALDOA 记录 `measured_00c6134fec4544efb1ad3b6d` 使用 754 对照、77 扰动实测和 6546 共同基因；代码没有调用 STATE。表达单位写为 `mean(log1p(CP10K))`，进入 scCellFie 前逆 log1p、不对裁剪面板重新归一化。

## 1. P1：基线优劣受批次组成影响，当前案例已经发生结论翻转

**状态：已确认的统计敏感性；不能据此断言模型整体无效。**

复现对象：`GET /api/v1/runs/run_feb6ebf11ef747ab/comparison`。冻结报告使用共有的 28 个 `gem_group`，选中 control=535、predicted=48、observed=46。它先把各组细胞直接汇总，所以三组的批次权重不同。对照和实测的批次频率总变差为 0.255912。

| 同一输入的汇总口径 | 变化 Pearson | 预测 MSE | 不变化 MSE | MSE / 不变化 MSE |
| --- | ---: | ---: | ---: | ---: |
| 当前各组细胞直接平均 | 0.432157 | 0.0180801 | 0.0193158 | 0.936028 |
| 相同 28 个批次、各组共同等权 | 0.343251 | 0.0210437 | 0.0184166 | 1.142647 |

第二行只重算已有矩阵的均值，未重新预测、未修改基因轴。第一行独立复算与冻结 JSON 一致。等权结果本身也有少细胞批次的噪声，不能取代原报告成为“正确答案”；它证明“误差低于不变化基线”对一个合理的批次权重选择不稳健。

**定位：** `backend/app/services/scientific_analysis.py:394–416` 只取共有批次；`expression_validation.py:125–127` 直接细胞均值；`frontend/src/components/tabs/MeasuredComparisonTab.vue:79–80` 仅凭比值小于 1 给出优势结论。JSON 已有不重加权的 limitation，但该组件不显示它。

**影响：** 研究者可能把批次构成差异当作扰动效应或模型增益，随后据此选验证实验。特别是本例只有约 6.4% 的原始 MSE 改善，不能省略敏感性信息。

**可实施修复：** 保留冻结原始统计；新增明确命名的“批次组成敏感性诊断”，展示各组批次人数、共同权重方案、两种估计和结论是否一致。出现翻转时写“基线结论依赖批次权重”，不要只显示优势颜色。不要把 `gem_group` 自动升级为生物学重复；有实验重复字段时再提供对应分析。

## 2. P1：统一研究结果把已经存在的匹配比较标为不可用

**状态：已确认的接口契约缺陷。**

同一运行：

- `GET /api/v1/runs/run_feb6ebf11ef747ab/comparison`：`status=available`，包含三组群体、表达/DE/代谢指标及来源。
- `GET /api/v1/research/results/prediction/run_feb6ebf11ef747ab`：`availability.comparison.available=false`，reason 为“缺少匹配观测或已确认的真实结果表达尺度”；`groups.control.count=null`、predicted=64。

**定位：** `backend/app/services/research_results.py:281–326` 只读取原运行 `expression_contract.json` 的 `source_scales.observed`，不查询已经验证的派生 comparison。原在线运行确实没有 observed，派生比较另存是合理设计；错误在于把“原运行没有 observed”映射成“这条研究记录没有比较”。`frontend/src/components/ResearchEvidence.vue:36–47` 直接展示这个不可用判断。

**影响：** 同一工作台的证据说明与比较页面互相矛盾；统一导出/后续研究记录使用者无法确定哪个群体和来源才对应当前结论。原群体对照人数缺失还使审阅者无法核对原摘要分母。

**可实施修复：** 在统一契约中分别提供 original 与 matched comparison 的 availability、counts、selection、manifest/hash。仅在 `load_comparison` 验证通过后声明派生比较可用；保留原表达群体语义，不把 535/48/46 偷换成原运行人数。原对照人数应来自已冻结的输入/分析计数，不使用绘图点数推测。

## 3. P1：代谢一致性把大量覆盖不足任务混合成一个“有效任务”指标

**状态：已确认的评价和展示缺口；不是 scCellFie 算法被证明算错。**

新 Jurkat 比较给出 Spearman=0.786296、有效任务=141、排除任务=0。将 `data/derived/comparisons/run_feb6ebf11ef747ab/comparison.json` 的 tasks 与同目录 `metabolic_coverage.csv` 按 task ID 连接，得到：132 个 `insufficient`、2 个 `exploratory`、7 个 `supported`。原输入仅覆盖知识库 138/931 个代谢关联基因。

同一比较的 141 个任务只有 113 种不同的 control/predicted/observed 三元均值（保留 8 位小数）；其中一组数值被 5 个任务共用。因此“141”也不是 141 条独立功能证据。相同模式在现有 Jurkat 256 细胞和 RPE1 案例中存在。

**定位：** `scientific_analysis.py:605–615` 对所有可计算的任务直接汇总指标；`measured_comparison.py:244–251` 和 `116–124` 生成任务比较行时未连接覆盖；`MeasuredComparisonTab.vue:82–87` 的图、表和有效任务数均没有覆盖列或筛选。下载的任务比较 CSV 也没有 coverage/evidence_level。

**影响：** 指标高可能来自少数共有输入基因推动的多项相关派生任务，不能被解释为大范围代谢功能已被预测或验证。RNA 派生分数与实测 RNA 的一致性还不能充当实测代谢通量验证。

**可实施修复：** 不删除历史指标；增加按覆盖分层的任务数量和指标，为每行附覆盖率、缺失基因和输入范围。把“有效”改为“具有有限数值的成对任务”，同时显示知识库总任务数和未评分数。重复评分结构可标记为同组关联证据，不应制造额外独立证据数量。主视图优先可解释的输入完整任务，允许展开其余任务。

## 4. P2：改变预测数量/随机种子，也会改变被用作评价真值的实测群体

**状态：已确认的比较协议问题；不等于两个运行的结果应相同。**

两个已保存的 Jurkat/ALDOA 比较使用同一份 75 细胞实测输入，但：

| 运行 | 请求 | 共同批次 | 最终对照 / 预测 / 实测 |
| --- | --- | ---: | --- |
| `run_feb6ebf11ef747ab` | 64，seed=20261107 | 28 | 535 / 48 / 46 |
| `run_34737097754841fd` | 256，seed=43 | 43 | 817 / 209 / 72 |

**定位：** `scientific_analysis.py:402–406` 取 control、predicted、observed 三者批次交集；predicted 的抽样批次因请求变化，因此评估时观测与对照也被重新截取。当前比较不是一个固定评估总体上的模型参数对比。

**影响：** 用户比较种子、预测数量或模型时，误差变化同时包含“预测变了”和“参考真值群体变了”。例如不能仅凭 0.936 与旧记录 0.861 的比值判断多预测一些细胞提高了准确度。

**可实施修复：** 给每个评价集合冻结 observed/control 的细胞 ID、批次权重和选择指纹；对比多个运行时要求相同指纹，或者明确标注不可直接横比。若预测缺少评价批次，报告覆盖不足，提供共同子集敏感性结果；不要静默把每个运行不同的真值当成统一基准。

## 5. P2：API 中的细胞级 DE 诊断限制没有进入显著性指标展示

**状态：已确认的解释信息丢失；统计单位风险仍需根据真实实验重复信息处理。**

新 Jurkat 比较显示实测显著基因 217、预测显著基因 155、共有 58、共有显著 DEG 方向一致率 1.0。`expression_validation.py:52–75` 对细胞记录做 Wilcoxon；`125–139` 分别计算预测对照、实测对照的检验，`165–168` 已正确声明细胞不是独立生物学重复。

**定位：** `MeasuredComparisonTab.vue:86–88` 展示 Wilcoxon/BH-FDR 和“显著 DEG”但没有呈现 API 的 warnings、`held_out_validation=false`、`training_exclusion_verified=false` 或批次 limitation。统一 ResearchEvidence 有一般性的非留出提示，但它既不替代统计单位说明，也未把比较警告带入当前显著性面板。

**影响：** 用户容易把“58 个共有诊断 DEG 方向全一致”误读为“预测基因方向完全正确”；预测样本数量是人为设置的，增加生成记录不能增加实测的独立证据。

**可实施修复：** 面板紧邻指标显示“细胞级探索性诊断，非生物学重复检验”，显示 `58/217` 等分母，并说明 1.0 只针对共有显著集合；把所有比较 warnings 做中文呈现。未提供重复元数据时优先效应大小和基线误差；不要新增看似精确的生物学显著性。暂不要求复杂统计平台。

## 6. P2：单独下载的比较 CSV 丢失它已经知道的关键溯源信息

**状态：已确认的便携导出缺口；在线 JSON 和完整分析包不能据此判为失去溯源。**

实测 `.../comparison/download?table=genes` 和 `table=tasks` 均成功。CSV 有 population=comparison、counts、units、selection_id，基础做得较好。但其中 `manifest_sha256` 是原预测 manifest `4dfcf455...`，该 manifest 的 observed_sha256=null；CSV 没有完整 comparison_sha256、观测数据 SHA-256、来源 revision、批次选择或诊断限制。selection_id 只含 comparison JSON SHA 的前 16 字符。

**定位：** `export_tables.py:93–145` 实际已经收集 comparison_sha256、selection、warnings；`15–30` 的输出列清单和 `262–267` 的写入却把它们丢掉。任务覆盖缺失另见发现 3。

**影响：** CSV 离开应用、被转交给同学或导入分析脚本后，仅凭文件无法还原这 46 个观测是如何从 75 个中筛选，或独立核对其具体比较来源。原预测 manifest 也不足以解释新增实测值。

**可实施修复：** 增加完整 comparison 指纹与 observed 输入指纹；将表及一份 metadata.json 一起作为轻量 ZIP 导出，元数据包含数据版本、群体选择、批次权重、单位、限制和完整 hash。若保留单 CSV，至少增加完整 comparison_sha256、protocol_status 和指向配套 JSON 的明确说明。

## 最小修复顺序与验收

1. 先处理发现 1、2：展示批次敏感性并统一 original/comparison 契约；不能改写旧 manifest 或把新诊断冒充当时冻结的指标。
2. 接着处理发现 3、5：覆盖分层与统计单位说明进入页面和导出。验收至少使用当前 Jurkat 的 132/2/7 分层和 58/217 分母。
3. 处理发现 4、6：冻结可比较的评价选择指纹，补齐便携导出元数据。此后再安排少量固定公开案例验证实用性，不需要先扩大模型规模。

本次没有确认预测表达伪造、量纲被重复归一化、原始输出 hash 不一致或把实测分析当作新模型预测。也没有验证四个模型对所有支持组合的性能、官方训练排除情况、独立生物学重复或真实湿实验效应。这些属于证据边界，不应写成已发现的系统错误。

## 只读复算脚本

在活动项目根目录使用 `.\.venv\Scripts\python.exe -B` 执行以下代码。仅读取已有 H5AD、面板和比较 JSON、输出数值；不导入业务服务、不生成文件、不启动预测。依赖活动环境已有的 anndata/numpy。输入 SHA 可在对应预测 manifest 和 comparison manifest 中核对。

```python
from pathlib import Path
import json
import numpy as np
import anndata as ad

root = Path(r'D:\全球校园人工智能精英大赛\celllens-national')
run = 'run_feb6ebf11ef747ab'
panel = [s.strip().upper() for s in
         (root / 'data/registry/state_jurkat_genes.txt').read_text().splitlines()
         if s.strip()]
assert len(panel) == 2000 and len(set(panel)) == 2000
frames = {
    'control': ad.read_h5ad(root / 'data/raw/replogle-jurkat/control.h5ad'),
    'predicted': ad.read_h5ad(root / f'data/derived/runs/{run}/predicted.h5ad'),
    'observed': ad.read_h5ad(root / 'data/raw/measured-comparison-v1/jurkat/ALDOA.h5ad'),
}
# STATE 保存了模拟对照和模拟处理；只保留目标处理，复现原分析契约。
p = frames['predicted']
frames['predicted'] = p[p.obs.gene.astype(str).str.upper() == 'ALDOA'].copy()
assert {k: a.n_obs for k, a in frames.items()} == {
    'control': 1024, 'predicted': 64, 'observed': 75}
common = sorted(set.intersection(*[
    set(a.obs.gem_group.astype(str)) for a in frames.values()]))
assert len(common) == 28
pooled, equal_batch, frequencies, counts = {}, {}, {}, {}
for name, a in frames.items():
    a = a[a.obs.gem_group.astype(str).isin(common)]
    counts[name] = a.n_obs
    # 对照和预测的 X_hvg 使用注册面板顺序；观测 X 按同一面板重排。
    if 'X_hvg' in a.obsm:
        x = a.obsm['X_hvg']
    else:
        names = a.var.get('gene_symbol', a.var_names).astype(str).str.upper().tolist()
        positions = {g: i for i, g in enumerate(names)}
        assert len(positions) == len(names)
        x = a[:, [positions[g] for g in panel]].X
    x = x.toarray() if hasattr(x, 'toarray') else np.asarray(x)
    assert x.shape[1] == 2000 and np.isfinite(x).all()
    batch = a.obs.gem_group.astype(str).to_numpy()
    pooled[name] = x.mean(axis=0)
    equal_batch[name] = np.mean([
        x[batch == g].mean(axis=0) for g in common], axis=0)
    frequencies[name] = a.obs.gem_group.astype(str).value_counts(
        normalize=True).reindex(common, fill_value=0).to_numpy()
assert counts == {'control': 535, 'predicted': 48, 'observed': 46}

def metrics(means):
    pred = means['predicted'] - means['control']
    obs = means['observed'] - means['control']
    mse = float(np.mean((pred - obs) ** 2))
    baseline = float(np.mean(obs ** 2))
    return {'pearson': float(np.corrcoef(pred, obs)[0, 1]),
            'mse': mse, 'no_change_mse': baseline,
            'mse_relative_to_no_change': mse / baseline,
            'direction_agreement': float(np.mean(np.sign(pred) == np.sign(obs)))}

frozen = json.loads((root / f'data/derived/comparisons/{run}/comparison.json').read_text())
original = metrics(pooled)
assert abs(original['mse'] - frozen['expression']['mse']) < 1e-7
assert abs(original['pearson'] - frozen['expression']['signed_delta_pearson']) < 1e-6
print('selected_cells', counts, 'common_batches', common)
print('batch_frequency_total_variation_control_observed',
      float(np.abs(frequencies['control'] - frequencies['observed']).sum() / 2))
print('pooled_cells', original)
print('equal_batch_weight_sensitivity', metrics(equal_batch))
```

公式：每组先得到每个批次的 2000 维表达均值；敏感性估计为这 28 个批次均值的简单平均。预测变化和实测变化分别减同口径 control 均值；MSE 对 2000 个基因平均，不变化基线为实测变化平方均值。这里没有对基因、细胞或批次做显著性检验。

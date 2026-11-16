# 科研与结果实现验收

验收对象为 `D:\全球校园人工智能精英大赛\celllens-national` 的当前活动源码，时间为 2026-11-07。本次作为独立复核，先对照 `science-review.md`、`cell-review.md`、`修复清单.md`、`cell-fixes.md` 核查规格，再检查实现与隔离测试。没有修改生产代码、提交新真实分析、重启服务、安装依赖或执行 Git 提交；没有用旧 8028 构建页面判定新代码缺陷。

结论：核心科研来源、冻结结果与交互契约已落实。发现的 1 项 P2（比较页将 `supported` 误称为“输入完整”）已由实现代理修复并完成措辞复核，当前检查范围内没有待处理的 P1/P2。以下结论是源码、隔离测试与冻结产物读取证据，不替代统一构建后的浏览器/WebGL验收，也不是独立科学泛化验证。

## 第一阶段：规格对照

| 要求 | 当前实现与验收结果 |
|---|---|
| 原运行与匹配比较分开 | `research_results.py` 保留 `groups` 与 `populations.original`，另外提供 `matched_comparison` 的计数、选择与独立指纹。前端总览使用明确的当前群体说明，详细表达/功能标签另提示原群体。统一结果仅在校验后的 `load_comparison` 成功时声明派生比较可用。 |
| 不以请求数或投影点数冒充原群体分母 | 原计数读取冻结契约及可核验的逐细胞评分行，检查重复来源身份与计数冲突；未记录时仍保留未知。 |
| 批次敏感性另存，历史结果不覆写 | `comparison-diagnostics-v2` 在独立目录保存清单和诊断；准备函数先复现冻结均值/指标，核对来源哈希，再原子发布。GET 路径只读 sidecar，未准备时明确不可用。 |
| 评价总体指纹 | 指纹包含对照/实测输入 hash、基因轴、批次、排序后的细胞身份和权重；不含 run ID。相同参考总体不因预测记录名称而产生伪差异；实际参考细胞改变会改变指纹。 |
| 低覆盖任务与重复评分结构 | 覆盖只连接本次 comparison 清单绑定的 `metabolic_coverage.csv`；显示分层数量、完整知识库任务数、未评分数及缺失成员。显式准备后提供分层指标和 8 位小数三元均值分组，说明不同组也不是独立证据。层级中文标签已按下述复核修正。 |
| 细胞级 DE 解释 | 比较页在指标附近显示细胞级探索性诊断、非生物学重复检验、共有显著集合分母、训练排除未核验与非留出限制。 |
| 便携导出 | 比较 CSV 增加完整 comparison/manifest/observed/diagnostics/reference 指纹、源 revision、选择 JSON、警告 JSON 与配套 JSON 地址；任务 CSV 附本次覆盖、缺失成员与评分结构。未准备字段保留空值。 |
| 固定坐标与身份 | 两投影组件均用全部有限坐标计算固定 x/y 轴域，群体筛选只改序列；双轴 `filterMode: none`，复位重置所有缩放轴。tooltip 保留来源与 cell_id，并转义外部身份文字。 |
| 当前研究选择 | 父页面接收 projection/layer/group；记录改变清空选择。表达投影筛选仅进入对应标签的上下文；旧任务明确呈现为保留上下文。 |
| ER/Golgi 导航 | 只匹配原始 System 值 `Processing in the ER` / `Processing in the Golgi`，且至少存在一个有限评分；零评分保留。未根据 ENERGY METABOLISM 推定线粒体定位。 |
| 实测任务成员证据 | 新接口先验证实测结果身份，随后核对知识库 manifest 版本及五个关联文件的 SHA-256；提供任务→反应→GPR/基因及零值/缺失值，声明知识关联并非因果验证。 |
| 结构资源与异步返回 | CellScene 使用存活标志和代数防止卸载后的异步挂载；销毁清理监听与 WebGL 资源。缩放有范围限制，2D/3D 往返保留选择、暂停与缩放状态。实际视觉行为留待浏览器验收。 |
| public/private 边界 | public 统一结果不会读取私有 comparison，比较准备/下载接口拒绝 public，研究导出不含私人笔记；实测成员证据路由不在公开白名单。路径/敏感字段经既有脱敏器处理。 |

## 第二阶段：确认的问题

### P2：supported 层级被错误标成输入完整（已修复）

定位：验收时 `frontend/src/components/tabs/MeasuredComparisonTab.vue:41` 默认筛选 `evidence_level === 'supported'`；`:54` 将其翻译为“输入完整”，`:108`、`:111` 再宣称“输入完整项”。但 `backend/app/services/scientific_analysis.py:526` 实际定义 `supported` 为 `gene_fraction >= 0.8`，`exploratory` 为 `>= 0.6`。

可复现条件：评分存在且覆盖率为 0.8–0.99 的任务合法属于 supported；当前前端会在同一行显示覆盖不足 100% 和“输入完整”，并把它归入“仅显示输入完整项”。这会把层级阈值解释成全部成员齐全。当前 Jurkat 的 7 项恰好均为 1.0，不能据该案例推广层级含义。

最小修复：将 supported 文案统一改为“较高覆盖（≥80%）”，默认筛选说明同步；若要使用“输入完整”，需另用 `coverage === 1` 分类且保留 supported 的原始意义。无需更改冻结评分或覆盖文件。

修复复核：当前 `MeasuredComparisonTab.vue:54` 已显示“较高覆盖（≥80%）/探索性（60%–<80%）/覆盖不足（<60%）”，`:108` 计数说明和 `:111` 默认筛选说明同步修改；文件已无“输入完整”文字。该修复不改变评分、阈值或 sidecar。此项关闭，最终浏览器措辞由主代理随统一构建验收。

## 执行证据

- `python -B -m pytest backend/tests/test_measured_trace.py backend/tests/test_research_projection.py -q`：15 passed。
- `python -B -m pytest backend/tests/test_scientific_contract_repairs.py -q`：8 passed。覆盖显式准备/只读 GET、历史文件不变、重复身份拒绝、零基线/常量向量返回未定义、参考指纹稳定性、篡改拒绝、原/匹配隔离、公私边界及 CSV 追溯。
- `node scripts/test-research-canvas.mjs`：固定轴、有限坐标、显式结构分类、零分、tooltip 转义、选择上下文、记录重置与缩放复位通过。
- `node scripts/test-run-overview.mjs`：原/匹配隔离、缺失任务、面板覆盖、目标存在性、AI 群体与公开只读读取通过。
- `node scripts/test-result-overview.mjs`：有限/缺失值、覆盖排序、正负共同尺度及实测独立显示通过。
- `node scripts/test-national-research.mjs`：16 项通过，包括异步过期返回、保存/导出取消及研究选择隔离。

后端警告为测试框架弃用提示，以及重复细胞身份负例触发的 AnnData 提示；没有测试失败。上述前端脚本运行 Vue setup/业务逻辑，不是图形渲染验收。

独立读取冻结实测 `measured_00c6134fec4544efb1ad3b6d`，先执行 `verified_result` 检查源与产物，再调用 `measured_task_evidence`。任务 `Conversion of glycine to pyruvate` 返回 1 个关联反应、1 个关联基因，覆盖 1/1；对照 0.4035407064、实测 0.4266808574、差值 0.0231401509，知识库 `scCellFie-0.6.2-human-Recon2`。清单 SHA-256 为 `661c973e1748ad88b5a0b22a632c4fa3a5ab517ea57a1e260f90260efd0a1421`。此次仅读取既有数据，未创建分析。

独立读取三个 v2 sidecar，逐文件比较读取前后的原运行目录与 comparison 目录哈希，全部保持一致：

| 运行 | 原汇总误差比 | 批次等权误差比 | 基线方向一致 |
|---|---:|---:|---|
| `run_feb6ebf11ef747ab` | 0.9360281572 | 1.1426468307 | 否 |
| `run_34737097754841fd` | 0.8612883843 | 0.9063466943 | 是 |
| `run_aef55809479e4c21` | 0.2085343503 | 0.2210245162 | 是 |

三个案例均为 141 个有限成对任务、知识库 218 项、未评分 77 项；supported/exploratory/insufficient 为 7/2/132，三元均值按 8 位小数为 113 组。两个 Jurkat 运行的参考选择指纹不同，当前实现没有将它们声明为同一评价总体。数值是已有数据的敏感性诊断，不是独立验证或模型总体有效性结论。

## 验收边界

本次没有进行最终构建页面、390 px/暗色、真实 WebGL context loss、触屏与键盘缩放的视觉验收。逐点身份当前通过 hover 查看，未实现点击固定详情或保存逐细胞子集；本轮没有承诺这类后端选择契约。未重新训练模型、提交预测、重跑真实投影或修改冻结文件。

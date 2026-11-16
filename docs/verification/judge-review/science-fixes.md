# 科研功能修复

工作目录：`D:\全球校园人工智能精英大赛\celllens-national`。依据同目录 `science-review.md` 的六项发现修复。没有运行 STATE、安装依赖、修改旧预测/比较结果或 manifest，也没有重启服务。本文的数值来自本地真实冻结文件和当前代码的直接读取；部署后的 HTTP 与浏览器验收由总体验收记录补充。

## 实现与证据

### 1. 批次敏感性单独准备、单独保存

新增 `backend/app/services/comparison_diagnostics.py`，当前产物版本为 `comparison-diagnostics-v2`。新诊断位于 `data/derived/comparison_diagnostics/comparison-diagnostics-v2/<run_id>/`，包含自己的 `diagnostics.json` 和 manifest。开发时产生的 v1 留在独立目录，当前读取器不采用 v1，不覆写任何旧文件。

- `load_comparison`、统一研究结果和 CSV GET 仅校验与读取已有产物。没有诊断时返回 `batch_sensitivity.status=unavailable` 和原因，读取不会打开表达矩阵或产生新计算。
- `POST /api/v1/runs/{run_id}/comparison/diagnostics/prepare` 是显式准备入口；复用同源校验、现有工作区访问策略，公开模式禁止，API 进程内串行准备。离线也可直接调用 `prepare_diagnostics(root, run_id)`。
- 准备只读取冻结 manifest 绑定的 control/predicted/observed、面板与表达契约。必须都是已确认的 `log1p_cp10k`；按冻结扰动选择与共同批次复现原始群体。检查来源内细胞 ID 唯一、实测对照与扰动 ID 不重叠、同一基因轴和有限值。
- 用比较自身受 SHA-256 约束的 `gene_identity.json` 还原来源到分析基因的映射。Jurkat 中有 7 个线粒体基因改名（例如 `MT-CO1 → COX1`）；这里不重新查询注册库，也不改变表达值。
- 先验证三组细胞均值逐基因复现旧表，再验证冻结 pooled MSE、baseline、比值与 Pearson。随后才计算共同批次等权均值。零基线的比值和常量向量的 Pearson 返回 null，明确未定义原因。
- 原 `comparison.expression` 不变；新增 `batch_sensitivity.pooled_cells` 与 `equal_batch_weight`、批次人数和频率总变差。诊断 hash 或来源绑定失败时原冻结比较仍可读取，新增诊断显示 invalid 与原因。

真实文件复算结果如下。三例准备前后，原运行和原 comparison 目录文件 SHA-256 均未变化。

| 运行 | 原细胞汇总 MSE 比值 | 共同批次等权 MSE 比值 | 基线判断一致 |
| --- | ---: | ---: | --- |
| `run_feb6ebf11ef747ab` | 0.936028157 | 1.142646831 | 否 |
| `run_34737097754841fd` | 0.861288384 | 0.906346694 | 是 |
| `run_aef55809479e4c21` | 0.208534350 | 0.221024516 | 是 |

第一例等权 Pearson 为 0.343251049。与审查报告 `0.936 → 1.142647` 一致。原冻结 MSE 比值为 0.936027927；独立矩阵均值复算的约 2.3e-7 差异来自浮点汇总，旧指标没有被替换。

比较页面紧邻原基线显示“基线结论依赖批次权重”，提供两种估计与各批次人数，明确小细胞批次的噪声、gem_group 不能直接视作生物学重复。未准备的历史记录显示准备按钮及原因。

### 2. 原群体与匹配群体分别建契约

`ResearchResults.groups` 保持原运行语义；原对照数从受冻结 manifest 约束的逐细胞分析行读取，拒绝重复/未知来源或与已存计数冲突，未使用投影点数。

- `populations.original`：availability、groups、原选择和原 manifest/文件指纹。
- `populations.matched_comparison`：仅在 `load_comparison` 验证后声明可用，另存 groups、选择、完整 comparison/manifest hash、实测来源、诊断和警告。
- 真实 Jurkat 原群体为 **control=1024、predicted=64**；匹配群体为 **535 / 48 / 46**。统一 `availability.comparison.available=true`，两个群体没有混用。
- 公开模式在调用比较读取器之前分支退出，不读取私有 comparison 或扩大公开允许路径。
- 总研究指纹绑定原指纹、完整 comparison/manifest hash 与已验证诊断 hash；各群体的原指纹分别保留。新保存的发现因此绑定用户实际看到的比较证据；旧笔记不改写，导出可标记指纹不一致。
- 有匹配比较时允许保存 observed 群体发现；observed 与原预测投影的组合仍被拒绝。

### 3. 每个任务使用比较自身的覆盖信息

比较任务行连接同一比较目录受 manifest 绑定的 `metabolic_coverage.csv`，新增 `coverage`、`evidence_level`、`missing_genes`、`coverage_source`、`input_scope`，不引用原运行另一个群体的面板。

真实 Jurkat 的 141 个有限成对任务中，**7 个较高覆盖 / 2 个探索性 / 132 个覆盖不足**；知识库总任务 218，未评分 77。新增按覆盖层级的数量和描述性 Spearman/MAE；原汇总指标保留并注明包含覆盖不足任务。层级阈值按现有评分契约：supported ≥80%，exploratory ≥60% 且 <80%，insufficient <60%；本例 7 个 supported 恰为 100%，但通用文案不将 supported 等同输入齐全。

8 位小数下有 113 种三元均值，每行附相同评分结构组 ID 和组内任务数。页面说明这些结构并不构成独立性证明，不将 141 当独立功能证据。默认图表只显示较高覆盖项（≥80%），可展开其余任务；覆盖率、层级和缺失基因进入逐项表。只有 2 个任务的 ±1 相关系数旁明确提示小样本描述性及任务共享输入问题。

### 4. 参考群体选择指纹

诊断冻结 control/observed 的源输入 hash、选中细胞 ID、批次、两种权重、基因轴和来源映射指纹。`reference_selection_sha256` 不纳入 run ID、预测输出或含 run ID 的 gene_identity 整文件 hash；后者仅保留作产物审计。这样相同参考总体跨运行可以得到相同指纹，改变实测细胞则改变指纹。

真实两个 Jurkat 运行的参考指纹分别为：

- 64 记录：`67c54215a774edf9513985d733d102122e8af08adfbc4da708d67357f79caa11`
- 256 记录：`a03fc8521d85a24ccef67dae2029b36b09f57a75d6ae911a60e17661ec34d25b`

界面和导出明确“仅相同参考群体选择指纹、基因轴与权重协议可横比；seed/n 可能改变真值”。本修复冻结并暴露现有评价选择，**没有重做固定总体的模型基准或宣称不同运行可直接比较**。

### 5. DE 解释贴近指标

比较页面将 DE 命名为“细胞级探索性诊断”，指标旁明确非生物学重复检验、生成数量不增加实测证据、未建立独立留出、训练排除未核验。直接呈现 **58 / 217**，方向一致率 1.0 仅作用于 58 个共有诊断显著基因，不是全部基因正确率。当前全部 6 条英文比较警告都有中文释义；未知新增警告保留原文并标记为来源提醒，避免静默丢弃。

### 6. 便携 CSV 补全来源

保持旧列兼容，增加完整 `comparison_sha256`、`comparison_manifest_sha256`、`observed_sha256`、source revision、protocol status、reference selection hash、diagnostics hash、选择 JSON、警告 JSON、配套 JSON 的 `metadata_url`。任务 CSV 同时加入覆盖与重复评分结构字段。使用已有 JSON 下载作为完整配套元数据，没有额外扩张为新的 ZIP 产品。

真实导出核验：基因 2000 行、任务 141 行；两份 CSV 都包含原比较 hash `2f7e529e…b606dc`、观测 hash `734e59f7…95657b`、来源 revision `d790193b…44da5` 及 v2 参考/诊断完整指纹。精确值见 `science-diagnostics-check.json`。

统一研究 JSON 导出也已分群体：兼容保留原 `tables` 键，但 `tables_population`、`summary_population`、`source_manifest_population` 和逐表 `population` 均明确为 `original`；另设 `population_exports.matched_comparison` 保存匹配群体自己的成对表、选择、指标、诊断和完整指纹。导出期间再次核验 comparison/diagnostics 绑定，避免把原群体数值挂到匹配群体名下。公开模式不读取或导出私有匹配表。

## 全量回归发现的兼容修复

总体验收发现的 15 个交换包失败来自离线 fixture 容器未定义 `api_prefix`。表元数据读取现在使用可配置前缀，缺省时采用服务既有 `/api/v1`；新增测试同时验证缺省和自定义前缀，未跳过任何来源或数值检查。另一个 assistant 断言更新为新真实行契约：缺比较覆盖信息必须为 `coverage=null`、`evidence_level=unknown`；原任务数值、匹配群体和不回退原摘要的断言全部保留。

按总体验收追加要求，科研助手上下文现纳入经过验证的批次敏感性、精简评价协议和任务覆盖分层，并引用 comparison、coverage、diagnostics 及其 manifest 的完整 hash。只传统计摘要，不传完整选中细胞 ID、批次逐细胞组成或矩阵；保留原 48,000 字节上限。解读约束明确基线翻转不能解释为稳定增益，缺诊断不能补写结论，有限任务数不是独立证据。没有更改外部模型连接配置，也没有把真实数据发送给外部服务。

真实 Jurkat 的本地只读上下文为 **23,875 字节**，包含 `baseline_conclusion_consistent=false`、0.936028/1.142647 及完整参考指纹。实际统一 JSON 导出同时保留原群体 1024/64 与匹配群体 535/48/46，分别列出原表和匹配 2000 基因/141 任务表。见 `science-export-context-check.json`。

兼容修复后，交换包、助手图表、科学契约及原比较/CSV/研究契约共 **95 passed**；随后新增助手翻转场景和精简上下文后，助手图表与科学修复两文件再运行 **23 passed**。新用例还验证诊断被篡改后拒绝旧上下文解读、没有上游网络调用、上下文不泄漏细胞 ID，并保持字节上限。新增改动的 Ruff 和 scoped basedpyright 通过。未在此子任务重复全量后端测试，由总体验收统一执行。

## 验证

- `python -m pytest backend/tests/test_scientific_contract_repairs.py backend/tests/test_measured_comparison.py backend/tests/test_export_tables.py backend/tests/test_research_contract.py -q`：**60 passed**。警告为已有 TestClient 依赖弃用和特意构造重复 ID 的拒绝用例。
- 新增 8 个有语义的回归：独立矩阵手算、显式准备/只读、原产物不变、重复细胞拒绝、零基线/常量向量、篡改拒绝、原/匹配分离与公开不读取、发现指纹与投影限制、参考指纹跨 run 稳定且真值变化时改变、CSV 来源和自身覆盖、同源/公开禁止/串行准备（部分场景合并在同一个测试中）。
- 所改服务/API 的 Ruff 检查通过；scoped basedpyright **0 errors / 0 warnings**。
- `npm --prefix frontend run typecheck`：通过。
- 三个真实案例直接准备/读取通过；真实统一契约与两份 CSV 已按上述人数、行数、hash 和分层断言。
- 没有在本子任务重启服务或做浏览器视觉验收。总体验收负责构建、部署与端到端验证。

## 保留的科学边界

批次等权是敏感性分析，不是真值纠正；其少细胞批次噪声仍在。当前实现有意仅接纳冻结 `log1p_cp10k`、唯一基因映射且可复现旧表的输入，其他尺度或不完整契约返回明确原因，不做推测性转换。没有新增生物学重复、训练排除证据、独立留出验证或实测代谢通量，已有模型能力范围也没有因此扩大。

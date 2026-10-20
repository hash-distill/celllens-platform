# 接口说明

默认 API 前缀 `/api/v1`。运行模型定义在 `backend/app/schemas.py`，辅助解读接口位于 `backend/app/assistant.py`。完整结构见 [openapi.json](openapi.json)；服务的 `/openapi.json` 是实时契约。

## 真实观测比较

`GET /api/v1/runs/{run_id}/comparison` 返回独立冻结的真实观测比较；`status=available` 时包含完整基因/任务三组均值、差值、表达/DE/任务指标、批次群体、来源和绑定哈希。`preparing` 表示比较准备中，可重试读取；`unavailable` 不含伪造指标，明确说明缺少观测或准备失败。冻结来源变化返回 409 `COMPARISON_SOURCE_CHANGED`。

`GET /api/v1/runs/{run_id}/comparison/download?table=json|genes|tasks` 下载同一核验结果，保留全部有效成对记录及合法零变化；无可用比较返回 404。该比较不改写旧 `/genes`、`/validation` 或原运行文件，评价子集与全量摘要可不同。

扰动目录新增 `measured_comparisons`，仅列当前背景、模型支持且已通过源文件哈希核对的实测扰动与细胞数。比较过程为匹配观测诊断，`held_out_validation=false`。详见[使用说明](guide/MEASURED_COMPARISON.md)。

## 大模型辅助解读

所有辅助解读响应标记 `Cache-Control: no-store`；POST 拒绝跨站浏览器请求并限制请求体为 64 KiB。无需账户，密钥由调用者随请求提供，不保存到数据库。

| 接口 | 行为 |
|---|---|
| `GET /assistant/capabilities` | 返回提供商预设（ID、名称、地址、协议、预算字段）、允许的服务 origin、超时与只读标记 |
| `GET /assistant/context?source_kind=run&source_id=run_...` | 根据已保存扰动实验结果构建摘要；`source_kind` 仅接受 `run` |
| `POST /assistant/test` | 使用指定模型发送简短连接检查，可能消耗额度 |
| `POST /assistant/interpret` | 校验预览摘要的哈希后调用模型；不更改科学结果 |

连接请求字段：`provider`（`openai` / `gemini` / `anthropic` / `deepseek` / `siliconflow` / `custom`；缺省 `custom` 以保留旧版兼容协议请求）、`base_url`（最多 512 字符）、`model`（1–128）、`api_key`（1–4096）、`max_tokens`（256–8192，默认 2048）、`token_parameter`（`max_completion_tokens` 默认，或 `max_tokens`）。额外字段拒绝，校验错误统一脱敏。

Claude 使用原生 `/messages`、`x-api-key` 与 `anthropic-version: 2023-06-01`，系统提示单独传入 `system`；其文本块、结束原因与 token 用量归一化为统一响应。Gemini 使用官方兼容 `/chat/completions`。Gemini、Claude、DeepSeek 与硅基流动使用 `max_tokens`；OpenAI 与 custom 使用选择的 `token_parameter`。除管理员额外信任的代理外，预设提供商的地址必须匹配对应官方 origin，避免将密钥发给错误提供商。

解读请求增加 `source_kind`（仅 run）、`source_id`、`context_sha256`（来自预览的 SHA-256）和 `purpose`（interpret / coverage / next_steps，默认 interpret）。客户端不能提交自定义科学上下文、文件路径或模型工具指令。

响应包含 `text`、调用的 `provider` / `model` / `base_url`、`finish_reason`、`generated_at`、服务返回的 token `usage`；解读另带来源、任务和摘要哈希。`length` 表示可能截断。未完成或改变的产物返回 409；缺失记录返回 404；不允许或不匹配的地址返回 422；并发繁忙返回 429；上游错误返回 502；超时返回 504。不会自动重试。

详情见 [设置与辅助解读](guide/ASSISTANT_SETTINGS.md)。

## 创建与查询运行

先查 catalog 获取在线就绪状态与支持扰动，再创建运行；取得编号后轮询状态，进入 completed 再读取产物。

```json
{
  "cell_line": "K562",
  "perturbation": "MYC",
  "mode": "online",
  "n_cells": 64,
  "seed": 42
}
```

| 字段 | 约束 |
|---|---|
| `cell_line` | K562、RPE1、Jurkat 或 HepG2；实际可用性由 catalog 与已校验资产决定 |
| `perturbation` | 1–64 字符，字母/数字/下划线/点/连字符；自动转大写，在线请求须在支持列表 |
| `mode` | 新建运行仅接受 online（默认）；其他旧值返回 422 EXPERIMENT_MODE_REMOVED |
| `n_cells` | 64–4096，默认 512；请求推理细胞数，不是质量指标 |
| `seed` | 0–2147483647，默认 42 |

额外字段被拒绝。POST /runs 成功返回 202 和 `run_id`、`status`、`cache_hit`。缓存命中可直接返回 completed，不一定经过可见的排队过程。

| 模式 | 行为 | 依赖 |
|---|---|---|
| online | STATE 预测与转录/代谢分析，不读取匹配观测 | MySQL、worker、GPU、模型及对照 |

运行查询返回请求、状态、`stage_progress`、时间、warnings 和错误信息。状态枚举为 queued、state_running、adapting、metabolic_running、validating、completed、failed。进度来自后端节点；completed/failed 为终态。

## 历史实验检索

`GET /api/v1/runs?limit=20&offset=0&q=AAMP&status=completed&mode=online` 从服务器数据库读取历史记录。`limit` 为 1–100（默认 20），`offset` 非负；`q` 最长 128 字符，对运行编号、背景、扰动进行不区分大小写的包含检索，百分号等作为普通字符。`status` 为 all/active/completed/failed，active 包含所有非终态；`mode` 可省略或指定 online/precomputed/validation。`total` 是筛选后的完整数量。浏览器存储不决定此列表，接口不提供删除操作。

## 接口列表

`GET /api/v1/runs/{run_id}/completeness` 返回保存并登记的 scCellFie 官方数据集级完整性报告：方法名、包版本、参数、函数源码与源基因文件哈希、冻结数据库来源、overall_summary、完整 tasks/reactions 明细。全部关联基因和 essential 基因范围同时保留；essential 空集返回 1 是官方约定，不表示完整证据。缺失产物返回 404，未登记、哈希变化或跨运行报告返回 500 `INVALID_COMPLETENESS`。读取不会即时补算或替换数据库。`metabolic-tasks` 响应的 `completeness_available` 用于避免请求已知缺失的报告。

旧 `coverage`、`evidence_level` 与三档计数仍保留兼容性，表示项目 80%／60% 规则，不是官方完整性、置信度或论文标准。新报告使用官方连续指标，未建立官方指标的项目分档门槛。

`GET /api/v1/coverage` 返回独立覆盖目录，默认使用首个已启用模型的基因面板。可选 `cell_line` 或 `run_id`，两个来源参数互斥。模型来源每次校验登记的基因文件与冻结数据库哈希，官方统计按面板和数据库清单缓存；读取不执行模型推理、不创建实验。实验来源读取已保存且哈希有效的报告和实际基因面板；报告与当前冻结数据库不一致返回 409，不套用当前模型结果。

目录在官方报告上增加 `source`、已启用 `models`、全部代谢库 `genes`，以及任务的 `coverage_status`（full / partial / absent / unmapped）、分类与 `present_genes_all`。基因条目包括符号、HGNC 身份、`in_panel` 和关联任务/反应。完整报告保留全部 tasks/reactions；这些条目是覆盖清单，不表示全部条目均有评分。响应不缓存到浏览器；无可用模型返回 404，来源冲突返回 422，面板或数据库校验失败返回 503。

覆盖目录另含 `gene_categories`、`classification`，基因条目增加 PANTHER 蛋白功能 `category_ids`、原始 `protein_classes` 与 HGNC 英文名称；任务增加双语 `guide`（当前七项已核验介绍）。页面和下载仅展示覆盖项，API 保留原始明细供来源核验。`GET /catalog/perturbations` 保持原 `items` 可用目标列表，同时返回逐基因 `genes`、当前类别 `categories` 与分类来源；分类为多标签，按显式 HGNC ID 对齐，批准符号优先于唯一旧名/别名，未知功能不凭名称猜测。快照损坏时扰动列表仍可读取，分类明确不可用，不删除目标。

路径均相对 `/api/v1`。

| 方法 | 路径 | 内容与注意事项 |
|---|---|---|
| GET | `/health` | 服务及数据库状态，需读取响应字段 |
| GET | `/ready` | 数据库与 worker/GPU 开关；未全部满足返回 503 |
| GET | `/catalog/contexts` | 在线就绪状态、模型 ID 及原因；旧 validation_ready / precomputed_ready 兼容字段固定 false |
| GET | `/catalog/perturbations?cell_line=K562&mode=online` | `{cell_line, mode, items}`；online 为模型支持扰动；旧 precomputed / validation 查询返回空列表 |
| GET | `/runs` | 服务器历史实验；按创建时间及编号倒序，返回 items/total/limit/offset，支持分页及检索筛选 |
| POST | `/runs` | 创建运行，成功返回 202 |
| GET | `/runs/{run_id}` | 请求、运行阶段与错误 |
| GET | `/runs/{run_id}/summary` | 汇总；未完成时可返回状态和空结果 |
| GET | `/runs/{run_id}/projection` | `{method, seed, points}`；合成单细胞演示另含 data_kind、input_sha256、generator 和可选的历史补充来源；点含 x/y/source/cell_index，默认最多 12000 点；新版在线分析另含 `population_selection`，记录目标扰动筛选的输入、保留与排除细胞数 |
| GET | `/runs/{run_id}/genes?limit=2000` | CSV 行转 JSON；gene/control/predicted/predicted_delta 与可选观测列，数值可能是字符串 |
| GET | `/runs/{run_id}/cell-state?feature_kind=gene&feature_id=ENO1&embedding=umap` | 只读科研视图：space 为 expression/metabolic，默认 expression；metabolic 须使用 feature_kind=task，坐标由完整且对照有变化的逐细胞任务分数按对照标准化后计算，无缺失插补；返回 embedding_space/embedding_preprocessing；embedding 为 pca/umap，默认 pca；PCA 使用共同对照参考，UMAP 在各来源的对应空间多维主成分上联合拟合，返回参数与版本，解释方差为空；显示点、完整群体 ECDF/统计、共享坐标与色标、来源核对；指标为空时选默认指标；无法核对冻结来源返回 409 CELL_STATE_UNAVAILABLE |
| GET | `/runs/{run_id}/cell-state/figure?feature_kind=gene&feature_id=ENO1&embedding=umap&file_format=svg` | 同数据 Matplotlib 图下载；space/embedding 与数据端点一致，文件名及图注区分表达/代谢；embedding 默认 pca，支持 svg/pdf/png（300 dpi）；坐标轴、图注与下载文件名区分 UMAP/PCA；响应头 X-CellLens-Manifest-SHA256 为来源哈希；不修改运行、不重新推理或评分 |
| GET | `/runs/{run_id}/metabolic-tasks?limit=1000` | 默认 scope=top 返回 Top 20；scope=all 从本次任务矩阵和覆盖表读取完整有效结果，缺少产物或旧 precomputed 长表格式时明确返回 scope=top 已保存摘要 |
| GET | `/runs/{run_id}/reactions?limit=1000` | 真实矩阵按来源取均值，再按绝对差异排序；其他 CSV 格式可能有不同列 |
| GET | `/runs/{run_id}/task-trace?task_id=...` | 读取本次冻结的任务—反应—基因知识关联及对照/预测/差值；reaction_limit、gene_limit 默认 30，范围 1–100 |
| GET | `/runs/{run_id}/provenance` | 本次 manifest 的历史模型/数据 ID、资产/代码/清单哈希及时间；不返回本机路径 |
| GET | `/runs/{run_id}/validation` | 已生成的验证指标，缺失返回 404；protocol_status=unconfirmed，不能视为正式验收 |
| GET | `/runs/{run_id}/report` | PDF 附件下载；包含实验参数、主要基因与代谢任务结果、来源和已准备的科研图 |

三类表格返回 `{items, limit, truncated}`，limit 均允许 1–10000。truncated=false 只表示接口未因 limit 截断，不证明摘要包含全部任务。真实基因表保持输出顺序，接口不会按效应大小排序。

新建运行仅支持 online。已移除的 precomputed / validation 请求在创建记录或入队前返回 422 `EXPERIMENT_MODE_REMOVED`，对应目录查询不再提供目标。历史记录保留原模式与来源，仍可按旧模式检索并读取已保存产物。在线运行发布前校验投影并登记哈希，不完整缓存不得复用。

历史运行的可选 `result_kind` 保留：`frozen_model_result` 为保存的真实结果，`synthetic_demo` 为历史合成数据。provenance 中的原运行编号、原始清单及资产哈希继续可查。读取这些记录不执行推理，不新增回放任务，也不修改保存结果。

metabolic-tasks 另返回 scope、total；全量分支返回 excluded_count，排除预测变化为非有限数值的任务，绝不将其替换为零。scope=all 表示完整有效变化集合，覆盖摘要的任务计数仍包含证据不足或不可计算任务。

任务列表还返回 `reactions_available`，各任务返回 `trace_available`：`false` 表示对应保存结果缺失，前端直接展示缺失说明，不请求不存在的可选接口；`true` 表示冻结追溯中包含该任务；`null` 表示追溯无法确认（例如哈希损坏），前端仍允许请求并展示真实错误，不将损坏伪装为缺失。Top 摘要与全量结果均提供这些字段，分类筛选只作用于已加载任务。

## 摘要语义

`GET /runs/{run_id}/task-trace?task_id=...&scope=all` 为功能对比提供该任务的全部关联反应和基因。`scope` 允许 `top` / `all`，默认 `top` 兼容旧调用；`top` 使用 `reaction_limit` / `gene_limit`（默认各 30，范围 1–100），`all` 忽略这两项列表限额，不删减已保存关联。响应返回实际 `scope`，保留 `gene_rule`、`observed_delta`、`score_units` 和缺失 null；仍按 run_id、冻结产物身份和 SHA-256 核验，只读取当前运行记录。这里的“全部”限于该任务的保存关联，不表示整个代谢库都已评分。

任务追溯响应包含数据库版本、源文件哈希、任务分类、反应列表及关联基因。`relationship_kind=knowledge_association` 不代表因果贡献；`determinant_status=unavailable` 明确表示未提供评分决定基因归因。缺少数值返回 null；反应和基因列表各自返回 total/truncated。缺少历史追溯产物返回 `404 TASK_TRACE_UNAVAILABLE`，任务不在产物中返回 `404 TASK_NOT_FOUND`；产物哈希或身份错误返回 500，不用当前数据库代替历史版本。

摘要包含运行编号、状态、背景、扰动、coverage、top_genes、metabolic_tasks、warnings 和 error_code。

| 字段 | 含义 |
|---|---|
| `predicted_delta` | 预测减对照的表达或任务分数差异 |
| `observed_delta` | 匹配观测减对照；无观测为 null |
| `coverage` | 可用基因比例，不是准确率或置信概率 |
| `evidence_level` | 当前覆盖规则分类 supported/exploratory/insufficient |
| `determinant_genes` | 预留决定基因列表；真实任务摘要当前为空 |

总体 coverage 可为 null，代谢降级时应展示 warnings 与转录结果。投影当前是固定种子的随机二维投影，应显示返回 method，不能标注 UMAP 或 t-SNE。

## 错误与缺失

业务错误通常在 detail 对象中含 code 和可选 message；参数校验的 detail 是字段错误数组，客户端需兼容两种结构。

| HTTP 状态 | 常见情形 |
|---|---|
| 404 | RUN_NOT_FOUND、PRECOMPUTED_NOT_FOUND、ARTIFACT_NOT_FOUND |
| 409 | RUN_NOT_COMPLETED，产物暂不可读 |
| 422 | 请求校验、UNSUPPORTED_PERTURBATION 或注册表错误 |
| 503 | WORKER_UNAVAILABLE、GPU_UNAVAILABLE 或资产不可用 |
| 500 | INVALID_PRECOMPUTED_RESULT、INVALID_ARTIFACT 等结果异常 |

单个产物缺失只应影响对应视图。provenance 只读取历史清单，不重新计算所有大型文件哈希，另返回 prediction_reused、reanalysis_of、analysis_script_sha256 和登记的表达尺度。真实旧运行缺少 expression_contract.json 时，summary 的 warnings 提示使用重算版本；不会改写旧摘要文件。

validation 读取后端指标文件，不在浏览器重算。metrics 保持原代谢任务字段，metric_scope=metabolic_task_delta；其 top-k 默认 10。expression 单独返回 log1p(CP10K) 群体变化的相关性、MSE/MAE、no_change_mse/mae、mse_relative_to_no_change 和改进比例。differential_expression 返回 Wilcoxon/BH/FDR 0.05 的 DEG 数、重叠率、方向、AP；parameters 记录方法、版本和不可用指标原因。无法计算的值返回 null。held_out_validation=false、protocol_status=unconfirmed 表示匹配观测诊断，不能宣称正式留出泛化验收。多个扰动判别能力、效应量排序及训练数据基线尚需独立协议。

更新契约时运行 `uv run --no-sync python scripts/export_openapi.py` 并核对前端类型。`frontend/src/types/run.ts` 为页面使用的 TypeScript 契约镜像。

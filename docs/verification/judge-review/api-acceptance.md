# API 任务验收

结论：新版本地服务的三条新任务均完成，最终重启后的结果读取、证据、群体契约与导出验收通过。详细请求、状态采样、文件 SHA-256、HTTP 响应摘要与导出清单保存在 `api-acceptance.json`。这是实际服务的工程验收，使用已有数据和模型，不是新的生物实验、独立泛化验证或性能基准。

活动源码为 `D:\全球校园人工智能精英大赛\celllens-national`，API 为 `http://127.0.0.1:8028/api/v1`。验收在 `local` 部署模式进行；下表“公开来源”指输入来源，不代表已验收公开服务器部署。请求按当前源码的 `CreateRunRequest`、`MeasuredRequest` 和导入分析路由构造，并经实时 catalog 确认 Jurkat 模型就绪，没有猜测模型 ID。

## 新任务

| 链路 | 新记录 | 输入 | 最终群体及状态 |
|---|---|---|---|
| GPU 基因扰动预测 | `run_7413f05770d14a22` | Jurkat / ALDOA，64，seed=20261108；`cache_hit=false` | completed 100%；原分析 1024 对照 / 64 预测；独立匹配比较 613 对照 / 55 预测 / 50 观测 |
| 受控自有 H5AD | `measured_beecf1c152044ecaa59df964` | 复用 `import_75219a9293f845edaadfce8c`，沿用该版本的 max_cells=16、seed=42 | completed 100%；16 对照 / 16 观测；未重复导入 |
| 公开来源实测 | `measured_9253d6f68c2e484bb6332bc4` | K562 / ALDOA，目标实测上限 16，seed=20261108 | completed 100%；270 匹配对照 / 16 观测；未运行 STATE |

三次提交均 HTTP 202。先等待 GPU 预测与匹配比较完成，再提交自有数据；等待自有数据完成后提交公开来源实测，没有将三个计算任务并行叠加。GPU 日志 `data/derived/runs/run_7413f05770d14a22/predicted.stdout.log` 明确记录 `Model device: cuda:0`、gene 输出空间、64 treated 与 64 simulated controls；结果契约只把 64 条目标预测作为预测群体。

## 完成的核验

- **冻结文件**：预测原清单 12 个输出、另行冻结的图形/坐标 9 个输出、匹配比较 12 个输出及其输入逐项核对；自有分析 11 个输出、公开来源分析 12 个输出以及各自来源/知识资产全部与清单哈希一致。新任务导出前后清单与输出不变。
- **统一结果与投影**：三条记录身份、来源、表达单位和完成状态一致；PCA / UMAP 均来自已冻结产物，显示数量、总群体数量和统一结果相符。预测原群体与匹配群体独立展示；两项实测没有伪造预测比较。
- **任务证据**：两项实测的 `/task-evidence` 均返回本分析身份与清单指纹；知识库 manifest 和关联文件哈希逐项核对。除完整覆盖项，还实际查询 `Synthesis of estradiol-17beta (E2) from androstenedione` 的 2/37 成员覆盖项，35 个缺失成员保持 `present=false` 和 `null` 数值。预测 `/task-trace?scope=all` 正确返回完整反应明细。
- **最终导出**：重启后，三条记录的统一研究 JSON、基因/任务 CSV、报告和 ZIP 均 HTTP 200，内容身份与群体符合当前记录。预测原/匹配 CSV 分开，分别为 2000 基因、141 有限评分任务；导出元数据 URL 使用 `/api/v1`。统一 JSON 明确 `tables_population=original`，各原表标记 original，匹配 genes/tasks 独立放在 `population_exports.matched_comparison`，并绑定比较源哈希。
- **报告和压缩包**：预测 PDF 通过文件签名核验，实测 HTML 包含 HTML 文档结构；这是内容与格式验收，未做报告逐页视觉验收。预测 ZIP 38 项、两项实测 ZIP 分别 12/13 项，CRC 检查通过；其中 10/11/12 项对应原冻结文件的字节哈希完全一致。包中元数据与派生格式不冒充原文件字节。
- **保全**：本轮前后 138 个已存在产物 SHA-256 不变，已登记导入版本的 manifest/source SHA-256 不变；没有保存、编辑或删除笔记。所有检查使用新记录；没有覆盖旧运行。

## 新预测的敏感性与上下文

三条任务完成并重启最终代码后，通过新预测记录的 `/comparison/diagnostics/prepare` 显式生成独立 `comparison-diagnostics-v2` 侧车；原预测和比较清单保持不变。

新记录相对“无变化”基线的 MSE 比值，原细胞汇总为 **0.9538909**，批次等权为 **1.0650094**，因此 `baseline_conclusion_consistent=false`。这是本次固定来源与选择下的权重敏感性，不是稳定增益或独立泛化结论。匹配参考选择指纹和诊断 JSON/manifest 指纹已绑定到结果及导出。

最后实际 GET `/assistant/context?source_kind=run&source_id=run_7413f05770d14a22&view=comparison` 返回 HTTP 200；本地预览保留上述 false、敏感性、参考选择指纹与诊断哈希，并与比较接口一致。没有调用外部模型，也没有发送原始矩阵或用户数据到外部提供商。

## 运行边界

最初运行进程为 API 31884、CPU 35336、GPU 39548；全部新任务完成后，由主任务统一重启至 API 32452、CPU 18196、GPU 16328。最终 `/ready` 与三个进程存活已验证；本代理没有停止服务或安装依赖。

本报告不替代浏览器交互、最终窄屏布局、键盘、报告视觉验收，也不涵盖目标 Linux/HTTPS 主机部署或外部 AI 服务连接。任务时间仅保存在证据记录中，用于确认发生顺序，不作吞吐或性能比较。

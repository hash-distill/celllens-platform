# 实测优先分析与泛化边界设计

2026-10-22。授权来自用户“按这个定位调整系统”，承接上一轮已确认的实测分析、预测评估和受限探索三个场景。直接实施，不重复要求批准，不自动提交当前混合工作区。

## 范围与产品流程

首版以固定官方公开源 State-Replogle-Filtered 为数据对象，不恢复任意用户上传。主入口：数据目录 → 已有实测直接 CPU 分析；缺少源观测且模型词表支持 → 明示探索预测；已有实测仍可主动选择模型预测并比较评估；模型词表外明确不支持。源没有记录仅代表该固定 filtered revision，无从推断全球没有实验数据。

实测分析不调用 STATE，不依赖 GPU 或 checkpoint。对照与目标扰动观测都来自核验的真实 H5AD；完整共同实测基因按已有 log1p(CP10K) 契约分析，不为了匹配模型强制截为 2000 HVG。输出对照/实测均值和差值、PCA/UMAP（可用时）、scCellFie 任务与反应评分、覆盖、来源、下载及持久记录。无预测群体，不把实测写入 predicted 字段。独立生物学重复未知时只报告描述性差异，不伪造显著性。

## 数据覆盖与泛化审计

新静态源目录由固定远程 H5AD 的 obs.cell_line 与 obs.gene 全量计数生成，保存源 revision、元数据摘要和真实计数，不下载完整表达矩阵。覆盖目录查询按背景/基因/有无实测/模型支持分页，并提供缺实测但模型支持组合的完整 CSV。源目录不可用或不完整时为 unknown，不能显示 0。

目录逐行区分 source_cell_count、local_measured_cells、local_verified、model_supported、official_split 和 generalization_verified=false。公开源计数与本地选取数分开。模型 supported 是词表映射存在，不是泛化成功。上游 fewshot test 名单作为“上游声明的留出候选”；本项目训练排除与独立评估均未核实时明确未验证。

对 checkpoint 的配置/词表/官方协议做只读审计，给出四背景支持边界、未测组合计数和名单、可复现来源证据与训练排除缺口。不得声称任意新基因、新细胞、药物、剂量、时间或组合扰动已支持。

## 独立实测任务

API /api/v1/measured/analyses：POST(cell_line,perturbation,max_cells=256,seed=42)，GET list，GET /{id}，GET /{id}/table，GET /{id}/projection，GET /{id}/download。仅固定目录组合，可下载缺失的对应观测表达子集；本地有效已登记观测与对照优先复用。不存在观测返回明确错误，不回退生成预测。

新 MySQL 表 measured_analyses 与独立 manager 存储生命周期；原 runs、预测和对比文件保持。任务在 CPU 子进程执行，单任务项目锁防资源争用，支持取消、退出清理、中断识别和重试；工作进程关闭不删除原输入。源请求、抽样、数据库版本与结果摘要冻结到独立目录 data/derived/measured/{id}。GET 只读且核验产物；修改资产身份后旧分析拒绝冒充有效。结果下载含 source_kind=measured、实际人数与表达单位。

前端 /measured 与 /measured/:id 提供选择、状态、结果与实测历史；/data-catalog 提供覆盖查询及“直接分析实测/探索预测/评估预测”操作。工作台已有实测时优先给直接分析入口，保留显式预测。导航、首页、使用说明与 README 统一新定位并注明已有功能/验证边界。

## 验收

先写失败测试：源计数/unknown/本地未下载与缺实测区分、分页/CSV、模型词表限制；实测任务不调用 STATE、完整共同基因、无 predicted 群体、实测差值正确、源哈希变化拒绝、持久历史/取消/中断；保留旧预测与比较回归。再用真实 ALDOA 数据完成一次 CPU 直接分析与浏览器端到端下载检查。源覆盖是真实全量元数据审计，泛化结论由证据等级表达，不能用软件测试替代独立科学验证。

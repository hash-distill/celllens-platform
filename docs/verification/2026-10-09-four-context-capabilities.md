# 四背景能力补齐与实测诊断

日期：2026-10-09。范围按用户确认：K562、RPE1、Jurkat、HepG2 均展示真实预测结果、演示和实测诊断。当前活跃模型仍为对应官方 ST-HVG fewshot；本次未训练或替换权重，也未启用实验 SE 解码。

## 可用功能

| 背景 | 在线推演 | 预计算演示 | 实测诊断 |
|---|---|---|---|
| K562 | 官方模型支持的 2024 个扰动 | ALDOA 真实结果回放；MYC 原合成样例 | ALDOA |
| RPE1 | 官方模型支持的 2024 个扰动 | ALDOA 真实结果回放 | ALDOA |
| Jurkat | 官方模型支持的 2024 个扰动 | ALDOA 真实结果回放 | ALDOA |
| HepG2 | 官方模型支持的 2024 个扰动 | ALDOA 真实结果回放 | ALDOA |

模式是否就绪由实时 catalog 与服务状态决定。细胞背景卡片采用等宽等高 2×2 布局。切换背景后需重新选择基因；不接受未登记的自由文本。

查看保存结果：打开 `/workbench` → 选择背景 → 预计算演示 → ALDOA → 开始实验；无需再进行推理。完成后可点击“演示本次实验”查看四章讲解。选择实测诊断则执行新的预测并与该背景的登记观测比较。

## 真实数据与协议

四份 ALDOA 观测从此前已冻结的 `reports/metabolic-full-coverage-2026-10-09/se-measured-aldoa/{背景}/measured.h5ad` 字节一致复制到 `data/raw/replogle-{背景}/diagnostic-aldoa-v1.h5ad`。来源为官方 State-Replogle-Filtered 固定 revision `d790193bb2c93726541a75ca3fa873a92ed44da5`；`source_row`、原始批次和来源元数据保留。没有生成、复制扩增、填零或修改实测表达。

`configs/diagnostics/*-aldoa-v1.json` 冻结背景、ALDOA 名单、观测哈希、log1p(CP10K) 尺度、gem_group 批次字段及来源行。catalog、POST 创建入口和科学管线共用协议核验；协议、观测或其哈希不匹配即关闭入口。请求名单外诊断在任务创建前返回 422 DIAGNOSTIC_UNAVAILABLE。缓存和运行清单包含协议哈希。

全部四次真实推理使用 n_cells=256、seed=43，未命中缓存。每次目标 ALDOA 预测槽为 256×2000；原 H5AD 另有 256 个其他标签细胞，分析先筛除。模型输出与输入对照不同，分析读取预测 X_hvg；不把未预测的完整 .X 当作预测表达。输入 log1p(CP10K) 不重复归一化；scCellFie 使用 expm1 后的线性 CP10K 和冻结阈值。

比较只保留对照、预测、观测共同的记录批次，不重加权各批次频率，不进行细胞一一配对。

| 背景 | 原观测细胞 | 比较对照 | 比较预测 | 比较观测 |
|---|---:|---:|---:|---:|
| K562 | 33 | 1278 | 106 | 32 |
| RPE1 | 29 | 416 | 104 | 29 |
| Jurkat | 34 | 456 | 108 | 34 |
| HepG2 | 33 | 501 | 116 | 33 |

## 实际表达诊断

MSE 评价 2000 基因的群体表达变化，基线为预测变化全部为零。DE 使用 Wilcoxon/BH、FDR<0.05；这些是细胞级样本诊断。下表数值取保存的后端指标，不由浏览器重算。

| 背景 | 预测 MSE | 不变化基线 MSE | MSE/基线 | 有符号变化 Pearson | 实测/预测显著 DEG | DE AP |
|---|---:|---:|---:|---:|---:|---:|
| K562 | 0.010222 | 0.010803 | 0.9462 | 0.2943 | 64 / 195 | 0.2254 |
| RPE1 | 0.008921 | 0.030430 | 0.2932 | 0.8514 | 296 / 842 | 0.6199 |
| Jurkat | 0.019216 | 0.020117 | 0.9552 | 0.4248 | 148 / 396 | 0.3384 |
| HepG2 | 0.006670 | 0.004634 | 1.4392 | 0.1146 | 0 / 153 | 不可计算 |

K562、RPE1、Jurkat 相比不变化基线的 MSE 分别降低约 5.4%、70.7%、4.5%；HepG2 高约 43.9%，这组诊断未显示表达误差改进。HepG2 没有实测显著 DEG，AP/Overlap@N 和共有 DEG 方向为 null，页面显示“未提供”，不能当作零准确率或证明不存在生物效应。有限样本、批次频率和模型误差可能共同影响结果，尚不能归因。

ALDOA 是已有四背景观测的固定方便样本；尚未核实检查点训练是否排除了该扰动。所有协议 `held_out_validation=false`、`training_exclusion_verified=false`；细胞检验不能替代独立生物学重复。不能将这四个数值当作四背景泛化排名、论文严格复现或完整 969 扰动验收。多个扰动、独立批次和训练数据基线仍需另行冻结评价协议。

代谢输出仍来自 2000 HVG 面板，未补齐未预测基因；scCellFie 分数是表达支持程度，不能视为实测通量。官方完整性衡量输入覆盖，不能证明预测准确。

## 运行与回放来源

| 背景 | 原始真实诊断 | 保存的回放检查运行 |
|---|---|---|
| K562 | run_6c55aca915454435 | run_2d7de9d129904b63 |
| RPE1 | run_e1b8d6c7bb234081 | run_2151b0c415484f8e |
| Jurkat | run_2e7f0b7ab38f4c61 | run_4a24afcd5b084acf |
| HepG2 | run_9454c770db3842a1 | run_0895eccf20f8405d |

`data/demo/{背景}/ALDOA/` 包含真实结果及 `source_manifest.json`。包清单校验所有文件哈希；真实数值文件还必须匹配原 manifest 的输出哈希。回放只改摘要/追溯/完整性/表达契约中的运行编号并生成带来源提示的 HTML 报告，验证指标和 CSV 数值字节不变；所有产物重新登记。

API 的 `result_kind=frozen_model_result`、provenance 的 `source_type=frozen_precomputed` 区别于旧 `synthetic_demo`。结果页、记录、比较、演示、观测标签共用来源判断。证据栏提供原运行链接和原清单哈希；页面及导出报告说明“真实结果回放（本次未重新计算）”。请求 n_cells/seed 不代表包生成参数。旧 K562/MYC 包和历史合成运行保持独立合成标识。

原始诊断的执行代码已冻结在证明目录 `execution-code/`，四次 manifest 的 code_sha256 均为 `4dc7f1f0dd775b6408461de46300f31f24135fd7386ea7d84c6bc9904428d982`。回放保留原清单，不将页面或导出报告调整冒充新的科学计算。

## 核验与产物

证明目录：`reports/four-context-capabilities-2026-10-09/`。

- `baseline.json`：458 个既有运行、演示、对照/观测、权重、面板和配置文件的保护哈希；`verify` 复核全部未改。
- `inputs.json` 和诊断协议：四份实测观测来源、哈希、数量和样本范围。
- `diagnostics.json`：真实 CUDA/STATE/scCellFie 运行、表达/DE/批次范围与原清单哈希。
- `bundles.json`、`replays.json`：四个真实包及四次真实 MySQL 回放；指标字节一致、来源和产物登记核验。
- `execution-code/`：科学执行时的代码、配置和登记快照；当前展示代码有后续来源及下拉框修复。
- `browser/`：生产页面与实际 API 的操作检查、各背景截图、不同宽度的设置截图。

后端完整测试 119 项通过；导出报告来源提示调整后，模式/来源相关测试再跑 9 项通过。Ruff、BasedPyright、前端 typecheck/build 及注册资产审计通过。构建仍提示已有三维网络分块超过 500 kB；测试依赖有弃用提醒，未影响此次运行。浏览器验收结果以 `browser/checks.json` 为准。

复查命令（项目根目录）：

```powershell
.venv/Scripts/python.exe -m scripts.audit_registry
.venv/Scripts/python.exe -m scripts.complete_context_capabilities verify
python scripts/check_context_capabilities_frontend.py --url http://127.0.0.1:8000
```

浏览器检查需要对应 Python 环境的 Playwright/Chromium。能力准备前四阶段已经执行，拒绝覆盖原产物；日常不用重新准备。数据库、worker 或 GPU 不可用时在线/诊断会按真实状态关闭，回放仍需数据库与已校验包。工作区保留其他既有改动，本次没有提交或推送。

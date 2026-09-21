# 后端与模型代码实施方案

## 1. 目标与完成判据

后端负责把一次虚拟实验变成可追溯运行：校验输入范围，串行调度 A6000，调用 STATE 官方推理入口，对齐表达空间，执行 scCellFie，计算匹配留出指标，写入不可变结果目录，并向前端提供精简 JSON。

第一版完成需同时满足：一条真实 K562 扰动跑通；每个结果带模型、数据、配置和代码哈希；代谢模块失败时仍保留转录结果；任何模拟或占位结果都不能进入正式缓存。

## 2. 模块和代码位置

| 模块 | 文件 | 输入 | 输出 | 失败行为 |
|---|---|---|---|---|
| 注册表 | `backend/app/core/registry.py` | JSON 资产清单 | 已验证路径与哈希 | 禁止启动任务 |
| API 契约 | `backend/app/schemas.py` | HTTP JSON | 严格 Pydantic 对象 | 422 |
| 任务状态 | `backend/app/core/storage.py` | 状态转换 | MySQL 运行、attempt、事件、产物与缓存记录 | lease 恢复并保留审计轨迹 |
| GPU 队列 | `backend/app/core/job_queue.py` | `run_id` | 单消费者执行 | 任务失败并记录 |
| STATE | `backend/app/engines/state_engine.py` | 对照 H5AD、模型、扰动 | `predicted.h5ad` | 整条任务失败 |
| 基因对齐 | `backend/app/engines/anndata_adapter.py` | control/predicted | 共同基因视图 | 重复或无交集时报错 |
| scCellFie | `backend/app/engines/metabolic_engine.py` | 统一 AnnData、固定阈值 | 任务/反应/决定基因 | 降级为转录结果 |
| 证据 | `backend/app/engines/evidence_engine.py` | control/predicted/observed | 增量指标与明细 | 不输出伪显著性 |
| 编排 | `backend/app/services/pipeline.py` | `run_id` | 不可变结果目录 | 保存错误码和日志 |

## 3. STATE 接入步骤

1. 将真实训练运行目录放到 `models/state-replogle-k562/`，其中必须包含 `config.yaml`、映射文件和 `checkpoints/final.ckpt`。
2. 将输入 H5AD 放入注册表指定位置，确认 `obs` 的扰动列、细胞类型列、控制标签和 `obsm['X_hvg']` 与训练配置一致。
3. 计算 checkpoint、基因列表、H5AD 和拆分文件的 SHA-256，写入注册表后才把 `enabled` 改为 `true`。
4. 运行 `uv run python scripts/audit_registry.py`。
5. 用一个开发集扰动执行真实 smoke test，记录命令、耗时、峰值显存、输入输出哈希和 AnnData 形状。
6. 只有 smoke test 通过后才设置 `CELLLENS_GPU_AVAILABLE=true` 和 `CELLLENS_WORKER_ENABLED=true`。

STATE 通过 `state tx infer` 子进程运行。这样能复用 0.11.1 的配置、checkpoint 和映射加载逻辑，并把命令、stdout、stderr 固化到每次运行目录。不要直接复制模型内部类或手写 `torch.load`。

## 4. scCellFie 接入步骤

1. 从 STATE 输出、真实对照和真实扰动中取同一基因交集；缺失基因单独报告，禁止补零。
2. 在开发/对照参考上冻结阈值版本，预测组与最终测试组复用相同阈值。
3. 先生成任务级完整度表，字段至少含 required/covered genes、required/covered reactions、关键缺失基因和证据等级。
4. 调用 `run_sccellfie_pipeline` 后读取 `adata.metabolic_tasks`、`adata.reactions` 和 `uns['Rxn-Max-Genes']`。
5. 只在支持任务上做主结论；探索和不足任务仍可下载，但必须带等级和缺失解释。

## 5. 结果目录与缓存

每次运行先写 `data/derived/runs/<run_id>.partial/`，全部校验通过后原子改名为 `<run_id>/`。正式缓存键必须包含：checkpoint、数据、拆分、基因映射、分析配置、阈值版本、代码版本、细胞背景、扰动、细胞数和随机种子。

```text
<run_id>/
├── manifest.json
├── predicted.h5ad
├── transcriptomic.parquet
├── metabolic_tasks.parquet
├── reactions.parquet
├── projection.parquet
├── summary.json
└── logs/
```

## 6. 测试层次

- 纯单元测试：哈希、基因交集、指标、状态转换、命令构造。
- 合同测试：假 AnnData 检查字段、顺序、来源和 provenance。
- 集成测试：一个开发集扰动跑通 STATE→scCellFie→summary。
- 留出验证：扰动或生物学重复为拆分单位，不按细胞随机拆分。
- 发布验收：报告数值与 `summary.json` 一致，失败任务不成为缓存命中。

## 7. 后端负责人每日交付

每个任务提交四类证据：代码 diff、可复现命令、测试输出、生成文件及 SHA-256。仅有截图不算完成。真实指标必须同时记录数据版本、拆分、模型配置、随机种子和基线。

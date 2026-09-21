# 细胞知镜后端逻辑与测试审计

**审计日期：** 2026-09-20  
**审计范围：** `backend/app/`、后端测试、API 生命周期、任务队列、资产注册、STATE/scCellFie 边界、证据指标  
**原始结论：** 本文保留修复前的审计快照。列出的 P0/P1/P2 问题已按 `BACKEND_FIX_REPORT_2026-09-20.md` 逐项处理；真实资产尚未登记，因此真实 STATE/scCellFie 运行仍需完成资产验收。

## 1. 已执行测试

| 检查 | 结果 |
|---|---|
| `uv lock --check` | 通过，锁文件可解析 |
| `uv pip check` | 通过，当前 37 个轻量依赖兼容 |
| `ruff check backend scripts` | 通过 |
| `python -m compileall backend scripts` | 通过 |
| `pytest -q` | 9 项通过，2 条上游测试客户端弃用警告 |
| Coverage | 总体 78%；pipeline 38%、catalog 41%、STATE engine 58%、runs API 61% |
| Pyright | 3 项错误：Evidence 的 pandas 类型推断 2 项，未安装可选 scCellFie 1 项 |
| 并发创建任务 | 32/32 返回 202，run_id 均唯一；worker 关闭时 32 项全部停在 queued |
| 进程重启恢复 | 失败；数据库中的 queued 任务不会自动重新入队 |
| 实际 STATE/scCellFie | 未执行；当前环境未安装 model extra，且没有登记 checkpoint/H5AD |

## 2. P0：提交前必须解决的阻断问题

### P0-1 管线会产生“伪完成”状态

`AnalysisPipeline` 在 STATE 输出后没有调用 `align_anndata`、`ScCellFieEngine` 或 `compare_task_deltas`。代码固定添加“coverage artifact is not frozen”警告，然后主动抛出 `InsufficientCoverageError`；异常分支把任务写成 `completed`，但 `top_genes` 和 `metabolic_tasks` 都为空。

**影响：** 前端会收到成功状态，却没有完成产品承诺的表达分析、代谢分析和验证。真实 checkpoint 一旦启用，这个问题会被隐藏成“成功但结果为空”。

**位置：** `backend/app/services/pipeline.py:55-83`。

**修复方向：** 只有真实转录汇总生成后才能允许 transcriptomic-only completion；覆盖不足应是代谢阶段的真实判断，而不是固定控制流。完整分支必须写入 transcriptomic、coverage、metabolic、evidence 和 provenance 产物。

### P0-2 三种运行模式没有分流

动态测试表明：

- `precomputed` 会调用一次 STATE，并被标记 completed；
- 随后执行 `validation` 会再次调用 STATE，并被标记 completed；
- 管线从未读取 `request.mode`，也没有读取 `observed_path`。

**影响：** 无 GPU 演示模式不能工作；验证模式不包含真实扰动数据；接口名称与实际行为不一致。

**位置：** `backend/app/api/runs.py:15-42`、`backend/app/services/pipeline.py:30-83`。

**修复方向：** 建立三个明确策略：`OnlinePipeline`、`PrecomputedRunService`、`ValidationPipeline`。预计算模式直接读取冻结产物；验证模式必须加载封存 observed H5AD；在线模式才进入 GPU 队列。

### P0-3 任务队列不持久且会产生永久 queued 任务

API 在 `worker_enabled=false` 时仍返回 202，但不提交队列。重启应用并启用 worker 后，SQLite 中已有 queued 任务不会重新入队。复现结果为：`status_after_restart=queued`，队列长度为 0。

**影响：** 配置错误、服务重启或进程崩溃都会让任务永久卡住；用户无法区分“等待中”和“永远不会运行”。

**位置：** `backend/app/api/runs.py:38-42`、`backend/app/main.py:16-22`、`backend/app/core/job_queue.py`。

**修复方向：** 在线请求在 worker 不可用时返回 503；启动时扫描并恢复可恢复任务；运行记录增加 lease、attempt、heartbeat。单 A6000 需要跨进程锁，不能只依赖进程内 `asyncio.Queue`。

### P0-4 预计算降级模式实际上被资产门禁阻断

`POST /runs` 对所有模式先要求启用模型和数据。当前默认注册表为 disabled，因此没有 GPU 时也无法通过预计算结果演示。

**影响：** 与“GPU 不可用时浏览预计算结果”的设计目标冲突，答辩现场的降级路径不存在。

**位置：** `backend/app/api/runs.py:15-17`。

**修复方向：** 预计算模式检查 demo manifest 和结果哈希，不要求本机 checkpoint、原始 H5AD 或 GPU。

## 3. P1：高风险逻辑问题

### P1-1 `.partial` 目录恢复逻辑不完整

`partial.mkdir(exist_ok=False)` 位于 `try` 外。只要上次崩溃留下同名 partial 目录，就抛出 `FileExistsError`，任务仍保持 queued，错误不会写入数据库。已动态复现。

**位置：** `backend/app/services/pipeline.py:31-37`。

**修复方向：** 把工作目录创建放入受控状态转换；区分恢复、重试和冲突；每次 attempt 使用独立目录并原子发布。

### P1-2 状态机没有转换约束

动态测试可将 `completed → queued`，也能设置任意进度。数据库只保存状态值，没有校验合法前驱、单调进度或终态不可变性。

**位置：** `backend/app/core/storage.py:66-97`。

**修复方向：** 定义允许转换表，并通过带当前状态条件的 SQL 更新实现 compare-and-set；终态默认不可修改，重试创建新 attempt。

### P1-3 Catalog 的 ready 只是 enabled，不是实际可运行

当注册表写 `enabled=true`、但文件完全不存在时，`/catalog/contexts` 仍返回 `online_ready=true`。它没有验证 checkpoint、输入 H5AD、哈希、STATE 命令或 GPU worker。

**位置：** `backend/app/api/catalog.py:12-28`。

**修复方向：** 启动时执行资产审计并缓存 readiness；分别返回 model、dataset、GPU、worker、demo 和 validation readiness。

### P1-4 资产校验不完整且路径可逃出项目根目录

管线只验证 checkpoint 和 control H5AD；没有验证 gene list、模型 config、STATE 映射文件、split、observed H5AD、scCellFie 数据库和阈值文件。`RegistryEntry.path()` 对 `../outside` 直接 resolve，动态测试确认可得到项目根目录之外的路径。

**位置：** `backend/app/core/registry.py:15-19`、`backend/app/services/pipeline.py:38-41`。

**修复方向：** 注册表使用严格 Pydantic schema；所有相对路径必须验证位于允许根目录；按运行模式审计完整资产集合和 SHA-256。

### P1-5 STATE 输出没有科学契约检查

当前只判断输出文件存在且非空，没有重新打开 H5AD 检查：

- 能否读取；
- 预测矩阵是否有限；
- 基因顺序和数量；
- 请求扰动与细胞背景；
- 控制/预测细胞的来源标记；
- 细胞数量；
- checkpoint 和输入 provenance。

**位置：** `backend/app/engines/state_engine.py:61-90`。

**影响：** 任意非空文件都可能进入“成功”路径，基因错位会继续污染后续代谢分析。

### P1-6 scCellFie 的“固定阈值”当前只是字符串标签（表述修正）

scCellFie 使用数据库 `Thresholds.csv` 中由 `threshold_key` 指定的阈值列，并不是对每次输入重新拟合阈值。原实现的问题是没有冻结和验证整套数据库文件及阈值列的哈希，也没有证明 control、predicted、observed 使用同一数据库对象。

**位置：** `backend/app/engines/metabolic_engine.py:23-48`。

**影响：** 三组分数可能不可直接比较，与方案要求的共享阈值相冲突。

### P1-7 证据指标没有处理非有限值

输入含一个 NaN 时，复现结果为：

```text
spearman = nan
mae = 0.3333
direction_agreement = 0.75
top_k_overlap = 1.0
```

Top-k 把 NaN 所在任务计入集合，得到虚高的 1.0；不同指标对缺失值使用了不同样本集合。

**位置：** `backend/app/engines/evidence_engine.py:23-49`。

**修复方向：** 先构造共同有限值掩码，再对同一任务集合计算所有指标；同时报告有效任务数、排除原因和覆盖层级。

### P1-8 进程内队列不能保证单 GPU 全局串行

每个应用进程都会建立自己的 `SingleGpuJobQueue`。如果 Uvicorn 使用多个 worker，多个进程可以同时启动 STATE，占用同一块 A6000。

**修复方向：** 部署层强制 API 单 worker 并分离一个 GPU worker，或使用数据库租约/Redis 锁保证全局互斥。

## 4. P2：工程质量问题

### P2-1 SQLite 连接没有显式关闭

`with sqlite3.Connection` 只处理事务，不负责关闭连接。Windows 复现中，连续 `get` 后不触发 GC 会导致临时数据库文件仍被占用；显式 `gc.collect()` 后才能清理。

**位置：** `backend/app/core/storage.py:17-20` 及所有 `_connect()` 调用。

**修复方向：** 使用 `contextlib.closing(self._connect())`，在其内部再使用事务上下文；增加 Windows 文件释放测试。

### P2-2 健康检查不能反映可服务状态

`/health` 始终返回 ok，即使 registry 禁用、worker 未启动、GPU 不可用。应保留 liveness，并增加 readiness 和详细依赖状态。

### P2-3 当前测试通过不代表主流程可用

现有测试主要覆盖 schema、命令构造和小函数。最关键的 pipeline 覆盖率只有 38%，没有成功/STATE 失败/代谢降级/验证模式/预计算模式/重启恢复测试。

### P2-4 类型检查尚未纳入质量门

Pyright 当前有 3 项错误，CI/本地命令没有类型检查步骤。pandas Top-k 类型提示和可选依赖导入需要显式处理。

## 5. 目前表现正常的部分

- Pydantic 请求约束能够拒绝额外字段和非法细胞数；
- 32 个并发创建请求得到唯一 run_id，进程内 SQLite 写入未发生冲突；
- 任务处理器抛异常后，当前进程内 worker 能继续执行下一任务；
- manifest 哈希与文件 SHA-256 函数逻辑清晰；
- 基因交集不会静默补零，并能拒绝大小写归一后的重复基因；
- 依赖锁、轻量依赖兼容、静态风格和 Python 编译均通过。

## 6. 建议修复顺序

1. **先纠正成功语义：** 未生成真实 summary 时不得 completed；补齐三种模式分流。
2. **完成一个真实纵向切片：** K562 单扰动 STATE → 输出校验 → AnnData 对齐 → scCellFie → evidence → summary。
3. **修复队列可靠性：** worker 不可用拒绝在线任务、启动恢复、attempt/lease、跨进程单 GPU 锁。
4. **冻结科学资产：** 注册表严格 schema、全资产哈希、共同阈值和最终测试拆分。
5. **补齐异常恢复：** partial、重试、终态和原子状态转换。
6. **补齐指标防线：** 非有限值、有效样本数、覆盖分层、基线和失败案例。
7. **最后扩展 API：** projection、genes、tasks、reactions、report、下载与缓存命中。

在第 1—3 项完成前，前端可以继续使用静态 fixture 开发，但不应把当前 `/runs` 接口作为正式真实推演服务。

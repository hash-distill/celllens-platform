# 细胞知镜（CellLens）代码工程

本工程实现“STATE 扰动表达预测 + scCellFie 代谢任务解释 + 匹配留出验证 + 交互式前端”的后端基础。STATE 通过官方 `state tx infer` 命令调用，运行元数据使用 MySQL，H5AD/CSV/JSON 科学产物保存在文件系统并在数据库登记 SHA-256。

## 当前能力

- MySQL + SQLAlchemy 2.0 持久化，Alembic 管理表结构；
- `online`、`validation`、`precomputed` 三种模式独立分流；
- worker、GPU、模型、数据文件及哈希门禁；
- 单 A6000 进程内队列和 MySQL 跨进程资源锁；
- attempt、lease、heartbeat、启动恢复、严格状态机和 attempt 独立临时目录；
- STATE 输出 H5AD 可读性、有限值、扰动标签、基因顺序和 provenance 校验；
- 对照/预测/观测基因交集、真实转录差异、冻结 scCellFie 数据库、代谢覆盖和留出指标；
- scCellFie 未冻结或覆盖不足时生成真实的转录结果，并明确标注代谢降级原因；
- 预计算演示无需 GPU 和本机模型资产。
- 确定性缓存键覆盖请求、模型/数据/代谢库哈希与后端代码指纹；
- 提供投影、基因、代谢任务、反应聚合和 HTML 报告接口。

K562 的 STATE checkpoint、2000 基因面板、control/heldout H5AD 和 scCellFie 六个数据库文件已登记并通过 SHA-256 审计。RPE1 资产仍保持禁用，不会用占位资产生成结果。

## 启动 MySQL

本机已配置独立的 MySQL 9.2 数据目录（端口 3307），最短启动路径：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_mysql.ps1
uv run alembic upgrade head
uv run python scripts/check_mysql.py
```

机器上已有的 `MySQL92/3306` 服务不受影响。若要在 Windows 登录前自动启动 3307 实例，需要管理员把 `ops/mysql-celllens.ini` 注册为独立服务；普通权限可直接运行上述脚本。详细表结构见 `docs/DATABASE.md`。

## 启动后端

```powershell
uv sync --extra model --extra report --group dev
uv run pytest
uv run uvicorn backend.app.main:app --reload --port 8000
```

打开 `http://127.0.0.1:8000/docs` 查看 OpenAPI。资产审计和真实闭环检查：

```powershell
uv sync --extra model --extra report --group dev
uv run python scripts/audit_registry.py
uv run python scripts/smoke_backend.py
```

当前 `.env` 已在本机 RTX 4060、CUDA PyTorch 和真实 STATE 推理通过后启用：

```dotenv
CELLLENS_WORKER_ENABLED=true
CELLLENS_GPU_AVAILABLE=true
```

## 目录职责

```text
backend/app/api/       HTTP 接口与模式分流
backend/app/core/      注册表、哈希、状态机、MySQL 存储与任务队列
backend/app/db/        SQLAlchemy 模型与 Alembic 迁移
backend/app/engines/   STATE、AnnData、scCellFie、证据指标适配层
backend/app/services/  端到端管线与科学分析编排
configs/               冻结分析阈值和模型配置
data/registry/         模型、数据与 scCellFie 资产清单
data/derived/          不可变运行产物
frontend/              前端工程边界与共享类型
docs/                  API、数据卡、模型卡、审计和验收记录
```

后端实现路径见 `docs/BACKEND_MODEL_IMPLEMENTATION.md`，数据库见 `docs/DATABASE.md`，本轮修复证据见 `docs/BACKEND_FIX_REPORT_2026-09-20.md`。

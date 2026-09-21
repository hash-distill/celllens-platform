# 测试报告

## 软件测试

执行日期：2026-09-21；环境：Windows，CPython 3.11，MySQL 9.2，NVIDIA GeForce RTX 4060 Laptop GPU。

- `uv run ruff check backend scripts`：通过，0 项错误；
- `uv run basedpyright`：通过，0 项错误、0 项警告；
- `uv run pytest -q`：33 项通过；
- `uv run alembic check`：通过，无遗漏迁移；
- `uv run python scripts/check_mysql.py`：通过，MySQL 表结构和运行记录往返正常；
- `uv run python scripts/export_openapi.py`：通过，生成 `docs/openapi.json`；
- `uv run python scripts/audit_registry.py`：通过；K562 模型、数据和 scCellFie 均完成哈希校验，RPE1 明确跳过。

测试过程出现 FastAPI/Starlette 测试客户端的 2 条上游弃用警告，不影响运行结果，后续锁定新测试客户端时再消除。

## GPU 真实推理

PyTorch 2.14.0+cu132 已确认 `torch.cuda.is_available() == True`。真实 STATE `MYC` smoke test 使用 64 个对照和 64 个虚拟扰动细胞，日志确认 `Model device: cuda:0`，成功生成带 `obsm['X_hvg']` 的 H5AD。完整 API 闭环经 MySQL 队列执行到 `completed`，`/health` 与 `/ready` 均为 200，summary、projection、genes、metabolic-tasks、reactions、report 六个结果接口均为 200。

## 科学验证

冻结测试集尚未打开；本次仅用开发扰动 `MYC` 验证工程链路。matched baseline、STATE 泛化指标与代谢任务验证指标仍须在正式实验阶段报告，不能由 smoke test 推断。

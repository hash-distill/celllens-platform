# 运行与检查

所有命令在仓库根目录执行。配置来自 `.env`，字段定义在 `backend/app/config.py`；不要用示例覆盖已有本机配置。

## 环境准备

项目要求 Python `>=3.11,<3.13`，使用 uv 和 `uv.lock` 管理依赖。运行元数据依赖 MySQL；完整科学链路还需已登记的模型、H5AD 和代谢数据库。

```powershell
if (-not (Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }
uv sync --locked --extra model --extra report --group dev
uv pip check
```

仅做接口/预计算开发时可用 `uv sync --locked --group dev`，并在 `.env` 设置 `CELLLENS_WORKER_ENABLED=false`、`CELLLENS_GPU_AVAILABLE=false`。示例默认开启这两个开关，开关不等于真实 GPU 与资产已经就绪。

## 启动数据库

本机独立 MySQL 9.2 监听 `127.0.0.1:3307`。脚本内程序及数据路径是 `D:\Mysql\mysql-9.2.0-winx64\bin\mysqld.exe`、`D:\Mysql\celllens-data`，换电脑需自行配置。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_mysql.ps1
uv run --no-sync alembic upgrade head
uv run --no-sync python scripts/check_mysql.py
```

新环境也可使用 `docker-compose.yml`：先执行 `docker compose up -d mysql`，数据库健康后再迁移。Docker 和本机脚本是两种选择，都占用宿主机 3307，不能同时启动。连接由 `CELLLENS_DATABASE_URL` 配置；示例凭据用于本地开发。

表结构统一由 Alembic 管理，保持 `CELLLENS_CREATE_DATABASE_SCHEMA=false`。停止 API 不会停止独立 MySQL。

## 启动与访问

```powershell
uv run --no-sync uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

| 地址 | 用途 |
|---|---|
| `http://127.0.0.1:8000/docs` | 调试请求及查看接口结构 |
| `http://127.0.0.1:8000/openapi.json` | 实时接口契约 |
| `http://127.0.0.1:8000/api/v1/health` | 服务与数据库状态 |
| `http://127.0.0.1:8000/api/v1/ready` | 数据库、worker/GPU 开关就绪状态 |
| `http://127.0.0.1:8000/api/v1/catalog/contexts` | 各细胞系的模式可用状态 |

`health` 在数据库故障时仍可能返回 HTTP 200，要检查响应字段。`ready` 不做完整 GPU 推理或资产审计；资产由 `audit_registry.py` 核验，细胞系状态查 catalog。根路径 `/` 无网页。局域网对接时用 `--host 0.0.0.0`，提供本机局域网地址。

## 无 GPU 演示

关闭 worker/GPU 后数据库仍须可用。若演示包不存在，可生成合成样例：

```powershell
uv run --no-sync python scripts/build_demo_bundle.py --cell-line K562 --perturbation MYC
```

通过 `/docs` 提交 `mode="precomputed"` 的 K562/MYC 请求，JSON 见 [接口说明](API.md)。生成脚本会写入对应演示目录，只用于合成样例。当前样例缺少投影、反应和报告，对应接口返回 404。

## 检查命令

```powershell
uv pip check
uv run --no-sync pytest -q
uv run --no-sync ruff check backend scripts
uv run --no-sync basedpyright
uv run --no-sync alembic check
uv run --no-sync python scripts/audit_registry.py
uv run --no-sync python scripts/export_openapi.py
uv run --no-sync python scripts/smoke_backend.py
```

`smoke_backend.py` 使用真实 MySQL 和应用生命周期，提交 K562/MYC、64 细胞、种子 42 的在线请求，再检查六类结果接口。看到 `cache_hit=true` 表示读取已有真实结果，不能记为本次重新完成 GPU 推理。首次或缓存变化后可能实际调用模型。

2026-10-03 本机已检查：依赖兼容；33 项测试通过；数据库迁移及持久化往返通过；K562 模型、数据及六个代谢数据库文件哈希审计通过；health/ready 与六类结果接口正常。当天冒烟请求命中已有真实运行缓存，未重新执行 GPU 推理。测试有两条上游弃用警告，前端尚未进行浏览器验收。

## 常见问题

| 现象 | 检查方向 |
|---|---|
| `/` 返回 404 | 当前无前端页面，用 `/docs` 调试 |
| 数据库不可用 | 3307 监听、`.env` 连接信息、数据库迁移 |
| online 返回 503 | worker/GPU 开关、资产审计、catalog 就绪原因 |
| 请求返回 422 | 扰动支持列表、细胞数/种子范围、额外字段 |
| validation 接受后失败 | 观测是否包含所请求扰动；整体就绪不保证每个扰动有观测 |
| completed 但无代谢结果 | warnings、覆盖等级、数据库及非负表达要求 |
| 单个结果返回 404 | 产物是否生成；演示和降级任务可缺少文件 |
| 前端请求跨域失败 | 后端无 CORS，按 [前端对接](FRONTEND.md) 使用开发代理或同源部署 |

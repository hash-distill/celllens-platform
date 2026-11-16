# 旧部署参考

**当前部署以 [CPU 部署](CPU部署.md)和[项目 README](../README.md#快速开始)为准。** 本页保留旧版 MySQL、Compose 和手动配置参考，不能代替当前独立 API/worker 的部署说明。当前 Windows 主入口为 `ops/run-local.ps1`，轻量启动使用 SQLite，MySQL 不是必需条件。旧 `scripts/start_system.ps1` 只启动 API，不负责启动当前独立 CPU/GPU worker。

下方旧配置示例统一使用 API 端口 **8001**，命令在仓库根目录执行；涉及旧入口、安装方式和任务执行方式时，请先对照新部署指南。既有 MySQL 环境仍可保留，API 与 worker 必须使用同一数据库和资产目录。

实测优先入口为 `/measured`，覆盖目录为 `/data-catalog`。CPU 实测分析无需 STATE 权重或 GPU，安装 analysis/report extras 并迁移数据库即可；原 `/workbench` 用于明确预测。详见[实测分析](MEASURED_ANALYSIS.md)和本页末尾实测部署补充。

## 环境与运行方式

| 项目 | 要求 |
|---|---|
| Python | `>=3.11,<3.13`，以下使用 3.11；uv 按 `uv.lock` 安装 |
| 前端 | Node.js / npm，依赖由 `frontend/package-lock.json` 锁定 |
| 数据库 | 支持事务与 `GET_LOCK` 的 MySQL；Compose 使用 8.4 |
| 科学依赖 | 实测 `--extra analysis --extra report`；预测另加 `--extra model`，STATE 0.11.1、scCellFie 0.6.2 |
| 在线推理 | NVIDIA GPU 与兼容当前锁定 PyTorch 2.14.0 / CUDA 13.2 包的驱动 |
| 页面 | 桌面现代浏览器，最小宽度 1280px |
| 存储 | 模型、真实对照、运行文件和数据库各自保留；下载单背景至少留出两份模型大小，另留环境与实验空间 |

页面可以先于权重启动。GPU 不可用时，安装 analysis/report 并启动独立 CPU worker，仍可运行真实数据分析和浏览已有结果；新建 STATE 预测不可用。预测相关开关不替代 CPU worker。新部署不会自动获得旧数据库或实验结果。

## 安装与配置

```bash
git clone https://github.com/hash-distill/celllens-platform.git
cd celllens-platform
uv sync --locked --python 3.11 --extra model --extra report
npm --prefix frontend ci
```

Windows 如拦截 `npm.ps1`，使用 `npm.cmd`。缺失时从 `.env.example` 复制 `.env`；不要覆盖原配置：

```powershell
if (-not (Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }
```

Linux 对应 `if [ ! -f .env ]; then cp .env.example .env; fi`。

| 配置 | 说明 |
|---|---|
| `CELLLENS_DATABASE_URL` | 实际业务库连接；本地模板 `127.0.0.1:3307/celllens` |
| `CELLLENS_CREATE_DATABASE_SCHEMA=false` | 表结构通过 Alembic 管理 |
| `CELLLENS_WORKER_MODE=external` | 默认由独立 CPU/GPU worker 执行，API 只入队；生产环境不使用 embedded |
| `CELLLENS_WORKER_ENABLED=true` | 允许预测任务执行；不表示已有独立 worker 或 GPU 就绪 |
| `CELLLENS_GPU_AVAILABLE=true` | 允许在线 GPU 入口，仍需实际硬件及依赖检测 |
| `CELLLENS_STATE_EXECUTABLE=state` | 运行当前环境中的 STATE |
| `CELLLENS_ALLOW_SYNTHETIC_RESULTS=false` | 正式运行不以合成结果替代模型结果 |
| `CELLLENS_ASSISTANT_EXTRA_ORIGINS` | 部署者额外允许的 AI 服务精确 origin，缺省留空 |
| `CELLLENS_ASSISTANT_TIMEOUT_SECONDS=90` | AI 请求超时，允许 5–90 秒 |

进程环境变量优先于 `.env`。Windows 启动器拒绝遗留的 worker/GPU 环境覆盖，防止文件与实际运行不一致；按错误提示清除覆盖后重试。AI Key 通过设置页按会话提供，勿写入结果或提交到仓库。

## 数据库：选择一种方式

### Docker MySQL

先启动 Docker Desktop / Docker daemon，然后执行：

```bash
docker compose up -d mysql
docker compose ps mysql
```

等待 `healthy`。默认映射 **宿主机 3307 → 容器 3306**，与 `.env.example` 对应；Compose 只管理 MySQL，不启动应用。数据保存在 `celllens_mysql_data` 命名卷。

本地模板账户不是公开部署凭据。更换账户时同步修改 Compose 的初始化环境、healthcheck 和 `.env`。初始化变量仅对空数据卷生效；已有库通过数据库管理操作更新账户，保留原数据卷。

### 本机 MySQL

使用数据库服务管理器启动已有实例，并把真实业务库和应用账户连接写入 `.env`。仓库提供的 Windows 辅助脚本只负责启动**已初始化**的项目实例，不安装 MySQL，也不创建账户。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_mysql.ps1 `
  -MysqlExecutable 'C:\mysql\bin\mysqld.exe' `
  -DataDirectory 'C:\mysql\celllens-data'
```

以上路径需替换为实际路径。也可在运行脚本的 PowerShell 终端设置 `CELLLENS_MYSQL_EXECUTABLE` 与 `CELLLENS_MYSQL_DATA_DIRECTORY`，再运行 `start_system.ps1 -StartLocalMysql -ApiPort 8001`。这两个变量由启动脚本读取，写入 `.env` 不会让 PowerShell 自动读取它们。

脚本固定启动本机项目端口 3307，支持从 PATH 查找 mysqld；保留当前开发电脑旧安装路径作为兼容回退。3307 已监听时直接返回。使用其他端口、托管数据库或系统服务时，通过对应的服务管理方式启动，不加 `-StartLocalMysql`。

数据库与业务账户需预先存在并具备本库读写、迁移权限。其他实例即使运行在 3306，也不能代替 `.env` 指向的 3307 实例。本机与 Docker 数据库二选一，避免争用端口。

### 连接与表结构检查

Windows `start_system.ps1` 会依次完成以下步骤；手动启动时自行执行：

```bash
uv run --no-sync python scripts/check_mysql.py --connection-only
uv run --no-sync alembic upgrade head
uv run --no-sync python scripts/check_mysql.py
```

最后应输出 `MySQL schema and durable run round trip: OK`，覆盖表结构、命名锁和临时记录写入/读取，检查记录随后清理。`uv run --no-sync` 复用已安装环境，不负责安装依赖或启动数据库。

## 启动应用

### Windows：构建后运行

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_system.ps1 -ApiPort 8001
```

已有本机项目 MySQL 可追加 `-StartLocalMysql`。构建后 Vue 页面、静态文件和 API 由同一个 FastAPI 进程提供，访问 <http://127.0.0.1:8001/workbench>。`Ctrl+C` 停止应用。

| 参数 | 行为 |
|---|---|
| `-Rebuild` | 强制重建前端；默认按内容指纹复用 |
| `-SkipBuild` | 跳过构建检查，要求已有正确的 dist；不能与 Rebuild 同用 |
| `-Mode Development` | 额外启动 Vite，退出时停止对应前端进程 |
| `-FrontendPort 5173` | 开发页面端口，必须与 API 端口不同 |
| `-HostAddress 0.0.0.0` | 受控网络访问，浏览器使用实际主机地址 |

### Windows：前后端开发

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_system.ps1 -Mode Development -ApiPort 8001 -FrontendPort 5173
```

访问 <http://127.0.0.1:5173/workbench>。启动器自动把 Vite 代理目标设为所选 API 端口。

### Linux / 手动运行

完成配置、启动数据库、执行迁移后：

```bash
npm --prefix frontend run build
uv run --no-sync uvicorn backend.app.main:app --host 127.0.0.1 --port 8001
```

访问 <http://127.0.0.1:8001/workbench>。开发模式可在另一终端进入 `frontend` 后运行 `CELLLENS_API_PROXY_TARGET=http://127.0.0.1:8001 npm run dev -- --host 127.0.0.1 --port 5173 --strictPort`。

当前默认 `worker_mode=external`：API 只校验、入队和读取，任务由独立进程执行。上述 Uvicorn 命令仅启动 API，还需启动 `python -m backend.app.worker --kind cpu`；预测环境另需 `python -m backend.app.worker --kind gpu` 及真实设备、依赖和资产。正式运行不使用 `--reload`；完整进程管理以 [CPU 部署](CPU部署.md)中的 systemd 或 Windows 启动器为准。跨主机、多实例、Linux 现场和远程 HTTPS 未验收。

## 页面准备模型与真实对照

启动页面后，打开 <http://127.0.0.1:8001/status>，在“按需准备细胞背景”选择所需背景。无需手动放置四套权重，也无需先下载完整训练数据。

每个背景约 467 MiB / 6 个模型文件；已有文件校验通过后复用。缺少真实对照时，从固定官方版本范围读取该背景最多 1,024 个 non-targeting 细胞。进度、取消、失败重试和文件状态均在页面展示。资源准备完成会刷新目录，无需重启后端；在线推理还需 GPU、worker 与依赖就绪。

具体来源、目录、历史保留、固定版本和许可见[资源管理](INFERENCE_RESOURCES.md)。完整注册表审计会检查所有背景，未下载的可选背景会报告缺失；不要求为了使用一个背景先准备全部背景。

## 启动验收与排错

| 检查 | 含义 |
|---|---|
| `/api/v1/health` | API 进程响应 |
| `/api/v1/ready` | HTTP 200 表示数据库和浏览入口可用；CPU/预测能力由未过期 worker 心跳及依赖/设备探针分别报告 |
| `/api/v1/resources` | 各背景模型与真实对照是否通过校验 |
| 工作台所选背景在线就绪 | 对应 worker 能力与该背景登记资产均需就绪；配置开关不能代替真实心跳和探针 |
| 一次真实推理完成 | 特定模型和输入上的流程验收，不替代独立留出评价 |

- **MySQL 2003 / WinError 10061：**核对 `.env` 主机和端口，先启动数据库。Docker 查看 `docker compose ps mysql` 和 `docker compose logs --tail 100 mysql`；本机实例查看其错误日志。
- **端口占用：**Windows 预检会报告 Listen、Bound 或 Established 的本地占用。使用其他 API 端口，或通过原终端管理已有服务；脚本不会终止占用者。
- **缺少前端：**运行构建，确认 `frontend/dist/index.html` 存在，或移除 SkipBuild。
- **资源准备失败：**按页面原因检查官方源网络、磁盘及 model/report 依赖，重试恢复；不要修改登记哈希跳过校验。
- **资源就绪而在线不可用：**查看页面环境原因，运行 `uv run --no-sync python -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"` 和 `uv run --no-sync state --help`。
- **旧实验缺失：**确认同时迁移 MySQL、冻结登记及对应运行文件，不能只复制截图或 demo 目录。

更多运行检查见 [OPERATIONS.md](OPERATIONS.md)。

## 旧实测环境迁移

旧环境升级前备份数据库及不可变产物，并执行全部 Alembic 迁移。仅 CPU 安装选择 `analysis` / `report` 依赖，通过独立 CPU worker 执行；SQLite 和 MySQL 均可使用。预测另需 `model` 依赖、对应权重、GPU 与独立预测 worker。当前研究入口为 `/research`，覆盖目录为 `/data-catalog`；详细启动以 [CPU 部署](CPU部署.md)为准。

实测任务在独立 CPU worker 的子进程执行，允许取消；worker 中断后按租约恢复并记录新的 attempt，API 重启不终止活跃任务。失败或取消的暂存目录保留用于诊断，不会作为完成结果公开。迁移时同时备份数据库、`data/derived/measured` 和清单引用的原始输入／冻结知识库，不能只复制网页或数据库。首次公开源范围提取需要访问固定 Hugging Face 数据源；不用提前下载全部 atlas。

# 部署与启动

本文按「准备环境 → 配置数据库 → 迁移 → 准备资产 → 构建 → 启动 → 检查」组织。所有相对路径和命令均从仓库根目录执行。

Windows 本机支持在线运行、手动服务入口及一键启动；Docker MySQL 与 Linux 常驻服务方案尚未在目标服务器实测。这里提供现有代码对应的部署流程，不表示仓库已经包含完整应用镜像或公网服务。

## 1. 选择运行方式

| 场景 | 所需进程 | 访问入口 |
|---|---|---|
| 前后端开发 | MySQL + Uvicorn + Vite | `http://127.0.0.1:5173/workbench` |
| 构建后运行完整系统 | MySQL + Uvicorn；Vue 构建产物由后端提供 | `http://127.0.0.1:8000/workbench` |
| 无 GPU 结果回放 | MySQL + Uvicorn + 前端构建；关闭 worker/GPU | 同上，工作台选择「结果回放」 |
| Linux 内部服务器 | MySQL + 单进程 Uvicorn + 进程管理；可接入反向代理 | 取决于服务器域名与网关 |

后端由 Uvicorn 运行，Vue 开发服务由 Vite 运行；PowerShell 只是 Windows 脚本的执行工具。Docker Compose 当前仅管理 MySQL，不会启动应用或下载科学资产。

## 2. 获取源码与准备依赖

获取项目源码：

```bash
git clone https://github.com/hash-distill/celllens-platform.git
cd celllens-platform
```

环境要求：Python `>=3.11,<3.13`、uv、Node.js/npm，以及可连接的 MySQL。本机已验证 Python 3.11.15、Node.js 24.19.0、npm 11.13.0、uv 0.12.5；依赖版本以 `uv.lock` 与 `frontend/package-lock.json` 为准。

完整在线环境：

```bash
uv sync --locked --python 3.11 --extra model --extra report --group dev
npm --prefix frontend ci
uv pip check
```

仅 API/预计算开发环境：

```bash
uv sync --locked --python 3.11 --group dev
npm --prefix frontend ci
uv pip check
```

两种 Python 安装命令按用途选择一组。`uv sync` 默认精确同步，在线环境再次同步时要保留 `--extra model --extra report`，否则这些额外依赖可能被移除。本文后续使用 `uv run --no-sync`，不会自动补装缺失依赖。

当前 `model` 依赖固定 PyTorch 2.14.0，并使用 CUDA 13.2 的专用索引。在线环境需核对 NVIDIA 驱动与安装包兼容性；预计算路径不安装该依赖组，也不要求 GPU。

## 3. 创建环境配置

Windows PowerShell：

```powershell
if (-not (Test-Path -LiteralPath .env)) {
    Copy-Item -LiteralPath .env.example -Destination .env
}
```

Linux/macOS shell：

```bash
if [ ! -f .env ]; then cp .env.example .env; fi
```

以上只创建缺失配置，不覆盖已有 `.env`。后端自动读取仓库根目录的 `.env`；不需要在 shell 中逐项设置环境变量。环境变量如已由进程管理器设置，会优先于文件配置。

主要配置：

```dotenv
CELLLENS_DATABASE_URL=mysql+pymysql://celllens:celllens_dev@127.0.0.1:3307/celllens?charset=utf8mb4
CELLLENS_CREATE_DATABASE_SCHEMA=false
CELLLENS_WORKER_ENABLED=true
CELLLENS_GPU_AVAILABLE=true
CELLLENS_STATE_EXECUTABLE=state
```

这是当前本机开发示例。其他机器使用自己的数据库地址和密码；连接 URL 中的特殊字符需要进行 URL 编码。表结构由 Alembic 管理，保持 `CELLLENS_CREATE_DATABASE_SCHEMA=false`。

无 GPU 结果回放请编辑 `.env`，将以下两项设为 `false`：

```dotenv
CELLLENS_WORKER_ENABLED=false
CELLLENS_GPU_AVAILABLE=false
```

`GPU_AVAILABLE=true` 只是允许在线路径的配置开关，不代表已检测到 GPU；完整在线就绪仍需硬件、依赖及资产检查。

## 4. 启动数据库

### 4.1 当前 Windows 本机实例

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_mysql.ps1
```

脚本启动或复用 `127.0.0.1:3307` 的独立实例。当前脚本中的路径为：

- 程序：`D:\Mysql\mysql-9.2.0-winx64\bin\mysqld.exe`。
- 数据目录：`D:\Mysql\celllens-data`。
- 错误日志：`D:\Mysql\celllens-data\celllens-mysql.err`。

程序目录保留历史版本名称，当前实例实测版本为 **9.7.2**，不能由目录名判断版本。脚本要求安装程序及已有数据目录存在，不负责初始化新数据库或创建账户；换电脑需要修改路径并先准备实例。

该实例由脚本启动，尚未为它配置开机自动启动。重启电脑后再次运行脚本，或使用带 `-StartLocalMysql` 的系统启动命令。

### 4.2 新环境使用 Docker MySQL

此方案与上面的独立实例二选一，同一台机器不能同时占用 `3307`。

```bash
docker compose up -d mysql
docker compose ps mysql
```

等待容器状态为 `healthy` 后继续迁移；失败时查看 `docker compose logs --tail 100 mysql`。容器使用 MySQL 8.4，宿主机 `3307` 映射到容器 `3306`，数据存入命名卷 `celllens_mysql_data`。

Compose 文件会在**空数据卷首次初始化**时创建 `celllens` 库及账户。现有数据卷的账户密码不会因为修改初始化环境变量而自动改变。这里的 `celllens_dev`、`celllens_root_dev` 是本地开发凭据；服务器使用前应配置实际密码，并将数据库端口绑定到本机地址或受控网络。

当前 `docker-compose.yml` 写有固定密码。只修改根目录 `.env` 的连接 URL，不会同步修改 Compose 里的数据库密码，需要两边一致。

### 4.3 连接现有 MySQL

让数据库管理员预先创建 `celllens` 库与应用账户，授予该库的业务读写和迁移所需权限，再设置 `CELLLENS_DATABASE_URL`。运行时需支持项目使用的事务与命名锁。

项目访问的是 `celllens` 业务库，没有依赖 `performance_schema`。Navicat 本机连接参数如下：

| 项目 | 本机开发值 |
|---|---|
| 主机 | `127.0.0.1` |
| 端口 | `3307` |
| 用户名 / 密码 | `celllens` / `celllens_dev` |
| 默认数据库 | `celllens` |

## 5. 迁移与验证数据库

数据库可连接后，先建表，再执行完整数据库检查：

```bash
uv run --no-sync alembic upgrade head
uv run --no-sync python scripts/check_mysql.py
```

检查成功应输出 `MySQL schema and durable run round trip: OK`。脚本检查六张表、命名锁与运行写入/读取，并清理自己创建的临时检查记录。

Windows 一键脚本在迁移前也会运行此检查，因此全新数据库必须先完成上述迁移；脚本不是空数据库的初始化向导。

## 6. 准备科学资产或真实回放结果

### 6.1 在线计算

从有权限的来源准备模型权重与输入 H5AD，按照 `data/registry/models.json`、`datasets.json` 的路径放置文件；保留已登记的模型配置、基因面板、数据拆分及冻结代谢数据库。

| 资产 | 当前位置或登记入口 |
|---|---|
| STATE checkpoint | `models/state-replogle-k562/checkpoints/final.ckpt` |
| 模型配置与面板 | `configs/models/`、`data/registry/state_k562_genes.txt` |
| 对照与观测 H5AD | `data/registry/datasets.json` 指向的 `data/raw/` 文件 |
| scCellFie 数据库 | `data/registry/sccellfie/human/manifest.json` 及其六个文件 |
| 数据拆分 | `configs/splits/replogle-v1.json` |

执行检查：

```bash
uv run --no-sync python scripts/audit_registry.py
uv run --no-sync python -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"
uv run --no-sync state --help
```

资产哈希失败时先确认实际文件、版本和来源，不要通过随意改哈希绕过检查。资产准备与科学解释见 [模型与数据](MODEL_AND_DATA.md)。当前没有自动下载完整模型和输入数据的安装步骤。

### 6.2 无 GPU 结果回放

使用已完成真实运行冻结的回放包，目录为 `data/demo/{背景}/{扰动}/`。当前四背景均提供 ALDOA；部署时同时迁移完整包、原运行清单和哈希记录。关闭 worker/GPU 后选择“结果回放”，后端核验来源和全部文件，再建立可追溯的回放记录，不调用 STATE 或 scCellFie。

正式配置保持 `CELLLENS_ALLOW_SYNTHETIC_RESULTS=false`。合成资产只供开发契约检查，不能代替真实回放包。生产前端始终调用真实 API，不提供浏览器 Mock 开关。

## 7. 手动启动

### 7.1 前后端开发

两个终端均保持在仓库根目录。

终端一，启动后端：

```bash
uv run --no-sync uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

终端二，启动 Vite：

```bash
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

打开 `http://127.0.0.1:5173/workbench`。Vite 代理 `/api` 到 `http://127.0.0.1:8000`，浏览器使用 `VITE_API_BASE=/api`。修改后端代码后重启后端；Vite 会处理前端开发热更新。

后端端口变更时，在 `frontend/.env.local` 中配置实际 `CELLLENS_API_PROXY_TARGET`，然后重启 Vite。后端当前未配置 CORS，不要直接把浏览器 API 地址改成另一个端口。

### 7.2 构建后同源运行

```bash
npm --prefix frontend run build
uv run --no-sync uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000/workbench`。前端构建包含 TypeScript 检查，产物位于 `frontend/dist/`；后端提供 HTML、静态资源和 API。这种方式无需单独运行 Vite，缺少构建时页面返回 503，API 仍可用。

运行时采用单个 Uvicorn 进程，不添加 `--workers`。当前 worker 随 Web 进程启动，队列尚未拆成独立服务，多实例部署未验收。日常正式运行也不使用开发重载。

Windows PowerShell 若拦截 `npm.ps1`，使用 `npm.cmd --prefix frontend ...`。这是 shell 入口差异，不改变前端命令含义。

## 8. Windows 一键启动

先完成依赖、配置、首次数据库迁移和科学资产或真实回放结果准备。

构建并运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_system.ps1 -StartLocalMysql
```

复用最新构建：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_system.ps1 -StartLocalMysql -SkipBuild
```

开发模式：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_system.ps1 -StartLocalMysql -Mode Development
```

| 参数 | 行为 |
|---|---|
| `-StartLocalMysql` | 运行当前本机数据库脚本；使用 Docker/外部数据库时省略 |
| `-SkipBuild` | 生产模式跳过构建，要求 `frontend/dist/index.html` 存在且版本最新 |
| `-Mode Development` | 启动 Vite 与后端；默认页面端口 5173 |
| `-ApiPort 8001` | 更改后端端口；开发模式同步设置代理目标 |
| `-FrontendPort 5174` | 更改开发前端端口，必须与后端不同 |
| `-HostAddress 0.0.0.0` | 允许受控局域网访问；访问时使用机器实际 IP |

脚本会检查工具、数据库和迁移，前端依赖缺失时执行 `npm ci`；Python 依赖及科学资产仍需提前准备。Ctrl+C 停止 API，开发模式同时停止它启动的 Vite；独立 MySQL 不随之停止。

## 9. Linux 内部服务器部署

此部分为待实测部署方案。当前仓库没有应用 Dockerfile、独立 worker 服务或公网访问控制，不能将 Docker MySQL 启动成功等同于整个系统已部署。

服务器先完成第 2–6 节，在部署账户下安装依赖、准备配置与资产、迁移数据库、构建前端，再按第 7.2 节前台启动一次。数据库可用、网页和实际所需模式检查通过后，再接入进程管理。

### 常驻服务示例

以下示例假设源码位于 `/srv/celllens`，已创建 `celllens` 系统账户，该账户能读取模型与输入数据、写入 `data/derived/`，且 `.venv` 已创建。路径和账户应按实际服务器修改。

保存为 `/etc/systemd/system/celllens.service`：

```ini
[Unit]
Description=CellLens web and analysis service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=celllens
WorkingDirectory=/srv/celllens
Environment=PATH=/srv/celllens/.venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/srv/celllens/.venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5
TimeoutStopSec=120

[Install]
WantedBy=multi-user.target
```

后端自动读取 `/srv/celllens/.env`。服务依赖数据库可用，`After=network-online.target` 只代表网络启动顺序，不保证 MySQL 已就绪；在启动服务前检查数据库，需要与实际数据库服务绑定时另外配置对应依赖。

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now celllens
sudo systemctl status celllens
sudo journalctl -u celllens -n 100 --no-pager
```

`127.0.0.1:8000` 仅供本机访问或反向代理使用。内部局域网直连时可以将绑定地址改为 `0.0.0.0`，并使用服务器实际 IP；公网交付还需要实际网关上的认证、TLS 和网络限制，因为应用本身尚无用户认证与权限隔离。反向代理应将网页、`/assets` 和 `/api` 一起转发到同一后端，避免跨域和详情刷新路径失效。

### 发布更新

1. 停止提交新任务，等待正在执行的分析完成，再停止应用服务。
2. 备份 `.env`、MySQL、注册资产与 `data/derived/runs/`；记录当前 Git 提交。
3. 更新源码，按原依赖集合重新同步 Python 与 npm 依赖；在线部署保留 `model`、`report`。
4. 执行 `alembic upgrade head`、数据库检查与前端构建。
5. 启动服务，检查网页、数据库、模式目录及已有结果，再开放任务提交。

不要只回退源码而忽略迁移版本；数据库恢复需要与备份和迁移兼容性一起考虑。Windows 日常更新采用相同步骤，再运行带构建的一键命令。

## 10. 启动后验收与停止

| 检查 | 预期结果 |
|---|---|
| `/workbench` | 构建后页面可打开，浏览器无整体渲染错误 |
| `/api/v1/health` | `status=ok`、`database=ok`；不要只看 HTTP 200 |
| `/api/v1/ready` | 在线环境检查数据库与 worker/GPU 开关；仅回放环境 503 可符合配置 |
| `/api/v1/catalog/contexts` | 所选细胞系、所选模式可用 |
| 已完成运行详情 | 基因、代谢及报告按实际产物可访问，详情刷新正常 |

`ready` 不会实际执行 GPU 推理，catalog 也不能证明模型依赖与硬件调用都成功。完整在线验收需要真实运行；命中缓存的请求只验证结果复用。检查命令与常见问题见 [运行与检查](OPERATIONS.md)。

手动运行用各终端的 Ctrl+C 停止服务；systemd 使用 `sudo systemctl stop celllens`。Docker MySQL 可使用 `docker compose stop mysql` 停止，不需要删除数据卷。MySQL 的存储与应用结果目录应持续保留。

## 参考文档

运行方式对应现有源码；工具参数参考 [FastAPI / Uvicorn](https://fastapi.tiangolo.com/deployment/manually/)、[Vite 6](https://v6.vite.dev/guide/)、[uv 同步与额外依赖](https://docs.astral.sh/uv/concepts/projects/sync/)、[Docker Compose 启动](https://docs.docker.com/reference/cli/docker/compose/up/)、[MySQL 容器初始化](https://hub.docker.com/_/mysql) 与 [systemd 服务](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html)。

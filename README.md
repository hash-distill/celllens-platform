<p align="center">
  <img src="frontend/public/favicon.png" alt="CellLens 图标" width="96" height="96" />
</p>

# 细胞知镜 · CellLens

**单细胞基因扰动预测与代谢功能分析工作台。**

CellLens 将 STATE 的扰动表达预测与 scCellFie 的代谢任务分析整合为 Web 工作流。用户可以选择细胞背景和扰动基因，提交计算，查看单细胞状态、基因响应与代谢功能变化，追溯结果来源并导出分析报告。


![CellLens 实验工作台](docs/screenshots/response-workbench.png)

## 功能

- **扰动预测**：支持 K562、RPE1、Jurkat、HepG2，选择登记的单基因扰动，设置预测细胞数和随机种子。
- **单细胞状态**：在共同对照 PCA 坐标中比较对照、预测与可用观测，按基因或代谢任务着色，查看累积分布。
- **基因响应**：查看平均表达、预测变化和匹配观测，筛选基因并联动单细胞图。
- **代谢功能**：比较任务与反应分数，浏览任务—反应—基因关联、GPR 规则、完整性指标和缺失基因。
- **实验管理**：查看任务进度，检索服务器实验记录，选择多个已完成实验进行比较，按章节解读结果。
- **来源与导出**：记录参数、模型与数据版本、文件哈希；导出 CSV、HTML 报告、关联与完整性 JSON，以及 SVG/PDF/PNG 科研图。

- **设置与辅助解读**：亮暗与跟随系统外观、页面快捷栏、OpenAI 兼容 API 配置；预览已保存结果摘要后生成解读、覆盖说明或验证建议，并下载带来源的 JSON。

### 分析工作流

新建实验执行在线推演：选择登记的单基因扰动，设置 64–4,096 个预测细胞及随机种子，由 STATE 生成预测并进行表达与代谢分析。已有结果从“实验记录”直接打开，无需再次创建任务。


在线可用背景与扰动由资产注册表和服务状态决定。代谢分数表示表达对功能的支持程度，完整性指标描述基因覆盖；结果解读见 [模型与数据](docs/MODEL_AND_DATA.md)。

## 技术栈

| 层次 | 组件 |
|---|---|
| 前端 | Vue 3、TypeScript、Pinia、Vite、ECharts、Three.js |
| 后端 | Python、FastAPI、Pydantic、SQLAlchemy |
| 科学计算 | STATE、scCellFie、AnnData、Scanpy |
| 存储 | MySQL、Alembic 迁移、文件式分析产物 |

## 安装与启动

环境需要 Python 3.11 或 3.12、uv、Node.js/npm 和 MySQL。在线计算还需要兼容当前 PyTorch/CUDA 依赖的 NVIDIA GPU。依赖版本以 `uv.lock` 和 `frontend/package-lock.json` 为准。

源码包含注册表、配置、基因面板和冻结代谢数据库。模型权重、原始 H5AD、真实回放包及历史运行产物需要另行准备。

### 1. 获取源码并安装依赖

以下命令在仓库根目录执行：

```bash
git clone https://github.com/hash-distill/celllens-platform.git
cd celllens-platform
uv sync --locked --python 3.11 --extra model --extra report --group dev
npm --prefix frontend ci
```

### 2. 配置数据库

将 `.env.example` 复制为 `.env`，设置 `CELLLENS_DATABASE_URL`。默认连接 `127.0.0.1:3307` 上的 `celllens` 库（账户 `celllens`，密码 `celllens_dev`）。以下三种方式任选其一；`3307` 同一时间只能由一个实例占用。

#### 2.1 本机独立实例

项目代码文件预设置了一键启动数据库的脚本，里面相应配置按本地环境进行修改：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_mysql.ps1
```

脚本启动或复用 `127.0.0.1:3307` 的实例：

| 项目 | 值 |
|---|---|
| 程序 | `D:\Mysql\mysql-9.2.0-winx64\bin\mysqld.exe` |
| 数据目录 | `D:\Mysql\celllens-data` |
| 错误日志 | `D:\Mysql\celllens-data\celllens-mysql.err` |
| 连接 | `127.0.0.1:3307`、`celllens` / `celllens_dev`、库 `celllens` |

**该实例由脚本手动拉起，没有配置开机自动启动：重启电脑后必须先重新运行脚本，否则后端无法启动。**

#### 2.2 Docker 容器

```bash
docker compose up -d mysql
docker compose ps mysql
```

等待状态为 `healthy`。容器使用 MySQL 8.4，宿主机 `3307` 映射到容器 `3306`，数据存入命名卷 `celllens_mysql_data`；空数据卷首次初始化时创建 `celllens` 库与账户。只修改 `.env` 不会同步修改 Compose 中的固定密码，两边需保持一致。

#### 2.3 连接已有 MySQL

由数据库管理员预先创建 `celllens` 库与应用账户，授予该库的业务读写与迁移所需权限，再设置 `CELLLENS_DATABASE_URL`。运行时需支持项目使用的事务与命名锁（`GET_LOCK`）。

#### 2.4 迁移与连接检查

数据库可连接后先建表，再执行完整检查：

```bash
uv run --no-sync alembic upgrade head
uv run --no-sync python scripts/check_mysql.py
```

检查成功输出 `MySQL schema and durable run round trip: OK`，覆盖运行所需表、命名锁与运行的写入/读取。

#### 2.5 数据库故障排查

后端启动即退出、终端最后停在 `ERROR: Application startup failed. Exiting.`，绝大多数情况是数据库不可达。开启 worker 时启动流程会查询可恢复任务，数据库连不上就会终止启动：

```
pymysql.err.OperationalError: (2003, "Can't connect to MySQL server on '127.0.0.1'
  ([WinError 10061] 由于目标计算机积极拒绝，无法连接。)")
```

按顺序检查：

1. 确认 `3307` 正在监听。没有输出说明 CellLens 实例未启动，运行 `.\scripts\start_mysql.ps1`：

   ```powershell
   netstat -ano | Select-String ':3307'
   ```

2. **`3306` 上有 MySQL 在运行，不代表 `celllens` 可用。** 本机可能另有一个监听 `3306` 的 MySQL 服务（例如 Windows 服务 `MySQL92`，数据目录 `D:\Mysql\mysql-9.2.0-winx64\Data`），与 `3307` 的 CellLens 实例是两套互不相干的数据，默认配置下不能互相替代。
3. 仍连不上时查看 `D:\Mysql\celllens-data\celllens-mysql.err` 末尾，并核对 `.env` 中的账户、密码与库名是否与实例一致。
4. 只想先确认代码与依赖是否正常，可在**当前这一次**启动命令前临时关闭 worker：该模式启动时不查询数据库，服务能正常起来。`/api/v1/health` 仍会如实报告数据库状态（连不上时为 `{"status":"degraded","database":"unavailable"}`），`/api/v1/ready` 因 `worker=false` 返回 `503`。

   PowerShell 用子作用域，退出即恢复，不污染当前终端：

   ```powershell
   & { $env:CELLLENS_WORKER_ENABLED = 'false'; uv run --no-sync uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 }
   ```

   **不要**在终端里执行 `$env:CELLLENS_WORKER_ENABLED = "false"` 后继续用同一个终端启动正式服务：环境变量优先级高于 `.env`，会一直覆盖 `.env` 中的 `true`，导致状态页“在线扰动推演”显示**未启用**且不报错。若已这样设置过，用 `Remove-Item Env:CELLLENS_WORKER_ENABLED` 清除，或直接开一个新终端。

Docker Compose 只启动 MySQL，不启动应用；应用需要单独启动。完整部署流程与 Linux 方案见[部署文档](docs/DEPLOYMENT.md)。

### 3. 准备科学资产


按照 [模型与数据说明](docs/MODEL_AND_DATA.md) 获取匹配版本的模型与数据，并放到注册表指定的位置：

| 内容 | 配置或目录 |
|---|---|
| 模型目录、检查点及配套文件 | `data/registry/models.json` → `models/` |
| 对照与观测 H5AD | `data/registry/datasets.json` → `data/raw/` |
| 模型配置与有序基因面板 | `configs/models/`、`data/registry/state_*_genes.txt` |
| 代谢数据库 | `data/registry/sccellfie/human/` |
| 真实回放包 | `data/demo/{背景}/{扰动}/` |

在线计算资产准备后运行：

```bash
uv run --no-sync python scripts/audit_registry.py
```

仅查看已保存的历史结果时，可**编辑根目录 `.env` 文件**（不是 shell 环境变量）将 `CELLLENS_WORKER_ENABLED` 和 `CELLLENS_GPU_AVAILABLE` 设为 `false`，然后重启后端。依赖与资产要求见 [部署文档](docs/DEPLOYMENT.md)。

### 4. 构建并启动

```bash
npm --prefix frontend run build
uv run --no-sync uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

打开 [应用首页](http://127.0.0.1:8000/) 或 [API 文档](http://127.0.0.1:8000/docs)。构建后由后端同时提供前端页面与 API。

数据库不可达时命令会在 `Application startup failed. Exiting.` 处退出，排查步骤见 2.5。Windows 上可用一条命令完成数据库检查、迁移、前端构建与启动：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_system.ps1 -StartLocalMysql
```

`-StartLocalMysql` 会先执行 `scripts/start_mysql.ps1`，随后检查数据库并运行迁移；`-SkipBuild` 跳过前端构建，`-Mode Development` 额外启动 Vite 开发服务。独立 MySQL 实例不随脚本停止。

服务使用单个 Uvicorn 进程。实验与分析结果为共享科研入口，部署时应使用受控网络。服务器配置见 [部署文档](docs/DEPLOYMENT.md)。

## 使用

1. 打开“实验工作台”，选择细胞背景、运行模式和扰动基因。
2. 设置预测细胞数和随机种子，提交实验并查看执行进度。
3. 运行完成后浏览单细胞状态、基因响应和代谢功能；查看关联基因、完整性与来源记录。
4. 在“实验记录”中检索已有运行，加入“实验比较”，或导出本次结果。

详细操作见 [使用指南](docs/guide/USER_GUIDE.md)。

## 开发

完成依赖、数据库和资产配置后，在两个终端分别启动后端与前端：

```bash
# 终端一
uv run --no-sync uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

# 终端二
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

开发页面为 `http://127.0.0.1:5173`，`/api` 默认代理到后端 8000 端口。Windows PowerShell 可使用 `npm.cmd` 执行 npm 命令。

开发检查：

```bash
uv run --no-sync pytest -q
uv run --no-sync ruff check backend scripts
uv run --no-sync basedpyright
npm --prefix frontend run build
```

## 目录

```text
celllens-platform/
├── backend/          API、计算适配、业务服务、迁移与测试
├── frontend/         页面、图表、功能网络与状态管理
├── configs/          模型、分析与数据划分配置
├── data/registry/    资产注册表、基因面板与冻结数据库
├── scripts/          启动、资产准备与检查工具
├── docs/             使用、部署、接口与技术文档
├── licenses/         第三方许可原文与来源清单
├── ops/              本地数据库配置参考
├── pyproject.toml    Python 依赖与开发配置
└── uv.lock           Python 依赖锁文件
```

## 文档

- [使用指南](docs/guide/USER_GUIDE.md)
- [设置与大模型辅助解读](docs/guide/ASSISTANT_SETTINGS.md)
- [部署与启动](docs/DEPLOYMENT.md)
- [系统架构](docs/ARCHITECTURE.md)
- [API 说明](docs/API.md)
- [模型与数据](docs/MODEL_AND_DATA.md)
- [前端开发](docs/FRONTEND.md)
- [脚本索引](scripts/README.md)
- [完整文档目录](docs/README.md)

## 许可

项目自有代码与文档采用 [MIT License](LICENSE)。第三方方法、模型、数据库与结果的适用条款见 [NOTICE](NOTICE) 和 [第三方许可说明](docs/THIRD_PARTY_NOTICES.md)；根目录 MIT 不替代这些上游许可。





代谢通路     真实测验

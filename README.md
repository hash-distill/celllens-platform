<p align="center">
  <img src="frontend/public/favicon.png" alt="CellLens 图标" width="96" height="96" />
</p>

# 细胞知镜 · CellLens

**单细胞基因扰动预测与代谢功能分析工作台。**

CellLens 将 STATE 的扰动表达预测与 scCellFie 的代谢任务分析整合为 Web 工作流。用户可以选择细胞背景和扰动基因，提交计算，查看单细胞状态、基因响应与代谢功能变化，追溯结果来源并导出分析报告。

也可以直接上传自己的表达 H5AD，完成数据质控、PCA、分组表达比较与 scCellFie 代谢分析，在共享科研工作区管理数据版本和分析结果，无需登录或注册。

![CellLens 实验工作台](docs/screenshots/response-workbench.png)

## 功能

- **扰动预测**：支持 K562、RPE1、Jurkat、HepG2，选择登记的单基因扰动，设置预测细胞数和随机种子。
- **单细胞状态**：在共同对照 PCA 坐标中比较对照、预测与可用观测，按基因或代谢任务着色，查看累积分布。
- **基因响应**：查看平均表达、预测变化和匹配观测，筛选基因并联动单细胞图。
- **代谢功能**：比较任务与反应分数，浏览任务—反应—基因关联、GPR 规则、完整性指标和缺失基因。
- **实验管理**：查看任务进度，检索服务器实验记录，选择多个已完成实验进行比较，按章节解读结果。
- **来源与导出**：记录参数、模型与数据版本、文件哈希；导出 CSV、HTML 报告、关联与完整性 JSON，以及 SVG/PDF/PNG 科研图。
- **用户数据分析**：上传人类 H5AD 的 X 或 layers，声明表达单位和文库范围，查看校验结果、管理数据集并创建 CPU 分析任务；使用完整上传面板分析代谢功能。
- **数据与任务管理**：按名称搜索数据集，为分析命名，按数据集和状态筛选任务，复查来源与结果，归档后保留既有数据和分析记录。

### 分析工作流

新建实验执行在线推演：选择登记的单基因扰动，设置 64–4,096 个预测细胞及随机种子，由 STATE 生成预测并进行表达与代谢分析。已有结果从“实验记录”直接打开，无需再次创建任务。

上传分析独立处理用户的 H5AD 表达数据，使用 CPU 完成质控、PCA、分组描述性比较和代谢分析。无需登录；数据与分析记录在当前部署中共享。上传文件不会自动接入 STATE 在线预测。

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

将 `.env.example` 复制为 `.env`，设置 `CELLLENS_DATABASE_URL`。可以连接已有 MySQL，也可以使用仓库中的数据库容器：

```bash
docker compose up -d mysql
docker compose ps mysql
```

等待数据库状态为 `healthy` 后执行迁移和连接检查：

```bash
uv run --no-sync alembic upgrade head
uv run --no-sync python scripts/check_mysql.py
```

Compose 的默认连接信息与 `.env.example` 一致。更改账户或密码时需同时修改数据库配置与连接 URL。Docker Compose 只启动 MySQL，应用需要单独启动。

### 3. 准备科学资产

用户表达探索无需 STATE 权重或登记的对照数据；上传代谢分析需要下述冻结 scCellFie 数据库与科学依赖。只有预设扰动预测工作流需要准备完整模型资产。

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

仅使用历史结果与上传分析时，可关闭 `CELLLENS_WORKER_ENABLED` 和 `CELLLENS_GPU_AVAILABLE`；上传分析需启用 `CELLLENS_DATA_WORKER_ENABLED=true`。依赖与资产要求见 [部署文档](docs/DEPLOYMENT.md)。

### 4. 构建并启动

```bash
npm --prefix frontend run build
uv run --no-sync uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

打开 [应用首页](http://127.0.0.1:8000/) 或 [API 文档](http://127.0.0.1:8000/docs)。构建后由后端同时提供前端页面与 API。

服务使用单个 Uvicorn 进程。上传数据、分析结果和预设实验均为共享科研入口，部署时应使用受控网络。无 GPU 上传分析与服务器配置见 [部署文档](docs/DEPLOYMENT.md)。

### 5. 启用上传数据分析

在 `.env` 设置 `CELLLENS_DATA_WORKER_ENABLED=true`，执行 `alembic upgrade head` 并重启应用。打开“上传分析”，直接上传数据并创建任务，无需创建账号。CPU 表达与代谢分析不依赖 GPU worker；若只使用上传数据分析，可设置 `CELLLENS_WORKER_ENABLED=false`、`CELLLENS_GPU_AVAILABLE=false`。

数据集按独立版本保存，任务与结果在服务器持久化；能访问系统的人可查看共享工作区数据。数据格式、接口、配额与分组分析说明见[用户数据指南](docs/guide/USER_DATA.md)。首期支持人类 H5AD；自有数据直接驱动 STATE 预测尚未开放。

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
- [部署与启动](docs/DEPLOYMENT.md)
- [系统架构](docs/ARCHITECTURE.md)
- [API 说明](docs/API.md)
- [模型与数据](docs/MODEL_AND_DATA.md)
- [前端开发](docs/FRONTEND.md)
- [脚本索引](scripts/README.md)
- [完整文档目录](docs/README.md)

## 许可

项目自有代码与文档采用 [MIT License](LICENSE)。第三方方法、模型、数据库与结果的适用条款见 [NOTICE](NOTICE) 和 [第三方许可说明](docs/THIRD_PARTY_NOTICES.md)；根目录 MIT 不替代这些上游许可。

# 运行与检查

环境准备、数据库初始化、开发/构建模式、Windows 脚本及服务器部署统一见 [部署与启动](DEPLOYMENT.md)。本文用于启动后的检查、维护与故障排查，命令均在仓库根目录执行。

## 日常启动与停止

已配置的 Windows 本机，前端构建最新时：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_system.ps1 -StartLocalMysql -SkipBuild
```

前端修改后去掉 `-SkipBuild`。使用 Docker 或外部数据库时省略 `-StartLocalMysql`，并提前启动实际数据库。首次空数据库必须先迁移，详见部署文档。

生产页面为 `http://127.0.0.1:8000/workbench`，开发页面默认端口为 `5173`。Ctrl+C 停止应用服务；独立 MySQL 继续运行。当前本机独立实例没有开机自动启动，重启电脑后需再运行数据库或系统脚本。

## 服务与模式检查

| 地址 | 检查内容 |
|---|---|
| `/api/v1/health` | 响应应包含 `status=ok`、`database=ok` |
| `/api/v1/ready` | 数据库与 worker/GPU 开关就绪状态 |
| `/api/v1/catalog/contexts` | 细胞系的在线、预计算及验证资产状态 |
| `/api/v1/catalog/perturbations?cell_line=K562&mode=precomputed` | 当前通过清单/哈希校验的预计算组合 |
| `/docs`、`/openapi.json` | 实时接口契约与请求调试 |

`health` 在数据库故障时仍可能返回 HTTP 200，要读取响应字段。`ready` 未满足全部开关时返回 503；关闭 GPU/worker 的结果回放环境可正常使用预计算，不能把该 503 直接判成回放不可用。在线资产状态以 catalog 与资产审计为准，硬件/依赖调用仍需真实推理验证。

## 检查命令

基础工程检查需要 `dev` 依赖组：

```bash
uv pip check
uv run --no-sync pytest -q
uv run --no-sync ruff check backend scripts
uv run --no-sync basedpyright
npm --prefix frontend run build
```

数据库、资产与接口检查：

```bash
uv run --no-sync python scripts/check_mysql.py
uv run --no-sync alembic check
uv run --no-sync python scripts/audit_registry.py
uv run --no-sync python scripts/export_openapi.py
```

`check_mysql.py` 检查迁移表、命名锁与临时运行记录，结束时清理自身记录。`alembic check` 比较数据库与模型，需要数据库可用；`audit_registry.py` 检查启用资产的文件与哈希，刚克隆且未准备科学资产时不应宣称该审计已通过。`export_openapi.py` 会更新 `docs/openapi.json`，接口变更后将快照一并提交。

### 真实在线冒烟

在具有完整 `model`、`report` 依赖、GPU、资产和数据库的环境中：

```bash
uv run --no-sync python scripts/smoke_backend.py
```

脚本使用真实 MySQL 和应用生命周期，提交 K562/MYC、64 细胞、seed=42 的在线请求，检查六类结果接口。它可能调用 GPU、创建持久运行与磁盘产物，不属于纯静态检查。`cache_hit=true` 表示读取已有结果，不能记为本次新推理。

### 前端回归

先启动开发服务，再执行：

```bash
uv run --no-sync python scripts/check_frontend.py --url http://127.0.0.1:5173
```

此检查需要执行命令的 Python 环境另外安装 Playwright 与 Chromium；它们尚未纳入仓库依赖组。检查覆盖响应正文超时/取消/中断、串行轮询、Mock 来源与刷新、来源隔离和基因分页，使用独立浏览器上下文，不修改用户浏览器。

Windows 构建入口使用 `frontend/.cache/build-tmp` 隔离临时文件，避免共享临时目录中的 esbuild 访问错误；缓存不纳入 Git。

## 已有验收记录

2026-10-04 本机联调记录：

- 38 项后端测试、Ruff、basedpyright 通过；测试有两条上游弃用警告。
- 前端生产构建通过，无大包警告；9 项浏览器缺陷回归通过。
- 新建 K562/MYC、64 细胞、seed=42 在线运行 `run_5fff9141331b469d`，`cache_hit=false`，STATE 与代谢分析实际完成，warnings 为空。
- 详情刷新、2000 行基因 CSV、141 项已生成有效任务、HTML 报告及 1366/1100/768 宽度检查通过。

这是历史验收状态，不能代替更新代码、更换依赖、迁移数据库或更换资产后的重新检查。当前匹配验证协议仍待确认，也没有完成目标 Linux 服务器和 Docker MySQL 的部署验收。

## 数据持久化与维护

MySQL 保存六张表：`runs`、`run_attempts`、`run_events`、`run_artifacts`、`run_cache`、`alembic_version`。模型、输入与结果文件保存在磁盘；文件清单与数据库产物记录需要一致。

备份至少包含数据库、`.env`、`data/registry/`、`configs/`、所引用的模型/输入文件及 `data/derived/runs/`，同时记录 Git 提交和迁移版本。真实回放包也应完整备份。仅复制数据库不能恢复文件产物；仅复制结果文件也不会重建运行记录。

更新前等待分析完成，备份后执行部署文档中的更新流程。不要从文件系统单独删除运行目录来做清理：当前没有已实现的自动保留策略或运行删除接口，需同时考虑产物、缓存和数据库记录。`configs/app.yaml` 的保留天数不是已执行的清理任务。

## 常见问题

| 现象 | 原因与处理 |
|---|---|
| 数据库报 2003 / 10061、连接被拒绝 | 先检查 `3307` 是否监听，启动实际数据库，再核对主机与端口 |
| Navicat 报 1045 / Access denied | 检查账号与密码；本机使用 `celllens` / `celllens_dev`，不是未验证的 root 凭据 |
| 1044 指向 `performance_schema` | 账号已认证，但没有监控库权限；默认数据库选 `celllens`，项目不依赖性能库 |
| 一键脚本提示 Missing MySQL tables | 新数据库先执行 `alembic upgrade head`；脚本检查在其内部迁移之前 |
| 页面返回 503 | 缺少 `frontend/dist/index.html`；构建前端或去掉 `-SkipBuild` |
| 页面显示旧版本 | 重建前端；确认实际服务使用的仓库与构建目录 |
| 8000 / 5173 已被占用 | 检查已运行的项目进程；选择其他端口并同步开发代理，避免重复启动 |
| PowerShell 拦截 npm.ps1 | 使用同一命令的 `npm.cmd` 入口 |
| online 返回 503 | 检查 worker/GPU、注册资产、catalog 原因；开关不代表真实 GPU 检测成功 |
| 预计算列表为空 | 生成或恢复相应包，核对 manifest 与文件哈希；目录存在不等于包有效 |
| 请求返回 422 | 扰动支持列表、细胞数/seed 范围或额外字段不符合契约 |
| validation 接受后失败 | 匹配观测可能没有该扰动；前端当前不开放提交，协议仍待确认 |
| completed 但无代谢结果 | 查看 warnings、覆盖等级、冻结数据库与表达要求 |
| 单个结果返回 404 | 该运行没有生成对应产物；历史或部分结果可能缺少对应产物，应核对该运行文件清单 |
| 浏览器跨域失败 | 当前后端无 CORS；开发用 Vite 代理，构建运行用后端同源页面 |
| Compose 修改密码后连接仍失败 | 初始化变量不更新已有数据卷账户，需核对实际账户与 `.env` |

Windows 端口检查：

```powershell
Get-NetTCPConnection -LocalPort 3307 -State Listen
Get-NetTCPConnection -LocalPort 8000 -State Listen
```

本机数据库错误日志为 `D:\Mysql\celllens-data\celllens-mysql.err`；容器数据库查看 `docker compose logs --tail 100 mysql`。科学计算错误详情先查运行接口，再查对应结果目录中的 `failure.json`、STATE 标准输出和错误日志。

# 运行与检查

更新日期：2026-10-22。首次安装、依赖、数据库初始化与服务器配置见[部署与启动](DEPLOYMENT.md)。本文命令在仓库根目录执行，示例显式使用端口 **8001**；启动脚本默认仍为 **8000**，更换端口后同步调整访问地址。

## 启动与运行检查

已有本机项目 MySQL 时：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_system.ps1 -StartLocalMysql -ApiPort 8001
```

使用容器或外部数据库时先启动对应实例，再省略 `-StartLocalMysql`。脚本迁移数据库、检查表结构并按需构建前端；只有确定现有构建对应当前代码时才用 `-SkipBuild`。访问 `http://127.0.0.1:8001/measured`。`Ctrl+C` 停止应用，独立数据库仍继续运行。

无 GPU 时将 `.env` 中 `CELLLENS_WORKER_ENABLED=false`、`CELLLENS_GPU_AVAILABLE=false`，安装 `analysis` 和所需 `report` 依赖后使用实测 CPU 分析。页面启动和实测分析不要求 STATE 权重；新预测仍需相应 GPU、依赖与资产。模型下载不安装 Python 依赖或驱动。

| 接口或入口 | 检查内容 |
|---|---|
| `/api/v1/health` | 读取响应中的服务与数据库字段，不只看 HTTP 状态 |
| `/api/v1/ready` | 预测运行的数据库、worker/GPU 开关状态；不能代替真实推理 |
| `/api/v1/catalog/contexts` | 按背景查看在线资产与不可用原因 |
| `/api/v1/measured/analyses` | 独立实测任务历史；不执行模型预测 |
| `/api/v1/runs` | 预测及保留的历史运行列表 |
| `/status` | 后端实际主机的服务、硬件与按背景资源准备 |
| `/docs`、`/openapi.json` | 运行服务的实时接口契约 |

预测开关关闭时 `/ready` 可能返回 503；这本身不说明实测 CPU 分析或已保存结果读取失败。验证实测能力应实际提交有真实数据的背景/目标，检查完成状态、输入人数、结果文件和导出。服务页未取得的信息不等于正常或零。

## 工程与运行验收

依赖与静态、回归检查：

```powershell
uv pip check
uv run --no-sync pytest backend/tests -q
uv run --no-sync ruff check backend/app scripts
uv run --no-sync basedpyright
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend run build
```

测试需要 `dev` 依赖组；科学计算检查还需要相应 extras。数据库与资产检查：

```powershell
uv run --no-sync python scripts/check_mysql.py
uv run --no-sync alembic check
uv run --no-sync python scripts/audit_registry.py
uv run --no-sync python scripts/export_openapi.py
```

数据库检查需要已启动实例。注册表审计遍历登记资产；未下载的可选背景可以报告缺失，不能仅因页面可打开就宣称完整资产审计通过。`export_openapi.py` 更新仓库快照，接口改动后应核对差异。

完整体验验收至少分别记录：

1. **实测链路：**从数据目录选择真实组合，提交 CPU 分析，核对共同批次、真实人数、共同面板、关键数值和完整下载；确认没有生成预测群体。
2. **预测链路：**具备 GPU 和资产后提交在线预测，记录 `run_id`、是否命中缓存、实际命令日志及产物；检查 `/runs/:runId` 刷新和旧链接跳转。
3. **匹配比较：**有真实观测时核对比较群体、共同面板、不变化基线及失败案例；没有时显示原因，不补造数值。
4. **AI 辅助：**分别核对实测与预测摘要、任务限制、来源和切换行为。受控回复验证协议，真实模型质量需要独立人工评价。

`scripts/smoke_backend.py` 会提交真实在线请求，可能使用 GPU、创建持久记录及文件；命中缓存不算新推理。浏览器检查按[脚本索引](../scripts/README.md)选择当前脚本和适用入口，需要相应浏览器依赖。历史专项脚本的旧路由、截图和测试数不自动代表当前版本。

历史证据保留在[文档验收索引](README.md#截图与检查记录)。每次验收应记录代码版本、日期、依赖/资产、命令、范围、失败与未验收事项；工程通过不能替代独立生物学验证。目标服务器与公开访问状态必须现场核验，不从历史本机记录推断。

## 备份、迁移与清理

数据库包括 `runs`、`run_attempts`、`run_events`、`run_artifacts`、`run_cache`、`measured_analyses` 六张业务表，以及 `alembic_version`。备份应在停止新增提交、等待当前分析结束后进行，保留数据库和文件的一致快照：

- 数据库、Git 提交、迁移版本、依赖锁文件和配置；`.env` 含凭据，应限制访问。
- `data/registry/`、`configs/`、登记引用的模型和真实输入文件。
- `data/derived/runs/`、`data/derived/measured/`、匹配观测比较包及其依赖输入；不能只备份预测目录。
- 资源准备状态、源目录缓存和完整历史冻结包；按 manifest 保存相关文件和 SHA-256。

最稳妥的迁移包含完整 `data/derived/` 及所有被引用的输入。仅复制数据库不能恢复科学产物，仅复制文件不能恢复历史记录。恢复后检查迁移版本、登记路径/哈希，并抽查一条实测和一条预测记录的详情及导出。

更新代码前备份，再按部署文档迁移和构建。不要单独删除运行或实测目录；清理须同时处理数据库、缓存、manifest 和输入引用。配置中的保留天数不代表已有自动清理任务。历史失败案例、科学数据、来源和许可证不属于无用缓存。

## 常见故障

| 现象 | 检查与处理 |
|---|---|
| MySQL 2003 / WinError 10061 | 确认 `.env` 实际端口有监听，先启动数据库；默认项目实例是 3307 |
| 新库缺表或迁移不一致 | 按部署流程执行 Alembic 迁移，核对包含 `measured_analyses`，不要手工拼表 |
| 页面 503 或显示旧界面 | 检查前端构建与运行的仓库位置；构建后刷新 |
| 端口被占用 | 检查占用进程或改 `-ApiPort`，同步浏览器与开发代理地址 |
| PowerShell 拦截 npm.ps1 | 使用 `npm.cmd` |
| 无法新建预测 | 查看背景资产、worker/GPU 开关和真实驱动/依赖；新建只接受 `online` |
| 实测提取失败 | 核对固定源网络、真实数据范围和 analysis 依赖；上限不等于实际人数 |
| 实测中断或取消 | 查看该分析状态与错误，修复后重新提交；临时目录不当作已发布结果 |
| completed 但部分图/代谢不可用 | 读取 warnings 与对应产物；完成不保证所有可选分析可用 |
| 旧记录缺少关联或比较 | 按原清单显示可用范围，不拿其他运行或当前数据库补造结果 |
| AI 实测任务不能选图表/比较 | 实测当前只支持结果概要、基因、代谢、覆盖和后续建议 |
| Compose 改密码仍认证失败 | 初始化变量不会改写已有数据卷账户，核对实际账户与 `.env` |

Windows 可用 `Get-NetTCPConnection -LocalPort 3307 -State Listen` 和实际 API 端口检查监听。数据库日志位置取决于实例配置；容器可查看 Compose 的 MySQL 日志。科学计算故障先查状态接口，再查看相应结果/临时目录和 STATE 输出日志，避免将凭据或原始细胞数据贴入公开日志。

# 脚本索引

所有命令从仓库根目录运行。脚本按用途保留，避免将仍可用于资产重建的工具误认为运行时必需步骤。

## 日常启动与检查

| 脚本 | 用途 |
|---|---|
| `start_system.ps1` | Windows 启动或复用数据库、构建前端并启动后端 |
| `start_mysql.ps1` | Windows 独立 MySQL 启动 |
| `check_mysql.py` | 数据库连接与表检查 |
| `audit_registry.py` | 注册资产、哈希与冻结数据库检查 |
| `smoke_backend.py` | 后端链路冒烟；按参数可能执行真实推理 |

## 前端检查

| 脚本 | 环境 | 产物 |
|---|---|---|
| `check_frontend.py` | 后端与 Vite；显式 Mock 回归 | 终端检查结果 |
| `check_3d_frontend.py` | 兼容入口，委托当前响应工作台/功能网络检查，须提供 --run-id | `reports/frontend/response/` |
| `check_navigation_frontend.py` | 真实 API；首页、服务器记录、分页筛选、导航、预计算提交与响应式检查，须提供 --run-id | `reports/frontend/navigation/` |
| `check_production_frontend.py` | 已构建前端、由后端提供页面 | `reports/frontend/production/` |
| `check_required_projection_frontend.py` | 真实 API；遍历全部完成实验、旧/新预计算投影、并排/叠加、刷新与手机布局 | `reports/frontend/projection/` |
| `check_response_frontend.py` | 真实已完成运行，含冻结追溯；用独立浏览器上下文注入局部错误 | `reports/frontend/response/` |
| `check_metabolism_frontend.py` | 单选覆盖等级、空分类、搜索、实际条形点击、真实与旧任务详情、缺失结果请求及手机布局 | `reports/frontend/metabolism-fix/` |

生产检查示例：

```bash
python scripts/check_production_frontend.py --url http://127.0.0.1:8000 --smoke
```

浏览器脚本需要其 Python 环境中的 Playwright 与 Chromium。`check_production_frontend.py` 由原 `inspect_3d_frontend.py` 更名，保留原生产页面检查功能。

## 资产准备与契约导出

| 脚本 | 用途 |
|---|---|
| `extract_gene_list.py` | 从模型自身保存的 `var_dims.pkl` 提取有序基因面板 |
| `extract_replogle_k562.py` | 从上游数据按范围读取 K562 子集；使用仓库内 `configs/splits/replogle-k562-source.toml` |
| `prepare_context_assets.py` | 固定官方 revision，下载并校验 RPE1/Jurkat/HepG2 的 ST-HVG 配套资产，抽取真实对照；仅 `--phase register` 修改登记表 |
| `smoke_contexts.py` | 三个新增背景的 MySQL + CUDA + STATE + scCellFie 真实运行；要求新推理，核验 H5AD、预测群体、清单和结果接口 |
| `check_contexts_frontend.py` | 核验四背景选择、扰动列表及三个真实结果页面；使用 `--runs reports/context-integration-2026-10-08/real_runs.json` 读取运行编号 |
| `attach_replogle_hvg.py` | 给已有 H5AD 补齐注册面板矩阵 |
| `register_assets.py` | 计算注册所需哈希；`--write` 会更新注册表 |
| `build_demo_bundle.py` | 生成明确标注的合成演示包，含单细胞表达矩阵与二维投影 |
| `repair_demo_projections.py` | 默认只盘点；--apply 对明确合成的旧演示补充矩阵/投影/来源，保留原运行文件；真实结果不得补合成点 |
| `export_openapi.py` | 导出接口快照 |

资产准备脚本会写入数据或注册文件；日常启动已准备好的系统时无需重复执行。`replogle-k562-source.toml` 是上游来源拆分快照，不能代替项目正式评价协议；当前协议限制见 [模型与数据](../docs/MODEL_AND_DATA.md)。

补齐旧预计算记录：先运行 `python -m scripts.repair_demo_projections` 盘点，再用 `--apply` 执行。产物审计写入 `reports/projection-repair/`，包清单修改前保存在 backups 中。必须使用安装了科学依赖且能连接项目数据库的 Python 环境。

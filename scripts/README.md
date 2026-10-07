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
| `check_3d_frontend.py` | 后端与 Vite；真实 API 与 WebGL | `reports/frontend/3d/` |
| `check_production_frontend.py` | 已构建前端、由后端提供页面 | `reports/frontend/production/` |

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
| `attach_replogle_hvg.py` | 给已有 H5AD 补齐注册面板矩阵 |
| `register_assets.py` | 计算注册所需哈希；`--write` 会更新注册表 |
| `build_demo_bundle.py` | 生成明确标注的合成演示包 |
| `export_openapi.py` | 导出接口快照 |

资产准备脚本会写入数据或注册文件；日常启动已准备好的系统时无需重复执行。`replogle-k562-source.toml` 是上游来源拆分快照，不能代替项目正式评价协议；当前协议限制见 [模型与数据](../docs/MODEL_AND_DATA.md)。

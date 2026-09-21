# API 契约

服务根路径：`/api/v1`。

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/health` | 服务存活检查 |
| GET | `/ready` | MySQL、worker 和 GPU 就绪检查 |
| GET | `/catalog/contexts` | 细胞背景及在线/验证可用状态 |
| GET | `/catalog/perturbations?cell_line=K562` | 审计后的扰动列表 |
| POST | `/runs` | 创建任务，返回 202 |
| GET | `/runs/{run_id}` | 查询阶段、进度、警告和错误 |
| GET | `/runs/{run_id}/summary` | 读取前端汇总结果 |
| GET | `/runs/{run_id}/projection` | 有上限、保留来源分层的二维投影 |
| GET | `/runs/{run_id}/genes?limit=2000` | 基因差异表 |
| GET | `/runs/{run_id}/metabolic-tasks?limit=1000` | 代谢任务差异摘要 |
| GET | `/runs/{run_id}/reactions?limit=1000` | 按绝对差异排序的反应聚合 |
| GET | `/runs/{run_id}/report` | 下载确定性 HTML 报告 |

创建任务示例：

```json
{
  "cell_line": "K562",
  "perturbation": "MYC",
  "mode": "online",
  "n_cells": 512,
  "seed": 42
}
```

相同请求、资产、代谢库和代码指纹命中已完成结果时，`POST /runs` 返回原 `run_id` 且 `cache_hit=true`。资产未注册、GPU 不可用或扰动不在支持列表时，接口会返回明确错误码，不回退到随机结果。运行 `uv run python scripts/export_openapi.py` 可生成完整 `docs/openapi.json`。

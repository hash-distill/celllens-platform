# 接口说明

默认 API 前缀 `/api/v1`。模型定义在 `backend/app/schemas.py`，路由位于 `backend/app/api/` 与 `main.py`。完整结构见 [openapi.json](openapi.json)；服务的 `/openapi.json` 是实时契约。

## 创建与查询运行

先查 catalog 获取模式就绪状态与支持扰动，再创建运行；取得编号后轮询状态，进入 completed 再读取产物。

```json
{
  "cell_line": "K562",
  "perturbation": "MYC",
  "mode": "online",
  "n_cells": 64,
  "seed": 42
}
```

| 字段 | 约束 |
|---|---|
| `cell_line` | K562 或 RPE1；后者当前禁用 |
| `perturbation` | 1–64 字符，字母/数字/下划线/点/连字符；自动转大写，在线请求须在支持列表 |
| `mode` | online、validation、precomputed；默认 online |
| `n_cells` | 64–4096，默认 512；请求推理细胞数，不是质量指标 |
| `seed` | 0–2147483647，默认 42 |

额外字段被拒绝。POST /runs 成功返回 202 和 `run_id`、`status`、`cache_hit`。缓存或预计算可直接返回 completed，不一定经过可见的排队过程。

| 模式 | 行为 | 依赖 |
|---|---|---|
| online | STATE 预测与转录/代谢分析，不读取匹配观测 | MySQL、worker、GPU、模型及对照 |
| validation | 在线链路加匹配扰动观测比较 | 在线依赖及包含该扰动的观测 |
| precomputed | 校验并复制现有预计算包，不调用模型 | MySQL、匹配目录中的摘要及清单 |

运行查询返回请求、状态、`stage_progress`、时间、warnings 和错误信息。状态枚举为 queued、state_running、adapting、metabolic_running、validating、completed、failed。进度来自后端节点；completed/failed 为终态。

## 接口列表

路径均相对 `/api/v1`。

| 方法 | 路径 | 内容与注意事项 |
|---|---|---|
| GET | `/health` | 服务及数据库状态，需读取响应字段 |
| GET | `/ready` | 数据库与 worker/GPU 开关；未全部满足返回 503 |
| GET | `/catalog/contexts` | 三种模式就绪状态、模型 ID 及原因 |
| GET | `/catalog/perturbations?cell_line=K562` | `{cell_line, items}`；模型登记扰动，不是预计算目录列表 |
| POST | `/runs` | 创建运行，成功返回 202 |
| GET | `/runs/{run_id}` | 请求、运行阶段与错误 |
| GET | `/runs/{run_id}/summary` | 汇总；未完成时可返回状态和空结果 |
| GET | `/runs/{run_id}/projection` | `{method, seed, points}`；点含 x/y/source/cell_index，默认最多 12000 点 |
| GET | `/runs/{run_id}/genes?limit=2000` | CSV 行转 JSON；gene/control/predicted/predicted_delta 与可选观测列，数值可能是字符串 |
| GET | `/runs/{run_id}/metabolic-tasks?limit=1000` | 摘要任务条目；真实分析当前只摘要变化最大的 20 项 |
| GET | `/runs/{run_id}/reactions?limit=1000` | 真实矩阵按来源取均值，再按绝对差异排序；其他 CSV 格式可能有不同列 |
| GET | `/runs/{run_id}/report` | HTML 下载；包含基因、任务及警告 |

三类表格返回 `{items, limit, truncated}`，limit 均允许 1–10000。truncated=false 只表示接口未因 limit 截断，不证明摘要包含全部任务。真实基因表保持输出顺序，接口不会按效应大小排序。

precomputed_ready 仅检查细胞系演示目录存在，validation_ready 检查资产整体就绪；分别不保证任意扰动有演示包或匹配观测。

## 摘要语义

摘要包含运行编号、状态、背景、扰动、coverage、top_genes、metabolic_tasks、warnings 和 error_code。

| 字段 | 含义 |
|---|---|
| `predicted_delta` | 预测减对照的表达或任务分数差异 |
| `observed_delta` | 匹配观测减对照；无观测为 null |
| `coverage` | 可用基因比例，不是准确率或置信概率 |
| `evidence_level` | 当前覆盖规则分类 supported/exploratory/insufficient |
| `determinant_genes` | 预留决定基因列表；真实任务摘要当前为空 |

总体 coverage 可为 null，代谢降级时应展示 warnings 与转录结果。投影当前是固定种子的随机二维投影，应显示返回 method，不能标注 UMAP 或 t-SNE。

## 错误与缺失

业务错误通常在 detail 对象中含 code 和可选 message；参数校验的 detail 是字段错误数组，客户端需兼容两种结构。

| HTTP 状态 | 常见情形 |
|---|---|
| 404 | RUN_NOT_FOUND、PRECOMPUTED_NOT_FOUND、ARTIFACT_NOT_FOUND |
| 409 | RUN_NOT_COMPLETED，产物暂不可读 |
| 422 | 请求校验、UNSUPPORTED_PERTURBATION 或注册表错误 |
| 503 | WORKER_UNAVAILABLE、GPU_UNAVAILABLE 或资产不可用 |
| 500 | INVALID_PRECOMPUTED_RESULT、INVALID_ARTIFACT 等结果异常 |

单个产物缺失只应影响对应视图。当前没有 HTTP 接口读取 manifest、完整代谢覆盖表、validation_metrics、运行列表或取消任务。

更新契约时运行 `uv run --no-sync python scripts/export_openapi.py` 并核对前端类型。`frontend/src/types/run.ts` 是部分镜像，不是完整契约。

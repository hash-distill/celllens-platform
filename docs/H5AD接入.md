# H5AD 接入 API

浏览器和脚本使用同一条流程：上传文件 → 查看元数据 → 声明分组和表达尺度 → 建立数据版本 → 提交分析。文件路径只存在于服务内部，客户端使用不透明的 `upload_id` 和 `import_id`。

本地模式仅监听回环地址；私有部署使用工作区登录 Cookie 或 `Authorization: Bearer <工作区令牌>`。当前权限单位为整个工作区，不是多租户个人空间。公开展示模式禁止上传和自有数据分析。

## 上传与预检

`GET /api/v1/research/uploads/capabilities` 返回上传是否启用及大小、维度限制。

```sh
curl --fail-with-body \
  -X POST 'http://127.0.0.1:8028/api/v1/research/uploads?filename=experiment.h5ad' \
  -H 'Content-Type: application/octet-stream' \
  --data-binary @experiment.h5ad
```

私有部署在请求中增加 `Authorization` 头；不要把真实令牌写入仓库。上传使用原始二进制请求体，不使用 multipart 表单。Windows PowerShell 中可显式调用 `curl.exe`，将上述命令改为一行。

成功返回 HTTP 201，包含 `upload_id`、文件名、字节数、SHA-256、细胞数、基因数、`obs_columns`、创建与过期时间。`obs_columns` 中包含字段类型、缺失数、唯一标签数、有限数量的标签及人数；`truncated` 明确标识枚举不完整。元数据不能用来自动推断表达尺度。

- `GET /api/v1/research/uploads/{upload_id}`：重新读取预检元数据。
- `DELETE /api/v1/research/uploads/{upload_id}`：删除上传暂存，返回 204；不删除已冻结的数据版本或分析。

默认单文件上限 256 MiB、输入最多 20,000 个细胞、60,000 个基因、12,000,000 个矩阵元素；这是资源约束，不是对所有 H5AD 的兼容承诺。传输按块写入，实际字节数仍会校验，不能只靠 Content-Length 绕过限制。非 HDF5 文件、外部存储链接、重复身份及不符合尺寸限制的文件会拒绝。

## 建立版本

向 `POST /api/v1/research/uploads/{upload_id}/imports` 发送 JSON，例如：

```json
{
  "expression_scale": "log1p_cp10k",
  "full_library": false,
  "group_key": "condition",
  "control_label": "control",
  "target_label": "treated",
  "cell_line": "K562",
  "perturbation": "ALDOA",
  "max_cells": 256,
  "seed": 42
}
```

示例中的字段和标签必须替换为真实文件的内容，不是可直接套用的数据声明。原始计数使用 `raw_counts`，须声明 `full_library=true`，或通过 `total_counts_key` 指向完整文库计数列。支持可选 `batch_key`，不能选择含缺失值的批次列。处理标签与对照必须不同。

返回 HTTP 201 和冻结版本的 `import_id`、来源指纹、实际组别人数、采样人数、归一化规则和限制。上传校验不等于分析完成；版本建立也不会自动运行模型。

## 提交与结果

`POST /api/v1/research/imports/{import_id}/analyses` 提交实测任务，返回 HTTP 202 和分析 ID。使用 `GET /api/v1/measured/analyses/{id}` 查询进度；完成后可在结果页浏览图表、来源及导出。

上传与版本建立失败可修正文件或字段后重试。如果提交分析时发生网络中断，应先查询实验记录，避免重复提交。公开模式与未授权私有请求被拒绝；不可变版本哈希不符时拒绝复用。

## 部署配置

默认本地及认证私有工作区启用浏览器上传，不依赖旧 `CONTROLLED_IMPORT_ROOT` 设置。

| 环境变量 | 默认值 | 含义 |
|---|---:|---|
| `CELLLENS_H5AD_UPLOAD_ENABLED` | `true` | 开放上传入口；公开模式始终关闭 |
| `CELLLENS_H5AD_UPLOAD_MAX_BYTES` | `268435456` | 单文件上限 |
| `CELLLENS_H5AD_UPLOAD_MAX_TOTAL_BYTES` | `1073741824` | 上传暂存总量上限 |
| `CELLLENS_H5AD_UPLOAD_TTL_SECONDS` | `86400` | 上传暂存保留时长 |
| `CELLLENS_H5AD_UPLOAD_TIMEOUT_SECONDS` | `300` | 上传传输超时 |

暂存过期在后续上传、查询或建立版本时清理，不依赖后台定时任务；已冻结的数据版本不受暂存过期影响。

服务账户需要写入项目 `data/uploads` 和 `data/imports`，普通用户不需要知道这些目录。若部署反向代理，需让请求体上限与超时容纳上述配置；代理设置不替代应用内限额。原始文件、上传暂存及版本均不进入源码仓库。旧受控目录接口保留兼容已有管理员脚本，浏览器默认使用上传流程。

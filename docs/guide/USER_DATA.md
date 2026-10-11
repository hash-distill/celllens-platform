# 用户数据与下游分析

个人数据工作流从实测表达矩阵开始，不要求用户提供 STATE 模型权重。上传的数据可以超出现有 K562、RPE1、Jurkat、HepG2 预设数据；人类代谢分析仍需满足基因身份、表达尺度与冻结数据库的适用条件。

## 启用服务

安装 `model`、`report` 依赖并执行 `alembic upgrade head`。新增 `users`、`user_sessions`、`user_datasets`、`user_analyses` 四张表，既有五张运行表继续保留。

```bash
uv sync --locked --group dev --extra model --extra report
uv run --no-sync alembic upgrade head
uv run --no-sync python scripts/manage_users.py create admin --role admin
```

管理员在终端输入自己的密码，至少 12 位；系统没有默认管理员密码，也不开放公众注册。登录后在“我的数据”创建普通用户。密码忘记或账号被登录失败锁定时，管理员可在服务器执行：

```bash
uv run --no-sync python scripts/manage_users.py reset-password alice
```

密码重置会撤销该账号全部会话。连续五次错误登录锁定 15 分钟；默认会话有效期 12 小时，退出立即撤销当前会话。用户账号为应用账号，与 MySQL 账户不同。

设置 `.env` 的 `CELLLENS_DATA_WORKER_ENABLED=true` 并重启。只运行用户表达/代谢分析时，GPU 与 STATE worker 可以关闭。HTTPS 部署设 `CELLLENS_SESSION_COOKIE_SECURE=true`，网页与 `/api` 通过同一来源访问；开发环境通过 Vite 同源代理访问。

`/api/v1/ready` 仍检查预设 STATE 服务的数据库、GPU 与 worker，因此仅启用 CPU 服务时返回 503。个人数据功能状态见 `/api/v1/data-capabilities`，数据库连通性见 `/api/v1/health`；创建分析时还会检查 CPU 开关、依赖和冻结数据库。

## 上传要求

在 `/datasets` 页面上传 `.h5ad`。一次上传创建独立不可变版本，不覆盖同名数据；保存 SHA-256、参数、来源说明与细胞/基因数。

| 字段 | 内容 |
|---|---|
| 基因 | `var_names` 或 `var.gene_symbol`，使用明确的人类基因符号；存在 `gene_symbol` 时优先使用它 |
| 可选身份 | `var.hgnc_id`；代谢分析复用冻结 HGNC 映射，冲突或歧义不自动合并 |
| 细胞 | 唯一且非空的 `obs_names` |
| 表达矩阵 | `X`，或填写 `layers` 中的具体名称；不使用 `obsm` 嵌入代替表达 |
| 分组 | `obs` 中无缺失且有 2–40 个不同取值的列，例如 condition、sample、cell_type |
| 背景 | 自行填写细胞背景或实验来源，不用于自动证明模型适用性 |

表达值必须有限、非负且尺度明确。原始计数必须为整数。

- `raw_counts` + 完整文库：用户明确确认矩阵包含完整文库后，系统可根据每个细胞的矩阵总计数计算 CP10K；也可提供真实完整文库总计数列。
- `raw_counts` + 筛选面板：必须指定 `obs` 中筛选前的完整文库总计数列，不能把当前面板的行和当作完整文库。
- `cp10k`：用户确认已按完整文库归一化。
- `log1p_cp10k`：用户确认已为 log1p(CP10K)。系统检查其逆变换是否有限，不再按所选面板重新归一化。

不自动猜测表达尺度、不填补缺失基因、不合并重复基因。Ensembl ID 可以用于一般表达探索；代谢分析应另提供 HGNC 符号或明确 HGNC 身份，系统没有通用 Ensembl 转换器。只有两个或以上细胞、两个或以上基因的数据可用于本工作流。

默认限制：单文件 256 MiB、个人源文件累计 2 GiB、10,000 个细胞、60,000 个基因、单个数组或稀疏非零数组 2,000 万个值、HDF5 数组解码预检 512 MiB。数值限制可以通过 `.env.example` 中对应配置调整。上传请求要求 `Content-Length`，同时检查实际读取量；拒绝外部/软 HDF5 链接、循环硬链接与引用对象。网关应配置对应请求体上限。解码预检是数组与元数据大小估计，并非操作系统内存硬限制；该版本仍面向受控科研用户。

## 分析任务

### 表达探索

保存逐细胞检出基因数、CP10K 总和、可用原始文库计数。对完整输入基因计算分组平均 log1p(CP10K) 和检出率；指定参考组时导出“本组平均 − 参考组平均”。这些是描述性统计，没有 p 值、FDR 或因果效应估计；选择细胞而缺乏生物学重复不能替代正式差异分析。

PCA 选择全部输入细胞中方差最高的最多 1,000 个基因，均匀抽取最多 2,000 个细胞进行展示，保存原始细胞标识、种子和解释方差。统计与代谢分析仍使用全部输入细胞；只对可视化进行抽样。常量表达返回零坐标和零解释方差，不编造结构。

### 代谢分析

包含表达探索，并运行 scCellFie 0.6.2。使用完整上传基因面板、冻结人类数据库与固定阈值，保存逐细胞任务/反应评分、分组均值和参考组差值。无需把输入裁成 STATE 的 2,000 个基因。上游会按可用基因筛选可评分任务与反应；页面区分本次返回的评分数和数据库总数，未返回评分的任务不能当作零分。官方完整性报告包含全部任务、反应、覆盖和缺失基因；其数值描述本输入面板相对于数据库的可用范围，不代表准确率或实测通量。

基因符号适配只调整明确身份，不修改或填充表达。失败时记录原因，保留源文件；没有结果的任务不显示完成。CPU 队列持久化排队/运行状态，并以数据库命名锁串行执行；重启后锁持有者可重新执行未完成任务。每用户最多同时保留三个未完成任务。当前没有任务取消、执行超时和集群资源调度；管理员应按机器资源设置输入上限。

### STATE 兼容性

上传后显示背景是否在注册表中，以及登记基因面板匹配情况和缺少的模型元数据列。当前兼容性检查不意味着已完成模型泛化验证，也不开放自有数据直接驱动 STATE。预设实验仍使用管理员登记的对照数据、模型与许可条件。

## 数据管理与权限

原始 H5AD 位于 `data/user_uploads/`，结果位于 `data/derived/user_analyses/`，均被 Git 忽略且不通过静态路由公开。数据集、任务、报告和下载接口检查会话及所有者；知道随机 ID 不能获得其他用户的数据。管理员可以创建账号，但不默认读取其他用户文件。

归档后不能新建分析，原始版本和既有结果继续保留以供复查。当前未提供用户删除、自动过期清理和配额回收；管理员需按科研数据保留规则备份和维护磁盘。结果文件每次下载校验 SHA-256，记录报告对应的源文件哈希。

现有预设实验和 `/runs` 历史结果仍是共享入口；新增账号权限只覆盖个人数据域，不能把本次功能描述为整站已完成多租户权限改造。

## API

基础路径 `/api/v1`，完整字段与请求示例见部署后的 `/docs`。

| 接口 | 用途 |
|---|---|
| `POST /auth/login` | 用户名与密码登录，返回用户和 CSRF 令牌，设置 HttpOnly 会话 Cookie |
| `GET /auth/me` | 当前用户与 CSRF 令牌 |
| `POST /auth/logout` | 撤销会话 |
| `POST /auth/users` | 管理员创建账号 |
| `GET /data-capabilities` | 科学依赖、CPU 服务状态、格式及资源上限 |
| `POST /datasets` | multipart：`file` 为 H5AD、`metadata` 为上传元数据 JSON 字符串 |
| `GET /datasets` | 分页个人数据集，`limit` / `offset` |
| `GET /datasets/{id}` | 校验信息与来源 |
| `GET /datasets/{id}/file` | 下载原始 H5AD |
| `POST /datasets/{id}/archive` | 归档数据集 |
| `POST /analyses` | 选择 dataset_id、kind（explore/metabolism）、group_key、reference_group、seed |
| `GET /analyses` | 分页个人任务 |
| `GET /analyses/{id}` | 状态、错误、结果文件清单与哈希 |
| `GET /analyses/{id}/report` | 完整分析报告 JSON |
| `GET /analyses/{id}/files/{filename}` | 下载清单中的结果 CSV/JSON |

所有个人数据接口需要会话 Cookie；写操作还需 `X-CSRF-Token`。服务不会接受客户端指定服务器文件路径。

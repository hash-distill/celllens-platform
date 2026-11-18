# CPU 部署

本版 API 与数据库轮询 worker 分开启动。CPU 分析不需要 NVIDIA GPU；预测 worker 只有在 CUDA、STATE 命令、已启用预测配置均通过探针后才启动。权重、输入与支持目标仍按 registry 校验。这里提供部署配置；实际部署与科学运行的验证结果应另行记录，不能把配置文件等同于已部署。

## 安装与数据

使用 Python 3.11/3.12、Node.js 和 uv，在新安装目录执行：

```sh
uv sync --frozen --no-dev --extra analysis --extra report
npm --prefix frontend ci
npm --prefix frontend run build
```

Python 使用仓库 `uv.lock`，前端使用 `package-lock.json`；CPU 安装不选 `model` extra。参考 [uv 可选依赖](https://docs.astral.sh/uv/concepts/projects/sync/)。模型大文件与真实数据不包含在前端包中。复制所需 registry、知识库与冻结案例时保留原相对路径和哈希；空安装只能显示数据未准备状态，不生成示例替代真实结果。

## Linux 私有工作空间

部署目录约定 `/srv/celllens`，独立服务账户 `celllens` 对 `data` 有读写权限，代码和环境只读。创建 `data/runtime`。将 `ops/cpu.env.example` 复制为仅服务账户可读的 `/etc/celllens/celllens.env`，在本机设置随机工作空间令牌；仓库不保存令牌。SQLite 配置适合单机 CPU 并发 1；MySQL 部署可替换连接地址，保持 API 与 worker 使用同一数据库和资产目录。

把三个 `ops/celllens-*.service` 安装到 systemd 后：

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now celllens-api celllens-worker
sudo systemctl status celllens-api celllens-worker
```

迁移服务先执行 `alembic upgrade head`，正式部署不要开启 `create_database_schema`。升级代码后先备份数据库与不可变结果；停止 API/worker，再重启迁移服务，随后启动 API/worker。这里没有自动备份或多主机共享磁盘方案。

API 绑定 `127.0.0.1:8000`；公网入口通过支持 HTTPS 的反向代理转发。代理需保留外部 Host，并设置 HTTPS scheme，例如由 uvicorn 的受信代理配置接收；本示例默认 `--no-proxy-headers`，代理时应按实际受信代理地址显式调整。私有 Cookie 默认为 Secure，HTTP 本地调试才临时设 `CELLLENS_SESSION_SECURE_COOKIE=false`。可用 `Authorization: Bearer <令牌>` 或页面登录获取 HttpOnly 会话。仅为单工作空间身份边界，没有用户隔离、配额或多人权限系统。

## Windows 本地

在独立副本执行 `powershell -File ops/run-local.ps1 -Install`；已安装时省略 `-Install`。脚本要求前端构建存在、端口空闲，使用本副本的 `data/runtime/celllens.db` 执行迁移，再隐藏启动 API 和 CPU worker。只有 API 端口确由本次进程持有、数据库可用且 CPU worker 心跳就绪后才报告成功；失败会回收本次进程并保留日志。可用 `-Port 8100` 或 `-StartupTimeoutSeconds 120` 调整端口和等待上限。

需要模型推演时执行 `powershell -File ops/run-local.ps1 -Gpu -Port 8028`。`-Gpu` 额外启用并启动独立 GPU worker，要求真实 CUDA/STATE 探针和预测 worker 心跳通过后才报告成功；不能只靠开关宣称 GPU 可用。全新专用环境可加 `-Install -Gpu`，安装时额外选择锁定的 `model` 依赖。默认不带 `-Gpu` 时仍只启动 CPU。GPU 日志位于 `data/runtime/gpu-worker.log` 和 `gpu-worker.err`；停止脚本会一并核对并停止可选 GPU 进程。

API 仅绑定回环地址，`local` 模式拒绝非回环客户端；不要把此模式接入公网反向代理。停止命令为 `powershell -File ops/stop-local.ps1`，可加 `-WhatIf` 预览。停止脚本同时核对工作区、PID、创建时间和 Python 模块命令，只结束匹配服务及其子进程；发现 PID 已复用则拒绝操作。数据库、结果与日志保留。重复启动时若记录中的进程仍在运行，启动脚本会拒绝另起实例。

若 `.venv` 是链接到其他项目的共享环境，`-Install` 会拒绝修改它，避免同步 CPU 依赖时移除原环境的模型包。可使用已安装环境直接启动；新机器部署应创建本副本专用环境。

## 启用自有数据

本地及认证私有工作区默认提供浏览器／API 上传。用户在页面选择文件，服务端按块接收并读取分组字段，确认尺度后建立独立数据版本。服务账户需要对 `data/uploads`、`data/imports`、`data/derived` 和数据库有写权限；不需要让用户操作服务器目录。主要配置为：

```text
CELLLENS_H5AD_UPLOAD_ENABLED=true
CELLLENS_H5AD_UPLOAD_MAX_BYTES=268435456
CELLLENS_H5AD_UPLOAD_MAX_TOTAL_BYTES=1073741824
CELLLENS_H5AD_UPLOAD_TTL_SECONDS=86400
CELLLENS_H5AD_UPLOAD_TIMEOUT_SECONDS=300
```

上传暂存默认最多 1 GiB，保留 24 小时；已冻结的数据版本独立保存。反向代理的请求体上限和传输超时需与这些配置配套，否则请求可能在到达应用之前被拒绝。公开模式始终禁止上传，开启配置不会扩大公开访问。接口示例见 [H5AD 接入](H5AD接入.md)。

旧 `CELLLENS_CONTROLLED_IMPORT_ENABLED` 和 `CELLLENS_CONTROLLED_IMPORT_ROOT` 仅保留给已有管理员脚本兼容，默认关闭；它们不控制新的浏览器上传入口。

## 公共只读案例

独立公开部署设置：

```text
CELLLENS_DEPLOYMENT_MODE=public
CELLLENS_WORKER_MODE=disabled
CELLLENS_PUBLIC_RESULT_IDS=允许公开的结果ID,另一个结果ID
```

公开部署不启动 worker，不开放写入、导入、发现笔记、外部解读或重建图形的 GET。冻结读路由还要求结果已完成；未登记的 ID 返回拒绝。研究包可导出白名单结果的数值与来源，始终剔除私人发现、注释和本机输入路径。列表只包含白名单案例；门户数据图谱也限定这些案例对应的公开来源快照，不读取私人 H5AD 来探测资源。默认白名单为空，先核对案例来源与披露范围后再填写。

## 运行、取消与恢复

CPU 进程：`python -m backend.app.worker --kind cpu`；可选预测进程：`python -m backend.app.worker --kind gpu`。部署默认 `worker_mode=external`，API 只入队，重启 API 不改写活跃任务。`embedded` 仅用于兼容测试/开发，不能同时启动独立 worker；`disabled` 拒绝新建实测任务。

worker 对任务执行条件更新后获取租约，持续续租，并记录 attempt。默认同一资产目录 CPU/GPU 各并发 1，OS 锁在崩溃时自动释放。超过租约的 attempt 标记 abandoned，新 attempt 重放；暂存目录按 attempt 分离。原子发布后数据库提交前崩溃时，恢复流程校验请求和文件哈希后接纳既有目录，绝不覆盖完成产物。异常暂存目录保留供排查，没有自动清理磁盘策略。

实测取消写入数据库，worker 结束子进程并确认 cancelled。预测取消保留原枚举 `failed`，通过 `RUN_CANCELLED` 和 attempt `cancelled` 区分。CPU 子进程超时为 1 小时，预测进程上限 2 小时；终止后未完成的任务由租约恢复。不要将失败/取消历史人工改为完成。

`GET /api/v1/ready` 的 HTTP 200 表示数据库和结果浏览入口可用。`capabilities.cpu_analysis` 与 `capabilities.prediction` 来自未过期的 worker 心跳与依赖/设备探针，不由 GPU 配置开关直接决定，也不是每个数据组合均已可算的承诺。`system-status` 属于私有接口，可查看真实探针与部署模式。

建议验收：真实 CPU 小样本完成、API 重启不中断任务、worker 强制退出后租约恢复、取消后不发布、未授权请求被拒绝、公开计算 GET 被拒绝。测试使用独立临时数据库，不能指向历史生产库。

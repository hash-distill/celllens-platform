# 后端修复与 MySQL 迁移报告

## 已修复

- 移除 SQLite 运行存储，改为 SQLAlchemy 2.0 + MySQL + Alembic；
- 创建 `runs`、`run_attempts`、`run_events`、`run_artifacts`、`run_cache` 五张业务表；
- 阻止 worker 关闭时创建永久 queued 的在线任务；
- 区分在线、验证、预计算三种模式，预计算模式不依赖 GPU/模型资产；
- 启动时恢复 queued 和租约过期任务，记录 attempt、heartbeat 和事件；
- 增加合法状态转换、进度单调和终态不可逆约束；
- 每次 attempt 使用独立临时目录并原子发布，避免旧 `.partial` 阻塞；
- Catalog 按文件存在性和 SHA-256 计算就绪状态；
- 阻止注册表路径逃出项目根目录；
- STATE 输出重新读取 H5AD，检查有限值、维度、扰动标签、基因顺序，并写入 provenance；
- 接入真实 control/predicted/observed 基因对齐、表达差异、scCellFie 任务分数和验证指标；
- scCellFie 使用一份带哈希的冻结数据库和同一阈值列，关闭跨来源 KNN 平滑；
- 证据指标统一过滤非有限任务并报告有效/排除数量；
- MySQL advisory lock 保证多个 API 进程不能同时占用一块 A6000；
- 健康检查现在包含数据库连通性。

## 当前验证

- `uv run pytest -q`：22 项测试通过；
- `uv run ruff check backend scripts`：通过；
- `uv run basedpyright`：0 项错误、0 项警告；
- `uv run alembic upgrade head`：已在本机 MySQL 成功执行；
- `uv run alembic check`：无遗漏迁移；
- `uv run python scripts/check_mysql.py`：五张业务表、Alembic 表及完整持久化往返通过；
- 纵向模拟测试覆盖 STATE 产物 → 科学汇总 → manifest → 原子发布 → 数据库产物登记。

## 尚需团队提供的外部资产

代码链路已经闭合，但当前仓库没有真实 checkpoint、H5AD 和冻结 scCellFie 数据库，因此不能在本机声称完成真实生物学推演。接入时必须：

1. 把 checkpoint、model gene list、control H5AD、observed H5AD 写入注册表并填入 SHA-256；
2. 将 scCellFie 官方 human 数据库六个文件放入 `data/registry/sccellfie/human/`；
3. 在该目录的 `manifest.json` 填写每个文件 SHA-256、版本并设 `enabled=true`；
4. 安装 `model` 依赖，在开发扰动上跑通后再开启最终留出集；
5. 运行 `scripts/audit_registry.py` 和一次 K562 端到端验收，并保存 manifest。

scCellFie 的阈值来自冻结数据库的 `Thresholds.csv` 指定列，而不是针对每次输入重新拟合。本实现验证阈值列存在，并把数据库文件哈希作为可复现边界。

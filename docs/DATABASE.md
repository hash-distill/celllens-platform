# CellLens MySQL 数据结构

运行元数据使用 MySQL，科学矩阵仍以 H5AD/CSV 文件保存。这样既能事务化管理任务，又避免在关系数据库中存储体积很大的单细胞矩阵。

| 表 | 作用 | 关键约束 |
|---|---|---|
| `runs` | 请求、状态、进度、错误和时间戳 | `run_id` 主键；状态/更新时间联合索引 |
| `run_attempts` | 每次执行的 worker、租约、心跳与结果 | `(run_id, attempt_no)` 唯一；级联删除 |
| `run_events` | 状态转换审计日志 | 外键指向 `runs`；按 `run_id` 索引 |
| `run_artifacts` | 产物相对路径、SHA-256、大小和 MIME | `(run_id, kind)` 唯一；级联删除 |
| `run_cache` | 确定性请求缓存到已完成运行的映射 | `cache_key` 主键；`run_id` 唯一 |
| `alembic_version` | 当前数据库迁移版本 | Alembic 管理 |

建表和升级统一由 Alembic 执行：

```powershell
uv run alembic upgrade head
uv run alembic check
uv run python scripts/check_mysql.py
```

首次迁移文件为 `backend/app/db/migrations/versions/0001_runtime_tables.py`。应用生产环境保持 `CELLLENS_CREATE_DATABASE_SCHEMA=false`，不要让 Web 进程隐式建表。

大型产物发布流程为：attempt 独立 `.partial` 目录写入 → 生成 manifest 和 SHA-256 → 原子改名为最终目录 → 在 `run_artifacts` 登记。数据库记录可据此验证文件是否被替换或损坏。

MySQL 的 `GET_LOCK('celllens:a6000', ...)` 用作跨进程 A6000 互斥锁；单个 run 还通过 `run_attempts.lease_expires_at` 防止多个 worker 重复执行。进程重启会恢复 queued 和租约过期的 active run。

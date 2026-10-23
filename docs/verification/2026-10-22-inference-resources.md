# 按背景准备推理资源与 README 验收

日期：2026-10-22。当前工作区未提交；保留原有未提交修改，上层目录 README 未改动。

## 交付

- 连接服务页 `/status` 提供 K562、RPE1、Jurkat、HepG2 四个资源卡片；用户确认上游许可后主动下载所选背景。
- 六个模型文件按固定版本、大小、SHA-256 校验；已有文件复用，范围续传、取消、重试、任务状态恢复与进程间安装锁。
- 缺少对照时范围读取固定官方图谱，按背景抽取最多 1024 个真实 non-targeting 细胞；登记新 ID，保留原对照及历史身份。
- 官方 checkpoint 的配套配置与映射文件也加入工作台可用性及执行检查。
- 本机 MySQL 启动路径可配置；Windows 端口预检加入 Bound / Established 本地占用，不终止占用者。
- 主 README 重写为项目介绍、功能预览、快速开始、按需下载、开发配置、架构、目录、FAQ 和许可；同步部署、接口、资源、使用说明及真实截图。

## 验证证据

本地原始记录位于 `reports/resources-2026-10-22/`（不随 Git 分发）。

| 验证 | 结果与范围 |
|---|---|
| 后端完整回归 | 最终 330 passed / 6 warnings，182.66 秒，XML 无失败或错误 |
| 新增资源与端口回归 | 20 项在最终完整回归中通过，含真实子进程取消检查。覆盖范围/哈希/大小、来源与路径拒绝、许可与并发、取消、恢复、旧 ID、配套文件和 Bound 端口 |
| Ruff | `backend/app`、`scripts` 及本次两个测试文件检查通过 |
| BasedPyright | 0 errors / 0 warnings / 0 notes |
| 前端 | `typecheck` 与生产构建通过，748 modules；现有 Three.js 关联块约 546 kB，仍有构建体积提示 |
| 浏览器真实读取 | 8001 主服务返回四个背景资源均已核验；打开页面无下载 POST |
| 浏览器协议夹具 | 仅浏览器拦截 RPE1 资源端点，验证许可、42% 进度、只请求 RPE1、取消/重试、完成后目录刷新及工作台选中 RPE1；不用于证明真实大权重下载 |
| 主题与宽度 | light / dark × 1280 / 1440 / 1920，6 组，无页面异常与横向溢出；资源底部说明另行确认可见 |
| 官方小文件实测 | 实际下载固定版本 RPE1 `config.yaml`，2752 bytes，SHA-256 `d5fb5229f68cabe0e76ff9c3c50598b8898380149e8fdaa85f9d0e1a839ddae7` 匹配 |
| 真实对照小样本 | 实际从固定远程图谱提取 RPE1 8 个细胞、6546 个源基因，核验背景、non-targeting 标签及有序 HVG 槽位；仅保存 reports，不登记为在线输入 |
| 原有资产 | 当前 24 个模型文件均匹配固定官方哈希；原 datasets.json 与修改前快照一致 |
| 实际 API 操作 | 主服务 K562 已有资源复用任务返回 202，随后 completed；未重新下载大权重或替换对照 |
| 文档与契约 | 导出 OpenAPI 共 33 paths，含 3 个资源路由；本次 README 与部署/资源/接口/索引本地链接核对 |

后端完整运行有依赖的弃用/文档警告，未据此宣称消除所有上游警告。新增子进程测试使用真实 OS 进程和管道，替换的是工作负载，使测试无需读取图谱即可验证取消后等待并回收子进程；不将其称为图谱提取中途崩溃实测。

## 启动实测

本次使用 README 中的命令：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_system.ps1 -ApiPort 8001
```

输出依次为 MySQL connection OK、Alembic 迁移、schema / durable round trip OK、复用已验证前端构建、Uvicorn 启动。主服务 `127.0.0.1:8001`，当前 PID 32072；本机项目 MySQL 监听 3307，PID 5900。临时测试端口 8013 / 8014 已停止。PID 是验收时快照，后续重启会变化。

`/health` 返回 200；`/ready` 的数据库及 worker/GPU 开关为 true；`/system-status` 显示 online worker 正在运行、pending 为 0。`ready` 与背景目录不检测全部驱动和 Python 科学依赖，不据此声称完成一次新推理验收。

## 范围与保留

本次没有重复下载四套约 467 MiB 模型，没有执行新的完整 1024 细胞冷安装，也没有重新完成四背景 GPU 推理。已经验证真实小文件链路、真实范围提取、已有资源复用、受控恢复与浏览器交互；新环境的完整冷安装仍需在对应网络和 GPU 条件下验收。

未改变原模型或原对照文件，未把提取对照视为独立生物学验证，未安装/更换驱动，未提交或推送。快照目录为 `C:\Users\zhs14\AppData\Local\Temp\celllens-resources-before-20261022-121626`。下载位置是后端机器，模型与数据分别遵循上游许可。

README 排版与信息组织参考 [RuoYi-FastAPI](https://github.com/insistence/RuoYi-FastAPI) 与 [vue-fastapi-admin](https://github.com/baizunxian/vue-fastapi-admin)；依赖及命令按本项目实际实现编写，未移植其权限或任务架构。

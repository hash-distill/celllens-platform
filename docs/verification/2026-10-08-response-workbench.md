# 2026-10-08 扰动响应工作台验收记录

**更正：第 1–10 节为早先的工程检查记录。随后发现 STATE 输出中的模拟对照被混入预测群体，原运行 `run_79bd3cd67f6c4aad` 的表达与代谢汇总因此不能作为修复后的结果依据。第 11 节记录筛选修复和新运行；旧产物保留。**

记录对象：`feat/perturbation-response-workbench` 分支上的表达响应、代谢功能、冻结任务追溯与三维功能网络改动。
本文件只记录可复核的观察结果，不证明生物学准确性，也不替代正式泛化评价。

## 1. 核验方式与边界

- 核验时间：2026-10-08，本机 Windows。
- 核验方式是**对运行中的系统做在线核验**，并在解除文件沙箱限制后补跑完整测试套件与前端构建：后端在 `127.0.0.1:8000` 提供同源页面与 API，前端构建产物由后端直接托管。
- 首次核验时受限沙箱阻止了 `pytest` 与 `npm run build`（见第 6 节）；解除限制后两者均已实际执行并通过，第 5 节记录最终结果。

## 2. 验收运行

| 项目 | 值 |
|---|---|
| run_id | `run_79bd3cd67f6c4aad` |
| 请求 | `cell_line=K562`，`perturbation=AAMP`，`mode=online`，`n_cells=64`，`seed=42` |
| 状态 | `completed`，`stage_progress=100` |
| 时间 | 创建 2026-10-08T01:25:40，更新 2026-10-08T01:27:50 |
| 产物目录 | `data/derived/runs/run_79bd3cd67f6c4aad/` |

冻结追溯产物 `task_trace.json`：`size_bytes=507315`，`sha256=8850e674ef0f176bed9ee134e9394d51ab520fbc3dd6dbdc844201a51f4d3c11`（与 `manifest.json` 的 `outputs` 条目逐字一致）。

## 3. 接口核验

| 请求 | 结果 |
|---|---|
| `GET /api/v1/health` | `200 {"service":"celllens","status":"ok","database":"ok"}` |
| `GET /api/v1/runs/run_79bd3cd67f6c4aad` | `200`，`status=completed` |
| `GET /api/v1/runs/run_79bd3cd67f6c4aad/task-trace?task_id=Alanine synthesis` | `200`，任务含 `category=AMINO ACIDS METABOLISM`、`coverage=0.2857`、`evidence_level=insufficient`、`control=7.0266`、`predicted_delta=0.1101`；`total_reactions=13`，`reaction_limit=2` 时 `truncated=true`；反应 `ACONTm` 关联基因 `ACO1`，基因 `predicted_delta=0.0756`；`database_version=scCellFie-0.6.2-human-Recon2`，`relationship_kind=knowledge_association`，`determinant_status=unavailable` |
| `GET .../task-trace?task_id=Task_3521`（不存在的任务） | `404 {"code":"TASK_NOT_FOUND"}` |
| `GET /api/v1/runs/run_05708065c9414005/task-trace?...`（历史运行，无追溯产物） | `404 {"code":"TASK_TRACE_UNAVAILABLE","message":"This run has no frozen task trace; a new analysis is required."}` —— 未回退到当前数据库 |
| `GET /api/v1/runs/run_79bd3cd67f6c4aad/metabolic-tasks?limit=3` | `200`，条目带 `label/category/subcategory/control/predicted` |
| `GET /api/v1/runs/run_05708065c9414005/metabolic-tasks?limit=2` | `200`，`category/subcategory/control/predicted` 为 `null`，`predicted_delta` 仍可用 —— 缺追溯产物的历史运行优雅降级，未出现 500 |

任务追溯端点在该运行上返回 200，同时说明注册产物哈希与磁盘文件一致；若哈希或身份不符，`_load_task_trace` 会返回 500。这是该运行通过哈希校验的在线证据。

## 4. 浏览器检查记录

来自 `reports/frontend/response/browser-checks.json`：`run_id=run_79bd3cd67f6c4aad`，`url=http://127.0.0.1:8000`，`pageerrors=[]`，12 项检查全部有记录：

- 空态不含编造结果，也不预加载三维画布
- 手动打开运行编号后加载真实表达、代谢与冻结追溯
- 修改草稿不改变结果身份；选择基因会更新数值详情
- 切换任务会替换追溯内容；真实数据三维图渲染且响应旋转
- 覆盖等级筛选与刷新保持 URL 绑定的结果身份
- 390px 移动布局无横向溢出
- 四章演示使用所选结果；Esc 回到绑定的工作台
- 运行详情默认响应视图；辅助结构三维仍可用
- 历史运行不借用当前数据库关系
- 注入的基因接口失败被限制在局部，重试后恢复真实数据
- 注入的运行中状态使用服务端进度，并隐藏已完成数据
- 不存在的运行显示明确空态

对应截图保存在 `reports/frontend/response/`：`empty-desktop.png`、`live-desktop.png`、`live-mobile.png`、`live-trace-network.png`、`demo-metabolism.png`。其中工作台主视图另存一份供文档引用：[response-workbench.png](../screenshots/response-workbench.png)。

`reports/` 不纳入 Git；这些记录来自生成时的运行，重跑 `scripts/check_response_frontend.py` 会覆盖同名文件。

## 5. 检查与构建

| 检查 | 结果 |
|---|---|
| `uv run --no-sync pytest -q` | **48 passed**，2 条第三方弃用警告，12.57s，退出码 0 |
| `npm --prefix frontend run build` | 退出码 0；先 `vue-tsc --noEmit`（构建脚本首步）再 Vite 打包，9.30s 完成 |
| `uv run --no-sync ruff check backend scripts` | All checks passed |
| `node node_modules/vue-tsc/bin/vue-tsc.js --noEmit`（单独执行） | 退出码 0，无类型错误 |
| `git diff --check` | 无输出（行尾空格已清理） |
| 构建产物一致性 | 构建输出的主 bundle 文件名与页面引用的 `/assets/index-ZDNkbNZB.js` 一致，说明线上托管产物就是当前源码的构建结果 |

`backend/tests/test_task_trace.py` 共 9 个用例，覆盖知识关联与分数匹配、冻结分类与来源均值、历史缺失不回退、列表截断与任务缺失、篡改与跨运行产物、真实冻结映射、持久化与无数据库告警、数据库文件必须全部固定、未注册文件不可信。

构建仅报告一项体积提示（`OrbitControls` 569 kB 超过 500 kB 建议值），属于既有三维依赖，不影响构建成功。

`ruff format --check` 报告 3 个文件待格式化，经逐文件复核，三者均不属于本次改动范围，故未纳入。

## 6. 首次核验时的环境限制

首次核验运行在受限文件沙箱内，以下两项被环境拦截，随后在解除限制的同一台机器上重跑并通过（结果见第 5 节）：

1. `uv run --no-sync pytest -q`：曾以 34 个 `ERROR` 结束，全部是 `PermissionError [WinError 5]` 访问 pytest 临时目录（`pytest-of-zhs14`），属于沙箱 ACL 拦截而非断言失败。
2. `npm --prefix frontend run build`：曾以 `spawn EPERM` 结束于 esbuild 启动阶段（受限环境无法建立子进程管道）。

这两项记录保留在此，用于说明"受限沙箱中的失败不等于代码缺陷"：判断测试或构建是否通过，必须在能正常创建临时目录与子进程的环境中执行。解除限制后的重跑结果已构成"测试与构建通过"的正式结论。

## 7. 科学边界

- 表达差值不是统计显著性；反应与任务分数不是通量、ATP 产量或代谢物浓度。
- 任务—反应—基因连线来自冻结知识库，`relationship_kind=knowledge_association`；当前不提供评分决定基因归因（`determinant_status=unavailable`），关联不是因果贡献。
- 三维功能网络坐标是展示布局，不是细胞器位置或实测形态；图示数量上限为 8 个反应、每反应 10 个基因。
- 覆盖支持表示通过既有覆盖门槛，不是准确率或生物学验证；本次运行的多项任务 `evidence_level` 为 `insufficient`。
- 结果来自在线推演（模型推理），不是重新训练，也不构成实验验证。

## 8. 复现命令

```powershell
# 后端与同源页面（服务已在运行时跳过）
uv run --no-sync uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

# 冻结追溯接口
curl.exe "http://127.0.0.1:8000/api/v1/runs/run_79bd3cd67f6c4aad/task-trace?task_id=Alanine%20synthesis&reaction_limit=2&gene_limit=2"

# 浏览器检查（需要含冻结追溯的已完成运行）
python scripts/check_response_frontend.py --url http://127.0.0.1:8000 --run-id run_79bd3cd67f6c4aad

# 静态检查
uv run --no-sync ruff check backend scripts
node frontend/node_modules/vue-tsc/bin/vue-tsc.js --noEmit
```

## 9. 运行环境的已知行为

- 后端 `uvicorn` 以交互会话的子进程运行：**会话结束时该进程会被清理**，因此页面上线后可能发现 8000 端口不再响应。日志中没有异常，只会看到被截断的 200 访问记录——这不是服务崩溃。重新执行 `scripts/start_system.ps1`（或单独启动 uvicorn）即可恢复，数据库中的数据与产物不受影响。
- 本机 MySQL 由 `scripts/start_mysql.ps1` 独立拉起（监听 3307），**不随会话结束而停止**；`.env` 的 `CELLLENS_DATABASE_URL` 必须与这个端口一致（当前为 3307）。若用其它实例的 3306，会遇到 `Access denied for user 'celllens'@'localhost'`。
- Vite 开发服务器在文件被编辑器原子写入时，可能因残留的 `frontend/src/**/.*.tmpdir` 目录触发 `EBUSY` 并退出。启动开发服务器前应先删除这些临时目录。

## 10. 演示页自动播放

2026-10-08 调整：每章自动播放由 22 秒改为 **10 秒**，标题下方增加进度条与倒计时（`DemoView.vue` 的 `CHAPTER_MS`）。章节名同步为“实验问题 / 表达响应 / 代谢功能 / 证据与验证”。

生产构建实测：进度条与倒计时按真实时间线性推进（t+5s 时 50%、剩余 5 秒），四章分别在 t+10/20/30 秒切换，t+40 秒在末章自动停止；手动点击“下一章”会取消自动播放。`vue-tsc`、`npm run build`、48 个后端测试与 12 项浏览器检查均通过。

历史版本说明：当时自动播放全程仅约 40 秒，明显快于 90 秒演示讲稿的分章节奏。该章节播放器与讲稿已退休，不作为当前操作指南；原稿可从清理前提交 `9ba57c7` 恢复。

历史检查见 [2026-10-04 工程检查记录](2026-10-04/README.md)。

## 11. 单细胞状态展示与预测群体筛选修复

按 [STATE 论文图 1 与方法 4.3](https://www.biorxiv.org/content/10.1101/2025.06.26.661135v2.full) 核查后，将首页顺序改为单细胞状态分布、基因响应、代谢功能、证据追溯。并排与叠加图共用后端变换和初始轴范围；点不表示同一细胞的前后实测配对。当前图仍是随机投影，不是 SE 嵌入或形态预测。

实际缺陷：原 STATE 输出 `predicted.h5ad` 有 128 行，其中 `obs['gene']` 是 64 行 `AAMP` 和 64 行 `non-targeting`。推理日志明确写有 `Controls simulated: 64`、`Treated simulated: 64`。原分析将两组一起用作 predicted，导致下游汇总混入模拟对照。

修复后先按登记扰动列筛选目标标签，再生成基因、投影、代谢和冻结追溯。缺少登记列或目标标签时失败，不静默混用。原始 STATE 输出保留完整文件；投影的 `population_selection` 记录筛选协议和数量。代码哈希属于缓存身份，修改后同参数请求不会复用原错误结果。旧在线投影没有筛选记录时显示重跑提醒。

新运行 `run_4d0b3038ea8642af`：K562 / AAMP / online / 64 / seed 42，`cache_hit=false`，实际完成至 100%，无 warnings。核对产物：

| 项目 | 结果 |
|---|---|
| STATE 原始输出 | 128 行，保留来源 |
| 目标扰动筛选 | `status=matched`，输入 128、保留 AAMP 64、排除其他标签 64 |
| 投影显示来源 | 对照 3000、预测 64，无扰动后观测点 |
| 代谢评分矩阵来源 | 对照 3000、预测 64，与筛选协议一致 |
| task_trace.json SHA-256 | `d3f46b541a07bce1c059f75703a508529174dc4b8fcae7d128aa0a313d31d048`，与 manifest 一致 |
| projection.json SHA-256 | `d5c8a7fec2f300dd9464291d880d84f1e4c20903d05fd3c3295dce4a18464eed` |

新增 4 项预测群体测试：目标矩阵与 obsm 保留、登记列缺失拒绝、目标缺失拒绝、混入模拟对照不改变目标表达/代谢/冻结追溯。另补充回归：冻结追溯损坏时，独立有效的代谢评分仍可读，追溯端点继续严格拒绝不可信文件。

本轮后端完整检查为 **53 passed**，Ruff 全部通过，BasedPyright 为 0 errors/0 warnings。前端构建包含类型检查并通过。新运行的 **14 项浏览器检查通过，pageerrors=[]**，覆盖实际群体数量、并排/叠加、历史筛选警告、缺失投影局部降级、既有追溯/草稿/移动/演示检查；生产 smoke 也通过。最终报告与截图写入 `reports/frontend/response/`，文档截图据此更新。上述证明工程行为，不证明生物学预测准确性。PCA/SE 产物、单基因/任务的完整单细胞分布分析和正式高维分布评价尚未完成。

复核新界面：`http://127.0.0.1:8000/workbench?run=run_4d0b3038ea8642af`。

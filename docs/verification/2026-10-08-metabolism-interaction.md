# 代谢功能页筛选、点击与缺失结果修复

日期：2026-10-08。

## 复现与原因

在 `run_386e07d2897f4e0f` 的代谢页复现用户截图：Top 摘要 8 项，覆盖支持 8、探索性 0、证据不足 0。旧界面是三个复选框，勾选零记录分类不会改变图表。`DivergingBar` 发出 select 事件，但代谢页没有接收，导致点击只有 tooltip，没有任务详情。

旧预计算结果没有 `reaction_scores.csv` 或 `task_trace.json`，页面仍请求可选接口。实际记录到 `reactions` 的 404 ARTIFACT_NOT_FOUND，页面显示 HTTP 404；响应概览还请求了不存在的 task-trace。原始复现请求记录位于 `reports/frontend/metabolism-fix/baseline.json`。

## 修复行为

- 改为全部/覆盖支持/探索性/证据不足互斥单选，默认全部；显示当前筛选与匹配数量。
- 零记录分类立即显示包含分类名与结果范围的空态，Top 摘要不外推全量分类数量。搜索空态包含查询文字。
- 点击条形、纵轴任务标签或表格任务名更新选中任务和分数详情；任务 id 用作选择身份，不借 label 拼接口。
- 保留缺失数值：旧摘要没有对照/预测分数时显示未提供，不根据差值补算。
- 任务接口给出 `reactions_available` 与每项 `trace_available`，覆盖 Top/全量两条分支。缺失反应或追溯直接显示说明，不发预期会失败的请求。
- 冻结追溯损坏时 `trace_available=null`，保留真实错误路径；不把哈希错误隐藏成缺失，不借当前数据库补造旧关联。

## 验证

- 修复前新增的两个后端可用性测试与浏览器单选检查失败，确认覆盖原缺陷。
- 后端完整测试：71 passed；包含缺失、匹配、任务不在追溯内、Top 摘要和损坏追溯的区别。
- 前端构建（含类型检查）通过；Ruff 通过，BasedPyright 0 errors/0 warnings。
- 新浏览器脚本检查单选、空分类、搜索、表格点击、实际画布条形点击、真实冻结追溯、历史缺失提示、响应概览以及 390px 布局。正常操作记录 `pageerrors=[]`、`failed_run_requests=[]`。
- 既有响应工作台 14 项回归通过，包括真实任务切换、追溯、图形网络、局部失败重试与手机布局。

新检查命令：

```powershell
python scripts/check_metabolism_frontend.py --url http://127.0.0.1:8000
```

浏览器环境使用安装了 Playwright/Chromium 的 Python；后端测试使用项目 `.venv`。证据与修复截图在 `reports/frontend/metabolism-fix/`，检查使用历史合成记录与已有真实 AAMP 运行，没有生成新预测或修改模型/科学数据。

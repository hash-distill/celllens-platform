# 功能前后对比验收

日期：2026-10-09。已完成用户要求的一期功能可视化，参照《相近系统调研.md》中“变化列表—网络—证据钻取”的交互思路，使用 CellLens 当前真实输出实现。

## 已实现

- 工作台新增“功能前后对比”：`/workbench?run=<run_id>&tab=function`。响应概览提供入口；随机二维投影改为可展开、按需加载的辅助视图。单细胞状态页签保留。
- 左侧展示本次已评分任务，支持分类、搜索、名称/变化幅度排序与 50 项分页，标明全量有效任务或 Top 摘要。
- 中间展示一个任务、当前选中反应及其全部关联基因。对照/预测使用相同节点位置和同类色标；变化量使用正负对称色标。没有把基因、反应和任务的不同单位混用。
- 保存真实观测时可切换预测/实测；实测均值按对照均值加保存观测差值恢复。无实测时不出现该按钮。
- 右侧提供鼠标/键盘选中节点的前后数值、变化、原始 GPR、官方全部基因/影响加权完整性、缺失基因、冻结版本和哈希；真实回放链接原始真实运行。
- 全部反应分页、全部基因列表与完整关联 JSON 导出。快速切换会取消旧请求，局部失败可重试；合成、缺失与损坏记录不自动生成替代网络。
- 演示第三章复用功能界面；SVG 节点空格键操作不触发演示自动播放。

后端 `task-trace` 增加 `scope=all`，读取该任务的完整保存关联；默认 `scope=top` 保持旧限额行为。所有分数、GPR、观测差值和数据库来源保持原记录，仍执行冻结产物哈希与身份校验，不借用当前知识库替代历史版本。接口及 OpenAPI 已同步。

## 真值核对

| 细胞背景 | 本轮浏览器使用的真实回放 |
|---|---|
| K562 | `run_2d7de9d129904b63` |
| RPE1 | `run_2151b0c415484f8e` |
| Jurkat | `run_4a24afcd5b084acf` |
| HepG2 | `run_0895eccf20f8405d` |

另检查 HepG2 原始实测诊断 `run_9454c770db3842a1`、HepG2/ACD 在线运行 `run_c76a0442621c4e0d` 及旧 K562/MYC 合成运行 `run_b69b0a932fa84675`。

四背景回放的节点分数与本次冻结 `task_trace.json` 核对一致；对照/预测、预测/实测坐标逐节点一致。ACD 无观测，不显示实测按钮。ACD 的 ENO3、未评分 FBA 保留为缺失，不画成零。

完整性例证：ACD 赖氨酸降解保留 92 个关联反应，分页为 50+42；`NADH2_u10m` 保留全部 46 个关联基因，突破旧 30 项显示上限。导出的 JSON 保留 92 个反应及相同数据库来源哈希。

## 检查结果

| 检查 | 结果 |
|---|---|
| 新 API 测试先失败后通过 | 原接口没有 scope 字段；实现后任务追溯 13 项通过 |
| `.venv/Scripts/python.exe -m pytest backend/tests -q` | 120 passed，6 项依赖弃用/语法警告 |
| Ruff：backend 与本轮浏览器脚本 | 全部通过 |
| BasedPyright：backend | 0 errors、0 warnings、0 notes |
| `npm run typecheck`、`npm run build` | 通过 |
| `node scripts/test-function-network.mjs` | 有限值、零/缺失、实测恢复、独立色标、数值改变后坐标稳定、101 基因完整保留、文字对比度通过 |
| `python scripts/check_function_frontend.py` | 15 组检查通过，页面异常和意外 HTTP 错误均为 0 |
| 显示检查 | 1920、1440、900、390 像素均无页面溢出；桌面/手机截图人工查看，缺失节点文字额外复核 |
| 历史产物保护 | 584 个既有运行文件 SHA-256 全部保持，无缺失 |
| 文档、OpenAPI、差异格式 | 已同步；`git diff --check` 通过 |

浏览器还测试分类/搜索空结果、任务分页、鼠标和键盘节点选择、辅助投影展开、演示绑定来源、合成网络缺失、注入 500 后局部重试以及旧响应不得覆盖新选中任务。旧导航/投影/四背景检查脚本已适配显式展开和演示第三章，本轮做静态检查，没有重复其创建实验步骤。

构建仍提示旧三维 `TraceNetwork` 分块大于 500 kB；此次 SVG 功能视图不依赖该三维模块。后端的依赖弃用提示未影响通过结果。

## 产物

- [操作说明](../guide/FUNCTION_WORKSPACE.md)
- [浏览器检查明细](../../reports/function-visualization-2026-10-09/browser/checks.json)
- [桌面页面](../../reports/function-visualization-2026-10-09/browser/ACD-function-1920.png)
- [手机页面](../../reports/function-visualization-2026-10-09/browser/ACD-function-390.png)
- [真实预测/实测示例](../../reports/function-visualization-2026-10-09/browser/HepG2-observed.png)
- [完整关联导出](../../reports/function-visualization-2026-10-09/browser/exported-trace.json)
- [历史产物保护结果](../../reports/function-visualization-2026-10-09/preservation.json)
- 备份位于 `reports/function-visualization-2026-10-09/backup/`，保留本轮主要修改文件的原内容。

## 科学范围

本次完成显示、交互和证据追溯，不改变模型、预测结果、实验划分或既有准确性指标。图中连线是知识库关联，图中位置是阅读布局；不宣称代谢通量、形态、空间位置、因果驱动或统计显著性。使用完整关联不代表整个代谢库已得到可靠评分；覆盖率也不等于模型置信度。独立留出验收仍按原诊断协议状态展示。

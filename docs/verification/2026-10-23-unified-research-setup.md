# 统一研究分析实验设置

日期：2026-10-23。

## 当前行为

- `/research` 为研究分析的统一入口，在“实验类型”中选择实测分析或模型预测，默认实测分析。
- 类型切换保留细胞背景和扰动；实测采样上限、实测种子与预测采样人数、预测种子分别保存在会话内草稿中。
- 实测表单仍核验固定源覆盖，预测表单仍核验背景就绪状态与支持的扰动列表。
- 实测使用 `POST /api/v1/measured/analyses`；预测使用 `POST /api/v1/runs`，`mode=online`。两类结果继续保留各自来源与结果地址。
- 数据目录、首页、实验记录、新建入口和预测参数复用接入统一页面。
- `/measured?...`、`/workbench?...` 兼容原查询参数；`/workbench?run=...` 跳转对应 `/runs/:runId`。
- 提交中禁用实验类型切换；实测创建响应不确定时，保留核对记录与手动恢复提交的操作。

## 变更范围

新增 `ResearchView.vue` 与 `MeasuredSetup.vue`。原 `MeasuredAnalysisView.vue` 保留实测结果展示、轮询、取消、重试、来源与下载，设置表单移到新组件。预测结果继续使用原结果组件。后端仅增加 `/research` 的 SPA 入口，不修改分析或预测计算接口。

实施前相关已有源码保存在 `output/research-setup-source-backup-20261023/`，原工作区已有未提交修改未被重置。

## 验证证据

1. `npm.cmd --prefix frontend run typecheck` 通过。
2. `npm.cmd --prefix frontend run build` 通过，含再次类型检查；Vite 提示已有大型 chunk，不阻断构建。
3. `node --test frontend/scripts/test-research-records.mjs frontend/scripts/test-measured-assistant.mjs frontend/scripts/test-run-overview.mjs`：16 项通过。
4. `.venv/Scripts/python.exe -m pytest backend/tests/test_system_integration.py -q`：7 项通过，含统一页面与 API 404 隔离检查；出现现有依赖弃用提示。
5. Ruff 检查改动的 Python 文件通过，新浏览器检查脚本格式检查通过。
6. `python scripts/check_research_setup_frontend.py`：10 组浏览器检查通过，页面脚本错误为 0。浏览器脚本使用系统 Python 中已有的 Playwright。

浏览器范围：类型切换与独立参数草稿、刷新恢复类型与组合、预测结果参数复用、旧链接、数据目录预填、缺失实测时禁止提交、预测服务不可用时实测仍可用、采样数值验证、背景变化清除旧基因、明暗主题及 1280px 桌面无横向溢出。

两次创建请求使用浏览器拦截测试响应，验证实际前端发送的不同接口与请求体及结果页跳转；没有提交真实实验或执行新的模型推理。另通过真实服务打开各一条已有已完成实测/预测结果，确认结果页仍可渲染，记录总数保持预测 6、实测 7。此验证属于界面与接线回归，不代表新的科学计算或模型质量验证。

证据：`reports/research-setup-2026-10-23/checks.json` 及同目录截图。

## 运行状态

已重启本机 8001 服务，`/research` 可直接打开；健康与就绪接口返回 200，数据库、worker、GPU 就绪。重启前确认没有正在运行的实测或预测任务。

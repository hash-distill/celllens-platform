# 代谢任务与基因中文补全验收

日期：2026-10-21

## 修复内容

原覆盖页只有 7 个完整覆盖任务配置了双语说明，其余任务回退为英文；基因名称也只有 `name_en`。

现在共用 `backend/app/resources/biology_zh.json` 作为显示词表：

- 冻结数据库的 218 个任务全部提供中文译名及中英文说明；原有 7 个具体反应步骤的来源和解释保留。新增任务说明按冻结任务标题解释，不增加知识库以外的关联。
- 当前四个模型面板展示的 138 个代谢基因全部提供中文释名，另补 ALDOA。中文释名按已验证的 HGNC 身份匹配，保留现用符号、数据库旧名称及英文原名；没有身份依据时不猜测名称。
- 全部 96 个不同的任务 System／Subsystem 名称提供中文显示。
- 覆盖列表、基因详情、关联任务、中文搜索和基因 CSV 使用新译名。结果页的任务列表、图表、追溯、分类选择、逐细胞指标选择及实验比较同步使用同一词表。
- 前端构建缓存包含共用词表，单独更新词表也会触发 `build:if-needed` 重建。

标准基因符号及知识库 ID 继续保留；中文释名是界面翻译，不是 HGNC 官方批准名称。

## 验证结果

- 后端相关测试：18 项通过，包含全部冻结任务、四个面板的已覆盖代谢基因、旧基因名称的显式 HGNC 身份及全部任务分类的中文完整性。
- `node --test frontend/scripts/test-build-cache.mjs`：2 项通过，验证更改共用译名会使前端缓存失效。
- 前端类型检查与生产构建通过；`build:if-needed` 已验证重建路径。
- Ruff 与 BasedPyright 检查通过。
- `scripts/check_coverage_frontend.py`：方法数据导航、两张架构图、任务覆盖、中文基因搜索及双语 CSV 下载通过；无页面错误、无写请求。
- 已有 4 条 ALDOA 实验的功能列表、任务分类、中文搜索、任务详情和评分表通过浏览器验证；实验数保持 4 条，未创建新预测。
- 冻结数据库来源哈希、931 个基因身份与关联、218 个任务的关联与覆盖计数保持一致。冷启动重算的浮点舍入差异最大为 `8.88e-16`，检查容差为 `1e-12`。本次没有修改原始知识库、模型或实验结果文件。

本地数据库与服务原先未运行，已使用现有 `start_system.ps1 -Mode Production -SkipBuild -StartLocalMysql` 启动，实际验收地址为 `http://127.0.0.1:8000`。

## 证据文件

`reports/bilingual-completeness-2026-10-21/` 中保存：

- `coverage-before.json` / `coverage-after.json`：修复前后目录响应。
- `scientific-fields-check.json`：身份、知识库来源与关联／覆盖字段核对。
- `browser/checks.json`：覆盖目录的浏览器验收。
- `result-browser/checks.json`：4 条已有实验的中文结果验收。
- `result-browser/*-function.png`、`gene-bilingual.png`、`partial-task-bilingual.png`：页面截图。
- `source-before/`：本次修改前的相关文件副本。

词表维护说明见 `backend/app/resources/README.md`。

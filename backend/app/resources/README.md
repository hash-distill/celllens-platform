# 生物学界面译名

`biology_zh.json` 是后端基因／任务介绍和前端结果图表共用的中文显示词表。

- `task_names`：冻结 human Recon2 的全部 218 个任务名称。
- `gene_names`：当前四个模型面板中展示的 138 个代谢基因，以及 ALDOA，按 HGNC 现用符号登记中文释名。
- `groups`：冻结任务表的全部 96 个不同 System／Subsystem 名称。

译名依据本地冻结任务标题和 HGNC 英文名称整理，仅用于界面说明。标准基因符号、HGNC ID、英文原名、知识库关联和评分结果均保留。中文释名不是 HGNC 的官方批准名称，不根据译名增加功能分类或推断生物学作用。

`gene_education.py` 保留原有 7 个具体反应步骤的来源和双语解释，为其他任务提供基于原任务定义的双语说明。没有身份依据的基因不猜测中文名称；新增面板或数据库任务需补充词表并通过完整性检查。

前端从此文件导入显示词表。构建缓存也将此文件计入指纹，词表变更后 `build:if-needed` 会重新构建。

相关检查：`backend/tests/test_gene_education.py`、`frontend/scripts/test-build-cache.mjs` 和 `scripts/check_coverage_frontend.py`。

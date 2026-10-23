# 方法数据页面验收

日期：2026-10-21。

## 页面与入口

- 顶部增加“方法数据”，首页“了解方法与数据”进入 `/methods/models`；`/about` 继续提供操作说明。
- `/methods/models`、`/methods/backgrounds`、`/methods/coverage` 分别提供“01 模型方法”“02 细胞背景”“03 覆盖范围”，共享标题、独立子路由并按需加载。模型方法页介绍 STATE ST-HVG 与 scCellFie 的输入、输出和接入关系，包含两张原生 SVG 示意图和官方来源。
- 细胞背景页介绍已登记细胞背景、生物学来源、模型表达面板、可选扰动与登记观测；支持表达基因搜索和完整面板 CSV 下载，覆盖范围页提供代谢基因分类、任务说明及来源信息。
- 代谢任务可按完整、部分、未覆盖和全部任务筛选并分页。缺失基因与未映射关联分别说明，切换范围后详情选择同步更新。
- 原首页覆盖卡片及其样式已移除。旧 `/coverage` 地址保留 `cell_line`、`run`、`task` 和 hash 跳转到覆盖范围页，历史实验按其保存范围展示。旧 `/methods/data` 默认跳转细胞背景页，包含 `run` 或 `task` 时跳转覆盖范围页。

## 数据依据与性能边界

新增只读 `GET /api/v1/catalog/data-summary`。它读取当前注册信息及校验过的小型基因面板，不打开权重或表达矩阵；面板不通过校验时返回不可用状态，不编造数量。实测条目明确为登记元数据，实际比较仍执行原来的文件核验。响应不返回服务器路径，禁止 HTTP 缓存。

页面统计来自接口。本次部署四个背景的表达面板各 2,000 个基因，可选扰动各 2,024 个；当前代谢交集为 138/931 个基因，完整覆盖为 7/218 项任务、86/787 条反应。表达基因、扰动目标和代谢关联基因分开介绍；完整性不作为准确率，匹配观测不作为独立留出验证。

模型介绍页不请求代谢覆盖或数据概览。细胞背景页只请求轻量数据概览，覆盖范围页独立加载原有官方完整性计算；首次科学库初始化仍可能较慢。本次没有修改官方完整性算法或其数据。两张图使用轻量 SVG，无 WebGL、实时滤镜或持续动画。

统计卡片仅展示实际覆盖数量：表达面板基因、已覆盖代谢基因、完整覆盖任务与完整覆盖反应；不展示知识库总量分母。任务介绍标签不显示整个知识库任务总数，实际覆盖计算与任务筛选保持原有含义。

## 共享覆盖依据

当前 K562、RPE1、Jurkat、HepG2 的有序 2,000 基因面板文件完全相同，SHA-256 为 `1846634939efbc2424c67d6b30bf80c4bd7cbfceca672ea7de29741916b6144e`。在同一冻结数据库下，基因、任务和反应的覆盖明细也一致。因此覆盖页仅展示一份共享 STATE 输出面板，标明适用的四个背景，移除重复的背景下拉框。各背景的模型权重、对照与观测独立登记；共享覆盖不意味着这些数据或预测相同。

覆盖接口为各模型返回经过校验的 `panel_sha256`，未通过校验时返回 `null`。前端仅按有效哈希合并，遇到不同面板时显示面板分组选项，未校验项独立保留。相关回归包含不同、相同及被篡改面板；浏览器响应夹具验证不同面板分组界面，未修改真实资产。

浏览器回归还定位并修正了 Windows 环境下 WebP 可能被识别为 `application/octet-stream` 的问题，静态服务现在对 WebP 明确返回 `image/webp`，保留原有不可变缓存设置。

## 验证

- 新增数据概览、页面直达、共享面板校验和 WebP 响应类型回归，先确认缺少接口/路由时失败，再实现。与现有覆盖、静态服务和启动边界合计 **20 项通过**；Ruff 与 BasedPyright 通过。
- 前端 TypeScript 检查与生产构建通过。现有按需加载的 Three.js 大 chunk 提示保留，没有提高阈值掩盖提示。
- 浏览器实际操作覆盖：首页入口、顶部导航、三个子页切换、两张图、刷新直达、动态计数、表达基因 CSV、代谢基因查询、任务范围与分页、四背景中英文详情和来源、旧任务链接、不同或未校验面板分组的响应夹具、失败保留导航与重试。
- 桌面主题检查覆盖 1280/1440/1920px、两种主题，共 **72 组**页面/窗口组合；页面错误与 POST 为 0。正式服务重新执行功能检查，实验记录数量保持不变。
- 首页正常动画回归仍通过：两主题采样约 59–60 fps，首屏图片编码体积 29,951 字节；未为介绍页增加首页数据加载。
- 确认活动/可恢复任务为 0 后更新正式服务，数据库、worker 与 GPU 开关的就绪检查返回 200；`/methods` 及三个子页均可直接访问。

本轮没有提交科学实验、重新推理或执行后端全量回归。数值是当前部署的接口结果，迁移部署后应重新获取，不作为所有环境的固定值。

本轮拆分的功能记录和截图位于 `reports/methods-data/`，布局记录位于 `reports/methods-data-layout/`。上一版原始记录与截图位于忽略目录 `reports/methods-data-2026-10-21/`，包含预览和正式服务的 `checks.json`、模型/数据页截图，以及首页回归 `metrics.json`。优化前正式前端构建保存在该目录的 `production-before-dist/`。

## 重复检查

在仓库根目录运行，浏览器检查使用已安装 Playwright/Chromium 的 Python 环境：

```bash
uv run --no-sync pytest backend/tests/test_methods_data.py backend/tests/test_coverage_catalog.py backend/tests/test_system_integration.py backend/tests/test_startup_performance.py -q
python scripts/check_coverage_frontend.py --url http://127.0.0.1:8000 --output reports/methods-data
python scripts/check_homepage_performance.py --url http://127.0.0.1:8000 --output reports/methods-data/homepage
```

源方法依据：[STATE 官方项目](https://github.com/ArcInstitute/state)、[scCellFie 官方文档](https://sccellfie.readthedocs.io/en/latest/)。页面图示是当前接入分支的说明，不声称复刻原论文完整架构。

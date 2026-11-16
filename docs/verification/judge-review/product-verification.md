# 产品修复验收

活动源码：`D:\全球校园人工智能精英大赛\celllens-national`。本次是独立验收，先按 `product-review.md`、`修复清单.md` 和 `product-fixes.md` 核查要求，再进入代码质量阶段。未使用 C 盘旧副本，未修改生产代码、安装依赖、重启服务或提交 Git。本代理开始时 8028 是旧构建，本报告未把该旧页面当作修复后的页面证据；随后的重建和浏览器验收由主任务独立记录。

当前结论：**两阶段源码与范围内业务逻辑验收通过，发现的 3 项 P2 均由主任务修复并经本代理重验关闭，未发现未关闭的范围内 P1/P2。** 桌面、窄屏、停靠 AI 面板与键盘焦点仍需主任务在包含最终改动的新构建上进行真实页面验收；不能据本报告宣称完整产品视觉验收通过。

## 第一阶段：要求核对

| 要求 | 验收结果及证据 |
|---|---|
| 顶层两任务、公开/自有属于实测来源 | 通过源码和 Vue setup 行为核验。ResearchView 顶层只有 measured/prediction，import 映射实测任务的自有来源；Home 对应两张动作卡，结果能力单独介绍。 |
| 三种旧 type 深链、三步核对、提交锁定 | 现有行为测试通过。合法初始参数进入草稿，无效参数不覆盖；三类提交状态均使任务与来源按钮禁用。浏览器更换路线会清理核对状态，导入卸载会中止客户端请求并释放父级锁定。 |
| 切换来源保留当前输入 | **修复后通过。** 新行为测试覆盖用户修改实测参数后公开→自有→公开，以及与预测任务往返后各自种子保留。详见问题 1。 |
| 自有 H5AD 准备流程可执行 | 通过。说明部署者放置文件、真实受控目录、相对路径、不提供浏览器上传；字段表包含 X 尺度、分组列、唯一 ID 和原始计数全库分母。实际提取页面的 Python 代码，在临时 2 细胞 × 2 基因合成 fixture 上编译并运行，正确打印 shape、obs 列、基因及分组数量，前后源文件 SHA-256 相同。此处仅验证辅助代码，不构成真实科研数据分析验证。 |
| local/private 目录可用、public 不泄露目录 | 通过直接函数执行和源码核验。local/private 在启用且目录存在时返回解析后的配置目录；public、禁用、目录不存在均不返回。HTTP 中间件对 private 先验证身份，public 不开放 imports/capabilities 与创建接口。 |
| public 不露出私人操作 | Home、ResearchView、DataCatalog、UtilityRail 的核心私有操作均按 read_only 隐藏或切换公开入口；目录下载函数也直接阻止 public 调用。About 仍是通用指南，其创建入口进入只读研究说明，不会绕开权限。 |
| 图谱查询前置、来源与空状态准确 | 通过。标题后直接是组合查询；同一路由 query 更新可见筛选，分析入口保留背景与目标；覆盖统计、关系示意后移，公开子集和未知来源提示保留。 |
| 工具栏安全区与窄屏语义 | 源码符合布局方案：全局直属页面桌面 72–80px 留白，900px 以下工具栏改为文档流页尾折叠区；按钮含可见名称、aria-expanded/controls，桌面 AI 停靠位移已覆盖。**未完成真实布局与键盘验收**，不能据此声称无覆盖、无横溢或完整无障碍通过。 |
| 保留绿色层次并提高字号 | 源码保留主题变量、主视觉、任务卡；相关正文约 14px，主要辅助说明约 12–13px。实际投屏可读性及全部对比度未测量。 |
| About 与最终能力一致 | **修复后通过源码核对。** About 已明确 ER/Golgi 使用冻结知识库的显式分类，未注释结构不推断关联，且不构成形态、定位或活性测量。详见问题 2。 |

## 发现的问题

### 1. P2：来源切换恢复旧 URL 采样值，覆盖用户的新输入

状态：**已修复并重验关闭。** `choose()` 当前按目标任务写入编辑后的草稿值，import 清除旧 URL 的采样字段；新增回归确认 `512/23 → import → measured → prediction(seed=11) → measured` 保留实测 `512/23` 与预测 `11`。

修复前证据位置：`frontend/src/views/ResearchView.vue:28` 的 `choose()`，以及当时 `:36` 的采样参数 watcher。以下为初次发现时的复现与原因。

独立执行真实 Vue setup/watch 的复现：

1. 初始查询为 `?type=measured&cell_line=K562&perturbation=ALDOA&max_cells=64&seed=7`。
2. 用户将 `draft.measuredMaxCells` 改为 `512`，将 `draft.measuredSeed` 改为 `23`。
3. 调用页面的 `choose('import')`，等待 Vue 更新，再 `choose('measured')`。
4. 实际草稿退回 `max_cells=64, seed=7`，不是用户最后编辑的 `512, 23`。

原因是 `choose()` 继续传播 route.query 的旧采样参数，随后的 query watcher 再次把它们写入草稿。影响从已有参数进入、调整分析后切换来源的用户；核对弹窗会显示旧值，存在误用采样条件的风险。建议内部切换保存当前任务的草稿，只对明确的外部深链更新重新应用参数，并增加“编辑后往返切换”行为测试；同时确认预测种子不会误用实测种子。

### 2. P2：使用说明否认本轮已实现的结构分类导航

状态：**已修复并重验关闭。** 当前 About 已说明结果页内质网或高尔基体的显式分类导航，保留无法映射时不推断关联及非形态/定位/活性测量边界。

修复前证据位置：`frontend/src/views/AboutView.vue` 中“从任务评分回到证据”后的 guide-note；对应 `frontend/src/components/ResearchCanvas.vue:90` 起的 `relatedTasks` / `select-task`。以下为初次发现时的不一致。

当前实现允许 ER/Golgi 沿冻结知识库的显式分类进入本记录任务，其他结构没有可靠映射时说明不可用。指南却笼统写成所有点击均仅切换说明，容易使用户错过本轮新增导航。建议准确区分：首页学习示意、结果页 ER/Golgi 的显式分类导航，以及未注释结构；保留“不表示形态、空间定位或细胞器活性测量”的边界。此项属于最终集成文案核对，没有把并行结果组件的暂时测试错误算作产品失败。

## 已执行验证

- `node --test scripts/test-product-navigation.mjs scripts/test-methods-pages.mjs`：首次 9/9，通过增加采样保留回归后的重验为 **10/10 通过**。
- `node --test --test-name-pattern="controlled import|import validation|research entry|read.only|public" scripts/test-national-research.mjs`：6/6 通过，包括 public 目录阻止私有 CSV、导入取消和实际重试来源保留。
- `.\.venv\Scripts\python.exe -m pytest backend/tests/test_research_contract.py -k "import_is_opt_in_confined_and_bounded or import_does_not_overwrite or import_retains_verified_background or import_rejects_invalid_science" -q`：11/11 通过，15 项未选择。唯一警告来自刻意设置重复 var_names 的拒绝用例。
- 页面准备代码：提取实际 `preparationScript`、Python compile、执行合成 H5AD、前后 SHA-256 一致。
- `capabilities()` 独立调用：local/private/public，以及 disabled/missing-root 五种情况符合目录披露边界。
- `.\.venv\Scripts\python.exe -m pytest backend/tests/test_measured_trace.py::test_import_preparation_location_is_never_disclosed_by_public_mode backend/tests/test_durable_workers.py::test_private_auth_session_and_cpu_readiness backend/tests/test_durable_workers.py::test_public_is_allowlist_not_get_based_permission backend/tests/test_durable_workers.py::test_private_missing_token_fails_closed -q`：**4/4 通过**，仅既有 Starlette/httpx 与 anyio 弃用警告。
- 本范围 `git diff --check` 通过。
- UtilityRail 独立 Vue setup 行为复验：展开后调用实际 `closeTools()`，确认收起状态；可见触发器在 `nextTick` 后收到 focus，隐藏触发器和空引用均不触发 focus。当前 Escape 事件已绑定该函数，按钮 ref 绑定一致。

验证没有运行真实用户数据导入、创建分析、外部 AI 请求、下载真实导出、生产构建或浏览器端验收；全局类型检查和最终构建由主任务统一执行。结果摘要、任务成员证据、导出内容和科学诊断由对应验收范围负责。

## 第二阶段：代码质量与边界

在第一阶段两项问题修复后继续检查：任务/来源切换状态、草稿与查询同步、异步请求取消、导入就绪条件、public 操作限制、目录披露、布局选择器、折叠工具栏可访问名称和使用指南。未发现新的 P1；发现并复核关闭下列 P2。

### 3. P2：窄屏 Escape 收起工具栏没有恢复触发器焦点

状态：**已修复并完成源码/行为重验关闭。** 当前新增 toggle ref 和异步 `closeTools()`，等待 `nextTick` 后只向可见的触发器返回焦点；实际执行可见、隐藏、空引用三种分支均符合预期。真实浏览器的最终键盘操作由主任务验收，未把 mock 触发器的 focus 调用等同于浏览器焦点已确认。

修复前证据位置：`frontend/src/components/UtilityRail.vue` 当时的 `@keydown.esc="expanded = false"` 及窄屏 `.rail-tools{display:none}`。以下为初次发现时的代码路径判断。

展开工具栏并把焦点移到内部按钮/链接后，Escape 事件会收起容纳当前焦点的内容，但没有将焦点返回“页面工具”按钮。代码中没有触发器 ref 或相应 focus 操作，收起后缺少稳定的键盘继续位置。建议 Escape 收起后，在触发器可见的窄屏模式将焦点返回触发器；避免桌面模式把焦点移到隐藏按钮。需要在新构建窄屏页面验证展开→Tab 进入→Escape→焦点返回及下一次 Tab 行为。本项为源码路径判断，尚未宣称真实浏览器复现。

其余质量检查未发现可确认的范围内 P1/P2。测试使用真实 Vue setup/watch，但替换网络及组件渲染，不覆盖浏览器布局、焦点与读屏软件；源码和行为测试不能代替新构建上的真实页面验收。

## 主任务新增视觉修复的登记

主任务反馈其浏览器检查发现结果标签区因原 `.tab` 的 `margin-bottom:-1px` 产生细小纵向滚动条，随后在 `national.css:110` 添加 `#app .result-tabs { overflow-y: hidden; }`，在 `:111` 添加标签 `margin-bottom: 0`。本代理已核对这两条规则存在且范围 diff 检查通过；没有独立观察该视觉问题或修复后的页面。应在包含 UtilityRail 最终修改的重建后，将结果标签栏和窄屏 Escape 焦点一起完成浏览器复核。

# 前端主题整合验收（2026-10-20）

## 来源与整合范围

- 设计来源：`origin/new_frontend`，提交 `3da8883`（refresh frontend experience and theme support）。
- 本地功能基线：`0a98ac7605861e27230361ee9cde9fd74218d139`。先保存原有未提交的系统实现，再迁移视觉设计。
- 整合内容：首页背景与图片、分段介绍和入口卡片、全局浅深色变量、组件及三维知识网络的主题样式。
- 保留内容：现有后端、数据库迁移、模型与数据登记、API、状态管理、路由、类型、结果来源标签、AI 解读、设置、快捷工具、覆盖目录和实测比较。
- 未直接采用设计分支中的后端删除、助手和设置删除、新建回放/对照模式、旧结果工作流及重复主题状态库。

## 适配与修复

- 仍用 `stores/preferences.ts` 管理主题；页头、快捷工具、设置页、系统外观与 ECharts 使用同一状态。
- 五张 PNG 原始内容与设计提交逐字节相同，移至 `frontend/src/assets/theme/` 后由 Vite 输出带哈希的 `/assets/` 地址，适配现有后端资源服务。
- 首页不虚构可用背景数，不重新开放已移除的实验模式；继续保留覆盖目录入口和科学解释边界。
- 修复 Vue scoped/global 选择器误作用于整个 HTML 文档、手机滚动按钮遮挡助手、深色主按钮与证据不足标记的文字对比度问题。
- 实测比较浏览器检查区分“明确没有实测细胞”和“本次尚无已准备比较”，不将未知数量写成零。

## 已验证结果

- 后端：`uv run --no-sync pytest -q`，245 passed，6 个依赖告警，286.50 秒。测试运行期间后端实现未发生迁移改动。
- 构建：`npm --prefix frontend run build` 成功，包含 TypeScript 检查；保留已有三维网络 chunk 大于 500 kB 的提示。
- 静态检查：`uv run --no-sync ruff check backend scripts` 通过；BasedPyright 为 0 errors / 0 warnings / 0 notes；`git diff --check` 通过。
- 原始内容核对：165 个后端、API、stores、router、types、utils、登记数据与配置文件与迁移前 SHA-256 相同；5 张 PNG 与设计分支内容一致。
- `python scripts/check_records_status_frontend.py` 通过：真实服务器历史、结果直达与刷新、服务状态、手机和平板布局，无页面异常。
- `python scripts/check_assistant_frontend.py` 通过：主题持久化与系统同步、设置、快捷工具、当前实验绑定、只读摘要和受控模拟的模型连接/解读。模拟响应不代表调用真实外部大模型。
- `python scripts/check_measured_comparison_frontend.py` 通过：7 个真实历史实验、可用与不可用状态、指标和下载、不同窗口宽度，无页面异常。
- `python scripts/check_theme_frontend.py` 通过：2 种主题 × 4 种宽度（390 / 768 / 1100 / 1440）× 10 个页面/结果视图，共 80 组；主题持久化、系统外观同步、资源 PNG 签名、页面透明度、按钮对比度、滚动按钮与助手位置、已有实验结果和 AI 绑定均通过。页面异常为 0，POST 请求为 0，验收前后实验记录总数均为 7。

## 证据与运行边界

本地证据目录：`reports/frontend-integration-2026-10-20/`，包含构建、静态检查、内容保护清单、图片 SHA-256 与页面截图。完整源码备份目录为项目上级的 `.frontend-integration-backup-20261020_231120/`；包含 ZIP、SHA-256 清单、原始差异和 refs。

浏览器验收使用真实本地 MySQL 历史记录和生产静态资源，验收服务关闭推理 worker；没有提交新的 GPU 推理任务，也没有改写科学结果或实验数据。结果页面通过不等于重新验证模型预测准确性。

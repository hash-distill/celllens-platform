# PDF 报告与页面文案验收

2026-10-19，本地主服务 `127.0.0.1:8000`。

## 结果

原导出接口直接返回 `report.html`，前端也用文本读取并包装 HTML Blob，因此下载为网页。现默认返回真实 PDF，响应 `application/pdf`，附件名 `celllens-{run_id}.pdf`；前端使用 Blob 二进制读取并检查 PDF 文件头。

报告包括实验参数、保存的主要基因和代谢任务结果、匹配实测指标（存在时）、模型/数据/版本与 Manifest SHA-256，以及已准备的表达、代谢 UMAP 图。导出不重新推理或拟合 UMAP。历史 HTML 和科学产物保留。

实际排版检查及独立代码复核发现，历史摘要没有保存基因对照/预测均值。现从 Manifest 校验过的 `gene_deltas.csv` 补齐；任务字段可读取同样校验过的 `task_trace.json`。未改写摘要。加入缺省均值及来源被篡改拒绝导出的回归测试。

移除用户指定的缺少扰动实测、观测列隐藏、非零完整数值筛选和纯知识库关联隐藏等提示，以及相关页面的同类重复文案；简化空态。页面实际数值和数据角色列名继续使用原结果。

## 验证证据

- 后端全量：244 passed；随后修复均值空列并新增回归后，报告/API 专项 10 passed。
- Ruff 全应用和测试通过；BasedPyright 0 errors / 0 warnings；前端生产构建通过。现有第三方弃用提醒与较大 chunk 提醒仍在。
- 7 条正式历史运行逐个实际请求导出，全部为可解析的 5 页 PDF；每条运行的 17 个原始顶层文件哈希完全一致。结果见 `reports/pdf-report-2026-10-19/downloads.json`。
- ATP5PD 无实测运行和 ALDOA 有实测运行均已核验。PDF 含正确的基因均值；HepG2/ALDOA 报告含 Pearson 0.26261、MSE 比值 1.5529 及匹配评价细胞数。
- 已将 ATP5PD 报告全部 5 页渲染为 PNG 并逐页检查，另检查 HepG2/ALDOA 实测指标页；中文、长任务名称、跨页表头和两张科研图无裁切。
- 浏览器实际点击“导出 PDF 报告”，下载路径 `C:\Users\zhs14\Downloads\celllens-run_68521813f0ce4507 (1).pdf`，文件解析及均值检查通过。结果页、基因响应和代谢功能页未发现用户指定文案。
- 页面截图：`reports/pdf-report-2026-10-19/result-page.png`。示例报告：`reports/pdf-report-2026-10-19/celllens-run_68521813f0ce4507.pdf`。
- 已更新 API 文档和 OpenAPI 快照。主服务 `/api/v1/health`、`/api/v1/ready` 均为 200。

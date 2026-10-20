# 响应概览 UMAP 验收

日期：2026-10-11。

## 变化与方法

响应概览默认展开共同 UMAP 科研图；单细胞状态及基因详情继续使用对照参考 PCA。图中保留群体叠加、逐细胞指标着色和完整有效群体的 ECDF/统计，切换指标不重新拟合坐标。SVG/PDF/PNG/JSON 的方法、坐标轴和文件名区分 UMAP 与 PCA。

UMAP 复用冻结来源校验和逐细胞表达重建。对照、预测和可用实测群体按原数量联合拟合最多 50 个主成分，随后共同 UMAP；不从二维 PCA 图生成 UMAP。参数为邻居数 min(30, n−1)、min_dist=0.3、Euclidean、random_state=42、n_jobs=1。UMAP 本身不报告解释方差，JSON 包含实际参数与依赖版本。解释范围为本实验的表达邻域结构，不将距离、密度或分隔程度解释为效应量或预测准确率，不比较独立拟合实验之间的坐标。

接口 `cell-state` 和 `cell-state/figure` 增加 `embedding=pca|umap`，默认仍为 pca；UMAP 缓存独立于 PCA，读取缓存也重新校验冻结输入。图形计算不写入或替换原实验产物，不触发模型推理或代谢评分。新增 report 依赖及对应锁定元数据；当前环境已有 umap-learn 0.5.12。

方法依据：[UMAP 参数](https://umap-learn.readthedocs.io/en/latest/parameters.html)、[固定随机状态](https://github.com/lmcinnes/umap/blob/master/doc/reproducibility.md)。实现前经 Context7 查询官方仓库文档。

## 验证结果

- `backend/tests/test_cell_state.py`：19 项通过，验证真实 UMAP 的有限坐标、三来源对齐、确定性、着色指标独立、数值与 PCA 不变、冻结文件保全、篡改拒绝及导出轴标签。既有 PCA、来源、分布和导出检查继续通过。
- 前端类型检查、生产构建、Ruff、basedpyright 和差异空白检查通过。构建保留已有 TraceNetwork 分块大小提示。
- 浏览器在两个现有真实实验 `run_f4a6276b0aff42aa`、`run_469edf3453324f66` 核对默认展开 UMAP、实际请求方法、不同指标坐标不变、UMAP JSON/SVG 导出和详细页 PCA。390/768 像素及深色页面通过，无页面脚本错误。
- 浏览器读取前后比较所有原实验产物 SHA-256 和实验记录响应，均未改变。

验收脚本：`scripts/check_umap_overview.py`。证据：`reports/umap-overview-2026-10-11/acceptance.json`、实际 UMAP 数据和页面截图。

## 运行状态

当前 8000 端口主服务运行的是此前加载的代码。自动审批拒绝了重启操作，仅返回 `blocked by policy`，没有说明具体原因。使用独立 8011 服务完成真实数据与页面验收，该服务关闭模型工作线程以避免重复执行任务。前端会拒绝把旧服务返回的 PCA 标成 UMAP，并提示重启。主服务正常重新启动后即可使用更新；8011 可先预览现有实验结果。

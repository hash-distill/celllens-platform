# Prepared cell state implementation plan

**Goal:** 将科研图计算纳入任务进度，结果页复用已保存坐标及默认SVG。

**Architecture:** 独立准备服务负责压缩数据/默认图/清单，cell_state读取经核验的准备结果，pipeline在完成前调用。旧运行显式回填，不重跑STATE。

**Tech Stack:** 现有Python/NumPy/UMAP/Matplotlib/FastAPI、Vue/TypeScript；不新增依赖。

- [x] 添加红灯测试：清空内存仍复用数据与SVG、篡改拒绝、准备失败不完成。
- [x] 新建cell_state_preparation.py；接入cell_state和figure读取，保留历史兼容。
- [x] 接入VALIDATING进度与租约；更新前端阶段/加载说明。
- [x] 添加旧记录CPU回填脚本，完整测试及构建，核验7个已有真实结果及来源哈希。

复核修正：耗时准备移至partial正式发布前；保存使用局部数据引用，不依赖请求LRU驻留。补充发布与驱逐回归通过。现场证据见docs/verification/2026-10-19-prepared-cell-state.md。

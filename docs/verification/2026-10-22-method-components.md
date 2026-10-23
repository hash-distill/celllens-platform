# 模型方法组件图验收

日期：2026-10-22

## 变更

`/methods/models` 的两张生成 PNG 替换为原生 Vue/SVG 组件。采用白底、细线、青绿强调色和中文注释，减少装饰元素。图是依据原论文机制与当前代码整理的架构示意图，不是论文原图；矩阵色块仅表示数据维度，不是实验结果。

- `StateArchitecture.vue`：表达、扰动与批次编码相加，进入细胞集合双向注意力；表达编码的残差支路在解码前融合。标注当前 8 层、2,000 基因 ST-HVG 配置、训练分布匹配和独立 SE 的关系。
- `ScCellFieArchitecture.vue`：阈值评分公式、AND/min 与 OR/max、逐细胞决定基因特异性校正、关联反应均值。知识库分别提供基因阈值、GPR 与任务—反应映射，虚线与评分链路区分。关联基因覆盖并行核查。
- `MethodDiagram.vue`：保留放大、Escape／关闭按钮／背景点击关闭和焦点返回，下载改为真正可编辑的 SVG。导出包含图内样式与标记，不嵌入栅格图。每个实例使用独立 ID，预览与弹窗的箭头不会串用。
- 旧 PNG 源文件保留，但不再导入生产页面。保留原有方法论文与官方项目链接。

## 科学依据

- [STATE 原论文](https://doi.org/10.1101/2025.06.26.661135) 与 [官方代码](https://github.com/ArcInstitute/state)。当前四个 `models/state-replogle-*/config.yaml` 均为 `X_hvg`、gene 输出、8 层、energy 分布损失和残差预测；本地 `state/tx/models/state_transition.py` 的当前分支为 `project_out(res_pred + control_cells)`，随后非负输出。
- [scCellFie 原论文](https://doi.org/10.1101/2025.05.09.653038) 与 [官方说明](https://sccellfie.readthedocs.io/en/latest/)。本地 0.6.2 的 `gene_score.py`、`reaction_activity.py`、`metabolic_task.py` 与系统 `backend/app/engines/metabolic_engine.py` 核对了公式与运行参数。特异性分母为同一细胞中以该基因为决定基因的反应数量；任务分数是表达支持度，不是代谢通量。

## 验证

- `npm run build`：先执行 `vue-tsc --noEmit`，再进行生产构建，均通过。保留既有 TraceNetwork 分块体积提示。
- `reports/method-components-2026-10-22/verify_components.py`：1280、1440、1920 三种宽度 × 亮暗两主题 × 两张图，共 12 组。检查页面溢出、文字相交、文本越框、实例 ID、箭头引用、键盘／关闭／背景交互。全部通过，无浏览器异常，无修改请求。
- 独立 SVG XML 可解析，包含样式和可编辑文字，不含 `<image>`；脱离应用打开与截图成功，图内字号不受页面全局类影响。浏览器截图逐图检查了主链、残差支路与规则支路。
- `python scripts/check_coverage_frontend.py --output reports/method-components-2026-10-22/coverage-regression`：10 项方法数据页回归检查通过；4 个背景、2,000 表达基因、138 个已覆盖代谢基因、7 个完全覆盖任务、150 个有完全／部分覆盖的可见任务与接口保持一致。无浏览器异常或修改请求。
- SHA-256 对比：800 个既有运行文件不变；5 条实验历史完整响应不变。

验证证据、下载 SVG、亮暗截图和源文件备份位于 `reports/method-components-2026-10-22/`。

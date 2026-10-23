# 模型方法架构图更新验收

日期：2026-10-21

## 更新范围

`/methods/models` 的两张简化 SVG 已替换为使用内置 `image_gen` 生成并校正的架构图。依据方法论文与当前接入代码重绘，均为 1672 × 941 PNG。细胞图、热图和散点图用于解释结构，不代表本地实验结果。

- STATE：展开对照表达编码、扰动编码、批次编码、条件相加、细胞集合双向注意力、残差融合、表达解码及非负输出；保留基因响应、细胞状态和代谢分析的下游关系。离线分布匹配训练及独立 SE 表示模块另行标示。
- scCellFie：展开 CP10K 输入、基因阈值与基因分数公式、GPR 的 AND/min 与 OR/max 规则、反应特异性校正、任务汇总及关联基因覆盖。
- 两图均支持点击放大、Esc 关闭、关闭按钮、遮罩关闭、原始尺寸查看和 PNG 下载；关闭后焦点回到预览按钮。

## 科学内容核对

依据本地 `arc-state 0.11.1`、四个已注册模型的 `config.yaml`、代谢引擎及科学分析服务核对：

- 默认推理链路为 ST-HVG，输出 2000 基因表达；SE 未画入默认推理主链。
- 注意力作用于细胞集合，四个配置均为 8 层双向注意力。
- 残差来自表达编码器输出，在表达解码前融合。
- 离线分布匹配比较预测扰动群体与实测扰动群体。
- 基因分数为 `5 ln(1 + E_g / T_g)`；GPR 的 AND 取最小值，OR 取最大值。
- 反应特异性校正分配同一决定性基因跨多个反应的贡献。
- 知识库的三个箭头分别指向基因评分、GPR 和任务汇总。
- 完整/部分覆盖描述输入中的关联基因可用性；图中明确区分表达派生的功能支持与实测代谢通量。

方法来源：

- [STATE 官方项目](https://github.com/ArcInstitute/state)
- [STATE 方法论文](https://doi.org/10.1101/2025.06.26.661135)
- [scCellFie 方法论文](https://pmc.ncbi.nlm.nih.gov/articles/PMC12132331/)
- [scCellFie 预印本](https://doi.org/10.1101/2025.05.09.653038)

## 验证结果

- `npm --prefix frontend run build`：类型检查与生产构建通过；原有大分包提示仍存在。
- `python scripts/check_coverage_frontend.py --output reports/model-method-figures-2026-10-21/browser`：通过。检查两图加载、放大/关闭/键盘、PNG 下载、方法数据导航及原有覆盖范围功能；无页面错误、无写请求。
- `python reports/model-method-figures-2026-10-21/check_figures_desktop.py`：1280、1440、1920 三种宽度与深浅两种主题全部通过；页面无横向溢出、弹窗位于视口内、遮罩关闭可用。首页未加载这两张图片。
- 已人工查看两张生成图及浏览器放大截图，核对关键连线与文字。
- `ruff check scripts/check_coverage_frontend.py`：通过。
- `basedpyright scripts/check_coverage_frontend.py`：0 错误、0 警告；相关改动的 `git diff --check` 通过。

## 文件与生成记录

- `frontend/src/components/MethodDiagram.vue`
- `frontend/src/assets/methods/state-architecture-v2.png`
- `frontend/src/assets/methods/sccellfie-architecture-v2.png`
- `reports/model-method-figures-2026-10-21/generation-prompts.json`：初始生成提示词。
- `reports/model-method-figures-2026-10-21/correction-prompts.json`：科学细节校正提示词。
- `reports/model-method-figures-2026-10-21/figure-manifest.json`：来源、原图位置、尺寸、文件大小及 SHA-256。
- 同目录 `browser/`、`desktop/`：浏览器验收 JSON 与截图。
- 同目录 `source-before/`：修改前组件及相关文件副本。

原始生成文件保留在 Codex 生成目录，项目使用单独复制的 PNG。无需调用外部图片生成接口。
